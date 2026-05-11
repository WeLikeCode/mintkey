"""
Agent CRUD endpoints.

POST   /v1/tenants/{tenant_id}/agents              — create agent (201, api_key shown once)
GET    /v1/tenants/{tenant_id}/agents              — list agents (200)
GET    /v1/tenants/{tenant_id}/agents/{agent_id}   — get agent (200, no plaintext key)
DELETE /v1/tenants/{tenant_id}/agents/{agent_id}   — delete agent (204)

Architecture constraints:
  - API key returned plaintext exactly once at creation — S-SEC-1, ADR-0014.4.
  - DB stores only Argon2id hash and 8-byte fingerprint — S-SEC-1, T-1.4.1.
  - Audit event "agent.created" carries fingerprint, NOT plaintext — ADR-0014.7.
  - Tenant context via bound parameters — ADR-0008, T-1.0.15.
  - ULID IDs with prefix "agent_" — ADR-0017.11.
  - Global channel "mintkey:agent" — ADR-0014.1.
  - mcp_endpoint computed from MCP_BASE_URL env var.

Source: T-1.4.1; ADR-0008; ADR-0014.7; ADR-0017.11; S-SEC-1.
"""
from __future__ import annotations

import hashlib
import os
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from argon2 import PasswordHasher
from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(prefix="/v1/tenants/{tenant_id}/agents")

# Crockford base32 alphabet (uppercase, no I/L/O/U) — matches services.py
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Argon2id hasher — S-SEC-1
_ph = PasswordHasher()


# ---------------------------------------------------------------------------
# ID generation — ADR-0017.11
# ---------------------------------------------------------------------------


def _new_agent_id() -> str:
    """
    Generate a ULID-format ID with the 'agent_' prefix — ADR-0017.11.

    Layout: 10 time chars (48-bit ms) + 16 random chars = 26 Crockford base32 chars.
    """
    ts_ms = int(time.time() * 1000)
    rand = int.from_bytes(uuid.uuid4().bytes[:10], "big")

    t_enc = []
    v = ts_ms
    for _ in range(10):
        t_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    t_enc.reverse()

    r_enc = []
    v = rand
    for _ in range(16):
        r_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    r_enc.reverse()

    return "agent_" + "".join(t_enc) + "".join(r_enc)


# ---------------------------------------------------------------------------
# API key generation — T-1.4.1, S-SEC-1
# ---------------------------------------------------------------------------


def _generate_agent_api_key() -> tuple[str, str, str]:
    """
    Returns (plaintext, argon2_hash, fingerprint_hex).

    plaintext    = "mk_agent_" + 52-char Crockford base32 of 32 random bytes
    fingerprint  = sha256(plaintext.encode())[:8].hex()
    argon2_hash  = Argon2id hash of plaintext

    The plaintext is returned to the caller exactly once.
    Only argon2_hash and fingerprint are persisted — S-SEC-1, ADR-0014.4.
    """
    raw = secrets.token_bytes(32)
    val = int.from_bytes(raw, "big")
    encoded = ""
    for _ in range(52):
        encoded = _CROCKFORD[val & 0x1F] + encoded
        val >>= 5
    plaintext = "mk_agent_" + encoded
    fingerprint = hashlib.sha256(plaintext.encode()).digest()[:8].hex()
    api_key_hash = _ph.hash(plaintext)
    return plaintext, api_key_hash, fingerprint


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class AgentCreate(BaseModel):
    name: str
    description: Optional[str] = None
    rate_limit_rps: Optional[int] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _agent_row_to_dict(row: Any) -> dict[str, Any]:
    """Map a DB row to the wire representation — no plaintext key."""
    raw_id = str(row.id)
    return {
        "id": f"agent_{raw_id.replace('-', '')}",
        "tenant_id": str(row.tenant_id),
        "name": row.name,
        "description": row.description,
        "api_key_fingerprint": row.api_key_fingerprint,
        "mcp_endpoint": row.mcp_endpoint,
        "status": row.status,
        "rate_limit_rps": row.rate_limit_rps,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_agent(
    tenant_id: UUID,
    body: AgentCreate,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Register a new agent under a tenant.

    Returns the plaintext API key exactly once in the response body.
    DB stores only the Argon2id hash and fingerprint — S-SEC-1, ADR-0014.4.

    Source: T-1.4.1; ADR-0008; ADR-0014.7; ADR-0017.11.
    """
    await set_tenant_context(session, tenant_id)

    agent_id = _new_agent_id()
    internal_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    plaintext, api_key_hash, fingerprint = _generate_agent_api_key()

    mcp_base = os.getenv("MCP_BASE_URL", "http://localhost:8100")
    mcp_endpoint = f"{mcp_base}/v1/agents/{agent_id}"

    await session.execute(
        text(
            "INSERT INTO agents"
            " (id, tenant_id, name, description, api_key_hash, api_key_fingerprint,"
            "  mcp_endpoint, status, rate_limit_rps, created_at, updated_at)"
            " VALUES"
            " (:id, :tenant_id, :name, :description, :api_key_hash, :api_key_fingerprint,"
            "  :mcp_endpoint, :status, :rate_limit_rps, :created_at, :updated_at)"
        ),
        {
            "id": str(internal_id),
            "tenant_id": str(tenant_id),
            "name": body.name,
            "description": body.description,
            "api_key_hash": api_key_hash,
            "api_key_fingerprint": fingerprint,
            "mcp_endpoint": mcp_endpoint,
            "status": "active",
            "rate_limit_rps": body.rate_limit_rps,
            "created_at": now,
            "updated_at": now,
        },
    )

    # Audit event carries fingerprint, NOT plaintext — ADR-0014.7, S-SEC-1
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="agent.created",
        actor_id=None,
        actor_type="operator",
        target_id=internal_id,
        target_type="agent",
        payload={"agent_id": agent_id, "api_key_fingerprint": fingerprint},
    )

    await notify_change(
        session,
        "mintkey:agent",
        {
            "event": "agent.created",
            "tenant_id": str(tenant_id),
            "agent_id": agent_id,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": agent_id,
            "tenant_id": str(tenant_id),
            "name": body.name,
            "description": body.description,
            "api_key": plaintext,
            "api_key_fingerprint": fingerprint,
            "mcp_endpoint": mcp_endpoint,
            "status": "active",
            "rate_limit_rps": body.rate_limit_rps,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )


@router.get("")
async def list_agents(
    tenant_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List all agents for a tenant. Never returns plaintext API keys.

    Source: T-1.4.1; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, tenant_id, name, description, api_key_fingerprint,"
            " mcp_endpoint, status, rate_limit_rps, created_at, updated_at"
            " FROM agents WHERE tenant_id = :tenant_id ORDER BY created_at"
        ),
        {"tenant_id": str(tenant_id)},
    )
    rows = result.fetchall()
    agents = [_agent_row_to_dict(r) for r in rows]
    return JSONResponse({"agents": agents})


@router.get("/{agent_id}")
async def get_agent(
    tenant_id: UUID,
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Get a single agent. Never returns the plaintext API key.

    Source: T-1.4.1; ADR-0008; S-SEC-1.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, tenant_id, name, description, api_key_fingerprint,"
            " mcp_endpoint, status, rate_limit_rps, created_at, updated_at"
            " FROM agents WHERE id = :aid AND tenant_id = :tid"
        ),
        {"aid": agent_id, "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Agent not found"},
        )
    return JSONResponse(_agent_row_to_dict(row))


@router.post("/{agent_id}/revoke")
async def revoke_agent(
    tenant_id: UUID,
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Set agent status to 'revoked', emit agent.revoked audit event,
    and fire NOTIFY on the global mintkey:agent channel.

    Source: T-1.9.1; ADR-0008; ADR-0014.1; ADR-0014.7.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text("SELECT id FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": agent_id, "tid": str(tenant_id)},
    )
    if result.fetchone() is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Agent not found"},
        )

    await session.execute(
        text(
            "UPDATE agents SET status = 'revoked', updated_at = now()"
            " WHERE id = :aid AND tenant_id = :tid"
        ),
        {"aid": agent_id, "tid": str(tenant_id)},
    )

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="agent.revoked",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="agent",
        payload={"agent_id": agent_id},
    )

    await notify_change(
        session,
        "mintkey:agent",
        {
            "event": "agent.revoked",
            "tenant_id": str(tenant_id),
            "agent_id": agent_id,
        },
    )

    return JSONResponse({"status": "ok", "agent_id": agent_id})


@router.delete("/{agent_id}", status_code=204)
async def delete_agent(
    tenant_id: UUID,
    agent_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """
    Delete (hard-delete) an agent.

    Source: T-1.4.1; ADR-0008; ADR-0014.7.
    """
    await set_tenant_context(session, tenant_id)

    await session.execute(
        text("DELETE FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": agent_id, "tid": str(tenant_id)},
    )

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="agent.deleted",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="agent",
        payload={"agent_id": agent_id},
    )

    await notify_change(
        session,
        "mintkey:agent",
        {
            "event": "agent.revoked",
            "tenant_id": str(tenant_id),
            "agent_id": agent_id,
        },
    )

    return Response(status_code=204)
