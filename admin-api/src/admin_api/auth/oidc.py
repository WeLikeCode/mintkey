"""
OIDC login flow via Keycloak (PKCE).

Source: design §4; Req 2 AC6; ADR-0009.
"""
from __future__ import annotations

import base64
import hashlib
import os
import secrets
from typing import Any

KEYCLOAK_BASE = os.getenv("KEYCLOAK_BASE_URL", "http://keycloak:8080")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "mintkey")
OIDC_CLIENT_ID = os.getenv("OIDC_CLIENT_ID", "mintkey-admin")
OIDC_REDIRECT_URI = os.getenv(
    "OIDC_REDIRECT_URI", "http://localhost:8080/v1/auth/oidc/callback"
)

# In-memory state store (production: Redis/DB — deferred per open-questions register).
_state_store: dict[str, dict] = {}


def generate_authorization_url() -> tuple[str, str, str]:
    """Return (auth_url, state, code_verifier).

    Implements PKCE S256 per RFC 7636.
    Source: Req 2 AC6.
    """
    state = secrets.token_urlsafe(32)
    code_verifier = secrets.token_urlsafe(64)

    digest = hashlib.sha256(code_verifier.encode()).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()

    _state_store[state] = {"code_verifier": code_verifier}

    auth_url = (
        f"{KEYCLOAK_BASE}/realms/{KEYCLOAK_REALM}/protocol/openid-connect/auth"
        f"?client_id={OIDC_CLIENT_ID}"
        f"&response_type=code"
        f"&state={state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&redirect_uri={OIDC_REDIRECT_URI}"
    )
    return auth_url, state, code_verifier


async def oidc_token_exchange(code: str, state: str) -> dict[str, Any]:
    """Exchange authorization code for verified ID token claims.

    Raises ValueError("state_mismatch") if the state is unknown or tampered.
    Raises Exception on token exchange or signature verification failure.

    This function is patched in tests.
    Full authlib integration wired in T-1.1.3.
    Source: Req 2 AC6.
    """
    stored = _state_store.pop(state, None)
    if stored is None:
        raise ValueError("state_mismatch")

    # Real implementation: use authlib AsyncOAuth2Client to exchange code,
    # then verify the ID token signature against Keycloak's JWKS endpoint.
    # Deferred to T-1.1.3; tests mock this function directly.
    raise NotImplementedError("oidc_token_exchange not yet wired to Keycloak")


async def lookup_operator_by_oidc_sub(sub: str) -> Any | None:
    """Return the operator whose oidc_sub matches, or None.

    Stub: full DB lookup wired in T-1.1.3.
    Patched in tests.
    Source: Req 2 AC6.
    """
    return None
