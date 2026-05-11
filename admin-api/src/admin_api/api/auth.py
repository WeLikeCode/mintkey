"""
Auth endpoints.

POST /v1/auth/internal-login  — Argon2id login (Req 2 AC2/AC3/AC4/ADR-0017.5)
POST /v1/auth/logout
GET  /v1/auth/whoami
GET  /v1/auth/oidc/login      — OIDC PKCE redirect (Req 2 AC6)
GET  /v1/auth/oidc/callback   — OIDC code exchange + session creation

Source: design §4 api/auth.py; Req 2; ADR-0017.5; ADR-0009.
"""
from __future__ import annotations

import secrets

from fastapi import APIRouter, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from admin_api.auth.internal import INVALID_CREDENTIALS_RESPONSE, verify_internal_login
from admin_api.auth.oidc import (
    generate_authorization_url,
    lookup_operator_by_oidc_sub,
    oidc_token_exchange,
)
from admin_api.auth.sessions import create_session
from admin_api.middleware.csrf import no_csrf

router = APIRouter(prefix="/v1/auth")


class LoginRequest(BaseModel):
    email: str
    password: str


@router.post("/internal-login")
@no_csrf  # login is the bootstrap surface; CSRF not yet applicable
async def internal_login(body: LoginRequest, response: Response) -> JSONResponse:
    """
    Argon2id login with identical body + equalized timing.
    All failure paths return the same body (ADR-0017.5 / Req SEC-9).
    Source: Req 2 AC2, AC3, AC4; design §4.
    """
    operator, failure_reason = await verify_internal_login(body.email, body.password)

    if failure_reason is not None:
        # All failures return byte-identical body (ADR-0017.5).
        return JSONResponse(status_code=401, content=INVALID_CREDENTIALS_RESPONSE)

    session_token = await create_session(operator.id, operator.tenant_id)
    csrf_token = secrets.token_urlsafe(32)

    resp = JSONResponse({
        "status": "ok",
        "operator_id": str(operator.id),
        "tenant_id": str(operator.tenant_id),
        "is_platform_admin": bool(operator.is_platform_admin),
    })
    resp.set_cookie(
        key="mintkey_session",
        value=session_token,
        httponly=True,
        secure=False,  # False for local dev; set via env in production
        samesite="lax",
        max_age=86400,
    )
    # Non-httponly so JS can read it for the double-submit CSRF pattern.
    resp.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=False,
        samesite="lax",
        max_age=86400,
    )
    return resp


@router.post("/logout")
async def logout(response: Response) -> JSONResponse:
    response.delete_cookie("mintkey_session")
    return JSONResponse({"status": "ok"})


@router.get("/whoami")
async def whoami() -> JSONResponse:
    """Returns the current operator's identity. Stub: wired in T-1.1.2."""
    return JSONResponse({"operator": None})


@router.get("/oidc/login")
async def oidc_login() -> JSONResponse:
    """
    Return OIDC authorization URL with PKCE. Client redirects the user there.
    Source: Req 2 AC6.
    """
    auth_url, state, _ = generate_authorization_url()
    return JSONResponse({"auth_url": auth_url, "state": state})


@router.get("/oidc/callback")
@no_csrf  # GET callback from Keycloak; CSRF not applicable
async def oidc_callback(code: str, state: str) -> JSONResponse:
    """
    Handle OIDC authorization code callback.

    Flow:
      1. Exchange code for ID token claims (validates state + signature).
      2. Look up operator by OIDC sub.
      3. Create session and set cookie.

    Failure paths:
      - state_mismatch   → 401
      - signature error  → 401
      - unknown sub      → 403 no_local_operator

    Source: Req 2 AC6; ADR-0009.
    """
    try:
        claims = await oidc_token_exchange(code, state)
    except ValueError as exc:
        if "state_mismatch" in str(exc):
            return JSONResponse(
                status_code=401,
                content={"code": "mintkey:auth_failed", "reason": "state_mismatch"},
            )
        return JSONResponse(
            status_code=401,
            content={"code": "mintkey:auth_failed", "reason": "id_token_invalid"},
        )
    except Exception:
        return JSONResponse(
            status_code=401,
            content={"code": "mintkey:auth_failed", "reason": "id_token_invalid"},
        )

    sub = claims.get("sub")
    operator = await lookup_operator_by_oidc_sub(sub)

    if operator is None:
        return JSONResponse(
            status_code=403,
            content={"mintkey:code": "no_local_operator"},
        )

    session_token = await create_session(operator.id, operator.tenant_id)
    resp = JSONResponse({"status": "ok", "operator_id": str(operator.id)})
    resp.set_cookie(
        key="mintkey_session",
        value=session_token,
        httponly=True,
        secure=True,
        samesite="strict",
        max_age=86400,
    )
    return resp
