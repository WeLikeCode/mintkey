"""
LISTEN/NOTIFY change-channel client stub.

Thin Python wrapper for asyncpg LISTEN. Channels are global (not per-tenant) —
per ADR-0014.1, the tenant filter lives inside the wrapper, not in the channel
name. Full asyncpg wiring is deferred to T-1.2.x.

Source: design §1; ADR-0014.1 (global channels, filter in wrapper).
"""
from __future__ import annotations

import logging
from typing import Callable

logger = logging.getLogger(__name__)

# Global channels — ADR-0014.1: channel names are global; filter is in the wrapper.
GLOBAL_CHANNELS = ["mintkey:service", "mintkey:credential", "mintkey:agent"]


class ChangesClient:
    """
    Client for Postgres LISTEN/NOTIFY change events.

    tenant_scope controls which tenant events the handler receives:
      - "*"            — all tenants (platform-admin use; ADR-0014.1)
      - list[str]      — specific tenant IDs

    Raises ValueError if tenant_scope is empty.
    """

    def __init__(self, dsn: str, tenant_scope: str | list[str]) -> None:
        # Guard: tenant_scope must not be empty — ADR-0014.1
        if tenant_scope == "" or tenant_scope == []:
            raise ValueError("tenant_scope is required")
        self._dsn = dsn
        self._tenant_scope = tenant_scope

    async def start(self, handler: Callable[[str, str], None]) -> None:
        """
        Connect and LISTEN on all global channels.

        Stub implementation: logs intent and returns immediately.
        Full asyncpg wiring is implemented in T-1.2.x.
        """
        logger.info(
            "ChangesClient.start called (stub) — full pgx wiring deferred to T-1.2.x",
            extra={"channels": GLOBAL_CHANNELS, "tenant_scope": self._tenant_scope},
        )
