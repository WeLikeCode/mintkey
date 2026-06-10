"""
MCP secret_list tool.

GET /v1/tools/secret_list[?after=sec_…&limit=N]

Returns metadata for all secrets the calling agent owns plus all secrets
shared with it. Never returns secret values.

Pagination: cursor-based (ordered by UUID PK — stable but not time-ordered,
since IDs are random UUIDv4 values).

Source: ADR-0025; tools.yaml secret_list schema; design.md D3.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.tools.discovery import get_agent_context
from mcp_server.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid

router = APIRouter(prefix="/v1/tools")


@router.get("/secret_list")
async def secret_list(
    request: Request,
    after: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    List metadata for owned + shared secrets.

    Parameters
    ----------
    after : str, optional
        Pagination cursor — sec_ wire ID from previous page (exclusive).
    limit : int
        Page size (1–200, default 50).
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    # Resolve pagination cursor
    after_uuid: str | None = None
    if after is not None:
        if not after.startswith("sec_"):
            return JSONResponse(
                status_code=422,
                content={
                    "code": "mintkey:invalid_argument",
                    "title": "after cursor must be a sec_ wire ID",
                },
            )
        try:
            after_uuid = wire_to_db_uuid(after, "sec")
            uuid.UUID(after_uuid)
        except (ValueError, AttributeError):
            return JSONResponse(
                status_code=422,
                content={
                    "code": "mintkey:invalid_argument",
                    "title": "after cursor is malformed",
                },
            )

    await set_tenant_context(session, tenant_id)

    # Fetch owned + shared in one union query, ordered by id (UUID PK order)
    if after_uuid is None:
        result = await session.execute(
            text(
                "SELECT s.id, s.name, s.version, s.size_bytes, s.content_type,"
                "       s.created_at, s.updated_at,"
                "       'owner' AS access"
                " FROM agent_secrets s"
                " WHERE s.agent_id = :lagent AND s.tenant_id = :ltid"
                " UNION ALL"
                " SELECT s.id, s.name, s.version, s.size_bytes, s.content_type,"
                "        s.created_at, s.updated_at,"
                "        'shared' AS access"
                " FROM agent_secrets s"
                " JOIN agent_secret_grants g ON g.secret_id = s.id"
                " WHERE g.recipient_agent_id = :lagent2 AND g.tenant_id = :ltid2"
                " ORDER BY id"
                " LIMIT :llimit"
            ),
            {
                "lagent": agent_id,
                "ltid": tenant_id,
                "lagent2": agent_id,
                "ltid2": tenant_id,
                "llimit": limit + 1,
            },
        )
    else:
        result = await session.execute(
            text(
                "SELECT s.id, s.name, s.version, s.size_bytes, s.content_type,"
                "       s.created_at, s.updated_at,"
                "       'owner' AS access"
                " FROM agent_secrets s"
                " WHERE s.agent_id = :lagent AND s.tenant_id = :ltid"
                "   AND s.id > :lafter"
                " UNION ALL"
                " SELECT s.id, s.name, s.version, s.size_bytes, s.content_type,"
                "        s.created_at, s.updated_at,"
                "        'shared' AS access"
                " FROM agent_secrets s"
                " JOIN agent_secret_grants g ON g.secret_id = s.id"
                " WHERE g.recipient_agent_id = :lagent2 AND g.tenant_id = :ltid2"
                "   AND s.id > :lafter2"
                " ORDER BY id"
                " LIMIT :llimit"
            ),
            {
                "lagent": agent_id,
                "ltid": tenant_id,
                "lagent2": agent_id,
                "ltid2": tenant_id,
                "lafter": after_uuid,
                "lafter2": after_uuid,
                "llimit": limit + 1,
            },
        )

    rows = result.fetchall()

    has_more = len(rows) > limit
    page_rows = rows[:limit]

    secrets = []
    for row in page_rows:
        row_id = str(row.id)
        wire = db_uuid_to_wire(row_id, "sec")
        item: dict = {
            "secret_id": wire,
            "name": row.name,
            "version": int(row.version),
            "size_bytes": int(row.size_bytes) if row.size_bytes is not None else 0,
            "content_type": row.content_type,
            "access": row.access,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        secrets.append(item)

    next_cursor: str | None = None
    if has_more and page_rows:
        last_id = str(page_rows[-1].id)
        next_cursor = db_uuid_to_wire(last_id, "sec")

    return JSONResponse(
        status_code=200,
        content={"secrets": secrets, "next_cursor": next_cursor},
    )
