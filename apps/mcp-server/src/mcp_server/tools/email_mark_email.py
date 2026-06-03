"""
MCP email_mark_email tool.

POST /v1/tools/email_mark_email
  body: {email_service_id, message_id, mailbox, add:[], remove:[]}
  (alias accepted: service_id instead of email_service_id)

Updates IMAP flags on a message (IMAP STORE +FLAGS / -FLAGS).
Supported flags: \\Seen, \\Flagged, \\Answered.

Implementation:
  1. Auth check (agent context present).
  2. Permission check (email_permission_grants).
  3. Broker JWT exchange (scope: write:email).
  4. PATCH /v1/email-proxy/messages/{uid}/flags?service_id=<id>&mailbox=<mb>
     body: {seen, answered, starred} derived from add/remove lists.
  5. Return 200 with updated flags.

Source: feat/email-tools-list-attach-move-mark-delete.
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


class MarkEmailRequest(BaseModel):
    email_service_id: Optional[str] = None
    service_id: Optional[str] = None  # alias
    message_id: str
    mailbox: str = "INBOX"
    add: List[str] = []    # e.g. ["\\Seen", "\\Flagged"]
    remove: List[str] = [] # e.g. ["\\Answered"]


def _flags_to_proxy_body(add: list[str], remove: list[str]) -> dict:
    """
    Convert add/remove flag lists to the email-proxy PATCH /flags body shape.

    The email-proxy handler accepts {seen, answered, starred} booleans.
    Rules:
      - If a flag appears in add → set that field to True.
      - If a flag appears in remove → set that field to False.
      - If absent from both → omit (None → field omitted).

    Normalise flag names to lowercase for matching.
    """
    body: dict = {}

    add_lower = {f.lower().lstrip("\\") for f in add}
    remove_lower = {f.lower().lstrip("\\") for f in remove}

    if "seen" in add_lower:
        body["seen"] = True
    elif "seen" in remove_lower:
        body["seen"] = False

    if "answered" in add_lower:
        body["answered"] = True
    elif "answered" in remove_lower:
        body["answered"] = False

    # \\Flagged → starred
    if "flagged" in add_lower:
        body["starred"] = True
    elif "flagged" in remove_lower:
        body["starred"] = False

    return body


@router.post("/email_mark_email")
async def email_mark_email(
    request: Request,
    body: MarkEmailRequest,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Update IMAP flags on a message (mark as seen, flagged, answered, etc.).

    Parameters (JSON body)
    ----------------------
    email_service_id : str
        The email service ID — svc_ wire form or raw UUID.
        Alias: ``service_id``.
    message_id : str
        The IMAP UID of the message.
    mailbox : str
        The mailbox containing the message (default: INBOX).
    add : list[str]
        Flags to add, e.g. ["\\\\Seen", "\\\\Flagged"].
    remove : list[str]
        Flags to remove, e.g. ["\\\\Answered"].
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    # Accept service_id alias.
    esvc_input = body.email_service_id or body.service_id
    if not esvc_input:
        return JSONResponse(
            status_code=422,
            content={
                "code": "mintkey:bad_request",
                "title": "Missing required field: email_service_id (or service_id)",
            },
        )

    if not body.add and not body.remove:
        return JSONResponse(
            status_code=422,
            content={"code": "mintkey:bad_request", "title": "add or remove must be non-empty"},
        )

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    await set_tenant_context(session, tenant_id)

    # Resolve email_service_id.
    esvc_uuid = await resolve_email_service_id(esvc_input, tenant_id, session)
    if esvc_uuid is None:
        return JSONResponse(
            status_code=404,
            content={
                "code": "mintkey:not_found",
                "reason_code": "email_service_not_found",
                "email_service_id_input": esvc_input,
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

    # Obtain brokered JWT (scope: write:email — included in all-scopes token).
    jwt = await _get_email_jwt(agent_id, tenant_id, db_esvc_id)
    if jwt is None:
        return JSONResponse(
            status_code=502,
            content={"code": "mintkey:broker_error", "title": "Broker unavailable"},
        )

    # Build the proxy body from add/remove flag lists.
    proxy_body = _flags_to_proxy_body(body.add, body.remove)
    if not proxy_body:
        return JSONResponse(
            status_code=422,
            content={
                "code": "mintkey:bad_request",
                "title": (
                    "No recognised IMAP flags in add/remove. "
                    "Supported: \\\\Seen, \\\\Flagged, \\\\Answered."
                ),
            },
        )

    # Call email-proxy — PATCH /v1/email-proxy/messages/{uid}/flags.
    email_proxy_url = os.getenv("EMAIL_PROXY_INTERNAL_URL", "http://email-proxy:8088")
    async with httpx.AsyncClient() as client:
        resp = await client.patch(
            f"{email_proxy_url}/v1/email-proxy/messages/{body.message_id}/flags",
            params={"service_id": db_esvc_id, "mailbox": body.mailbox},
            json=proxy_body,
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=30.0,
        )

    if resp.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "code": "mintkey:not_found",
                "reason_code": "message_not_found",
                "message_id": body.message_id,
            },
        )

    if resp.status_code not in (200, 204):
        return JSONResponse(
            status_code=resp.status_code,
            content={
                "code": "mintkey:email_proxy_error",
                "title": f"email-proxy returned {resp.status_code}",
                "detail": resp.text[:500],
            },
        )

    if resp.status_code == 204 or not resp.content:
        return JSONResponse({"message_id": body.message_id, "flags_updated": True})

    return JSONResponse(resp.json())
