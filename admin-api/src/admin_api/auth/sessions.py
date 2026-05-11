"""
Server-side session storage in the `sessions` table.

Source: design §4 auth/sessions.py; Req 2 AC2.
"""
from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID


async def create_session(operator_id: UUID, tenant_id: UUID) -> str:
    """
    Insert a row into the sessions table and return the session UUID as the token.
    The UUID is the opaque token stored in the mintkey_session cookie.
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
                    " (id, tenant_id, operator_id, expires_at, last_used_at, created_at)"
                    " VALUES (:id, :tid, :oid, :exp, now(), now())"
                ),
                {"id": session_id, "tid": tenant_id, "oid": operator_id, "exp": expires_at},
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
