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
from admin_api.utils.wire_ids import db_uuid_to_wire
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
    """Map a DB row to the wire representation — no plaintext key.

    Emits Crockford ULID wire-form IDs (canonical per ADR-0017.11 / #13).
    """
    return {
        "id": db_uuid_to_wire(row.id, "agent"),
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
    # Derive the DB UUID from the ULID's 128-bit value — R8-redux (ADR-0017.11).
    # _new_agent_id() returns "agent_<26-char Crockford ULID>"; decode the 26-char
    # tail to the same 128-bit integer and wrap as uuid.UUID so the stored row PK
    # is algebraically identical to what _wire_id_to_uuid() decodes from the wire ID.
    # Dropping the independent uuid.uuid4() eliminates the asymmetry that caused silent
    # 404s: POST returned agent_<Crockford> whose bits never matched the stored PK.
    _crockford_tail = agent_id[len("agent_"):]
    _val = 0
    for _ch in _crockford_tail.upper():
        _val = (_val << 5) | _CROCKFORD.index(_ch)
    _val &= (1 << 128) - 1
    internal_id = uuid.UUID(int=_val)
    now = datetime.now(timezone.utc)

    plaintext, api_key_hash, fingerprint = _generate_agent_api_key()

    mcp_base = os.getenv("MCP_BASE_URL", "http://localhost:8082")
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


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input cannot glob-match unexpectedly."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _wire_id_to_uuid(wire_id: str, prefix: str) -> str:
    """
    Accept either a UUID string or a prefixed wire ID and return the UUID string.

    Thin wrapper around utils.wire_ids.wire_to_db_uuid — kept here so that
    api_keys.py and permissions.py can import it from this module without
    circular-import issues.

    Two wire forms are accepted (ADR-0017.11 / #13 backward-compat):
      - <prefix>_<26 Crockford base32 chars> — canonical post-R13 form
      - <prefix>_<32 hex chars>              — legacy pre-R13 list form

    The ``prefix`` argument may include a trailing underscore (historic callers
    pass ``"agent_"``, ``"svc_"`` etc.) — the trailing underscore is stripped
    before forwarding to ``wire_to_db_uuid`` which builds ``f"{prefix}_"``
    internally.

    Raises ValueError if the wire_id looks like a prefixed ID but cannot be decoded.

    Source: ADR-0017.11; R8; #13.
    """
    from admin_api.utils.wire_ids import wire_to_db_uuid as _decode  # noqa: PLC0415
    # Normalise: strip trailing underscore if callers pass "agent_" instead of "agent"
    bare_prefix = prefix.rstrip("_")
    return _decode(wire_id, bare_prefix)


@router.get("")
async def list_agents(
    tenant_id: UUID,
    q: Optional[str] = None,
    has_access_to_service_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List all agents for a tenant. Never returns plaintext API keys.

    Optional query parameters:
      q                     — case-insensitive substring search on name or description.
      has_access_to_service_id — filter to agents with at least one active permission_grant
                                  on the given service (UUID or svc_ wire-ID).

    Source: T-1.4.1; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    params: dict = {"tenant_id": str(tenant_id)}

    base_sql = (
        "SELECT id, tenant_id, name, description, api_key_fingerprint,"
        " mcp_endpoint, status, rate_limit_rps, created_at, updated_at"
        " FROM agents WHERE tenant_id = :tenant_id"
    )

    if q is not None:
        escaped = _escape_like(q)
        pattern = f"%{escaped}%"
        base_sql += " AND (name ILIKE :pat ESCAPE '\\' OR description ILIKE :pat ESCAPE '\\')"
        params["pat"] = pattern

    if has_access_to_service_id is not None:
        try:
            svc_uuid = _wire_id_to_uuid(has_access_to_service_id, "svc_")
        except ValueError:
            from fastapi.responses import JSONResponse as _JSONResponse  # noqa: PLC0415
            return _JSONResponse(
                status_code=422,
                content={"mintkey:code": "invalid_id", "title": "Invalid has_access_to_service_id"},
            )
        base_sql += (
            " AND EXISTS ("
            "   SELECT 1 FROM permission_grants pg"
            "   WHERE pg.agent_id = agents.id"
            "     AND pg.tenant_id = :tenant_id"
            "     AND pg.service_id = :svc_id"
            " )"
        )
        params["svc_id"] = svc_uuid

    base_sql += " ORDER BY created_at"

    result = await session.execute(text(base_sql), params)
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
    # Decode wire-prefixed ID (agent_<32hex> or agent_<26-Crockford>) → UUID — ADR-0017.11; R8
    try:
        agent_uuid = _wire_id_to_uuid(agent_id, "agent_")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
        )
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, tenant_id, name, description, api_key_fingerprint,"
            " mcp_endpoint, status, rate_limit_rps, created_at, updated_at"
            " FROM agents WHERE id = :aid AND tenant_id = :tid"
        ),
        {"aid": agent_uuid, "tid": str(tenant_id)},
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
    # Decode wire-prefixed ID → UUID — ADR-0017.11; R8
    try:
        agent_uuid = _wire_id_to_uuid(agent_id, "agent_")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
        )
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text("SELECT id FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": agent_uuid, "tid": str(tenant_id)},
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
        {"aid": agent_uuid, "tid": str(tenant_id)},
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
    # Decode wire-prefixed ID → UUID — ADR-0017.11; R8
    try:
        agent_uuid = _wire_id_to_uuid(agent_id, "agent_")
    except ValueError:
        return Response(status_code=422)
    await set_tenant_context(session, tenant_id)

    await session.execute(
        text("DELETE FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": agent_uuid, "tid": str(tenant_id)},
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
