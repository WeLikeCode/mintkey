"""
MCP discovery tools.

GET /v1/tools/list_services        — services the agent has permission to call.
GET /v1/tools/discover             — alias for list_services with how_to_call hints.
GET /v1/tools/describe_service/{service_id} — full service metadata.
GET /v1/tools/get_openapi/{service_id}      — OpenAPI URL or null.
GET /v1/tools/instructions         — LLM-ready usage guide (no auth required).

All queries run under tenant context (RLS enforces isolation).
IDs emitted in responses use the canonical svc_ wire form (ADR-0017.11; OPS-CC).
Incoming service_id path/body parameters accept BOTH wire form and raw UUID
for backward-compatibility with agents built before OPS-CC.
Source: Req 6 AC3, AC4; ADR-0008; ADR-0017.11; OPS-CC.
"""
from __future__ import annotations

from typing import Optional

from mcp_server.config.public_urls import resolve_proxy_public_url

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.utils.wire_ids import ServiceNotFound, db_uuid_to_wire, resolve_service_id

router = APIRouter(prefix="/v1/tools")

_INSTRUCTIONS_MARKDOWN = """\
# Mintkey Proxy — Agent Usage Guide

You are an agent with access to backend services via the Mintkey credential proxy.
Your API key is secret — never log or share it.

## Step 1: Discover available services
GET /v1/tools/discover
Header: X-API-Key: <your_api_key>

Returns a list of services you are permitted to call. Note the `id` and `base_url` for the service you want to use.

## Step 2: Request a temporary token
POST /v1/tools/request_token
Header: X-API-Key: <your_api_key>
Body: {"service_id": "<id_from_discover>", "action": "call"}

IMPORTANT: the action string must match what was granted to your agent. Use "call" unless your operator
explicitly told you a different action (e.g. "send"). When in doubt, use "call" — it is the default action
granted to most agents. If you get permission_not_found, try "call" before assuming access is missing.

Returns: {"token": "<jwt>", "expires_at": <unix_timestamp>, "service_id": "..."}
The token is valid for 10 minutes. Never log it.

## Step 3: Call the service through the proxy
METHOD <proxy_url>/v1/call/<service_id>/<path>
Header: Authorization: Bearer <token_from_step_2>

The `proxy_url` value is announced in the bootstrap response (`GET /v1/tools/bootstrap`)
and is also embedded in each service's `how_to_call.proxy_url_pattern` (returned by
`discover` and `list_services`). Use the value the server gives you — do not assume
localhost.

Rules:
- The path after /v1/call/<service_id>/ is forwarded verbatim to the target service.
- The proxy already knows the target URL from the registered service base_url — no extra header needed.
- The proxy strips your Authorization header and injects the real service credential automatically.
- You never see the actual API key/password — the proxy holds it encrypted.
- If you get 401 from the proxy, your token has expired — repeat from Step 2.
- If you get 403 from the proxy, your agent lacks permission for this service — contact the operator.

For complete usage examples, call the bootstrap tool (GET /v1/tools/bootstrap — no auth required) \
to retrieve the authoritative agent-bootstrap.md skill.
"""


async def get_agent_context(request: Request):
    """
    Dependency: extract validated agent context from request state.
    Set in middleware by validate_agent_key (T-1.5.1).
    Returns None when no agent context is present; endpoints return 401.
    """
    return getattr(request.state, "agent_context", None)


def _make_how_to_call(service_id: str, base_url: str) -> dict:
    """Build the how_to_call usage hint for a service entry."""
    proxy_url = resolve_proxy_public_url()
    return {
        "action": "call",
        "step1_request_token": (
            f'POST /v1/tools/request_token {{"service_id": "{service_id}", "action": "call"}}'
        ),
        "step2_proxy_call": (
            f"Send request to proxy with Authorization: Bearer <token>"
        ),
        "proxy_url_pattern": f"{proxy_url}/v1/call/{service_id}/<path_on_target_api>",
        "notes": (
            'The action defaults to "call" for all services. '
            "Use the action string your operator granted you — if unsure, try \"call\". "
            "The proxy strips your Bearer token and injects the real credential before forwarding. "
            "No X-Mintkey-Target header is needed — the target URL is stored with the credential."
        ),
    }


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
            "id": db_uuid_to_wire(r.id, "svc"),
            "name": r.name,
            "slug": r.slug,
            "base_url": r.base_url,
            "auth_scheme": r.auth_scheme,
        }
        for r in rows
    ]
    payload: dict = {"services": services}
    if not services:
        payload["hint"] = (
            "You have no permission grants on any service. "
            "Ask your operator to add a Permission Grant in the admin UI: "
            "Permissions > New > pick this agent + a service + action."
        )
    return JSONResponse(payload)


@router.get("/discover")
async def discover(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    List services with per-service how_to_call usage hints.
    Used by E2E smoke test (T-1.11.2) and LLM agents.
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
            "id": db_uuid_to_wire(r.id, "svc"),
            "name": r.name,
            "slug": r.slug,
            "base_url": r.base_url,
            "auth_scheme": r.auth_scheme,
            "how_to_call": _make_how_to_call(db_uuid_to_wire(r.id, "svc"), r.base_url),
        }
        for r in rows
    ]
    payload: dict = {"services": services}
    if not services:
        payload["hint"] = (
            "You have no permission grants on any service. "
            "Ask your operator to add a Permission Grant in the admin UI: "
            "Permissions > New > pick this agent + a service + action."
        )
    return JSONResponse(payload)


@router.get("/instructions")
async def instructions() -> JSONResponse:
    """
    Return a complete LLM system-prompt-ready usage guide for the Mintkey proxy.
    No authentication required — safe to inject into agent system prompts.
    """
    return JSONResponse({"format": "markdown", "content": _INSTRUCTIONS_MARKDOWN})


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

    tenant_id = agent_ctx["tenant_id"]
    await set_tenant_context(session, tenant_id)

    # Resolve service_id from any of three accepted forms:
    #   1. Raw UUID, 2. svc_ wire form, 3. slug — OPS-LL.
    # (ADR-0017.11; OPS-CC backward-compat).
    try:
        db_service_uuid = await resolve_service_id(service_id, tenant_id, session)
    except ServiceNotFound as exc:
        return JSONResponse(
            status_code=404,
            content={
                "code": "mintkey:not_found",
                "reason_code": "service_not_found",
                "service_id_input": exc.service_id_input,
                "hint": (
                    "Use the 'id' field from list_services (e.g., 'svc_…') "
                    "or the service slug ('github'). Slugs are case-sensitive."
                ),
            },
        )

    db_service_id = str(db_service_uuid)

    result = await session.execute(
        text("SELECT * FROM services WHERE id = :sid"),
        {"sid": db_service_id},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(status_code=404, content={"code": "mintkey:not_found"})

    return JSONResponse(
        {
            "service": {
                "id": db_uuid_to_wire(row.id, "svc"),
                "name": row.name,
                "slug": row.slug,
                "base_url": row.base_url,
                "auth_scheme": row.auth_scheme,
                "description": row.description,  # may be null
                "openapi_url": row.openapi_url,   # may be null
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

    tenant_id = agent_ctx["tenant_id"]
    await set_tenant_context(session, tenant_id)

    # Resolve service_id from any of three accepted forms:
    #   1. Raw UUID, 2. svc_ wire form, 3. slug — OPS-LL.
    # (ADR-0017.11; OPS-CC backward-compat).
    try:
        db_service_uuid = await resolve_service_id(service_id, tenant_id, session)
    except ServiceNotFound as exc:
        return JSONResponse(
            status_code=404,
            content={
                "code": "mintkey:not_found",
                "reason_code": "service_not_found",
                "service_id_input": exc.service_id_input,
                "hint": (
                    "Use the 'id' field from list_services (e.g., 'svc_…') "
                    "or the service slug ('github'). Slugs are case-sensitive."
                ),
            },
        )

    db_service_id = str(db_service_uuid)

    result = await session.execute(
        text("SELECT openapi_url FROM services WHERE id = :sid"),
        {"sid": db_service_id},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(status_code=404, content={"code": "mintkey:not_found"})

    openapi_url = getattr(row, "openapi_url", None)
    return JSONResponse({"openapi_url": openapi_url})
