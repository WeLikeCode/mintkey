"""
pg_notify publisher — fires LISTEN/NOTIFY change events.

Channel names are global (not per-tenant). The tenant filter lives inside
the consumer wrapper — ADR-0014.1.

All SQL uses bound parameters. Never uses f-strings — ADR-0008, T-1.0.15.

Source: design §4; ADR-0008; ADR-0014.1.
"""
from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def notify_change(session: AsyncSession, channel: str, payload: dict) -> None:
    """
    Fire pg_notify with bound parameters. Never uses f-strings.

    Source: ADR-0008 (bound parameters); ADR-0014.1 (global channels).
    """
    await session.execute(
        text("SELECT pg_notify(:channel, :payload)"),
        {"channel": channel, "payload": json.dumps(payload)},
    )
