"""
Credential endpoints.

POST /v1/tenants/{tenant_id}/services/{service_id}/credentials — register credential (201)
GET  /v1/tenants/{tenant_id}/services/{service_id}/credentials — list versions (200)

Architecture constraints:
  - Vault Adapter called to store encrypted credential — ADR-0011, ADR-0014.4.
  - Response NEVER contains plaintext credential — S-SEC-1, ADR-0014.4.
  - Audit event "credential.registered" emitted with NO plaintext — ADR-0014.7.
  - Tenant context via bound parameters — ADR-0008, T-1.0.15.
  - pg_notify via bound parameters — ADR-0008, ADR-0014.1.
  - ULID IDs with prefix "cred_" — ADR-0017.11.
  - Global channel "mintkey:credential" — ADR-0014.1.

Source: T-1.3.2 (session 1); ADR-0008; ADR-0011; ADR-0014.4; ADR-0014.7; ADR-0017.11.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from admin_api.services.vault_client import VaultAdapterClient, get_vault_client
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(
    prefix="/v1/tenants/{tenant_id}/services/{service_id}/credentials"
)

# Crockford base32 alphabet (uppercase, no I/L/O/U)
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _new_cred_id() -> str:
    """
    Generate a ULID-format ID with the 'cred_' prefix — ADR-0017.11.

    Layout: 10 time chars (48-bit ms) + 16 random chars = 26 Crockford base32 chars.
    """
    ts_ms = int(time.time() * 1000)
    rand = int.from_bytes(uuid.uuid4().bytes[:10], "big")

    t_enc = []
    v = ts_ms
    for _ in range(10):
        t_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    t_enc.reverse()

    r_enc = []
    v = rand
    for _ in range(16):
        r_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    r_enc.reverse()

    return "cred_" + "".join(t_enc) + "".join(r_enc)


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class CredentialCreate(BaseModel):
    auth_scheme: str  # e.g., "bearer_token", "api_key_header"
    value: str        # SENSITIVE — never echoed back (S-SEC-1, ADR-0014.4)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_credential(
    tenant_id: UUID,
    service_id: UUID,
    body: CredentialCreate,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    Register a new credential for a service.

    Calls the Vault Adapter to store the encrypted credential. Only metadata
    is persisted locally and returned. The plaintext value is NEVER stored,
    logged, audited, or returned — ADR-0014.4, S-SEC-1.

    Source: T-1.3.2; ADR-0008; ADR-0011; ADR-0014.4; ADR-0014.7; ADR-0017.11.
    """
    # Step 1: Set tenant context — bound parameters, ADR-0008
    await set_tenant_context(session, tenant_id)

    # Step 2: Call Vault Adapter — plaintext is passed only within this request scope
    # and is NOT stored, logged, or returned. ADR-0014.4.
    vault_result = await vault.put_credential(
        tenant_id=str(tenant_id),
        service_id=str(service_id),
        auth_scheme=body.auth_scheme,
        plaintext=body.value,  # plaintext leaves scope here; vault encrypts it
    )
    key_version: int = vault_result["key_version"]

    # Step 3: Generate wire ID and internal UUID — ADR-0017.11
    cred_wire_id = _new_cred_id()
    internal_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Step 4: Insert metadata-only record (NO plaintext stored) — ADR-0014.4
    # ciphertext/nonce/wrapped_dek are stored in the vault; local row holds metadata.
    # The stub fills placeholder bytes; the real integration will receive them from
    # the vault-adapter gRPC response in T-1.3.1.
    await session.execute(
        text(
            "INSERT INTO credentials"
            " (id, tenant_id, service_id, key_version, ciphertext, nonce,"
            "  wrapped_dek, auth_scheme, status, created_at)"
            " VALUES"
            " (:id, :tenant_id, :service_id, :key_version, :ciphertext, :nonce,"
            "  :wrapped_dek, :auth_scheme, :status, :created_at)"
        ),
        {
            "id": str(internal_id),
            "tenant_id": str(tenant_id),
            "service_id": str(service_id),
            "key_version": key_version,
            "ciphertext": b"",          # filled by real vault-adapter in T-1.3.1
            "nonce": b"",               # filled by real vault-adapter in T-1.3.1
            "wrapped_dek": b"",         # filled by real vault-adapter in T-1.3.1
            "auth_scheme": body.auth_scheme,
            "status": "active",
            "created_at": now,
        },
    )

    # Step 5: Emit audit event — ADR-0014.7
    # Rotation detected when vault returns key_version > 1 — T-1.8.2.
    # Payload MUST NOT include body.value or any plaintext — ADR-0014.4, S-SEC-1.
    is_rotation = key_version > 1
    event_type = "credential.rotated" if is_rotation else "credential.registered"
    audit_payload: dict = {
        "credential_id": cred_wire_id,
        "service_id": str(service_id),
        "key_version": key_version,
        "auth_scheme": body.auth_scheme,
    }
    if is_rotation:
        audit_payload["previous_key_version"] = key_version - 1

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type=event_type,
        actor_id=None,
        actor_type="operator",
        target_id=internal_id,
        target_type="credential",
        payload=audit_payload,
    )

    # Step 6: NOTIFY change channel — ADR-0014.1, bound parameters
    await notify_change(
        session,
        "mintkey:credential",
        {
            "event": event_type,
            "tenant_id": str(tenant_id),
            "service_id": str(service_id),
            "credential_id": cred_wire_id,
        },
    )

    # Step 7: Return 201 with metadata ONLY — NEVER include body.value
    return JSONResponse(
        status_code=201,
        content={
            "id": cred_wire_id,
            "key_version": key_version,
            "auth_scheme": body.auth_scheme,
            "created_at": now.isoformat(),
        },
    )


@router.get("")
async def list_credential_versions(
    tenant_id: UUID,
    service_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    List credential version metadata for a service.

    Returns version metadata only — no plaintext, no ciphertext — S-SEC-1.

    Source: T-1.3.2; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, key_version, auth_scheme, status, created_at, revoked_at"
            " FROM credentials"
            " WHERE service_id = :sid AND tenant_id = :tid"
            " ORDER BY key_version DESC"
        ),
        {"sid": str(service_id), "tid": str(tenant_id)},
    )
    rows = result.fetchall()

    versions = [
        {
            "key_version": row.key_version,
            "auth_scheme": row.auth_scheme,
            "status": row.status,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
        }
        for row in rows
    ]
    return JSONResponse({"versions": versions})
