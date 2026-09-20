"""
MCP request_share tool.

POST /v1/tools/request_share

Requests sharing access on an existing service with another agent (outbound —
the calling agent shares access it holds), or requests access to a service
owned by another agent (inbound). The direction is inferred from whether the
calling agent currently holds the (service, action) grant, and returned as
share_direction. Creates a share request (kind=share, status=pending) with a
default 30-day expiration. Emits access_request.created (actor=agent).

Input  : {service_id, action, target_agent_id}  (no tenant_id)
Output : {request_id, status, share_direction}

The tenant is resolved from the Agent API Key context (ADR-0009); no tenant
argument is accepted (Req 13.2). Mirrors the admin-api service-layer create
logic in-process — the MCP container cannot import the admin-api package (see
tools/_access_requests_common.py).

Source: T-7.1; tools.yaml request_share; Req 3.1-3.9, 13.2; ADR-0009,
        ADR-0008 (tenant GUC), ADR-0017.11, ADR-0014.7.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.tools import _access_requests_common as arc
from mcp_server.tools.discovery import get_agent_context
from mcp_server.utils.wire_ids import db_uuid_to_wire

router = APIRouter(prefix="/v1/tools")


class RequestShareInput(BaseModel):
    service_id: str
    action: str
    target_agent_id: str


@router.post("/request_share")
async def request_share(
    request: Request,
    body: RequestShareInput,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict[str, str]] = Depends(get_agent_context),
) -> JSONResponse:
    """Create a ``share`` request for the calling agent — Req 3.1-3.9."""
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
        target_agent_uuid = arc.decode_wire_id(
            body.target_agent_id, "agent", field="target_agent_id"
        )
        requesting_agent_uuid = uuid.UUID(agent_id)

        # Req 3.4 — no self-target.
        if target_agent_uuid == requesting_agent_uuid:
            raise arc.AccessRequestToolError(
                "invalid_argument",
                "target_agent_id must differ from the requesting agent",
                field="target_agent_id",
            )

        await set_tenant_context(session, uuid.UUID(tenant_id))

        # Req 3.5 — service must exist in the requester's tenant.
        if not await arc.service_exists(session, tenant_id, service_uuid):
            raise arc.AccessRequestToolError("service_not_found", "service not found")

        # Req 3.6 — target agent must exist in the requester's tenant.
        if not await arc.agent_exists(session, tenant_id, target_agent_uuid):
            raise arc.AccessRequestToolError(
                "agent_not_found", "target agent not found"
            )

        # Direction: outbound when the requester already holds the grant it is
        # sharing; inbound when it is asking for access held by another agent.
        requester_holds = await arc.grant_exists(
            session, tenant_id, requesting_agent_uuid, service_uuid, action
        )
        share_direction = "outbound" if requester_holds else "inbound"

        # Req 3.7 — outbound requires the requester to actually hold the grant.
        if share_direction == "outbound" and not requester_holds:
            raise arc.AccessRequestToolError(
                "action_not_granted",
                "requesting agent does not hold the (service, action) grant it "
                "is attempting to share",
            )

        # Req 3.8 — the target must not already hold the grant.
        if await arc.grant_exists(
            session, tenant_id, target_agent_uuid, service_uuid, action
        ):
            raise arc.AccessRequestToolError(
                "already_granted",
                "target agent already holds this (service, action) grant",
            )

        request_id, request_uuid = arc.new_request_id()
        now = datetime.now(timezone.utc)
        expires_at = arc.compute_expires_at(now)

        await arc.insert_request(
            session,
            tenant_id=tenant_id,
            request_uuid=request_uuid,
            kind="share",
            requesting_agent_uuid=requesting_agent_uuid,
            service_uuid=service_uuid,
            action=action,
            target_agent_uuid=target_agent_uuid,
            share_direction=share_direction,
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
            kind="share",
            expires_at=expires_at,
            payload_target={
                "service_id": db_uuid_to_wire(service_uuid, "svc"),
                "action": action,
                "target_agent_id": db_uuid_to_wire(target_agent_uuid, "agent"),
                "share_direction": share_direction,
            },
        )
    except arc.AccessRequestToolError as err:
        return arc.tool_error_response(err)

    await session.commit()
    return JSONResponse(
        {
            "request_id": request_id,
            "status": "pending",
            "share_direction": share_direction,
        }
    )
