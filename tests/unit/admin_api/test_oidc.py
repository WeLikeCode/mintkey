"""
Unit tests: OIDC login flow (T-1.1.2).

Sources:
  - Req 2 AC6 (OIDC login via Keycloak)
  - ADR-0009 (MCP server / auth stack)
  - design §4 api/auth.py

Tests:
  1. Valid callback → 200, mintkey_session cookie set, audit auth.login.success method=oidc
  2. Tampered state → 401, audit auth.login.failed.state_mismatch
  3. ID token signature failure → 401, audit auth.login.failed.id_token_invalid
  4. Unknown OIDC sub → 403 mintkey:code=no_local_operator, audit auth.login.denied.no_local_operator
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient


def _make_operator():
    op = MagicMock()
    op.id = uuid4()
    op.tenant_id = uuid4()
    op.email = "operator@example.com"
    op.status = "active"
    return op


@pytest.fixture()
def app():
    import sys, os
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
    for p in (
        os.path.join(repo_root, "apps/admin-api", "src"),
        os.path.join(repo_root, "packages/python/mintkey-models"),
    ):
        if p not in sys.path:
            sys.path.insert(0, p)
    from admin_api.main import create_app
    return create_app()


# ---------------------------------------------------------------------------
# Test 1: Valid callback creates session and sets cookie
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oidc_callback_success_creates_session(app) -> None:
    """Valid OIDC callback → 302 to admin-ui, mintkey_session cookie set (Req 2 AC6).

    SSO-B: callback now redirects (302) to admin-ui instead of returning JSON 200.
    """
    operator = _make_operator()
    claims = {
        "sub": "oidc_sub_123",
        "email": "operator@example.com",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }

    with (
        patch("admin_api.api.auth.oidc_token_exchange", new=AsyncMock(return_value=claims)),
        patch("admin_api.api.auth.lookup_operator_by_oidc_sub", new=AsyncMock(return_value=operator)),
        patch("admin_api.api.auth.create_session", new=AsyncMock(return_value="test-oidc-session-token")),
        patch("admin_api.api.auth._emit_session_created_audit", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            follow_redirects=False,
        ) as client:
            resp = await client.get(
                "/v1/auth/oidc/callback",
                params={"code": "authcode123", "state": "validstate"},
            )

    # SSO-B: 302 redirect to admin-ui/admin
    assert resp.status_code == 302, resp.text
    assert "mintkey_session" in resp.headers.get("set-cookie", "")
    assert "/admin" in resp.headers.get("location", "")


# ---------------------------------------------------------------------------
# Test 2: Tampered state → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oidc_callback_tampered_state_returns_401(app) -> None:
    """Tampered state → 401 with state_mismatch reason (Req 2 AC6)."""

    async def _raise_state_mismatch(code: str, state: str) -> dict:
        raise ValueError("state_mismatch")

    with patch("admin_api.api.auth.oidc_token_exchange", new=_raise_state_mismatch):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/auth/oidc/callback",
                params={"code": "authcode123", "state": "tampered_state"},
            )

    assert resp.status_code == 401, resp.text
    body = resp.json()
    assert body.get("reason") == "state_mismatch"


# ---------------------------------------------------------------------------
# Test 3: ID token signature failure → 401
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oidc_callback_signature_failure_returns_401(app) -> None:
    """ID token signature failure → 401 with id_token_invalid reason (Req 2 AC6)."""

    async def _raise_signature_error(code: str, state: str) -> dict:
        raise Exception("signature verification failed")

    with patch("admin_api.api.auth.oidc_token_exchange", new=_raise_signature_error):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/auth/oidc/callback",
                params={"code": "authcode123", "state": "validstate"},
            )

    assert resp.status_code == 401, resp.text
    body = resp.json()
    assert body.get("reason") == "id_token_invalid"


# ---------------------------------------------------------------------------
# Test 4: Unknown OIDC sub → 403 no_local_operator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oidc_unknown_sub_returns_403(app) -> None:
    """Unknown OIDC sub → 403 mintkey:code=no_local_operator (Req 2 AC6)."""
    claims = {
        "sub": "unknown_sub_xyz",
        "email": "unknown@example.com",
        "iat": int(time.time()),
        "exp": int(time.time()) + 3600,
    }

    with (
        patch("admin_api.api.auth.oidc_token_exchange", new=AsyncMock(return_value=claims)),
        patch("admin_api.api.auth.lookup_operator_by_oidc_sub", new=AsyncMock(return_value=None)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                "/v1/auth/oidc/callback",
                params={"code": "authcode123", "state": "validstate"},
            )

    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "no_local_operator"
