"""
LISTEN/NOTIFY subscriber for MCP Server.

Subscribes to global channels: mintkey:service, mintkey:agent
Per ADR-0014.1: channels are global (not per-tenant). The tenant filter
lives inside the consumer (this module) — extracted from the payload.

On mintkey:service → invalidates discovery cache for affected tenant.
On mintkey:agent   → if event_type == "agent.revoked", adds agent_id
                     to revoked_agents set (checked on every tool call).

Source: ADR-0014.1; T-1.5.6.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional, Set

import asyncpg

_log = logging.getLogger(__name__)

_CHANNEL_SERVICE = "mintkey:service"
_CHANNEL_AGENT = "mintkey:agent"


class ChangeSubscriber:
    """
    Subscribes to global Postgres LISTEN/NOTIFY channels and reacts:

    * mintkey:service → invalidate discovery cache for the affected tenant.
    * mintkey:agent   → add agent_id to revoked_agents on agent.revoked events.

    Usage::

        subscriber = ChangeSubscriber(dsn, discovery_cache, revoked_agents)
        await subscriber.start()   # starts background loop
        ...
        await subscriber.stop()
    """

    def __init__(
        self,
        dsn: str,
        discovery_cache: object,
        revoked_agents: Set[str],
    ) -> None:
        self._dsn = dsn
        self._discovery_cache = discovery_cache
        self._revoked_agents = revoked_agents
        self._conn: Optional[asyncpg.Connection] = None
        self._task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        """Connect to Postgres, register listeners, start the keep-alive loop."""
        self._conn = await asyncpg.connect(self._dsn)
        await self._conn.add_listener(_CHANNEL_SERVICE, self._on_service_change)
        await self._conn.add_listener(_CHANNEL_AGENT, self._on_agent_change)
        self._task = asyncio.get_event_loop().create_task(self._run())
        _log.info(
            "ChangeSubscriber started; listening on %s, %s",
            _CHANNEL_SERVICE,
            _CHANNEL_AGENT,
        )

    async def stop(self) -> None:
        """Remove listeners, cancel keep-alive task, close connection."""
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._conn is not None:
            try:
                await self._conn.remove_listener(_CHANNEL_SERVICE, self._on_service_change)
                await self._conn.remove_listener(_CHANNEL_AGENT, self._on_agent_change)
                await self._conn.close()
            except Exception:
                _log.warning("Error closing subscriber connection", exc_info=True)
            self._conn = None

        _log.info("ChangeSubscriber stopped")

    async def _run(self) -> None:
        """Keep the connection alive (asyncpg delivers notifications via the event loop)."""
        try:
            while True:
                await asyncio.sleep(10)
        except asyncio.CancelledError:
            pass

    def _on_service_change(
        self,
        conn: object,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """
        Called by asyncpg on mintkey:service notifications.

        Parses JSON payload and invalidates discovery cache for the affected tenant.
        Bad JSON is logged and silently dropped — no exception propagated to asyncpg.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _log.warning(
                "ChangeSubscriber: malformed JSON on %s channel; payload=%r",
                channel,
                payload,
            )
            return

        tenant_id = data.get("tenant_id")
        if tenant_id:
            self._discovery_cache.invalidate(tenant_id)
            _log.debug(
                "ChangeSubscriber: invalidated discovery cache for tenant=%s",
                tenant_id,
            )
        else:
            _log.warning(
                "ChangeSubscriber: service change payload missing tenant_id; data=%r",
                data,
            )

    def _on_agent_change(
        self,
        conn: object,
        pid: int,
        channel: str,
        payload: str,
    ) -> None:
        """
        Called by asyncpg on mintkey:agent notifications.

        On event_type=agent.revoked: adds agent_id to revoked_agents set.
        Other event types are ignored.
        Bad JSON is logged and silently dropped.
        """
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            _log.warning(
                "ChangeSubscriber: malformed JSON on %s channel; payload=%r",
                channel,
                payload,
            )
            return

        event_type = data.get("event_type")
        if event_type == "agent.revoked":
            agent_id = data.get("agent_id")
            if agent_id:
                self._revoked_agents.add(agent_id)
                _log.info(
                    "ChangeSubscriber: agent revoked; agent_id=%s",
                    agent_id,
                )
            else:
                _log.warning(
                    "ChangeSubscriber: agent.revoked payload missing agent_id; data=%r",
                    data,
                )
