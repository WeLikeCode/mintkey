"""
Vault Adapter client stub.
Full gRPC client wired in T-1.3.1 integration phase.

Source: ADR-0011 (Go vault-adapter, gRPC interface); T-1.3.2.
"""
from __future__ import annotations

import time
import uuid


class VaultAdapterClient:
    """Stub — real gRPC client added when vault-adapter gRPC is exposed."""

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
        return {
            "credential_id": f"cred_{uuid.uuid4().hex[:26]}",
            "key_version": 1,
            "created_at": time.time(),
        }

    async def list_versions(self, tenant_id: str, service_id: str) -> list:
        """List credential versions for a service. Stub returns empty list."""
        return []


_vault_client = VaultAdapterClient()


async def get_vault_client() -> VaultAdapterClient:
    return _vault_client
