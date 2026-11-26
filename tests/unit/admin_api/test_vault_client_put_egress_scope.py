"""
Unit tests for VaultAdapterClient.put_credential — the egress scope metadata.

Requirement: proxy-public-egress › The vault stores an egress scope with each
credential › the admin-api client sends the scope.
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


@pytest.mark.l4("C-9f390972")
@pytest.mark.asyncio
async def test_C_9f390972_put_credential_sends_the_scope_metadata() -> None:
    """
    put_credential must put the egress scope in the PutCredential call
    metadata as ("x-mintkey-egress-scope", <scope>) when a scope is given,
    and send no such pair when the argument is omitted.

    Source: proxy-public-egress › the admin-api client sends the scope.
    """
    import admin_api.services.vault_client as vc_mod

    stub = MagicMock()
    stub.PutCredential = AsyncMock(return_value=MagicMock(key_version=1))

    client = vc_mod.VaultAdapterClient()
    with patch.object(client, "_stub", AsyncMock(return_value=stub)):
        await client.put_credential(
            "tenant-egress",
            "svc-public",
            "bearer_token",
            "secret-value",
            egress_scope="public",
        )
        await client.put_credential(
            "tenant-egress",
            "svc-default",
            "bearer_token",
            "secret-value",
        )

    calls = stub.PutCredential.call_args_list
    assert len(calls) == 2, (
        f"expected PutCredential to be called twice, got {len(calls)} call(s)"
    )

    first_metadata = dict(calls[0].kwargs.get("metadata") or {})
    second_metadata = dict(calls[1].kwargs.get("metadata") or {})

    assert first_metadata.get("x-mintkey-egress-scope") == "public", (
        "put_credential(egress_scope='public') must send "
        "('x-mintkey-egress-scope', 'public') in the PutCredential metadata; "
        f"got {first_metadata}"
    )
    assert "x-mintkey-egress-scope" not in second_metadata, (
        "put_credential() without egress_scope must send no "
        f"x-mintkey-egress-scope pair; got {second_metadata}"
    )

    for metadata in (first_metadata, second_metadata):
        assert "x-mintkey-service-identity" in metadata, (
            f"x-mintkey-service-identity missing from PutCredential metadata: {metadata}"
        )
        assert "x-mintkey-service-token" in metadata, (
            f"x-mintkey-service-token missing from PutCredential metadata: {metadata}"
        )
    assert first_metadata["x-mintkey-service-identity"], (
        "x-mintkey-service-identity must not be empty"
    )
