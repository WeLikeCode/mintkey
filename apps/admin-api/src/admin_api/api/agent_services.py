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
from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, field_validator
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
    service_view,
)
from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid
from mintkey_models.audit import audit_emit
from mintkey_models.egress import TargetNotAllowed, check_agent_target_url
from mintkey_models.tenant_ctx import set_tenant_context

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


@router.post("", status_code=201)
async def create_agent_service(
    request: Request,
    principal: AgentPrincipal = Depends(require_publisher_principal),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    """Create a service owned by the calling publisher (201)."""
    body = await parse_agent_body(request, AgentServiceCreate)

    await set_tenant_context(session, principal.tenant_id)
    await _check_target(body.base_url, "base_url")
    if body.openapi_url is not None:
        await _check_target(body.openapi_url, "openapi_url")

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


@router.get("")
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


async def _update_agent_service(
    service_ref: str,
    request: Request,
    principal: AgentPrincipal = Depends(require_publisher_principal),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    raise NotImplementedError
