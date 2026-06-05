"""
Per-tenant OAuth2 client configuration endpoints (feat/oauth2-providers-per-tenant-vault).

Operator-facing:
  POST   /v1/tenants/{tenant_id}/oauth2-providers/{provider}   (201)
      Configure (or replace) the OAuth2 client credentials for a provider.
      Body: {client_id, client_secret}
      Response: {provider, client_id_last4, configured_at}
      NEVER echoes client_secret in any response (NFR-17).

  GET    /v1/tenants/{tenant_id}/oauth2-providers              (200)
      List configured providers for the tenant.
      Response: {providers: [{provider, client_id_last4, configured_at}]}

  GET    /v1/tenants/{tenant_id}/oauth2-providers/{provider}   (200)
      Fetch a single provider config (no secret returned).
      Response: {provider, client_id_last4, configured_at}

  DELETE /v1/tenants/{tenant_id}/oauth2-providers/{provider}   (204)
      Remove a provider config and revoke the vault credential.

Vault integration (Option A — feat spec §Layer 2):
  client_id is stored in cleartext in oauth2_client_configs.client_id.
  client_secret is stored via vault.put_credential with:
    - auth_scheme = "email_oauth2_client"   (new enum value 17)
    - service_id  = "oauth2cfg_<provider>"  (synthetic, e.g. "oauth2cfg_gmail")
  This reuses the existing vault gRPC contract with zero new proto changes.

Audit events (NFR-17):
  - oauth2_provider.configured — payload: {provider, client_id_last4} — NO secret
  - oauth2_provider.deleted    — payload: {provider}

Security:
  - Responses NEVER include client_secret (not even last4).
  - Audit payloads NEVER include client_secret.
  - Bound parameters everywhere (no f-strings in text()).

Sources: feat/oauth2-providers-per-tenant-vault scope §Layer 3; ADR-0024; NFR-17.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.sessions import require_tenant_session
from admin_api.db.deps import get_db_session
from admin_api.services.vault_client import VaultAdapterClient, get_vault_client
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_SUPPORTED_PROVIDERS = {"gmail", "outlook"}

# Synthetic vault service_id pattern: "oauth2cfg_<provider>"
# e.g. "oauth2cfg_gmail", "oauth2cfg_outlook"
_VAULT_SERVICE_ID_PREFIX = "oauth2cfg_"

# Vault auth_scheme for OAuth2 client secrets (enum value 17)
_VAULT_AUTH_SCHEME = "email_oauth2_client"

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/v1/tenants/{tenant_id}/oauth2-providers")

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class OAuth2ProviderConfigBody(BaseModel):
    """Body for POST /v1/tenants/{tid}/oauth2-providers/{provider}."""

    client_id: str
    client_secret: str

    @field_validator("client_id", "client_secret")
    @classmethod
    def not_empty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("must not be empty")
        return v


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


# Stable per-(tenant, provider) namespace for the UUIDv5. Generated once via
# uuid.uuid4() and committed — any UUID works, this just disambiguates from
# accidental collisions with other UUIDv5 callers in the codebase.
_OAUTH2_CLIENT_VAULT_NAMESPACE = uuid.UUID("2f3a7b91-4c4e-5d6a-9e0f-a1b2c3d4e5f6")


def _vault_service_id(tenant_id: str | UUID, provider: str) -> str:
    """Deterministic UUID used as the vault service_id for the OAuth2 client config.

    The vault postgres backend's `service_id` column is typed UUID — synthetic
    strings like "oauth2cfg_gmail" don't cast. We derive a stable UUIDv5 from
    (tenant_id, provider) so every PUT/GET for the same tenant+provider hits the
    same vault row, while collisions across tenants or providers are impossible.

    Returned as a string because vault.put_credential takes string IDs.
    """
    return str(uuid.uuid5(_OAUTH2_CLIENT_VAULT_NAMESPACE, f"{tenant_id}:{provider}"))


def _client_id_last4(client_id: str) -> str:
    """Return last 4 chars of client_id for identification without exposure."""
    return client_id[-4:] if len(client_id) >= 4 else client_id


# ---------------------------------------------------------------------------
# POST /v1/tenants/{tenant_id}/oauth2-providers/{provider}
# ---------------------------------------------------------------------------


@router.post("/{provider}", status_code=201)
async def configure_oauth2_provider(
    tenant_id: UUID,
    provider: str,
    body: OAuth2ProviderConfigBody,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Configure (or replace) OAuth2 client credentials for a provider.

    Stores client_id in oauth2_client_configs; client_secret via vault with
    synthetic service_id "oauth2cfg_<provider>" and auth_scheme=email_oauth2_client.

    If a config already exists for this (tenant_id, provider), it is replaced
    (UPSERT pattern: UPDATE existing row + overwrite vault credential).

    Returns 422 for unsupported providers or empty fields.
    Returns 201 with {provider, client_id_last4, configured_at} on success.
    NEVER returns client_secret (NFR-17).

    Emits oauth2_provider.configured — payload: {provider, client_id_last4} (NO secret).

    Source: feat/oauth2-providers-per-tenant-vault §Layer 3.
    """
    if provider not in _SUPPORTED_PROVIDERS:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "unsupported_provider",
                "title": (
                    f"provider '{provider}' is not supported. "
                    f"Supported: {sorted(_SUPPORTED_PROVIDERS)}"
                ),
            },
        )

    # Defense-in-depth (#358): trim leading/trailing whitespace BEFORE persistence /
    # vault-store. Operator paste-with-leading-space silently produced configs that
    # Google rejected with `invalid_client` 401, requiring a manual SQL trim.
    # Per-field explicit `.strip()` rather than a global Pydantic str_strip_whitespace
    # to keep the blast radius small.
    client_id = (body.client_id or "").strip()
    client_secret = (body.client_secret or "").strip()
    if not client_id:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "invalid_client_id",
                "title": "client_id must not be empty or whitespace",
            },
        )
    if not client_secret:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "invalid_client_secret",
                "title": "client_secret must not be empty or whitespace",
            },
        )

    await set_tenant_context(session, tenant_id)

    # Store client_secret in vault — plaintext leaves scope after this call
    vault_service_id = _vault_service_id(tenant_id, provider)
    try:
        await vault.put_credential(
            tenant_id=str(tenant_id),
            service_id=vault_service_id,
            auth_scheme=_VAULT_AUTH_SCHEME,
            plaintext=client_secret,  # NEVER logged or returned
        )
    except Exception as exc:
        logger.error(
            "configure_oauth2_provider: vault put_credential failed provider=%s tenant=%s: %s",
            provider,
            tenant_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=502,
            content={"mintkey:code": "vault_error", "title": "Failed to store credential in vault"},
        )

    # Upsert client_id row in oauth2_client_configs
    now = datetime.now(timezone.utc)
    last4 = _client_id_last4(client_id)

    await session.execute(
        text(
            "INSERT INTO oauth2_client_configs"
            " (tenant_id, provider, client_id, created_at, updated_at)"
            " VALUES (:tid, :provider, :client_id, :now, :now)"
            " ON CONFLICT (tenant_id, provider)"
            " DO UPDATE SET client_id = :client_id, updated_at = :now"
        ),
        {
            "tid": str(tenant_id),
            "provider": provider,
            "client_id": client_id,
            "now": now,
        },
    )

    # Emit audit event — NO client_secret in payload (NFR-17)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="oauth2_provider.configured",
        actor_id=None,
        actor_type="operator",
        target_id=tenant_id,
        target_type="tenant",
        payload={
            "provider": provider,
            "client_id_last4": last4,
            # client_secret NEVER appears here (NFR-17)
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "provider": provider,
            "client_id_last4": last4,
            "configured_at": now.isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# GET /v1/tenants/{tenant_id}/oauth2-providers
# ---------------------------------------------------------------------------


@router.get("", status_code=200)
async def list_oauth2_providers(
    tenant_id: UUID,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    List configured OAuth2 providers for the tenant.

    Returns {providers: [{provider, client_id_last4, configured_at}]}.
    NEVER returns client_secret (NFR-17).

    Source: feat/oauth2-providers-per-tenant-vault §Layer 3.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT provider, client_id, updated_at"
            " FROM oauth2_client_configs"
            " WHERE tenant_id = :tid"
            " ORDER BY provider"
        ),
        {"tid": str(tenant_id)},
    )
    rows = result.fetchall()

    providers = [
        {
            "provider": row.provider,
            "client_id_last4": _client_id_last4(row.client_id),
            "configured_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]

    return JSONResponse({"providers": providers})


# ---------------------------------------------------------------------------
# GET /v1/tenants/{tenant_id}/oauth2-providers/{provider}
# ---------------------------------------------------------------------------


@router.get("/{provider}", status_code=200)
async def get_oauth2_provider(
    tenant_id: UUID,
    provider: str,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Fetch configuration for a single provider.

    Returns {provider, client_id_last4, configured_at}.
    Returns 404 if not configured.
    NEVER returns client_secret (NFR-17).

    Source: feat/oauth2-providers-per-tenant-vault §Layer 3.
    """
    if provider not in _SUPPORTED_PROVIDERS:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "unsupported_provider",
                "title": (
                    f"provider '{provider}' is not supported. "
                    f"Supported: {sorted(_SUPPORTED_PROVIDERS)}"
                ),
            },
        )

    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT provider, client_id, updated_at"
            " FROM oauth2_client_configs"
            " WHERE tenant_id = :tid AND provider = :provider"
        ),
        {"tid": str(tenant_id), "provider": provider},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={
                "mintkey:code": "not_found",
                "title": f"OAuth2 provider '{provider}' is not configured for this tenant",
            },
        )

    return JSONResponse(
        {
            "provider": row.provider,
            "client_id_last4": _client_id_last4(row.client_id),
            "configured_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    )


# ---------------------------------------------------------------------------
# DELETE /v1/tenants/{tenant_id}/oauth2-providers/{provider}
# ---------------------------------------------------------------------------


@router.delete("/{provider}", status_code=204)
async def delete_oauth2_provider(
    tenant_id: UUID,
    provider: str,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Remove the OAuth2 client config for a provider and revoke the vault credential.

    Idempotent for vault revocation: if the vault credential doesn't exist, that is fine.
    Returns 404 if the DB row doesn't exist.
    Returns 204 on success.

    Emits oauth2_provider.deleted — payload: {provider} (NFR-17).

    Source: feat/oauth2-providers-per-tenant-vault §Layer 3.
    """
    if provider not in _SUPPORTED_PROVIDERS:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "unsupported_provider",
                "title": (
                    f"provider '{provider}' is not supported. "
                    f"Supported: {sorted(_SUPPORTED_PROVIDERS)}"
                ),
            },
        )

    await set_tenant_context(session, tenant_id)

    # Delete the DB row
    delete_result = await session.execute(
        text(
            "DELETE FROM oauth2_client_configs"
            " WHERE tenant_id = :tid AND provider = :provider"
            " RETURNING id"
        ),
        {"tid": str(tenant_id), "provider": provider},
    )
    deleted_row = delete_result.fetchone()
    if deleted_row is None:
        return JSONResponse(
            status_code=404,
            content={
                "mintkey:code": "not_found",
                "title": f"OAuth2 provider '{provider}' is not configured for this tenant",
            },
        )

    # Revoke vault credential — idempotent (empty value overwrites)
    vault_service_id = _vault_service_id(tenant_id, provider)
    try:
        existing = await vault.get_credential(
            tenant_id=str(tenant_id), service_id=vault_service_id
        )
        if existing is not None:
            await vault.put_credential(
                tenant_id=str(tenant_id),
                service_id=vault_service_id,
                auth_scheme=_VAULT_AUTH_SCHEME,
                plaintext="",  # revoke by overwriting with empty
            )
    except Exception as exc:
        logger.error(
            "delete_oauth2_provider: vault revocation failed provider=%s tenant=%s: %s",
            provider,
            tenant_id,
            type(exc).__name__,
        )
        # Continue — DB row is deleted; vault failure is non-fatal for the response
        # but logged for operator investigation.

    # Emit audit event (NFR-17: only provider name, NO secret)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="oauth2_provider.deleted",
        actor_id=None,
        actor_type="operator",
        target_id=tenant_id,
        target_type="tenant",
        payload={"provider": provider},
    )

    return JSONResponse(status_code=204, content=None)
