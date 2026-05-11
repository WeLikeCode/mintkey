"""
MCP request_token tool.

POST /v1/tools/request_token

Looks up the permission_grant for (agent_id, service_id, action), evaluates
rate_limit and time_window constraints, and — if permitted — issues a stub JWT
(full broker call deferred to T-1.6.x).

Constraint split:
  - MCP Server evaluates: rate_limit, time_window.
  - Proxy plugin evaluates: request_path_prefix, source_ip_allowlist.

All denials emit a token.denied audit event (ADR-0014.7).

Source: Req 6 AC5, AC10; ADR-0016.4; ADR-0014.7; ADR-0008.
"""
from __future__ import annotations

import secrets
import time
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.policy.constraints import RateLimiter, evaluate_rate_limit, evaluate_time_window
from mcp_server.tools.discovery import get_agent_context

router = APIRouter(prefix="/v1/tools")

# Module-level rate limiter — persists across requests within the same process.
_rate_limiter = RateLimiter()


class TokenRequest(BaseModel):
    service_id: str
    action: str


@router.post("/request_token")
async def request_token(
    request: Request,
    body: TokenRequest,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Issue a short-lived token for an agent to call a service.

    Steps:
      1. Auth check (agent context present).
      2. Set tenant context (RLS — ADR-0008).
      3. Look up permission_grant.
      4. Evaluate rate_limit constraint.
      5. Evaluate time_window constraint.
      6. Stub: generate token (broker call in T-1.6.x).

    All denials emit token.denied audit events (ADR-0014.7).
    """
    if agent_ctx is None:
        return JSONResponse(
            status_code=401, content={"code": "mintkey:auth_required"}
        )

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    await set_tenant_context(session, tenant_id)

    # 1. Look up permission grant
    result = await session.execute(
        text(
            "SELECT agent_id, service_id, action, constraints"
            " FROM permission_grants"
            " WHERE agent_id = :aid AND service_id = :sid AND action = :action"
            " LIMIT 1"
        ),
        {"aid": agent_id, "sid": body.service_id, "action": body.action},
    )
    grant = result.fetchone()

    if grant is None:
        await _emit_denial(
            session, tenant_id, agent_id, body.service_id, body.action,
            "permission_not_found",
        )
        return JSONResponse(
            status_code=403,
            content={
                "code": "mintkey:not_authorized",
                "reason_code": "permission_not_found",
            },
        )

    constraints: dict = grant.constraints or {}

    # 2. Evaluate rate_limit constraint
    if rate_limit := constraints.get("rate_limit"):
        key = f"{agent_id}:{body.service_id}:{body.action}"
        allowed, reason = evaluate_rate_limit(_rate_limiter, key, rate_limit)
        if not allowed:
            await _emit_denial(
                session, tenant_id, agent_id, body.service_id, body.action, reason
            )
            return JSONResponse(
                status_code=403,
                content={"code": "mintkey:not_authorized", "reason_code": reason},
            )

    # 3. Evaluate time_window constraint
    if time_window := constraints.get("time_window"):
        allowed, reason = evaluate_time_window(time_window)
        if not allowed:
            await _emit_denial(
                session, tenant_id, agent_id, body.service_id, body.action, reason
            )
            return JSONResponse(
                status_code=403,
                content={"code": "mintkey:not_authorized", "reason_code": reason},
            )

    # 4. Stub token (full broker call in T-1.6.x)
    stub_token = secrets.token_urlsafe(32)
    expires_at = int(time.time()) + 300  # 5-minute stub TTL

    return JSONResponse(
        {"token": stub_token, "expires_at": expires_at, "service_id": body.service_id}
    )


async def _emit_denial(
    session: AsyncSession,
    tenant_id: str,
    agent_id: str,
    service_id: str,
    action: str,
    reason_code: str,
) -> None:
    """Emit token.denied audit event for any denial path. ADR-0014.7."""
    from uuid import UUID
    await audit_emit(
        session=session,
        tenant_id=UUID(tenant_id),
        event_type="token.denied",
        actor_id=None,
        actor_type="agent",
        target_id=None,
        target_type="service",
        payload={
            "agent_id": agent_id,
            "service_id": service_id,
            "action": action,
            "reason_code": reason_code,
        },
    )
