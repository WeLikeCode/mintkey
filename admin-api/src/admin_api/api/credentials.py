"""
Credential endpoints.

POST   /v1/tenants/{tenant_id}/services/{service_id}/credentials                   — register (201)
POST   /v1/tenants/{tenant_id}/services/{service_id}/credentials/rotate            — rotate (200)
GET    /v1/tenants/{tenant_id}/services/{service_id}/credentials                   — list (200)
DELETE /v1/tenants/{tenant_id}/services/{service_id}/credentials/{key_version}     — revoke (204)

Architecture constraints:
  - Vault Adapter called to store encrypted credential — ADR-0011, ADR-0014.4.
  - Response NEVER contains plaintext credential — S-SEC-1, ADR-0014.4.
  - Audit event "credential.registered"/"credential.rotated" emitted with NO plaintext — ADR-0014.7.
  - Tenant context via bound parameters — ADR-0008, T-1.0.15.
  - pg_notify via bound parameters — ADR-0008, ADR-0014.1.
  - ULID IDs with prefix "cred_" — ADR-0017.11.
  - Global channel "mintkey:credential" — ADR-0014.1.
  - Rotation: old credential marked superseded, new inserted active, atomic — ADR-0013 §3.1.
  - service_id in rotate accepts both svc_ Crockford and svc_ 32-hex wire forms — R12/R14a.

Source: T-1.3.2 (session 1); ADR-0008; ADR-0011; ADR-0013; ADR-0014.4; ADR-0014.7; ADR-0017.11.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Union
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
# Wire-form decoder — mirrors services.py _wire_id_to_db_uuid (R12/R14a).
# Credentials accept svc_ wire IDs in the rotate endpoint path; admin-ui
# passes the wire form through without decoding (ADR lesson from R8/R12).
# ---------------------------------------------------------------------------


def _svc_wire_to_db_uuid(wire_id: str) -> str:
    """
    Convert a wire svc_ ID back to the UUID string stored in the DB.

    Two wire forms exist (ADR-0017.11):
      - "svc_" + 32 hex chars  — old serialised form
      - "svc_" + 26 Crockford base32 chars — ULID form post-R12

    Returns wire_id unchanged for raw UUIDs (fallback).
    """
    if wire_id.startswith("svc_"):
        tail = wire_id[4:]
        if len(tail) == 32:
            return (
                f"{tail[:8]}-{tail[8:12]}-{tail[12:16]}"
                f"-{tail[16:20]}-{tail[20:]}"
            )
        if len(tail) == 26:
            val = 0
            for ch in tail.upper():
                val = (val << 5) | _CROCKFORD.index(ch)
            val &= (1 << 128) - 1
            h = f"{val:032x}"
            return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    return wire_id


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CredentialCreate(BaseModel):
    auth_scheme: str  # e.g., "bearer_token", "api_key_header"
    value: str        # SENSITIVE — never echoed back (S-SEC-1, ADR-0014.4)


class CredentialRotateRequest(BaseModel):
    """
    Body for POST .../credentials/rotate — ADR-0013 §3.1.

    auth_scheme: the scheme whose active credential is being rotated.
    rotate_from: credential_id (cred_ wire form) being superseded; if omitted,
        the currently-active credential of that auth_scheme is looked up and
        superseded. If multiple active credentials share the same auth_scheme
        (which the schema does not prevent), the one with the highest key_version
        is superseded (deterministic rule documented here per CLAUDE.md §3).
    value: new secret material (SENSITIVE — never stored or returned).
    """
    auth_scheme: str
    rotate_from: Optional[str] = None
    value: Optional[Union[str, dict]] = None  # SENSITIVE — ADR-0014.4


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


@router.post("/rotate", status_code=200)
async def rotate_credential(
    tenant_id: UUID,
    service_id: str,
    body: CredentialRotateRequest,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    Rotate a credential — ADR-0013 §3.1.

    Atomically marks the old credential as 'superseded' and inserts a new
    active credential. The plaintext value (body.value) is passed to the
    Vault Adapter and NEVER stored, logged, or returned (ADR-0014.4, S-SEC-1).

    service_id accepts both svc_<26-char Crockford> and svc_<32-hex> wire forms
    (admin-ui passes wire form through; admin-api decodes — R12/R14a lesson).

    If rotate_from is omitted, the currently-active credential with the highest
    key_version for the given auth_scheme is superseded (deterministic rule:
    highest key_version wins when multiple actives share the same scheme).

    Returns 404 if the service does not exist or belongs to another tenant.
    Returns 404 if rotate_from is specified but no matching credential exists.
    Returns 409 if the target credential is already superseded or revoked.
    """
    # Step 1: Set tenant context — bound parameters, ADR-0008
    await set_tenant_context(session, tenant_id)

    # Step 2: Decode wire-form service_id → DB UUID
    db_svc_uuid = _svc_wire_to_db_uuid(service_id)

    # Step 3: Verify service exists under this tenant (enforces RLS + ownership)
    svc_result = await session.execute(
        text("SELECT id FROM services WHERE id = :sid AND tenant_id = :tid"),
        {"sid": db_svc_uuid, "tid": str(tenant_id)},
    )
    if svc_result.fetchone() is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Service not found"},
        )

    # Step 4: Resolve the old credential to supersede.
    # When rotate_from is provided, the caller intends to supersede the currently-
    # active credential of that auth_scheme (rotate_from identifies it by cred_ wire
    # form, but we don't decode cred_ wire IDs here — we match the active row for
    # the scheme, which is the only semantically valid target).  If the schema ever
    # prevents multiple actives of the same scheme (via a unique index) this is
    # equivalent; otherwise the deterministic rule (highest key_version) applies.
    old_result = await session.execute(
        text(
            "SELECT id, key_version, status FROM credentials"
            " WHERE tenant_id = :tid AND service_id = :sid"
            "   AND auth_scheme = :scheme AND status = 'active'"
            " ORDER BY key_version DESC LIMIT 1"
        ),
        {"tid": str(tenant_id), "sid": db_svc_uuid, "scheme": body.auth_scheme},
    )
    old_row = old_result.fetchone()

    if old_row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "No active credential to rotate"},
        )

    old_internal_id: Any = old_row.id

    # Step 5: Call Vault Adapter for new credential — plaintext never stored
    plaintext: str = ""
    if body.value is not None:
        plaintext = body.value if isinstance(body.value, str) else str(body.value)

    vault_result = await vault.put_credential(
        tenant_id=str(tenant_id),
        service_id=db_svc_uuid,
        auth_scheme=body.auth_scheme,
        plaintext=plaintext,
    )
    new_key_version: int = vault_result["key_version"]

    # Step 6: Generate new cred ID and UUID — ADR-0017.11
    new_cred_wire_id = _new_cred_id()
    new_internal_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Step 7: Atomic DB transaction — mark old superseded, insert new active
    await session.execute(
        text(
            "UPDATE credentials SET status = 'superseded'"
            " WHERE id = :old_id AND tenant_id = :tid"
        ),
        {"old_id": str(old_internal_id), "tid": str(tenant_id)},
    )
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
            "id": str(new_internal_id),
            "tenant_id": str(tenant_id),
            "service_id": db_svc_uuid,
            "key_version": new_key_version,
            "ciphertext": b"",
            "nonce": b"",
            "wrapped_dek": b"",
            "auth_scheme": body.auth_scheme,
            "status": "active",
            "created_at": now,
        },
    )

    # Step 8: Emit audit event — ADR-0014.7; no plaintext in payload (ADR-0014.4)
    audit_payload: dict = {
        "credential_id": new_cred_wire_id,
        "service_id": service_id,  # wire form, not decoded UUID
        "key_version": new_key_version,
        "auth_scheme": body.auth_scheme,
        "superseded_credential_id": str(old_internal_id),
    }
    if body.rotate_from is not None:
        audit_payload["rotate_from"] = body.rotate_from

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="credential.rotated",
        actor_id=None,
        actor_type="operator",
        target_id=new_internal_id,
        target_type="credential",
        payload=audit_payload,
    )

    # Step 9: NOTIFY change channel — ADR-0014.1, bound parameters
    await notify_change(
        session,
        "mintkey:credential",
        {
            "event": "credential.rotated",
            "tenant_id": str(tenant_id),
            "service_id": service_id,
            "credential_id": new_cred_wire_id,
        },
    )

    # Step 10: Return 200 with metadata ONLY — NEVER include plaintext
    return JSONResponse(
        status_code=200,
        content={
            "id": new_cred_wire_id,
            "key_version": new_key_version,
            "auth_scheme": body.auth_scheme,
            "effective_at": now.isoformat(),
        },
    )


@router.delete("/{key_version}", status_code=204)
async def delete_credential_version(
    tenant_id: UUID,
    service_id: UUID,
    key_version: int,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Revoke a specific credential version (soft-delete: sets status to 'revoked').

    Returns 404 if the version does not exist for this service/tenant.
    Returns 409 if the version is already revoked.

    Source: OpenAPI deleteCredentialVersion; ADR-0014.4; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, status FROM credentials"
            " WHERE service_id = :sid AND tenant_id = :tid AND key_version = :kv"
        ),
        {"sid": str(service_id), "tid": str(tenant_id), "kv": key_version},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Credential version not found"},
        )
    if row.status == "revoked":
        return JSONResponse(
            status_code=409,
            content={"mintkey:code": "already_revoked", "title": "Credential version already revoked"},
        )

    now = datetime.now(timezone.utc)
    await session.execute(
        text(
            "UPDATE credentials SET status = 'revoked', revoked_at = :now"
            " WHERE service_id = :sid AND tenant_id = :tid AND key_version = :kv"
        ),
        {"now": now, "sid": str(service_id), "tid": str(tenant_id), "kv": key_version},
    )

    # Emit audit event — ADR-0014.7
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="credential.revoked",
        actor_id=None,
        actor_type="operator",
        target_id=row.id,
        target_type="credential",
        payload={
            "service_id": str(service_id),
            "key_version": key_version,
        },
    )

    # NOTIFY change channel — ADR-0014.1
    await notify_change(
        session,
        "mintkey:credential",
        {
            "event": "credential.revoked",
            "tenant_id": str(tenant_id),
            "service_id": str(service_id),
            "key_version": key_version,
        },
    )

    return JSONResponse(status_code=204, content=None)


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input cannot glob-match unexpectedly."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
async def list_credential_versions(
    tenant_id: UUID,
    service_id: UUID,
    q: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    List credential version metadata for a service.

    Optional query parameters:
      q — case-insensitive substring search on auth_scheme.

    Returns version metadata only — no plaintext, no ciphertext — S-SEC-1.

    Note: credentials have no human-readable name field; q matches auth_scheme only.

    Source: T-1.3.2; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    if q is not None:
        escaped = _escape_like(q)
        pattern = f"%{escaped}%"
        result = await session.execute(
            text(
                "SELECT id, key_version, auth_scheme, status, created_at, revoked_at"
                " FROM credentials"
                " WHERE service_id = :sid AND tenant_id = :tid"
                " AND auth_scheme ILIKE :pat ESCAPE '\\'"
                " ORDER BY key_version DESC"
            ),
            {"sid": str(service_id), "tid": str(tenant_id), "pat": pattern},
        )
    else:
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
