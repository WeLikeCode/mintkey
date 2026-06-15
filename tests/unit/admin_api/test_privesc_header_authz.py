"""
Privilege escalation regression test — Chunk D (ADR-0027 §D2).

Proves that X-Platform-Admin: true header ALONE no longer grants access after
the fix. Before: header-only → 201/200. After: header-only → 401 (no session).

Test cases:
  1. test_header_only_create_tenant_rejected_401: POST /v1/tenants with ONLY
     X-Platform-Admin: true header (no session cookie) → 401
  2. test_header_only_verify_chain_rejected_401: POST /v1/admin/audit/verify-chain
     with ONLY X-Platform-Admin: true header → 401
  3. test_platform_admin_session_allowed: valid platform-admin session → 201
  4. test_non_admin_session_forbidden: valid session but not platform-admin → 403

Sources: ADR-0027 §D2; SCOPE-A chunk D.
"""
from __future__ import annotations

import sys
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_URL = "/v1/tenants"
VERIFY_URL = "/v1/admin/audit/verify-chain"
TENANT_ID = "tenant_00000000000000000000000001"
OPERATOR_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
SESSION_TOKEN = "11111111-1111-1111-1111-111111111111"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tenant_mock_db():
    session = MagicMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _make_audit_mock_db():
    session = MagicMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.fetchall.return_value = []
        result.fetchone.return_value = None
        return result

    session.execute = _execute
    return session


def _make_session_ctx(is_admin: bool):
    class _Ctx:
        pass
    ctx = _Ctx()
    ctx.operator_id = OPERATOR_ID
    ctx.tenant_id = uuid.UUID("00000000-0000-0000-0000-000000000000")
    ctx._is_admin = is_admin
    return ctx


def _create_tenant_app_no_dep_override():
    """Tenant app with REAL require_platform_admin_session — no override."""
    from fastapi import FastAPI
    from admin_api.api.tenants import router as tenants_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(tenants_router)

    async def mock_db():
        yield _make_tenant_mock_db()

    app.dependency_overrides[get_db_session] = mock_db
    csrf_exempt(TENANT_URL)
    app.add_middleware(CsrfMiddleware)
    return app


def _create_audit_app_no_dep_override():
    """Audit-admin app with REAL require_platform_admin_session — no override."""
    from fastapi import FastAPI
    from admin_api.api.audit_admin import router as audit_admin_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(audit_admin_router)

    async def mock_db():
        yield _make_audit_mock_db()

    app.dependency_overrides[get_db_session] = mock_db
    csrf_exempt(VERIFY_URL)
    app.add_middleware(CsrfMiddleware)
    return app


# ---------------------------------------------------------------------------
# AC4 tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_header_only_create_tenant_rejected_401() -> None:
    """
    PRIVESC: POST /v1/tenants with X-Platform-Admin: true header ONLY (no session cookie)
    must be REJECTED with 401.

    BEFORE fix: header-only would have returned 201 (header checked in _is_platform_admin).
    AFTER fix: header is ignored; no session cookie → 401 unauthenticated.

    Source: ADR-0027 §D2; SCOPE-A chunk D.
    """
    app = _create_tenant_app_no_dep_override()

    with patch("admin_api.api.tenants.audit_emit", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                TENANT_URL,
                json={"slug": "t_evil", "name": "Evil Corp"},
                headers={"X-Platform-Admin": "true"},
                # No mintkey_session cookie — header only
            )

    # AFTER: header alone is no longer accepted — must be 401
    assert resp.status_code == 401, (
        f"PRIVESC: header-only should be rejected (401), got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("mintkey:code") == "unauthenticated"


@pytest.mark.asyncio
async def test_header_only_verify_chain_rejected_401() -> None:
    """
    PRIVESC: POST /v1/admin/audit/verify-chain with X-Platform-Admin: true header ONLY
    must be REJECTED with 401.

    BEFORE fix: header-only would have returned 200.
    AFTER fix: header is ignored; no session cookie → 401.

    Source: ADR-0027 §D2; SCOPE-A chunk D.
    """
    app = _create_audit_app_no_dep_override()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            VERIFY_URL,
            params={"tenant_id": TENANT_ID},
            headers={"X-Platform-Admin": "true"},
            # No mintkey_session cookie — header only
        )

    assert resp.status_code == 401, (
        f"PRIVESC: header-only should be rejected (401), got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("mintkey:code") == "unauthenticated"


@pytest.mark.asyncio
async def test_platform_admin_session_allowed() -> None:
    """
    A valid platform-admin session (validate_session returns ctx,
    _is_operator_platform_admin returns True) MUST succeed on POST /v1/tenants.
    Source: ADR-0027 §D2.
    """
    app = _create_tenant_app_no_dep_override()
    ctx = _make_session_ctx(is_admin=True)

    with patch("admin_api.auth.sessions.validate_session", new=AsyncMock(return_value=ctx)), \
         patch("admin_api.auth.sessions._is_operator_platform_admin", new=AsyncMock(return_value=True)), \
         patch("admin_api.api.tenants.audit_emit", new=AsyncMock()):

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                TENANT_URL,
                json={"slug": "t_legit", "name": "Legit Corp"},
                cookies={"mintkey_session": SESSION_TOKEN},
            )

    assert resp.status_code == 201, f"Platform-admin session should succeed; got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["slug"] == "t_legit"


@pytest.mark.asyncio
async def test_non_admin_session_forbidden() -> None:
    """
    A valid session for an operator who is NOT platform-admin → 403 permission_denied.
    Source: ADR-0027 §D2.
    """
    app = _create_tenant_app_no_dep_override()
    ctx = _make_session_ctx(is_admin=False)

    with patch("admin_api.auth.sessions.validate_session", new=AsyncMock(return_value=ctx)), \
         patch("admin_api.auth.sessions._is_operator_platform_admin", new=AsyncMock(return_value=False)), \
         patch("admin_api.api.tenants.audit_emit", new=AsyncMock()):

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                TENANT_URL,
                json={"slug": "t_denied", "name": "Denied Corp"},
                cookies={"mintkey_session": SESSION_TOKEN},
            )

    assert resp.status_code == 403, f"Non-admin session should be forbidden; got {resp.status_code}: {resp.text}"
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("mintkey:code") == "permission_denied"
