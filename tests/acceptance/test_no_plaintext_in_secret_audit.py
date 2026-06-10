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

Source: S-SEC-1; ADR-0014.4; ADR-0014.7; ADR-0025.
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import NamedTuple

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
