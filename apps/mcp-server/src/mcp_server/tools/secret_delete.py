"""
MCP secret_delete tool.

DELETE /v1/tools/secret_delete?secret_id=<sec_…>

Deletes a secret owned by the calling agent. Cascades any share grants
(FK cascade defined in Liquibase 027).

Anti-enumeration: returns the same status + body for nonexistent AND
not-owned secrets (ADR-0025.D5).

Idempotent: returns success even if the row was already absent.

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
        "title": "Secret not found or not owned by calling agent",
    },
)


@router.delete("/secret_delete")
async def secret_delete(
    request: Request,
    secret_id: str = Query(...),
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Delete a secret owned by the calling agent.

    Parameters
    ----------
    secret_id : str
        sec_ wire form of the secret.
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    # Decode secret_id — return uniform not-found on malformed input
    if not secret_id.startswith("sec_"):
        return _SECRET_NOT_FOUND
    try:
        secret_db_id = wire_to_db_uuid(secret_id, "sec")
        uuid.UUID(secret_db_id)
    except (ValueError, AttributeError):
        return _SECRET_NOT_FOUND

    await set_tenant_context(session, tenant_id)

    # Owner-only check: return not-found for non-owner and nonexistent alike
    ownership = await session.execute(
        text(
            "SELECT id, name FROM agent_secrets"
            " WHERE id = :dsecret AND tenant_id = :dtid AND agent_id = :dagent"
        ),
        {"dsecret": secret_db_id, "dtid": tenant_id, "dagent": agent_id},
    )
    row = ownership.fetchone()
    if row is None:
        return _SECRET_NOT_FOUND

    secret_name = row.name
    wire_id = db_uuid_to_wire(secret_db_id, "sec")

    # Delete encrypted blob (idempotent — vault returns ok if already absent)
    vault_client = await get_agent_secrets_vault_client()
    await vault_client.delete_agent_secret(
        tenant_id=tenant_id,
        secret_id=secret_db_id,
    )

    # Delete metadata (grants cascade via FK ON DELETE CASCADE)
    await session.execute(
        text(
            "DELETE FROM agent_secrets"
            " WHERE id = :dsecret AND tenant_id = :dtid"
        ),
        {"dsecret": secret_db_id, "dtid": tenant_id},
    )

    # Audit
    agent_wire_id = db_uuid_to_wire(agent_id, "agent")
    await audit_emit(
        session=session,
        tenant_id=uuid.UUID(tenant_id),
        event_type="agent_secret.deleted",
        actor_id=uuid.UUID(agent_id) if agent_id else None,
        actor_type="agent",
        target_id=uuid.UUID(secret_db_id),
        target_type="agent_secret",
        payload={
            "secret_id": wire_id,
            "agent_id": agent_wire_id,
            "name": secret_name,
        },
    )

    await session.commit()

    return JSONResponse(status_code=200, content={})
