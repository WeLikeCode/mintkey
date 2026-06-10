"""
MCP secret_get tool.

GET /v1/tools/secret_get?secret_id=<sec_…>

Reads the plaintext value of a secret the calling agent owns or has been
granted read access to.

Anti-enumeration: returns the same status + body for nonexistent AND
not-visible secrets (ADR-0025.D5, D6).

Plaintext is returned in the response body ONLY. It MUST NOT appear in
logs, audit payloads, span attributes, or change-event payloads.

Source: ADR-0025; spec agent-secret-storage; design.md D3, D6.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.tools.discovery import get_agent_context
from mcp_server.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid
from mcp_server.vault.agent_secrets_client import get_agent_secrets_vault_client

router = APIRouter(prefix="/v1/tools")

_SECRET_NOT_FOUND = JSONResponse(
    status_code=404,
    content={
        "code": "mintkey:secret_not_found",
        "title": "Secret not found or not visible",
    },
)


@router.get("/secret_get")
async def secret_get(
    request: Request,
    secret_id: str = Query(...),
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Read the plaintext value of a secret.

    Parameters
    ----------
    secret_id : str
        sec_ wire form of the secret.
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    # Decode secret_id to DB UUID — return uniform not-found on malformed input
    if not secret_id.startswith("sec_"):
        return _SECRET_NOT_FOUND
    try:
        secret_db_id = wire_to_db_uuid(secret_id, "sec")
        uuid.UUID(secret_db_id)  # validate
    except (ValueError, AttributeError):
        return _SECRET_NOT_FOUND

    await set_tenant_context(session, tenant_id)

    # Resolve owner-or-shared visibility with a single SQL query
    vis = await session.execute(
        text(
            "SELECT s.id, s.name, s.version, s.content_type,"
            "  CASE WHEN s.agent_id = :cagent THEN 'owner' ELSE 'shared' END AS access"
            " FROM agent_secrets s"
            " WHERE s.id = :gsecret AND s.tenant_id = :gtid"
            "   AND ("
            "     s.agent_id = :cagent2"
            "     OR EXISTS ("
            "       SELECT 1 FROM agent_secret_grants g"
            "       WHERE g.secret_id = s.id AND g.recipient_agent_id = :cagent3"
            "         AND g.tenant_id = :gtid2"
            "     )"
            "   )"
        ),
        {
            "cagent": agent_id,
            "gsecret": secret_db_id,
            "gtid": tenant_id,
            "cagent2": agent_id,
            "cagent3": agent_id,
            "gtid2": tenant_id,
        },
    )
    row = vis.fetchone()
    if row is None:
        return _SECRET_NOT_FOUND

    meta_secret_id = str(row.id)
    name = row.name
    version = int(row.version)
    content_type = row.content_type
    access = row.access
    wire_id = db_uuid_to_wire(meta_secret_id, "sec")

    # Unseal via vault-adapter
    vault_client = await get_agent_secrets_vault_client()
    plaintext: bytes | None = await vault_client.get_agent_secret(
        tenant_id=tenant_id,
        secret_id=meta_secret_id,
    )
    if plaintext is None:
        # Vault blob missing (orphan metadata) — treat as not-found
        return _SECRET_NOT_FOUND

    # Audit: identifier-only payload — NO value
    reader_agent_wire_id = db_uuid_to_wire(agent_id, "agent")
    await audit_emit(
        session=session,
        tenant_id=uuid.UUID(tenant_id),
        event_type="agent_secret.read",
        actor_id=uuid.UUID(agent_id) if agent_id else None,
        actor_type="agent",
        target_id=uuid.UUID(meta_secret_id),
        target_type="agent_secret",
        payload={
            "secret_id": wire_id,
            "version": version,
            "reader_agent_id": reader_agent_wire_id,
            "access": access,
        },
    )

    await session.commit()

    # Plaintext only in response body — never in logs/audit/spans
    response: dict = {
        "secret_id": wire_id,
        "name": name,
        "version": version,
        "value": plaintext.decode("utf-8", errors="replace"),
        "access": access,
    }
    if content_type is not None:
        response["content_type"] = content_type

    return JSONResponse(status_code=200, content=response)
