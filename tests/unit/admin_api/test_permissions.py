"""
Unit tests: Permission grant/revoke endpoints.

POST   /v1/tenants/{tid}/agents/{aid}/permissions        — grant permission (201)
DELETE /v1/tenants/{tid}/agents/{aid}/permissions/{pid}  — revoke permission (204)

Test cases:
  1. Valid constraints → 201
  2. Unknown key in constraints → 422 with mintkey:code=validation_failed
  3. Idempotent re-grant (same params) → 200
  4. Conflicting constraints (same agent+service+action, different constraints) → 409
  5. Audit agent.permission.granted emitted with full constraints
  6. DELETE emits agent.permission.revoked + NOTIFY mintkey:agent
  7. Cross-tenant grant attempt → 404

Sources:
  - ADR-0016.4 (closed Constraints schema)
  - ADR-0008 (bound parameters)
  - ADR-0014.7 (audit emit on every state change)
  - ADR-0017.11 (ULID IDs with perm_ prefix)
  - T-1.4.2
"""
from __future__ import annotations

import json
import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
OTHER_TENANT_ID = "00000000-0000-0000-0000-000000000002"
AGENT_ID = "agent_00000000000000000000000001"
PERM_ID = "perm_00000000000000000000000001"
BASE_URL = f"/v1/tenants/{TENANT_ID}/agents/{AGENT_ID}/permissions"

VALID_GRANT_BODY = {
    "service_id": "svc_abc",
    "action": "read",
    "constraints": {
        "rate_limit": {"requests_per_second": 10, "burst": 20},
    },
}


def _make_mock_session(agent_exists: bool = True, existing_perm=None):
    """Return an async-capable mock DB session.

    Uses SQL-pattern matching so call ordering is stable after R12 which
    inserted _resolve_service_uuid() queries between the agent check and the
    permission idempotency check.
    """
    session = MagicMock()
    session._execute_calls = []

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []

        stmt_str = str(args[0]).lower() if args else ""

        if "set_config" in stmt_str:
            pass  # tenant context — no-op
        elif "select" in stmt_str and "agents" in stmt_str:
            if agent_exists:
                mock_row = MagicMock()
                mock_row.id = AGENT_ID
                result.fetchone.return_value = mock_row
        elif "select" in stmt_str and "services" in stmt_str:
            # R12: _resolve_service_uuid verifies service exists.
            # Return a non-None row so the primary path succeeds.
            mock_row = MagicMock()
            mock_row.id = "svc_abc"
            result.fetchone.return_value = mock_row
        elif "select" in stmt_str and "permission_grants" in stmt_str:
            result.fetchone.return_value = existing_perm
        # INSERT and other statements fall through with fetchone=None

        return result

    session.execute = _execute
    return session


def create_test_app(agent_exists: bool = True, existing_perm=None, bypass_authz: bool = True):
    """
    Create a test app with:
      - permissions router included
      - get_db_session overridden to a mock (no real DB)
      - require_tenant_session bypassed by default (unit tests don't exercise session auth)
      - CSRF paths registered as exempt
      - validation error handler registered
    """
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from admin_api.api.permissions import router as permissions_router, validation_error_handler
    from admin_api.auth.sessions import require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(permissions_router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    async def mock_db_session():
        yield _make_mock_session(agent_exists=agent_exists, existing_perm=existing_perm)

    app.dependency_overrides[get_db_session] = mock_db_session
    if bypass_authz:
        app.dependency_overrides[require_tenant_session] = lambda: None

    csrf_exempt(BASE_URL)
    csrf_exempt(f"{BASE_URL}/{PERM_ID}")

    app.add_middleware(CsrfMiddleware)
    return app


@pytest.fixture()
def app():
    return create_test_app()


@pytest.fixture()
def mock_audit():
    with patch("admin_api.api.permissions.audit_emit", new=AsyncMock()) as m:
        yield m


@pytest.fixture()
def mock_notify():
    with patch("admin_api.api.permissions.notify_change", new=AsyncMock()) as m:
        yield m


# ---------------------------------------------------------------------------
# Test 1: Valid constraints → 201
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grant_with_valid_constraints_returns_201(app, mock_audit, mock_notify) -> None:
    """
    POST with valid constraints returns 201.
    Response id starts with 'perm_' — ADR-0017.11.
    Source: T-1.4.2; ADR-0016.4.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(BASE_URL, json=VALID_GRANT_BODY)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("perm_"), f"Expected perm_ prefix, got: {body['id']}"
    assert body["agent_id"] == AGENT_ID
    assert body["service_id"] == "svc_abc"
    assert body["action"] == "read"


# ---------------------------------------------------------------------------
# Test 2: Unknown key in constraints → 422 validation_failed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_grant_with_unknown_constraints_key_returns_422(app, mock_audit, mock_notify) -> None:
    """
    POST with an unknown key in constraints returns 422 with mintkey:code=validation_failed.
    Closed schema — ADR-0016.4.
    Source: T-1.4.2.
    """
    body = {
        "service_id": "svc_abc",
        "action": "read",
        "constraints": {"foobar": 42},
    }
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(BASE_URL, json=body)

    assert resp.status_code == 422, resp.text
    resp_body = resp.json()
    assert resp_body.get("mintkey:code") == "validation_failed", resp.text


# ---------------------------------------------------------------------------
# Test 3: Idempotent re-grant → 200
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_idempotent_regrant_returns_200(mock_audit, mock_notify) -> None:
    """
    POST with identical params when a matching grant already exists returns 200.
    Source: T-1.4.2.
    """
    # Simulate existing permission with identical constraints
    existing = MagicMock()
    existing.id = PERM_ID
    existing.agent_id = AGENT_ID
    existing.service_id = "svc_abc"
    existing.action = "read"
    existing.constraints = json.dumps(VALID_GRANT_BODY["constraints"])

    app = create_test_app(existing_perm=existing)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(BASE_URL, json=VALID_GRANT_BODY)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"] == PERM_ID


# ---------------------------------------------------------------------------
# Test 4: Conflicting constraints → 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_conflicting_constraints_returns_409(mock_audit, mock_notify) -> None:
    """
    POST with same (agent, service, action) but different constraints returns 409
    with mintkey:code=permission_constraints_conflict.
    Source: T-1.4.2.
    """
    # Existing record has different constraints
    existing = MagicMock()
    existing.id = PERM_ID
    existing.agent_id = AGENT_ID
    existing.service_id = "svc_abc"
    existing.action = "read"
    existing.constraints = json.dumps({
        "rate_limit": {"requests_per_second": 5, "burst": 10},
    })

    app = create_test_app(existing_perm=existing)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(BASE_URL, json=VALID_GRANT_BODY)

    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "permission_constraints_conflict", resp.text


# ---------------------------------------------------------------------------
# Test 5: Audit emitted on grant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_emitted_on_grant(app, mock_audit, mock_notify) -> None:
    """
    audit_emit is called with event_type='agent.permission.granted'
    and full constraints in payload — ADR-0014.7, T-1.4.2.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(BASE_URL, json=VALID_GRANT_BODY)

    assert resp.status_code == 201, resp.text
    mock_audit.assert_called_once()
    kwargs = mock_audit.call_args.kwargs
    assert kwargs.get("event_type") == "agent.permission.granted"
    payload = kwargs.get("payload", {})
    assert "constraints" in payload, "audit payload must include constraints"
    assert payload["constraints"] == VALID_GRANT_BODY["constraints"]


# ---------------------------------------------------------------------------
# Test 6: DELETE emits revoked + NOTIFY mintkey:agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_returns_204_and_notifies(app, mock_audit, mock_notify) -> None:
    """
    DELETE returns 204, emits agent.permission.revoked audit event,
    and fires NOTIFY on 'mintkey:agent' channel — ADR-0014.7, ADR-0014.1.
    Source: T-1.4.2.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"{BASE_URL}/{PERM_ID}")

    assert resp.status_code == 204, resp.text
    mock_audit.assert_called_once()
    kwargs = mock_audit.call_args.kwargs
    assert kwargs.get("event_type") == "agent.permission.revoked"

    mock_notify.assert_called_once()
    notify_kwargs = mock_notify.call_args
    # Channel is first positional arg after session
    assert "mintkey:agent" in str(notify_kwargs), f"Expected mintkey:agent channel, got: {notify_kwargs}"


# ---------------------------------------------------------------------------
# Test 7: Cross-tenant grant attempt → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cross_tenant_grant_returns_404(mock_audit, mock_notify) -> None:
    """
    POST where agent_id does not belong to the given tenant returns 404.
    RLS + explicit agent check enforces tenant isolation — ADR-0008, T-1.4.2.
    """
    app = create_test_app(agent_exists=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(BASE_URL, json=VALID_GRANT_BODY)

    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "not_found"

# ---------------------------------------------------------------------------
# Cross-tenant authz: require_tenant_session enforces 403 — ADR-SCOPE-A
# ---------------------------------------------------------------------------

TENANT_A_ID = TENANT_ID    # "00000000-0000-0000-0000-000000000001"
TENANT_B_ID = OTHER_TENANT_ID  # "00000000-0000-0000-0000-000000000002"
CROSS_TENANT_URL = f"/v1/tenants/{TENANT_B_ID}/agents/{AGENT_ID}/permissions"


@pytest.mark.asyncio
async def test_grant_permission_cross_tenant_returns_403(mock_audit, mock_notify) -> None:
    """
    POST /v1/tenants/{TENANT_B}/agents/.../permissions with a session scoped to
    TENANT_A must return 403 — require_tenant_session enforcement (ADR-SCOPE-A).
    Before dep: handler reached (201).  After dep: 403 permission_denied.
    """
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from admin_api.api.permissions import router as permissions_router, validation_error_handler
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(permissions_router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    async def mock_db_session():
        yield _make_mock_session(agent_exists=True)

    app.dependency_overrides[get_db_session] = mock_db_session
    csrf_exempt(CROSS_TENANT_URL)
    app.add_middleware(CsrfMiddleware)

    class _FakeCtx:
        operator_id = "op-uuid-a"
        tenant_id = TENANT_A_ID

    with (
        patch("admin_api.auth.sessions.validate_session", new=AsyncMock(return_value=_FakeCtx())),
        patch("admin_api.auth.sessions._is_operator_platform_admin", new=AsyncMock(return_value=False)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                CROSS_TENANT_URL,
                json=VALID_GRANT_BODY,
                cookies={"mintkey_session": "tok-a"},
            )

    assert resp.status_code == 403, (
        f"Expected 403 for cross-tenant POST /permissions, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("mintkey:code") == "permission_denied"
