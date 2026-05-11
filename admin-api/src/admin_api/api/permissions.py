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
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(prefix="/v1/tenants/{tenant_id}/agents/{agent_id}/permissions")

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
# Endpoints
# ---------------------------------------------------------------------------


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
    # 1. Set tenant context — RLS applies — ADR-0008
    await set_tenant_context(session, tenant_id)

    # 2. Verify agent exists in this tenant (cross-tenant → 404)
    agent_result = await session.execute(
        text("SELECT id FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": agent_id, "tid": str(tenant_id)},
    )
    if agent_result.fetchone() is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Agent not found"},
        )

    # 3. Check for existing grant with same (agent_id, service_id, action)
    existing_result = await session.execute(
        text(
            "SELECT id, constraints FROM permission_grants"
            " WHERE agent_id = :aid AND service_id = :sid AND action = :action"
            "   AND tenant_id = :tid"
        ),
        {
            "aid": agent_id,
            "sid": body.service_id,
            "action": body.action,
            "tid": str(tenant_id),
        },
    )
    existing = existing_result.fetchone()

    constraints_dict = (
        body.constraints.model_dump(exclude_none=True) if body.constraints else None
    )

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
                    "id": existing.id,
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

    # 4. Generate perm_ ULID ID — ADR-0017.11
    perm_id = _new_perm_id()
    internal_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # 5. INSERT permission_grants
    granted_by = body.granted_by or agent_id
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
            "agent_id": agent_id,
            "service_id": body.service_id,
            "action": body.action,
            "constraints": json.dumps(constraints_dict) if constraints_dict is not None else None,
            "created_at": now,
            "created_by": granted_by,
        },
    )

    # 6. Emit audit event — ADR-0014.7
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

    # 7. Return 201
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

    # 2. DELETE (RLS ensures tenant isolation)
    await session.execute(
        text(
            "DELETE FROM permission_grants"
            " WHERE id = :pid AND agent_id = :aid AND tenant_id = :tid"
        ),
        {"pid": permission_id, "aid": agent_id, "tid": str(tenant_id)},
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
