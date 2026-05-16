"""
OIDC login flow via Keycloak (PKCE).

Source: design §4; Req 2 AC6; ADR-0009; ADR-0016.2 (JWKS cache + force-refresh).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import secrets
import time
from typing import Any

from authlib.jose import JsonWebToken
from authlib.jose.errors import JoseError
import httpx

_logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Env-var resolvers (read lazily so tests can override without module-load order
# issues; resolved on first call).
# ---------------------------------------------------------------------------

def _keycloak_internal_url() -> str:
    from admin_api.config.public_urls import resolve_keycloak_internal_url
    return resolve_keycloak_internal_url()


def _keycloak_public_url() -> str:
    from admin_api.config.public_urls import resolve_keycloak_public_url
    return resolve_keycloak_public_url()


KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "mintkey")
OIDC_CLIENT_ID = "mintkey-admin-api"

_OIDC_CLIENT_SECRET_FILE = os.getenv(
    "OIDC_CLIENT_SECRET_FILE",
    "/run/secrets/mintkey/bootstrap-secrets/oidc_client_secret",
)

_SECRET_CACHE: str | None = None


def _read_client_secret() -> str:
    global _SECRET_CACHE
    if _SECRET_CACHE is not None:
        return _SECRET_CACHE
    try:
        _SECRET_CACHE = open(_OIDC_CLIENT_SECRET_FILE).read().strip()
        return _SECRET_CACHE
    except OSError:
        _logger.warning("oidc_client_secret file not found at %s", _OIDC_CLIENT_SECRET_FILE)
        return ""


# ---------------------------------------------------------------------------
# JWKS cache (ADR-0016.2 pattern: 1 h TTL, force-refresh on signature mismatch)
# ---------------------------------------------------------------------------

_JWKS_CACHE: dict[str, Any] | None = None
_JWKS_FETCHED_AT: float = 0.0
_JWKS_TTL = 3600.0  # 1 hour
_jwks_lock = asyncio.Lock()


async def _fetch_jwks(force: bool = False) -> dict[str, Any]:
    """Return JWKS from cache or re-fetch. Force-refreshes on signature mismatch."""
    global _JWKS_CACHE, _JWKS_FETCHED_AT

    async with _jwks_lock:
        now = time.monotonic()
        if not force and _JWKS_CACHE is not None and (now - _JWKS_FETCHED_AT) < _JWKS_TTL:
            return _JWKS_CACHE

        url = f"{_keycloak_internal_url()}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/certs"
        _logger.info("oidc.jwks_fetch url=%s force=%s", url, force)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            _JWKS_CACHE = resp.json()
            _JWKS_FETCHED_AT = time.monotonic()
        return _JWKS_CACHE


# ---------------------------------------------------------------------------
# In-memory state store (single-server PKCE state; Redis deferred per open-Q)
# ---------------------------------------------------------------------------

_state_store: dict[str, dict[str, str]] = {}


def generate_authorization_url() -> tuple[str, str, str]:
    """Return (auth_url, state, code_verifier).

    Uses MINTKEY_KEYCLOAK_PUBLIC_URL for the browser-facing redirect.
    Implements PKCE S256 per RFC 7636.
    Source: Req 2 AC6.
    """
    admin_api_public = os.getenv("MINTKEY_ADMIN_API_PUBLIC_URL", "http://localhost:8080")
    redirect_uri = f"{admin_api_public.rstrip('/')}/v1/auth/oidc/callback"

    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)

    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    _state_store[state] = {"code_verifier": code_verifier, "redirect_uri": redirect_uri}

    auth_url = (
        f"{_keycloak_public_url()}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth"
        f"?client_id={OIDC_CLIENT_ID}"
        f"&response_type=code"
        f"&scope=openid+email+profile"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&redirect_uri={redirect_uri}"
    )
    return auth_url, state, code_verifier


async def oidc_token_exchange(code: str, state: str) -> dict[str, Any]:
    """Exchange authorization code for verified ID token claims.

    Raises ValueError("state_mismatch") if the state is unknown or tampered.
    Raises Exception on token exchange or signature verification failure.

    Source: Req 2 AC6; ADR-0016.2.
    """
    stored = _state_store.pop(state, None)
    if stored is None:
        raise ValueError("state_mismatch")

    code_verifier = stored["code_verifier"]
    redirect_uri = stored["redirect_uri"]
    client_secret = _read_client_secret()

    token_url = (
        f"{_keycloak_internal_url()}/realms/{KEYCLOAK_REALM}"
        f"/protocol/openid-connect/token"
    )

    # POST to token endpoint using httpx directly (authlib AsyncOAuth2Client)
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
                "client_id": OIDC_CLIENT_ID,
                "client_secret": client_secret,
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    if resp.status_code != 200:
        _logger.error(
            "oidc.token_exchange_failed status=%s body=%s",
            resp.status_code, resp.text[:200],
        )
        raise Exception(f"token exchange failed: HTTP {resp.status_code}")

    token_response = resp.json()
    id_token = token_response.get("id_token")
    if not id_token:
        raise Exception("id_token missing from token response")

    # Verify ID token signature. Force-refresh JWKS on failure (ADR-0016.2).
    claims = await _verify_id_token(id_token, force_refresh=False)
    return claims


async def _verify_id_token(id_token: str, *, force_refresh: bool) -> dict[str, Any]:
    """Verify ID token signature against Keycloak JWKS. Force-refreshes on first failure."""

    # Use the PUBLIC URL here: Keycloak embeds the URL the browser hit (the
    # public-facing base URL) as the `iss` claim in issued ID tokens.
    # admin-api's token-exchange POST and JWKS fetch stay on the internal URL
    # (server-to-server); only iss validation must match the browser-visible URL.
    # Mirror of SSO-E redux 31270130 that applied the same fix to jaeger-auth.
    expected_issuer = f"{_keycloak_public_url()}/realms/{KEYCLOAK_REALM}"

    jwks = await _fetch_jwks(force=force_refresh)

    try:
        jwt = JsonWebToken(["RS256", "RS384", "RS512", "ES256", "ES384", "ES512"])
        claims = jwt.decode(  # type: ignore[call-overload]  # authlib stubs expect JWK/str but runtime accepts JWKS dict
            id_token,
            jwks,
            claims_options={
                "iss": {"essential": True, "value": expected_issuer},
                "aud": {"essential": True, "value": OIDC_CLIENT_ID},
            },
        )
        claims.validate()
        return dict(claims)
    except JoseError as exc:
        if not force_refresh:
            _logger.warning(
                "oidc.id_token_verify_failed error=%s — force-refreshing JWKS (ADR-0016.2)",
                exc,
            )
            return await _verify_id_token(id_token, force_refresh=True)
        _logger.error("oidc.id_token_verify_failed_after_refresh error=%s", exc)
        raise Exception(f"ID token signature verification failed: {exc}") from exc


async def lookup_operator_by_oidc_sub(
    sub: str,
    email: str | None = None,
) -> Any | None:
    """Look up operator by oidc_sub; fall back to email link on first login.

    Shadow-operator model (D1):
    1. SELECT by oidc_sub (fast path after pre-link).
    2. If None and email provided: SELECT by email, UPDATE oidc_sub (lazy link).
    3. If still None: log error, return None (callback will 403).

    Source: Req 2 AC6; D1 shadow operators.
    """
    from admin_api.db.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        async with db.begin():
            # Need platform_admin_view to bypass RLS for cross-tenant lookup.
            await db.execute(
                text(
                    "SELECT set_config('app.current_tenant',"
                    " '00000000-0000-0000-0000-000000000000', true),"
                    " set_config('app.platform_admin_view', 'on', true)"
                )
            )

            # Step 1: lookup by oidc_sub
            result = await db.execute(
                text(
                    "SELECT id, tenant_id, email, is_platform_admin, status, internal_password_hash"
                    " FROM operators WHERE oidc_sub = :sub"
                ),
                {"sub": sub},
            )
            row = result.fetchone()

            if row is not None:
                return _row_to_operator(row)

            # Step 2: lazy first-login link by email
            if email:
                result2 = await db.execute(
                    text(
                        "SELECT id, tenant_id, email, is_platform_admin, status, internal_password_hash"
                        " FROM operators WHERE email = :email"
                    ),
                    {"email": email},
                )
                row2 = result2.fetchone()
                if row2 is not None:
                    _logger.info(
                        "oidc.lazy_link email=%s sub=%s operator_id=%s",
                        email, sub, row2[0],
                    )
                    await db.execute(
                        text(
                            "UPDATE operators SET oidc_sub = :sub WHERE id = :oid"
                        ),
                        {"sub": sub, "oid": str(row2[0])},
                    )
                    return _row_to_operator(row2)

            _logger.error(
                "oidc.operator_not_found sub=%s email=%s — 403 will be returned",
                sub, email,
            )
            return None


def _row_to_operator(row: Any) -> Any:
    """Wrap a raw DB row as a simple namespace object."""
    class _Op:
        def __init__(self, r: Any) -> None:
            self.id = r[0]
            self.tenant_id = r[1]
            self.email = r[2]
            self.is_platform_admin = bool(r[3])
            self.status = r[4]
            self.internal_password_hash = r[5]
    return _Op(row)


def extract_realm_roles(claims: dict[str, Any]) -> list[str]:
    """Extract realm roles from ID token claims.realm_access.roles."""
    realm_access = claims.get("realm_access", {})
    return list(realm_access.get("roles", []))


def is_platform_admin_from_claims(claims: dict[str, Any]) -> bool:
    """Return True if mintkey-platform-admin realm role is present."""
    return "mintkey-platform-admin" in extract_realm_roles(claims)
