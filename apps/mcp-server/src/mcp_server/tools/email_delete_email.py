"""
MCP email_delete_email tool.

DELETE /v1/tools/email_delete_email?email_service_id=<id>&message_id=<uid>&mailbox=<mb>&hard=false
  (alias accepted: ?service_id=<id>)

Deletes an IMAP message.
  - Default (hard=false): soft-delete — moves to "Trash" mailbox.
  - hard=true: hard-delete — sets \\Deleted flag and EXPUNGEs.

Implementation:
  1. Auth check (agent context present).
  2. Permission check (email_permission_grants).
  3. Broker JWT exchange (scope: delete:email).
  4. For soft-delete: POST /v1/email-proxy/messages/{uid}/move with to_mailbox=Trash.
     For hard-delete: DELETE /v1/email-proxy/messages/{uid}?service_id=<id>&mailbox=<mb>.
  5. Return 204 on success.

Source: feat/email-tools-list-attach-move-mark-delete.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.tools.discovery import get_agent_context
from mcp_server.tools.email_list_mailboxes import _get_email_jwt
from mcp_server.utils.wire_ids import db_uuid_to_wire, resolve_email_service_id

router = APIRouter(prefix="/v1/tools")

# Default trash mailbox name. Operators with non-standard trash folder names
# (e.g. "[Gmail]/Trash") should use email_move_email instead.
_DEFAULT_TRASH_MAILBOX = "Trash"


@router.delete("/email_delete_email")
async def email_delete_email(
    request: Request,
    message_id: str,
    email_service_id: Optional[str] = None,
    service_id: Optional[str] = None,
    mailbox: str = "INBOX",
    hard: bool = False,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> Response:
    """
    Delete an email message (soft-delete by default, hard-delete with hard=true).

    Parameters
    ----------
    email_service_id : str
        The email service ID — svc_ wire form or raw UUID.
        Alias: ``service_id``.
    message_id : str
        The IMAP UID of the message to delete.
    mailbox : str
        The mailbox containing the message (default: INBOX).
    hard : bool
        False (default): move to Trash mailbox.
        True: EXPUNGE (permanent delete).
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    # Accept ?service_id= as alias.
    esvc_input = email_service_id or service_id
    if not esvc_input:
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

    # Obtain brokered JWT (scope: delete:email — included in all-scopes token).
    jwt = await _get_email_jwt(agent_id, tenant_id, db_esvc_id)
    if jwt is None:
        return JSONResponse(
            status_code=502,
            content={"code": "mintkey:broker_error", "title": "Broker unavailable"},
        )

    email_proxy_url = os.getenv("EMAIL_PROXY_INTERNAL_URL", "http://email-proxy:8088")

    if hard:
        # Hard-delete: DELETE /v1/email-proxy/messages/{uid} → EXPUNGE on proxy side.
        async with httpx.AsyncClient() as client:
            resp = await client.delete(
                f"{email_proxy_url}/v1/email-proxy/messages/{message_id}",
                params={"service_id": db_esvc_id, "mailbox": mailbox},
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=30.0,
            )
    else:
        # Soft-delete: move to Trash via POST .../move.
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{email_proxy_url}/v1/email-proxy/messages/{message_id}/move",
                params={"service_id": db_esvc_id, "mailbox": mailbox},
                json={"destination_mailbox": _DEFAULT_TRASH_MAILBOX},
                headers={"Authorization": f"Bearer {jwt}"},
                timeout=30.0,
            )

        if resp.status_code in (422, 404) and not hard:
            # Trash mailbox doesn't exist on this server. Return a clear 422 with hint.
            _trash_hint = (
                "Soft delete failed: could not move message to "
                + repr(_DEFAULT_TRASH_MAILBOX)
                + ". The trash mailbox may not exist on this IMAP server. "
                "Use email_move_email to move the message to the correct trash mailbox name "
                "(e.g. '[Gmail]/Trash'), or call with ?hard=true to EXPUNGE instead."
            )
            return JSONResponse(
                status_code=422,
                content={
                    "code": "mintkey:email_proxy_error",
                    "title": _trash_hint,
                    "detail": resp.text[:500],
                },
            )

    if resp.status_code == 404:
        return JSONResponse(
            status_code=404,
            content={
                "code": "mintkey:not_found",
                "reason_code": "message_not_found",
                "message_id": message_id,
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

    return Response(status_code=204)
