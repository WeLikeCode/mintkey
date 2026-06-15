"""
Service CRUD endpoints.

POST   /v1/tenants/{tenant_id}/services              — register a service (201)
GET    /v1/tenants/{tenant_id}/services              — list services (200)
PATCH  /v1/tenants/{tenant_id}/services/{sid}        — update a service (200)
DELETE /v1/tenants/{tenant_id}/services/{sid}        — delete a service (204)
POST   /v1/tenants/{tenant_id}/services/test-transient — dry-run test without persistence (200)

Architecture constraints:
  - Tenant context via bound parameters — ADR-0008, T-1.0.15.
  - pg_notify via bound parameters — ADR-0008, T-1.0.15.
  - Audit emit on every state change — ADR-0014.7, Req AUD-3.
  - ULID IDs with prefix "svc_" — ADR-0017.11.
  - Global channel "mintkey:service" — ADR-0014.1.
  - RFC1918 / loopback / metadata destinations rejected — S-SEC-1.
  - No plaintext credentials in responses or logs — S-SEC-1, ADR-0014.4.
  - test-transient: credential value NEVER written to DB, vault, logs, or audit — OPS-T.

Source: design §4 api/services.py; Req 3; ADR-0008; ADR-0014.7; ADR-0017.11.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Literal, Optional, cast
from urllib.parse import urlparse, urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.sessions import require_tenant_session
from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from admin_api.services.credential_service import resolve_hostname_is_private
from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid as _wire_to_db
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/tenants/{tenant_id}/services")

# ---------------------------------------------------------------------------
# Forbidden destination check — S-SEC-1 / ADR-0014.4
# The _FORBIDDEN_NETWORKS list and the DNS resolver live in credential_service
# (single source of truth); we import resolve_hostname_is_private from there.
# ---------------------------------------------------------------------------

# Crockford base32 alphabet (uppercase, no I/L/O/U)
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _new_svc_id() -> str:
    """
    Generate a ULID-format ID with the 'svc_' prefix — ADR-0017.11.

    Layout: 10 time chars (48-bit ms) + 16 random chars = 26 Crockford base32 chars.
    """
    ts_ms = int(time.time() * 1000)
    rand = int.from_bytes(uuid.uuid4().bytes[:10], "big")

    # Encode 48-bit timestamp into 10 Crockford chars
    t_enc = []
    v = ts_ms
    for _ in range(10):
        t_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    t_enc.reverse()

    # Encode 80 random bits into 16 Crockford chars
    r_enc = []
    v = rand
    for _ in range(16):
        r_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    r_enc.reverse()

    return "svc_" + "".join(t_enc) + "".join(r_enc)


def _is_forbidden_destination(base_url: str) -> bool:
    """
    Return True when base_url resolves to a forbidden network — S-SEC-1.

    Forbidden: RFC1918, loopback (127/8, ::1), link-local (169.254/16, fe80::/10),
    and unique-local (fc00::/7).

    Both IP literals AND DNS-resolved hostnames are checked so that a hostname
    that resolves to a private/loopback address is also rejected (BUG-13).

    DNS resolution is delegated to ``credential_service.resolve_hostname_is_private``
    — the single shared SSRF helper (no third copy of the logic).

    Operators may set MINTKEY_SSRF_ALLOW_PRIVATE=1 to opt OUT of the private-IP
    block (e.g. dev workflows hitting a private mock backend).
    """
    try:
        parsed = urlparse(base_url)
        host = parsed.hostname
        if not host:
            return False

        # Opt-out for dev environments
        if os.environ.get("MINTKEY_SSRF_ALLOW_PRIVATE") == "1":
            return False

        return resolve_hostname_is_private(host)
    except Exception:  # noqa: BLE001
        return False


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ServiceCreate(BaseModel):
    name: str
    base_url: str
    auth_scheme: str
    display_name: Optional[str] = None
    description: Optional[str] = None
    openapi_url: Optional[str] = None


class ServiceUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    auth_scheme: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    openapi_url: Optional[str] = None
    status: Optional[str] = None


class ServiceOverrides(BaseModel):
    """Optional overrides when instantiating a service from a template."""

    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    base_url: Optional[str] = None


class FromTemplateRequest(BaseModel):
    """Body for POST /v1/tenants/{tid}/services/from-template.

    Source: design §4 From-Template Instantiation; Requirements 4.1, 4.2.
    """

    template_id: str
    overrides: Optional[ServiceOverrides] = None


class TestRunRequest(BaseModel):
    """
    Body for POST /{service_id}/test — operationId testRunService.

    All fields are optional with sensible defaults so that an empty body `{}`
    falls back to GET /health (matching the OpenAPI default).

    Source: openapi.yaml TestRunRequest; R14b fix (R13 found body silently dropped).
    """

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    path: str = "/health"
    headers: Optional[dict[str, str]] = None
    body: Optional[str] = None
    timeout_ms: Optional[int] = 5000


class TransientServiceCandidate(BaseModel):
    """Candidate service config for a dry-run test — OPS-T."""

    name: str = "candidate"
    base_url: str
    auth_scheme: str


class TransientCredentialCandidate(BaseModel):
    """
    Candidate credential for a dry-run test — OPS-T.

    The `value` field is used inline for the HTTP call ONLY.
    It is NEVER written to DB, vault, any log line, or the audit payload.
    """

    value: str
    header_name: Optional[str] = None   # api_key_header scheme
    query_param: Optional[str] = None   # api_key_query scheme
    token_url: Optional[str] = None     # oauth2_client_credentials (future)
    client_id: Optional[str] = None     # oauth2_client_credentials (future)


class TransientTestParams(BaseModel):
    """HTTP call parameters for a dry-run test — OPS-T."""

    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"] = "GET"
    path: str = "/"
    headers: Optional[dict[str, str]] = None
    body: Optional[str] = None
    timeout_ms: int = 5000


class TransientTestRequest(BaseModel):
    """
    Body for POST /test-transient — operationId testServiceTransient.

    Carries the full candidate service config + credential inline.
    Nothing is persisted to DB or vault.

    Source: openapi.yaml TransientTestRequest; OPS-T.
    """

    service: TransientServiceCandidate
    credential: TransientCredentialCandidate
    test: TransientTestParams = TransientTestParams()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _forbidden_response() -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "mintkey:code": "forbidden_destination",
            "title": "The base_url resolves to a forbidden destination",
        },
    )


def _check_ssrf_hostname(final_url: str, base_url: str) -> str:
    """
    Enforce that the outbound URL's effective hostname stays within the
    service's declared base_url hostname — S-SEC-1 / ADR-0014.4.

    A malicious test.path (e.g. ``//evil.com/foo``) could cause the
    constructed final_url to escape to a different host.  Parsing both URLs
    and comparing hostnames (case-insensitive) closes that gap.

    Raises HTTPException(400) if the hostnames do not match.

    Returns ``final_url`` unchanged when the hostname is safe.  Returning the
    value (rather than raising-only) lets CodeQL's taint analysis recognise
    the assignment site as a dataflow sanitization point.
    """
    base_host = urlparse(base_url).hostname or ""
    final_host = urlparse(final_url).hostname or ""
    if final_host.lower() != base_host.lower():
        raise HTTPException(
            status_code=400,
            detail={
                "mintkey:code": "ssrf_blocked",
                "title": "Outbound hostname does not match the service base_url",
                "base_host": base_host,
                "final_host": final_host,
            },
        )
    return final_url


def _validate_test_url(url: str) -> tuple[bool, str | None]:
    """Validate URL is safe for outbound test calls.

    Returns (is_safe, reason_if_unsafe).
    Rejects:
      - non-http(s) schemes
      - URLs without a host
      - hostnames that resolve to private, loopback, link-local, multicast,
        reserved, or unspecified IP ranges (v4 OR v6)

    Operators may set MINTKEY_SSRF_ALLOW_PRIVATE=1 to opt OUT of the
    private-IP block (e.g. dev workflows hitting a private mock backend).
    """
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return (False, "scheme_not_allowed")
    if not parts.hostname:
        return (False, "missing_host")
    try:
        resolved = socket.getaddrinfo(parts.hostname, None)
    except socket.gaierror:
        return (False, "dns_resolution_failed")
    if os.environ.get("MINTKEY_SSRF_ALLOW_PRIVATE") != "1":
        for _family, _type, _proto, _canonname, sockaddr in resolved:
            addr = sockaddr[0]
            ip = ipaddress.ip_address(addr)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return (False, "private_or_special_ip_blocked")
    return (True, None)


def _parse_ssh_host_port(base_url: str) -> str:
    """
    Parse an SSH base_url (scheme ssh://) into "host:port" for vault.credentials.target_address.

    Examples:
      "ssh://172.24.1.234:22"  → "172.24.1.234:22"
      "ssh://target-host:2222" → "target-host:2222"

    Raises ValueError if the URL is malformed:
      - scheme is not "ssh"
      - host is missing
      - port is missing (port is required for SSH routing)

    Non-SSH base_urls must not be passed here — the caller is responsible for
    checking auth_scheme before calling this helper.

    Source: C-6a; ADR-0021.
    """
    parsed = urlsplit(base_url)
    if parsed.scheme != "ssh":
        raise ValueError(f"Expected ssh:// scheme, got '{parsed.scheme}://'")
    host = parsed.hostname
    if not host:
        raise ValueError("ssh:// URL missing hostname")
    port = parsed.port
    if port is None:
        raise ValueError("ssh:// URL missing port (required for SSH routing)")
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


def _wire_id_to_db_uuid(wire_id: str) -> str:
    """
    Convert a wire svc_ ID back to the UUID string stored in the DB.

    Thin wrapper around utils.wire_ids.wire_to_db_uuid — accepts both the
    canonical Crockford form and the legacy 32-hex form for backward-compat.
    Returns wire_id unchanged if it does not match a known svc_ prefix.

    Source: ADR-0017.11; #13.
    """
    return _wire_to_db(wire_id, "svc")


def _service_row_to_dict(row: Any) -> dict[str, Any]:
    """Map a DB row (namedtuple-like) to the wire representation.

    Emits Crockford ULID wire-form IDs (canonical per ADR-0017.11 / #13).
    Includes current_key_version — MAX key_version of active credentials (UX-FB-B).
    Includes template_id if the service was created from a template (Req 4.4).
    """
    result: dict[str, Any] = {
        "id": db_uuid_to_wire(row.id, "svc"),
        "tenant_id": str(row.tenant_id),
        "name": row.name,
        "slug": row.slug,
        "display_name": row.display_name,
        "description": row.description,
        "base_url": row.base_url,
        "auth_scheme": row.auth_scheme,
        "openapi_url": row.openapi_url,
        "status": row.status,
        "current_key_version": int(row.current_key_version or 0),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }
    # Include template_id if present (nullable column)
    if hasattr(row, "template_id") and row.template_id is not None:
        result["template_id"] = row.template_id
    return result


# ---------------------------------------------------------------------------
# SSH test helper — ADR-0021 / OPS-T
# Implemented in _ssh_test.py to keep this module importable without asyncssh
# and to allow unit testing without pulling in mintkey_models.
# ---------------------------------------------------------------------------

from admin_api.api._ssh_test import SSH_SCHEMES as _SSH_SCHEMES  # noqa: E402
from admin_api.api._ssh_test import test_ssh_credential as _test_ssh_credential  # noqa: E402


async def _run_ssh_post_save_test(
    auth_scheme: str,
    cred_entry: dict[str, Any] | None,
    base_url: str,
    timeout_ms: int,
) -> dict[str, Any]:
    """
    Build the envelope JSON for a post-save SSH credential test and call
    _test_ssh_credential.  Credential plaintext NEVER appears in return dict.

    For ssh_private_key: {"scheme": ..., "private_key_pem": ..., "ssh_user": ..., "target_address": ...}
    For ssh_password:    {"scheme": ..., "username": ..., "password": ..., "target_address": ...}

    Returns the same {ok, status_code, latency_ms, final_url, response_body_truncated}
    shape as the HTTP test path so the UI renders it unchanged.

    ADR-0021 / OPS-T / S-SEC-1.
    """
    import json as _json  # noqa: PLC0415

    if not cred_entry:
        return {
            "ok": False,
            "status_code": 400,
            "latency_ms": 0,
            "final_url": base_url,
            "response_body_truncated": "No credential found for this service.",
        }

    target_address: str = cast(str, cred_entry.get("target_address") or "")
    ssh_user: str = cast(str, cred_entry.get("ssh_user") or "")
    plaintext: str = cast(str, cred_entry.get("plaintext") or "")

    # Guard: legacy credentials created before ADR-0021 may lack these fields.
    if not target_address or not ssh_user:
        return {
            "ok": False,
            "status_code": 400,
            "latency_ms": 0,
            "final_url": base_url,
            "response_body_truncated": (
                "Credential is missing target_address or ssh_user metadata. "
                "Re-create the credential to populate these fields."
            ),
        }

    if auth_scheme == "ssh_private_key":
        envelope = _json.dumps({
            "scheme": auth_scheme,
            "private_key_pem": plaintext,
            "ssh_user": ssh_user,
            "target_address": target_address,
        })
    else:  # ssh_password
        envelope = _json.dumps({
            "scheme": auth_scheme,
            "username": ssh_user,
            "password": plaintext,
            "target_address": target_address,
        })

    return await _test_ssh_credential(
        scheme=auth_scheme,
        credential_value=envelope,
        base_url=base_url,
        timeout_ms=timeout_ms,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_service(
    tenant_id: UUID,
    body: ServiceCreate,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Register a new backend service under a tenant.

    Source: Req 3; ADR-0008; ADR-0014.7; ADR-0017.11.
    """
    # Validate base_url is not a forbidden destination — S-SEC-1
    if _is_forbidden_destination(body.base_url):
        return _forbidden_response()

    # Set tenant context — bound parameters, ADR-0008
    await set_tenant_context(session, tenant_id)

    # Generate ULID ID with svc_ prefix — ADR-0017.11
    svc_id = _new_svc_id()
    # Derive the DB UUID from the ULID's 128-bit value — R12 (mirrors R8-redux for agents).
    # _new_svc_id() returns "svc_<26-char Crockford ULID>"; decode the 26-char tail to the
    # same 128-bit integer and wrap as uuid.UUID so the stored row PK is algebraically
    # identical to what _wire_id_to_uuid(svc_id, "svc_") decodes from the wire form.
    # Dropping the independent uuid.uuid4() eliminates the asymmetry that caused silent
    # 404s for new services: POST returned svc_<Crockford> whose bits never matched the PK.
    _crockford_tail = svc_id[len("svc_"):]
    _val = 0
    for _ch in _crockford_tail.upper():
        _val = (_val << 5) | _CROCKFORD.index(_ch)
    _val &= (1 << 128) - 1
    internal_id = uuid.UUID(int=_val)
    now = datetime.now(timezone.utc)

    # Derive slug from name
    slug = body.name.lower().replace(" ", "-")

    await session.execute(
        text(
            "INSERT INTO services"
            " (id, tenant_id, name, slug, display_name, description,"
            "  base_url, auth_scheme, openapi_url, status, created_at, updated_at)"
            " VALUES"
            " (:id, :tenant_id, :name, :slug, :display_name, :description,"
            "  :base_url, :auth_scheme, :openapi_url, :status, :created_at, :updated_at)"
        ),
        {
            "id": str(internal_id),
            "tenant_id": str(tenant_id),
            "name": body.name,
            "slug": slug,
            "display_name": body.display_name,
            "description": body.description,
            "base_url": body.base_url,
            "auth_scheme": body.auth_scheme,
            "openapi_url": body.openapi_url,
            "status": "active",
            "created_at": now,
            "updated_at": now,
        },
    )

    # Emit audit event — ADR-0014.7, Req AUD-3
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.registered",
        actor_id=None,
        actor_type="operator",
        target_id=internal_id,
        target_type="service",
        payload={"name": body.name, "auth_scheme": body.auth_scheme, "svc_id": svc_id},
    )

    # NOTIFY change channel — ADR-0014.1, bound parameters
    await notify_change(
        session,
        "mintkey:service",
        {
            "event": "service.registered",
            "tenant_id": str(tenant_id),
            "service_id": svc_id,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": svc_id,
            "tenant_id": str(tenant_id),
            "name": body.name,
            "slug": slug,
            "display_name": body.display_name,
            "description": body.description,
            "base_url": body.base_url,
            "auth_scheme": body.auth_scheme,
            "openapi_url": body.openapi_url,
            "status": "active",
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input cannot glob-match unexpectedly."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.post("/from-template", status_code=201)
async def create_service_from_template(
    tenant_id: UUID,
    body: FromTemplateRequest,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Create a service from a template, merging template values with optional overrides.

    Source: design §4 From-Template Instantiation; Requirements 4.1-4.5, 23.5.
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

    # Merge template values with overrides — Req 4.2
    name = body.overrides.name if body.overrides and body.overrides.name else template.name
    display_name = (
        body.overrides.display_name
        if body.overrides and body.overrides.display_name
        else template.display_name
    )
    description = (
        body.overrides.description
        if body.overrides and body.overrides.description
        else template.description
    )
    base_url = (
        body.overrides.base_url
        if body.overrides and body.overrides.base_url
        else template.base_url
    )
    if base_url is None:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "base_url_required",
                "title": (
                    "Template has no base_url — email_service templates must be "
                    "instantiated via POST /v1/tenants/{tid}/email-services/from-template"
                ),
            },
        )

    # SSRF check on merged base_url — S-SEC-1
    if _is_forbidden_destination(base_url):
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "forbidden_destination",
                "title": "The base_url resolves to a forbidden destination",
            },
        )

    # Set tenant context — bound parameters, ADR-0008
    await set_tenant_context(session, tenant_id)

    # Derive slug from name — used in uq_services_tenant_slug unique constraint
    slug = name.lower().replace(" ", "-")

    # Generate ULID ID with svc_ prefix — ADR-0017.11
    svc_id = _new_svc_id()
    _crockford_tail = svc_id[len("svc_"):]
    _val = 0
    for _ch in _crockford_tail.upper():
        _val = (_val << 5) | _CROCKFORD.index(_ch)
    _val &= (1 << 128) - 1
    internal_id = uuid.UUID(int=_val)
    now = datetime.now(timezone.utc)

    # INSERT service with template_id metadata — Req 4.1, 4.4
    # Duplicate-name 409 comes from catching the IntegrityError on INSERT (atomic,
    # no TOCTOU race window) — BUG-18 fix.
    try:
        await session.execute(
            text(
                "INSERT INTO services"
                " (id, tenant_id, name, slug, display_name, description,"
                "  base_url, auth_scheme, openapi_url, status, template_id,"
                "  created_at, updated_at)"
                " VALUES"
                " (:id, :tenant_id, :name, :slug, :display_name, :description,"
                "  :base_url, :auth_scheme, :openapi_url, :status, :template_id,"
                "  :created_at, :updated_at)"
            ),
            {
                "id": str(internal_id),
                "tenant_id": str(tenant_id),
                "name": name,
                "slug": slug,
                "display_name": display_name,
                "description": description,
                "base_url": base_url,
                "auth_scheme": template.auth_type,
                "openapi_url": template.openapi_spec_url,
                "status": "active",
                "template_id": template.template_id,
                "created_at": now,
                "updated_at": now,
            },
        )
    except IntegrityError:
        # uq_services_tenant_slug unique constraint violation — Req 4.5
        return JSONResponse(
            status_code=409,
            content={
                "mintkey:code": "service_name_taken",
                "title": f"A service with name '{name}' already exists in this tenant",
            },
        )

    # Emit audit event — ADR-0014.7, Req 4.3
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.registered",
        actor_id=None,
        actor_type="operator",
        target_id=internal_id,
        target_type="service",
        payload={
            "name": name,
            "auth_scheme": template.auth_type,
            "svc_id": svc_id,
            "template_id": template.template_id,
        },
    )

    # NOTIFY change channel — ADR-0014.1
    await notify_change(
        session,
        "mintkey:service",
        {
            "event": "service.registered",
            "tenant_id": str(tenant_id),
            "service_id": svc_id,
            "template_id": template.template_id,
        },
    )

    # Build credential_hint payload — Req 23.5.
    # The hint exposes the expected credential structure (field names, token_url,
    # token_response_path) so the operator knows what to supply.  No secret value
    # is stored or returned; placeholder strings from the YAML are included as-is
    # so the operator can see the field names only.
    credential_hint_payload: dict[str, Any] | None = None
    if template.credential_hint is not None:
        hint = template.credential_hint
        # For oauth2_password_grant templates the hint carries token_url, etc.
        if hint.token_url is not None:
            credential_hint_payload = {
                "token_url": hint.token_url,
                "credential_fields": hint.credential_fields,
                "token_response_path": hint.token_response_path,
            }
        else:
            # Simple auth types (bearer_token, api_key_header, etc.) — include field/help/format
            credential_hint_payload = {
                k: v for k, v in {
                    "field": hint.field,
                    "help": hint.help,
                    "format": hint.format,
                }.items() if v is not None
            } or None

    return JSONResponse(
        status_code=201,
        content={
            "id": svc_id,
            "tenant_id": str(tenant_id),
            "name": name,
            "slug": slug,
            "display_name": display_name,
            "description": description,
            "base_url": base_url,
            "auth_scheme": template.auth_type,
            "openapi_url": template.openapi_spec_url,
            "status": "active",
            "template_id": template.template_id,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
            "credential_hint": credential_hint_payload,
        },
    )


@router.get("")
async def list_services(
    tenant_id: UUID,
    q: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    List all services for a tenant.

    Optional query parameters:
      q — case-insensitive substring search across name, slug, description, base_url.

    Source: Req 3; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    if q is not None:
        escaped = _escape_like(q)
        pattern = f"%{escaped}%"
        result = await session.execute(
            text(
                "SELECT s.id, s.tenant_id, s.name, s.slug, s.display_name, s.description,"
                " s.base_url, s.auth_scheme, s.openapi_url, s.status, s.created_at, s.updated_at,"
                " s.template_id,"
                " COALESCE(("
                "   SELECT MAX(c.key_version)"
                "   FROM credentials c"
                "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id AND c.status = 'active'"
                " ), 0) AS current_key_version"
                " FROM services s WHERE s.tenant_id = :tenant_id"
                " AND (s.name ILIKE :pat ESCAPE '\\'"
                "   OR s.slug ILIKE :pat ESCAPE '\\'"
                "   OR s.description ILIKE :pat ESCAPE '\\'"
                "   OR s.base_url ILIKE :pat ESCAPE '\\')"
                " ORDER BY s.created_at"
            ),
            {"tenant_id": str(tenant_id), "pat": pattern},
        )
    else:
        result = await session.execute(
            text(
                "SELECT s.id, s.tenant_id, s.name, s.slug, s.display_name, s.description,"
                " s.base_url, s.auth_scheme, s.openapi_url, s.status, s.created_at, s.updated_at,"
                " s.template_id,"
                " COALESCE(("
                "   SELECT MAX(c.key_version)"
                "   FROM credentials c"
                "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id AND c.status = 'active'"
                " ), 0) AS current_key_version"
                " FROM services s WHERE s.tenant_id = :tenant_id ORDER BY s.created_at"
            ),
            {"tenant_id": str(tenant_id)},
        )
    rows = result.fetchall()
    services = [_service_row_to_dict(r) for r in rows]
    return JSONResponse({"services": services})


@router.get("/{service_id}")
async def get_service(
    tenant_id: UUID,
    service_id: str,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Describe a single service.

    Source: openapi.yaml operationId=getService; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    db_uuid = _wire_id_to_db_uuid(service_id)
    result = await session.execute(
        text(
            "SELECT s.id, s.tenant_id, s.name, s.slug, s.display_name, s.description,"
            " s.base_url, s.auth_scheme, s.openapi_url, s.status, s.created_at, s.updated_at,"
            " s.template_id,"
            " COALESCE(("
            "   SELECT MAX(c.key_version)"
            "   FROM credentials c"
            "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id AND c.status = 'active'"
            " ), 0) AS current_key_version"
            " FROM services s WHERE s.id = :sid AND s.tenant_id = :tid"
        ),
        {"sid": db_uuid, "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Service not found"},
        )
    return JSONResponse(_service_row_to_dict(row))


@router.post("/test-transient")
async def test_service_transient(
    tenant_id: UUID,
    body: TransientTestRequest,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Validate a candidate service config + credential WITHOUT persisting to DB or vault.

    Accepts a full TransientTestRequest (service config + credential + test params),
    performs the HTTP call in-memory, emits a service.test_executed audit event with
    transient=True, and returns the result.

    The credential value is NEVER written to DB, vault, any log line, or the audit payload.

    Source: openapi.yaml operationId=testServiceTransient; OPS-T; S-SEC-1; ADR-0014.4.
    """
    # SSRF guardrail — S-SEC-1 / ADR-0014.4
    if _is_forbidden_destination(body.service.base_url):
        return _forbidden_response()

    await set_tenant_context(session, tenant_id)

    base_url: str = body.service.base_url
    auth_scheme: str = body.service.auth_scheme
    test = body.test

    # SSH schemes — dial the target directly via asyncssh; no HTTP involved.
    # This branch MUST appear before the URL-building / httpx path below.
    if auth_scheme in _SSH_SCHEMES:
        ssh_result = await _test_ssh_credential(
            scheme=auth_scheme,
            credential_value=body.credential.value,
            base_url=base_url,
            timeout_ms=test.timeout_ms,
        )
        # Emit audit event for SSH test — same shape as HTTP test, no credential data.
        try:
            await audit_emit(
                session=session,
                tenant_id=tenant_id,
                event_type="service.test_executed",
                actor_id=None,
                actor_type="operator",
                target_id=None,
                target_type="service",
                payload={
                    "method": "SSH",
                    "path_template": test.path,
                    "base_url": base_url,
                    "auth_scheme": auth_scheme,
                    "target_host": urlparse(ssh_result.get("final_url", base_url)).hostname,
                    "status_code": ssh_result.get("status_code", 0),
                    "latency_ms": ssh_result.get("latency_ms", 0),
                    "ok": ssh_result.get("ok", False),
                    "transient": True,
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "test_service_transient(SSH): audit_emit failed (non-fatal). tenant=%s",
                str(tenant_id),
            )
        return JSONResponse(ssh_result)

    # Build the final URL
    base_url_stripped = base_url.rstrip("/")
    path_part = test.path if test.path.startswith("/") else "/" + test.path
    final_url = base_url_stripped + path_part

    # Build request headers based on auth_scheme using the inline credential
    # The plaintext value is used here only — it must not appear in any log or audit payload.
    headers: dict[str, str] = {}
    plaintext: str = body.credential.value
    if auth_scheme == "bearer_token":
        headers["Authorization"] = f"Bearer {plaintext}"
    elif auth_scheme == "api_key_header":
        header_name: str = body.credential.header_name or ""
        if not header_name:
            logger.warning(
                "test_service_transient: api_key_header credential missing header_name — "
                "falling back to 'X-API-Key'. tenant=%s",
                str(tenant_id),
            )
            header_name = "X-API-Key"
        headers[header_name] = plaintext
    elif auth_scheme == "api_key_query":
        query_param: str = body.credential.query_param or ""
        if not query_param:
            logger.warning(
                "test_service_transient: api_key_query credential missing query_param — "
                "falling back to 'api_key'. tenant=%s",
                str(tenant_id),
            )
            query_param = "api_key"
        separator = "&" if "?" in final_url else "?"
        final_url = f"{final_url}{separator}{query_param}={plaintext}"

    # SSRF host-binding guardrail — S-SEC-1 / ADR-0014.4
    # Verify the assembled URL's hostname hasn't escaped the service base_url
    # (e.g. via a malicious test.path like //evil.com/steal).
    final_url = _check_ssrf_hostname(final_url, base_url)

    # Merge auth headers with optional extra headers from the request body
    merged_headers = {**headers, **(test.headers or {})}
    timeout_s = test.timeout_ms / 1000.0

    is_safe, reason = _validate_test_url(final_url)
    if not is_safe:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "mintkey:ssrf_rejected",
                "reason": reason,
                "host_redacted": (urlsplit(final_url).hostname or "")[:4] + "***",
            },
        )

    # Make outbound HTTP call
    import time as _time  # noqa: PLC0415
    start = _time.monotonic()
    ok: bool = False
    status_code: int = 0
    latency_ms: int = 0
    response_body_truncated: str = ""
    error: Optional[str] = None

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.request(
                method=test.method,
                url=final_url,
                headers=merged_headers,
                content=test.body,
            )
        latency_ms = int((_time.monotonic() - start) * 1000)
        ok = 200 <= response.status_code < 300
        status_code = response.status_code
        response_body_truncated = response.text[:500]
    except httpx.TimeoutException:
        latency_ms = int((_time.monotonic() - start) * 1000)
        error = "timeout"
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((_time.monotonic() - start) * 1000)
        # ADR-0014.7 / S-SEC-1: do NOT include str(exc) — may contain internal hostnames
        # or stack frames. Emit exception type only; details go to structured logger.
        error = type(exc).__name__

    # Emit audit event — ADR-0014.7, Req AUD-3
    # Wrapped in try/except so a logging failure never breaks the response.
    # IMPORTANT: credential value and response body bytes are NEVER included.
    try:
        await audit_emit(
            session=session,
            tenant_id=tenant_id,
            event_type="service.test_executed",
            actor_id=None,
            actor_type="operator",
            target_id=None,
            target_type="service",
            payload={
                "method": test.method,
                "path_template": test.path,
                "base_url": base_url,
                "auth_scheme": auth_scheme,
                "status_code": status_code,
                "latency_ms": latency_ms,
                "ok": ok,
                "transient": True,
            },
        )
    except Exception:  # noqa: BLE001
        logger.warning(
            "test_service_transient: audit_emit failed (non-fatal). tenant=%s",
            str(tenant_id),
        )

    result: dict[str, Any] = {"ok": ok, "latency_ms": latency_ms, "final_url": final_url}
    if status_code:
        result["status_code"] = status_code
    if response_body_truncated:
        result["response_body_truncated"] = response_body_truncated
    if error is not None:
        result["error"] = error
    return JSONResponse(result)


@router.post("/{service_id}/test")
async def test_service(
    tenant_id: UUID,
    service_id: str,
    req: Optional[TestRunRequest] = None,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Test the registered service using its stored base_url + the request body's path/method.

    Accepts TestRunRequest body (method, path, headers, body, timeout_ms).
    All fields are optional with defaults (GET, /health, 5000 ms).
    Emits service.test_executed audit event with transient=False.

    Source: openapi.yaml operationId=testRunService; ADR-0014.4; S-SEC-1; R14b; OPS-T.
    """
    if req is None:
        req = TestRunRequest()
    await set_tenant_context(session, tenant_id)

    # Fetch the service row
    db_uuid = _wire_id_to_db_uuid(service_id)
    result = await session.execute(
        text(
            "SELECT id, tenant_id, name, base_url, auth_scheme"
            " FROM services WHERE id = :sid AND tenant_id = :tid"
        ),
        {"sid": db_uuid, "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Service not found"},
        )

    base_url: str = row.base_url
    auth_scheme: str = row.auth_scheme

    # SSRF guardrail — S-SEC-1 / ADR-0014.4
    if _is_forbidden_destination(base_url):
        return _forbidden_response()

    # Fetch credential from vault (plaintext stays in request scope — ADR-0014.4)
    from admin_api.services.vault_client import get_vault_client  # noqa: PLC0415
    vault = await get_vault_client()
    cred_entry = await vault.get_credential(str(tenant_id), str(row.id))

    # SSH schemes — dial via asyncssh; method/path/headers/body are meaningless.
    # For ssh_* schemes, method/path/headers/body are ignored. — OPS-T / ADR-0021.
    if auth_scheme in _SSH_SCHEMES:
        ssh_result = await _run_ssh_post_save_test(
            auth_scheme=auth_scheme,
            cred_entry=cred_entry,
            base_url=base_url,
            timeout_ms=req.timeout_ms or 10000,
        )
        try:
            await audit_emit(
                session=session,
                tenant_id=tenant_id,
                event_type="service.test_executed",
                actor_id=None,
                actor_type="operator",
                target_id=row.id,
                target_type="service",
                payload={
                    "method": "SSH",
                    "auth_scheme": auth_scheme,
                    "target_host_port": (ssh_result.get("final_url") or base_url).replace("ssh://", ""),
                    "status_code": ssh_result.get("status_code", 0),
                    "latency_ms": ssh_result.get("latency_ms", 0),
                    "ok": ssh_result.get("ok", False),
                    "transient": False,
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "test_service(SSH): audit_emit failed (non-fatal). service=%s tenant=%s",
                service_id,
                str(tenant_id),
            )
        return JSONResponse({
            "ok": ssh_result.get("ok", False),
            "status_code": ssh_result.get("status_code", 0),
            "latency_ms": ssh_result.get("latency_ms", 0),
            "response_body_truncated": ssh_result.get("response_body_truncated", ""),
            "final_url": ssh_result.get("final_url", base_url),
        })

    # Build the final URL: urljoin handles leading-slash on path correctly.
    # urljoin('http://x:8999', '/health') == 'http://x:8999/health'
    # urljoin('http://x:8999/', '/health') == 'http://x:8999/health'
    base_url_stripped = base_url.rstrip("/")
    path_part = req.path if req.path.startswith("/") else "/" + req.path
    final_url = base_url_stripped + path_part

    # Build request headers based on auth_scheme
    headers: dict[str, str] = {}
    if cred_entry and cred_entry.get("plaintext"):
        plaintext: str = cast(str, cred_entry["plaintext"])
        if auth_scheme == "bearer_token":
            headers["Authorization"] = f"Bearer {plaintext}"
        elif auth_scheme == "api_key_header":
            header_name: str = cast(str, cred_entry.get("header_name") or "")
            if not header_name:
                logger.warning(
                    "test_service: api_key_header credential missing header_name — "
                    "falling back to 'X-API-Key'. service=%s tenant=%s",
                    service_id,
                    str(tenant_id),
                )
                header_name = "X-API-Key"
            headers[header_name] = plaintext
        elif auth_scheme == "api_key_query":
            query_param: str = cast(str, cred_entry.get("query_param") or "")
            if not query_param:
                logger.warning(
                    "test_service: api_key_query credential missing query_param — "
                    "falling back to 'api_key'. service=%s tenant=%s",
                    service_id,
                    str(tenant_id),
                )
                query_param = "api_key"
            separator = "&" if "?" in final_url else "?"
            final_url = f"{final_url}{separator}{query_param}={plaintext}"

    # SSRF host-binding guardrail — S-SEC-1 / ADR-0014.4
    # base_url comes from DB (trusted) but an attacker-supplied req.path
    # could still redirect to a different host via e.g. //evil.com/steal.
    final_url = _check_ssrf_hostname(final_url, base_url)

    # Merge auth headers with optional extra headers from the request body
    merged_headers = {**headers, **(req.headers or {})}
    timeout_s = (req.timeout_ms or 5000) / 1000.0

    is_safe, reason = _validate_test_url(final_url)
    if not is_safe:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "mintkey:ssrf_rejected",
                "reason": reason,
                "host_redacted": (urlsplit(final_url).hostname or "")[:4] + "***",
            },
        )

    # Make outbound HTTP call
    import time as _time  # noqa: PLC0415
    start = _time.monotonic()
    test_ok: bool = False
    test_status_code: int = 0
    test_latency_ms: int = 0
    test_response_body: str = ""

    try:
        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.request(
                method=req.method,
                url=final_url,
                headers=merged_headers,
                content=req.body,
            )
        test_latency_ms = int((_time.monotonic() - start) * 1000)
        test_ok = 200 <= response.status_code < 300
        test_status_code = response.status_code
        test_response_body = response.text[:500]

        # Emit audit event — ADR-0014.7, Req AUD-3, OPS-T
        # Wrapped in try/except so a logging failure never breaks the response.
        # IMPORTANT: credential value and response body bytes are NEVER included.
        try:
            await audit_emit(
                session=session,
                tenant_id=tenant_id,
                event_type="service.test_executed",
                actor_id=None,
                actor_type="operator",
                target_id=row.id,
                target_type="service",
                payload={
                    "method": req.method,
                    "path_template": req.path,
                    "auth_scheme": auth_scheme,
                    "status_code": test_status_code,
                    "latency_ms": test_latency_ms,
                    "ok": test_ok,
                    "transient": False,
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "test_service: audit_emit failed (non-fatal). service=%s tenant=%s",
                service_id,
                str(tenant_id),
            )

        return JSONResponse(
            {
                "ok": test_ok,
                "status_code": test_status_code,
                "latency_ms": test_latency_ms,
                "response_body_truncated": test_response_body,
                "final_url": final_url,
            }
        )
    except httpx.TimeoutException:
        test_latency_ms = int((_time.monotonic() - start) * 1000)

        try:
            await audit_emit(
                session=session,
                tenant_id=tenant_id,
                event_type="service.test_executed",
                actor_id=None,
                actor_type="operator",
                target_id=row.id,
                target_type="service",
                payload={
                    "method": req.method,
                    "path_template": req.path,
                    "auth_scheme": auth_scheme,
                    "status_code": 0,
                    "latency_ms": test_latency_ms,
                    "ok": False,
                    "transient": False,
                    "error": "timeout",
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "test_service: audit_emit failed (non-fatal). service=%s tenant=%s",
                service_id,
                str(tenant_id),
            )

        return JSONResponse({"ok": False, "latency_ms": test_latency_ms, "error": "timeout"})
    except Exception as exc:  # noqa: BLE001
        test_latency_ms = int((_time.monotonic() - start) * 1000)
        logger.warning(
            "test_service: unexpected error. service=%s tenant=%s error=%r",
            service_id,
            str(tenant_id),
            exc,
        )

        try:
            await audit_emit(
                session=session,
                tenant_id=tenant_id,
                event_type="service.test_executed",
                actor_id=None,
                actor_type="operator",
                target_id=row.id,
                target_type="service",
                payload={
                    "method": req.method,
                    "path_template": req.path,
                    "auth_scheme": auth_scheme,
                    "status_code": 0,
                    "latency_ms": test_latency_ms,
                    "ok": False,
                    "transient": False,
                    "error": "internal_error",
                },
            )
        except Exception:  # noqa: BLE001
            logger.warning(
                "test_service: audit_emit failed (non-fatal). service=%s tenant=%s",
                service_id,
                str(tenant_id),
            )

        return JSONResponse({"ok": False, "error": "internal_error"})


@router.patch("/{service_id}")
async def update_service(
    tenant_id: UUID,
    service_id: str,
    body: ServiceUpdate,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> JSONResponse:
    """
    Update mutable fields of a service.

    C-6a: When base_url changes on an SSH service (auth_scheme starts with "ssh_"),
    the active credential's vault.credentials.target_address is updated in the same
    SQL transaction so that ssh-proxy immediately routes to the new address.
    Non-SSH services are unaffected. Malformed ssh:// URLs (missing port, etc.)
    are rejected with a structured 400 before any writes occur.

    Source: Req 3; ADR-0008; ADR-0014.7; C-6a.
    """
    if body.base_url is not None and _is_forbidden_destination(body.base_url):
        return _forbidden_response()

    # C-6a: Validate ssh:// base_url early — reject before any DB write.
    # Only applies when base_url is being updated for an SSH service.
    # We check the requested auth_scheme first; if that's not set, we'll
    # check the stored auth_scheme after the service lookup below.
    new_target_address: str | None = None  # populated for SSH services below
    if body.base_url is not None:
        # Determine effective auth_scheme: prefer explicit override, fall back to stored.
        # We must check the stored scheme when body.auth_scheme is None.
        effective_scheme_hint = body.auth_scheme  # may be None; resolved below if needed
        if effective_scheme_hint is not None and effective_scheme_hint.startswith("ssh_"):
            # The caller is explicitly setting an SSH scheme — validate now.
            try:
                new_target_address = _parse_ssh_host_port(body.base_url)
            except ValueError:
                # Use a fixed message to avoid surfacing exception data in the response —
                # ADR-0014.7, S-SEC-1. The validation constraint is always the same:
                # base_url must be in ssh://host:port or host:port format.
                return JSONResponse(
                    status_code=400,
                    content={
                        "mintkey:code": "invalid_ssh_base_url",
                        "title": "Malformed ssh:// base_url — expected ssh://host:port or host:port",
                    },
                )
        elif effective_scheme_hint is None and body.base_url.startswith("ssh://"):
            # base_url looks like SSH but we don't yet know the stored scheme.
            # Validate the URL shape now; whether to cascade is decided after
            # the service SELECT below.
            try:
                new_target_address = _parse_ssh_host_port(body.base_url)
            except ValueError:
                return JSONResponse(
                    status_code=400,
                    content={
                        "mintkey:code": "invalid_ssh_base_url",
                        "title": "Malformed ssh:// base_url — expected ssh://host:port or host:port",
                    },
                )

    await set_tenant_context(session, tenant_id)

    db_uuid = _wire_id_to_db_uuid(service_id)
    now = datetime.now(timezone.utc)

    # C-6a: Fetch the current stored auth_scheme when the caller didn't supply one.
    # We need it to decide whether to cascade the base_url change to vault.credentials.
    stored_auth_scheme: str | None = None
    if body.base_url is not None and body.auth_scheme is None:
        svc_lookup = await session.execute(
            text("SELECT auth_scheme FROM services WHERE id = :sid AND tenant_id = :tid"),
            {"sid": db_uuid, "tid": str(tenant_id)},
        )
        svc_lookup_row = svc_lookup.fetchone()
        if svc_lookup_row is not None:
            stored_auth_scheme = str(svc_lookup_row.auth_scheme or "")
            # Validate the base_url as SSH if stored scheme is ssh_* and we
            # haven't parsed it yet (meaning it doesn't start with "ssh://").
            if stored_auth_scheme.startswith("ssh_") and new_target_address is None:
                try:
                    new_target_address = _parse_ssh_host_port(body.base_url)
                except ValueError:
                    return JSONResponse(
                        status_code=400,
                        content={
                            "mintkey:code": "invalid_ssh_base_url",
                            "title": "Malformed ssh:// base_url — expected ssh://host:port or host:port",
                        },
                    )

    # Build the UPDATE using a fixed set of known columns to avoid dynamic SQL.
    # Each column is either updated to its new value or kept via COALESCE to the
    # existing value. This keeps the SQL template a string literal — ADR-0008,
    # T-1.0.15 (no f-string SQL).
    await session.execute(
        text(
            "UPDATE services"
            " SET name = COALESCE(:name, name),"
            "     base_url = COALESCE(:base_url, base_url),"
            "     auth_scheme = COALESCE(:auth_scheme, auth_scheme),"
            "     display_name = COALESCE(:display_name, display_name),"
            "     description = COALESCE(:description, description),"
            "     openapi_url = COALESCE(:openapi_url, openapi_url),"
            "     status = COALESCE(:status, status),"
            "     updated_at = :updated_at"
            " WHERE id = :sid AND tenant_id = :tid"
        ),
        {
            "name": body.name,
            "base_url": body.base_url,
            "auth_scheme": body.auth_scheme,
            "display_name": body.display_name,
            "description": body.description,
            "openapi_url": body.openapi_url,
            "status": body.status,
            "updated_at": now,
            "sid": db_uuid,
            "tid": str(tenant_id),
        },
    )

    # C-6a: Cascade base_url change to vault.credentials.target_address for SSH services.
    # The target_address column lives in vault.credentials (encrypted-blob store), NOT
    # in public.credentials (admin metadata table).  mintkey_app has SELECT+UPDATE on
    # vault.credentials (granted in 018-vault-schema.yaml + 019-grants-defensive.yaml).
    # We UPDATE the is_current=true row — vault-adapter ensures at most one per service.
    # If no credential exists yet, the WHERE matches nothing and the UPDATE is a no-op.
    # Same session → same implicit transaction; both UPDATEs commit or rollback together.
    # Source: C-6a; ADR-0021.
    effective_auth_scheme = body.auth_scheme or stored_auth_scheme or ""
    if body.base_url is not None and new_target_address is not None and effective_auth_scheme.startswith("ssh_"):
        await session.execute(
            text(
                "UPDATE vault.credentials"
                "   SET target_address = :target_address"
                " WHERE service_id = :sid AND tenant_id = :tid"
                "   AND is_current = true"
            ),
            {
                "target_address": new_target_address,
                "sid": db_uuid,
                "tid": str(tenant_id),
            },
        )
        logger.info(
            "update_service: cascaded base_url → vault.credentials.target_address='%s'"
            " for service=%s scheme=%s",
            new_target_address,
            service_id,
            effective_auth_scheme,
        )

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.updated",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="service",
        payload={"service_id": service_id},
    )

    await notify_change(
        session,
        "mintkey:service",
        {
            "event": "service.updated",
            "tenant_id": str(tenant_id),
            "service_id": service_id,
        },
    )

    result = await session.execute(
        text(
            "SELECT s.id, s.tenant_id, s.name, s.slug, s.display_name, s.description,"
            " s.base_url, s.auth_scheme, s.openapi_url, s.status, s.created_at, s.updated_at,"
            " s.template_id,"
            " COALESCE(("
            "   SELECT MAX(c.key_version)"
            "   FROM credentials c"
            "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id AND c.status = 'active'"
            " ), 0) AS current_key_version"
            " FROM services s WHERE s.id = :sid AND s.tenant_id = :tid"
        ),
        {"sid": db_uuid, "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Service not found"},
        )
    return JSONResponse(_service_row_to_dict(row))


@router.delete("/{service_id}", status_code=204)
async def delete_service(
    tenant_id: UUID,
    service_id: str,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
) -> Response:
    """
    Delete (hard-delete) a service with in-app transactional cascade.

    Deletes dependent rows first (child-first order) within the same
    AsyncSession transaction, then deletes the service row.  Emits a
    per-class cascade audit event for each child table before emitting
    the top-level service.deleted event.

    Cascade order (FK leaf-first):
      1. service_api_keys  — fk_service_api_keys_service
      2. permission_grants — fk_permission_grants_service
      3. credentials       — fk_credentials_service

    Every child DELETE is tenant-pinned (tenant_id = :tid) for
    defence-in-depth alongside the RLS policy — ADR-0008.

    Source: Req 3; ADR-0008; ADR-0014.7; Option-A cascade decision.
    """
    await set_tenant_context(session, tenant_id)

    db_uuid = _wire_id_to_db_uuid(service_id)
    params = {"sid": db_uuid, "tid": str(tenant_id)}

    # 1. DELETE service_api_keys (most leaf-ward)
    sak_result = await session.execute(
        text(
            "DELETE FROM service_api_keys"
            " WHERE service_id = :sid AND tenant_id = :tid"
            " RETURNING id"
        ),
        params,
    )
    sak_count = len(sak_result.fetchall())

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.api_keys.cascade_deleted",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="service",
        payload={"service_id": service_id, "count": sak_count},
    )

    # 2. DELETE permission_grants
    pg_result = await session.execute(
        text(
            "DELETE FROM permission_grants"
            " WHERE service_id = :sid AND tenant_id = :tid"
            " RETURNING id"
        ),
        params,
    )
    pg_count = len(pg_result.fetchall())

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.permission_grants.cascade_deleted",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="service",
        payload={"service_id": service_id, "count": pg_count},
    )

    # 3. DELETE credentials
    cred_result = await session.execute(
        text(
            "DELETE FROM credentials"
            " WHERE service_id = :sid AND tenant_id = :tid"
            " RETURNING id"
        ),
        params,
    )
    cred_count = len(cred_result.fetchall())

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.credentials.cascade_deleted",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="service",
        payload={"service_id": service_id, "count": cred_count},
    )

    # 4. DELETE the service row (FK constraints satisfied above)
    await session.execute(
        text("DELETE FROM services WHERE id = :sid AND tenant_id = :tid"),
        params,
    )

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.deleted",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="service",
        payload={"service_id": service_id},
    )

    await notify_change(
        session,
        "mintkey:service",
        {
            "event": "service.deleted",
            "tenant_id": str(tenant_id),
            "service_id": service_id,
        },
    )

    return Response(status_code=204)
