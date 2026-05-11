"""
Vault Adapter client — in-memory implementation.
Full gRPC client wired in T-1.3.1 integration phase.

Source: ADR-0011 (Go vault-adapter, gRPC interface); T-1.3.2.
"""
from __future__ import annotations

import time
import uuid


class VaultAdapterClient:
    """
    In-memory credential store keyed by (tenant_id, service_id).

    Plaintext is held only in this process — never logged or returned
    via the API. ADR-0014.4, S-SEC-1.
    """

    def __init__(self) -> None:
        # key=(tenant_id, service_id) → {auth_scheme, plaintext, key_version}
        self._store: dict = {}

    async def put_credential(
        self,
        tenant_id: str,
        service_id: str,
        auth_scheme: str,
        plaintext: str,
    ) -> dict:
        """
        Store a credential in the vault. Returns metadata (NO plaintext).

        Source: ADR-0011; ADR-0014.4 (no plaintext caching or logging).
        """
        key_version = self._store.get((tenant_id, service_id), {}).get("key_version", 0) + 1
        self._store[(tenant_id, service_id)] = {
            "auth_scheme": auth_scheme,
            "plaintext": plaintext,
            "key_version": key_version,
        }
        return {
            "credential_id": f"cred_{uuid.uuid4().hex[:26]}",
            "key_version": key_version,
            "created_at": time.time(),
        }

    async def get_credential(self, tenant_id: str, service_id: str) -> dict | None:
        """Return stored credential entry or None if not present."""
        return self._store.get((tenant_id, service_id))

    async def list_versions(self, tenant_id: str, service_id: str) -> list:
        """List credential versions for a service."""
        entry = self._store.get((tenant_id, service_id))
        if not entry:
            return []
        return [{"key_version": entry["key_version"], "auth_scheme": entry["auth_scheme"]}]


_vault_client = VaultAdapterClient()


async def get_vault_client() -> VaultAdapterClient:
    return _vault_client
