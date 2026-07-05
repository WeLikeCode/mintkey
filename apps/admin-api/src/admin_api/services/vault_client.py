"""
Vault Adapter gRPC client.

Calls the Go vault-adapter service over insecure gRPC (dev mode).
Plaintext is passed in-flight only; never logged, cached, or returned.

Source: ADR-0011; ADR-0014.4; vault.proto; T-1.3.1; WS-9; WS-11.

WS-11 changes (perf):
- Migrated from sync grpc.Channel + blocking stub calls to grpc.aio.Channel
  with fully async awaitable calls — no thread-pool / executor shim.
- Singleton channel: one grpc.aio.Channel shared for the process lifetime,
  opened lazily on first call and closed via FastAPI lifespan shutdown hook.
  grpc.aio handles transparent reconnection after vault-adapter restart.

Concurrency safety (WS-11 polish):
- _channel_lock (asyncio.Lock) guards lazy init so that concurrent first
  callers don't each open a separate channel and leak the extras.  The
  double-checked pattern (check → lock → check) avoids lock contention on
  the hot path once the channel is set.
- CPython single-worker uvicorn: GIL alone would be sufficient, but the
  lock is nearly free and documents the intent explicitly.
- Multi-worker uvicorn (--workers N): each OS process has its own lock and
  its own singleton — the per-process singleton remains safe.
"""
from __future__ import annotations

import asyncio
import logging
import os
import time

import grpc
import grpc.aio

from admin_api.services import vault_pb2, vault_pb2_grpc

logger = logging.getLogger(__name__)

# Auth-scheme string → proto enum int (mirrors vault.proto AuthScheme).
_AUTH_SCHEME_MAP: dict[str, int] = {
    "api_key_header": 1,
    "api_key_query": 2,
    "bearer_token": 3,
    "basic_auth": 4,
    "oauth2_client_credentials": 5,
    "oidc_client_secret": 6,
    "mtls": 7,
    "oauth2_password_grant": 8,
    "apple_jwt": 9,
    "google_service_account": 10,
    "ssh_private_key": 11,  # ADR-0021: SSH private key for SSH proxy auth
    "ssh_ca": 12,           # ADR-0021: SSH CA key for certificate signing (Phase 2)
    "ssh_password": 13,     # ADR-0021: SSH username+password for SSH proxy auth
    "email_password": 14,   # ADR-0024: Email IMAP/SMTP username+password
    "email_oauth2": 15,     # ADR-0024: Email OAuth2 refresh token (gmail/outlook)
    "email_app_password": 16,  # ADR-0024: Email app-password credential
    "email_oauth2_client": 17,  # feat/oauth2-providers-per-tenant-vault: per-tenant OAuth2 client secret
    # ADR-0029: HTTP Digest (RFC 2617) key pair — MongoDB Atlas Programmatic API Keys.
    # Canonical vault.proto value AUTH_SCHEME_HTTP_DIGEST = 17.
    "http_digest": 17,
}

_VAULT_ADDR = os.getenv("VAULT_GRPC_ADDR", "vault-adapter:8084")

# Service identity sent on every vault gRPC call (BUG-20 fix).
# Must match what vault-adapter has registered for this identity.
# Override in production via a secret manager; never commit a real secret.
_VAULT_ADMIN_IDENTITY_ID = os.getenv("MINTKEY_VAULT_ADMIN_IDENTITY_ID", "svcid_admin_api")
_VAULT_ADMIN_TOKEN = os.getenv("MINTKEY_VAULT_ADMIN_TOKEN", "")

# ---------------------------------------------------------------------------
# Singleton channel — one per process, shared across all requests.
# grpc.aio reconnects automatically when vault-adapter restarts; no manual
# reconnect logic is required.
# ---------------------------------------------------------------------------
_channel: grpc.aio.Channel | None = None
_channel_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    """Return the module-level lock, creating it lazily (must be called from an async context)."""
    global _channel_lock
    if _channel_lock is None:
        _channel_lock = asyncio.Lock()
    return _channel_lock


async def _get_channel() -> grpc.aio.Channel:
    """Return the singleton grpc.aio channel, creating it on first call.

    Uses a double-checked asyncio.Lock to prevent multiple concurrent
    callers from each opening a channel on the very first request:

      fast path (channel already set): no lock acquired.
      slow path (channel is None): acquire lock, re-check, then create.

    Safety properties:
    - Single-worker CPython uvicorn: GIL makes the fast-path assignment
      atomic; the lock adds defence-in-depth at near-zero cost.
    - Multi-worker uvicorn (--workers N): each OS process has its own
      event loop, its own lock, and its own singleton — fully isolated.
    - Concurrent asyncio tasks on first call: at most one channel is
      created; all others reuse it after the lock is released.
    """
    global _channel
    if _channel is not None:
        return _channel
    async with _get_lock():
        if _channel is None:
            _channel = grpc.aio.insecure_channel(_VAULT_ADDR)
            logger.info("vault_client: grpc.aio channel ready → %s", _VAULT_ADDR)
    return _channel


async def close_channel() -> None:
    """Close the singleton channel.  Call from FastAPI lifespan shutdown."""
    global _channel
    if _channel is not None:
        await _channel.close()  # type: ignore[call-arg]  # grpc-stubs require positional `grace`; runtime default=None so no-arg call is valid
        _channel = None
        logger.info("vault_client: grpc.aio channel closed")


class VaultAdapterClient:
    """gRPC client for the Go vault-adapter service.

    Uses the module-level singleton grpc.aio.Channel so all concurrent
    requests multiplex over the same HTTP/2 connection.
    """

    async def _stub(self) -> vault_pb2_grpc.VaultAdapterStub:
        return vault_pb2_grpc.VaultAdapterStub(await _get_channel())  # type: ignore[no-untyped-call]  # vault_pb2_grpc is auto-generated; excluded from mypy by config

    async def put_credential(
        self,
        tenant_id: str,
        service_id: str,
        auth_scheme: str,
        plaintext: str,
        target_url: str = "",
        header_name: str = "",
        query_param: str = "",
        target_address: str = "",
        ssh_user: str = "",
    ) -> dict[str, object]:
        """Seal and store a credential. Returns metadata — no plaintext.

        header_name: HTTP header name for api_key_header scheme (e.g. "X-API-Key") — UX-C6.
        query_param: query parameter name for api_key_query scheme (e.g. "api_key") — UX-C6.
        target_address: SSH-only "host:port" of the backend SSH server — ADR-0021.
        ssh_user: SSH-only username for authentication — ADR-0021.
        """
        scheme_int = _AUTH_SCHEME_MAP.get(auth_scheme, 0)
        req = vault_pb2.PutCredentialRequest(  # type: ignore[attr-defined]  # vault_pb2 is auto-generated; excluded from mypy by config
            tenant_id=tenant_id,
            service_id=service_id,
            auth_scheme=scheme_int,
            value=plaintext.encode(),
            target_url=target_url,
            header_name=header_name,
            query_param=query_param,
            target_address=target_address,
            ssh_user=ssh_user,
        )
        resp = await (await self._stub()).PutCredential(
            req,
            metadata=(
                ("x-mintkey-service-identity", _VAULT_ADMIN_IDENTITY_ID),
                ("x-mintkey-service-token", _VAULT_ADMIN_TOKEN),
            ),
        )
        return {
            "credential_id": f"cred_{tenant_id[:8]}_{service_id[:8]}",
            "key_version": resp.key_version,
            "created_at": time.time(),
        }

    async def get_credential(self, tenant_id: str, service_id: str) -> dict[str, object] | None:
        """
        Fetch current credential. Returns dict with 'plaintext' (decoded bytes)
        plus metadata fields, or None if not found.

        The 'plaintext' key is provided so existing call sites (proxy.py, services.py)
        that call cred_entry.get("plaintext") work without modification.
        Plaintext stays in request scope — ADR-0014.4.
        """
        req = vault_pb2.GetCredentialRequest(  # type: ignore[attr-defined]  # vault_pb2 is auto-generated; excluded from mypy by config
            tenant_id=tenant_id,
            service_id=service_id,
            key_version=0,
        )
        try:
            resp = await (await self._stub()).GetCredential(
                req,
                metadata=(
                    ("x-mintkey-service-identity", _VAULT_ADMIN_IDENTITY_ID),
                    ("x-mintkey-service-token", _VAULT_ADMIN_TOKEN),
                ),
            )
            return {
                "plaintext": resp.value.decode("utf-8", errors="replace"),
                "auth_scheme": resp.auth_scheme,
                "key_version": resp.returned_key_version,
                "header_name": resp.header_name,
                "query_param": resp.query_param,
                # SSH metadata — ADR-0021; empty string for non-SSH schemes.
                "target_address": resp.target_address,
                "ssh_user": resp.ssh_user,
            }
        except grpc.aio.AioRpcError:
            return None

    async def list_versions(self, tenant_id: str, service_id: str) -> list[dict[str, object]]:
        """List credential version descriptors (no plaintext).

        Returns a list of dicts with metadata fields per VersionDescriptor:
          key_version, auth_scheme, is_current, status, created_at (ISO-8601).

        Raises on real gRPC errors so callers are not silently blinded.
        Returns [] only when the vault-adapter reports Unimplemented
        (backward-compat for pre-WS-10 deployments during rolling upgrade).
        """
        req = vault_pb2.ListVersionsRequest(  # type: ignore[attr-defined]  # vault_pb2 is auto-generated; excluded from mypy by config
            tenant_id=tenant_id,
            service_id=service_id,
        )
        try:
            resp = await (await self._stub()).ListVersions(
                req,
                metadata=(
                    ("x-mintkey-service-identity", _VAULT_ADMIN_IDENTITY_ID),
                    ("x-mintkey-service-token", _VAULT_ADMIN_TOKEN),
                ),
            )
            return [
                {
                    "key_version": v.key_version,
                    "auth_scheme": v.auth_scheme,
                    "is_current": v.is_current,
                    "status": v.status,
                    "created_at": (
                        v.created_at.ToDatetime().isoformat()
                        if v.HasField("created_at")
                        else None
                    ),
                }
                for v in resp.versions
            ]
        except grpc.aio.AioRpcError as exc:
            if exc.code() == grpc.StatusCode.UNIMPLEMENTED:
                # Backward-compat: old vault-adapter deployment; log and return empty.
                logger.warning(
                    "vault_client.list_versions: vault-adapter returned UNIMPLEMENTED "
                    "(pre-WS-10 deployment?) — returning []. tenant=%s service=%s",
                    tenant_id,
                    service_id,
                )
                return []
            logger.error(
                "vault_client.list_versions: gRPC error %s — %s. tenant=%s service=%s",
                exc.code(),
                exc.details(),
                tenant_id,
                service_id,
            )
            raise


_vault_client = VaultAdapterClient()


async def get_vault_client() -> VaultAdapterClient:
    return _vault_client
