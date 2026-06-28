"""
Budget consumers aggregation endpoint.

GET /v1/tenants/{tenant_id}/budget-consumers

Returns a JSON array of budget consumer records with consumption data.
Server-side join across permission_grants, budget_counters, agents, services.
Computes consumption_percentage = round((used / ceiling) * 100).
RLS-scoped via set_tenant_context.

Source: design §Components → Admin-API: Aggregation Endpoint;
        requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.deps import get_db_session
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(prefix="/v1/tenants/{tenant_id}/budget-consumers")


@router.get("")
async def list_budget_consumers(
    tenant_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """List all budget-configured permission grants with consumption data.

    Performs a server-side join across permission_grants, budget_counters,
    agents, and services. Results are sorted: exhausted first, then by
    consumption percentage descending.

    Source: design §Components; requirements 2.1–2.6.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text("""
            SELECT
                pg.id AS permission_id,
                a.id AS agent_id,
                a.name AS agent_name,
                s.id AS service_id,
                s.name AS service_name,
                (pg.constraints->'budget'->>'ceiling')::int AS ceiling,
                pg.constraints->'budget'->>'period' AS period,
                COALESCE(bc.used, 0) AS used,
                COALESCE(
                    (SELECT COUNT(*) FROM audit_events ae
                     WHERE ae.event_type = 'token.issued'
                       AND ae.payload->>'permission_id' = pg.id::text
                       AND ae.created_at > NOW() - INTERVAL '30 minutes'
                       AND ae.tenant_id = :tid),
                    0
                ) AS requests_last_30_min,
                bc.period_start,
                bc.period_end
            FROM permission_grants pg
            JOIN agents a ON a.id = pg.agent_id AND a.tenant_id = :tid
            JOIN services s ON s.id = pg.service_id AND s.tenant_id = :tid
            LEFT JOIN budget_counters bc ON bc.permission_id = pg.id
                AND NOW() BETWEEN bc.period_start AND bc.period_end
            WHERE pg.tenant_id = :tid
              AND pg.constraints->'budget' IS NOT NULL
              AND (pg.constraints->'budget'->>'ceiling') IS NOT NULL
            ORDER BY
                CASE WHEN COALESCE(bc.used, 0) >= (pg.constraints->'budget'->>'ceiling')::int
                     THEN 0 ELSE 1 END,
                COALESCE(bc.used, 0)::float
                    / NULLIF((pg.constraints->'budget'->>'ceiling')::int, 0) DESC NULLS LAST
        """),
        {"tid": str(tenant_id)},
    )

    rows = result.fetchall()

    records = []
    for row in rows:
        ceiling = row.ceiling
        used = row.used
        consumption_percentage = round((used / ceiling) * 100) if ceiling > 0 else 0

        period_start = row.period_start
        period_end = row.period_end

        records.append(
            {
                "permission_id": str(row.permission_id),
                "agent_id": str(row.agent_id),
                "agent_name": row.agent_name,
                "service_id": str(row.service_id),
                "service_name": row.service_name,
                "consumption_percentage": consumption_percentage,
                "used": used,
                "ceiling": ceiling,
                "period": row.period,
                "period_start": period_start.isoformat() if period_start else None,
                "period_end": period_end.isoformat() if period_end else None,
                "requests_last_30_min": row.requests_last_30_min,
            }
        )

    return JSONResponse(status_code=200, content=records)
