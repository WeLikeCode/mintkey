"""
MCP email_list_emails tool.

GET /v1/tools/email_list_emails?email_service_id=<id>&mailbox=INBOX&limit=50&offset=0
  (alias accepted: ?service_id=<id>)

Paginated UID listing for a given IMAP mailbox.

Implementation:
  1. Auth check (agent context present).
  2. Permission check (email_permission_grants).
  3. Broker JWT exchange (scope: read:email).
  4. GET /v1/email-proxy/messages?service_id=<id>&mailbox=<mb>&limit=<n>&offset=<o>.
  5. Return paginated message list.

Source: feat/email-tools-list-attach-move-mark-delete.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.tools.discovery import get_agent_context
from mcp_server.tools.email_list_mailboxes import _get_email_jwt
from mcp_server.utils.wire_ids import db_uuid_to_wire, resolve_email_service_id

router = APIRouter(prefix="/v1/tools")


@router.get("/email_list_emails")
async def email_list_emails(
    request: Request,
    email_service_id: Optional[str] = None,
    service_id: Optional[str] = None,
    mailbox: str = "INBOX",
    limit: int = 50,
    offset: int = 0,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    List emails in an IMAP mailbox with pagination.

    Parameters
    ----------
    email_service_id : str
        The email service ID — svc_ wire form or raw UUID.
        Alias: ``service_id`` (matches the broker token-hint vocabulary).
    mailbox : str
        The mailbox to list (default: INBOX).
    limit : int
        Number of messages to return per page (1-200, default 50).
    offset : int
        Pagination offset (0-based).
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    # Accept ?service_id= as alias for ?email_service_id=
    email_service_id = email_service_id or service_id
    if not email_service_id:
        return JSONResponse(
            status_code=422,
            content={
                "code": "mintkey:bad_request",
                "title": "Missing required query parameter: email_service_id (or service_id)",
            },
        )

    # Validate pagination params.
    if limit < 1 or limit > 200:
        return JSONResponse(
            status_code=422,
            content={"code": "mintkey:bad_request", "title": "limit must be between 1 and 200"},
        )
    if offset < 0:
        return JSONResponse(
            status_code=422,
            content={"code": "mintkey:bad_request", "title": "offset must be >= 0"},
        )

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    await set_tenant_context(session, tenant_id)

    # Resolve email_service_id.
    esvc_uuid = await resolve_email_service_id(email_service_id, tenant_id, session)
    if esvc_uuid is None:
        return JSONResponse(
            status_code=404,
            content={
                "code": "mintkey:not_found",
                "reason_code": "email_service_not_found",
                "email_service_id_input": email_service_id,
            },
        )
    db_esvc_id = str(esvc_uuid)
    wire_esvc_id = db_uuid_to_wire(db_esvc_id, "svc")

    # Check email_permission_grants.
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

    # Obtain brokered JWT (scope: read:email).
    jwt = await _get_email_jwt(agent_id, tenant_id, db_esvc_id)
    if jwt is None:
        return JSONResponse(
            status_code=502,
            content={"code": "mintkey:broker_error", "title": "Broker unavailable"},
        )

    # Call email-proxy — GET /v1/email-proxy/messages with pagination params.
    email_proxy_url = os.getenv("EMAIL_PROXY_INTERNAL_URL", "http://email-proxy:8088")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{email_proxy_url}/v1/email-proxy/messages",
            params={
                "service_id": db_esvc_id,
                "mailbox": mailbox,
                "limit": limit,
                "offset": offset,
            },
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=30.0,
        )

    if resp.status_code != 200:
        return JSONResponse(
            status_code=resp.status_code,
            content={
                "code": "mintkey:email_proxy_error",
                "title": f"email-proxy returned {resp.status_code}",
                "detail": resp.text[:500],
            },
        )

    return JSONResponse(resp.json())
