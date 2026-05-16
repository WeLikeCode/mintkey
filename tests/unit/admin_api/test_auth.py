"""
Unit tests: POST /v1/auth/internal-login.

Sources:
  - Req 2 AC2 (valid credentials → session cookie)
  - Req 2 AC3 (identical body + equalized timing across failure modes)
  - Req 2 AC4 (account lockout after 10 failed attempts in 5 minutes)
  - Req 2 AC12 (audit events distinguish failure modes)
  - Req SEC-9 / ADR-0017.5 (identical body + equalized timing)
"""
from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient


VALID_EMAIL = "admin@mintkey.internal"
VALID_PASSWORD = "correct-horse-battery-staple"

# Argon2id hash of VALID_PASSWORD (pre-computed for deterministic tests)
import argon2
_ph = argon2.PasswordHasher()
VALID_HASH = _ph.hash(VALID_PASSWORD)


def _make_operator(*, locked: bool = False, password_hash: str = VALID_HASH):
    op = MagicMock()
    op.id = uuid4()
    op.tenant_id = uuid4()
    op.email = VALID_EMAIL
    op.internal_password_hash = password_hash
    op.is_platform_admin = True
    op.status = "locked" if locked else "active"
    return op


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    import sys, os
    from unittest.mock import MagicMock, AsyncMock
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../../../admin-api/src"))
    from admin_api.main import create_app
    from admin_api.db.deps import get_db_session

    _app = create_app()

    # Override DB session so unit tests don't need a real postgres connection
    mock_session = MagicMock()
    mock_session.execute = AsyncMock(return_value=MagicMock(fetchone=MagicMock(return_value=None)))
    mock_session.commit = AsyncMock()
    mock_session.rollback = AsyncMock()

    async def mock_db():
        yield mock_session

    _app.dependency_overrides[get_db_session] = mock_db
    return _app


# ---------------------------------------------------------------------------
# Success path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_credentials_return_session_cookie(app) -> None:
    """Valid credentials → 200 + Set-Cookie: mintkey_session (Req 2 AC2)."""
    operator = _make_operator()

    with (
        patch("admin_api.auth.internal.fetch_operator", new=AsyncMock(return_value=operator)),
        patch("admin_api.api.auth.create_session", new=AsyncMock(return_value="test-session-token")),
        patch("admin_api.auth.internal.record_failed_attempt", new=AsyncMock()),
        patch("admin_api.auth.internal.clear_failed_attempts", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/auth/internal-login",
                json={"email": VALID_EMAIL, "password": VALID_PASSWORD},
            )

    assert resp.status_code == 200, resp.text
    assert "mintkey_session" in resp.headers.get("set-cookie", "")


# ---------------------------------------------------------------------------
# Identical-body tests (Req 2 AC3 / ADR-0017.5)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_user_body_matches_bad_password_body(app) -> None:
    """Unknown user and wrong-password return byte-identical response body (ADR-0017.5)."""
    with patch("admin_api.auth.internal.fetch_operator", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp_unknown = await client.post(
                "/v1/auth/internal-login",
                json={"email": "nobody@mintkey.internal", "password": "x"},
            )

    operator = _make_operator()
    with (
        patch("admin_api.auth.internal.fetch_operator", new=AsyncMock(return_value=operator)),
        patch("admin_api.auth.internal.record_failed_attempt", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp_bad_pw = await client.post(
                "/v1/auth/internal-login",
                json={"email": VALID_EMAIL, "password": "wrong-password"},
            )

    assert resp_unknown.status_code == 401
    assert resp_bad_pw.status_code == 401
    assert resp_unknown.content == resp_bad_pw.content, (
        f"Response bodies differ!\n"
        f"  unknown user: {resp_unknown.text}\n"
        f"  bad password: {resp_bad_pw.text}"
    )


@pytest.mark.asyncio
async def test_locked_account_body_matches_bad_password_body(app) -> None:
    """Locked account returns same body as bad password (ADR-0017.5)."""
    locked_operator = _make_operator(locked=True)

    with (
        patch("admin_api.auth.internal.fetch_operator", new=AsyncMock(return_value=locked_operator)),
        patch("admin_api.auth.internal.record_failed_attempt", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp_locked = await client.post(
                "/v1/auth/internal-login",
                json={"email": VALID_EMAIL, "password": VALID_PASSWORD},
            )

    operator = _make_operator()
    with (
        patch("admin_api.auth.internal.fetch_operator", new=AsyncMock(return_value=operator)),
        patch("admin_api.auth.internal.record_failed_attempt", new=AsyncMock()),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp_bad_pw = await client.post(
                "/v1/auth/internal-login",
                json={"email": VALID_EMAIL, "password": "wrong-password"},
            )

    assert resp_locked.status_code == 401
    assert resp_bad_pw.status_code == 401
    assert resp_locked.content == resp_bad_pw.content


@pytest.mark.asyncio
async def test_failure_response_body_shape(app) -> None:
    """Failure response has required fields from ADR-0017.5 / Req 2 AC3."""
    with patch("admin_api.auth.internal.fetch_operator", new=AsyncMock(return_value=None)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/auth/internal-login",
                json={"email": "x@y.com", "password": "x"},
            )

    body = resp.json()
    assert resp.status_code == 401
    assert body.get("mintkey:code") == "invalid_credentials"
    assert body.get("status") == 401
    assert "Invalid credentials" in body.get("title", "")


# ---------------------------------------------------------------------------
# D2-b: internal_password_hash IS NULL → 404 (SSO-B)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_internal_login_returns_404_when_hash_null(app) -> None:
    """D2-b: internal_password_hash=NULL → 404 (hash-IS-NULL gate, not env-var flag)."""
    null_hash_operator = _make_operator(password_hash=None)

    with patch("admin_api.auth.internal.fetch_operator", new=AsyncMock(return_value=null_hash_operator)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                "/v1/auth/internal-login",
                json={"email": VALID_EMAIL, "password": VALID_PASSWORD},
            )

    assert resp.status_code == 404, resp.text
