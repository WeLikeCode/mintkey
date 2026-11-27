"""Agent service routes (``/v1/agent/services``).

Task 2.1 stubs: the route handlers that the red tests of
``tests/unit/admin_api/test_agent_services_create.py`` call. The green task
fills in the bodies, the request models and the router.

Source: openspec/changes/agent-service-routes/spec.md — A publisher creates a
service; A publisher lists its own services.
"""

from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.agent_principal import AgentPrincipal


async def create_agent_service(
    request: Request,
    principal: AgentPrincipal,
    session: AsyncSession,
) -> JSONResponse:
    raise NotImplementedError


async def list_agent_services(
    principal: AgentPrincipal,
    session: AsyncSession,
) -> JSONResponse:
    raise NotImplementedError
