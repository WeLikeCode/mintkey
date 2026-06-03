"""
MCP email_download_attachment tool.

GET /v1/tools/email_download_attachment?email_service_id=<id>&message_id=<uid>&part_id=<pid>&mailbox=INBOX
  (alias accepted: ?service_id=<id>)

Downloads a specific MIME attachment part from an IMAP message.
Response shape: {filename, content_type, size, content_base64}.

Implementation:
  1. Auth check (agent context present).
  2. Permission check (email_permission_grants).
  3. Broker JWT exchange (scope: read:email).
  4. GET /v1/email-proxy/messages/{uid}/attachments/{part_id}?service_id=<id>&mailbox=<mb>.
  5. Return the attachment metadata + base64 content.

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


@router.get("/email_download_attachment")
async def email_download_attachment(
    request: Request,
    message_id: str,
    part_id: str,
    email_service_id: Optional[str] = None,
    service_id: Optional[str] = None,
    mailbox: str = "INBOX",
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Download a specific MIME part (attachment) from an IMAP message.

    Returns base64-encoded content in:
      {filename, content_type, size, content_base64}

    Parameters
    ----------
    email_service_id : str
        The email service ID — svc_ wire form or raw UUID.
        Alias: ``service_id`` (matches the broker token-hint vocabulary).
    message_id : str
        The IMAP UID of the message.
    part_id : str
        The MIME part identifier (e.g. "1", "2", "1.1").
    mailbox : str
        The mailbox containing the message (default: INBOX).
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

    # Call email-proxy — GET /v1/email-proxy/messages/{uid}/attachments/{part_id}.
    email_proxy_url = os.getenv("EMAIL_PROXY_INTERNAL_URL", "http://email-proxy:8088")
    async with httpx.AsyncClient() as client:
        resp = await client.get(
            f"{email_proxy_url}/v1/email-proxy/messages/{message_id}/attachments/{part_id}",
            params={"service_id": db_esvc_id, "mailbox": mailbox},
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=60.0,  # attachments may be large
        )

    if resp.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "code": "mintkey:not_found",
                "reason_code": "attachment_not_found",
                "message_id": message_id,
                "part_id": part_id,
            },
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

    # email-proxy returns raw bytes with Content-Type header set.
    # Re-wrap as JSON with base64 content per the contract.
    import base64

    content_type = resp.headers.get("content-type", "application/octet-stream")
    content_b64 = base64.b64encode(resp.content).decode("ascii")
    # Filename may be surfaced via Content-Disposition if the proxy sets it.
    content_disposition = resp.headers.get("content-disposition", "")
    filename = ""
    if "filename=" in content_disposition:
        filename = content_disposition.split("filename=")[-1].strip().strip('"')

    return JSONResponse({
        "filename": filename,
        "content_type": content_type,
        "size": len(resp.content),
        "content_base64": content_b64,
    })
