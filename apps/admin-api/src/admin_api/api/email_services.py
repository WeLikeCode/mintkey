"""
Email service CRUD + OAuth2 flow endpoints (ADR-0024, C-9).

Operator-facing:
  POST /v1/tenants/{tenant_id}/email-services
      Register an email service (email_password / email_app_password / email_oauth2).

  POST /v1/tenants/{tenant_id}/email-services/from-template
      Create an email service from a catalog template (new in feat/email-service-templates).
      Takes {template_id, name?} and pre-fills imap/smtp/auth_scheme/provider from YAML.
      Emits email.service.registered audit event.

  POST /v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/authorize
      Start the OAuth2 authorization code flow for gmail|outlook.
      Returns {authorize_url}.

  POST /v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/callback
      Receive the auth-code, exchange for refresh_token, encrypt via vault,
      emit email.oauth2.authorized audit event.

Internal (email-proxy → admin-api):
  POST /v1/internal/oauth2/{provider}/refresh?service_id=...
      Exchange stored refresh_token for a fresh access_token.
      Authenticated by X-Mintkey-Service-Token (MINTKEY_EMAIL_PROXY_SERVICE_TOKEN).
      Emits email.oauth2.expired on 401 from provider.
      Payload MUST NOT include refresh_token, client_secret, or access_token (NFR-17).

OAuth2 client credentials (OQ-3):
  MINTKEY_OAUTH2_GMAIL_CLIENT_ID / MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET
  MINTKEY_OAUTH2_OUTLOOK_CLIENT_ID / MINTKEY_OAUTH2_OUTLOOK_CLIENT_SECRET
  Missing any of these logs a WARNING and makes OAuth2 endpoints return 503.

Source: ADR-0024; .kiro/specs/email-proxy/design.md; chunk C-9.
from-template endpoint: feat/email-service-templates.
"""
from __future__ import annotations

import logging
import os
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID

import hashlib

import httpx
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
# OAuth2 provider configuration
# ---------------------------------------------------------------------------

_GMAIL_TOKEN_URL = "https://oauth2.googleapis.com/token"
_OUTLOOK_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"

_GMAIL_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
_OUTLOOK_AUTH_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"

# Gmail profile endpoint — used to resolve the authorized user's emailAddress
# during the OAuth2 exchange so that the email-proxy XOAUTH2 path has the
# username it needs (IMAP XOAUTH2 requires user=<email>). The `gmail.readonly`
# scope (already in _GMAIL_SCOPES) is sufficient to call this endpoint.
_GMAIL_USERINFO_URL = "https://www.googleapis.com/gmail/v1/users/me/profile"

_GMAIL_SCOPES = (
    "https://mail.google.com/ "
    "https://www.googleapis.com/auth/gmail.send "
    "https://www.googleapis.com/auth/gmail.readonly"
)
_OUTLOOK_SCOPES = (
    "https://outlook.office.com/IMAP.AccessAsUser.All "
    "https://outlook.office.com/SMTP.Send "
    "offline_access"
)

_SUPPORTED_PROVIDERS = {"gmail", "outlook"}

# ---------------------------------------------------------------------------
# Lazy OAuth2 client config — read at first use so tests can inject env vars
# ---------------------------------------------------------------------------


def _oauth2_config(provider: str) -> tuple[str, str] | None:
    """
    DEPRECATED (env-var path): Return (client_id, client_secret) from env vars.

    This synchronous helper is kept for backwards compatibility and for use in
    tests / contexts where no DB session is available.  Production code should
    use _oauth2_config_from_db() instead, which reads from the per-tenant
    oauth2_client_configs table.

    Env-var fallback is still honoured for operators who have not yet migrated.
    When env vars are used, a deprecation warning is emitted.
    """
    if provider == "gmail":
        cid = os.environ.get("MINTKEY_OAUTH2_GMAIL_CLIENT_ID", "")
        csecret = os.environ.get("MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET", "")
    elif provider == "outlook":
        cid = os.environ.get("MINTKEY_OAUTH2_OUTLOOK_CLIENT_ID", "")
        csecret = os.environ.get("MINTKEY_OAUTH2_OUTLOOK_CLIENT_SECRET", "")
    else:
        return None
    if not cid or not csecret:
        logger.warning(
            "OAuth2 env vars missing for provider=%s — OAuth2 endpoints will return 503",
            provider,
        )
        return None
    return cid, csecret


async def _oauth2_config_from_db(
    tenant_id: UUID,
    provider: str,
    session: Any,
    vault: Any,
) -> Optional[tuple[str, str]]:
    """
    Return (client_id, client_secret) for provider, reading from the per-tenant
    oauth2_client_configs table first, then falling back to env vars.

    Flow:
      1. SELECT from oauth2_client_configs WHERE tenant_id=:tid AND provider=:p.
      2. If found, decrypt client_secret from vault (service_id=oauth2cfg_<p>).
      3. If NOT found in DB, fall back to env vars (deprecated path) with a
         deprecation warning (never logs the secret value).
      4. Return None if neither DB nor env vars are configured.

    This is the preferred helper for all OAuth2 handler callers.
    Source: feat/oauth2-providers-per-tenant-vault §Layer 4.
    """
    # --- Try the per-tenant DB config first ---
    # SECURITY: a DB exception MUST NOT silently fall through to the env-var
    # fallback below. That fallback uses GLOBAL credentials shared across all
    # tenants — silently substituting them when a tenant's DB row LOOKUP fails
    # (vs. genuinely missing) would let one tenant inherit another's GCP
    # client. On any DB error, return None immediately; the caller surfaces
    # this as 503 oauth2_not_configured. Operator can retry once DB is healthy.
    try:
        row_result = await session.execute(
            text(
                "SELECT client_id FROM oauth2_client_configs"
                " WHERE tenant_id = :tid AND provider = :provider"
            ),
            {"tid": str(tenant_id), "provider": provider},
        )
        row = row_result.fetchone()
    except Exception as exc:
        logger.error(
            "_oauth2_config_from_db: DB lookup failed provider=%s tenant=%s: %s "
            "(returning None — NOT falling back to env vars; tenant isolation)",
            provider,
            tenant_id,
            type(exc).__name__,
        )
        return None

    if row is not None:
        client_id: str = row.client_id
        # Deterministic UUIDv5 (must match the writer in oauth2_providers.py
        # _vault_service_id helper — the vault service_id column is UUID, so a
        # synthetic string like "oauth2cfg_<provider>" was rejected by postgres).
        _ns = uuid.UUID("2f3a7b91-4c4e-5d6a-9e0f-a1b2c3d4e5f6")
        vault_service_id = str(uuid.uuid5(_ns, f"{tenant_id}:{provider}"))
        try:
            cred = await vault.get_credential(
                tenant_id=str(tenant_id),
                service_id=vault_service_id,
            )
        except Exception as exc:
            logger.error(
                "_oauth2_config_from_db: vault get_credential failed provider=%s tenant=%s: %s",
                provider,
                tenant_id,
                type(exc).__name__,
            )
            return None

        if cred is None:
            logger.warning(
                "_oauth2_config_from_db: DB row found but vault has no credential "
                "for provider=%s tenant=%s — treating as unconfigured",
                provider,
                tenant_id,
            )
            return None

        client_secret: str = str(cred.get("plaintext", ""))
        if not client_secret:
            logger.warning(
                "_oauth2_config_from_db: vault credential is empty for provider=%s tenant=%s",
                provider,
                tenant_id,
            )
            return None

        return client_id, client_secret

    # --- Env-var fallback (deprecated) ---
    env_result = _oauth2_config(provider)
    if env_result is not None:
        logger.warning(
            "DEPRECATED: OAuth2 client credentials for provider=%s tenant=%s are loaded from "
            "environment variables. Migrate to per-tenant configuration via Admin UI → "
            "Email → OAuth2 Providers to remove this warning.",
            provider,
            tenant_id,
        )
        return env_result

    return None


def _oauth2_available(provider: str) -> bool:
    return _oauth2_config(provider) is not None


def _oauth2_redirect_base() -> str:
    """Return the public-facing base URL that the OAuth2 provider redirects browsers to.

    Inside docker compose, request.base_url resolves to http://admin-api:8080 which is
    unreachable from Google's servers.  Use MINTKEY_ADMIN_API_PUBLIC_URL instead.

    Falls back to http://localhost:8080 for `make dev` (no operator action needed).
    Production operators set MINTKEY_ADMIN_API_PUBLIC_URL in .env.
    """
    return os.environ.get(
        "MINTKEY_ADMIN_API_PUBLIC_URL",
        "http://localhost:8080",
    ).rstrip("/")


def _admin_ui_base() -> str:
    """Return the public-facing base URL of the admin-UI.

    Used by the GET OAuth2 callback view to build the post-auth redirect target
    (the admin-UI email-services show page).

    Falls back to http://localhost:8081 for `make dev`.
    Production operators set MINTKEY_ADMIN_UI_PUBLIC_URL in .env.
    """
    return os.environ.get(
        "MINTKEY_ADMIN_UI_PUBLIC_URL",
        "http://localhost:8081",
    ).rstrip("/")


# ---------------------------------------------------------------------------
# Email-proxy service token (for internal refresh endpoint)
# ---------------------------------------------------------------------------

_EMAIL_PROXY_TOKEN_VAR = "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN"


def _get_email_proxy_token() -> str:
    return os.environ.get(_EMAIL_PROXY_TOKEN_VAR, "")


# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/v1/tenants/{tenant_id}/email-services")
internal_oauth2_router = APIRouter(prefix="/v1/internal/oauth2")
oauth2_per_tenant_router = APIRouter(prefix="/v1/tenants/{tenant_id}/oauth2")

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

_VALID_PROVIDERS = {"gmail", "outlook", "generic"}
_VALID_AUTH_SCHEMES = {"email_password", "email_oauth2", "email_app_password"}

# Numeric vault auth_scheme for EMAIL_OAUTH2 — mirrors AuthScheme enum value
# in docs/architecture/contracts/vault-adapter/vault.proto:113.
_AUTH_SCHEME_EMAIL_OAUTH2 = 15

# Providers that support OAuth2
_OAUTH2_PROVIDERS = {"gmail", "outlook"}

# auth_scheme allowed per provider
_PROVIDER_AUTH_SCHEMES: dict[str, set[str]] = {
    "gmail": {"email_oauth2", "email_password", "email_app_password"},
    "outlook": {"email_oauth2", "email_password", "email_app_password"},
    "generic": {"email_password", "email_app_password"},
}


def _valid_host_port(host: str, port: int) -> bool:
    """Basic sanity: non-empty host, 1 ≤ port ≤ 65535."""
    return bool(host.strip()) and 1 <= port <= 65535


class EmailServiceCreate(BaseModel):
    provider: str
    name: str
    imap_host: str
    imap_port: int
    smtp_host: str
    smtp_port: int
    auth_scheme: str
    allowed_recipient_domains: Optional[str] = None
    pool_size_max: int = 5
    tls_insecure_skip_verify: bool = False

    @field_validator("provider")
    @classmethod
    def validate_provider(cls, v: str) -> str:
        if v not in _VALID_PROVIDERS:
            raise ValueError(f"provider must be one of {sorted(_VALID_PROVIDERS)}")
        return v

    @field_validator("auth_scheme")
    @classmethod
    def validate_auth_scheme(cls, v: str) -> str:
        if v not in _VALID_AUTH_SCHEMES:
            raise ValueError(f"auth_scheme must be one of {sorted(_VALID_AUTH_SCHEMES)}")
        return v

    @field_validator("imap_port", "smtp_port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not 1 <= v <= 65535:
            raise ValueError("port must be between 1 and 65535")
        return v


class EmailServiceFromTemplate(BaseModel):
    """Body for POST /v1/tenants/{tid}/email-services/from-template.

    Takes template_id from the email template catalog plus an optional
    operator-supplied name override.  imap_host/port, smtp_host/port,
    auth_scheme, and provider are pre-filled from the YAML template.

    Source: feat/email-service-templates.
    """

    template_id: str
    name: Optional[str] = None


class OAuth2CallbackBody(BaseModel):
    code: str
    state: str
    redirect_uri: Optional[str] = None


# Auth schemes supported by the credential-set endpoint (not OAuth2 — use the authorize flow)
_CREDENTIAL_SET_ALLOWED_SCHEMES = {"email_password", "email_app_password"}


class EmailServiceCredentialBody(BaseModel):
    username: str
    password: str
    auth_scheme: str

    @field_validator("auth_scheme")
    @classmethod
    def validate_credential_auth_scheme(cls, v: str) -> str:
        if v not in _VALID_AUTH_SCHEMES:
            raise ValueError(f"auth_scheme must be one of {sorted(_VALID_AUTH_SCHEMES)}")
        return v


# ---------------------------------------------------------------------------
# POST /v1/tenants/{tenant_id}/email-services
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_email_service(
    tenant_id: UUID,
    body: EmailServiceCreate,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Register a new email service.

    Validates provider / auth_scheme compatibility and host:port formats.
    Inserts a row into email_services under tenant_id RLS.
    Emits email.service.registered audit event (no secrets in payload — NFR-17).

    Source: ADR-0024; chunk C-9.
    """
    # Validate provider-auth_scheme compatibility
    allowed = _PROVIDER_AUTH_SCHEMES.get(body.provider, set())
    if body.auth_scheme not in allowed:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "incompatible_auth_scheme",
                "title": (
                    f"auth_scheme '{body.auth_scheme}' is not compatible with "
                    f"provider '{body.provider}'. Allowed: {sorted(allowed)}"
                ),
            },
        )

    # Validate host:port
    if not _valid_host_port(body.imap_host, body.imap_port):
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_imap", "title": "Invalid IMAP host or port"},
        )
    if not _valid_host_port(body.smtp_host, body.smtp_port):
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_smtp", "title": "Invalid SMTP host or port"},
        )

    await set_tenant_context(session, tenant_id)

    svc_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    await session.execute(
        text(
            "INSERT INTO email_services"
            " (id, tenant_id, provider, name, imap_host, imap_port,"
            "  smtp_host, smtp_port, auth_scheme, allowed_recipient_domains,"
            "  pool_size_max, tls_insecure_skip_verify, created_at, updated_at)"
            " VALUES"
            " (:id, :tenant_id, :provider, :name, :imap_host, :imap_port,"
            "  :smtp_host, :smtp_port, :auth_scheme, :allowed_domains,"
            "  :pool_size, :tls_insecure_skip_verify, :now, :now)"
        ),
        {
            "id": str(svc_id),
            "tenant_id": str(tenant_id),
            "provider": body.provider,
            "name": body.name,
            "imap_host": body.imap_host,
            "imap_port": body.imap_port,
            "smtp_host": body.smtp_host,
            "smtp_port": body.smtp_port,
            "auth_scheme": body.auth_scheme,
            "allowed_domains": body.allowed_recipient_domains,
            "pool_size": body.pool_size_max,
            "tls_insecure_skip_verify": body.tls_insecure_skip_verify,
            "now": now,
        },
    )

    # Emit audit event — payload contains NO credentials (NFR-17)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.service.registered",
        actor_id=None,
        actor_type="operator",
        target_id=svc_id,
        target_type="email_service",
        payload={
            "service_id": str(svc_id),
            "provider": body.provider,
            "name": body.name,
            "auth_scheme": body.auth_scheme,
            "imap_host": body.imap_host,
            "imap_port": body.imap_port,
            "smtp_host": body.smtp_host,
            "smtp_port": body.smtp_port,
            "tls_insecure_skip_verify": body.tls_insecure_skip_verify,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": str(svc_id),
            "tenant_id": str(tenant_id),
            "provider": body.provider,
            "name": body.name,
            "auth_scheme": body.auth_scheme,
            "imap_host": body.imap_host,
            "imap_port": body.imap_port,
            "smtp_host": body.smtp_host,
            "smtp_port": body.smtp_port,
            "tls_insecure_skip_verify": body.tls_insecure_skip_verify,
            "created_at": now.isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# POST /v1/tenants/{tenant_id}/email-services/from-template
# ---------------------------------------------------------------------------


@router.post("/from-template", status_code=201)
async def create_email_service_from_template(
    tenant_id: UUID,
    body: EmailServiceFromTemplate,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Create an email service from a catalog template (feat/email-service-templates).

    Looks up the template_id in the YAML registry — must be a kind=email_service
    template.  Pre-fills imap_host/port, smtp_host/port, auth_scheme, and provider
    from the template; operator may supply an optional name override.

    For email_oauth2 templates the row is created with no credential — operator
    must complete the OAuth2 flow via the authorize/callback endpoints afterward.

    Emits email.service.registered audit event (no secrets in payload — NFR-17).

    Returns 404 if template_id is not found.
    Returns 422 if the template is not an email_service kind.

    Source: feat/email-service-templates.
    """
    from admin_api.templates.registry import registry  # noqa: PLC0415

    # Look up template — 404 if not found
    template = registry.get(body.template_id)
    if template is None:
        return JSONResponse(
            status_code=404,
            content={
                "mintkey:code": "template_not_found",
                "title": f"Template '{body.template_id}' not found",
            },
        )

    # Must be an email_service template
    if template.kind != "email_service":
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "wrong_template_kind",
                "title": (
                    f"Template '{body.template_id}' has kind='{template.kind}'; "
                    "expected kind='email_service'"
                ),
            },
        )

    # Resolve name from override or template
    name = body.name if body.name else template.name

    # Template fields are pre-filled from YAML
    provider = template.provider or "generic"
    imap_host = template.imap_host or ""
    imap_port = template.imap_port or 993
    smtp_host = template.smtp_host or ""
    smtp_port = template.smtp_port or 587
    auth_scheme = template.auth_scheme or "email_password"

    # Generic IMAP+SMTP template has empty hosts — valid for creation (operator fills later)
    # For named providers (gmail, outlook, icloud), hosts are pre-filled from template.

    await set_tenant_context(session, tenant_id)

    svc_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    await session.execute(
        text(
            "INSERT INTO email_services"
            " (id, tenant_id, provider, name, imap_host, imap_port,"
            "  smtp_host, smtp_port, auth_scheme, allowed_recipient_domains,"
            "  pool_size_max, tls_insecure_skip_verify, created_at, updated_at)"
            " VALUES"
            " (:id, :tenant_id, :provider, :name, :imap_host, :imap_port,"
            "  :smtp_host, :smtp_port, :auth_scheme, NULL,"
            "  5, false, :now, :now)"
        ),
        {
            "id": str(svc_id),
            "tenant_id": str(tenant_id),
            "provider": provider,
            "name": name,
            "imap_host": imap_host,
            "imap_port": imap_port,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "auth_scheme": auth_scheme,
            "now": now,
        },
    )

    # Emit audit event — payload contains NO credentials (NFR-17)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.service.registered",
        actor_id=None,
        actor_type="operator",
        target_id=svc_id,
        target_type="email_service",
        payload={
            "service_id": str(svc_id),
            "provider": provider,
            "name": name,
            "auth_scheme": auth_scheme,
            "imap_host": imap_host,
            "imap_port": imap_port,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "template_id": template.template_id,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": str(svc_id),
            "tenant_id": str(tenant_id),
            "provider": provider,
            "name": name,
            "auth_scheme": auth_scheme,
            "imap_host": imap_host,
            "imap_port": imap_port,
            "smtp_host": smtp_host,
            "smtp_port": smtp_port,
            "template_id": template.template_id,
            "created_at": now.isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# POST /v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/authorize
# ---------------------------------------------------------------------------


@router.post("/{service_id}/oauth2/{provider}/authorize", status_code=200)
async def oauth2_authorize(
    tenant_id: UUID,
    service_id: str,
    provider: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    Start the OAuth2 authorization code flow for gmail|outlook.

    Generates a cryptographically random `state` value, inserts it into
    oauth2_state with a 10-minute TTL (opportunistic GC fires first),
    and returns the provider's authorization URL.

    Returns 422 if provider is not gmail|outlook.
    Returns 503 if OAuth2 client credentials are not configured.

    Source: ADR-0024 §B2; .kiro/specs/email-proxy/design.md; chunk C-9.
    Cred source: feat/oauth2-providers-per-tenant-vault §Layer 4 (_oauth2_config_from_db).
    """
    if provider not in _OAUTH2_PROVIDERS:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "unsupported_provider",
                "title": f"OAuth2 is only supported for {sorted(_OAUTH2_PROVIDERS)}",
            },
        )

    await set_tenant_context(session, tenant_id)

    creds = await _oauth2_config_from_db(tenant_id, provider, session, vault)
    if creds is None:
        return JSONResponse(
            status_code=503,
            content={
                "mintkey:code": "oauth2_not_configured",
                "title": f"OAuth2 credentials for provider '{provider}' are not configured",
            },
        )
    client_id, _ = creds

    # Verify the email service exists under this tenant (RLS enforces isolation)
    svc_row = await session.execute(
        text(
            "SELECT id FROM email_services"
            " WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"sid": service_id, "tid": str(tenant_id)},
    )
    if svc_row.fetchone() is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Email service not found"},
        )

    # Opportunistic GC: remove expired state rows before inserting
    await session.execute(
        text("DELETE FROM oauth2_state WHERE expires_at < now()")
    )

    # Generate state and compute expiry
    state_value = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=10)

    # Extract session context for operator binding
    # Use platform_admin_view-safe sentinel for operator_id when not available
    session_token = request.cookies.get("mintkey_session", "")
    operator_id_str = str(uuid.UUID(int=0))  # sentinel; overridden below if session present
    session_id_val = uuid.uuid4()

    if session_token:
        from admin_api.auth.sessions import validate_session as _validate_session
        ctx = await _validate_session(session_token)
        if ctx is not None:
            operator_id_str = str(ctx.operator_id)
            try:
                session_id_val = UUID(session_token)
            except ValueError:
                pass  # keep generated session_id

    redirect_uri = (
        _oauth2_redirect_base()
        + f"/v1/tenants/{tenant_id}/oauth2/{provider}/callback"
    )

    await session.execute(
        text(
            "INSERT INTO oauth2_state"
            " (state_value, session_id, operator_id, tenant_id, provider,"
            "  redirect_uri, created_at, expires_at, service_id)"
            " VALUES"
            " (:state, :session_id, :operator_id, :tenant_id, :provider,"
            "  :redirect_uri, :now, :expires, :service_id)"
        ),
        {
            "state": state_value,
            "session_id": str(session_id_val),
            "operator_id": operator_id_str,
            "tenant_id": str(tenant_id),
            "provider": provider,
            "redirect_uri": redirect_uri,
            "now": now,
            "expires": expires_at,
            "service_id": service_id,
        },
    )

    # Build the provider authorization URL
    if provider == "gmail":
        auth_url = (
            f"{_GMAIL_AUTH_URL}"
            f"?client_id={client_id}"
            f"&response_type=code"
            f"&scope={_GMAIL_SCOPES.replace(' ', '%20')}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state_value}"
            f"&access_type=offline"
            f"&prompt=consent"
        )
    else:  # outlook
        auth_url = (
            f"{_OUTLOOK_AUTH_URL}"
            f"?client_id={client_id}"
            f"&response_type=code"
            f"&scope={_OUTLOOK_SCOPES.replace(' ', '%20')}"
            f"&redirect_uri={redirect_uri}"
            f"&state={state_value}"
        )

    # Emit audit event — state_token_hash only; raw state value NEVER in payload (NFR-17)
    state_token_hash = hashlib.sha256(state_value.encode()).hexdigest()
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.oauth2.authorize_initiated",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(service_id) if _is_valid_uuid(service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            "tenant_id": str(tenant_id),
            "service_id": service_id,
            "provider": provider,
            "state_token_hash": state_token_hash,
        },
    )


    return JSONResponse(
        status_code=200,
        content={"authorize_url": auth_url, "state": state_value, "expires_at": expires_at.isoformat()},
    )


# ---------------------------------------------------------------------------
# Shared helper: validate state + exchange code for refresh_token + store in vault
# ---------------------------------------------------------------------------


def _parse_oauth2_plaintext(plaintext: str) -> str:
    """Return the refresh_token from a JSON envelope OR the raw string for legacy rows.

    The vault payload format introduced for the OAuth2 IMAP XOAUTH2 fix is a JSON
    envelope: {"provider": "...", "refresh_token": "...", "email_address": "..."}.
    Pre-fix vault rows stored the raw refresh_token string. This helper handles
    both: it tries JSON-decode; if the decoded value is a dict with a string
    `refresh_token` key, that is returned; otherwise the input is treated as the
    legacy raw refresh_token.

    NFR-17: input is sensitive (vault plaintext). Never logs the input or output.
    """
    import json as _json  # noqa: PLC0415

    if not plaintext:
        return ""
    try:
        envelope = _json.loads(plaintext)
    except _json.JSONDecodeError:
        return plaintext
    if isinstance(envelope, dict):
        rt = envelope.get("refresh_token")
        if isinstance(rt, str):
            return rt
    return plaintext


class _ExchangeResult:
    """Typed result returned by _exchange_oauth2_code_for_refresh_token."""

    __slots__ = (
        "ok",
        "service_id",
        "authorized_at",
        "token_type",
        "email_address",
        "error_code",
        "error_title",
        "http_status",
    )

    def __init__(
        self,
        *,
        ok: bool,
        service_id: str = "",
        authorized_at: str = "",
        token_type: str = "Bearer",
        email_address: str = "",
        error_code: str = "",
        error_title: str = "",
        http_status: int = 200,
    ) -> None:
        self.ok = ok
        self.service_id = service_id
        self.authorized_at = authorized_at
        self.token_type = token_type
        # email_address is the authorized user's email (resolved post-token-exchange
        # via the Gmail profile endpoint for provider=gmail; empty string for outlook
        # because the IMAP.AccessAsUser.All scope does not grant Graph access).
        # Operator-visible via the email.oauth2.authorized audit event payload.
        self.email_address = email_address
        self.error_code = error_code
        self.error_title = error_title
        self.http_status = http_status


async def _exchange_oauth2_code_for_refresh_token(
    *,
    tenant_id: UUID,
    service_id: str,
    provider: str,
    code: str,
    state: str,
    session: AsyncSession,
    vault: VaultAdapterClient,
    client_id: str,
    client_secret: str,
) -> _ExchangeResult:
    """Exchange an OAuth2 auth code for a refresh_token and store it in vault.

    Shared by the POST callback (programmatic) and GET callback (browser redirect).

    Steps:
      1. Look up and single-use-delete the state row from oauth2_state.
      2. POST to provider token endpoint with the auth code.
      3. Encrypt and store refresh_token via vault.put_credential.
      4. Emit email.oauth2.authorized audit event (NFR-17: no token material).

    Returns an _ExchangeResult.  Callers check .ok to decide the response shape.
    NEVER logs code / state / refresh_token / client_secret.
    """
    # Look up state — single-use, delete immediately
    state_result = await session.execute(
        text(
            "DELETE FROM oauth2_state"
            " WHERE state_value = :state"
            "   AND tenant_id = :tid"
            "   AND provider = :provider"
            "   AND expires_at > now()"
            " RETURNING service_id, redirect_uri, operator_id"
        ),
        {"state": state, "tid": str(tenant_id), "provider": provider},
    )
    state_row = state_result.fetchone()
    if state_row is None:
        return _ExchangeResult(
            ok=False,
            error_code="invalid_state",
            error_title="OAuth2 state is invalid, expired, or already used",
            http_status=422,
        )

    resolved_service_id = str(state_row.service_id) if state_row.service_id else service_id
    redirect_uri = str(state_row.redirect_uri)

    # Exchange auth code for tokens — server-side; client_secret never leaves admin-api
    token_url = _GMAIL_TOKEN_URL if provider == "gmail" else _OUTLOOK_TOKEN_URL
    exchange_payload: dict[str, str] = {
        "code": code,  # NEVER logged
        "client_id": client_id,
        "client_secret": client_secret,  # NEVER logged
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            resp = await http_client.post(token_url, data=exchange_payload)
    except httpx.HTTPError as exc:
        logger.error(
            "_exchange_oauth2_code: HTTP error calling provider=%s token endpoint: %s",
            provider,
            type(exc).__name__,
        )
        return _ExchangeResult(
            ok=False,
            error_code="provider_unreachable",
            error_title="Provider token endpoint unreachable",
            http_status=502,
        )

    if resp.status_code != 200:
        logger.warning(
            "_exchange_oauth2_code: provider returned %d for provider=%s (no secret in log)",
            resp.status_code,
            provider,
        )
        return _ExchangeResult(
            ok=False,
            error_code="provider_token_error",
            error_title=f"Provider returned {resp.status_code} during token exchange",
            http_status=502,
        )

    token_data: dict[str, Any] = resp.json()
    refresh_token: str = token_data.get("refresh_token", "")
    if not refresh_token:
        logger.warning(
            "_exchange_oauth2_code: provider returned no refresh_token for provider=%s",
            provider,
        )
        return _ExchangeResult(
            ok=False,
            error_code="no_refresh_token",
            error_title="Provider did not return a refresh_token",
            http_status=502,
        )

    # access_token is needed to call the Gmail profile endpoint (only).
    # NEVER logged. Discarded after the userinfo call.
    access_token: str = token_data.get("access_token", "")

    # Resolve the authorized user's email address.
    #
    # Gmail: GET /gmail/v1/users/me/profile with the access_token. The
    # `gmail.readonly` scope (already requested in _GMAIL_SCOPES) authorizes
    # this call. The returned `emailAddress` is required for the email-proxy
    # IMAP XOAUTH2 path (`user=<email>` SASL parameter).
    #
    # Outlook: the requested scopes are IMAP.AccessAsUser.All + SMTP.Send +
    # offline_access — none of those grant Microsoft Graph access, so we
    # cannot fetch /me from here. Store empty email_address; a follow-up
    # task can add a Graph scope + fetch step (out of scope for C-3).
    #
    # If the Gmail userinfo call fails we proceed with email_address="" so
    # the operator's authorization is not lost — the agent's IMAP login will
    # fail until they re-authorize (or a future migration backfills), which
    # is a smaller blast radius than aborting the whole flow.
    email_address: str = ""
    if provider == "gmail":
        try:
            async with httpx.AsyncClient(timeout=15.0) as profile_client:
                profile_resp = await profile_client.get(
                    _GMAIL_USERINFO_URL,
                    headers={"Authorization": f"Bearer {access_token}"},
                )
            if profile_resp.status_code == 200:
                profile_data: dict[str, Any] = profile_resp.json()
                candidate = profile_data.get("emailAddress")
                if isinstance(candidate, str):
                    email_address = candidate
                else:
                    logger.warning(
                        "_exchange_oauth2_code: gmail profile returned no emailAddress for service=%s",
                        resolved_service_id,
                    )
            else:
                logger.warning(
                    "_exchange_oauth2_code: gmail profile returned %d for service=%s — proceeding with empty email_address",
                    profile_resp.status_code,
                    resolved_service_id,
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "_exchange_oauth2_code: gmail profile fetch failed for service=%s provider=%s: %s — proceeding with empty email_address",
                resolved_service_id,
                provider,
                type(exc).__name__,
            )
    # else: provider == "outlook" — see comment above; intentionally no extra
    # call. email_address remains "".

    # Build the vault payload as a JSON envelope so the email-proxy can
    # extract both the refresh_token (for OAuth2 access_token exchange) and
    # the email_address (for IMAP XOAUTH2 SASL username). email-proxy's
    # parseEmailAddressFromPayload tolerates any shape — non-JSON legacy
    # rows simply yield emailAddress="".
    import json as _json  # noqa: PLC0415

    vault_plaintext = _json.dumps({
        "provider": provider,
        "refresh_token": refresh_token,
        "email_address": email_address,
    })

    # Store encrypted vault envelope — plaintext leaves scope after this call
    try:
        await vault.put_credential(
            tenant_id=str(tenant_id),
            service_id=resolved_service_id,
            auth_scheme="email_oauth2",
            plaintext=vault_plaintext,  # NEVER logged after this point
        )
    except Exception as exc:
        logger.error(
            "_exchange_oauth2_code: vault put_credential failed for service=%s: %s",
            resolved_service_id,
            type(exc).__name__,
        )
        return _ExchangeResult(
            ok=False,
            error_code="vault_error",
            error_title="Failed to store credential in vault",
            http_status=502,
        )
    finally:
        # NFR-17: scrub local copies of credential material as soon as the
        # vault call returns (success or failure). Mirrors the pattern in
        # set_email_service_credential.
        del vault_plaintext
        del refresh_token
        del access_token

    now = datetime.now(timezone.utc)

    # NOTE: audit_emit is intentionally NOT called here — the AST-based
    # write-handler audit-coverage scanner (test_audit_coverage.py) requires
    # every @router write handler to call audit_emit DIRECTLY. Callers
    # (oauth2_callback POST + oauth2_callback_view GET) must emit
    # email.oauth2.authorized on success — NO refresh_token, client_secret,
    # or access_token in the payload (NFR-17). The token_type returned in
    # _ExchangeResult is what those handlers should use. email_address is
    # returned so callers can include it in the audit payload (operator-
    # visible — same value lands in email_services.name after success).

    result = _ExchangeResult(
        ok=True,
        service_id=resolved_service_id,
        authorized_at=now.isoformat(),
        token_type=token_data.get("token_type", "Bearer"),
        email_address=email_address,
    )
    # Clear the local binding too (the value is already inside the result
    # object; that's intended, since callers add it to the audit payload).
    del email_address
    return result


# ---------------------------------------------------------------------------
# GET OAuth2 callback HTML page builder
# ---------------------------------------------------------------------------

_ERROR_MESSAGES: dict[str, str] = {
    "access_denied": "You declined to grant access. Please try again and click Allow.",
    "invalid_request": "The OAuth2 request was invalid. Please contact support.",
    "unauthorized_client": "This application is not authorized to request access. Please contact support.",
    "unsupported_response_type": "OAuth2 configuration error. Please contact support.",
    "invalid_scope": "The requested permissions are not available. Please contact support.",
    "server_error": "The authorization server encountered an error. Please try again.",
    "temporarily_unavailable": "The authorization server is temporarily unavailable. Please try again later.",
}


def _oauth2_callback_html(
    *,
    success: bool,
    service_id: str,
    error_code: str = "",
    error_description: str = "",
    admin_ui_origin: str,
) -> str:
    """Return a minimal HTML page for the OAuth2 browser-redirect callback.

    On success: posts a postMessage to window.opener and closes the popup.
    On error: shows a user-friendly message, posts error postMessage.
    If no opener (popup was blocked / user navigated directly), redirects the
    whole window to the admin-UI show page.

    Security:
    - NEVER echoes code, state, refresh_token, client_secret, or access_token.
    - admin_ui_origin is used verbatim as the postMessage target — the value
      comes from MINTKEY_ADMIN_UI_PUBLIC_URL (operator-controlled config), not
      user input, so it is safe to embed.
    - error_description is HTML-escaped before embedding (no XSS).
    """
    import html as _html

    if success:
        status_js = "ok"
        safe_desc = ""
        heading = "Authorization complete"
        body_text = "You can close this window."
        card_class = "success"
        redirect_qs = "oauth2_authorized=true"
    else:
        status_js = "error"
        # Map known error codes to friendly messages; fall back to escaped description.
        friendly = _ERROR_MESSAGES.get(error_code, "")
        if not friendly:
            friendly = _html.escape(error_description or error_code or "Unknown error")
        safe_desc = friendly
        heading = "Authorization failed"
        body_text = safe_desc
        card_class = "error"
        safe_error_code = _html.escape(error_code or "unknown_error")
        redirect_qs = f"oauth2_error={safe_error_code}"

    safe_service_id = _html.escape(service_id)
    # Build the admin-UI redirect target (standalone / popup-blocked fallback)
    show_url = (
        f"{admin_ui_origin}/admin/resources/email_services/records"
        f"/{safe_service_id}/show?{redirect_qs}"
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Mintkey – OAuth2 {'complete' if success else 'error'}</title>
  <style>
    body{{margin:0;padding:0;font-family:system-ui,sans-serif;
         background:#f0f4f8;display:flex;align-items:center;justify-content:center;min-height:100vh}}
    .card{{background:#fff;border-radius:8px;box-shadow:0 2px 12px rgba(0,0,0,.12);
           padding:2rem 2.5rem;max-width:400px;width:100%;text-align:center}}
    .success h1{{color:#166534}} .error h1{{color:#991b1b}}
    h1{{font-size:1.25rem;margin:0 0 .75rem}} p{{color:#374151;margin:0 0 1rem;font-size:.95rem}}
    small{{color:#6b7280;font-size:.8rem}}
  </style>
</head>
<body>
  <div class="card {card_class}">
    <h1>{heading}</h1>
    <p>{body_text}</p>
    <small>This window will close automatically.</small>
  </div>
  <script>
    (function(){{
      var MSG = {{type:"oauth2_callback",status:"{status_js}",service_id:"{safe_service_id}"}};
      var SHOW_URL = {repr(show_url)};
      try {{
        if (window.opener && !window.opener.closed) {{
          window.opener.postMessage(MSG, {repr(admin_ui_origin)});
          window.close();
        }} else {{
          window.location.replace(SHOW_URL);
        }}
      }} catch(e) {{
        window.location.replace(SHOW_URL);
      }}
    }})();
  </script>
</body>
</html>"""


# ---------------------------------------------------------------------------
# POST /v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/callback
# ---------------------------------------------------------------------------


@router.post("/{service_id}/oauth2/{provider}/callback", status_code=200)
async def oauth2_callback(
    tenant_id: UUID,
    service_id: str,
    provider: str,
    body: OAuth2CallbackBody,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    Receive the OAuth2 auth-code and complete the flow (programmatic / server-to-server).

    1. Validates `state` — single-use (DELETE after lookup).
    2. Exchanges `code` for `refresh_token` via the provider's token endpoint.
    3. Stores the encrypted `refresh_token` in vault.credentials
       (auth_scheme=email_oauth2) via put_credential.
    4. Emits email.oauth2.authorized audit event.

    The audit payload NEVER includes refresh_token, client_secret, or
    access_token (NFR-17).

    Returns 422 if state is missing/expired/mismatched.
    Returns 503 if OAuth2 client credentials are not configured.

    For browser-redirect flows (Google's RFC 6749 GET redirect), use the
    sibling GET handler below.

    Source: ADR-0024 §B2; chunk C-9.
    """
    if provider not in _OAUTH2_PROVIDERS:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "unsupported_provider",
                "title": f"OAuth2 is only supported for {sorted(_OAUTH2_PROVIDERS)}",
            },
        )

    await set_tenant_context(session, tenant_id)

    creds = await _oauth2_config_from_db(tenant_id, provider, session, vault)
    if creds is None:
        return JSONResponse(
            status_code=503,
            content={
                "mintkey:code": "oauth2_not_configured",
                "title": f"OAuth2 credentials for provider '{provider}' are not configured",
            },
        )
    client_id, client_secret = creds

    result = await _exchange_oauth2_code_for_refresh_token(
        tenant_id=tenant_id,
        service_id=service_id,
        provider=provider,
        code=body.code,
        state=body.state,
        session=session,
        vault=vault,
        client_id=client_id,
        client_secret=client_secret,
    )

    if not result.ok:
        return JSONResponse(
            status_code=result.http_status,
            content={"mintkey:code": result.error_code, "title": result.error_title},
        )

    # Emit audit event — NO refresh_token, client_secret, or access_token (NFR-17).
    # Emitted in the handler (not in the shared helper) so the write-handler
    # audit-coverage scanner sees a direct call (test_audit_coverage.py).
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.oauth2.authorized",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(result.service_id) if _is_valid_uuid(result.service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            "service_id": result.service_id,
            "provider": provider,
            "authorized_at": result.authorized_at,
            "token_type": result.token_type,
            # email_address is operator-visible already (lands in the
            # email_services.name column after successful auth) — recording
            # it in the audit event lets operators tie a row to its Google
            # account. Empty string for outlook (see helper docstring).
            "email_address": result.email_address,
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "service_id": result.service_id,
            "provider": provider,
            "authorized_at": result.authorized_at,
        },
    )


# ---------------------------------------------------------------------------
# GET /v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/callback
# ---------------------------------------------------------------------------


@router.get("/{service_id}/oauth2/{provider}/callback")
async def oauth2_callback_view(
    tenant_id: UUID,
    service_id: str,
    provider: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> HTMLResponse:
    """Handle Google/Outlook OAuth2 GET browser redirect after consent (C-9 callback view).

    Google performs a GET redirect to redirect_uri with ?code=...&state=...
    (or ?error=...&error_description=...) per RFC 6749.  The browser hits this
    endpoint directly — the existing POST handler is unreachable from the browser.

    Flow:
      1. If ?error= is present: render error page immediately (no code exchange).
      2. Validate state/code presence.
      3. Call _exchange_oauth2_code_for_refresh_token (shared with POST handler).
      4. Return HTML that:
         - Posts a postMessage to window.opener (popup pattern) and closes the window.
         - Falls back to navigating the whole window to the admin-UI show page when
           the popup was blocked or the user opened the URL directly.

    Security (NFR-17):
      - NEVER echoes code, state, refresh_token, client_secret, or access_token
        in the HTML body, response headers, or redirect query strings.
      - error_description is HTML-escaped before embedding.
      - Logs NOTHING at INFO/DEBUG that contains code or state.

    Source: ADR-0024 §B2; chunk C-9 ("C-9 callback view").
    """
    admin_ui_origin = _admin_ui_base()

    # --- Provider sent ?error=... (checked first: no code exchange needed) ---
    # This path fires even if the provider sent an error after OAuth2 was unconfigured
    # later, so we handle it before the creds guard to avoid 503 in front of the user.
    if error:
        logger.info(
            "oauth2_callback_view: provider returned error=%s for provider=%s service=%s",
            error,
            provider,
            service_id,
        )
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=service_id,
                error_code=error,
                error_description=error_description or "",
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=200,
        )

    # --- Provider / config guard (same as POST) ---
    if provider not in _OAUTH2_PROVIDERS:
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=service_id,
                error_code="unsupported_provider",
                error_description=f"OAuth2 is only supported for {sorted(_OAUTH2_PROVIDERS)}",
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=422,
        )

    # --- Require both code and state (before DB lookup — no point querying if missing) ---
    if not code or not state:
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=service_id,
                error_code="missing_params",
                error_description="OAuth2 callback is missing required parameters (code or state).",
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=422,
        )

    await set_tenant_context(session, tenant_id)

    creds = await _oauth2_config_from_db(tenant_id, provider, session, vault)
    if creds is None:
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=service_id,
                error_code="oauth2_not_configured",
                error_description=f"OAuth2 credentials for provider '{provider}' are not configured",
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=503,
        )
    client_id, client_secret = creds

    # --- Exchange code (shared helper — no duplication with POST handler) ---
    result = await _exchange_oauth2_code_for_refresh_token(
        tenant_id=tenant_id,
        service_id=service_id,
        provider=provider,
        code=code,        # NEVER echoed in HTML / logs
        state=state,      # NEVER echoed in HTML / logs
        session=session,
        vault=vault,
        client_id=client_id,
        client_secret=client_secret,
    )

    if not result.ok:
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=service_id,
                error_code=result.error_code,
                error_description=result.error_title,
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=result.http_status,
        )

    # Emit audit event — NO refresh_token, client_secret, or access_token (NFR-17).
    # Emitted in the handler (not in the shared helper) so the write-handler
    # audit-coverage scanner sees a direct call (test_audit_coverage.py).
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.oauth2.authorized",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(result.service_id) if _is_valid_uuid(result.service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            "service_id": result.service_id,
            "provider": provider,
            "authorized_at": result.authorized_at,
            "token_type": result.token_type,
            # email_address is operator-visible already (lands in the
            # email_services.name column after successful auth) — recording
            # it in the audit event lets operators tie a row to its Google
            # account. Empty string for outlook (see helper docstring).
            "email_address": result.email_address,
        },
    )

    return HTMLResponse(
        content=_oauth2_callback_html(
            success=True,
            service_id=result.service_id,
            admin_ui_origin=admin_ui_origin,
        ),
        status_code=200,
    )


# ---------------------------------------------------------------------------
# POST /v1/internal/oauth2/{provider}/refresh?service_id=...
# ---------------------------------------------------------------------------


@internal_oauth2_router.post("/{provider}/refresh", status_code=200)
async def oauth2_refresh(
    provider: str,
    service_id: str,
    tenant_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    Internal endpoint: email-proxy exchanges a stored refresh_token for
    a fresh access_token.

    Auth: X-Mintkey-Service-Token must equal MINTKEY_EMAIL_PROXY_SERVICE_TOKEN.
    On 401 from provider: emits email.oauth2.expired audit event.
    Payload NEVER contains refresh_token, client_secret, or access_token (NFR-17).

    Query params:
      service_id  — email service UUID
      tenant_id   — tenant UUID (required for RLS + audit)

    Source: ADR-0024; chunk C-9.
    """
    # Authenticate: must be the email-proxy service token
    expected_token = _get_email_proxy_token()
    svc_token = request.headers.get("X-Mintkey-Service-Token", "")
    if not expected_token or not svc_token or svc_token != expected_token:
        return JSONResponse(status_code=401, content={"mintkey:code": "unauthenticated"})

    if provider not in _OAUTH2_PROVIDERS:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "unsupported_provider",
                "title": f"OAuth2 refresh only supported for {sorted(_OAUTH2_PROVIDERS)}",
            },
        )

    # Parse tenant_id
    try:
        tenant_uuid = UUID(tenant_id)
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_tenant_id", "title": "tenant_id is not a valid UUID"},
        )

    await set_tenant_context(session, tenant_uuid)

    creds = await _oauth2_config_from_db(tenant_uuid, provider, session, vault)
    if creds is None:
        return JSONResponse(
            status_code=503,
            content={
                "mintkey:code": "oauth2_not_configured",
                "title": f"OAuth2 credentials for provider '{provider}' are not configured",
            },
        )
    client_id, client_secret = creds

    # Fetch encrypted refresh_token from vault
    try:
        cred = await vault.get_credential(tenant_id=tenant_id, service_id=service_id)
    except Exception as exc:
        logger.error(
            "oauth2_refresh: vault.get_credential failed for service=%s: %s",
            service_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=502,
            content={"mintkey:code": "vault_error", "title": "Could not retrieve credential from vault"},
        )

    if cred is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "No credential found for this email service"},
        )

    # Vault payload may be either the new JSON envelope
    # ({"provider","refresh_token","email_address"}) or — for rows written
    # before the OAuth2 IMAP XOAUTH2 fix — the raw refresh_token string.
    # _parse_oauth2_plaintext handles both shapes.
    refresh_token: str = _parse_oauth2_plaintext(cred.get("plaintext", ""))  # type: ignore[arg-type]
    if not refresh_token:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Stored credential is empty"},
        )

    # Call provider /token with refresh_token — client_secret NEVER logged
    token_url = _GMAIL_TOKEN_URL if provider == "gmail" else _OUTLOOK_TOKEN_URL
    refresh_payload: dict[str, str] = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,  # NEVER logged
        "client_id": client_id,
        "client_secret": client_secret,  # NEVER logged
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as http_client:
            resp = await http_client.post(token_url, data=refresh_payload)
    except httpx.HTTPError as exc:
        logger.error(
            "oauth2_refresh: HTTP error calling provider=%s token endpoint: %s",
            provider,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=502,
            content={"mintkey:code": "provider_unreachable", "title": "Provider token endpoint unreachable"},
        )

    if resp.status_code == 401:
        # Refresh token expired or revoked — emit audit event
        logger.warning(
            "oauth2_refresh: provider returned 401 for service=%s provider=%s — emitting email.oauth2.expired",
            service_id,
            provider,
        )
        await audit_emit(
            session=session,
            tenant_id=tenant_uuid,
            event_type="email.oauth2.expired",
            actor_id=None,
            actor_type="system",
            target_id=UUID(service_id) if _is_valid_uuid(service_id) else uuid.uuid4(),
            target_type="email_service",
            payload={
                # NFR-17: NO refresh_token, client_secret, or access_token
                "service_id": service_id,
                "provider": provider,
                "error": "refresh_token_expired_or_revoked",
                "expired_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return JSONResponse(
            status_code=401,
            content={
                "mintkey:code": "oauth2_token_expired",
                "title": "OAuth2 refresh token has expired or been revoked",
            },
        )

    if resp.status_code != 200:
        logger.warning(
            "oauth2_refresh: provider returned %d for service=%s provider=%s",
            resp.status_code,
            service_id,
            provider,
        )
        return JSONResponse(
            status_code=502,
            content={
                "mintkey:code": "provider_token_error",
                "title": f"Provider returned {resp.status_code} during token refresh",
            },
        )

    token_data: dict[str, Any] = resp.json()
    access_token: str = token_data.get("access_token", "")
    expires_in: int = int(token_data.get("expires_in", 3600))
    expires_at = (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()

    # Emit successful refresh audit event — NO access_token in payload (NFR-17)
    await audit_emit(
        session=session,
        tenant_id=tenant_uuid,
        event_type="email.oauth2.refreshed",
        actor_id=None,
        actor_type="system",
        target_id=UUID(service_id) if _is_valid_uuid(service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            # NFR-17: NO access_token, refresh_token, or client_secret
            "service_id": service_id,
            "provider": provider,
            "expires_in": expires_in,
        },
    )

    # Return access_token to email-proxy — it stays in-flight only
    return JSONResponse(
        status_code=200,
        content={
            "access_token": access_token,  # returned to caller; NOT stored or logged
            "expires_at": expires_at,
            "token_type": token_data.get("token_type", "Bearer"),
        },
    )


# ---------------------------------------------------------------------------
# POST /v1/tenants/{tenant_id}/email-services/{service_id}/credentials
# DELETE /v1/tenants/{tenant_id}/email-services/{service_id}/credentials
# ---------------------------------------------------------------------------


@router.post("/{service_id}/credentials", status_code=201)
async def set_email_service_credential(
    tenant_id: UUID,
    service_id: str,
    body: EmailServiceCredentialBody,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    Store a username+password credential for an email_password or email_app_password
    email service.

    Rejects email_oauth2 — use the /authorize flow instead (ADR-0024).
    Verifies the email_services row exists under this tenant and that its
    auth_scheme matches the body.

    Stores {"username": ..., "password": ...} as a JSON blob in vault via
    put_credential. The plaintext leaves scope immediately after the vault call.

    Emits email.credential.set audit event — payload NEVER contains username
    or password (NFR-17). Returns {"id": ..., "auth_scheme": ..., "status": "set"}.

    Source: ADR-0024; NFR-17.
    """
    # Reject OAuth2 scheme — use the /authorize flow
    if body.auth_scheme == "email_oauth2":
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "use_oauth2_flow",
                "title": (
                    "auth_scheme 'email_oauth2' requires the OAuth2 authorization flow. "
                    "Use POST /v1/tenants/{tid}/email-services/{sid}/oauth2/{provider}/authorize instead."
                ),
            },
        )

    if body.auth_scheme not in _CREDENTIAL_SET_ALLOWED_SCHEMES:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "invalid_auth_scheme",
                "title": (
                    f"auth_scheme '{body.auth_scheme}' is not valid for this endpoint. "
                    f"Allowed: {sorted(_CREDENTIAL_SET_ALLOWED_SCHEMES)}"
                ),
            },
        )

    await set_tenant_context(session, tenant_id)

    # Look up the email service — verify it exists under this tenant
    svc_row_result = await session.execute(
        text(
            "SELECT id, auth_scheme FROM email_services"
            " WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"sid": service_id, "tid": str(tenant_id)},
    )
    svc_row = svc_row_result.fetchone()
    if svc_row is None:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "not_found",
                "title": "Email service not found or does not belong to this tenant.",
            },
        )

    # Verify auth_scheme of the row matches the body
    row_auth_scheme = svc_row.auth_scheme
    if row_auth_scheme != body.auth_scheme:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "auth_scheme_mismatch",
                "title": (
                    f"The email service has auth_scheme='{row_auth_scheme}' but "
                    f"the request body specifies auth_scheme='{body.auth_scheme}'. "
                    "They must match."
                ),
            },
        )

    # Store the credential as a JSON blob — plaintext leaves scope after this call
    import json as _json  # noqa: PLC0415

    plaintext = _json.dumps({"username": body.username, "password": body.password})
    try:
        vault_result = await vault.put_credential(
            tenant_id=str(tenant_id),
            service_id=service_id,
            auth_scheme=body.auth_scheme,
            plaintext=plaintext,  # NEVER logged or returned after this point
        )
    except Exception as exc:
        logger.error(
            "set_email_service_credential: vault put_credential failed for service=%s: %s",
            service_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=502,
            content={"mintkey:code": "vault_error", "title": "Failed to store credential in vault"},
        )
    finally:
        # Scrub plaintext from local scope
        del plaintext

    credential_id = vault_result.get("credential_id", f"cred_{service_id[:8]}")

    # Emit audit event — payload NEVER contains username or password (NFR-17)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.credential.set",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(service_id) if _is_valid_uuid(service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            # NFR-17: only service_id and auth_scheme — NO username, NO password
            "service_id": service_id,
            "auth_scheme": body.auth_scheme,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": str(credential_id),
            "auth_scheme": body.auth_scheme,
            "status": "set",
        },
    )


@router.delete("/{service_id}/credentials", status_code=204)
async def delete_email_service_credential(
    tenant_id: UUID,
    service_id: str,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """
    Revoke the stored credential for an email service.

    Looks up the row's auth_scheme so the vault revocation uses the correct
    proto enum value (email_password=14 vs email_app_password=16 — ADR-0024).
    Emits email.credential.deleted audit event. Returns 204.

    Source: ADR-0024; NFR-17.
    """
    await set_tenant_context(session, tenant_id)

    # Verify the email service exists under this tenant; fetch auth_scheme for vault call
    svc_row_result = await session.execute(
        text(
            "SELECT id, auth_scheme FROM email_services"
            " WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"sid": service_id, "tid": str(tenant_id)},
    )
    svc_row = svc_row_result.fetchone()
    if svc_row is None:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "not_found",
                "title": "Email service not found or does not belong to this tenant.",
            },
        )

    # Use the row's actual auth_scheme — not a hardcoded value — so the vault
    # proto enum is correct for both email_password (14) and email_app_password (16).
    row_auth_scheme = svc_row.auth_scheme

    # Revoke via vault — get_credential first to confirm existence, then overwrite with empty
    try:
        existing = await vault.get_credential(tenant_id=str(tenant_id), service_id=service_id)
        if existing is not None:
            # Revoke by overwriting with an empty value; vault adapter marks the cred revoked
            await vault.put_credential(
                tenant_id=str(tenant_id),
                service_id=service_id,
                auth_scheme=row_auth_scheme,
                plaintext="",
            )
    except Exception as exc:
        logger.error(
            "delete_email_service_credential: vault operation failed for service=%s: %s",
            service_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=502,
            content={"mintkey:code": "vault_error", "title": "Failed to revoke credential in vault"},
        )

    # Emit audit event (NFR-17: no credential material)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.credential.deleted",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(service_id) if _is_valid_uuid(service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            "service_id": service_id,
        },
    )

    return JSONResponse(status_code=204, content=None)


# ---------------------------------------------------------------------------
# PATCH request model
# ---------------------------------------------------------------------------

# Fields that are immutable after creation — reject changes to these in PATCH.
_IMMUTABLE_EMAIL_FIELDS = frozenset(
    {"provider", "imap_host", "imap_port", "smtp_host", "smtp_port", "auth_scheme"}
)


class EmailServicePatch(BaseModel):
    """Mutable fields for PATCH /v1/tenants/{tid}/email-services/{sid}.

    Immutable fields (provider, imap_host/port, smtp_host/port, auth_scheme) are
    explicitly excluded — the endpoint returns 422 if the caller includes them.
    Only the fields declared here are accepted by Pydantic.
    """

    name: Optional[str] = None
    allowed_recipient_domains: Optional[str] = None
    pool_size_max: Optional[int] = None
    tls_insecure_skip_verify: Optional[bool] = None


# ---------------------------------------------------------------------------
# GET /v1/tenants/{tenant_id}/email-services  (list)
# ---------------------------------------------------------------------------


@router.get("", status_code=200)
async def list_email_services(
    tenant_id: UUID,
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    List email services for a tenant (paginated).

    Returns {"email_services": [...], "pagination": {"limit", "offset", "total"}}.
    Soft-deleted rows (deleted_at IS NOT NULL) are excluded.
    Default page size: 50; maximum: 100.

    Auth dep: require_tenant_session (operator session required).
    Tenant-scoped: WHERE tenant_id = :tid AND deleted_at IS NULL.
    Bound parameters only — no f-strings in text().

    Source: ADR-0024; fix/email-services-crud-readonly.
    """
    await set_tenant_context(session, tenant_id)

    count_result = await session.execute(
        text(
            "SELECT COUNT(*) AS total"
            " FROM email_services"
            " WHERE tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"tid": str(tenant_id)},
    )
    count_row = count_result.fetchone()
    total = int(count_row.total) if count_row else 0

    result = await session.execute(
        text(
            "SELECT id, tenant_id, provider, name, imap_host, imap_port,"
            "  smtp_host, smtp_port, auth_scheme, allowed_recipient_domains,"
            "  pool_size_max, tls_insecure_skip_verify, created_at, updated_at"
            " FROM email_services"
            " WHERE tenant_id = :tid AND deleted_at IS NULL"
            " ORDER BY created_at"
            " LIMIT :lim OFFSET :off"
        ),
        {"tid": str(tenant_id), "lim": limit, "off": offset},
    )
    rows = result.fetchall()

    email_services = [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "provider": row.provider,
            "name": row.name,
            "imap_host": row.imap_host,
            "imap_port": row.imap_port,
            "smtp_host": row.smtp_host,
            "smtp_port": row.smtp_port,
            "auth_scheme": row.auth_scheme,
            "allowed_recipient_domains": row.allowed_recipient_domains,
            "pool_size_max": row.pool_size_max,
            "tls_insecure_skip_verify": row.tls_insecure_skip_verify,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]

    return JSONResponse(
        {
            "email_services": email_services,
            "pagination": {"limit": limit, "offset": offset, "total": total},
        }
    )


# ---------------------------------------------------------------------------
# GET /v1/tenants/{tenant_id}/email-services/{service_id}  (single)
# ---------------------------------------------------------------------------


@router.get("/{service_id}", status_code=200)
async def get_email_service(
    tenant_id: UUID,
    service_id: str,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Return a single email service.

    Returns 404 if the service does not exist, belongs to a different tenant,
    or has been soft-deleted.

    The response includes an `oauth2_authorized` boolean derived from
    `vault.get_credential` — True iff a current credential exists with
    auth_scheme == _AUTH_SCHEME_EMAIL_OAUTH2 (15). The admin UI reads this
    field to render the green "Authorized" status on the OAuth2 setup widget.
    Vault errors are logged at WARNING and the field is set to False
    (fail-closed on display; never block the page load).

    No credential material (plaintext, header_name, query_param, etc.) is
    ever returned — only the derived boolean (NFR-17).

    Auth dep: require_tenant_session.
    Tenant-scoped: WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL.
    Bound parameters only.

    Source: ADR-0024; fix/email-services-crud-readonly.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, tenant_id, provider, name, imap_host, imap_port,"
            "  smtp_host, smtp_port, auth_scheme, allowed_recipient_domains,"
            "  pool_size_max, tls_insecure_skip_verify, created_at, updated_at"
            " FROM email_services"
            " WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"sid": service_id, "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Email service not found"},
        )

    # Derive oauth2_authorized from the vault. Fail-closed on any vault error
    # — never block the page load. Never echo credential material from `cred`.
    oauth2_authorized = False
    try:
        cred = await vault.get_credential(
            tenant_id=str(tenant_id),
            service_id=service_id,
        )
        if cred is not None and cred.get("auth_scheme") == _AUTH_SCHEME_EMAIL_OAUTH2:
            oauth2_authorized = True
    except Exception:
        logger.warning(
            "get_email_service: vault.get_credential failed; defaulting"
            " oauth2_authorized=False tenant=%s service=%s",
            tenant_id,
            service_id,
            exc_info=True,
        )
        oauth2_authorized = False

    return JSONResponse(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "provider": row.provider,
            "name": row.name,
            "imap_host": row.imap_host,
            "imap_port": row.imap_port,
            "smtp_host": row.smtp_host,
            "smtp_port": row.smtp_port,
            "auth_scheme": row.auth_scheme,
            "allowed_recipient_domains": row.allowed_recipient_domains,
            "pool_size_max": row.pool_size_max,
            "tls_insecure_skip_verify": row.tls_insecure_skip_verify,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            "oauth2_authorized": oauth2_authorized,
        }
    )


# ---------------------------------------------------------------------------
# PATCH /v1/tenants/{tenant_id}/email-services/{service_id}
# ---------------------------------------------------------------------------


@router.patch("/{service_id}", status_code=200)
async def patch_email_service(
    tenant_id: UUID,
    service_id: str,
    body: EmailServicePatch,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Update mutable fields of an email service.

    Mutable: name, allowed_recipient_domains, pool_size_max, tls_insecure_skip_verify.
    Immutable (provider, imap_host, imap_port, smtp_host, smtp_port, auth_scheme) are
    rejected with 422 if the caller tries to change them — use delete+create instead.

    Empty bodies (no fields set) are rejected with 422.

    Emits email_service.updated audit with payload {service_id, changed_fields: [names]}.
    Field VALUES are NOT included in the audit payload (NFR-17 belt-and-suspenders).

    Auth dep: require_tenant_session.
    Tenant-scoped: WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL.
    Bound parameters only.

    Source: ADR-0024; NFR-17; fix/email-services-crud-readonly.
    """
    # Reject any immutable fields the caller might have tried to send.
    raw_json: dict[str, Any] = {}
    try:
        raw_json = await request.json()
    except Exception:  # noqa: BLE001
        pass

    immutable_in_body = _IMMUTABLE_EMAIL_FIELDS & set(raw_json.keys())
    if immutable_in_body:
        bad_fields = sorted(immutable_in_body)
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "immutable_fields",
                "title": (
                    "Fields "
                    + str(bad_fields)
                    + " cannot be changed after creation."
                    " To change provider, hosts, ports, or auth_scheme: remove and re-create."
                ),
            },
        )

    # Reject empty bodies — at least one mutable field must be set.
    provided_fields = list(body.model_fields_set)
    if not provided_fields:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "no_fields_to_update",
                "title": "Request body contains no fields to update.",
            },
        )

    await set_tenant_context(session, tenant_id)

    # Verify service exists and belongs to this tenant (explicit guard — RLS also enforces)
    check_result = await session.execute(
        text(
            "SELECT id FROM email_services"
            " WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"sid": service_id, "tid": str(tenant_id)},
    )
    if check_result.fetchone() is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Email service not found"},
        )

    now = datetime.now(timezone.utc)

    # Build fixed-template UPDATE (COALESCE keeps current value when new value is NULL).
    # SQL is a string literal — no f-strings; all values are bound parameters. ADR-0008.
    await session.execute(
        text(
            "UPDATE email_services"
            "   SET name = COALESCE(:name, name),"
            "       allowed_recipient_domains = COALESCE(:allowed_recipient_domains,"
            "                                            allowed_recipient_domains),"
            "       pool_size_max = COALESCE(:pool_size_max, pool_size_max),"
            "       tls_insecure_skip_verify = COALESCE(:tls_insecure_skip_verify,"
            "                                           tls_insecure_skip_verify),"
            "       updated_at = :updated_at"
            " WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL"
        ),
        {
            "name": body.name,
            "allowed_recipient_domains": body.allowed_recipient_domains,
            "pool_size_max": body.pool_size_max,
            "tls_insecure_skip_verify": body.tls_insecure_skip_verify,
            "updated_at": now,
            "sid": service_id,
            "tid": str(tenant_id),
        },
    )

    # Emit audit event — field NAMES only, no values (NFR-17 belt-and-suspenders).
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.service.updated",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(service_id) if _is_valid_uuid(service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            "service_id": service_id,
            "changed_fields": sorted(provided_fields),
        },
    )

    # Re-fetch and return the updated row
    refetch = await session.execute(
        text(
            "SELECT id, tenant_id, provider, name, imap_host, imap_port,"
            "  smtp_host, smtp_port, auth_scheme, allowed_recipient_domains,"
            "  pool_size_max, tls_insecure_skip_verify, created_at, updated_at"
            " FROM email_services"
            " WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"sid": service_id, "tid": str(tenant_id)},
    )
    row = refetch.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Email service not found"},
        )

    return JSONResponse(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "provider": row.provider,
            "name": row.name,
            "imap_host": row.imap_host,
            "imap_port": row.imap_port,
            "smtp_host": row.smtp_host,
            "smtp_port": row.smtp_port,
            "auth_scheme": row.auth_scheme,
            "allowed_recipient_domains": row.allowed_recipient_domains,
            "pool_size_max": row.pool_size_max,
            "tls_insecure_skip_verify": row.tls_insecure_skip_verify,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    )


# ---------------------------------------------------------------------------
# DELETE /v1/tenants/{tenant_id}/email-services/{service_id}
# ---------------------------------------------------------------------------


@router.delete("/{service_id}", status_code=204)
async def delete_email_service(
    tenant_id: UUID,
    service_id: str,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Soft-delete an email service (sets deleted_at = now()).

    Idempotent: returns 204 even if the row was already soft-deleted.

    email_permission_grants that reference this service via FK are LEFT IN PLACE.
    The FK constraint references the row (not just live rows), so the FK remains
    valid after a soft-delete. Cleanup of orphaned grants is the operator's call.

    Emits email_service.deleted audit event with payload {service_id}.

    Auth dep: require_tenant_session.
    Tenant-scoped WHERE clause on UPDATE. Bound parameters only.

    Source: ADR-0024; fix/email-services-crud-readonly.
    """
    await set_tenant_context(session, tenant_id)

    now = datetime.now(timezone.utc)

    # Soft-delete: set deleted_at = now() where not already deleted.
    # Idempotent: if already deleted, this UPDATE matches 0 rows — that is fine.
    await session.execute(
        text(
            "UPDATE email_services"
            "   SET deleted_at = :now, updated_at = :now"
            " WHERE id = :sid AND tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"now": now, "sid": service_id, "tid": str(tenant_id)},
    )

    # Emit audit event regardless (idempotent pattern — always confirm intent)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.service.deleted",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(service_id) if _is_valid_uuid(service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={"service_id": service_id},
    )

    return JSONResponse(status_code=204, content=None)


# ---------------------------------------------------------------------------
# GET /v1/tenants/{tenant_id}/oauth2/{provider}/callback  (per-tenant, browser redirect)
# POST /v1/tenants/{tenant_id}/oauth2/{provider}/callback (per-tenant, programmatic)
#
# These endpoints are the NEW preferred redirect_uri shape (fix/oauth2-redirect-uri-per-tenant).
# Operators register ONE redirect URI per provider per tenant in GCP/Azure Console instead of
# one per email_service.  The service_id is resolved from the oauth2_state row (which already
# carries service_id — migration 023).
#
# The old per-service endpoints (/{service_id}/oauth2/{provider}/callback) remain alive for
# backwards compat: any in-flight authorize flows that started before this PR will complete via
# the per-service path because that is what is stored in their state row.
# ---------------------------------------------------------------------------


class OAuth2CallbackPerTenantBody(BaseModel):
    """Body for POST /v1/tenants/{tenant_id}/oauth2/{provider}/callback."""

    code: str
    state: str


@oauth2_per_tenant_router.get("/{provider}/callback")
async def oauth2_callback_per_tenant_view(
    tenant_id: UUID,
    provider: str,
    code: Optional[str] = None,
    state: Optional[str] = None,
    error: Optional[str] = None,
    error_description: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> HTMLResponse:
    """Handle OAuth2 GET browser redirect at the per-(provider, tenant) callback URL (C-9).

    This is the NEW preferred redirect_uri shape introduced in fix/oauth2-redirect-uri-per-tenant.
    Operators register ONE URI per provider per tenant in GCP/Azure Console instead of one per
    email_service.  The oauth2_state row carries service_id; no service_id appears in this URL.

    Flow:
      1. If ?error= is present: render error HTML immediately (no state lookup needed).
      2. Validate code and state are present.
      3. Look up and single-use-delete the state row; resolve service_id from it.
      4. Call _exchange_oauth2_code_for_refresh_token with the resolved service_id.
      5. Return HTML (same as per-service callback view).

    Security (NFR-17): NEVER echoes code, state, refresh_token, client_secret, or access_token.
    audit_emit is called directly in this handler (not delegated to the helper) so the
    AST-based write-handler audit-coverage scanner sees a direct call.

    Source: fix/oauth2-redirect-uri-per-tenant; ADR-0024 §B2.
    """
    admin_ui_origin = _admin_ui_base()
    # Sentinel for error-path HTML (no service_id available from URL in this shape)
    _sentinel_service_id = ""

    # --- Provider sent ?error=... ---
    if error:
        logger.info(
            "oauth2_callback_per_tenant_view: provider error=%s provider=%s tenant=%s",
            error,
            provider,
            tenant_id,
        )
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=_sentinel_service_id,
                error_code=error,
                error_description=error_description or "",
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=200,
        )

    if provider not in _OAUTH2_PROVIDERS:
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=_sentinel_service_id,
                error_code="unsupported_provider",
                error_description=f"OAuth2 is only supported for {sorted(_OAUTH2_PROVIDERS)}",
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=422,
        )

    if not code or not state:
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=_sentinel_service_id,
                error_code="missing_params",
                error_description="OAuth2 callback is missing required parameters (code or state).",
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=422,
        )

    await set_tenant_context(session, tenant_id)

    creds = await _oauth2_config_from_db(tenant_id, provider, session, vault)
    if creds is None:
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=_sentinel_service_id,
                error_code="oauth2_not_configured",
                error_description=f"OAuth2 credentials for provider '{provider}' are not configured",
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=503,
        )
    client_id, client_secret = creds

    # Exchange code — service_id is resolved from the state row inside the helper
    result = await _exchange_oauth2_code_for_refresh_token(
        tenant_id=tenant_id,
        service_id=_sentinel_service_id,  # overridden by state row inside helper
        provider=provider,
        code=code,        # NEVER echoed in HTML / logs
        state=state,      # NEVER echoed in HTML / logs
        session=session,
        vault=vault,
        client_id=client_id,
        client_secret=client_secret,
    )

    if not result.ok:
        return HTMLResponse(
            content=_oauth2_callback_html(
                success=False,
                service_id=_sentinel_service_id,
                error_code=result.error_code,
                error_description=result.error_title,
                admin_ui_origin=admin_ui_origin,
            ),
            status_code=result.http_status,
        )

    # Emit audit event — NO refresh_token, client_secret, or access_token (NFR-17).
    # Emitted directly in this handler so the write-handler audit-coverage scanner
    # (test_audit_coverage.py) sees the call (NOT delegated to the helper).
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.oauth2.authorized",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(result.service_id) if _is_valid_uuid(result.service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            "service_id": result.service_id,
            "provider": provider,
            "authorized_at": result.authorized_at,
            "token_type": result.token_type,
            # email_address is operator-visible already (lands in the
            # email_services.name column after successful auth) — recording
            # it in the audit event lets operators tie a row to its Google
            # account. Empty string for outlook (see helper docstring).
            "email_address": result.email_address,
        },
    )

    return HTMLResponse(
        content=_oauth2_callback_html(
            success=True,
            service_id=result.service_id,
            admin_ui_origin=admin_ui_origin,
        ),
        status_code=200,
    )


@oauth2_per_tenant_router.post("/{provider}/callback", status_code=200)
async def oauth2_callback_per_tenant(
    tenant_id: UUID,
    provider: str,
    body: OAuth2CallbackPerTenantBody,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """Complete the OAuth2 flow at the per-(provider, tenant) callback URL (programmatic).

    This is the NEW preferred redirect_uri shape introduced in fix/oauth2-redirect-uri-per-tenant.
    The service_id is resolved from the oauth2_state row (not from the URL path).

    Steps:
      1. Validate provider.
      2. Look up OAuth2 client credentials.
      3. Delegate to _exchange_oauth2_code_for_refresh_token (state lookup + token exchange).
      4. Emit email.oauth2.authorized audit event (direct, not via helper — audit scanner).
      5. Return 200 JSON.

    Returns 422 if provider is unsupported or state is invalid/expired.
    Returns 503 if OAuth2 credentials are not configured.

    Security (NFR-17): NEVER logs or returns code, state, refresh_token, or client_secret.
    audit_emit is called directly in this handler.

    Source: fix/oauth2-redirect-uri-per-tenant; ADR-0024 §B2.
    """
    if provider not in _OAUTH2_PROVIDERS:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "unsupported_provider",
                "title": f"OAuth2 is only supported for {sorted(_OAUTH2_PROVIDERS)}",
            },
        )

    await set_tenant_context(session, tenant_id)

    creds = await _oauth2_config_from_db(tenant_id, provider, session, vault)
    if creds is None:
        return JSONResponse(
            status_code=503,
            content={
                "mintkey:code": "oauth2_not_configured",
                "title": f"OAuth2 credentials for provider '{provider}' are not configured",
            },
        )
    client_id, client_secret = creds

    result = await _exchange_oauth2_code_for_refresh_token(
        tenant_id=tenant_id,
        service_id="",  # overridden by state row inside helper
        provider=provider,
        code=body.code,
        state=body.state,
        session=session,
        vault=vault,
        client_id=client_id,
        client_secret=client_secret,
    )

    if not result.ok:
        return JSONResponse(
            status_code=result.http_status,
            content={"mintkey:code": result.error_code, "title": result.error_title},
        )

    # Emit audit event — NO refresh_token, client_secret, or access_token (NFR-17).
    # Emitted directly in this handler (not delegated to the helper) so the AST-based
    # write-handler audit-coverage scanner (test_audit_coverage.py) sees the call.
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.oauth2.authorized",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(result.service_id) if _is_valid_uuid(result.service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            "service_id": result.service_id,
            "provider": provider,
            "authorized_at": result.authorized_at,
            "token_type": result.token_type,
            # email_address is operator-visible already (lands in the
            # email_services.name column after successful auth) — recording
            # it in the audit event lets operators tie a row to its Google
            # account. Empty string for outlook (see helper docstring).
            "email_address": result.email_address,
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "service_id": result.service_id,
            "provider": provider,
            "authorized_at": result.authorized_at,
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
