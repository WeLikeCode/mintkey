"""
MCP email_search_messages tool.

GET /v1/tools/email_search_messages?email_service_id=<id>&mailbox=INBOX&query=<q>

Searches messages in an IMAP mailbox.

Implementation:
  1. Auth check.
  2. Permission check (email_permission_grants).
  3. Broker JWT exchange.
  4. GET /v1/email-proxy/messages/search?service_id=<id>&mailbox=<mb>&query=<q>.

Source: feat/agent-email-e2e.
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


@router.get("/email_search_messages")
async def email_search_messages(
    request: Request,
    query: str,
    email_service_id: Optional[str] = None,
    service_id: Optional[str] = None,
    mailbox: str = "INBOX",
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Search messages in an IMAP mailbox.

    Parameters
    ----------
    email_service_id : str
        The email service ID — svc_ wire form or raw UUID.
        Alias: ``service_id`` (matches the broker token-hint vocabulary).
    query : str
        RFC 3501 IMAP SEARCH query string (e.g. "FROM user@example.com UNSEEN").
    mailbox : str
        The mailbox to search (default: INBOX).
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    email_service_id = email_service_id or service_id
    if not email_service_id:
        return JSONResponse(
            status_code=422,
            content={
                "code": "mintkey:bad_request",
                "title": "Missing required query parameter: email_service_id (or service_id)",
            },
        )

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    await set_tenant_context(session, tenant_id)

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
            },
        )

    jwt = await _get_email_jwt(agent_id, tenant_id, db_esvc_id)
    if jwt is None:
        return JSONResponse(
            status_code=502,
            content={"code": "mintkey:broker_error", "title": "Broker unavailable"},
        )

    email_proxy_url = os.getenv("EMAIL_PROXY_INTERNAL_URL", "http://email-proxy:8088")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{email_proxy_url}/v1/email-proxy/messages/search",
            params={"service_id": db_esvc_id, "mailbox": mailbox, "query": query},
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
