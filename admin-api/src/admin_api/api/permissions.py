"""
Permission grant/revoke endpoints.

POST   /v1/tenants/{tenant_id}/agents/{agent_id}/permissions        — grant permission (201)
DELETE /v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{pid}  — revoke permission (204)

Architecture constraints:
  - Constraints schema is CLOSED (additionalProperties=false) — ADR-0016.4.
  - Tenant context via bound parameters — ADR-0008, T-1.0.15.
  - Audit emit on every state change — ADR-0014.7.
  - ULID IDs with prefix "perm_" — ADR-0017.11.
  - Global channel "mintkey:agent" — ADR-0014.1.
  - Cross-tenant access returns 404 (RLS + explicit check) — ADR-0008.
  - Idempotent re-grant: same params → 200; different constraints → 409.

Source: T-1.4.2; ADR-0008; ADR-0014.7; ADR-0016.4; ADR-0017.11.
"""
from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.api.agents import _wire_id_to_uuid as _decode_agent_wire_id
from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from admin_api.db.tables import (
    agents as agents_table,
    permission_grants as pg_table,
    services as services_table,
)
from admin_api.utils.wire_ids import db_uuid_to_wire
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(prefix="/v1/tenants/{tenant_id}/agents/{agent_id}/permissions")

# Flat list router — no agent_id scoping; used by admin-ui dashboard + ApiKeyCreate
# Source: A2 R9 fix; AdminJS RestResource listPath="/v1/tenants/{tenantId}/permissions"
tenant_permissions_router = APIRouter(prefix="/v1/tenants/{tenant_id}/permissions")

# Crockford base32 alphabet (uppercase, no I/L/O/U) — ADR-0017.11
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


# ---------------------------------------------------------------------------
# ID generation — ADR-0017.11
# ---------------------------------------------------------------------------


def _new_perm_id() -> str:
    """Generate a ULID-format ID with the 'perm_' prefix — ADR-0017.11."""
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

    return "perm_" + "".join(t_enc) + "".join(r_enc)


# ---------------------------------------------------------------------------
# Constraints schema — CLOSED per ADR-0016.4
# ---------------------------------------------------------------------------


class RateLimitConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    requests_per_second: int
    burst: int


class TimeWindowConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timezone: str
    days: list[str]
    start_local: str
    end_local: str


class RequestPathPrefixConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prefix: str


class SourceIpAllowlistConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")
    cidrs: list[str]


class Constraints(BaseModel):
    model_config = ConfigDict(extra="forbid")  # CLOSED — ADR-0016.4
    rate_limit: Optional[RateLimitConstraint] = None
    time_window: Optional[TimeWindowConstraint] = None
    request_path_prefix: Optional[RequestPathPrefixConstraint] = None
    source_ip_allowlist: Optional[SourceIpAllowlistConstraint] = None


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class PermissionGrantRequest(BaseModel):
    service_id: str
    action: str
    constraints: Optional[Constraints] = None
    granted_by: Optional[str] = None


# ---------------------------------------------------------------------------
# Exception handler — wrap Pydantic 422 with mintkey:code — ADR-0016.4
# ---------------------------------------------------------------------------


async def validation_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """
    Convert FastAPI RequestValidationError into the Mintkey error envelope.

    Registered in main.py and in test app factories so that unknown
    Constraints keys return 422 with mintkey:code=validation_failed.

    Source: T-1.4.2; ADR-0016.4.
    """
    return JSONResponse(
        status_code=422,
        content={"mintkey:code": "validation_failed", "title": str(exc)},
    )


# ---------------------------------------------------------------------------
# Shared helper — resolve svc_ wire-form to DB UUID — R12; ADR-0017.11
# ---------------------------------------------------------------------------


async def _resolve_service_uuid(
    session: AsyncSession,
    tenant_id: UUID,
    svc_input: str,
) -> str:
    """
    Translate a service identifier (wire-form or plain UUID) to the DB UUID string.

    Primary path (R12+, new services): decode the 26-char Crockford ULID or 32-hex form
    via _decode_agent_wire_id(svc_input, "svc_"), then verify the decoded UUID exists in
    the services table.  For post-R12 services this resolves directly without any audit
    lookup because create_service now derives internal_id from the same ULID bits.

    Fallback path (pre-R12, old services): if the decoded UUID doesn't exist in services
    (because the old code used uuid4() independently), fall back to the audit_events
    lookup added by R11a.  This ensures old data continues to work.

    Returns the UUID string, or raises HTTPException(404) if neither path resolves.

    Source: R12; R11a; ADR-0017.11.
    """
    if not svc_input.startswith("svc_"):
        # Plain UUID — return as-is
        return svc_input

    # Primary path: decode wire form → UUID
    try:
        decoded_uuid = _decode_agent_wire_id(svc_input, "svc_")
    except ValueError:
        raise Exception("invalid_service_id")

    # Verify the decoded UUID exists in services table (post-R12 services resolve here)
    exists_result = await session.execute(
        text("SELECT 1 FROM services WHERE id = :sid AND tenant_id = :tid"),
        {"sid": decoded_uuid, "tid": str(tenant_id)},
    )
    if exists_result.fetchone() is not None:
        return decoded_uuid

    # Fallback: old services (pre-R12) stored uuid4() independent of ULID bits.
    # Look up the DB UUID via the wire-form stored in audit_events payload.
    svc_lookup = await session.execute(
        text(
            "SELECT target_id FROM audit_events"
            " WHERE event_type = 'service.registered'"
            "   AND tenant_id = :tid"
            "   AND payload->>'svc_id' = :svc_wire"
            " LIMIT 1"
        ),
        {"tid": str(tenant_id), "svc_wire": svc_input},
    )
    svc_row = svc_lookup.fetchone()
    if svc_row is None:
        raise Exception("not_found")
    return str(svc_row.target_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input cannot glob-match unexpectedly."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
async def list_permissions(
    tenant_id: UUID,
    agent_id: str,
    service_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List permission grants for an agent.

    Optional query parameters:
      service_id — filter to grants for a specific service (UUID or svc_ wire-ID).

    Note: permission_grants has no free-text searchable field; q param is not
    applicable and is omitted. service_id contextual filter is supported.

    Source: T-1.4.2; ADR-0008.
    """
    # Decode wire-prefixed agent_id → UUID — ADR-0017.11; R8
    try:
        agent_uuid = _decode_agent_wire_id(agent_id, "agent_")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
        )
    await set_tenant_context(session, tenant_id)

    # Defense-in-depth: pass only full string literals to text() so the
    # SQL is statically verifiable with no dynamic concatenation.
    # Option B: explicit branches — each text() call has a constant argument.
    svc_uuid_val: str | None = None
    if service_id is not None:
        # Accept svc_ wire-ID (Crockford or legacy 32-hex) or plain UUID
        from admin_api.utils.wire_ids import wire_to_db_uuid as _decode_wire  # noqa: PLC0415
        svc_uuid_val = _decode_wire(service_id, "svc")

    if svc_uuid_val is not None:
        result = await session.execute(
            text(
                "SELECT id, tenant_id, agent_id, service_id, action, constraints, created_at, created_by"
                " FROM permission_grants"
                " WHERE agent_id = :aid AND tenant_id = :tid"
                " AND service_id = :svc_id"
                " ORDER BY created_at"
            ),
            {"aid": agent_uuid, "tid": str(tenant_id), "svc_id": svc_uuid_val},
        )
    else:
        result = await session.execute(
            text(
                "SELECT id, tenant_id, agent_id, service_id, action, constraints, created_at, created_by"
                " FROM permission_grants"
                " WHERE agent_id = :aid AND tenant_id = :tid"
                " ORDER BY created_at"
            ),
            {"aid": agent_uuid, "tid": str(tenant_id)},
        )
    rows = result.fetchall()

    grants = [
        {
            "id": db_uuid_to_wire(row.id, "perm"),
            "tenant_id": str(row.tenant_id),
            "agent_id": db_uuid_to_wire(row.agent_id, "agent"),
            "service_id": db_uuid_to_wire(row.service_id, "svc") if row.service_id else None,
            "action": row.action,
            "constraints": row.constraints if isinstance(row.constraints, dict) else (
                json.loads(row.constraints) if row.constraints else None
            ),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "created_by": str(row.created_by) if row.created_by else None,
        }
        for row in rows
    ]
    return JSONResponse({"grants": grants})


# ---------------------------------------------------------------------------
# Flat tenant-level list — no agent_id scoping
# GET /v1/tenants/{tenant_id}/permissions
# Used by: admin-ui dashboard + ApiKeyCreate dropdown (RestResource listPath)
# Source: A2 R9 fix; ADR-0008.
# ---------------------------------------------------------------------------

@tenant_permissions_router.get("")
async def list_tenant_permissions(
    tenant_id: UUID,
    service_id: Optional[str] = None,
    agent_id: Optional[str] = None,
    q: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List all permission grants for a tenant.

    Optional query parameters:
      service_id — filter by service (UUID or svc_ wire-ID).
      agent_id   — filter by agent (UUID or agent_ wire-ID).
      q          — case-insensitive substring match on action (ILIKE '%q%').

    Returns {"permissions": [...]} to match admin-ui RestResource listKey.

    Source: A2 R9 fix; T-1.4.3; ADR-0008; UX-B.
    """
    await set_tenant_context(session, tenant_id)

    # Defense-in-depth: SQLAlchemy Core select() with chained .where() calls.
    # Option A: Table API — no text()/string-concat SQL; all WHERE clauses are
    # bound by SQLAlchemy's parameterisation engine.
    # Columns aliased to preserve the existing response shape.
    stmt = (
        select(
            pg_table.c.id,
            pg_table.c.tenant_id,
            pg_table.c.agent_id,
            pg_table.c.service_id,
            pg_table.c.action,
            pg_table.c.constraints,
            pg_table.c.created_at,
            pg_table.c.created_by,
            services_table.c.name.label("service_name"),
            services_table.c.slug.label("service_slug"),
            agents_table.c.name.label("agent_name"),
        )
        .select_from(
            pg_table
            .outerjoin(
                services_table,
                (services_table.c.id == pg_table.c.service_id)
                & (services_table.c.tenant_id == pg_table.c.tenant_id),
            )
            .outerjoin(
                agents_table,
                (agents_table.c.id == pg_table.c.agent_id)
                & (agents_table.c.tenant_id == pg_table.c.tenant_id),
            )
        )
        .where(pg_table.c.tenant_id == tenant_id)
        .order_by(pg_table.c.created_at)
    )

    if agent_id is not None:
        try:
            agent_uuid_val = _decode_agent_wire_id(agent_id, "agent_")
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
            )
        stmt = stmt.where(pg_table.c.agent_id == agent_uuid_val)

    if service_id is not None:
        # Accept svc_ wire-ID (Crockford or legacy 32-hex) or plain UUID
        from admin_api.utils.wire_ids import wire_to_db_uuid as _decode_wire  # noqa: PLC0415
        svc_uuid_val = _decode_wire(service_id, "svc")
        stmt = stmt.where(pg_table.c.service_id == svc_uuid_val)

    if q is not None and q.strip() != "":
        # ILIKE substring match on action — UX-B inline search.
        # .ilike(f"%{...}%") passes a *value* bound at execution time;
        # SQLAlchemy parameterises it — this is the safe idiom.
        stmt = stmt.where(pg_table.c.action.ilike(f"%{_escape_like(q.strip())}%"))

    result = await session.execute(stmt)
    rows = result.fetchall()

    permissions = [
        {
            "id": db_uuid_to_wire(row.id, "perm"),
            "tenant_id": str(row.tenant_id),
            "agent_id": db_uuid_to_wire(row.agent_id, "agent"),
            "service_id": db_uuid_to_wire(row.service_id, "svc") if row.service_id else None,
            "action": row.action,
            "constraints": row.constraints if isinstance(row.constraints, dict) else (
                json.loads(row.constraints) if row.constraints else None
            ),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "created_by": str(row.created_by) if row.created_by else None,
            # UX-BL1: denormalised display fields from services/agents JOIN
            "service_name": row.service_name,
            "service_slug": row.service_slug,
            "agent_name": row.agent_name,
        }
        for row in rows
    ]
    return JSONResponse({"permissions": permissions})


@router.post("", status_code=201)
async def grant_permission(
    tenant_id: UUID,
    agent_id: str,
    body: PermissionGrantRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Grant a permission from an agent to a service action.

    - Idempotent: same (agent, service, action, constraints) → 200.
    - Conflict: same (agent, service, action), different constraints → 409.
    - Cross-tenant: agent not in tenant → 404.

    Source: T-1.4.2; ADR-0008; ADR-0014.7; ADR-0016.4; ADR-0017.11.
    """
    # 1. Decode wire-prefixed agent_id → UUID — ADR-0017.11; R8
    try:
        agent_uuid = _decode_agent_wire_id(agent_id, "agent_")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
        )

    # 2. Set tenant context — RLS applies — ADR-0008
    await set_tenant_context(session, tenant_id)

    # 3. Verify agent exists in this tenant (cross-tenant → 404)
    agent_result = await session.execute(
        text("SELECT id FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": agent_uuid, "tid": str(tenant_id)},
    )
    if agent_result.fetchone() is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Agent not found"},
        )

    # 4. Resolve wire-prefixed service_id to DB UUID — ADR-0017.11; R12
    #    Uses the shared _resolve_service_uuid helper which tries _wire_id_to_uuid first
    #    (works directly for post-R12 services), then falls back to the audit_events
    #    lookup for pre-R12 services whose uuid4() didn't match the ULID bits.
    try:
        svc_uuid = await _resolve_service_uuid(session, tenant_id, body.service_id)
    except Exception as exc:
        if "not_found" in str(exc):
            return JSONResponse(
                status_code=404,
                content={"mintkey:code": "not_found", "title": "Service not found"},
            )
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_service_id", "title": "Invalid service_id"},
        )

    # 5. Default constraints to {} when caller omits field — R11a
    constraints_dict = (
        body.constraints.model_dump(exclude_none=True) if body.constraints else {}
    )

    # 6. Check for existing grant with same (agent_uuid, svc_uuid, action)
    existing_result = await session.execute(
        text(
            "SELECT id, constraints FROM permission_grants"
            " WHERE agent_id = :aid AND service_id = :sid AND action = :action"
            "   AND tenant_id = :tid"
        ),
        {
            "aid": agent_uuid,
            "sid": svc_uuid,
            "action": body.action,
            "tid": str(tenant_id),
        },
    )
    existing = existing_result.fetchone()

    if existing is not None:
        # Normalize stored constraints for comparison
        stored_raw = existing.constraints
        if isinstance(stored_raw, str):
            stored = json.loads(stored_raw)
        elif stored_raw is None:
            stored = None
        else:
            stored = stored_raw

        if stored == constraints_dict:
            # Idempotent — same params, return existing
            return JSONResponse(
                status_code=200,
                content={
                    "id": str(existing.id),
                    "agent_id": agent_id,
                    "service_id": body.service_id,
                    "action": body.action,
                    "constraints": constraints_dict,
                },
            )
        else:
            # Conflict — different constraints
            return JSONResponse(
                status_code=409,
                content={
                    "mintkey:code": "permission_constraints_conflict",
                    "title": "A permission grant with different constraints already exists",
                },
            )

    # 7. Generate perm_ ULID ID — ADR-0017.11
    # Derive internal DB UUID from ULID bits — same pattern as agents/services (#13).
    perm_id = _new_perm_id()
    _perm_tail = perm_id[len("perm_"):]
    _perm_val = 0
    for _ch in _perm_tail.upper():
        _perm_val = (_perm_val << 5) | _CROCKFORD.index(_ch)
    _perm_val &= (1 << 128) - 1
    internal_id = uuid.UUID(int=_perm_val)
    now = datetime.now(timezone.utc)

    # 8. INSERT permission_grants — bind svc_uuid (decoded UUID), not raw wire-form
    granted_by = body.granted_by or agent_uuid
    await session.execute(
        text(
            "INSERT INTO permission_grants"
            " (id, tenant_id, agent_id, service_id, action, constraints, created_at, created_by)"
            " VALUES"
            " (:id, :tenant_id, :agent_id, :service_id, :action, CAST(:constraints AS jsonb), :created_at, :created_by)"
        ),
        {
            "id": str(internal_id),
            "tenant_id": str(tenant_id),
            "agent_id": agent_uuid,
            "service_id": svc_uuid,
            "action": body.action,
            "constraints": json.dumps(constraints_dict),
            "created_at": now,
            "created_by": granted_by,
        },
    )

    # 9. Emit audit event — ADR-0014.7
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="agent.permission.granted",
        actor_id=None,
        actor_type="operator",
        target_id=internal_id,
        target_type="permission",
        payload={
            "perm_id": perm_id,
            "agent_id": agent_id,
            "service_id": body.service_id,
            "action": body.action,
            "constraints": constraints_dict,
        },
    )

    # 10. Return 201
    return JSONResponse(
        status_code=201,
        content={
            "id": perm_id,
            "tenant_id": str(tenant_id),
            "agent_id": agent_id,
            "service_id": body.service_id,
            "action": body.action,
            "constraints": constraints_dict,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )


@router.delete("/{permission_id}", status_code=204)
async def revoke_permission(
    tenant_id: UUID,
    agent_id: str,
    permission_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """
    Revoke a permission grant.

    Emits audit agent.permission.revoked and NOTIFY mintkey:agent.

    Source: T-1.4.2; ADR-0008; ADR-0014.7; ADR-0014.1.
    """
    # 1. Set tenant context — ADR-0008
    await set_tenant_context(session, tenant_id)

    # Decode wire-form IDs → DB UUIDs — ADR-0017.11; #13
    from admin_api.utils.wire_ids import wire_to_db_uuid as _decode_wire  # noqa: PLC0415
    try:
        perm_db_id = _decode_wire(permission_id, "perm")
        agent_db_id = _decode_agent_wire_id(agent_id, "agent_") if agent_id.startswith("agent_") else agent_id
    except ValueError:
        return Response(status_code=422)

    # 2. DELETE (RLS ensures tenant isolation)
    await session.execute(
        text(
            "DELETE FROM permission_grants"
            " WHERE id = :pid AND agent_id = :aid AND tenant_id = :tid"
        ),
        {"pid": perm_db_id, "aid": agent_db_id, "tid": str(tenant_id)},
    )

    # 3. Emit audit event — ADR-0014.7
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="agent.permission.revoked",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="permission",
        payload={"permission_id": permission_id, "agent_id": agent_id},
    )

    # 4. NOTIFY global channel — ADR-0014.1
    await notify_change(
        session,
        "mintkey:agent",
        {
            "event": "agent.permission.revoked",
            "tenant_id": str(tenant_id),
            "agent_id": agent_id,
            "permission_id": permission_id,
        },
    )

    return Response(status_code=204)
