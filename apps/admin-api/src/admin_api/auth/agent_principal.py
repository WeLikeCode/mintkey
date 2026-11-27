"""
Agent principal: turn a Bearer agent key into a tenant, agent and role.

Signature-only stubs for the red step; the behaviour is added in the green
step.

Source: openspec/changes/agent-principal-and-egress (task 3.1; spec
agent-principal, requirement "An agent key yields a principal").
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from admin_api.db.session import AsyncSessionLocal  # noqa: F401


@dataclass(frozen=True)
class AgentPrincipal:
    """The identity a valid agent key yields for one request."""

    tenant_id: UUID
    agent_id: UUID
    role: str


class AgentApiError(Exception):
    pass


async def agent_api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    raise NotImplementedError


def agent_error_body(body: dict[str, Any]) -> dict[str, Any]:
    raise NotImplementedError


async def require_agent_principal(request: Request) -> AgentPrincipal:
    raise NotImplementedError


async def require_publisher_principal(
    request: Request,
    principal: AgentPrincipal = Depends(require_agent_principal),
) -> AgentPrincipal:
    raise NotImplementedError


async def record_denied_operation(
    principal: AgentPrincipal, operation: str
) -> None:
    raise NotImplementedError
