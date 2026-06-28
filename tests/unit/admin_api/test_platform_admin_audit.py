"""
Unit tests: PlatformAdmin cross-tenant access audit emission.

Tests that platform_admin.access audit events are emitted on PlatformAdmin reads.

Test cases:
  1. test_platform_admin_audit_emitted_on_read: caller with a valid platform-admin session
     → audit_emit called with event_type="platform_admin.access" and real actor_id
  2. test_platform_admin_audit_has_resource_type: payload contains resource_type
     and viewed_tenant_id
  3. test_non_platform_admin_no_audit: no session cookie → NO platform_admin.access emitted

Session-based authz per ADR-0027 §D2 — X-Platform-Admin header is no longer trusted.

Sources:
  - ADR-0014.7 (audit emit on every state change)
  - T-1.13.4
  - ADR-0027 §D2
"""
from __future__ import annotations

import sys
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
AUDIT_URL = f"/v1/tenants/{TENANT_ID}/audit"
OPERATOR_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")


def _make_mock_db_session(rows=None):
    session = MagicMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.fetchall.return_value = rows or []
        result.fetchone.return_value = None
        return result

    session.execute = _execute
    return session


def _make_platform_admin_session_ctx(operator_id=OPERATOR_ID):
    """Return a fake session ctx object."""
    class _Ctx:
        pass
    ctx = _Ctx()
    ctx.operator_id = operator_id
    return ctx


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_platform_admin_audit_emitted_on_read() -> None:
    """
    emit_platform_admin_access with a valid platform-admin session calls audit_emit
    with event_type="platform_admin.access" and actor_id from the session.
    Source: T-1.13.4; ADR-0014.7; ADR-0027 §D2.
    """
    from admin_api.middleware.platform_admin_audit import emit_platform_admin_access

    session = _make_mock_db_session(rows=[])
    ctx = _make_platform_admin_session_ctx()

    with patch("admin_api.middleware.platform_admin_audit.audit_emit", new=AsyncMock()) as mock_emit, \
         patch("admin_api.middleware.platform_admin_audit.validate_session", new=AsyncMock(return_value=ctx)), \
         patch("admin_api.middleware.platform_admin_audit._is_operator_platform_admin", new=AsyncMock(return_value=True)):

        from fastapi import Request
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {"mintkey_session": "some-session-token"}
        mock_request.url.path = AUDIT_URL
        mock_request.method = "GET"

        await emit_platform_admin_access(
            request=mock_request,
            session=session,
            tenant_id=TENANT_ID,
            resource_type="audit_events",
        )

    mock_emit.assert_called_once()
    call_kwargs = mock_emit.call_args.kwargs
    assert call_kwargs["event_type"] == "platform_admin.access"
    assert call_kwargs["actor_id"] == OPERATOR_ID


@pytest.mark.asyncio
async def test_platform_admin_audit_has_resource_type() -> None:
    """
    The platform_admin.access audit event payload must contain resource_type
    and viewed_tenant_id.
    Source: T-1.13.4.
    """
    from admin_api.middleware.platform_admin_audit import emit_platform_admin_access

    session = _make_mock_db_session(rows=[])
    ctx = _make_platform_admin_session_ctx()

    with patch("admin_api.middleware.platform_admin_audit.audit_emit", new=AsyncMock()) as mock_emit, \
         patch("admin_api.middleware.platform_admin_audit.validate_session", new=AsyncMock(return_value=ctx)), \
         patch("admin_api.middleware.platform_admin_audit._is_operator_platform_admin", new=AsyncMock(return_value=True)):

        from fastapi import Request
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {"mintkey_session": "some-session-token"}
        mock_request.url.path = AUDIT_URL
        mock_request.method = "GET"

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
    A caller with no session cookie must NOT emit platform_admin.access.
    Source: T-1.13.4; ADR-0027 §D2.
    """
    from admin_api.middleware.platform_admin_audit import emit_platform_admin_access

    session = _make_mock_db_session(rows=[])

    with patch("admin_api.middleware.platform_admin_audit.audit_emit", new=AsyncMock()) as mock_emit:
        from fastapi import Request
        mock_request = MagicMock(spec=Request)
        mock_request.cookies = {}  # No mintkey_session cookie
        mock_request.url.path = AUDIT_URL
        mock_request.method = "GET"

        await emit_platform_admin_access(
            request=mock_request,
            session=session,
            tenant_id=TENANT_ID,
            resource_type="audit_events",
        )

    mock_emit.assert_not_called()
