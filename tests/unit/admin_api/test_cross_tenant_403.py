"""
Cross-tenant 403 tests for Chunk B — credentials.create_credential and services.get_service.

Proves that `require_tenant_session` blocks a session scoped to TENANT_A from
accessing a TENANT_B path.

Shows:
  - BEFORE: dependency overridden to no-op → 20x (reaches handler)
  - AFTER: real dependency active, session.tenant_id=TENANT_A, path tenant=TENANT_B → 403

Source: ADR-SCOPE-A (SCOPE-A cross-tenant authz fix).
"""
from __future__ import annotations

import sys
import os
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _p in (ADMIN_API_SRC, MODELS_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

TENANT_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
SERVICE_ID = "00000000-0000-0000-0000-000000000002"

# ---------------------------------------------------------------------------
# credentials.create_credential — cross-tenant 403
# ---------------------------------------------------------------------------

def _make_cred_mock_db():
    """Mock DB for create_credential — service lookup returns a row on call #2."""
    session = MagicMock()
    _n = {"v": 0}

    async def _execute(*args, **kwargs):
        result = MagicMock()
        _n["v"] += 1
        if _n["v"] == 2:
            svc_row = MagicMock()
            svc_row.id = SERVICE_ID
            svc_row.base_url = "http://mock-backend:8999"
            result.fetchone.return_value = svc_row
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _build_cred_app(*, override_authz: bool):
    """
    Build a FastAPI app including the credentials router.

    override_authz=True  → require_tenant_session no-op (simulates BEFORE state).
    override_authz=False → real dep active; test patches validate_session directly.
    """
    from fastapi import FastAPI
    from admin_api.api.credentials import router as credentials_router
    from admin_api.auth.sessions import require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.services.vault_client import VaultAdapterClient, get_vault_client
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(credentials_router)

    async def _mock_db():
        yield _make_cred_mock_db()

    app.dependency_overrides[get_db_session] = _mock_db

    class _MockVault(VaultAdapterClient):
        async def put_credential(self, tenant_id, service_id, auth_scheme, plaintext,
                                 target_url="", header_name="", query_param="",
                                 target_address="", ssh_user=""):
            return {"credential_id": "cred_mock_001", "key_version": 1, "created_at": 0.0}

        async def list_versions(self, tenant_id, service_id):
            return []

    async def _mock_vault():
        return _MockVault()

    app.dependency_overrides[get_vault_client] = _mock_vault

    if override_authz:
        async def _noop():
            return None
        app.dependency_overrides[require_tenant_session] = _noop

    url = f"/v1/tenants/{TENANT_B}/services/{SERVICE_ID}/credentials"
    csrf_exempt(url)
    app.add_middleware(CsrfMiddleware)
    return app


@pytest.mark.asyncio
async def test_create_credential_cross_tenant_before_dep_reaches_handler() -> None:
    """
    BEFORE: with require_tenant_session overridden to no-op, a cross-tenant request
    reaches the handler and returns non-403 (handler processes normally).
    """
    app = _build_cred_app(override_authz=True)
    url = f"/v1/tenants/{TENANT_B}/services/{SERVICE_ID}/credentials"

    with patch("admin_api.api.credentials.audit_emit", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(url, json={"auth_scheme": "bearer_token", "value": "s3cr3t"})

    # Handler reached — returns 201 (or any non-403)
    assert resp.status_code != 403, f"Expected non-403 BEFORE dep; got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_create_credential_cross_tenant_after_dep_returns_403() -> None:
    """
    AFTER: real require_tenant_session active. Session scoped to TENANT_A hits TENANT_B
    path → 403 permission_denied.
    """
    app = _build_cred_app(override_authz=False)
    url = f"/v1/tenants/{TENANT_B}/services/{SERVICE_ID}/credentials"

    ctx = SimpleNamespace(operator_id="op-uuid-1", tenant_id=TENANT_A)

    with (
        patch("admin_api.auth.sessions.validate_session", new=AsyncMock(return_value=ctx)),
        patch("admin_api.auth.sessions._is_operator_platform_admin", new=AsyncMock(return_value=False)),
        patch("admin_api.api.credentials.audit_emit", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"mintkey_session": "aaaaaaaa-aaaa-aaaa-aaaa-000000000001"},
        ) as client:
            resp = await client.post(url, json={"auth_scheme": "bearer_token", "value": "s3cr3t"})

    assert resp.status_code == 403, f"Expected 403 AFTER dep; got {resp.status_code}: {resp.text}"
    # FastAPI wraps HTTPException detail in {"detail": ...}
    assert resp.json()["detail"]["mintkey:code"] == "permission_denied"


# ---------------------------------------------------------------------------
# services.get_service — cross-tenant 403
# ---------------------------------------------------------------------------

def _make_svc_mock_db():
    """Mock DB for get_service — returns a service row on fetchone."""
    session = MagicMock()
    stub_row = MagicMock()
    stub_row.id = SERVICE_ID
    stub_row.tenant_id = TENANT_B
    stub_row.name = "mock-svc"
    stub_row.slug = "mock-svc"
    stub_row.display_name = "Mock"
    stub_row.description = ""
    stub_row.base_url = "https://api.example.com"
    stub_row.auth_scheme = "bearer_token"
    stub_row.openapi_url = None
    stub_row.status = "active"
    stub_row.created_at = None
    stub_row.updated_at = None
    stub_row.template_id = None
    stub_row.current_key_version = 0

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.fetchone.return_value = stub_row
        result.fetchall.return_value = [stub_row]
        return result

    session.execute = _execute
    return session


def _build_svc_app(*, override_authz: bool):
    """
    Build a FastAPI app including the services router.

    override_authz=True  → no-op authz (BEFORE).
    override_authz=False → real dep active (AFTER).
    """
    from fastapi import FastAPI
    from admin_api.api.services import router as services_router
    from admin_api.auth.sessions import require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(services_router)

    async def _mock_db():
        yield _make_svc_mock_db()

    app.dependency_overrides[get_db_session] = _mock_db

    if override_authz:
        async def _noop():
            return None
        app.dependency_overrides[require_tenant_session] = _noop

    base = f"/v1/tenants/{TENANT_B}/services"
    csrf_exempt(base)
    csrf_exempt(f"{base}/{SERVICE_ID}")
    app.add_middleware(CsrfMiddleware)
    return app


@pytest.mark.asyncio
async def test_get_service_cross_tenant_before_dep_reaches_handler() -> None:
    """
    BEFORE: with require_tenant_session overridden to no-op, cross-tenant GET
    reaches the handler and returns 200.
    """
    app = _build_svc_app(override_authz=True)
    url = f"/v1/tenants/{TENANT_B}/services/{SERVICE_ID}"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(url)

    assert resp.status_code != 403, f"Expected non-403 BEFORE dep; got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_get_service_cross_tenant_after_dep_returns_403() -> None:
    """
    AFTER: real require_tenant_session active. Session scoped to TENANT_A hits TENANT_B
    path → 403 permission_denied.
    """
    app = _build_svc_app(override_authz=False)
    url = f"/v1/tenants/{TENANT_B}/services/{SERVICE_ID}"

    ctx = SimpleNamespace(operator_id="op-uuid-1", tenant_id=TENANT_A)

    with (
        patch("admin_api.auth.sessions.validate_session", new=AsyncMock(return_value=ctx)),
        patch("admin_api.auth.sessions._is_operator_platform_admin", new=AsyncMock(return_value=False)),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            cookies={"mintkey_session": "aaaaaaaa-aaaa-aaaa-aaaa-000000000001"},
        ) as client:
            resp = await client.get(url)

    assert resp.status_code == 403, f"Expected 403 AFTER dep; got {resp.status_code}: {resp.text}"
    # FastAPI wraps HTTPException detail in {"detail": ...}
    assert resp.json()["detail"]["mintkey:code"] == "permission_denied"
