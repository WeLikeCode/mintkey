"""
MCP secret_put tool.

POST /v1/tools/secret_put

Stores (or overwrites) a named secret owned by the calling agent.
Flow: auth check → set_tenant_context → upsert metadata → PutAgentSecret gRPC
      → audit emit → commit.

Blob-first write ordering: gRPC seal happens before metadata commit so an
orphaned vault blob (gRPC OK, metadata commit fails) is overwritten on retry.

Source: ADR-0025; design.md D2, D3.
"""
from __future__ import annotations

import re
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.tools.discovery import get_agent_context
from mcp_server.utils.wire_ids import db_uuid_to_wire
from mcp_server.vault.agent_secrets_client import get_agent_secrets_vault_client

router = APIRouter(prefix="/v1/tools")

_NAME_RE = re.compile(r"^[a-zA-Z0-9._-]{1,128}$")
_MAX_VALUE_BYTES = 65536


class SecretPutRequest(BaseModel):
    name: str
    value: str
    content_type: Optional[str] = None


@router.post("/secret_put")
async def secret_put(
    request: Request,
    body: SecretPutRequest,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Store (or overwrite) a named secret.

    Parameters
    ----------
    name : str
        Secret name (^[a-zA-Z0-9._-]{1,128}$), unique per owning agent.
    value : str
        Plaintext secret value (UTF-8, max 65536 bytes).
    content_type : str, optional
        Free-text hint (e.g. "application/json").
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    # Validate name
    if not _NAME_RE.match(body.name):
        return JSONResponse(
            status_code=422,
            content={
                "code": "mintkey:invalid_argument",
                "title": (
                    "name must match ^[a-zA-Z0-9._-]{1,128}$; "
                    f"got {body.name!r}"
                ),
            },
        )

    # Validate value size
    value_bytes = body.value.encode("utf-8")
    if len(value_bytes) > _MAX_VALUE_BYTES:
        return JSONResponse(
            status_code=422,
            content={
                "code": "mintkey:invalid_argument",
                "title": f"value exceeds {_MAX_VALUE_BYTES} bytes",
            },
        )

    await set_tenant_context(session, tenant_id)

    # Check whether a row already exists for (tenant, agent, name)
    existing = await session.execute(
        text(
            "SELECT id, version FROM agent_secrets"
            " WHERE tenant_id = :stid AND agent_id = :sagent AND name = :sname"
        ),
        {"stid": tenant_id, "sagent": agent_id, "sname": body.name},
    )
    row = existing.fetchone()

    if row is None:
        # First store — mint a new UUID
        new_uuid = uuid.uuid4()
        secret_db_id = str(new_uuid)
        new_version = 1
        is_create = True
    else:
        secret_db_id = str(row.id)
        new_version = int(row.version) + 1
        is_create = False

    wire_id = db_uuid_to_wire(secret_db_id, "sec")

    # ---- BLOB-FIRST: call vault-adapter before committing metadata ----
    vault_client = await get_agent_secrets_vault_client()
    await vault_client.put_agent_secret(
        tenant_id=tenant_id,
        secret_id=secret_db_id,
        value=value_bytes,
    )

    # ---- Upsert metadata row ----
    if is_create:
        await session.execute(
            text(
                "INSERT INTO agent_secrets"
                " (id, tenant_id, agent_id, name, content_type, size_bytes, version)"
                " VALUES (:sid, :stid, :sagent, :sname, :sctype, :ssize, 1)"
            ),
            {
                "sid": secret_db_id,
                "stid": tenant_id,
                "sagent": agent_id,
                "sname": body.name,
                "sctype": body.content_type,
                "ssize": len(value_bytes),
            },
        )
    else:
        await session.execute(
            text(
                "UPDATE agent_secrets"
                " SET version = :sver, size_bytes = :ssize,"
                "     content_type = :sctype, updated_at = now()"
                " WHERE id = :sid AND tenant_id = :stid"
            ),
            {
                "sver": new_version,
                "ssize": len(value_bytes),
                "sctype": body.content_type,
                "sid": secret_db_id,
                "stid": tenant_id,
            },
        )

    # ---- Audit (in same transaction, identifier-only — no value) ----
    event_type = "agent_secret.created" if is_create else "agent_secret.updated"
    agent_wire_id = db_uuid_to_wire(agent_id, "agent")
    audit_payload: dict = {
        "secret_id": wire_id,
        "agent_id": agent_wire_id,
        "name": body.name,
        "version": new_version,
    }
    if not is_create:
        # previous_version is known: it was new_version - 1
        audit_payload["previous_version"] = new_version - 1
    await audit_emit(
        session=session,
        tenant_id=uuid.UUID(tenant_id),
        event_type=event_type,
        actor_id=uuid.UUID(agent_id) if agent_id else None,
        actor_type="agent",
        target_id=uuid.UUID(secret_db_id),
        target_type="agent_secret",
        payload=audit_payload,
    )

    await session.commit()

    return JSONResponse(
        status_code=200,
        content={
            "secret_id": wire_id,
            "name": body.name,
            "version": new_version,
        },
    )
