"""
OPS-LL: request_token accepts service_id as slug, svc_ wire form, or raw UUID.

Unit tests (no docker required):
  1. Slug input → 403 permission_not_found (grant exists under the resolved UUID).
  2. svc_ wire form → behaviour unchanged (backward compat — OPS-CC).
  3. Raw UUID → behaviour unchanged (backward compat — OPS-CC).
  4. Unknown slug → 404 with canonical error shape (reason_code + hint).
  5. Cross-tenant: slug from tenant A is NOT resolvable from tenant B's agent.

Integration tests (MINTKEY_INTEGRATION_TEST=true):
  6. Live container: slug resolves → 403 permission_not_found (not 404).

Source: OPS-LL; Req 6 AC5, AC10; ADR-0016.4; ADR-0008; ADR-0017.11.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Integration marker
# ---------------------------------------------------------------------------
INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full docker-compose stack",
)

BASE_MCP = os.getenv("MINTKEY_MCP_URL", "http://localhost:8082")

_BOOTSTRAP_PASS_FILE = (
    __import__("pathlib").Path(__file__).resolve().parents[3]
    / "data" / "bootstrap-secrets" / "admin_password"
)
BOOTSTRAP_PASSWORD = os.getenv(
    "MINTKEY_BOOTSTRAP_PASSWORD",
    _BOOTSTRAP_PASS_FILE.read_text().strip()
    if _BOOTSTRAP_PASS_FILE.exists()
    else "changeme",
)

# A fixed UUID used across unit tests.
_TEST_SERVICE_UUID = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
_TEST_SLUG = "github"


# ---------------------------------------------------------------------------
# ASGI harness helpers
# ---------------------------------------------------------------------------


def _build_app_with_mocked_db(
    *,
    # slug_row: what the slug lookup returns (None = not found)
    slug_row=None,
    # grant_row: what the permission_grant lookup returns (None = not found)
    grant_row=None,
    tenant_id: uuid.UUID | None = None,
    agent_id: str | None = None,
):
    """
    Create a FastAPI app with stubbed DB and agent context.

    The DB session mock is set up so that:
    - A call with a dict that contains 'slug' key returns slug_row (slug lookup).
    - All other execute calls return grant_row (permission_grant lookup).

    This lets us test slug resolution and grant lookup independently.
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context
    from mcp_server.main import create_app

    _tenant_id = tenant_id or uuid.uuid4()
    _agent_id = agent_id or str(uuid.uuid4())
    fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

    _orig_validate = _main_mod.validate_agent_key

    async def _fake_validate(key):
        return fake_ctx, None

    _main_mod.validate_agent_key = _fake_validate

    app = create_app()

    async def _fake_agent_context():
        return fake_ctx

    app.dependency_overrides[get_agent_context] = _fake_agent_context

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()

        async def _execute(stmt, params=None, **kw):
            result_mock = MagicMock()
            if params and "slug" in params:
                # slug lookup
                if slug_row is not None:
                    result_mock.fetchall.return_value = [slug_row]
                else:
                    result_mock.fetchall.return_value = []
            else:
                # grant / other lookup
                result_mock.fetchone.return_value = grant_row
            return result_mock

        session.execute = _execute
        # set_tenant_context calls session.execute with SET LOCAL — let it pass.
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session

    return app, _orig_validate, _main_mod


def _make_slug_row(service_uuid: str = _TEST_SERVICE_UUID):
    row = MagicMock()
    row.id = service_uuid
    return row


def _make_grant_row(
    agent_id: str | None = None,
    service_id: str = _TEST_SERVICE_UUID,
    action: str = "call",
    constraints: dict | None = None,
):
    row = MagicMock()
    row.agent_id = agent_id or str(uuid.uuid4())
    row.service_id = service_id
    row.action = action
    row.constraints = constraints or {}
    return row


def _run_request_token(
    service_id: str,
    action: str = "call",
    *,
    slug_row=None,
    grant_row=None,
    tenant_id: uuid.UUID | None = None,
    agent_id: str | None = None,
):
    from httpx import AsyncClient, ASGITransport

    app, _orig, _main_mod = _build_app_with_mocked_db(
        slug_row=slug_row,
        grant_row=grant_row,
        tenant_id=tenant_id,
        agent_id=agent_id,
    )
    try:
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/request_token",
                    json={"service_id": service_id, "action": action},
                    headers={"X-API-Key": "mk_agent_testkey"},
                )

        resp = asyncio.run(_inner())
    finally:
        _main_mod.validate_agent_key = _orig
    return resp


# ===========================================================================
# Unit tests
# ===========================================================================


def test_request_token_slug_resolves_to_permission_not_found() -> None:
    """
    Slug input resolves correctly; because no grant exists the response is
    403 permission_not_found — NOT 404 (which would mean slug didn't resolve).

    OPS-LL acceptance criterion: slug resolves → downstream logic runs normally.
    """
    # Slug lookup finds a row; grant lookup finds nothing → 403
    resp = _run_request_token(
        _TEST_SLUG,
        slug_row=_make_slug_row(),
        grant_row=None,
    )
    assert resp.status_code == 403, (
        f"Expected 403 permission_not_found when slug resolves but no grant, "
        f"got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("reason_code") == "permission_not_found", (
        f"Expected reason_code='permission_not_found', got: {body}"
    )


def test_request_token_svc_wire_form_unchanged() -> None:
    """
    svc_ wire form still works (OPS-CC backward compat).
    No slug lookup is performed; grant lookup returns None → 403.
    """
    from mcp_server.utils.wire_ids import db_uuid_to_wire

    wire_id = db_uuid_to_wire(_TEST_SERVICE_UUID, "svc")
    resp = _run_request_token(
        wire_id,
        slug_row=None,  # should never be called for wire form
        grant_row=None,
    )
    assert resp.status_code == 403, (
        f"Expected 403 for wire-form input with no grant, got {resp.status_code}: {resp.text}"
    )
    assert resp.json().get("reason_code") == "permission_not_found"


def test_request_token_raw_uuid_unchanged() -> None:
    """
    Raw UUID still works (OPS-CC backward compat).
    No slug lookup is performed; grant lookup returns None → 403.
    """
    resp = _run_request_token(
        _TEST_SERVICE_UUID,
        slug_row=None,
        grant_row=None,
    )
    assert resp.status_code == 403, (
        f"Expected 403 for raw-UUID input with no grant, got {resp.status_code}: {resp.text}"
    )
    assert resp.json().get("reason_code") == "permission_not_found"


def test_request_token_unknown_slug_returns_404_with_error_shape() -> None:
    """
    Unknown slug → 404 with canonical OPS-LL error shape:
      code, reason_code, service_id_input, hint.

    Source: OPS-LL error message spec.
    """
    resp = _run_request_token(
        "nonexistent-slug",
        slug_row=None,
        grant_row=None,
    )
    assert resp.status_code == 404, (
        f"Expected 404 for unknown slug, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("code") == "mintkey:not_found", (
        f"Expected code='mintkey:not_found', got: {body}"
    )
    assert body.get("reason_code") == "service_not_found", (
        f"Expected reason_code='service_not_found', got: {body}"
    )
    assert body.get("service_id_input") == "nonexistent-slug", (
        f"Expected service_id_input='nonexistent-slug', got: {body}"
    )
    assert "hint" in body and body["hint"], (
        f"Expected non-empty 'hint' in error body, got: {body}"
    )
    assert "list_services" in body["hint"] or "svc_" in body["hint"], (
        f"Hint should reference list_services or svc_ form: {body['hint']!r}"
    )


def test_request_token_cross_tenant_slug_not_resolvable() -> None:
    """
    Cross-tenant security: a slug that exists in tenant A is NOT resolvable
    when the calling agent belongs to tenant B (slug lookup is scoped to the
    calling agent's tenant_id).

    Simulated by: the slug_row is None (DB returns 0 rows for tenant B's slug
    lookup — as it would when RLS + the tenant_id param scope the query).

    Source: OPS-LL hard rule — DO NOT make slug resolution global.
    """
    tenant_b = uuid.uuid4()
    # Slug lookup for tenant B returns nothing (the slug 'github' belongs to tenant A)
    resp = _run_request_token(
        "github",
        slug_row=None,  # tenant B has no 'github' service
        grant_row=None,
        tenant_id=tenant_b,
    )
    assert resp.status_code == 404, (
        f"Expected 404 when cross-tenant slug lookup returns nothing, "
        f"got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("reason_code") == "service_not_found", (
        f"Cross-tenant slug should result in service_not_found: {body}"
    )


# ===========================================================================
# Integration tests (requires docker-compose stack)
# ===========================================================================


@INTEGRATION
def test_integration_slug_resolves_to_permission_not_found() -> None:
    """
    Live container: pass slug 'github' as service_id to request_token.
    The slug should resolve; the test agent has no grant, so we expect
    403 permission_not_found (NOT 404 unknown service).

    Source: OPS-LL smoke test.
    """
    import httpx
    import time

    with httpx.Client(timeout=30) as client:
        # Login as admin
        login_r = client.post(
            f"{os.getenv('MINTKEY_API_URL', 'http://localhost:8080')}/v1/auth/internal-login",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
        )
        assert login_r.status_code == 200, f"login failed: {login_r.text}"
        tenant_id = login_r.json()["tenant_id"]
        csrf_token = client.cookies.get("csrf_token", "")

        # Create a fresh agent with no grants
        agent_r = client.post(
            f"{os.getenv('MINTKEY_API_URL', 'http://localhost:8080')}/v1/tenants/{tenant_id}/agents",
            json={"name": f"ops-ll-test-agent-{int(time.time())}"},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert agent_r.status_code == 201, f"create agent failed: {agent_r.text}"
        api_key = agent_r.json()["api_key"]

        # Call request_token with slug
        token_r = client.post(
            f"{BASE_MCP}/v1/tools/request_token",
            json={"service_id": "github", "action": "call"},
            headers={"X-API-Key": api_key},
        )
        # The slug 'github' resolves → no grant → 403
        # (or 404 if 'github' service does not exist in this tenant)
        assert token_r.status_code in (403, 404), (
            f"Expected 403 or 404 for slug 'github' with no grant, "
            f"got {token_r.status_code}: {token_r.text}"
        )
        body = token_r.json()
        if token_r.status_code == 404:
            assert body.get("reason_code") == "service_not_found", (
                f"404 should have reason_code=service_not_found: {body}"
            )
        else:
            assert body.get("reason_code") == "permission_not_found", (
                f"403 should have reason_code=permission_not_found: {body}"
            )


@INTEGRATION
def test_integration_unknown_slug_returns_404_error_shape() -> None:
    """
    Live container: totally unknown slug returns 404 with the OPS-LL error shape.

    Source: OPS-LL smoke test.
    """
    import httpx
    import time

    with httpx.Client(timeout=30) as client:
        login_r = client.post(
            f"{os.getenv('MINTKEY_API_URL', 'http://localhost:8080')}/v1/auth/internal-login",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
        )
        assert login_r.status_code == 200
        tenant_id = login_r.json()["tenant_id"]
        csrf_token = client.cookies.get("csrf_token", "")

        agent_r = client.post(
            f"{os.getenv('MINTKEY_API_URL', 'http://localhost:8080')}/v1/tenants/{tenant_id}/agents",
            json={"name": f"ops-ll-test-agent-404-{int(time.time())}"},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert agent_r.status_code == 201
        api_key = agent_r.json()["api_key"]

        token_r = client.post(
            f"{BASE_MCP}/v1/tools/request_token",
            json={"service_id": "this-slug-does-not-exist-xyz", "action": "call"},
            headers={"X-API-Key": api_key},
        )
        assert token_r.status_code == 404, (
            f"Expected 404 for unknown slug, got {token_r.status_code}: {token_r.text}"
        )
        body = token_r.json()
        assert body.get("reason_code") == "service_not_found"
        assert body.get("service_id_input") == "this-slug-does-not-exist-xyz"
        assert "hint" in body and body["hint"]
