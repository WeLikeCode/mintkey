"""
Auth endpoints.

POST /v1/auth/internal-login  — Argon2id login (Req 2 AC2/AC3/AC4/ADR-0017.5)
                                 Returns 404 when operator.internal_password_hash IS NULL (D2-b)
POST /v1/auth/logout
GET  /v1/auth/whoami
GET  /v1/auth/oidc/login      — OIDC PKCE redirect (Req 2 AC6)  → 302 to Keycloak
GET  /v1/auth/oidc/callback   — OIDC code exchange + session creation → 302 to admin-ui

Source: design §4 api/auth.py; Req 2; ADR-0017.5; ADR-0009; ADR-0019 §3.
"""
from __future__ import annotations

import logging
import secrets
import time
from typing import Any

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse, RedirectResponse
from pydantic import BaseModel

from admin_api.auth.internal import INVALID_CREDENTIALS_RESPONSE, verify_internal_login
from admin_api.auth.oidc import (
    generate_authorization_url,
    lookup_operator_by_oidc_sub,
    oidc_token_exchange,
)
from admin_api.auth.oidc_state import OidcStateRepository
from admin_api.auth.sessions import create_session, validate_session
from admin_api.middleware.csrf import no_csrf

_logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/auth")


class LoginRequest(BaseModel):
    email: str
    password: str


# ---------------------------------------------------------------------------
# /v1/auth/internal-login — D2-b: hash-IS-NULL → 404
# ---------------------------------------------------------------------------


@router.post("/internal-login")
@no_csrf  # login is the bootstrap surface; CSRF not yet applicable
async def internal_login(body: LoginRequest, response: Response) -> JSONResponse:
    """
    Argon2id login with identical body + equalized timing.
    All failure paths return the same body (ADR-0017.5 / Req SEC-9).

    D2-b: if operator.internal_password_hash IS NULL, return 404 — the internal
    login gate is disabled. Timing is equalized via an extra DUMMY_HASH verify.

    Source: Req 2 AC2, AC3, AC4; design §4.
    """
    from admin_api.auth.internal import DUMMY_HASH, fetch_operator
    import argon2

    _ph = argon2.PasswordHasher()

    operator = await fetch_operator(body.email)

    # D2-b gate: hash NULL → 404. Equalize timing via DUMMY_HASH verify.
    if operator is not None and operator.internal_password_hash is None:
        try:
            _ph.verify(DUMMY_HASH, body.password)
        except Exception:
            pass
        # 404 hides that the route exists in disabled state (D2-b spec)
        return JSONResponse(status_code=404, content={"mintkey:code": "not_found"})

    operator_out, failure_reason = await verify_internal_login(body.email, body.password)

    if failure_reason is not None or operator_out is None:
        # All failures return byte-identical body (ADR-0017.5).
        return JSONResponse(status_code=401, content=INVALID_CREDENTIALS_RESPONSE)

    session_token = await create_session(
        operator_out.id, operator_out.tenant_id, auth_method="internal"
    )
    csrf_token = secrets.token_urlsafe(32)

    resp = JSONResponse({
        "status": "ok",
        "operator_id": str(operator_out.id),
        "tenant_id": str(operator_out.tenant_id),
        "is_platform_admin": bool(operator_out.is_platform_admin),
    })
    resp.set_cookie(
        key="mintkey_session",
        value=session_token,
        httponly=True,
        secure=False,  # False for local dev; True in production
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


# ---------------------------------------------------------------------------
# /v1/auth/logout
# ---------------------------------------------------------------------------


@router.post("/logout")
async def logout(response: Response) -> Response:
    response.delete_cookie("mintkey_session")
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# /v1/auth/whoami — ADR-0019 §3; 15 s in-process LRU cache
# ---------------------------------------------------------------------------

# (session_token → (result_dict, fetched_at)) simple TTL cache
_WHOAMI_CACHE: dict[str, tuple[dict[str, Any], float]] = {}
_WHOAMI_TTL = 15.0


async def _whoami_lookup(session_token: str) -> dict[str, Any] | None:
    """Validate session, look up operator, return dict or None."""
    now = time.monotonic()
    cached = _WHOAMI_CACHE.get(session_token)
    if cached is not None and (now - cached[1]) < _WHOAMI_TTL:
        return cached[0]

    ctx = await validate_session(session_token)
    if ctx is None:
        return None

    from admin_api.db.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                text(
                    "SELECT set_config('app.current_tenant',"
                    " '00000000-0000-0000-0000-000000000000', true),"
                    " set_config('app.platform_admin_view', 'on', true)"
                )
            )
            result = await db.execute(
                text(
                    "SELECT o.id, o.tenant_id, o.email, o.is_platform_admin,"
                    " s.auth_method"
                    " FROM operators o"
                    " JOIN sessions s ON s.id = CAST(:token AS uuid)"
                    " WHERE o.id = CAST(:oid AS uuid)"
                    " AND s.expires_at > now()"
                ),
                {"oid": str(ctx.operator_id), "token": session_token},
            )
            row = result.fetchone()

    if row is None:
        return None

    # Normalise auth_method for the UI: DB stores "oidc" (protocol name),
    # but the frontend badge differentiates only "internal" (break-glass)
    # vs anything else (Keycloak / OIDC). Map "oidc" → "keycloak" so the
    # AdminSession type contract is satisfied; NULL legacy rows stay NULL.
    raw_auth_method = row[4]
    auth_method = (
        "keycloak" if raw_auth_method == "oidc"
        else raw_auth_method  # "internal" or None
    )

    data = {
        "operator_id": str(row[0]),
        "tenant_id": str(row[1]),
        "email": row[2],
        "is_platform_admin": bool(row[3]),
        "auth_method": auth_method,
    }
    _WHOAMI_CACHE[session_token] = (data, now)
    # Prune cache: evict entries older than TTL to avoid unbounded growth
    stale = [k for k, v in _WHOAMI_CACHE.items() if (now - v[1]) >= _WHOAMI_TTL]
    for k in stale:
        _WHOAMI_CACHE.pop(k, None)

    return data


@router.get("/whoami")
async def whoami(request: Request) -> JSONResponse:
    """Returns the current operator's identity.

    Reads mintkey_session cookie → validate_session → operator row.
    15-second in-process LRU cache (ADR-0019 §3) to avoid hammering postgres.

    Returns 401 if no session.
    Source: ADR-0019 §3; Req 2 AC6.
    """
    session_token = request.cookies.get("mintkey_session")
    if not session_token:
        return JSONResponse(
            status_code=401,
            content={"mintkey:code": "unauthenticated", "title": "No session"},
        )

    data = await _whoami_lookup(session_token)
    if data is None:
        return JSONResponse(
            status_code=401,
            content={"mintkey:code": "unauthenticated", "title": "Session not found or expired"},
        )

    return JSONResponse({"operator": data})


# ---------------------------------------------------------------------------
# /v1/auth/oidc/login — 302 redirect to Keycloak
# ---------------------------------------------------------------------------


@router.get("/oidc/login")
async def oidc_login() -> RedirectResponse:
    """
    302 redirect to Keycloak authorization URL (PKCE S256).

    Uses MINTKEY_KEYCLOAK_PUBLIC_URL for browser-facing redirect.
    Source: Req 2 AC6.
    """
    from admin_api.db.session import AsyncSessionLocal

    async with AsyncSessionLocal() as db:
        async with db.begin():
            state_repo = OidcStateRepository(db)
            auth_url, _state, _ = await generate_authorization_url(state_repo)
    return RedirectResponse(url=auth_url, status_code=302)


# ---------------------------------------------------------------------------
# /v1/auth/oidc/callback — code exchange, session, cookies, audit
# ---------------------------------------------------------------------------


@router.get("/oidc/callback")
@no_csrf  # GET callback from Keycloak; CSRF not applicable
async def oidc_callback(code: str, state: str, request: Request) -> Response:
    """
    Handle OIDC authorization code callback.

    Flow:
      1. Exchange code for ID token claims (validates state + signature per ADR-0016.2).
      2. Look up operator by OIDC sub; email fallback link for first login.
      3. Create session and set mintkey_session + csrf_token cookies.
      4. Emit operator.session.created audit event.
      5. 302 redirect to <MINTKEY_ADMIN_UI_PUBLIC_URL>/admin.

    Failure paths:
      - state_mismatch   → 401
      - signature error  → 401
      - unknown sub      → 403 no_local_operator

    Source: Req 2 AC6; ADR-0009; ADR-0016.2.
    """
    # Grab IP early for audit
    ip = request.headers.get("X-Forwarded-For") or (
        request.client.host if request.client else "unknown"
    )

    try:
        from admin_api.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as db:
            async with db.begin():
                state_repo = OidcStateRepository(db)
                claims = await oidc_token_exchange(code, state, state_repo)
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
    except Exception as exc:
        _logger.warning("oidc.callback_token_exchange_error error=%s", exc)
        return JSONResponse(
            status_code=401,
            content={"code": "mintkey:auth_failed", "reason": "id_token_invalid"},
        )

    sub = claims.get("sub")
    email = claims.get("email")
    if not isinstance(sub, str):
        return JSONResponse(
            status_code=401,
            content={"code": "mintkey:auth_failed", "reason": "id_token_invalid"},
        )
    operator = await lookup_operator_by_oidc_sub(sub, email=email)

    if operator is None:
        return JSONResponse(
            status_code=403,
            content={"mintkey:code": "no_local_operator"},
        )

    session_token = await create_session(
        operator.id, operator.tenant_id, auth_method="oidc"
    )
    csrf_token = secrets.token_urlsafe(32)

    # Emit audit event: operator.session.created
    try:
        await _emit_session_created_audit(
            operator_id=operator.id,
            tenant_id=operator.tenant_id,
            keycloak_sub=sub,
            ip=ip,
        )
    except Exception as exc:
        _logger.error("oidc.audit_emit_failed error=%s", exc)
        # Never block login on audit failure

    # Determine redirect target
    from admin_api.config.public_urls import resolve_admin_ui_public_url
    admin_ui = resolve_admin_ui_public_url()
    redirect_url = f"{admin_ui}/admin"

    # Detect scheme for Secure flag
    scheme = request.headers.get("X-Forwarded-Proto", request.url.scheme)
    secure_cookie = scheme == "https"

    resp = RedirectResponse(url=redirect_url, status_code=302)
    resp.set_cookie(
        key="mintkey_session",
        value=session_token,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        max_age=86400,
    )
    resp.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,
        secure=secure_cookie,
        samesite="lax",
        max_age=86400,
    )
    return resp


async def _emit_session_created_audit(
    operator_id: Any,
    tenant_id: Any,
    keycloak_sub: str | None,
    ip: str,
) -> None:
    """Emit operator.session.created audit event (ADR-0014.7)."""
    import uuid as _uuid
    from admin_api.db.session import AsyncSessionLocal
    from mintkey_models.audit import audit_emit
    from mintkey_models.tenant_ctx import set_tenant_context

    tid = _uuid.UUID(str(tenant_id))
    oid = _uuid.UUID(str(operator_id))

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await set_tenant_context(db, tid)
            await audit_emit(
                session=db,
                tenant_id=tid,
                event_type="operator.session.created",
                actor_id=oid,
                actor_type="operator",
                target_id=oid,
                target_type="operator",
                payload={
                    "auth_method": "oidc",
                    "keycloak_sub": keycloak_sub,
                    "ip": ip,
                },
            )
