"""
Discovery cache with tenant-scoped invalidation.

Stores list_services results keyed by (tenant_id, agent_id) with TTL-based
expiry. invalidate(tenant_id) removes all entries for the given tenant
without affecting other tenants.

Source: T-1.5.6; ADR-0014.1.
"""
from __future__ import annotations

import asyncio
import time
from typing import Dict, List, Optional, Tuple


class DiscoveryCache:
    """In-memory TTL cache for discovery results, scoped per (tenant_id, agent_id).

    Thread-safe for async access via asyncio.Lock.
    """

    def __init__(self, ttl_seconds: int = 300) -> None:
        self._ttl = ttl_seconds
        # key: (tenant_id, agent_id) → (value, expires_at)
        self._store: Dict[Tuple[str, str], Tuple[list, float]] = {}
        self._lock = asyncio.Lock()

    def get(self, tenant_id: str, agent_id: str) -> Optional[List]:
        """Return cached value or None if absent / expired."""
        entry = self._store.get((tenant_id, agent_id))
        if entry is None:
            return None
        value, expires_at = entry
        if time.monotonic() >= expires_at:
            del self._store[(tenant_id, agent_id)]
            return None
        return value

    def set(self, tenant_id: str, agent_id: str, value: list) -> None:
        """Store value under (tenant_id, agent_id) with TTL."""
        expires_at = time.monotonic() + self._ttl
        self._store[(tenant_id, agent_id)] = (value, expires_at)

    def invalidate(self, tenant_id: str) -> None:
        """Remove all cache entries for the given tenant."""
        keys_to_remove = [k for k in self._store if k[0] == tenant_id]
        for k in keys_to_remove:
            del self._store[k]
