"""
Unit tests for VaultAdapterClient.get_credential — UX-C5 Bug 3.

Verifies that get_credential returns header_name and query_param from the
GetCredentialResponse proto so that test_service (Bug 2) can use them.

Source: UX-C5 Bug 3 fix; vault_pb2.GetCredentialResponse fields 6 (header_name)
        and 7 (query_param).
"""
from __future__ import annotations

import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Ensure admin-api source and mintkey-models are on sys.path.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
_ADMIN_API_SRC = os.path.join(_REPO_ROOT, "apps/admin-api", "src")
_MODELS_SRC = os.path.join(_REPO_ROOT, "packages/python/mintkey-models")
for _p in (_ADMIN_API_SRC, _MODELS_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.mark.asyncio
async def test_get_credential_returns_header_name():
    """
    When the vault returns a non-empty header_name, get_credential must
    include it in the returned dict so test_service can use it as the
    HTTP header name for api_key_header credentials.

    Source: UX-C5 Bug 3.
    """
    import admin_api.services.vault_client as vc_mod

    # Construct a mock GetCredentialResponse with all relevant fields set.
    mock_resp = MagicMock()
    mock_resp.value = b"supersecret"
    mock_resp.auth_scheme = 1  # AUTH_SCHEME_API_KEY_HEADER
    mock_resp.returned_key_version = 7
    mock_resp.header_name = "X-Custom-Auth"
    mock_resp.query_param = ""

    mock_stub = MagicMock()
    mock_stub.GetCredential = AsyncMock(return_value=mock_resp)

    client = vc_mod.VaultAdapterClient()
    with patch.object(client, "_stub", AsyncMock(return_value=mock_stub)):
        result = await client.get_credential("tenant-abc", "svc-xyz")

    assert result is not None, "get_credential returned None — expected a dict"
    assert result["header_name"] == "X-Custom-Auth", (
        f"Expected header_name='X-Custom-Auth', got: {result.get('header_name')!r}"
    )
    assert result["query_param"] == "", (
        f"Expected empty query_param, got: {result.get('query_param')!r}"
    )
    assert result["plaintext"] == "supersecret"
    assert result["key_version"] == 7


@pytest.mark.asyncio
async def test_get_credential_returns_query_param():
    """
    When the vault returns a non-empty query_param, get_credential must
    include it in the returned dict so test_service can use it as the
    query parameter name for api_key_query credentials.

    Source: UX-C5 Bug 3.
    """
    import admin_api.services.vault_client as vc_mod

    mock_resp = MagicMock()
    mock_resp.value = b"myapikey123"
    mock_resp.auth_scheme = 2  # AUTH_SCHEME_API_KEY_QUERY
    mock_resp.returned_key_version = 3
    mock_resp.header_name = ""
    mock_resp.query_param = "token"

    mock_stub = MagicMock()
    mock_stub.GetCredential = AsyncMock(return_value=mock_resp)

    client = vc_mod.VaultAdapterClient()
    with patch.object(client, "_stub", AsyncMock(return_value=mock_stub)):
        result = await client.get_credential("tenant-abc", "svc-xyz")

    assert result is not None
    assert result["query_param"] == "token", (
        f"Expected query_param='token', got: {result.get('query_param')!r}"
    )
    assert result["header_name"] == ""
    assert result["plaintext"] == "myapikey123"


@pytest.mark.asyncio
async def test_get_credential_empty_strings_preserved():
    """
    When header_name and query_param are both empty (e.g. bearer_token scheme),
    the returned dict must still carry them as empty strings — not absent.

    Source: UX-C5 Bug 3 — preserve whatever the proto returned.
    """
    import admin_api.services.vault_client as vc_mod

    mock_resp = MagicMock()
    mock_resp.value = b"bearer-token-value"
    mock_resp.auth_scheme = 3  # AUTH_SCHEME_BEARER_TOKEN
    mock_resp.returned_key_version = 1
    mock_resp.header_name = ""
    mock_resp.query_param = ""

    mock_stub = MagicMock()
    mock_stub.GetCredential = AsyncMock(return_value=mock_resp)

    client = vc_mod.VaultAdapterClient()
    with patch.object(client, "_stub", AsyncMock(return_value=mock_stub)):
        result = await client.get_credential("tenant-bearer", "svc-bearer")

    assert result is not None
    assert "header_name" in result, "header_name key must be present in returned dict"
    assert "query_param" in result, "query_param key must be present in returned dict"
    assert result["header_name"] == ""
    assert result["query_param"] == ""
