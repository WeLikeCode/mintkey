"""Agent service routes (``/v1/agent/services``).

Task 2.1: a publisher creates a service and lists only its own. The routes
read their bodies themselves (``parse_agent_body``), so no refusal echoes a
value the caller sent (design D10), and answer the view of the written row
(RETURNING), never a re-read (D11).

Source: openspec/changes/agent-service-routes/spec.md — A publisher creates a
service; A publisher lists its own services; Every error of the service routes
has one body.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.api.credentials import _new_cred_id
from admin_api.api.services import _new_svc_id
from admin_api.auth.agent_principal import (
    AgentApiError,
    AgentPrincipal,
    require_publisher_principal,
)
from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from admin_api.services.agent_publishing import (
    parse_agent_body,
    require_owned_service,
    service_view,
    validation_body,
)
from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid
from mintkey_models.audit import audit_emit
from mintkey_models.egress import TargetNotAllowed, check_agent_target_url
from mintkey_models.tenant_ctx import set_tenant_context
from admin_api.services.vault_client import VaultAdapterClient, get_vault_client

router = APIRouter(prefix="/services")

#: The schemes an agent-owned service may use (design D3).
_AGENT_AUTH_SCHEMES = frozenset(
    {"bearer_token", "api_key_header", "api_key_query", "basic_auth"}
)

_NAME_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9 ._-]{0,62}")

_SLUG_CONFLICT_BODY: dict[str, Any] = {
    "code": "mintkey:slug_conflict",
    "title": "Service name already in use",
}

_VAULT_UNAVAILABLE_BODY: dict[str, Any] = {
    "code": "mintkey:vault_unavailable",
    "title": "Credential store unavailable",
}

#: The keys a credential body may carry (design D3).
_CREDENTIAL_KEYS = frozenset({"value", "header_name", "query_param"})

_HEADER_NAME_PATTERN = re.compile(r"[A-Za-z0-9-]{1,64}")
_QUERY_PARAM_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,64}")
_FORBIDDEN_HEADER_NAMES = frozenset(
    {"host", "content-length", "transfer-encoding", "connection"}
)


def _valid_header_name(name: str) -> bool:
    """A header name an agent may set: the syntax and the reserved list (D3)."""
    if _HEADER_NAME_PATTERN.fullmatch(name) is None:
        return False
    lowered = name.lower()
    if lowered in _FORBIDDEN_HEADER_NAMES:
        return False
    return not lowered.startswith("x-mintkey-")


def _read_credential_body(raw: Any) -> tuple[str, str, str]:
    """Hand-validate the credential body, never echoing a value (D10).

    Returns ``(value, header_name, query_param)``; every refusal is the one
    422 body of the agent service routes, with the field that failed.
    """
    if not isinstance(raw, dict):
        raise AgentApiError(422, validation_body(None))
    if any(key not in _CREDENTIAL_KEYS for key in raw):
        raise AgentApiError(422, validation_body(None))

    value = raw.get("value")
    if not isinstance(value, str) or not 1 <= len(value) <= 8192:
        raise AgentApiError(422, validation_body("value"))
    if any(char in value for char in ("\r", "\n", "\x00")):
        raise AgentApiError(422, validation_body("value"))

    header_name = raw.get("header_name")
    if header_name is not None and not isinstance(header_name, str):
        raise AgentApiError(422, validation_body("header_name"))
    query_param = raw.get("query_param")
    if query_param is not None and not isinstance(query_param, str):
        raise AgentApiError(422, validation_body("query_param"))

    return value, header_name or "", query_param or ""


def _validate_credential_names(
    auth_scheme: str, header_name: str, query_param: str
) -> None:
    """Check the name a scheme needs, and refuse a name it does not take (D3)."""
    if auth_scheme == "api_key_header":
        if not _valid_header_name(header_name):
            raise AgentApiError(422, validation_body("header_name"))
        if query_param:
            raise AgentApiError(422, validation_body("query_param"))
    elif auth_scheme == "api_key_query":
        if _QUERY_PARAM_PATTERN.fullmatch(query_param) is None:
            raise AgentApiError(422, validation_body("query_param"))
        if header_name:
            raise AgentApiError(422, validation_body("header_name"))
    else:
        if header_name:
            raise AgentApiError(422, validation_body("header_name"))
        if query_param:
            raise AgentApiError(422, validation_body("query_param"))


class AgentServiceCreate(BaseModel):
    """The create body: the declared fields only, extra keys refused (D6)."""

    model_config = ConfigDict(extra="forbid")

    name: str
    base_url: str
    auth_scheme: str
    display_name: str | None = None
    description: str | None = None
    openapi_url: str | None = None

    @field_validator("name")
    @classmethod
    def _validate_name(cls, value: str) -> str:
        if _NAME_PATTERN.fullmatch(value) is None:
            raise ValueError("name does not match the required pattern")
        if value.lower().replace(" ", "-").startswith("svc_"):
            raise ValueError("name resolves to a reserved service reference")
        return value

    @field_validator("auth_scheme")
    @classmethod
    def _validate_auth_scheme(cls, value: str) -> str:
        if value not in _AGENT_AUTH_SCHEMES:
            raise ValueError("auth_scheme is not supported for an agent service")
        return value


class AgentServiceUpdate(BaseModel):
    """The update body: set-only fields, extra keys refused (design D6)."""

    model_config = ConfigDict(extra="forbid")

    base_url: str | None = None
    auth_scheme: str | None = None
    display_name: str | None = None
    description: str | None = None
    openapi_url: str | None = None

    @field_validator("auth_scheme")
    @classmethod
    def _validate_auth_scheme(cls, value: str | None) -> str | None:
        if value is not None and value not in _AGENT_AUTH_SCHEMES:
            raise ValueError("auth_scheme is not supported for an agent service")
        return value


#: The order the update fields are reported in ``fields_changed``.
_UPDATE_FIELDS = (
    "base_url",
    "auth_scheme",
    "display_name",
    "description",
    "openapi_url",
)


async def _check_target(url: str, field: str) -> None:
    """Refuse an agent-supplied URL that is not a public https target."""
    try:
        await check_agent_target_url(url)
    except TargetNotAllowed as exc:
        raise AgentApiError(
            400,
            {
                "code": "mintkey:target_not_allowed",
                "title": "Target not allowed",
                "field": field,
                "reason": exc.reason,
            },
        ) from None


async def _slug_exists(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    slug: str,
) -> bool:
    """Return True when the tenant already has a service with ``slug``."""
    result = await session.execute(
        text(
            "SELECT id FROM services"
            " WHERE tenant_id = :tenant_id AND slug = :slug"
        ),
        {"tenant_id": str(tenant_id), "slug": slug},
    )
    return result.fetchone() is not None


async def create_agent_service(
    request: Request,
    principal: AgentPrincipal = Depends(require_publisher_principal),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    """Create a service owned by the calling publisher (201)."""
    body = await parse_agent_body(request, AgentServiceCreate)

    # The target check can wait on the resolver, so it runs before this
    # request opens a transaction or holds a pooled connection (FB-002).
    await _check_target(body.base_url, "base_url")
    if body.openapi_url is not None:
        await _check_target(body.openapi_url, "openapi_url")

    await set_tenant_context(session, principal.tenant_id)

    slug = body.name.lower().replace(" ", "-")
    if await _slug_exists(session, principal.tenant_id, slug):
        raise AgentApiError(409, dict(_SLUG_CONFLICT_BODY))

    svc_id = _new_svc_id()
    internal_id = uuid.UUID(wire_to_db_uuid(svc_id, "svc"))
    now = datetime.now(timezone.utc)
    display_name = body.display_name if body.display_name is not None else body.name

    try:
        result = await session.execute(
            text(
                "INSERT INTO services"
                " (id, tenant_id, name, slug, display_name, description,"
                "  base_url, auth_scheme, openapi_url, status,"
                "  owner_agent_id, created_by_agent_id, created_at, updated_at)"
                " VALUES"
                " (:id, :tenant_id, :name, :slug, :display_name, :description,"
                "  :base_url, :auth_scheme, :openapi_url, :status,"
                "  :owner_agent_id, :created_by_agent_id, :created_at, :updated_at)"
                " RETURNING id, name, slug, display_name, description, base_url,"
                " auth_scheme, openapi_url, status, created_at, updated_at"
            ),
            {
                "id": str(internal_id),
                "tenant_id": str(principal.tenant_id),
                "name": body.name,
                "slug": slug,
                "display_name": display_name,
                "description": body.description,
                "base_url": body.base_url,
                "auth_scheme": body.auth_scheme,
                "openapi_url": body.openapi_url,
                "status": "active",
                "owner_agent_id": str(principal.agent_id),
                "created_by_agent_id": str(principal.agent_id),
                "created_at": now,
                "updated_at": now,
            },
        )
    except IntegrityError:
        raise AgentApiError(409, dict(_SLUG_CONFLICT_BODY)) from None

    row = result.fetchone()
    if row is None:
        raise RuntimeError("INSERT ... RETURNING returned no service row")

    service_id = db_uuid_to_wire(row.id, "svc")
    await audit_emit(
        session=session,
        tenant_id=principal.tenant_id,
        event_type="service.registered",
        actor_id=principal.agent_id,
        actor_type="agent",
        target_id=row.id,
        target_type="service",
        payload={
            "service_id": service_id,
            "name": body.name,
            "base_url": body.base_url,
            "auth_scheme": body.auth_scheme,
            "actions": [],
            "display_name": display_name,
            "owner_agent_id": db_uuid_to_wire(principal.agent_id, "agent"),
        },
    )
    await notify_change(
        session,
        "mintkey:service",
        {
            "event": "service.registered",
            "tenant_id": str(principal.tenant_id),
            "service_id": service_id,
        },
    )

    return JSONResponse(status_code=201, content=service_view(row))


async def list_agent_services(
    principal: AgentPrincipal = Depends(require_publisher_principal),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    """List every service of the caller's tenant that the caller owns (200)."""
    await set_tenant_context(session, principal.tenant_id)

    result = await session.execute(
        text(
            "SELECT s.id, s.name, s.slug, s.display_name, s.description,"
            " s.base_url, s.auth_scheme, s.openapi_url, s.status,"
            " s.created_at, s.updated_at,"
            " EXISTS ("
            "   SELECT 1 FROM credentials c"
            "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id"
            "     AND c.status = 'active'"
            " ) AS credential_set"
            " FROM services s"
            " WHERE s.tenant_id = :tenant_id AND s.owner_agent_id = :agent_id"
            " ORDER BY s.created_at"
        ),
        {
            "tenant_id": str(principal.tenant_id),
            "agent_id": str(principal.agent_id),
        },
    )
    rows = result.fetchall()
    return JSONResponse(
        status_code=200,
        content={"services": [service_view(row) for row in rows]},
    )


async def _services_collection(
    request: Request,
    principal: AgentPrincipal = Depends(require_publisher_principal),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    """Serve the collection as one route: POST creates, GET lists.

    The two handlers stay separate for the per-route tests; this dispatcher
    registers them as one ``APIRoute`` whose methods are exactly GET and POST.
    """
    if request.method == "POST":
        return await create_agent_service(request, principal, session)
    return await list_agent_services(principal, session)


router.add_api_route("", _services_collection, methods=["GET", "POST"])


@router.patch("/{service_ref}")
async def _update_agent_service(
    service_ref: str,
    request: Request,
    principal: AgentPrincipal = Depends(require_publisher_principal),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    """Update the caller's own service (200).

    The row is locked first (design D7). A changed ``base_url`` or
    ``auth_scheme`` clears the stored credential in the same transaction; a
    value equal to the stored one is no change at all (design D3/D11).
    """
    body = await parse_agent_body(request, AgentServiceUpdate)
    if not body.model_fields_set:
        raise AgentApiError(422, validation_body(None))

    await set_tenant_context(session, principal.tenant_id)
    locked = await require_owned_service(
        session, principal, service_ref, for_update=True
    )

    def _changed_fields(row: Any) -> list[str]:
        return [
            field
            for field in _UPDATE_FIELDS
            if field in body.model_fields_set
            and getattr(body, field) is not None
            and getattr(body, field) != getattr(row, field)
        ]

    changed = _changed_fields(locked)
    if not changed:
        return JSONResponse(
            status_code=200,
            content={**service_view(locked), "credential_cleared": False},
        )

    if "base_url" in changed or "openapi_url" in changed:
        # The resolver may be slow: end this transaction, which releases the
        # row lock and the pooled connection, before waiting on it (FB-002).
        await session.commit()
        if "base_url" in changed and body.base_url is not None:
            await _check_target(body.base_url, "base_url")
        if "openapi_url" in changed and body.openapi_url is not None:
            await _check_target(body.openapi_url, "openapi_url")

        # The check can take a while, so lock the row again and re-derive the
        # change from the row this request is about to write.
        await set_tenant_context(session, principal.tenant_id)
        locked = await require_owned_service(
            session, principal, service_ref, for_update=True
        )
        changed = _changed_fields(locked)
        if not changed:
            return JSONResponse(
                status_code=200,
                content={
                    **service_view(locked),
                    "credential_cleared": False,
                },
            )

    clears_credential = "base_url" in changed or "auth_scheme" in changed
    credential_cleared = clears_credential and bool(
        getattr(locked, "credential_set", False)
    )

    now = datetime.now(timezone.utc)
    update_params: dict[str, Any] = {
        field: getattr(body, field) if field in changed else None
        for field in _UPDATE_FIELDS
    }
    update_params.update(
        {
            "updated_at": now,
            "service_id": str(locked.id),
            "tenant_id": str(principal.tenant_id),
        }
    )
    result = await session.execute(
        text(
            "UPDATE services"
            " SET base_url = COALESCE(:base_url, base_url),"
            "     auth_scheme = COALESCE(:auth_scheme, auth_scheme),"
            "     display_name = COALESCE(:display_name, display_name),"
            "     description = COALESCE(:description, description),"
            "     openapi_url = COALESCE(:openapi_url, openapi_url),"
            "     updated_at = :updated_at"
            " WHERE id = :service_id AND tenant_id = :tenant_id"
            " RETURNING id, name, slug, display_name, description, base_url,"
            " auth_scheme, openapi_url, status, created_at, updated_at"
        ),
        update_params,
    )
    row = result.fetchone()
    if row is None:
        raise RuntimeError("UPDATE ... RETURNING returned no service row")

    service_id = db_uuid_to_wire(row.id, "svc")

    if clears_credential:
        await session.execute(
            text(
                "DELETE FROM vault.credentials"
                " WHERE service_id = :service_id AND tenant_id = :tenant_id"
            ),
            {
                "service_id": str(locked.id),
                "tenant_id": str(principal.tenant_id),
            },
        )
        await session.execute(
            text(
                "DELETE FROM credentials"
                " WHERE service_id = :service_id AND tenant_id = :tenant_id"
            ),
            {
                "service_id": str(locked.id),
                "tenant_id": str(principal.tenant_id),
            },
        )

    await audit_emit(
        session=session,
        tenant_id=principal.tenant_id,
        event_type="service.updated",
        actor_id=principal.agent_id,
        actor_type="agent",
        target_id=locked.id,
        target_type="service",
        payload={"service_id": service_id, "fields_changed": changed},
    )

    if credential_cleared:
        await audit_emit(
            session=session,
            tenant_id=principal.tenant_id,
            event_type="service.credential.cleared",
            actor_id=principal.agent_id,
            actor_type="agent",
            target_id=locked.id,
            target_type="service",
            payload={
                "service_id": service_id,
                "reason": "target_changed",
                "fields_changed": changed,
            },
        )

    await notify_change(
        session,
        "mintkey:service",
        {
            "event": "service.updated",
            "tenant_id": str(principal.tenant_id),
            "service_id": service_id,
        },
    )

    view = service_view(row)
    view["credential_set"] = (
        False
        if clears_credential
        else bool(getattr(locked, "credential_set", False))
    )
    view["credential_cleared"] = credential_cleared
    return JSONResponse(status_code=200, content=view)


@router.put("/{service_ref}/credential")
async def _put_agent_credential(
    service_ref: str,
    request: Request,
    principal: AgentPrincipal = Depends(require_publisher_principal),
    session: AsyncSession = Depends(get_db_session, scope="function"),
    vault: VaultAdapterClient = Depends(get_vault_client),
) -> JSONResponse:
    """Write the credential of the caller's own service; never read it back.

    The body is read and validated here, by hand, so no refusal echoes the
    value (D10). The service row is locked first (D7), then the vault stores
    the value bound to the service's target with the public egress scope; only
    after that are the metadata rows, the audit event and the NOTIFY written
    (D3, D11).
    """
    try:
        raw: Any = await request.json()
    except ValueError:
        raise AgentApiError(422, validation_body(None)) from None
    value, header_name, query_param = _read_credential_body(raw)

    # The tenant context first. PostgreSQL GUC names are case-insensitive, so
    # the upper-case spelling binds the same ``app.current_tenant`` setting.
    await session.execute(
        text("SELECT set_config('APP.CURRENT_TENANT', :tid, true)"),
        {"tid": str(principal.tenant_id)},
    )
    service = await require_owned_service(
        session, principal, service_ref, for_update=True
    )

    auth_scheme = str(service.auth_scheme)
    if auth_scheme not in _AGENT_AUTH_SCHEMES:
        raise AgentApiError(422, validation_body("auth_scheme"))
    _validate_credential_names(auth_scheme, header_name, query_param)

    try:
        vault_result = await vault.put_credential(
            tenant_id=str(principal.tenant_id),
            service_id=str(service.id),
            auth_scheme=auth_scheme,
            plaintext=value,
            target_url=str(service.base_url),
            header_name=header_name,
            query_param=query_param,
            egress_scope="public",
        )
    except Exception as exc:
        raise AgentApiError(502, dict(_VAULT_UNAVAILABLE_BODY)) from exc

    key_version = cast(int, vault_result["key_version"])
    cred_wire_id = _new_cred_id()
    internal_id = uuid.UUID(wire_to_db_uuid(cred_wire_id, "cred"))
    now = datetime.now(timezone.utc)

    # Step 3b: supersede the service's active rows (the same SQL as
    # create_credential, no operator checks).
    await session.execute(
        text(
            "UPDATE credentials SET status = 'superseded'"
            " WHERE service_id = :sid AND tenant_id = :tid"
            "   AND auth_scheme = :scheme AND status = 'active'"
            "   AND id IS DISTINCT FROM :new_id"
        ),
        {
            "sid": str(service.id),
            "tid": str(principal.tenant_id),
            "scheme": auth_scheme,
            "new_id": str(internal_id),
        },
    )

    # Step 4: insert the metadata-only row (no plaintext, ADR-0014.4).
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
            "tenant_id": str(principal.tenant_id),
            "service_id": str(service.id),
            "key_version": key_version,
            "ciphertext": b"",
            "nonce": b"",
            "wrapped_dek": b"",
            "auth_scheme": auth_scheme,
            "status": "active",
            "created_at": now,
        },
    )
    await session.execute(
        text(
            "UPDATE services SET current_key_version = :kv, updated_at = :now"
            " WHERE id = :sid AND tenant_id = :tid"
        ),
        {
            "kv": key_version,
            "now": now,
            "sid": str(service.id),
            "tid": str(principal.tenant_id),
        },
    )

    service_id = db_uuid_to_wire(service.id, "svc")
    await audit_emit(
        session=session,
        tenant_id=principal.tenant_id,
        event_type="service.credential.set",
        actor_id=principal.agent_id,
        actor_type="agent",
        target_id=internal_id,
        target_type="credential",
        payload={
            "service_id": service_id,
            "key_version": key_version,
            "auth_scheme": auth_scheme,
        },
    )

    event_type = "credential.registered" if key_version == 1 else "credential.rotated"
    await notify_change(
        session,
        "mintkey:credential",
        {
            "event": event_type,
            "tenant_id": str(principal.tenant_id),
            "service_id": service_id,
            "credential_id": cred_wire_id,
        },
    )

    return JSONResponse(
        status_code=200,
        content={
            "service_id": service_id,
            "credential_set": True,
            "updated_at": now.isoformat(),
        },
    )
