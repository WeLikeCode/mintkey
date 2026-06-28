"""
Architecture gate: agent-secret tool modules and admin-api agent_secrets router
must never pass the plaintext secret value into audit, change-notification,
structlog, or OTel span calls.

AST-walks:
  - apps/mcp-server/src/mcp_server/tools/secret_put.py
  - apps/mcp-server/src/mcp_server/tools/secret_get.py
  - apps/mcp-server/src/mcp_server/tools/secret_delete.py
  - apps/mcp-server/src/mcp_server/tools/secret_list.py
  - apps/admin-api/src/admin_api/api/agent_secrets.py

For each module the test:
  1. Traces which local variable names bind the plaintext / submitted value
     (e.g. body.value, value_bytes, plaintext, value — see comments per module).
  2. Asserts none of those names appear as arguments inside:
       - audit_emit(...)
       - notify_change(...)
       - structlog / logging calls (bind / log / info / warning / error / debug)
       - span.set_attribute(...) / set_attributes(...)

Strategy: collect all Call nodes whose callee-name matches the forbidden
sinks, then walk their subtrees looking for Name nodes whose .id is in the
set of plaintext-bearing identifiers for that module.

Runtime canary section (bottom of file):
  - Drives the real POST create-secret and PUT update-secret handlers
    with a known canary value "CANARY-PLAINTEXT-Δ-9f3a".
  - Captures every audit_emit call via unittest.mock.patch.
  - Asserts the canary string appears in ZERO audit payloads.
  - Asserts the canary string is absent from the response body.
  - Includes proof-of-detection tests confirming the canary assertions
    would catch a hypothetical future leak.

Source: S-SEC-1; ADR-0014.4; ADR-0014.7; ADR-0025.
"""
from __future__ import annotations

import ast
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, NamedTuple
from unittest.mock import AsyncMock, MagicMock, patch

_REPO_ROOT = Path(__file__).parent.parent.parent

# ---------------------------------------------------------------------------
# Sink function names that must never receive the plaintext value
# ---------------------------------------------------------------------------
_AUDIT_SINKS = frozenset({"audit_emit"})
_CHANGE_SINKS = frozenset({"notify_change"})
_LOG_SINKS = frozenset({"bind", "log", "info", "warning", "error", "debug", "exception", "critical"})
_SPAN_SINKS = frozenset({"set_attribute", "set_attributes"})

_ALL_SINKS = _AUDIT_SINKS | _CHANGE_SINKS | _LOG_SINKS | _SPAN_SINKS


class ModuleSpec(NamedTuple):
    path: Path
    # Names that bind the plaintext/submitted value in this module
    plaintext_names: frozenset[str]
    description: str


_MODULES: list[ModuleSpec] = [
    ModuleSpec(
        path=_REPO_ROOT / "apps/mcp-server/src/mcp_server/tools/secret_put.py",
        plaintext_names=frozenset({
            # body.value — the submitted plaintext string (SecretPutRequest.value)
            # value_bytes — body.value.encode("utf-8")
            "value",
            "value_bytes",
        }),
        description="secret_put: body.value / value_bytes must not enter audit/log/span sinks",
    ),
    ModuleSpec(
        path=_REPO_ROOT / "apps/mcp-server/src/mcp_server/tools/secret_get.py",
        plaintext_names=frozenset({
            # plaintext — bytes returned by vault_client.get_agent_secret(...)
            # response  — dict that DOES contain the value key, but the dict itself
            #             is only passed to JSONResponse, not to any audit sink.
            #             We track "plaintext" as the primary bearer.
            "plaintext",
        }),
        description="secret_get: plaintext bytes must not enter audit/log/span sinks",
    ),
    ModuleSpec(
        path=_REPO_ROOT / "apps/mcp-server/src/mcp_server/tools/secret_delete.py",
        # secret_delete does not decrypt the value; no plaintext variable exists.
        # We still validate: no accidental 'value' or 'plaintext' name in sinks.
        plaintext_names=frozenset({"value", "plaintext"}),
        description="secret_delete: no value/plaintext variable must appear in audit/log/span sinks",
    ),
    ModuleSpec(
        path=_REPO_ROOT / "apps/mcp-server/src/mcp_server/tools/secret_list.py",
        # secret_list never touches the encrypted blob; validate defensively.
        plaintext_names=frozenset({"value", "plaintext"}),
        description="secret_list: no value/plaintext variable must appear in audit/log/span sinks",
    ),
    ModuleSpec(
        path=_REPO_ROOT / "apps/admin-api/src/admin_api/api/agent_secrets.py",
        # The operator router never decrypts; no plaintext variable should exist.
        # Defensively check for 'value', 'plaintext', 'ciphertext'.
        plaintext_names=frozenset({"value", "plaintext", "ciphertext"}),
        description="agent_secrets router: no value/plaintext/ciphertext variable must appear in audit/log/span sinks",
    ),
]


def _callee_name(node: ast.Call) -> str:
    """Return the bare function/method name of a Call node."""
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _find_plaintext_in_sink(
    tree: ast.AST,
    plaintext_names: frozenset[str],
) -> list[tuple[int, str, str]]:
    """
    Walk the AST, find every Call whose callee-name is a sink, then
    inspect all descendant Name nodes for plaintext-bearing identifiers.

    Returns a list of (lineno, sink_name, plaintext_name) violations.
    """
    violations: list[tuple[int, str, str]] = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        sink = _callee_name(node)
        if sink not in _ALL_SINKS:
            continue

        # Walk the subtree of this call for any Name whose id is a plaintext bearer
        for child in ast.walk(node):
            if isinstance(child, ast.Name) and child.id in plaintext_names:
                violations.append((node.lineno, sink, child.id))

    return violations


def test_secret_tool_files_exist() -> None:
    """All target module files must be present before we can gate them."""
    for spec in _MODULES:
        assert spec.path.exists(), (
            f"Expected module not found: {spec.path}\n"
            f"  Description: {spec.description}"
        )


def test_no_plaintext_in_secret_audit_sinks() -> None:
    """
    No audit_emit / notify_change / structlog / span call in any secret tool
    module may reference a variable that carries the plaintext secret value.

    Covers: secret_put.py, secret_get.py, secret_delete.py, secret_list.py,
            agent_secrets.py (operator router).

    Source: S-SEC-1; ADR-0014.4; ADR-0014.7; ADR-0025.
    """
    all_violations: list[str] = []

    for spec in _MODULES:
        src = spec.path.read_text(encoding="utf-8")
        tree = ast.parse(src, filename=str(spec.path))
        found = _find_plaintext_in_sink(tree, spec.plaintext_names)
        for lineno, sink, pname in found:
            rel = spec.path.relative_to(_REPO_ROOT)
            all_violations.append(
                f"{rel}:{lineno}: sink '{sink}(...)' receives plaintext-bearing name '{pname}'"
            )

    assert not all_violations, (
        "Plaintext secret value flows into audit/log/span sinks:\n"
        + "\n".join(all_violations)
        + "\n\nAll audit/notify/log/span calls must contain identifier-only payloads. "
        "Do not pass body.value, value_bytes, plaintext, or ciphertext to these sinks. "
        "(S-SEC-1; ADR-0025)"
    )


# ---------------------------------------------------------------------------
# Proof-of-detection: demonstrate the test WOULD catch a leak
# ---------------------------------------------------------------------------

def test_detector_catches_injected_leak() -> None:
    """
    Synthetic proof: inject a fake audit_emit call that passes the 'plaintext'
    variable, and confirm the detector flags it.

    This test does NOT modify any real source file — it operates on an
    in-memory string only.
    """
    leaky_source = """\
async def secret_get_leaky(session):
    plaintext = b"super-secret-value"
    await audit_emit(
        session=session,
        event_type="agent_secret.read",
        payload={"value": plaintext},   # <-- leak: plaintext in audit payload
    )
"""
    tree = ast.parse(leaky_source, filename="<synthetic>")
    violations = _find_plaintext_in_sink(tree, frozenset({"plaintext"}))
    assert violations, (
        "Detector FAILED to catch the injected plaintext leak — "
        "the detection logic is broken and must be fixed before this gate is trusted."
    )
    # Confirm the violation points at the audit_emit call
    assert any(sink == "audit_emit" and pname == "plaintext" for _, sink, pname in violations), (
        f"Violation found but not for audit_emit/plaintext: {violations}"
    )


def test_detector_passes_identifier_only_payload() -> None:
    """
    Confirm the detector does NOT flag calls that pass only wire IDs (no value variable).
    This guards against false positives that would break legitimate audit code.
    """
    clean_source = """\
async def secret_get_clean(session, wire_id, version, reader_agent_wire_id, access):
    plaintext = b"super-secret-value"
    await audit_emit(
        session=session,
        event_type="agent_secret.read",
        payload={
            "secret_id": wire_id,
            "version": version,
            "reader_agent_id": reader_agent_wire_id,
            "access": access,
        },
    )
    return plaintext   # returned in response, NOT passed to any sink
"""
    tree = ast.parse(clean_source, filename="<synthetic-clean>")
    violations = _find_plaintext_in_sink(tree, frozenset({"plaintext"}))
    assert not violations, (
        f"Detector produced false-positive violations on clean code: {violations}"
    )


# ===========================================================================
# Runtime canary gate — operator create/update path (C5/C5b)
# ===========================================================================
#
# These tests drive the REAL admin-api FastAPI handlers via ASGI (httpx),
# inject a known canary value, and assert the canary never surfaces in:
#   1. Any audit_emit call argument (captured via mock.patch).
#   2. The HTTP response body.
#
# They complement the AST-walk gate above: AST-walk proves no *variable name*
# is passed to a sink; the runtime gate proves no *runtime value* leaks even
# through indirect paths (dict construction, string formatting, etc.).
#
# If a future change routes body.value (or value_bytes) into an audit payload,
# the mock will capture the canary string and the assertion will FAIL — which is
# the correct behaviour (STATUS: ESCALATE, do not suppress).
#
# Source: S-SEC-1; ADR-0014.4; ADR-0014.7; ADR-0025; C5/C5b acceptance criteria.
# ===========================================================================

_CANARY = "CANARY-PLAINTEXT-Δ-9f3a"

# Inject admin-api src onto sys.path so the router can be imported.
_REPO_ROOT_RT = Path(__file__).parent.parent.parent
_ADMIN_API_SRC = str(_REPO_ROOT_RT / "apps/admin-api/src")
_MODELS_SRC = str(_REPO_ROOT_RT / "packages/python/mintkey-models")
for _p in (_ADMIN_API_SRC, _MODELS_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Shared test fixtures (inline — no pytest fixtures needed; keep standalone)
# ---------------------------------------------------------------------------

_TENANT_ID_C = "00000000-0000-0000-0000-000000000001"
_AGENT_UUID_C = "66666666-6666-6666-6666-666666666666"
_SECRET_UUID_C = "11111111-1111-1111-1111-111111111111"
_OPERATOR_UUID_C = "55555555-5555-5555-5555-555555555555"
_BASE_C = f"/v1/tenants/{_TENANT_ID_C}/agent-secrets"
_SECRET_PATH_C = f"{_BASE_C}/{_SECRET_UUID_C}"
_CSRF_TOKEN_C = "canary-test-csrf"
_NOW_C = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _make_agent_row_c() -> Any:
    row = MagicMock()
    row.id = uuid.UUID(_AGENT_UUID_C)
    return row


def _make_secret_row_c(version: int = 1) -> Any:
    row = MagicMock()
    row.id = uuid.UUID(_SECRET_UUID_C)
    row.tenant_id = uuid.UUID(_TENANT_ID_C)
    row.agent_id = uuid.UUID(_AGENT_UUID_C)
    row.name = "canary-secret"
    row.version = version
    row.size_bytes = len(_CANARY.encode("utf-8"))
    row.content_type = None
    row.created_at = _NOW_C
    row.updated_at = _NOW_C
    return row


class _MockSessionC:
    """Simple configurable async session for canary tests."""

    def __init__(self, fetch_once_rows: list[Any] | None = None) -> None:
        self._once = list(fetch_once_rows) if fetch_once_rows is not None else []

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        result = MagicMock()
        result.fetchone.return_value = self._once.pop(0) if self._once else None
        result.fetchall.return_value = []
        return result

    async def commit(self) -> None:
        pass


class _FakeCtxC:
    operator_id = uuid.UUID(_OPERATOR_UUID_C)
    tenant_id = uuid.UUID(_TENANT_ID_C)


def _create_canary_app(session: Any, vault_client: Any) -> Any:
    """Build a minimal FastAPI app wired to the real agent_secrets router."""
    from fastapi import FastAPI
    from admin_api.api.agent_secrets import router as agent_secrets_router
    from admin_api.auth.sessions import get_session_context, require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt
    from admin_api.services.agent_secrets_vault_client import get_agent_secrets_vault_client

    app = FastAPI()
    app.include_router(agent_secrets_router)

    async def _mock_db() -> Any:
        yield session

    async def _mock_vault() -> Any:
        return vault_client

    async def _mock_ctx() -> Any:
        return _FakeCtxC()

    async def _noop_require_tenant_session() -> None:
        return None

    app.dependency_overrides[get_db_session] = _mock_db
    app.dependency_overrides[get_agent_secrets_vault_client] = _mock_vault
    app.dependency_overrides[get_session_context] = _mock_ctx
    app.dependency_overrides[require_tenant_session] = _noop_require_tenant_session

    csrf_exempt(_BASE_C)
    csrf_exempt(_SECRET_PATH_C)
    app.add_middleware(CsrfMiddleware)
    return app


# ---------------------------------------------------------------------------
# Helper: serialise all arguments of a mock call as a single string
# ---------------------------------------------------------------------------

def _serialise_call_args(call_args: Any) -> str:
    """
    Convert all positional/keyword arguments of a mock call to a single string
    so we can grep it for the canary.  Uses json.dumps with ensure_ascii=False
    so non-ASCII canary characters (e.g. Δ) are not escaped to \\uXXXX, which
    would defeat string-containment checks.
    """
    parts: list[str] = []
    if call_args is not None:
        for arg in call_args.args:
            try:
                parts.append(json.dumps(arg, default=str, ensure_ascii=False))
            except Exception:
                parts.append(repr(arg))
        for key, val in call_args.kwargs.items():
            try:
                parts.append(f"{key}={json.dumps(val, default=str, ensure_ascii=False)}")
            except Exception:
                parts.append(f"{key}={repr(val)}")
    return " ".join(parts)


# ---------------------------------------------------------------------------
# Canary test 1: POST create-secret
# ---------------------------------------------------------------------------

import pytest

@pytest.mark.asyncio
async def test_canary_create_agent_secret_no_plaintext_in_audit() -> None:
    """
    Red-team canary gate (C5 operator path):

    Drive POST /v1/tenants/{tid}/agent-secrets with the known canary value
    "CANARY-PLAINTEXT-Δ-9f3a".  Assert:
      1. Every audit_emit call argument contains ZERO occurrences of the canary.
      2. Every notify_change call argument contains ZERO occurrences of the canary.
      3. The HTTP response body contains ZERO occurrences of the canary.
      4. The HTTP response is 201 (handler ran successfully, not short-circuited).

    If this test FAILS, a live plaintext leak has been introduced into the
    operator provisioning path — STATUS: ESCALATE.

    Source: S-SEC-1; ADR-0025.D4; C5 AC-3.
    """
    from httpx import ASGITransport, AsyncClient

    agent_row = _make_agent_row_c()
    # fetchonce: (1) agent-exists → agent_row, (2) dup-check → None
    session = _MockSessionC(fetch_once_rows=[agent_row, None])

    mock_vault = AsyncMock()
    mock_vault.put_agent_secret = AsyncMock(return_value={"kek_version": 0})

    captured_audit_calls: list[Any] = []
    captured_change_calls: list[Any] = []

    async def _capturing_audit_emit(**kwargs: Any) -> None:
        captured_audit_calls.append(kwargs)

    async def _capturing_notify_change(*args: Any, **kwargs: Any) -> None:
        captured_change_calls.append((args, kwargs))

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=_capturing_audit_emit),
        patch("admin_api.api.agent_secrets.notify_change", new=_capturing_notify_change),
    ):
        app = _create_canary_app(session, mock_vault)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                _BASE_C,
                json={
                    "agent_id": _AGENT_UUID_C,
                    "name": "canary-secret",
                    "value": _CANARY,
                },
                headers={"X-CSRF-Token": _CSRF_TOKEN_C},
            )

    # AC-4: handler must succeed (not short-circuit before the audit/vault calls)
    assert resp.status_code == 201, (
        f"Expected 201 from canary create; got {resp.status_code}: {resp.text}"
    )

    # AC-1: no canary in any audit_emit argument
    assert captured_audit_calls, "audit_emit was never called — canary gate cannot verify"
    for call_kwargs in captured_audit_calls:
        serialised = json.dumps(call_kwargs, default=str, ensure_ascii=False)
        assert _CANARY not in serialised, (
            f"CANARY LEAK DETECTED in audit_emit payload!\n"
            f"  canary: {_CANARY!r}\n"
            f"  serialised audit kwargs: {serialised}\n"
            f"STATUS: ESCALATE — plaintext value is leaking into the audit path."
        )

    # AC-1 (change notifications): no canary in notify_change
    for call_args, call_kwargs in captured_change_calls:
        serialised = json.dumps({"args": list(call_args), "kwargs": call_kwargs}, default=str, ensure_ascii=False)
        assert _CANARY not in serialised, (
            f"CANARY LEAK DETECTED in notify_change call!\n"
            f"  canary: {_CANARY!r}\n"
            f"  serialised change kwargs: {serialised}\n"
            f"STATUS: ESCALATE — plaintext value is leaking into the change-notification path."
        )

    # AC-2: no canary in HTTP response body (metadata-only invariant)
    response_text = resp.text
    assert _CANARY not in response_text, (
        f"CANARY LEAK DETECTED in HTTP 201 response body!\n"
        f"  canary: {_CANARY!r}\n"
        f"  response body: {response_text}\n"
        f"STATUS: ESCALATE — plaintext value is leaking into the API response."
    )

    # Additional: confirm audit payload is identifier-only (has secret_id, no value)
    audit_payload = captured_audit_calls[0].get("payload", {})
    assert "secret_id" in audit_payload, f"Audit payload missing secret_id: {audit_payload}"
    assert "value" not in audit_payload, (
        f"Audit payload contains 'value' key: {audit_payload}"
    )


# ---------------------------------------------------------------------------
# Canary test 2: PUT update-secret (rotate)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_canary_update_agent_secret_no_plaintext_in_audit() -> None:
    """
    Red-team canary gate (C5b operator path):

    Drive PUT /v1/tenants/{tid}/agent-secrets/{secret_id} with the known canary
    value "CANARY-PLAINTEXT-Δ-9f3a".  Assert:
      1. Every audit_emit call argument contains ZERO occurrences of the canary.
      2. Every notify_change call argument contains ZERO occurrences of the canary.
      3. The HTTP response body contains ZERO occurrences of the canary.
      4. The HTTP response is 200.

    If this test FAILS, a live plaintext leak has been introduced into the
    operator rotate path — STATUS: ESCALATE.

    Source: S-SEC-1; ADR-0025.D4; C5b AC-1.
    """
    from httpx import ASGITransport, AsyncClient

    old_row = _make_secret_row_c(version=3)
    # fetchonce: (1) SELECT existing row → old_row
    session = _MockSessionC(fetch_once_rows=[old_row])

    mock_vault = AsyncMock()
    mock_vault.put_agent_secret = AsyncMock(return_value={"kek_version": 0})

    captured_audit_calls: list[Any] = []
    captured_change_calls: list[Any] = []

    async def _capturing_audit_emit(**kwargs: Any) -> None:
        captured_audit_calls.append(kwargs)

    async def _capturing_notify_change(*args: Any, **kwargs: Any) -> None:
        captured_change_calls.append((args, kwargs))

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=_capturing_audit_emit),
        patch("admin_api.api.agent_secrets.notify_change", new=_capturing_notify_change),
    ):
        app = _create_canary_app(session, mock_vault)
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.put(
                _SECRET_PATH_C,
                json={"value": _CANARY},
                headers={"X-CSRF-Token": _CSRF_TOKEN_C},
            )

    # AC-4: handler must succeed
    assert resp.status_code == 200, (
        f"Expected 200 from canary update; got {resp.status_code}: {resp.text}"
    )

    # AC-1: no canary in any audit_emit argument
    assert captured_audit_calls, "audit_emit was never called — canary gate cannot verify"
    for call_kwargs in captured_audit_calls:
        serialised = json.dumps(call_kwargs, default=str, ensure_ascii=False)
        assert _CANARY not in serialised, (
            f"CANARY LEAK DETECTED in audit_emit payload (update path)!\n"
            f"  canary: {_CANARY!r}\n"
            f"  serialised audit kwargs: {serialised}\n"
            f"STATUS: ESCALATE — plaintext value is leaking into the audit path."
        )

    # AC-1 (change notifications): no canary in notify_change
    for call_args, call_kwargs in captured_change_calls:
        serialised = json.dumps({"args": list(call_args), "kwargs": call_kwargs}, default=str, ensure_ascii=False)
        assert _CANARY not in serialised, (
            f"CANARY LEAK DETECTED in notify_change call (update path)!\n"
            f"  canary: {_CANARY!r}\n"
            f"  serialised change kwargs: {serialised}\n"
            f"STATUS: ESCALATE — plaintext value is leaking into the change-notification path."
        )

    # AC-2: no canary in HTTP response body
    response_text = resp.text
    assert _CANARY not in response_text, (
        f"CANARY LEAK DETECTED in HTTP 200 response body (update path)!\n"
        f"  canary: {_CANARY!r}\n"
        f"  response body: {response_text}\n"
        f"STATUS: ESCALATE — plaintext value is leaking into the API response."
    )

    # Additional: confirm audit payload for update contains version/previous_version, no value
    audit_payload = captured_audit_calls[0].get("payload", {})
    assert "secret_id" in audit_payload, f"Audit payload missing secret_id: {audit_payload}"
    assert "previous_version" in audit_payload, (
        f"Audit payload missing previous_version: {audit_payload}"
    )
    assert "value" not in audit_payload, (
        f"Audit payload contains 'value' key: {audit_payload}"
    )


# ---------------------------------------------------------------------------
# Proof-of-detection: canary assertion would catch a leak
# ---------------------------------------------------------------------------

def test_canary_detection_logic_catches_audit_leak() -> None:
    """
    Proof-of-detection: confirm the canary assertion WOULD fire if a future change
    placed the canary value into an audit payload.

    This test operates entirely on in-memory data — no real handler is driven.
    It simulates what would happen if audit_emit was called with the canary in payload.

    Source: S-SEC-1; ADR-0025.D4.
    """
    # Simulate a leaky audit call where the canary ended up in the payload
    leaky_audit_kwargs = {
        "event_type": "agent_secret.created",
        "actor_type": "operator",
        "payload": {
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "value": _CANARY,  # <-- hypothetical future leak
        },
    }
    serialised = json.dumps(leaky_audit_kwargs, default=str, ensure_ascii=False)

    # The assertion that the canary tests use — confirm it would trigger
    leak_detected = _CANARY in serialised
    assert leak_detected, (
        "Detection logic FAILED: the canary string was not found in the serialised "
        "leaky audit kwargs.  The canary gate would NOT catch a real leak — fix the "
        "serialisation/assertion logic."
    )


def test_canary_detection_logic_passes_clean_audit() -> None:
    """
    Proof-of-detection: confirm the canary assertion does NOT fire on a clean
    identifier-only audit payload (guards against false positives).

    Source: S-SEC-1; ADR-0025.D4.
    """
    clean_audit_kwargs = {
        "event_type": "agent_secret.created",
        "actor_type": "operator",
        "payload": {
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "agent_id": "agent_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "name": "db-password",
            "version": 1,
        },
    }
    serialised = json.dumps(clean_audit_kwargs, default=str, ensure_ascii=False)
    assert _CANARY not in serialised, (
        "Detection logic produced a false positive on clean identifier-only audit "
        "payload — the canary appeared where it should not."
    )
