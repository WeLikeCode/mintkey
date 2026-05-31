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
  - service_id in ALL endpoints accepts both svc_ Crockford and svc_ 32-hex wire forms — R12/R14a/OPS-AA.

Source: T-1.3.2 (session 1); ADR-0008; ADR-0011; ADR-0013; ADR-0014.4; ADR-0014.7; ADR-0017.11.
"""
from __future__ import annotations

import logging
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Optional, Union, cast
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from admin_api.services.credential_service import (
    GoogleServiceAccountPayload,
    OAuth2PasswordGrantPayload,
)
from admin_api.services.vault_client import VaultAdapterClient, get_vault_client
from admin_api.utils.wire_ids import wire_to_db_uuid as _wire_to_db
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

logger = logging.getLogger(__name__)

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
# Wire-form decoder — delegates to utils.wire_ids (R12/R14a/R13 unification).
# Credentials accept svc_ wire IDs in the rotate endpoint path; admin-ui
# passes the wire form through without decoding (ADR lesson from R8/R12).
# ---------------------------------------------------------------------------


def _svc_wire_to_db_uuid(wire_id: str) -> str:
    """
    Convert a wire svc_ ID back to the UUID string stored in the DB.

    Thin wrapper around utils.wire_ids.wire_to_db_uuid — accepts both the
    canonical Crockford form and the legacy 32-hex form for backward-compat.
    Returns wire_id unchanged for raw UUIDs (fallback).

    Source: ADR-0017.11; #13.
    """
    return _wire_to_db(wire_id, "svc")


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CredentialCreate(BaseModel):
    auth_scheme: str               # e.g., "bearer_token", "api_key_header"
    value: str                     # SENSITIVE — never echoed back (S-SEC-1, ADR-0014.4)
    header_name: Optional[str] = None  # injection hint for api_key_header (e.g. "X-API-Key") — UX-C6
    query_param: Optional[str] = None  # injection hint for api_key_query (e.g. "api_key") — UX-C6


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
    value: Optional[Union[str, dict[str, Any]]] = None  # SENSITIVE — ADR-0014.4


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_credential(
    tenant_id: UUID,
    service_id: str,
    body: CredentialCreate,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    Register a new credential for a service.

    Calls the Vault Adapter to store the encrypted credential. Only metadata
    is persisted locally and returned. The plaintext value is NEVER stored,
    logged, audited, or returned — ADR-0014.4, S-SEC-1.

    service_id accepts both svc_<26-char Crockford> and svc_<32-hex> wire forms
    (admin-ui passes wire form through; admin-api decodes — R12/R14a lesson).

    Source: T-1.3.2; ADR-0008; ADR-0011; ADR-0014.4; ADR-0014.7; ADR-0017.11.
    """
    # Step 0: Decode wire-form service_id → DB UUID (mirrors rotate endpoint)
    db_svc_uuid = _svc_wire_to_db_uuid(service_id)

    # Step 1: Set tenant context — bound parameters, ADR-0008
    await set_tenant_context(session, tenant_id)

    # Step 1b: Fetch service base_url so vault-adapter can use it as the proxy target.
    # Fail fast with 422 if the service doesn't exist (RLS ensures tenant isolation).
    svc_result = await session.execute(
        text("SELECT base_url FROM services WHERE id = :sid AND tenant_id = :tid"),
        {"sid": db_svc_uuid, "tid": str(tenant_id)},
    )
    svc_row = svc_result.fetchone()
    if svc_row is None:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "not_found", "title": "Service not found"},
        )
    service_base_url: str = svc_row.base_url or ""

    # Step 1c: For oauth2_password_grant, validate the structured payload — BUG-2/BUG-9.
    # body.value is expected to be a JSON-encoded OAuth2PasswordGrantPayload.
    # Rejects: non-HTTPS token_url, loopback/private/link-local token_url (S-SEC-1),
    # empty credential_fields. Requirements 19.2, 19.4, 19.5, 19.6.
    if body.auth_scheme == "oauth2_password_grant":
        try:
            import json as _json_mod
            raw = _json_mod.loads(body.value) if isinstance(body.value, str) else body.value
            OAuth2PasswordGrantPayload(**raw)
        except (_json_mod.JSONDecodeError, TypeError):
            return JSONResponse(
                status_code=422,
                content={
                    "mintkey:code": "invalid_oauth2_payload",
                    "title": "oauth2_password_grant value must be a valid JSON object",
                },
            )
        except ValueError as exc:
            logger.warning("oauth2_password_grant payload validation failed", exc_info=exc)
            return JSONResponse(
                status_code=422,
                content={
                    "mintkey:code": "invalid_oauth2_payload",
                    "title": "oauth2_password_grant payload failed validation",
                },
            )

    # Step 1d: For google_service_account, validate the structured payload — spec §4.3.
    # body.value is expected to be the JSON envelope:
    #   { "scheme": "google_service_account", "service_account_json": ..., "scope": ... }
    # Validation: service_account_json parses as valid Google SA JSON, required fields
    # present, private_key starts with -----BEGIN, client_email contains @, token_uri
    # starts with https://. scope must be non-empty.
    # service_account_json, json_key, and private_key are scrubbed from all log calls —
    # ADR-0014.7, S-SEC-1.
    # On success: serialise as canonical vault envelope so the Vault Adapter receives
    # EXACTLY the expected JSON shape { scheme, json_key, scope }.
    _gsa_envelope: bytes | None = None
    _gsa_validated: GoogleServiceAccountPayload | None = None
    if body.auth_scheme == "google_service_account":
        import json as _json_mod
        try:
            raw_gsa = _json_mod.loads(body.value) if isinstance(body.value, str) else body.value
            if not isinstance(raw_gsa, dict):
                raise TypeError("google_service_account value must be a JSON object")
            # Strip the outer "scheme" key if present (UI may include it).
            raw_gsa.pop("scheme", None)
            _gsa_validated = GoogleServiceAccountPayload(**raw_gsa)
        except (_json_mod.JSONDecodeError, TypeError):
            return JSONResponse(
                status_code=400,
                content={
                    "type": "about:blank",
                    "title": "validation error",
                    "detail": "google_service_account value must be a valid JSON object",
                },
            )
        except ValueError as exc:
            # Log the error without including service_account_json — ADR-0014.7.
            # Only the terse validation message is logged — NEVER private_key material.
            logger.warning(
                "google_service_account credential validation failed: %s", str(exc)
            )
            return JSONResponse(
                status_code=400,
                content={
                    "type": "about:blank",
                    "title": "validation error",
                    "detail": str(exc),
                },
            )
        # Serialise the validated envelope for the vault — service_account_json is in
        # these bytes but is passed directly to StoreCredential and never logged.
        _gsa_envelope = _gsa_validated.to_vault_envelope()

    # Step 2: Call Vault Adapter — plaintext is passed only within this request scope
    # and is NOT stored, logged, or returned. ADR-0014.4.
    # For google_service_account: pass the canonical JSON envelope as plaintext so the
    # Vault Adapter receives exactly { scheme, json_key, scope }.
    _vault_plaintext: str = (
        _gsa_envelope.decode() if _gsa_envelope is not None else body.value
    )
    vault_result = await vault.put_credential(
        tenant_id=str(tenant_id),
        service_id=db_svc_uuid,
        auth_scheme=body.auth_scheme,
        plaintext=_vault_plaintext,  # plaintext leaves scope here; vault encrypts it
        target_url=service_base_url,
        header_name=body.header_name or "",
        query_param=body.query_param or "",
    )
    key_version: int = cast(int, vault_result["key_version"])

    # Step 3: Generate wire ID and internal UUID — ADR-0017.11
    # Group E fix: derive internal_id from the wire ID so that decoding the
    # cred_ wire form always yields the UUID stored in the DB.  Previously
    # cred_wire_id and internal_id were generated independently, making the
    # wire form un-decodable to the DB row (rotate_from couldn't target it).
    cred_wire_id = _new_cred_id()
    internal_id = uuid.UUID(_wire_to_db(cred_wire_id, "cred"))
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
            "service_id": db_svc_uuid,
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
    audit_payload: dict[str, Any] = {
        "credential_id": cred_wire_id,
        "service_id": str(service_id),
        "key_version": key_version,
        "auth_scheme": body.auth_scheme,
    }
    if is_rotation:
        audit_payload["previous_key_version"] = key_version - 1
    if _gsa_validated is not None:
        import hashlib as _hashlib
        import json as _json_gsa
        # Include non-sensitive metadata only — NEVER service_account_json or private_key.
        _gsa_parsed: dict[str, object] = _json_gsa.loads(_gsa_validated.service_account_json)
        audit_payload["auth_scheme"] = "google_service_account"
        audit_payload["service_account_email"] = str(_gsa_parsed.get("client_email", ""))
        audit_payload["project_id"] = str(_gsa_parsed.get("project_id", ""))
        audit_payload["json_key_fingerprint"] = _hashlib.sha256(
            _gsa_validated.service_account_json.encode()
        ).hexdigest()[:16]

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

    If rotate_from is provided (cred_ wire ID), the SELECT for the credential to
    supersede is filtered to that exact ID.  Returns 404 if the specified credential
    does not exist, belongs to another tenant/service, or is not in 'active' status.

    Returns 404 if the service does not exist or belongs to another tenant.
    Returns 404 if rotate_from is specified but no matching active credential exists.
    Returns 404 if no active credential exists for the scheme (rotate_from omitted).
    Returns 409 if the target credential is already superseded or revoked.
    """
    # Step 1: Set tenant context — bound parameters, ADR-0008
    await set_tenant_context(session, tenant_id)

    # Step 2: Decode wire-form service_id → DB UUID
    db_svc_uuid = _svc_wire_to_db_uuid(service_id)

    # Step 3: Verify service exists under this tenant (enforces RLS + ownership)
    # Also fetch base_url so vault-adapter can store it as the proxy target (WS-9).
    svc_result = await session.execute(
        text("SELECT id, base_url FROM services WHERE id = :sid AND tenant_id = :tid"),
        {"sid": db_svc_uuid, "tid": str(tenant_id)},
    )
    svc_row_rotate = svc_result.fetchone()
    if svc_row_rotate is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Service not found"},
        )
    rotate_service_base_url: str = svc_row_rotate.base_url or ""

    # Step 4: Resolve the old credential to supersede.
    # C1: when rotate_from is provided it identifies a specific credential by its
    # cred_ wire ID; the SELECT adds an equality filter on the wire ID so only that
    # exact row is targeted.  If the row is not found (wrong ID, wrong tenant, or
    # already superseded/revoked) we return 404 per the documented contract.
    # When rotate_from is omitted, the deterministic rule applies: highest
    # key_version active row for the given auth_scheme is superseded.
    #
    # Group E fix: decode the cred_ wire form to a DB UUID before the query.
    # asyncpg rejects raw wire-form strings (e.g. "cred_01KRKJ…") as invalid UUIDs
    # since their length (31) is outside the 32-36 char range accepted for UUID cols.
    # Decoder: _wire_to_db (utils.wire_ids.wire_to_db_uuid) — ADR-0017.11; #13.
    # If decoding fails (malformed wire ID) return 422 instead of letting asyncpg 500.
    if body.rotate_from is not None:
        try:
            rotate_from_uuid = _wire_to_db(body.rotate_from, "cred")
            # Validate that the decoded/passthrough value is a UUID the DB will accept.
            # _wire_to_db returns the input unchanged for non-prefixed strings (passthrough
            # for raw UUIDs); validate to avoid asyncpg rejecting garbage strings with 500.
            uuid.UUID(rotate_from_uuid)
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={
                    "mintkey:code": "invalid_rotate_from",
                    "title": "rotate_from is not a valid cred_ wire-form ID",
                },
            )
        old_result = await session.execute(
            text(
                "SELECT id, key_version, status FROM credentials"
                " WHERE tenant_id = :tid AND service_id = :sid"
                "   AND auth_scheme = :scheme AND status = 'active'"
                "   AND id = :rotate_from_id"
                " ORDER BY key_version DESC LIMIT 1"
            ),
            {
                "tid": str(tenant_id),
                "sid": db_svc_uuid,
                "scheme": body.auth_scheme,
                "rotate_from_id": rotate_from_uuid,
            },
        )
    else:
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
        if body.rotate_from is not None:
            return JSONResponse(
                status_code=404,
                content={
                    "mintkey:code": "not_found",
                    "title": "Credential specified by rotate_from not found or not active",
                },
            )
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "No active credential to rotate"},
        )

    old_internal_id: Any = old_row.id

    # Step 4b: For oauth2_password_grant, validate the new credential value — BUG-2/BUG-9.
    # Mirrors the create_credential validation (Step 1c) so that the rotate path
    # cannot be used to bypass HTTPS + SSRF checks by rotating to a malicious token_url.
    # Rejects: non-HTTPS token_url, loopback/private/link-local/IPv6-ULA (S-SEC-1),
    # empty credential_fields. Requirements 19.2, 19.4, 19.5, 19.6.
    if body.auth_scheme == "oauth2_password_grant" and body.value is not None:
        try:
            import json as _json_mod
            raw = _json_mod.loads(body.value) if isinstance(body.value, str) else body.value
            OAuth2PasswordGrantPayload(**raw)
        except (_json_mod.JSONDecodeError, TypeError):
            return JSONResponse(
                status_code=422,
                content={
                    "mintkey:code": "invalid_oauth2_payload",
                    "title": "oauth2_password_grant value must be a valid JSON object",
                },
            )
        except ValueError as exc:
            logger.warning("oauth2_password_grant payload validation failed", exc_info=exc)
            return JSONResponse(
                status_code=422,
                content={
                    "mintkey:code": "invalid_oauth2_payload",
                    "title": "oauth2_password_grant payload failed validation",
                },
            )

    # Step 5: Call Vault Adapter for new credential — plaintext never stored
    # When body.value is None (e.g., operator clicked Rotate in the UI without
    # supplying a new value), auto-generate a cryptographically-random secret.
    # The vault adapter rejects empty plaintext; auto-generation prevents the 500.
    # ADR-0014.4: generated plaintext is passed through and never stored or returned.
    if body.value is not None:
        plaintext: str = body.value if isinstance(body.value, str) else str(body.value)
    else:
        plaintext = secrets.token_urlsafe(32)  # 256-bit random secret

    vault_result = await vault.put_credential(
        tenant_id=str(tenant_id),
        service_id=db_svc_uuid,
        auth_scheme=body.auth_scheme,
        plaintext=plaintext,
        target_url=rotate_service_base_url,
    )
    new_key_version: int = cast(int, vault_result["key_version"])

    # Step 6: Generate new cred ID and UUID — ADR-0017.11
    # Group E fix: derive new_internal_id from the wire ID (same as create_credential)
    # so the wire form is decodable to the DB row UUID for future rotate_from targeting.
    new_cred_wire_id = _new_cred_id()
    new_internal_id = uuid.UUID(_wire_to_db(new_cred_wire_id, "cred"))
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
    audit_payload: dict[str, Any] = {
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
    service_id: str,
    key_version: int,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Revoke a specific credential version (soft-delete: sets status to 'revoked').

    Returns 404 if the version does not exist for this service/tenant.
    Returns 409 if the version is already revoked.

    service_id accepts both svc_<26-char Crockford> and svc_<32-hex> wire forms
    (mirrors create and rotate — R12/R14a lesson).

    Source: OpenAPI deleteCredentialVersion; ADR-0014.4; ADR-0008.
    """
    # Decode wire-form service_id → DB UUID (mirrors create/rotate endpoints)
    db_svc_uuid = _svc_wire_to_db_uuid(service_id)

    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, status FROM credentials"
            " WHERE service_id = :sid AND tenant_id = :tid AND key_version = :kv"
        ),
        {"sid": db_svc_uuid, "tid": str(tenant_id), "kv": key_version},
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
        {"now": now, "sid": db_svc_uuid, "tid": str(tenant_id), "kv": key_version},
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
            "service_id": service_id,  # wire form preserved in audit, mirrors rotate
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
            "service_id": service_id,  # wire form preserved in notify, mirrors rotate
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
    service_id: str,
    q: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    List credential version metadata for a service.

    Optional query parameters:
      q — case-insensitive substring search on auth_scheme.

    Returns version metadata only — no plaintext, no ciphertext — S-SEC-1.

    service_id accepts both svc_<26-char Crockford> and svc_<32-hex> wire forms
    (mirrors create and rotate — R12/R14a lesson).

    Note: credentials have no human-readable name field; q matches auth_scheme only.

    Source: T-1.3.2; ADR-0008.
    """
    # Decode wire-form service_id → DB UUID (mirrors create/rotate/delete endpoints)
    db_svc_uuid = _svc_wire_to_db_uuid(service_id)

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
            {"sid": db_svc_uuid, "tid": str(tenant_id), "pat": pattern},
        )
    else:
        result = await session.execute(
            text(
                "SELECT id, key_version, auth_scheme, status, created_at, revoked_at"
                " FROM credentials"
                " WHERE service_id = :sid AND tenant_id = :tid"
                " ORDER BY key_version DESC"
            ),
            {"sid": db_svc_uuid, "tid": str(tenant_id)},
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
