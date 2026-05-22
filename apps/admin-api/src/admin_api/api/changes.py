"""
Change channel reconciliation endpoint.

GET /v1/changes?since=<event_id> — returns change events after cursor.
If since cursor is unknown/expired → 410 Gone per ADR-0017.7.

Architecture constraints:
  - since=unknown → 410 with mintkey:code=since_unknown + oldest_known_event_id — ADR-0017.7.
  - Never silently start from the beginning — ADR-0017.7.
  - Bound parameters only — ADR-0008.

Source: T-1.9.3; ADR-0010; ADR-0017.7.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.deps import get_db_session

router = APIRouter()


@router.get("/v1/changes")
async def get_changes(
    since: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Return change events after the given cursor.

    If since is provided but unknown/expired, return 410 Gone with
    mintkey:code=since_unknown and oldest_known_event_id — ADR-0017.7.

    Source: T-1.9.3; ADR-0010; ADR-0017.7.
    """
    if since is not None:
        result = await session.execute(
            text("SELECT id FROM audit_events WHERE id = :since"),
            {"since": since},
        )
        if result.fetchone() is None:
            oldest = await session.execute(
                text("SELECT id FROM audit_events ORDER BY at ASC LIMIT 1")
            )
            oldest_row = oldest.fetchone()
            oldest_known = str(oldest_row.id) if oldest_row else None
            return JSONResponse(
                status_code=410,
                content={
                    "code": "mintkey:since_unknown",
                    "oldest_known_event_id": oldest_known,
                },
            )

    # Return events after cursor (stub: empty list — full streaming deferred to T-1.2.x)
    return JSONResponse({"events": [], "next_cursor": None})
