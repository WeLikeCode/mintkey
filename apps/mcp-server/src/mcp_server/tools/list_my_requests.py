"""
MCP list_my_requests tool.

GET /v1/tools/list_my_requests

Lists the calling agent's own access requests (access, integration, and share),
filtered to its tenant. Supports optional filtering by status and kind, with
ULID cursor pagination matching the other list tools.

Input  : {status?, kind?, after?, limit?}  (no tenant_id)
Output : {requests: [{request_id, kind, status, created_at, expires_at}], next_cursor}

Only the calling agent's rows are returned (requesting_agent_id = caller),
scoped to the agent's tenant via RLS (Req 1.7). The tenant is resolved from the
Agent API Key context (ADR-0009); no tenant argument is accepted (Req 13.2).
The pending-but-elapsed lazy-expiry guard is applied on read (Req 9.2).

Mirrors the admin-api service-layer list logic in-process — the MCP container
cannot import the admin-api package (see tools/_access_requests_common.py).

Source: T-7.1; tools.yaml list_my_requests; Req 1.7, 8.4, 13.2; ADR-0009,
        ADR-0008 (RLS), ADR-0017.11.
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
from mcp_server.tools import _access_requests_common as arc
from mcp_server.tools.discovery import get_agent_context
from mcp_server.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid

router = APIRouter(prefix="/v1/tools")


@router.get("/list_my_requests")
async def list_my_requests(
    request: Request,
    status: Optional[str] = Query(default=None),
    kind: Optional[str] = Query(default=None),
    after: Optional[str] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict[str, str]] = Depends(get_agent_context),
) -> JSONResponse:
    """Return the calling agent's own tenant-scoped access requests — Req 1.7."""
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    try:
        status_norm = arc.norm(status)
        if status_norm and status_norm not in arc.STATUS_ENUM:
            raise arc.AccessRequestToolError(
                "invalid_argument",
                f"status '{status_norm}' is not a member of the status enum",
                field="status",
            )
        kind_norm = arc.norm(kind)
        if kind_norm and kind_norm not in arc.KIND_ENUM:
            raise arc.AccessRequestToolError(
                "invalid_argument",
                f"kind '{kind_norm}' is not a member of the kind enum",
                field="kind",
            )

        # Decode the optional pagination cursor (exclusive). The cursor is a
        # request_ wire id from the previous page; a malformed value is a client
        # error. Ordering is created_at DESC, id DESC — so "after" a cursor
        # means rows whose id sorts strictly below it.
        after_uuid: Optional[str] = None
        if after:
            try:
                after_uuid = wire_to_db_uuid(after, "request")
                uuid.UUID(after_uuid)
            except (ValueError, AttributeError):
                raise arc.AccessRequestToolError(
                    "invalid_argument", "after cursor is malformed", field="after"
                )
    except arc.AccessRequestToolError as err:
        return arc.tool_error_response(err)

    await set_tenant_context(session, uuid.UUID(tenant_id))

    # Fetch limit+1 to determine whether a next page exists. Scope to the
    # calling agent (requesting_agent_id) AND tenant (redundant with RLS, but
    # explicit) so an agent only ever sees its own requests (Req 1.7).
    result = await session.execute(
        text(
            "SELECT id, kind, status, created_at, expires_at"
            "  FROM access_requests"
            " WHERE tenant_id = :tid AND requesting_agent_id = :aid"
            "   AND (CAST(:status AS text) IS NULL OR status = CAST(:status AS text))"
            "   AND (CAST(:kind AS text) IS NULL OR kind = CAST(:kind AS text))"
            "   AND (CAST(:after AS uuid) IS NULL OR id < CAST(:after AS uuid))"
            " ORDER BY created_at DESC, id DESC"
            " LIMIT :lim"
        ),
        {
            "tid": tenant_id,
            "aid": agent_id,
            "status": status_norm or None,
            "kind": kind_norm or None,
            "after": after_uuid,
            "lim": limit + 1,
        },
    )
    rows = list(result.mappings())

    has_more = len(rows) > limit
    page = rows[:limit]

    requests = [
        {
            "request_id": db_uuid_to_wire(row["id"], "request"),
            "kind": row["kind"],
            # Lazy-on-read guard (Req 9.2): a pending-but-elapsed row reads as
            # expired without persisting the flip (the sweep owns persistence).
            "status": arc.effective_status(row["status"], row["expires_at"]),
            "created_at": row["created_at"].isoformat(),
            "expires_at": row["expires_at"].isoformat(),
        }
        for row in page
    ]

    next_cursor = (
        db_uuid_to_wire(page[-1]["id"], "request") if has_more and page else None
    )

    return JSONResponse({"requests": requests, "next_cursor": next_cursor})
