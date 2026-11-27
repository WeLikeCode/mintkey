"""Owned-service lookup for the ``/v1/agent`` service routes.

Source: openspec/changes/agent-service-routes (task 1.1; spec
agent-service-routes, requirement "The owned service lookup is one function").
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.agent_principal import AgentPrincipal


def parse_service_ref(service_ref: str) -> tuple[Literal["id", "slug"], str]:
    raise NotImplementedError


async def require_owned_service(
    session: AsyncSession,
    principal: AgentPrincipal,
    service_ref: str,
    *,
    for_update: bool = False,
) -> Any:
    raise NotImplementedError


def service_view(row: Any) -> dict[str, Any]:
    raise NotImplementedError


async def parse_agent_body[M: BaseModel](request: Request, model: type[M]) -> M:
    raise NotImplementedError
