"""
MCP discovery tools.

GET /v1/tools/list_services        — services the agent has permission to call.
GET /v1/tools/describe_service/{service_id} — full service metadata.
GET /v1/tools/get_openapi/{service_id}      — OpenAPI URL or null.

All queries run under tenant context (RLS enforces isolation).
Source: Req 6 AC3, AC4; ADR-0008.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session

router = APIRouter(prefix="/v1/tools")


async def get_agent_context(request: Request):
    """
    Dependency: extract validated agent context from request state.
    Set in middleware by validate_agent_key (T-1.5.1).
    Returns None when no agent context is present; endpoints return 401.
    """
    return getattr(request.state, "agent_context", None)


@router.get("/list_services")
async def list_services(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Return services the requesting agent has at least one permission grant for.
    RLS enforced via set_tenant_context.
    Source: Req 6 AC3; ADR-0008.
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    await set_tenant_context(session, agent_ctx["tenant_id"])

    result = await session.execute(
        text(
            "SELECT DISTINCT s.id, s.name, s.slug, s.base_url, s.auth_scheme"
            " FROM services s"
            " JOIN permission_grants pg ON pg.service_id = s.id"
            " WHERE pg.agent_id = :agent_id"
        ),
        {"agent_id": agent_ctx["agent_id"]},
    )
    rows = result.fetchall()
    services = [
        {
            "id": str(r.id),
            "name": r.name,
            "slug": r.slug,
            "base_url": r.base_url,
            "auth_scheme": r.auth_scheme,
        }
        for r in rows
    ]
    return JSONResponse({"services": services})


@router.get("/describe_service/{service_id}")
async def describe_service(
    service_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Return full metadata for a service.
    Source: Req 6 AC4; ADR-0008.
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    await set_tenant_context(session, agent_ctx["tenant_id"])

    result = await session.execute(
        text("SELECT * FROM services WHERE id = :sid"),
        {"sid": service_id},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(status_code=404, content={"code": "mintkey:not_found"})

    return JSONResponse(
        {
            "service": {
                "id": str(row.id),
                "name": row.name,
                "slug": row.slug,
                "base_url": row.base_url,
                "auth_scheme": row.auth_scheme,
            }
        }
    )


@router.get("/get_openapi/{service_id}")
async def get_openapi(
    service_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Return the OpenAPI URL for a service, or null if not set.
    Source: Req 6 AC4; ADR-0008.
    """
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    await set_tenant_context(session, agent_ctx["tenant_id"])

    result = await session.execute(
        text("SELECT openapi_url FROM services WHERE id = :sid"),
        {"sid": service_id},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(status_code=404, content={"code": "mintkey:not_found"})

    openapi_url = getattr(row, "openapi_url", None)
    return JSONResponse({"openapi_url": openapi_url})
