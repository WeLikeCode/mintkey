"""
AgentSecretsVault gRPC client for admin-api.

Singleton grpc.aio channel, identical pattern to
apps/admin-api/src/admin_api/services/vault_client.py.

Calls the vault-adapter AgentSecretsVault service (ADR-0025) using the
admin-api service identity — authorized for vault.secret.put and
vault.secret.delete (NOT vault.secret.read; operators never read
agent-secret plaintext — least privilege).

Env vars:
  VAULT_GRPC_ADDR                — vault-adapter gRPC address (default vault-adapter:8084)
  MINTKEY_VAULT_ADMIN_IDENTITY_ID — service identity id  (default svcid_admin_api)
  MINTKEY_VAULT_ADMIN_TOKEN       — service identity token (default "")
"""
from __future__ import annotations

import logging
import os

from admin_api.services import vault_pb2, vault_pb2_grpc

logger = logging.getLogger(__name__)

_VAULT_ADDR = os.getenv("VAULT_GRPC_ADDR", "vault-adapter:8084")

# Reuse the same admin identity constants as vault_client.py.
_VAULT_ADMIN_IDENTITY_ID = os.getenv("MINTKEY_VAULT_ADMIN_IDENTITY_ID", "svcid_admin_api")
_VAULT_ADMIN_TOKEN = os.getenv("MINTKEY_VAULT_ADMIN_TOKEN", "")


class AgentSecretsVaultClient:
    """gRPC client for the AgentSecretsVault service (ADR-0025).

    Uses the module-level singleton grpc.aio.Channel from vault_client
    (shared HTTP/2 connection). Injects admin-api identity headers so the
    vault-adapter scopeInterceptor authorizes vault.secret.put and
    vault.secret.delete calls.

    Does NOT expose get_agent_secret — admin-api is not permitted to read
    agent-secret plaintext (vault.secret.read is NOT granted).
    """

    def _metadata(self) -> tuple[tuple[str, str], ...]:
        return (
            ("x-mintkey-service-identity", _VAULT_ADMIN_IDENTITY_ID),
            ("x-mintkey-service-token", _VAULT_ADMIN_TOKEN),
        )

    async def _stub(self) -> vault_pb2_grpc.AgentSecretsVaultStub:
        # Import lazily so the singleton channel is only opened on demand.
        from admin_api.services.vault_client import _get_channel
        return vault_pb2_grpc.AgentSecretsVaultStub(await _get_channel())  # type: ignore[no-untyped-call]

    async def put_agent_secret(
        self,
        tenant_id: str,
        secret_id: str,
        value: bytes,
    ) -> dict[str, object]:
        """Seal and store an agent secret. Returns metadata — no plaintext."""
        req = vault_pb2.PutAgentSecretRequest(  # type: ignore[attr-defined]
            tenant_id=tenant_id,
            secret_id=secret_id,
            value=value,
            kek_version=0,
        )
        resp = await (await self._stub()).PutAgentSecret(req, metadata=self._metadata())
        return {
            "kek_version": resp.kek_version,
        }

    async def delete_agent_secret(
        self,
        tenant_id: str,
        secret_id: str,
    ) -> bool:
        """
        Delete encrypted blob for (tenant_id, secret_id).

        Returns True if a row was deleted, False if already absent (idempotent).
        """
        req = vault_pb2.DeleteAgentSecretRequest(  # type: ignore[attr-defined]
            tenant_id=tenant_id,
            secret_id=secret_id,
        )
        resp = await (await self._stub()).DeleteAgentSecret(req, metadata=self._metadata())
        return bool(resp.deleted)


_agent_secrets_vault_client = AgentSecretsVaultClient()


async def get_agent_secrets_vault_client() -> AgentSecretsVaultClient:
    return _agent_secrets_vault_client
