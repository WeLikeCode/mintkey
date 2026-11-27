"""Owned-service lookup for the ``/v1/agent`` service routes.

Source: openspec/changes/agent-service-routes (task 1.1; spec
agent-service-routes, requirement "The owned service lookup is one function").
"""

from __future__ import annotations

from typing import Any, Literal
from uuid import UUID

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.agent_principal import AgentApiError, AgentPrincipal
from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid

_NOT_FOUND_BODY: dict[str, Any] = {
    "code": "mintkey:not_found",
    "title": "Service not found",
}

_NOT_OWNER_BODY: dict[str, Any] = {
    "code": "mintkey:not_owner",
    "title": "Not the owner of this service",
}


def parse_service_ref(service_ref: str) -> tuple[Literal["id", "slug"], str]:
    """Split a service reference into an id or a slug.

    A value that starts with ``svc_`` is an id: it is decoded to the dashed
    UUID stored in the database. A value that does not decode answers the 404
    of the agent error table. Any other value is a slug.
    """
    if service_ref.startswith("svc_"):
        try:
            decoded = wire_to_db_uuid(service_ref, "svc")
            return ("id", str(UUID(decoded)))
        except ValueError:
            raise AgentApiError(404, dict(_NOT_FOUND_BODY)) from None
    return ("slug", service_ref)


async def require_owned_service(
    session: AsyncSession,
    principal: AgentPrincipal,
    service_ref: str,
    *,
    for_update: bool = False,
) -> Any:
    """Return the caller's service, or raise the agent error for the cause.

    The lookup is pinned to the principal's tenant; a service of another
    tenant is not found. A service of another agent (or of none) is refused
    with 403. The row is locked only when ``for_update`` is true.
    """
    kind, value = parse_service_ref(service_ref)

    statement = (
        "SELECT s.id, s.tenant_id, s.name, s.slug, s.display_name, s.description,"
        " s.base_url, s.auth_scheme, s.openapi_url, s.status, s.created_at, s.updated_at,"
        " s.owner_agent_id, s.created_by_agent_id,"
        " EXISTS ("
        "   SELECT 1 FROM credentials c"
        "   WHERE c.service_id = s.id AND c.tenant_id = s.tenant_id"
        "     AND c.status = 'active'"
        " ) AS credential_set"
        " FROM services s WHERE s.tenant_id = :tenant_id"
    )
    params: dict[str, Any] = {"tenant_id": str(principal.tenant_id)}
    if kind == "id":
        statement += " AND s.id = :service_id"
        params["service_id"] = value
    else:
        statement += " AND s.slug = :slug"
        params["slug"] = value
    if for_update:
        statement += " FOR UPDATE"

    result = await session.execute(text(statement), params)
    row = result.fetchone()
    if row is None:
        raise AgentApiError(404, dict(_NOT_FOUND_BODY))

    owner = getattr(row, "owner_agent_id", None)
    if owner is None or str(owner) != str(principal.agent_id):
        raise AgentApiError(403, dict(_NOT_OWNER_BODY))
    return row


def service_view(row: Any) -> dict[str, Any]:
    """Map a service row to the twelve-key answer of the agent routes."""
    created_at = getattr(row, "created_at", None)
    updated_at = getattr(row, "updated_at", None)
    return {
        "id": db_uuid_to_wire(row.id, "svc"),
        "name": row.name,
        "slug": row.slug,
        "display_name": row.display_name,
        "description": row.description,
        "base_url": row.base_url,
        "auth_scheme": row.auth_scheme,
        "openapi_url": row.openapi_url,
        "status": row.status,
        "credential_set": bool(getattr(row, "credential_set", False)),
        "created_at": created_at.isoformat() if created_at else None,
        "updated_at": updated_at.isoformat() if updated_at else None,
    }


async def parse_agent_body[M: BaseModel](request: Request, model: type[M]) -> M:
    raise NotImplementedError
