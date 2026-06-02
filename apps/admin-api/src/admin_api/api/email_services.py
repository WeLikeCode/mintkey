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
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
    Return (client_id, client_secret) for `provider`, or None if any var is missing.

    Fails-soft: missing env var → returns None → endpoints return 503.
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


def _oauth2_available(provider: str) -> bool:
    return _oauth2_config(provider) is not None


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

# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

_VALID_PROVIDERS = {"gmail", "outlook", "generic"}
_VALID_AUTH_SCHEMES = {"email_password", "email_oauth2", "email_app_password"}

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
            "  pool_size_max, created_at, updated_at)"
            " VALUES"
            " (:id, :tenant_id, :provider, :name, :imap_host, :imap_port,"
            "  :smtp_host, :smtp_port, :auth_scheme, :allowed_domains,"
            "  :pool_size, :now, :now)"
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
            "  pool_size_max, created_at, updated_at)"
            " VALUES"
            " (:id, :tenant_id, :provider, :name, :imap_host, :imap_port,"
            "  :smtp_host, :smtp_port, :auth_scheme, NULL,"
            "  5, :now, :now)"
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
) -> JSONResponse:
    """
    Start the OAuth2 authorization code flow for gmail|outlook.

    Generates a cryptographically random `state` value, inserts it into
    oauth2_state with a 10-minute TTL (opportunistic GC fires first),
    and returns the provider's authorization URL.

    Returns 422 if provider is not gmail|outlook.
    Returns 503 if OAuth2 client credentials are not configured.

    Source: ADR-0024 §B2; .kiro/specs/email-proxy/design.md; chunk C-9.
    """
    if provider not in _OAUTH2_PROVIDERS:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "unsupported_provider",
                "title": f"OAuth2 is only supported for {sorted(_OAUTH2_PROVIDERS)}",
            },
        )

    creds = _oauth2_config(provider)
    if creds is None:
        return JSONResponse(
            status_code=503,
            content={
                "mintkey:code": "oauth2_not_configured",
                "title": f"OAuth2 credentials for provider '{provider}' are not configured",
            },
        )
    client_id, _ = creds

    await set_tenant_context(session, tenant_id)

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
        str(request.base_url).rstrip("/")
        + f"/v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/callback"
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
    Receive the OAuth2 auth-code and complete the flow.

    1. Validates `state` — single-use (DELETE after lookup).
    2. Exchanges `code` for `refresh_token` via the provider's token endpoint.
    3. Stores the encrypted `refresh_token` in vault.credentials
       (auth_scheme=email_oauth2) via put_credential.
    4. Emits email.oauth2.authorized audit event.

    The audit payload NEVER includes refresh_token, client_secret, or
    access_token (NFR-17).

    Returns 422 if state is missing/expired/mismatched.
    Returns 503 if OAuth2 client credentials are not configured.

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

    creds = _oauth2_config(provider)
    if creds is None:
        return JSONResponse(
            status_code=503,
            content={
                "mintkey:code": "oauth2_not_configured",
                "title": f"OAuth2 credentials for provider '{provider}' are not configured",
            },
        )
    client_id, client_secret = creds

    await set_tenant_context(session, tenant_id)

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
        {"state": body.state, "tid": str(tenant_id), "provider": provider},
    )
    state_row = state_result.fetchone()
    if state_row is None:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "invalid_state",
                "title": "OAuth2 state is invalid, expired, or already used",
            },
        )

    resolved_service_id = str(state_row.service_id) if state_row.service_id else service_id
    redirect_uri = body.redirect_uri or str(state_row.redirect_uri)
    # operator_id from state used for audit actor binding (future: pass as actor_id)
    # Currently kept for traceability; the audit event is emitted with actor_id=None.

    # Exchange auth code for tokens — server-side; client_secret never leaves admin-api
    token_url = _GMAIL_TOKEN_URL if provider == "gmail" else _OUTLOOK_TOKEN_URL
    exchange_payload: dict[str, str] = {
        "code": body.code,
        "client_id": client_id,
        "client_secret": client_secret,  # NEVER logged or returned
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(token_url, data=exchange_payload)
    except httpx.HTTPError as exc:
        logger.error("oauth2_callback: HTTP error exchanging code for provider=%s: %s", provider, type(exc).__name__)
        return JSONResponse(
            status_code=502,
            content={"mintkey:code": "provider_unreachable", "title": "Provider token endpoint unreachable"},
        )

    if resp.status_code != 200:
        logger.warning(
            "oauth2_callback: provider returned %d for provider=%s (no secret in log)",
            resp.status_code,
            provider,
        )
        return JSONResponse(
            status_code=502,
            content={
                "mintkey:code": "provider_token_error",
                "title": f"Provider returned {resp.status_code} during token exchange",
            },
        )

    token_data: dict[str, Any] = resp.json()
    refresh_token: str = token_data.get("refresh_token", "")
    if not refresh_token:
        logger.warning("oauth2_callback: provider returned no refresh_token for provider=%s", provider)
        return JSONResponse(
            status_code=502,
            content={"mintkey:code": "no_refresh_token", "title": "Provider did not return a refresh_token"},
        )

    # Store encrypted refresh_token in vault — plaintext leaves scope here
    try:
        await vault.put_credential(
            tenant_id=str(tenant_id),
            service_id=resolved_service_id,
            auth_scheme="email_oauth2",
            plaintext=refresh_token,  # NEVER logged after this point
        )
    except Exception as exc:
        logger.error(
            "oauth2_callback: vault put_credential failed for service=%s: %s",
            resolved_service_id,
            type(exc).__name__,
        )
        return JSONResponse(
            status_code=502,
            content={"mintkey:code": "vault_error", "title": "Failed to store credential in vault"},
        )

    now = datetime.now(timezone.utc)

    # Emit audit event — NO refresh_token, client_secret, or access_token (NFR-17)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email.oauth2.authorized",
        actor_id=None,
        actor_type="operator",
        target_id=UUID(resolved_service_id) if _is_valid_uuid(resolved_service_id) else uuid.uuid4(),
        target_type="email_service",
        payload={
            "service_id": resolved_service_id,
            "provider": provider,
            "authorized_at": now.isoformat(),
            # token_type only — NEVER the token values
            "token_type": token_data.get("token_type", "Bearer"),
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "service_id": resolved_service_id,
            "provider": provider,
            "authorized_at": now.isoformat(),
        },
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

    creds = _oauth2_config(provider)
    if creds is None:
        return JSONResponse(
            status_code=503,
            content={
                "mintkey:code": "oauth2_not_configured",
                "title": f"OAuth2 credentials for provider '{provider}' are not configured",
            },
        )
    client_id, client_secret = creds

    # Parse tenant_id
    try:
        tenant_uuid = UUID(tenant_id)
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_tenant_id", "title": "tenant_id is not a valid UUID"},
        )

    await set_tenant_context(session, tenant_uuid)

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

    refresh_token: str = cred.get("plaintext", "")  # type: ignore[assignment]
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
# Helpers
# ---------------------------------------------------------------------------


def _is_valid_uuid(value: str) -> bool:
    try:
        UUID(value)
        return True
    except (ValueError, AttributeError):
        return False
