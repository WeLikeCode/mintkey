"""
Budget status and reset endpoints.

GET  /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget       — current budget status
POST /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget/reset — manual reset

Architecture constraints:
  - Budget config lives in permission_grants.constraints.budget — FR-1; design §2.
  - Period boundaries UTC-aligned — design §3.
  - Audit emit on every state change — ADR-0014.7; FR-7.
  - Global channel "mintkey:agent" — ADR-0014.1; FR-10.
  - Wire IDs use perm_ prefix — ADR-0017.11.
  - Tenant isolation via RLS + explicit tenant_id — ADR-0008.

Source: T-BUD-2.3; T-BUD-2.4; FR-5, FR-9; design §5.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.api.permissions import _budget_period_bounds
from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from admin_api.utils.wire_ids import wire_to_db_uuid
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{permission_id}/budget"
)


# ---------------------------------------------------------------------------
# GET /budget — current budget status (FR-9; design §5; T-BUD-2.3)
# ---------------------------------------------------------------------------


@router.get("")
async def get_budget_status(
    tenant_id: UUID,
    agent_id: str,
    permission_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Return current-period budget status for a permission grant.

    - 404 if grant has no budget constraint.
    - Queries budget_counters for the row where now() BETWEEN period_start AND period_end.

    Source: T-BUD-2.3; FR-9; design §5.
    """
    # 1. Decode wire-form permission_id → DB UUID — ADR-0017.11
    perm_db_id = wire_to_db_uuid(permission_id, "perm")

    # 2. Set tenant context — ADR-0008
    await set_tenant_context(session, tenant_id)

    # 3. Fetch the grant to read budget config from constraints
    grant_result = await session.execute(
        text(
            "SELECT id, constraints FROM permission_grants"
            " WHERE id = :pid AND tenant_id = :tid"
        ),
        {"pid": perm_db_id, "tid": str(tenant_id)},
    )
    grant_row = grant_result.fetchone()
    if grant_row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Permission grant not found"},
        )

    # Parse constraints to extract budget config
    constraints_raw = grant_row.constraints
    if isinstance(constraints_raw, str):
        constraints = json.loads(constraints_raw)
    elif constraints_raw is None:
        constraints = {}
    else:
        constraints = constraints_raw

    budget_cfg = constraints.get("budget")
    if not budget_cfg:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "no_budget", "title": "No budget configured for this grant"},
        )

    # 4. Query budget_counters for the current period row
    now = datetime.now(timezone.utc)
    counter_result = await session.execute(
        text(
            "SELECT ceiling, used, period_start, period_end"
            " FROM budget_counters"
            " WHERE permission_id = :pid"
            "   AND period_start <= :now AND period_end > :now"
            " ORDER BY period_start DESC"
            " LIMIT 1"
        ),
        {"pid": perm_db_id, "now": now},
    )
    counter_row = counter_result.fetchone()

    if counter_row is not None:
        ceiling = counter_row.ceiling
        used = counter_row.used
        period_start = counter_row.period_start
        period_end = counter_row.period_end
    else:
        # No counter row yet for this period — budget exists in config but
        # no requests have been made. Return fresh status.
        ceiling = budget_cfg["ceiling"]
        used = 0
        period_start, period_end = _budget_period_bounds(budget_cfg["period"], now)

    remaining = max(0, ceiling - used)
    alert_thresholds = budget_cfg.get("alert_thresholds", [50, 80, 100])

    return JSONResponse(
        status_code=200,
        content={
            "ceiling": ceiling,
            "period": budget_cfg["period"],
            "used": used,
            "remaining": remaining,
            "period_start": period_start.isoformat() if hasattr(period_start, "isoformat") else str(period_start),
            "period_end": period_end.isoformat() if hasattr(period_end, "isoformat") else str(period_end),
            "alert_thresholds": alert_thresholds,
        },
    )


# ---------------------------------------------------------------------------
# POST /budget/reset — manual reset (FR-5; design §5; T-BUD-2.4)
# ---------------------------------------------------------------------------


@router.post("/reset")
async def reset_budget(
    tenant_id: UUID,
    agent_id: str,
    permission_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Reset budget for a permission grant mid-period.

    Creates a new counter row with used=0 for the current period remainder.
    Emits budget.reset audit event.
    Fires change-channel notification.
    Returns the new BudgetStatus.

    Source: T-BUD-2.4; FR-5; design §5.
    """
    # 1. Decode wire-form permission_id → DB UUID — ADR-0017.11
    perm_db_id = wire_to_db_uuid(permission_id, "perm")

    # 2. Set tenant context — ADR-0008
    await set_tenant_context(session, tenant_id)

    # 3. Fetch the grant to read budget config from constraints
    grant_result = await session.execute(
        text(
            "SELECT id, constraints FROM permission_grants"
            " WHERE id = :pid AND tenant_id = :tid"
        ),
        {"pid": perm_db_id, "tid": str(tenant_id)},
    )
    grant_row = grant_result.fetchone()
    if grant_row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Permission grant not found"},
        )

    # Parse constraints to extract budget config
    constraints_raw = grant_row.constraints
    if isinstance(constraints_raw, str):
        constraints = json.loads(constraints_raw)
    elif constraints_raw is None:
        constraints = {}
    else:
        constraints = constraints_raw

    budget_cfg = constraints.get("budget")
    if not budget_cfg:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "no_budget", "title": "No budget configured for this grant"},
        )

    # 4. Read the current counter row (to capture previous_used for audit)
    now = datetime.now(timezone.utc)
    current_counter = await session.execute(
        text(
            "SELECT ceiling, used, period_start, period_end"
            " FROM budget_counters"
            " WHERE permission_id = :pid"
            "   AND period_start <= :now AND period_end > :now"
            " ORDER BY period_start DESC"
            " LIMIT 1"
        ),
        {"pid": perm_db_id, "now": now},
    )
    current_row = current_counter.fetchone()
    previous_used = current_row.used if current_row else 0
    previous_ceiling = current_row.ceiling if current_row else budget_cfg["ceiling"]

    # 5. Compute period bounds for the reset row
    #    The reset creates a new counter for the CURRENT period remainder
    #    (same period_end as the current period boundary).
    period_start_new = now  # reset starts now
    _, period_end = _budget_period_bounds(budget_cfg["period"], now)
    ceiling = budget_cfg["ceiling"]

    # 6. Upsert new counter row with used=0
    #    Use ON CONFLICT to handle edge case where reset is called multiple times
    #    within the same timestamp (period_start). In practice this creates a new
    #    row because period_start=now is unique per invocation.
    await session.execute(
        text(
            "INSERT INTO budget_counters"
            " (permission_id, period_start, period_end, ceiling, used, tenant_id)"
            " VALUES (:pid, :ps, :pe, :ceiling, 0, :tid)"
            " ON CONFLICT (permission_id, period_start) DO UPDATE"
            " SET used = 0, ceiling = :ceiling, period_end = :pe"
        ),
        {
            "pid": perm_db_id,
            "ps": period_start_new,
            "pe": period_end,
            "ceiling": ceiling,
            "tid": str(tenant_id),
        },
    )

    # 7. Emit budget.reset audit event — ADR-0014.7; FR-7
    perm_uuid = uuid.UUID(perm_db_id) if isinstance(perm_db_id, str) else perm_db_id
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="budget.reset",
        actor_id=None,
        actor_type="operator",
        target_id=perm_uuid,
        target_type="permission",
        payload={
            "permission_id": permission_id,
            "previous_used": previous_used,
            "previous_ceiling": previous_ceiling,
            "new_period_start": period_start_new.isoformat(),
        },
    )

    # 8. Fire change-channel notification — ADR-0014.1; FR-10
    await notify_change(
        session,
        "mintkey:agent",
        {
            "event_type": "budget.config_updated",
            "tenant_id": str(tenant_id),
            "target_id": permission_id,
            "payload": {
                "ceiling": ceiling,
                "period": budget_cfg["period"],
                "reset": True,
            },
            "at": now.isoformat(),
        },
    )

    # 9. Return new BudgetStatus
    remaining = ceiling  # used=0 after reset
    alert_thresholds = budget_cfg.get("alert_thresholds", [50, 80, 100])

    return JSONResponse(
        status_code=200,
        content={
            "ceiling": ceiling,
            "period": budget_cfg["period"],
            "used": 0,
            "remaining": remaining,
            "period_start": period_start_new.isoformat(),
            "period_end": period_end.isoformat() if hasattr(period_end, "isoformat") else str(period_end),
            "alert_thresholds": alert_thresholds,
        },
    )
