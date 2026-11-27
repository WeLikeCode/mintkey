"""
Agent principal: turn a Bearer agent key into a tenant, agent and role.

A request to a ``/v1/agent/`` route carries only its own ``Authorization:
Bearer mk_agent_...`` key. The dependency checks it in a dedicated session
(so the platform view it turns on never leaks into the route's transaction),
commits the session and closes it before the route runs.

Source: openspec/changes/agent-principal-and-egress (task 3.1; spec
agent-principal, requirement "An agent key yields a principal"; design D1, D2, D7).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import Depends, Request
from fastapi.responses import JSONResponse

from admin_api.api import internal
from admin_api.auth import agent_key_guard
from admin_api.db.session import AsyncSessionLocal
from admin_api.middleware.tenant import set_tenant_context
from admin_api.utils.wire_ids import db_uuid_to_wire
from mintkey_models.audit import audit_emit
from mintkey_models.roles import normalize_role

logger = logging.getLogger(__name__)

_AUTH_REQUIRED_BODY: dict[str, Any] = {
    "code": "mintkey:auth_required",
    "title": "Agent key required",
}

_VERIFY_UNAVAILABLE_BODY: dict[str, Any] = {
    "code": "mintkey:verify_unavailable",
    "title": "Key check unavailable",
}

_AUTH_UNAVAILABLE_BODY: dict[str, Any] = {
    "code": "mintkey:auth_unavailable",
    "title": "Key check unavailable",
}


@dataclass(frozen=True)
class AgentPrincipal:
    """The identity a valid agent key yields for one request."""

    tenant_id: UUID
    agent_id: UUID
    role: str


class AgentApiError(Exception):
    """Every error of a ``/v1/agent`` route; the body is the JSON answer."""

    status_code: int
    body: dict[str, Any]
    headers: dict[str, str] | None

    def __init__(
        self,
        status_code: int,
        body: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(body.get("title", body.get("code", "agent api error")))
        self.status_code = status_code
        self.body = body
        self.headers = headers


async def agent_api_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """Answer an ``AgentApiError`` with its status, JSON body and headers."""
    if not isinstance(exc, AgentApiError):
        raise exc
    return JSONResponse(
        status_code=exc.status_code,
        content=exc.body,
        headers=exc.headers,
    )


def agent_error_body(body: dict[str, Any]) -> dict[str, Any]:
    """Re-key a ``validate-agent-key`` body in the agent error convention.

    The value of ``mintkey:code`` moves to ``code`` (with a ``mintkey:``
    prefix when it has none); every other key stays. A body without a
    ``title`` gets ``Key check unavailable``.
    """
    result = dict(body)
    code = result.pop("mintkey:code", None)
    if code is not None:
        text = str(code)
        if not text.startswith("mintkey:"):
            text = f"mintkey:{text}"
        result["code"] = text
    if "title" not in result:
        result["title"] = "Key check unavailable"
    return result


def _agent_key_from_request(request: Request) -> str | None:
    """Return the Bearer agent key, or None for anything else.

    Only ``Authorization: Bearer mk_agent_...`` is accepted: cookies,
    ``X-API-Key`` and other schemes never open an agent route (design D2).
    """
    header = request.headers.get("authorization")
    if not header:
        return None
    scheme, _, credentials = header.partition(" ")
    if scheme.lower() != "bearer":
        return None
    key = credentials.strip()
    if not key.startswith("mk_agent_"):
        return None
    return key


async def require_agent_key_shape(request: Request) -> None:
    """Refuse a bearer that is not the exact shape of a real agent key.

    The check runs before ``require_agent_principal`` on every ``/v1/agent``
    route, so a wrong-shaped bearer never opens a key-check session or reaches
    an Argon2id verify. A request with no bearer (or one that does not start
    with ``mk_agent_``) is left to ``require_agent_principal``, which answers
    the same ``401 mintkey:auth_required``.
    """
    api_key = _agent_key_from_request(request)
    if api_key is not None and not agent_key_guard.agent_key_shape_is_valid(api_key):
        raise AgentApiError(401, dict(_AUTH_REQUIRED_BODY))


def _json_body(response: JSONResponse) -> dict[str, Any]:
    """Return the JSON object of a response body, or an empty object."""
    parsed: Any = json.loads(bytes(response.body))
    if isinstance(parsed, dict):
        return parsed
    return {}


async def require_agent_principal(request: Request) -> AgentPrincipal:
    """Yield the principal of a valid agent key, or raise ``AgentApiError``.

    The key check runs in a dedicated session from ``AsyncSessionLocal``,
    which is committed (so an expiry audit event is stored) and closed before
    the dependency returns — and before the route's own session opens. The
    platform view the check turns on therefore never reaches a route's
    transaction.
    """
    api_key = _agent_key_from_request(request)
    if api_key is None:
        raise AgentApiError(401, dict(_AUTH_REQUIRED_BODY))

    capacity = agent_key_guard.agent_verify_capacity()
    if capacity.locked():
        # The agent routes' own capacity is full: answer at once rather than
        # queue this check behind it (and never touch the internal one).
        raise AgentApiError(503, dict(_AUTH_UNAVAILABLE_BODY))

    row: Any | None = None
    try:
        with internal.verify_capacity_scope(capacity):
            async with AsyncSessionLocal() as session:
                row, response = await internal.check_agent_key(session, api_key)
                await session.commit()
                if response is not None:
                    raise AgentApiError(
                        response.status_code,
                        agent_error_body(_json_body(response)),
                    )
    except AgentApiError:
        raise
    except Exception as exc:
        logger.warning("agent key check unavailable (%s)", type(exc).__name__)
        raise AgentApiError(503, dict(_VERIFY_UNAVAILABLE_BODY)) from exc

    if row is None:
        # Defensive: check_agent_key returns either a row or a response.
        raise AgentApiError(503, dict(_VERIFY_UNAVAILABLE_BODY))

    return AgentPrincipal(
        tenant_id=UUID(str(row.tenant_id)),
        agent_id=UUID(str(row.id)),
        role=normalize_role(getattr(row, "role", None)),
    )


async def require_publisher_principal(
    request: Request,
    principal: AgentPrincipal = Depends(require_agent_principal),
) -> AgentPrincipal:
    """Return the principal only when it may publish; refuse and record otherwise.

    A role other than ``publisher`` is refused with a 403 ``role_forbidden``
    answer after the refusal is recorded. Recording uses its own session and
    never depends on the route's transaction (design D3).
    """
    if principal.role == "publisher":
        return principal

    operation = f"{request.method} {request.url.path}"[:256]
    await record_denied_operation(principal, operation)
    role = normalize_role(principal.role)
    raise AgentApiError(
        403,
        {
            "code": "mintkey:role_forbidden",
            "title": "Role not allowed",
            "role": role,
            "required_role": "publisher",
            "hint": "This operation requires the publisher role.",
        },
    )


async def record_denied_operation(
    principal: AgentPrincipal, operation: str
) -> None:
    """Write one ``agent.operation.denied`` event, or log and return.

    The event is written in a session of its own, bound to the principal's
    tenant context (never the platform view), so it survives the 403 raised by
    the caller. A failure is logged and swallowed: a refusal never depends on
    its record (design D3).
    """
    role = normalize_role(principal.role)
    payload = {
        "agent_id": db_uuid_to_wire(principal.agent_id, "agent"),
        "role": role,
        "operation": operation[:256],
    }
    try:
        async with AsyncSessionLocal() as session:
            await set_tenant_context(session, principal.tenant_id)
            await audit_emit(
                session=session,
                tenant_id=principal.tenant_id,
                event_type="agent.operation.denied",
                actor_id=principal.agent_id,
                actor_type="agent",
                target_id=principal.agent_id,
                target_type="agent",
                payload=payload,
            )
            await session.commit()
    except Exception as exc:
        logger.warning(
            "could not record denied agent operation (%s)",
            type(exc).__name__,
        )
