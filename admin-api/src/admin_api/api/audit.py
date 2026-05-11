"""
Audit log API endpoint.

GET /v1/tenants/{tenant_id}/audit — list audit events with cursor pagination and filters.

Architecture constraints:
  - Tenant context via set_tenant_context (bound parameters, RLS) — ADR-0008.
  - All SQL uses bound parameters — no f-string interpolation — ADR-0008, T-1.0.15.
  - Cursor-based pagination: WHERE id > :after ORDER BY id ASC LIMIT :limit.
  - audit_events columns: id, event_type, tenant_id, payload (jsonb), hash, prev_hash, created_at.

Source: T-1.7.1; ADR-0008; ADR-0014.7; ADR-0017.11.
"""
from __future__ import annotations

from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.deps import get_db_session
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(prefix="/v1/tenants/{tenant_id}/audit")


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Map an audit_events row to the wire representation."""
    return {
        "id": row.id,
        "event_type": row.event_type,
        "tenant_id": str(row.tenant_id),
        "payload": row.payload if isinstance(row.payload, dict) else {},
        "created_at": row.at.isoformat() if row.at else None,
    }


@router.get("")
async def list_audit_events(
    tenant_id: UUID,
    agent_id: Optional[str] = None,
    service_id: Optional[str] = None,
    event_type: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    after: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List audit events for a tenant with optional filters and cursor pagination.

    Query parameters:
      agent_id   — filter by agent ID in payload
      service_id — filter by service ID in payload
      event_type — exact match on event_type column
      from_ts    — ISO8601 lower bound on created_at
      to_ts      — ISO8601 upper bound on created_at
      after      — cursor: return events with id > after (opaque event id)
      limit      — max events per page (default 50)

    Returns {"events": [...], "next_cursor": "<id> | null"}.
    next_cursor is the id of the last event when limit rows are returned,
    otherwise null.

    Source: T-1.7.1; ADR-0008; ADR-0014.7.
    """
    await set_tenant_context(session, tenant_id)

    # All filters expressed as optional IS NULL guards so the SQL is a
    # single string literal — no concatenation or f-strings (ADR-0008 / T-1.0.15).
    result = await session.execute(
        text(
            "SELECT id, event_type, tenant_id, payload, hash, prev_hash, at"
            " FROM audit_events"
            " WHERE tenant_id = :tenant_id"
            " AND (:after IS NULL OR id > :after)"
            " AND (:event_type IS NULL OR event_type = :event_type)"
            " AND (:from_ts IS NULL OR at >= CAST(:from_ts AS timestamptz))"
            " AND (:to_ts IS NULL OR at <= CAST(:to_ts AS timestamptz))"
            " AND (:agent_id IS NULL OR payload->>'agent_id' = :agent_id)"
            " AND (:service_id IS NULL OR payload->>'service_id' = :service_id)"
            " ORDER BY id ASC"
            " LIMIT :limit"
        ),
        {
            "tenant_id": str(tenant_id),
            "after": after,
            "event_type": event_type,
            "from_ts": from_ts,
            "to_ts": to_ts,
            "agent_id": agent_id,
            "service_id": service_id,
            "limit": limit,
        },
    )
    rows = result.fetchall()

    events = [_row_to_dict(r) for r in rows]
    next_cursor = rows[-1].id if len(rows) == limit else None

    return JSONResponse({"events": events, "next_cursor": next_cursor})
