"""
Vault Adapter gRPC client.

Calls the Go vault-adapter service over insecure gRPC (dev mode).
Plaintext is passed in-flight only; never logged, cached, or returned.

Source: ADR-0011; ADR-0014.4; vault.proto; T-1.3.1.
"""
from __future__ import annotations

import os
import time

import grpc

from admin_api.services import vault_pb2, vault_pb2_grpc

# Auth-scheme string → proto enum int (mirrors vault.proto AuthScheme).
_AUTH_SCHEME_MAP: dict[str, int] = {
    "api_key_header": 1,
    "api_key_query": 2,
    "bearer_token": 3,
    "basic_auth": 4,
    "oauth2_client_credentials": 5,
    "oidc_client_secret": 6,
    "mtls": 7,
}

_VAULT_ADDR = os.getenv("VAULT_GRPC_ADDR", "vault-adapter:8084")


class VaultAdapterClient:
    """gRPC client for the Go vault-adapter service."""

    def _stub(self) -> vault_pb2_grpc.VaultAdapterStub:
        channel = grpc.insecure_channel(_VAULT_ADDR)
        return vault_pb2_grpc.VaultAdapterStub(channel)

    async def put_credential(
        self,
        tenant_id: str,
        service_id: str,
        auth_scheme: str,
        plaintext: str,
        target_url: str = "",
    ) -> dict:
        """Seal and store a credential. Returns metadata — no plaintext."""
        scheme_int = _AUTH_SCHEME_MAP.get(auth_scheme, 0)
        req = vault_pb2.PutCredentialRequest(
            tenant_id=tenant_id,
            service_id=service_id,
            auth_scheme=scheme_int,
            value=plaintext.encode(),
            target_url=target_url,
        )
        resp = self._stub().PutCredential(req)
        return {
            "credential_id": f"cred_{tenant_id[:8]}_{service_id[:8]}",
            "key_version": resp.key_version,
            "created_at": time.time(),
        }

    async def get_credential(self, tenant_id: str, service_id: str) -> dict | None:
        """Fetch current credential metadata. Returns None if not found."""
        req = vault_pb2.GetCredentialRequest(
            tenant_id=tenant_id,
            service_id=service_id,
            key_version=0,
        )
        try:
            resp = self._stub().GetCredential(req)
            return {
                "auth_scheme": resp.auth_scheme,
                "key_version": resp.returned_key_version,
            }
        except grpc.RpcError:
            return None

    async def list_versions(self, tenant_id: str, service_id: str) -> list:
        """List credential version descriptors (no plaintext)."""
        req = vault_pb2.ListVersionsRequest(
            tenant_id=tenant_id,
            service_id=service_id,
        )
        try:
            resp = self._stub().ListVersions(req)
            return [
                {"key_version": v.key_version, "auth_scheme": v.auth_scheme}
                for v in resp.versions
            ]
        except grpc.RpcError:
            return []


_vault_client = VaultAdapterClient()


async def get_vault_client() -> VaultAdapterClient:
    return _vault_client
