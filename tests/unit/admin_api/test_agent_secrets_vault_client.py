"""
Unit tests for admin_api AgentSecretsVaultClient.

Mock only the external gRPC stub (not the system under test).
Asserts:
- put_agent_secret sends PutAgentSecretRequest with correct fields + admin metadata.
- delete_agent_secret returns the stub's `deleted` bool.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_put_agent_secret_sends_correct_request_and_metadata() -> None:
    """put_agent_secret calls PutAgentSecret with right fields and admin identity headers."""
    from admin_api.services.agent_secrets_vault_client import AgentSecretsVaultClient
    from admin_api.services import vault_pb2

    # Build a fake response
    fake_resp = MagicMock()
    fake_resp.kek_version = 1

    mock_stub = MagicMock()
    mock_stub.PutAgentSecret = AsyncMock(return_value=fake_resp)

    client = AgentSecretsVaultClient()

    with patch.object(client, "_stub", AsyncMock(return_value=mock_stub)):
        result = await client.put_agent_secret(
            tenant_id="t_tenant01",
            secret_id="sec_secret01",
            value=b"s3cr3t",
        )

    mock_stub.PutAgentSecret.assert_called_once()
    call_args = mock_stub.PutAgentSecret.call_args

    req = call_args.args[0]
    assert isinstance(req, vault_pb2.PutAgentSecretRequest)
    assert req.tenant_id == "t_tenant01"
    assert req.secret_id == "sec_secret01"
    assert req.value == b"s3cr3t"
    assert req.kek_version == 0  # always 0 per MCP client pattern

    # Verify admin identity metadata was injected
    metadata = call_args.kwargs["metadata"]
    metadata_dict = dict(metadata)
    assert "x-mintkey-service-identity" in metadata_dict
    assert "x-mintkey-service-token" in metadata_dict
    # identity must be the admin identity (not mcp or proxy)
    assert metadata_dict["x-mintkey-service-identity"] == "svcid_admin_api"

    assert result == {"kek_version": 1}


@pytest.mark.asyncio
async def test_delete_agent_secret_returns_deleted_bool() -> None:
    """delete_agent_secret returns True when stub reports deleted=True."""
    from admin_api.services.agent_secrets_vault_client import AgentSecretsVaultClient

    fake_resp = MagicMock()
    fake_resp.deleted = True

    mock_stub = MagicMock()
    mock_stub.DeleteAgentSecret = AsyncMock(return_value=fake_resp)

    client = AgentSecretsVaultClient()

    with patch.object(client, "_stub", AsyncMock(return_value=mock_stub)):
        result = await client.delete_agent_secret(
            tenant_id="t_tenant01",
            secret_id="sec_secret01",
        )

    assert result is True


@pytest.mark.asyncio
async def test_delete_agent_secret_returns_false_when_absent() -> None:
    """delete_agent_secret returns False when stub reports deleted=False (idempotent)."""
    from admin_api.services.agent_secrets_vault_client import AgentSecretsVaultClient

    fake_resp = MagicMock()
    fake_resp.deleted = False

    mock_stub = MagicMock()
    mock_stub.DeleteAgentSecret = AsyncMock(return_value=fake_resp)

    client = AgentSecretsVaultClient()

    with patch.object(client, "_stub", AsyncMock(return_value=mock_stub)):
        result = await client.delete_agent_secret(
            tenant_id="t_tenant01",
            secret_id="sec_secret01",
        )

    assert result is False
