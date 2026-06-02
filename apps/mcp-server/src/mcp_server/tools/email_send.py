"""
MCP email_send tool.

POST /v1/tools/email_send

Sends an email via the granted email service.

Implementation:
  1. Auth check.
  2. Permission check (email_permission_grants).
  3. Broker JWT exchange.
  4. POST /v1/email-proxy/messages with the JWT.

Source: feat/agent-email-e2e.
"""
from __future__ import annotations

import os
from typing import List, Optional

import httpx

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.tools.discovery import get_agent_context
from mcp_server.tools.email_list_mailboxes import _get_email_jwt
from mcp_server.utils.wire_ids import db_uuid_to_wire, resolve_email_service_id

router = APIRouter(prefix="/v1/tools")


class EmailSendRequest(BaseModel):
    email_service_id: str
    to: List[str]
    subject: str
    body: str                      # plain-text body
    cc: Optional[List[str]] = None
    bcc: Optional[List[str]] = None
    html_body: Optional[str] = None


@router.post("/email_send")
async def email_send(
    request: Request,
    body: EmailSendRequest,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Send an email via a granted email service.

    Parameters
    ----------
    email_service_id : str
        The email service ID — svc_ wire form or raw UUID.
    to : list[str]
        Recipient addresses.
    subject : str
        Email subject line.
    body : str
        Plain-text body.
    cc : list[str], optional
        CC addresses.
    bcc : list[str], optional
        BCC addresses.
    html_body : str, optional
        HTML body (used in addition to the plain-text body).
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    await set_tenant_context(session, tenant_id)

    esvc_uuid = await resolve_email_service_id(body.email_service_id, tenant_id, session)
    if esvc_uuid is None:
        return JSONResponse(
            status_code=404,
            content={
                "code": "mintkey:not_found",
                "reason_code": "email_service_not_found",
                "email_service_id_input": body.email_service_id,
            },
        )
    db_esvc_id = str(esvc_uuid)
    wire_esvc_id = db_uuid_to_wire(db_esvc_id, "svc")

    grant_result = await session.execute(
        text(
            "SELECT id FROM email_permission_grants"
            " WHERE agent_id = :aid AND email_service_id = :esid LIMIT 1"
        ),
        {"aid": agent_id, "esid": db_esvc_id},
    )
    if grant_result.fetchone() is None:
        return JSONResponse(
            status_code=403,
            content={
                "code": "mintkey:not_authorized",
                "reason_code": "permission_not_found",
                "email_service_id": wire_esvc_id,
                "hint": (
                    f"No email_permission_grant for this agent on '{wire_esvc_id}'. "
                    "Ask the operator to add one in the admin UI."
                ),
            },
        )

    jwt = await _get_email_jwt(agent_id, tenant_id, db_esvc_id)
    if jwt is None:
        return JSONResponse(
            status_code=502,
            content={"code": "mintkey:broker_error", "title": "Broker unavailable"},
        )

    # Build the payload for email-proxy POST /v1/email-proxy/messages.
    payload: dict = {
        "service_id": db_esvc_id,
        "to": body.to,
        "subject": body.subject,
        "body": body.body,
    }
    if body.cc:
        payload["cc"] = body.cc
    if body.bcc:
        payload["bcc"] = body.bcc
    if body.html_body:
        payload["html_body"] = body.html_body

    email_proxy_url = os.getenv("EMAIL_PROXY_INTERNAL_URL", "http://email-proxy:8088")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{email_proxy_url}/v1/email-proxy/messages",
            json=payload,
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=30.0,
        )

    if resp.status_code not in (200, 201, 202):
        return JSONResponse(
            status_code=resp.status_code,
            content={
                "code": "mintkey:email_proxy_error",
                "title": f"email-proxy returned {resp.status_code}",
                "detail": resp.text[:500],
            },
        )

    return JSONResponse(resp.json(), status_code=resp.status_code)
