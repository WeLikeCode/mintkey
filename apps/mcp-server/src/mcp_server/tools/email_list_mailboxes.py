"""
MCP email_list_mailboxes tool.

GET /v1/tools/email_list_mailboxes?email_service_id=<id>
  (alias accepted: ?service_id=<id> — matches the broker token-hint vocabulary)

Lists IMAP mailboxes for the agent's granted email service.

Implementation:
  1. Auth check (agent context present).
  2. request_token exchange via broker (service_kind=email).
  3. GET /v1/email-proxy/mailboxes?service_id=<id> on email-proxy.
  4. Return the mailbox list.

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
from mcp_server.utils.wire_ids import db_uuid_to_wire, resolve_email_service_id

router = APIRouter(prefix="/v1/tools")


@router.get("/email_list_mailboxes")
async def email_list_mailboxes(
    request: Request,
    email_service_id: Optional[str] = None,
    service_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    List IMAP mailboxes for a granted email service.

    Parameters
    ----------
    email_service_id : str
        The email service ID — accepts svc_ wire form or raw UUID.
        Alias: ``service_id`` (matches the broker token-hint vocabulary).
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    # Accept ?service_id= as alias for ?email_service_id= so agents following the
    # broker's token hint verbatim don't 422 here.
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

    # Obtain brokered JWT.
    jwt = await _get_email_jwt(agent_id, tenant_id, db_esvc_id)
    if jwt is None:
        return JSONResponse(
            status_code=502,
            content={"code": "mintkey:broker_error", "title": "Broker unavailable"},
        )

    # Call email-proxy.
    email_proxy_url = os.getenv("EMAIL_PROXY_INTERNAL_URL", "http://email-proxy:8088")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{email_proxy_url}/v1/email-proxy/mailboxes",
            params={"service_id": db_esvc_id},
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15.0,
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


async def _get_email_jwt(agent_id: str, tenant_id: str, db_esvc_id: str) -> Optional[str]:
    """Call broker /v1/issue and return the JWT string, or None on failure."""
    broker_url = os.getenv("BROKER_BASE_URL", "http://broker:8083")
    mcp_token = os.getenv("MINTKEY_MCP_SERVICE_TOKEN", "")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{broker_url}/v1/issue",
            json={
                "agent_id": agent_id,
                "service_id": db_esvc_id,
                "tenant_id": tenant_id,
                "scope": "read:email send:email",
                "service_kind": "email",
                "ttl_seconds": 600,
            },
            headers={"X-Mintkey-Service-Token": mcp_token},
            timeout=5.0,
        )
    if resp.status_code != 200:
        return None
    return resp.json().get("token")
