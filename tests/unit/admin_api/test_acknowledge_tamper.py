"""
Unit tests: Acknowledge tamper endpoint.

POST /v1/admin/audit/acknowledge-tamper (PlatformAdmin only)

Test cases:
  1. test_acknowledge_requires_platform_admin: no X-Platform-Admin header → 403
  2. test_acknowledge_records_event: POST with tenant_id + event_id → 201, emits "audit.chain.tamper_acknowledged"
  3. test_acknowledge_audit_payload: payload contains {tenant_id, event_id, acknowledged_by: "platform_admin"}
  4. test_unknown_tenant_returns_404: tenant_id not found → 404 mintkey:code=tenant_not_found

Sources: T-1.13.5; ADR-0014.7; Req 15.
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

ACK_URL = "/v1/admin/audit/acknowledge-tamper"
TENANT_ID = "tenant_00000000000000000000000001"
EVENT_ID = "audit_00000000000000000000000042"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_session(tenant_exists: bool = True):
    """Return a mock AsyncSession where tenant lookup returns a row or None."""
    session = MagicMock()
    session.commit = AsyncMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        # First execute call is the tenant existence check
        result.fetchone.return_value = MagicMock() if tenant_exists else None
        return result

    session.execute = _execute
    return session


def _create_test_app(tenant_exists: bool = True):
    from fastapi import FastAPI
    from admin_api.api.audit_admin import router as audit_admin_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(audit_admin_router)

    async def mock_db_session():
        yield _make_mock_session(tenant_exists=tenant_exists)

    app.dependency_overrides[get_db_session] = mock_db_session

    csrf_exempt(ACK_URL)
    app.add_middleware(CsrfMiddleware)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_acknowledge_requires_platform_admin() -> None:
    """
    POST /v1/admin/audit/acknowledge-tamper without X-Platform-Admin header returns 403.
    Source: T-1.13.5.
    """
    app = _create_test_app()

    with patch("mintkey_models.audit.audit_emit", new_callable=AsyncMock):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                ACK_URL,
                params={"tenant_id": TENANT_ID, "event_id": EVENT_ID},
            )

    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "permission_denied"


@pytest.mark.asyncio
async def test_acknowledge_records_event() -> None:
    """
    POST /v1/admin/audit/acknowledge-tamper with valid PlatformAdmin header returns 201
    and emits "audit.chain.tamper_acknowledged".
    Source: T-1.13.5; ADR-0014.7.
    """
    app = _create_test_app(tenant_exists=True)

    with patch("admin_api.api.audit_admin.audit_emit", new_callable=AsyncMock) as mock_emit:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                ACK_URL,
                params={"tenant_id": TENANT_ID, "event_id": EVENT_ID},
                headers={"X-Platform-Admin": "true"},
            )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["acknowledged"] is True
    assert body["event_id"] == EVENT_ID
    assert body["tenant_id"] == TENANT_ID

    mock_emit.assert_awaited_once()
    call_kwargs = mock_emit.call_args.kwargs
    assert call_kwargs["event_type"] == "audit.chain.tamper_acknowledged"


@pytest.mark.asyncio
async def test_acknowledge_audit_payload() -> None:
    """
    The audit event payload must contain {tenant_id, event_id, acknowledged_by: "platform_admin"}.
    Source: T-1.13.5; ADR-0014.7.
    """
    app = _create_test_app(tenant_exists=True)

    with patch("admin_api.api.audit_admin.audit_emit", new_callable=AsyncMock) as mock_emit:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            await client.post(
                ACK_URL,
                params={"tenant_id": TENANT_ID, "event_id": EVENT_ID},
                headers={"X-Platform-Admin": "true"},
            )

    call_kwargs = mock_emit.call_args.kwargs
    payload = call_kwargs["payload"]
    assert payload["tenant_id"] == TENANT_ID
    assert payload["event_id"] == EVENT_ID
    assert payload["acknowledged_by"] == "platform_admin"


@pytest.mark.asyncio
async def test_unknown_tenant_returns_404() -> None:
    """
    POST /v1/admin/audit/acknowledge-tamper with a non-existent tenant_id returns 404
    with mintkey:code=tenant_not_found.
    Source: T-1.13.5.
    """
    app = _create_test_app(tenant_exists=False)

    with patch("admin_api.api.audit_admin.audit_emit", new_callable=AsyncMock) as mock_emit:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                ACK_URL,
                params={"tenant_id": "tenant_nonexistent0000000000001", "event_id": EVENT_ID},
                headers={"X-Platform-Admin": "true"},
            )

    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "tenant_not_found"
    mock_emit.assert_not_awaited()
