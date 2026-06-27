"""
Server-side session storage in the `sessions` table.

Source: design §4 auth/sessions.py; Req 2 AC2.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException, Request


async def create_session(
    operator_id: UUID, tenant_id: UUID, auth_method: str = "oidc"
) -> str:
    """
    Insert a row into the sessions table and return the session UUID as the token.
    The UUID is the opaque token stored in the mintkey_session cookie.

    auth_method: "oidc" (default, Keycloak login) or "internal" (break-glass login).
    """
    from admin_api.db.session import AsyncSessionLocal
    from mintkey_models.tenant_ctx import set_tenant_context
    from sqlalchemy import text

    session_id = _uuid.uuid4()
    expires_at = datetime.now(timezone.utc) + timedelta(hours=8)

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await set_tenant_context(db, tenant_id)
            # Pass UUID objects directly — asyncpg resolves the type from the column.
            await db.execute(
                text(
                    "INSERT INTO sessions"
                    " (id, tenant_id, operator_id, expires_at, last_used_at, created_at, auth_method)"
                    " VALUES (:id, :tid, :oid, :exp, now(), now(), :auth_method)"
                ),
                {
                    "id": session_id,
                    "tid": tenant_id,
                    "oid": operator_id,
                    "exp": expires_at,
                    "auth_method": auth_method,
                },
            )
    return str(session_id)


async def validate_session(token: str) -> Any | None:
    """
    Look up a non-expired session by its UUID token.
    Returns a namespace with operator_id and tenant_id, or None.
    """
    from admin_api.db.session import AsyncSessionLocal
    from sqlalchemy import text

    try:
        _uuid.UUID(token)
    except ValueError:
        return None

    async with AsyncSessionLocal() as db:
        async with db.begin():
            # RLS requires a valid UUID for current_tenant even when unused.
            await db.execute(
                text("SELECT set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', true)")
            )
            await db.execute(
                text("SELECT set_config('app.platform_admin_view', 'on', true)")
            )
            row = await db.execute(
                text(
                    "SELECT operator_id, tenant_id FROM sessions"
                    " WHERE id = CAST(:token AS uuid) AND expires_at > now()"
                ),
                {"token": token},
            )
            result = row.one_or_none()
    if result is None:
        return None

    class _Ctx:
        def __init__(self, operator_id: Any, tenant_id: Any) -> None:
            self.operator_id = operator_id
            self.tenant_id = tenant_id

    return _Ctx(result.operator_id, result.tenant_id)


async def _is_operator_platform_admin(operator_id: Any) -> bool:
    """Look up the is_platform_admin flag for the given operator_id."""
    from admin_api.db.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                text(
                    "SELECT set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', true),"
                    " set_config('app.platform_admin_view', 'on', true)"
                )
            )
            row = await db.execute(
                text(
                    "SELECT is_platform_admin FROM operators"
                    " WHERE id = CAST(:oid AS uuid)"
                ),
                {"oid": str(operator_id)},
            )
            result = row.one_or_none()
    return bool(result.is_platform_admin) if result is not None else False


async def require_platform_admin_session(request: Request) -> None:
    """
    FastAPI dependency: enforce that the caller is an authenticated platform-admin.

    Reads the `mintkey_session` cookie → validate_session() → checks
    _is_operator_platform_admin(ctx.operator_id).

    Raises:
        HTTPException(401)  — no/invalid session cookie.
        HTTPException(403)  — operator is not platform-admin.

    Source: ADR-0027 §D2; SCOPE-A chunk D.
    """
    session_token = request.cookies.get("mintkey_session")
    if not session_token:
        raise HTTPException(
            status_code=401,
            detail={"mintkey:code": "unauthenticated", "title": "No session"},
        )

    ctx = await validate_session(session_token)
    if ctx is None:
        raise HTTPException(
            status_code=401,
            detail={"mintkey:code": "unauthenticated", "title": "Session not found or expired"},
        )

    if not await _is_operator_platform_admin(ctx.operator_id):
        raise HTTPException(
            status_code=403,
            detail={
                "mintkey:code": "permission_denied",
                "title": "Platform admin access required",
            },
        )


async def require_tenant_session(request: Request, tenant_id: UUID) -> None:
    """
    FastAPI dependency: enforce that the caller's session is scoped to `tenant_id`.

    Reads the `mintkey_session` cookie → validate_session() → checks that
    session.tenant_id == tenant_id (path param). Platform admins bypass.

    Raises:
        HTTPException(401)  — no/invalid session cookie.
        HTTPException(403)  — session belongs to a different tenant.

    Source: SCOPE-A cross-tenant authz fix; ADR-SCOPE-A.
    """
    session_token = request.cookies.get("mintkey_session")
    if not session_token:
        raise HTTPException(
            status_code=401,
            detail={"mintkey:code": "unauthenticated", "title": "No session"},
        )

    ctx = await validate_session(session_token)
    if ctx is None:
        raise HTTPException(
            status_code=401,
            detail={"mintkey:code": "unauthenticated", "title": "Session not found or expired"},
        )

    # Platform admins may operate across any tenant.
    if await _is_operator_platform_admin(ctx.operator_id):
        return

    if UUID(str(ctx.tenant_id)) != tenant_id:
        raise HTTPException(
            status_code=403,
            detail={
                "mintkey:code": "permission_denied",
                "title": "Session tenant does not match the requested tenant",
            },
        )
