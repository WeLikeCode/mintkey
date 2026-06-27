"""
Unit tests: Admin Settings endpoints.

GET   /v1/admin/settings — retrieve platform settings (PlatformAdmin only)
PATCH /v1/admin/settings — update platform settings (PlatformAdmin only)

Test cases:
  1. test_get_settings_as_platform_admin: returns full AdminSettings
  2. test_get_settings_as_non_platform_admin: 403 mintkey:code=permission_denied
  3. test_patch_merges_partial_body: missing keys retain existing values
  4. test_patch_unknown_key_returns_422: extra="forbid" enforcement
  5. test_patch_emits_settings_updated_audit

Sources:
  - ADR-0014.7 (audit emit on every state change)
  - T-1.13.1
"""
from __future__ import annotations

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

SETTINGS_URL = "/v1/admin/settings"


async def _noop_platform_admin():
    """Dep override: treat all callers as platform-admin."""
    return None


def _make_mock_session(stored_value: str = None):
    """Return an async-capable mock DB session."""
    session = MagicMock()
    session._execute_calls = []

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        result = MagicMock()
        if stored_value is not None:
            row = MagicMock()
            row.value = stored_value
            result.fetchone.return_value = row
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _create_test_app(is_platform_admin: bool = True, stored_value: str = None):
    """Build a minimal FastAPI app with the settings router and mocked DB.

    When is_platform_admin=True, require_platform_admin_session is overridden to a no-op.
    When is_platform_admin=False, the real dependency runs (no cookie → 401).
    """
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from admin_api.api.settings import router as settings_router
    from admin_api.api.permissions import validation_error_handler
    from admin_api.auth.sessions import require_platform_admin_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(settings_router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    async def mock_db_session():
        yield _make_mock_session(stored_value=stored_value)

    app.dependency_overrides[get_db_session] = mock_db_session
    if is_platform_admin:
        app.dependency_overrides[require_platform_admin_session] = _noop_platform_admin

    csrf_exempt(SETTINGS_URL)
    app.add_middleware(CsrfMiddleware)

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_settings_as_platform_admin() -> None:
    """
    GET /v1/admin/settings with X-Platform-Admin: true returns 200 with full AdminSettings.
    Source: T-1.13.1.
    """
    app = _create_test_app(is_platform_admin=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(SETTINGS_URL)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "oidc" in body
    assert "audit" in body
    assert "enabled" in body["oidc"]
    assert "retention_days" in body["audit"]


@pytest.mark.asyncio
async def test_get_settings_as_non_platform_admin() -> None:
    """
    GET /v1/admin/settings without a valid platform-admin session returns 401.
    Session-based authz (ADR-0027 §D2); no session cookie → 401 unauthenticated.
    Source: T-1.13.1.
    """
    app = _create_test_app(is_platform_admin=False)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(SETTINGS_URL)

    assert resp.status_code == 401, resp.text
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("mintkey:code") == "unauthenticated"


@pytest.mark.asyncio
async def test_patch_merges_partial_body() -> None:
    """
    PATCH with only {"audit": {"retention_days": 180}} must preserve all
    other fields at their defaults.
    Source: T-1.13.1.
    """
    app = _create_test_app(is_platform_admin=True)

    with patch("admin_api.api.settings.audit_emit", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                SETTINGS_URL,
                json={"audit": {"retention_days": 180}},
                )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Patched field is updated
    assert body["audit"]["retention_days"] == 180
    # Unmentioned sub-field retains default
    assert body["audit"]["chain_verify_interval_hours"] == 24
    # Whole other section retained at defaults
    assert "oidc" in body
    assert body["oidc"]["enabled"] is False


@pytest.mark.asyncio
async def test_patch_unknown_key_returns_422() -> None:
    """
    PATCH with an unknown top-level key returns 422 (Pydantic extra="forbid").
    Source: T-1.13.1.
    """
    app = _create_test_app(is_platform_admin=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.patch(
            SETTINGS_URL,
            json={"unknown_key": "bad"},
        )

    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_get_settings_has_api_key_section() -> None:
    """
    GET /v1/admin/settings must include api_key sub-object with all 5 keys at defaults.
    Source: task 1.2; Req 7.6; ADR-0018 §8.
    """
    app = _create_test_app(is_platform_admin=True)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(SETTINGS_URL)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "api_key" in body, "api_key sub-object missing from AdminSettings"
    ak = body["api_key"]
    assert ak["proxy_cache_ttl_seconds"] == 60
    assert ak["require_expiry"] is False
    assert ak["allow_no_expiry"] is True
    assert ak["max_expiry_days"] == 365
    assert ak["require_ip_allowlist"] is False


@pytest.mark.asyncio
async def test_patch_api_key_settings() -> None:
    """
    PATCH with api_key sub-fields merges correctly; unknown api_key keys → 422.
    Source: task 1.2; Req 10.4; ADR-0016.6 extra="forbid".
    """
    app = _create_test_app(is_platform_admin=True)

    with patch("admin_api.api.settings.audit_emit", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                SETTINGS_URL,
                json={"api_key": {"require_expiry": True, "max_expiry_days": 30}},
                )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["api_key"]["require_expiry"] is True
    assert body["api_key"]["max_expiry_days"] == 30
    assert body["api_key"]["proxy_cache_ttl_seconds"] == 60  # default retained

    # Unknown api_key key → 422 (extra="forbid")
    with patch("admin_api.api.settings.audit_emit", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp2 = await client.patch(
                SETTINGS_URL,
                json={"api_key": {"unknown_flag": True}},
                )
    assert resp2.status_code == 422, resp2.text


@pytest.mark.asyncio
async def test_patch_emits_settings_updated_audit() -> None:
    """
    PATCH must call audit_emit with event_type="settings.updated".
    Source: T-1.13.1; ADR-0014.7.
    """
    app = _create_test_app(is_platform_admin=True)

    with patch("admin_api.api.settings.audit_emit", new=AsyncMock()) as mock_audit:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.patch(
                SETTINGS_URL,
                json={"oidc": {"enabled": True}},
                )

        assert resp.status_code == 200, resp.text
        mock_audit.assert_called_once()
        call_kwargs = mock_audit.call_args.kwargs
        assert call_kwargs.get("event_type") == "settings.updated"
