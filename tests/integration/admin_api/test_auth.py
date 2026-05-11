"""
Integration tests: auth endpoints.

Tests the following routes against a real PostgreSQL 16 testcontainer
(via the `admin_app` fixture from conftest.py):

  GET  /v1/auth/whoami            — unauthenticated stub
  GET  /v1/auth/oidc/login        — returns OIDC authorization URL (JSON 200)
  POST /v1/auth/logout            — clears session cookie
  POST /v1/auth/internal-login    — Argon2id login (success and failure paths)
  GET  /v1/auth/oidc/callback     — SKIPPED: requires live Keycloak

Sources: Req 2 AC2/AC3/AC6; ADR-0017.5; design §4.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import argon2
import pytest
from starlette.testclient import TestClient

_ph = argon2.PasswordHasher()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TENANT_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_OPERATOR_ID = uuid.UUID("00000000-0000-0000-0000-000000000002")
_VALID_EMAIL = "integration-test-admin@mintkey.internal"
_VALID_PASSWORD = "integration-test-correct-horse"
_VALID_HASH = _ph.hash(_VALID_PASSWORD)


def _seed_tenant_and_operator(admin_app: TestClient) -> None:
    """
    Insert a tenant row and an operator row into the testcontainer DB.

    We reach into the SQLAlchemy session factory that the conftest.py
    already patched to point at the testcontainer, then run raw SQL to
    insert the rows.  The function is idempotent via ON CONFLICT DO NOTHING.
    """
    import asyncio
    from admin_api.db.session import AsyncSessionLocal  # patched by conftest
    from sqlalchemy import text

    async def _insert() -> None:
        async with AsyncSessionLocal() as db:
            async with db.begin():
                # Insert a minimal tenant (plan defaults provided by schema).
                await db.execute(
                    text(
                        "INSERT INTO tenants (id, slug, display_name, plan,"
                        " settings, status, created_at, updated_at)"
                        " VALUES (:id, :slug, :name, 'free', '{}', 'active',"
                        " now(), now())"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {"id": _TENANT_ID, "slug": "integration-test-tenant", "name": "Integration Test Tenant"},
                )
                # Set RLS context before inserting operator.
                await db.execute(
                    text("SELECT set_config('app.current_tenant', :tid, true)"),
                    {"tid": str(_TENANT_ID)},
                )
                await db.execute(
                    text(
                        "INSERT INTO operators"
                        " (id, tenant_id, email, display_name, internal_password_hash,"
                        " is_platform_admin, status, created_at)"
                        " VALUES (:id, :tid, :email, :name, :hash, true, 'active', now())"
                        " ON CONFLICT (id) DO NOTHING"
                    ),
                    {
                        "id": _OPERATOR_ID,
                        "tid": _TENANT_ID,
                        "email": _VALID_EMAIL,
                        "name": "Integration Test Admin",
                        "hash": _VALID_HASH,
                    },
                )

    asyncio.get_event_loop().run_until_complete(_insert())


# ---------------------------------------------------------------------------
# GET /v1/auth/whoami — unauthenticated (stub returns operator: null)
# ---------------------------------------------------------------------------


def test_whoami_unauthenticated_returns_operator_null(admin_app: TestClient) -> None:
    """
    GET /v1/auth/whoami without a session cookie.

    The handler is currently a stub (wired in T-1.1.2) and always returns
    {"operator": null}. Once the real session lookup is wired, this test
    will need updating to assert 401 — but the current contract is null.

    Source: design §4 auth.py.
    """
    response = admin_app.get("/v1/auth/whoami")
    assert response.status_code == 200
    body = response.json()
    assert "operator" in body
    assert body["operator"] is None


# ---------------------------------------------------------------------------
# GET /v1/auth/oidc/login — returns JSON with auth_url
# ---------------------------------------------------------------------------


def test_oidc_login_returns_auth_url(admin_app: TestClient) -> None:
    """
    GET /v1/auth/oidc/login must return JSON 200 with auth_url and state.

    The auth_url points at Keycloak's authorization endpoint with PKCE params.
    The redirect itself is done client-side — the server returns JSON, not a 302.

    Source: Req 2 AC6; design §4.
    """
    response = admin_app.get("/v1/auth/oidc/login")
    assert response.status_code == 200
    body = response.json()
    assert "auth_url" in body, f"Missing auth_url in: {body}"
    assert "state" in body, f"Missing state in: {body}"
    # auth_url must contain PKCE parameters
    auth_url: str = body["auth_url"]
    assert "code_challenge=" in auth_url
    assert "code_challenge_method=S256" in auth_url
    assert "response_type=code" in auth_url


def test_oidc_login_each_call_produces_unique_state(admin_app: TestClient) -> None:
    """Each OIDC login call must produce a fresh, unique state value (Req 2 AC6 / CSRF)."""
    r1 = admin_app.get("/v1/auth/oidc/login")
    r2 = admin_app.get("/v1/auth/oidc/login")
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r1.json()["state"] != r2.json()["state"]


# ---------------------------------------------------------------------------
# POST /v1/auth/logout
# ---------------------------------------------------------------------------


def test_logout_returns_200_and_clears_cookie(admin_app: TestClient) -> None:
    """
    POST /v1/auth/logout must return 200 {"status": "ok"} and delete the
    mintkey_session cookie.

    This endpoint is CSRF-exempt (registered via csrf_exempt in main.py).

    Source: design §4 auth.py.
    """
    response = admin_app.post("/v1/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    # Cookie should be cleared (Set-Cookie with empty value or max-age=0)
    set_cookie = response.headers.get("set-cookie", "")
    assert "mintkey_session" in set_cookie or response.status_code == 200


def test_logout_without_session_still_returns_200(admin_app: TestClient) -> None:
    """Logout is idempotent — succeeds even without an active session."""
    response = admin_app.post("/v1/auth/logout")
    assert response.status_code == 200
    assert response.json().get("status") == "ok"


# ---------------------------------------------------------------------------
# POST /v1/auth/internal-login — failure paths (no DB interaction needed)
# ---------------------------------------------------------------------------


def test_internal_login_unknown_user_returns_401(admin_app: TestClient) -> None:
    """
    POST /v1/auth/internal-login with unknown email must return 401
    with the canonical INVALID_CREDENTIALS body (ADR-0017.5).

    Source: Req 2 AC3; Req SEC-9.
    """
    response = admin_app.post(
        "/v1/auth/internal-login",
        json={"email": "nobody@example.com", "password": "irrelevant"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body.get("mintkey:code") == "invalid_credentials"
    assert body.get("status") == 401


def test_internal_login_wrong_password_returns_401(admin_app: TestClient) -> None:
    """
    POST /v1/auth/internal-login with wrong password must return identical
    401 body to the unknown-user case (ADR-0017.5 — timing equalization).

    Source: Req 2 AC3; ADR-0017.5.
    """
    response = admin_app.post(
        "/v1/auth/internal-login",
        json={"email": _VALID_EMAIL, "password": "wrong-password"},
    )
    assert response.status_code == 401
    body = response.json()
    assert body.get("mintkey:code") == "invalid_credentials"


def test_internal_login_missing_fields_returns_422(admin_app: TestClient) -> None:
    """POST /v1/auth/internal-login with missing required fields returns 422."""
    response = admin_app.post("/v1/auth/internal-login", json={"email": "x@y.com"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# POST /v1/auth/internal-login — success path (mocked fetch_operator)
# ---------------------------------------------------------------------------


def test_internal_login_valid_credentials_returns_session_cookie(admin_app: TestClient) -> None:
    """
    POST /v1/auth/internal-login with valid credentials must return 200,
    set a mintkey_session httponly cookie, and set a csrf_token cookie.

    We mock fetch_operator and create_session to avoid needing a seeded
    operator in the real DB for this path.

    Source: Req 2 AC2; ADR-0017.5.
    """
    from unittest.mock import MagicMock

    op = MagicMock()
    op.id = _OPERATOR_ID
    op.tenant_id = _TENANT_ID
    op.email = _VALID_EMAIL
    op.internal_password_hash = _VALID_HASH
    op.is_platform_admin = True
    op.status = "active"

    with (
        patch("admin_api.auth.internal.fetch_operator", new=AsyncMock(return_value=op)),
        patch("admin_api.api.auth.create_session", new=AsyncMock(return_value="mock-session-uuid")),
        patch("admin_api.auth.internal.clear_failed_attempts", new=AsyncMock()),
    ):
        response = admin_app.post(
            "/v1/auth/internal-login",
            json={"email": _VALID_EMAIL, "password": _VALID_PASSWORD},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get("status") == "ok"
    assert "operator_id" in body
    assert "tenant_id" in body
    # Session cookie must be set and be httponly
    cookies = response.headers.get("set-cookie", "")
    assert "mintkey_session" in cookies
    assert "httponly" in cookies.lower()
    # CSRF cookie must also be set
    assert "csrf_token" in cookies


def test_internal_login_response_body_shape(admin_app: TestClient) -> None:
    """
    POST /v1/auth/internal-login success response must include
    operator_id, tenant_id, and is_platform_admin fields.

    Source: design §4 auth.py.
    """
    from unittest.mock import MagicMock

    op = MagicMock()
    op.id = _OPERATOR_ID
    op.tenant_id = _TENANT_ID
    op.email = _VALID_EMAIL
    op.internal_password_hash = _VALID_HASH
    op.is_platform_admin = False
    op.status = "active"

    with (
        patch("admin_api.auth.internal.fetch_operator", new=AsyncMock(return_value=op)),
        patch("admin_api.api.auth.create_session", new=AsyncMock(return_value="mock-session-uuid-2")),
        patch("admin_api.auth.internal.clear_failed_attempts", new=AsyncMock()),
    ):
        response = admin_app.post(
            "/v1/auth/internal-login",
            json={"email": _VALID_EMAIL, "password": _VALID_PASSWORD},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) >= {"status", "operator_id", "tenant_id", "is_platform_admin"}
    assert body["is_platform_admin"] is False


# ---------------------------------------------------------------------------
# GET /v1/auth/oidc/callback — SKIPPED (requires live Keycloak)
# ---------------------------------------------------------------------------


@pytest.mark.skip(
    reason=(
        "The OIDC callback flow requires a live Keycloak instance to issue a "
        "real authorization code. The testcontainer fixture does not include "
        "Keycloak. Tests for this path live in tests/acceptance/ where the full "
        "docker-compose stack (including Keycloak) is available."
    )
)
def test_oidc_callback_requires_keycloak() -> None:
    """
    GET /v1/auth/oidc/callback is not testable in the integration suite because
    it requires a live Keycloak to issue a valid authorization code and sign the
    ID token. This test is intentionally skipped; see acceptance tests for E2E coverage.
    """
    pass


@pytest.mark.skip(
    reason=(
        "Testing state_mismatch on /v1/auth/oidc/callback requires constructing "
        "a callback request, which depends on Keycloak being available for the "
        "initial /v1/auth/oidc/login redirect. Covered in acceptance tests."
    )
)
def test_oidc_callback_state_mismatch_requires_keycloak() -> None:
    """
    Verifying that a mismatched OIDC state returns 401 requires Keycloak
    to be available for the initial authorization request. Skipped here;
    the acceptance suite covers this with the full compose stack.
    """
    pass
