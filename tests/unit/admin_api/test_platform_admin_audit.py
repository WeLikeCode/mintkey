"""
Unit tests: PlatformAdmin cross-tenant access audit emission.

Tests that platform_admin.access audit events are emitted on PlatformAdmin reads.

Test cases:
  1. test_platform_admin_audit_emitted_on_read: GET /v1/tenants/{id}/audit with
     X-Platform-Admin: true → audit_emit called with event_type="platform_admin.access"
  2. test_platform_admin_audit_has_resource_type: payload contains resource_type
     and viewed_tenant_id
  3. test_non_platform_admin_no_audit: regular operator GET → NO platform_admin.access emitted

Sources:
  - ADR-0014.7 (audit emit on every state change)
  - T-1.13.4
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
AUDIT_URL = f"/v1/tenants/{TENANT_ID}/audit"


def _make_mock_session(rows=None):
    session = MagicMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.fetchall.return_value = rows or []
        result.fetchone.return_value = None
        return result

    session.execute = _execute
    return session


def _create_audit_app(rows=None):
    """Build a test app with the audit router (tenant-scoped read)."""
    from fastapi import FastAPI
    from admin_api.api.audit import router as audit_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(audit_router)

    async def mock_db_session():
        yield _make_mock_session(rows=rows)

    app.dependency_overrides[get_db_session] = mock_db_session
    csrf_exempt(AUDIT_URL)
    app.add_middleware(CsrfMiddleware)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_admin_audit_emitted_on_read() -> None:
    """
    GET /v1/tenants/{id}/audit with X-Platform-Admin: true must call audit_emit
    with event_type="platform_admin.access".
    Source: T-1.13.4; ADR-0014.7.
    """
    from admin_api.middleware.platform_admin_audit import emit_platform_admin_access

    session = _make_mock_session(rows=[])

    with patch("admin_api.middleware.platform_admin_audit.audit_emit", new=AsyncMock()) as mock_emit:
        from fastapi import Request
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-Platform-Admin": "true"}
        mock_request.url.path = AUDIT_URL

        await emit_platform_admin_access(
            request=mock_request,
            session=session,
            tenant_id=TENANT_ID,
            resource_type="audit_events",
        )

    mock_emit.assert_called_once()
    call_kwargs = mock_emit.call_args.kwargs
    assert call_kwargs["event_type"] == "platform_admin.access"


@pytest.mark.asyncio
async def test_platform_admin_audit_has_resource_type() -> None:
    """
    The platform_admin.access audit event payload must contain resource_type
    and viewed_tenant_id.
    Source: T-1.13.4.
    """
    from admin_api.middleware.platform_admin_audit import emit_platform_admin_access

    session = _make_mock_session(rows=[])

    with patch("admin_api.middleware.platform_admin_audit.audit_emit", new=AsyncMock()) as mock_emit:
        from fastapi import Request
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {"X-Platform-Admin": "true"}
        mock_request.url.path = AUDIT_URL

        await emit_platform_admin_access(
            request=mock_request,
            session=session,
            tenant_id=TENANT_ID,
            resource_type="audit_events",
        )

    call_kwargs = mock_emit.call_args.kwargs
    payload = call_kwargs["payload"]
    assert "resource_type" in payload
    assert payload["resource_type"] == "audit_events"
    assert "viewed_tenant_id" in payload
    assert payload["viewed_tenant_id"] == TENANT_ID


@pytest.mark.asyncio
async def test_non_platform_admin_no_audit() -> None:
    """
    A regular operator GET (no X-Platform-Admin header) must NOT emit
    platform_admin.access.
    Source: T-1.13.4.
    """
    from admin_api.middleware.platform_admin_audit import emit_platform_admin_access

    session = _make_mock_session(rows=[])

    with patch("admin_api.middleware.platform_admin_audit.audit_emit", new=AsyncMock()) as mock_emit:
        from fastapi import Request
        mock_request = MagicMock(spec=Request)
        mock_request.headers = {}  # No X-Platform-Admin header
        mock_request.url.path = AUDIT_URL

        await emit_platform_admin_access(
            request=mock_request,
            session=session,
            tenant_id=TENANT_ID,
            resource_type="audit_events",
        )

    mock_emit.assert_not_called()
