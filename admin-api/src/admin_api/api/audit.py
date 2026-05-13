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

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.deps import get_db_session
from mintkey_models.tenant_ctx import set_tenant_context


def _parse_ts(ts_str: Optional[str]) -> Optional[datetime]:
    """
    Parse an ISO 8601 / RFC 3339 timestamp string into a timezone-aware datetime.
    Returns None if ts_str is None. The resulting datetime is UTC.
    """
    if ts_str is None:
        return None
    # Handle trailing Z → +00:00
    ts_str = ts_str.replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(ts_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None

router = APIRouter(prefix="/v1/tenants/{tenant_id}/audit")


def _row_to_dict(row: Any) -> dict[str, Any]:
    """Map an audit_events row to the wire representation."""
    return {
        "id": str(row.id),
        "event_type": row.event_type,
        "tenant_id": str(row.tenant_id),
        "payload": row.payload if isinstance(row.payload, dict) else {},
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input cannot glob-match unexpectedly."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
async def list_audit_events(
    tenant_id: UUID,
    q: Optional[str] = None,
    agent_id: Optional[str] = None,
    service_id: Optional[str] = None,
    event_type: Optional[str] = None,
    actor_id: Optional[str] = None,
    target_id: Optional[str] = None,
    from_ts: Optional[str] = None,
    to_ts: Optional[str] = None,
    after: Optional[str] = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List audit events for a tenant with optional filters and cursor pagination.

    Query parameters:
      q          — substring search on event_type (case-insensitive)
      agent_id   — filter by agent ID in payload
      service_id — filter by service ID in payload
      event_type — exact match on event_type column
      actor_id   — exact match on actor_id column
      target_id  — exact match on target_id column (UUID string)
      from_ts    — ISO8601 inclusive lower bound on created_at
      to_ts      — ISO8601 exclusive upper bound on created_at
      after      — cursor: return events with id > after (opaque event id)
      limit      — max events per page (default 50)

    Returns {"events": [...], "next_cursor": "<id> | null"}.
    next_cursor is the id of the last event when limit rows are returned,
    otherwise null.

    Source: T-1.7.1; ADR-0008; ADR-0014.7.
    """
    await set_tenant_context(session, tenant_id)

    # q param: ILIKE on event_type for searchability.
    # All other filters expressed as optional IS NULL guards — ADR-0008 / T-1.0.15.
    q_pattern = f"%{_escape_like(q)}%" if q is not None else None
    from_dt = _parse_ts(from_ts)
    to_dt = _parse_ts(to_ts)

    result = await session.execute(
        text(
            "SELECT id, event_type, tenant_id, payload, hash, prev_hash, at AS created_at"
            " FROM audit_events"
            " WHERE tenant_id = :tenant_id"
            " AND (CAST(:after AS uuid) IS NULL OR id > CAST(:after AS uuid))"
            " AND (CAST(:event_type AS text) IS NULL OR event_type = CAST(:event_type AS text))"
            " AND (CAST(:q_pattern AS text) IS NULL OR event_type ILIKE CAST(:q_pattern AS text) ESCAPE '\\')"
            " AND (CAST(:from_dt AS timestamptz) IS NULL OR at >= CAST(:from_dt AS timestamptz))"
            " AND (CAST(:to_dt AS timestamptz) IS NULL OR at < CAST(:to_dt AS timestamptz))"
            " AND (CAST(:agent_id AS text) IS NULL OR payload->>'agent_id' = CAST(:agent_id AS text))"
            " AND (CAST(:service_id AS text) IS NULL OR payload->>'service_id' = CAST(:service_id AS text))"
            " AND (CAST(:actor_id AS text) IS NULL OR CAST(actor_id AS text) = CAST(:actor_id AS text))"
            " AND (CAST(:target_id AS text) IS NULL OR CAST(target_id AS text) = CAST(:target_id AS text))"
            " ORDER BY id ASC"
            " LIMIT :limit"
        ),
        {
            "tenant_id": str(tenant_id),
            "after": after,
            "event_type": event_type,
            "q_pattern": q_pattern,
            "from_dt": from_dt,
            "to_dt": to_dt,
            "agent_id": agent_id,
            "service_id": service_id,
            "actor_id": actor_id,
            "target_id": target_id,
            "limit": limit,
        },
    )
    rows = result.fetchall()

    events = [_row_to_dict(r) for r in rows]
    next_cursor = str(rows[-1].id) if len(rows) == limit else None

    return JSONResponse({"events": events, "next_cursor": next_cursor})
