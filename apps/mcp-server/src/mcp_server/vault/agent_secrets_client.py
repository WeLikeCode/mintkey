"""
AgentSecretsVault gRPC client for the MCP server.

Singleton grpc.aio channel, identical pattern to
apps/admin-api/src/admin_api/services/vault_client.py.

Calls the vault-adapter AgentSecretsVault service (ADR-0025).
Plaintext in GetAgentSecret responses stays in request scope —
never logged, never cached, never stored. (ADR-0014.4)

Env vars:
  VAULT_GRPC_ADDR               — vault-adapter gRPC address (default vault-adapter:8084)
  MINTKEY_VAULT_MCP_IDENTITY_ID — service identity id  (default svcid_mcp)
  MINTKEY_VAULT_MCP_TOKEN       — service identity token (default "")
"""
from __future__ import annotations

import asyncio
import logging
import os

import grpc
import grpc.aio

from mcp_server.vault import vault_pb2, vault_pb2_grpc  # type: ignore[attr-defined]

logger = logging.getLogger(__name__)

_VAULT_ADDR = os.getenv("VAULT_GRPC_ADDR", "vault-adapter:8084")
_VAULT_MCP_IDENTITY_ID = os.getenv("MINTKEY_VAULT_MCP_IDENTITY_ID", "svcid_mcp")
_VAULT_MCP_TOKEN = os.getenv("MINTKEY_VAULT_MCP_TOKEN", "")

_channel: grpc.aio.Channel | None = None
_channel_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _channel_lock
    if _channel_lock is None:
        _channel_lock = asyncio.Lock()
    return _channel_lock


async def _get_channel() -> grpc.aio.Channel:
    global _channel
    if _channel is not None:
        return _channel
    async with _get_lock():
        if _channel is None:
            _channel = grpc.aio.insecure_channel(_VAULT_ADDR)
            logger.info("agent_secrets_client: grpc.aio channel ready → %s", _VAULT_ADDR)
    return _channel


async def close_channel() -> None:
    """Close the singleton channel. Call from FastAPI lifespan shutdown."""
    global _channel
    if _channel is not None:
        await _channel.close()  # type: ignore[call-arg]
        _channel = None
        logger.info("agent_secrets_client: grpc.aio channel closed")


class AgentSecretsVaultClient:
    """gRPC client for the AgentSecretsVault service (ADR-0025)."""

    def _metadata(self) -> tuple:
        return (
            ("x-mintkey-service-identity", _VAULT_MCP_IDENTITY_ID),
            ("x-mintkey-service-token", _VAULT_MCP_TOKEN),
        )

    async def _stub(self) -> vault_pb2_grpc.AgentSecretsVaultStub:
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

    async def get_agent_secret(
        self,
        tenant_id: str,
        secret_id: str,
    ) -> bytes | None:
        """
        Unseal and return plaintext bytes for (tenant_id, secret_id).

        Returns None if NOT_FOUND. SENSITIVE — keep in request scope only.
        """
        req = vault_pb2.GetAgentSecretRequest(  # type: ignore[attr-defined]
            tenant_id=tenant_id,
            secret_id=secret_id,
        )
        try:
            resp = await (await self._stub()).GetAgentSecret(req, metadata=self._metadata())
            return bytes(resp.value)
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.NOT_FOUND:
                return None
            raise

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


_agent_secrets_client = AgentSecretsVaultClient()


async def get_agent_secrets_vault_client() -> AgentSecretsVaultClient:
    return _agent_secrets_client
