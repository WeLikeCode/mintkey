"""
MCP request_access tool.

POST /v1/tools/request_access

Requests a permission grant on a service that already exists in the calling
agent's tenant. Creates an access request (kind=access, status=pending) with a
default 30-day expiration for an operator to approve or reject. Does not itself
grant access. Emits access_request.created (actor=agent).

Input  : {service_id, action}  (no tenant_id — resolved from Agent API Key ctx)
Output : {request_id, status}

The agent_id/tenant_id come from the Bearer Agent API Key context (ADR-0009);
no tenant argument is accepted (Req 13.2). The tool mirrors the admin-api
service-layer create logic in-process — the MCP container cannot import the
admin-api package (see tools/_access_requests_common.py).

Source: T-7.1; tools.yaml request_access; Req 1.1-1.6, 13.2; ADR-0009,
        ADR-0008 (tenant GUC), ADR-0017.11, ADR-0014.7.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.tools import _access_requests_common as arc
from mcp_server.tools.discovery import get_agent_context
from mcp_server.utils.wire_ids import db_uuid_to_wire

router = APIRouter(prefix="/v1/tools")


class RequestAccessInput(BaseModel):
    service_id: str
    action: str


async def _pending_duplicate_exists(
    session: AsyncSession,
    tenant_id: str,
    requesting_agent_uuid: uuid.UUID,
    service_uuid: uuid.UUID,
    action: str,
) -> bool:
    """True if an identical pending access request already exists (Req 1.6)."""
    result = await session.execute(
        text(
            "SELECT 1 FROM access_requests"
            " WHERE kind = 'access' AND status = 'pending'"
            "   AND requesting_agent_id = :aid AND service_id = :sid"
            "   AND action = :action AND tenant_id = :tid"
        ),
        {
            "aid": str(requesting_agent_uuid),
            "sid": str(service_uuid),
            "action": action,
            "tid": tenant_id,
        },
    )
    return result.fetchone() is not None


@router.post("/request_access")
async def request_access(
    request: Request,
    body: RequestAccessInput,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict[str, str]] = Depends(get_agent_context),
) -> JSONResponse:
    """Create an ``access`` request for the calling agent — Req 1.1-1.6."""
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    try:
        service_uuid = arc.decode_wire_id(body.service_id, "svc", field="service_id")
        action = arc.norm(body.action)
        if not action:
            raise arc.AccessRequestToolError(
                "invalid_argument", "action is required", field="action"
            )
        requesting_agent_uuid = uuid.UUID(agent_id)

        await set_tenant_context(session, uuid.UUID(tenant_id))

        if not await arc.service_exists(session, tenant_id, service_uuid):
            raise arc.AccessRequestToolError("service_not_found", "service not found")

        if await arc.grant_exists(
            session, tenant_id, requesting_agent_uuid, service_uuid, action
        ):
            raise arc.AccessRequestToolError(
                "already_granted",
                "the agent already holds this (service, action) grant",
            )

        if await _pending_duplicate_exists(
            session, tenant_id, requesting_agent_uuid, service_uuid, action
        ):
            raise arc.AccessRequestToolError(
                "request_already_pending",
                "an identical pending access request already exists",
            )

        request_id, request_uuid = arc.new_request_id()
        now = datetime.now(timezone.utc)
        expires_at = arc.compute_expires_at(now)

        await arc.insert_request(
            session,
            tenant_id=tenant_id,
            request_uuid=request_uuid,
            kind="access",
            requesting_agent_uuid=requesting_agent_uuid,
            service_uuid=service_uuid,
            action=action,
            target_agent_uuid=None,
            share_direction=None,
            proposed_config=None,
            created_at=now,
            expires_at=expires_at,
        )
        await arc.emit_created_audit(
            session,
            tenant_id=tenant_id,
            request_uuid=request_uuid,
            requesting_agent_uuid=requesting_agent_uuid,
            request_id=request_id,
            kind="access",
            expires_at=expires_at,
            payload_target={
                "service_id": db_uuid_to_wire(service_uuid, "svc"),
                "action": action,
            },
        )
    except arc.AccessRequestToolError as err:
        return arc.tool_error_response(err)

    await session.commit()
    return JSONResponse({"request_id": request_id, "status": "pending"})
