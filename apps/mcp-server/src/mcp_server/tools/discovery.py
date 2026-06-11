"""
MCP discovery tools.

GET /v1/tools/list_services        — services the agent has permission to call.
GET /v1/tools/discover             — alias for list_services with how_to_call hints.
GET /v1/tools/describe_service/{service_id} — full service metadata.
GET /v1/tools/get_openapi/{service_id}      — OpenAPI URL or inline document.
GET /v1/tools/instructions         — LLM-ready usage guide (no auth required).

All queries run under tenant context (RLS enforces isolation).
IDs emitted in responses use the canonical svc_ wire form (ADR-0017.11; OPS-CC).
Incoming service_id path/body parameters accept BOTH wire form and raw UUID
for backward-compatibility with agents built before OPS-CC.
Source: Req 6 AC3, AC4; ADR-0008; ADR-0017.11; OPS-CC.
"""
from __future__ import annotations

from typing import Optional

import httpx
from httpx import RequestError as _HttpxRequestError, TimeoutException as _HttpxTimeoutException, TooManyRedirects as _HttpxTooManyRedirects
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.auth_schemes import INJECTION_HINTS
from mcp_server.config.public_urls import resolve_proxy_public_url, resolve_ssh_proxy_public_host
from mcp_server.db.session import get_db_session
from mcp_server.utils.wire_ids import ServiceNotFound, db_uuid_to_wire, resolve_service_id

# OpenAPI fetch limits (task 3.4)
_OPENAPI_MAX_BYTES = 1024 * 1024  # 1 MiB
_OPENAPI_TIMEOUT_S = 10.0

# Auth schemes that use SSH transport (ssh-proxy) rather than Kong HTTP proxy.
_SSH_AUTH_SCHEMES = {"ssh_private_key", "ssh_password", "ssh_ca"}


def _connect_type(auth_scheme: str) -> str:
    """Return 'ssh' for SSH auth schemes, 'http' for everything else."""
    return "ssh" if auth_scheme in _SSH_AUTH_SCHEMES else "http"


def _ssh_agent_connection_guide() -> dict:
    """
    Return the agent_connection_guide block for SSH-scheme services.
    The bastion host/port come from the env-driven resolver so the returned
    text matches the actual external address (not a hardcoded IP).
    """
    ext_host, ext_port = resolve_ssh_proxy_public_host()
    return {
        "summary": (
            "This service is accessed via the Mintkey SSH bastion, not the HTTP proxy."
        ),
        "steps": [
            "1. Call request_token({service_id, action: 'call'}) to get a JWT.",
            f"2. SSH to the bastion: ssh -p {ext_port} <agent_id>@{ext_host}",
            "3. Use the JWT (from step 1) as the SSH PASSWORD when prompted.",
            "4. The bastion validates the JWT, fetches the stored credential from the vault, "
            "and routes you to the real target.",
        ],
        "example_command_template": (
            f'sshpass -p "$JWT" ssh -p {ext_port} '
            "-o PreferredAuthentications=password "
            f"-o PubkeyAuthentication=no <agent_id>@{ext_host} '<your-command>'"
        ),
        "do_not": [
            "Do not route through Kong (HTTP-only).",
            "Do not store the JWT — it expires in ~10 minutes.",
            "Do not attempt agent forwarding (-A), X11 (-X), or local port forwarding (-L) "
            "— the bastion rejects them.",
        ],
        "lifetime_seconds": 600,
    }

def _make_auth_scheme_details(auth_scheme: str) -> dict:
    """
    Build auth_scheme_details for describe_service from the INJECTION_HINTS table.

    Per-credential header_name/query_param overrides live in vault.credentials
    (vault schema, ADR-0021) which is not reachable from the MCP-server's DB session
    without a separate vault-adapter gRPC call. We use table defaults here and note
    that the proxy may use a custom name configured by the operator at credential
    registration.
    """
    hint = INJECTION_HINTS.get(auth_scheme)
    if hint is None:
        return {
            "injection_point": "unknown",
            "header_name": None,
            "query_param": None,
            "format": "unknown scheme",
        }
    location = hint["location"]
    status = hint["status"]

    if status == "not_implemented":
        return {
            "injection_point": location,
            "header_name": None,
            "query_param": None,
            "format": "not_implemented — proxy returns an error for this scheme",
        }
    if status == "handled_by_other_proxy":
        return {
            "injection_point": location,
            "header_name": None,
            "query_param": None,
            "format": f"handled by {hint['handled_by']} — not the HTTP proxy",
        }

    # location == "header" schemes
    if auth_scheme == "api_key_header":
        return {
            "injection_point": "header",
            "header_name": "X-API-Key",  # default; operator may override
            "query_param": None,
            "format": "<raw_key>",
        }
    if auth_scheme == "api_key_query":
        return {
            "injection_point": "query",
            "header_name": None,
            "query_param": "api_key",  # default; operator may override
            "format": "<raw_key>",
        }
    if auth_scheme == "basic_auth":
        return {
            "injection_point": "header",
            "header_name": "Authorization",
            "query_param": None,
            "format": "Basic base64(user:pass)",
        }
    # All remaining http-proxy schemes inject a Bearer token
    return {
        "injection_point": "header",
        "header_name": "Authorization",
        "query_param": None,
        "format": "Bearer <token>",
    }


def _make_your_constraints(constraints_raw) -> dict:
    """
    Extract the calling agent's permission-grant constraints into the contracted shape.
    constraints_raw may be a dict (asyncpg returns JSONB as dict), a JSON string, or None.
    Each field is null when the operator has not set a limit.
    """
    if constraints_raw is None:
        c: dict = {}
    elif isinstance(constraints_raw, dict):
        c = constraints_raw
    else:
        import json as _json
        try:
            c = _json.loads(constraints_raw)
        except Exception:
            c = {}
    return {
        "rate_limit": c.get("rate_limit"),
        "time_window": c.get("time_window"),
        "request_path_prefix": c.get("request_path_prefix"),
        "source_ip_allowlist": c.get("source_ip_allowlist"),
    }


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

## Vanilla MCP clients

Standard MCP-over-HTTP (JSON-RPC 2.0) is available at `POST /mcp` (and `/`, `/v1/mcp`). Send the JSON-RPC envelope `{"jsonrpc":"2.0","id":1,"method":"initialize",...}` to start. See `GET /` for the full endpoint index.
"""


async def get_agent_context(request: Request):
    """
    Dependency: extract validated agent context from request state.
    Set in middleware by validate_agent_key (T-1.5.1).
    Returns None when no agent context is present; endpoints return 401.
    """
    return getattr(request.state, "agent_context", None)


def _make_email_how_to_call(email_service_id: str) -> dict:
    """Build the how_to_call usage hint for an email_service entry."""
    return {
        "step1_request_token": (
            f'POST /v1/tools/request_token {{"service_id": "{email_service_id}", "action": "call"}}'
        ),
        "step2_list_mailboxes": (
            f"GET /v1/tools/email_list_mailboxes?email_service_id={email_service_id}"
        ),
        "step3_send_email": (
            "POST /v1/tools/email_send — body: {email_service_id, to, subject, body}"
        ),
        "notes": (
            "For email services, use the email_* MCP tools directly — they handle "
            "broker token exchange internally. "
            "Alternatively, call request_token to get a JWT, then call email-proxy "
            "endpoints directly with ?service_id=<id>."
        ),
    }


def _make_how_to_call(service_id: str, base_url: str, auth_scheme: str = "") -> dict:
    """Build the how_to_call usage hint for a service entry."""
    proxy_url = resolve_proxy_public_url()
    result: dict = {
        "action": "call",
        "step1_request_token": (
            f'POST /v1/tools/request_token {{"service_id": "{service_id}", "action": "call"}}'
        ),
        "step2_proxy_call": (
            "Send request to proxy with Authorization: Bearer <token>"
        ),
        "proxy_url_pattern": f"{proxy_url}/v1/call/{service_id}/<path_on_target_api>",
        "notes": (
            'The action defaults to "call" for all services. '
            "Use the action string your operator granted you — if unsure, try \"call\". "
            "The proxy strips your Bearer token and injects the real credential before forwarding. "
            "No X-Mintkey-Target header is needed — the target URL is stored with the credential. "
            "Call describe_service for full auth details and your permission constraints."
        ),
    }
    if auth_scheme and auth_scheme in INJECTION_HINTS:
        result["injection_hint"] = INJECTION_HINTS[auth_scheme]
    return result


@router.get("/list_services")
async def list_services(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Return services the requesting agent has at least one permission grant for.
    Includes both HTTP/SSH services (permission_grants) and email services
    (email_permission_grants) — feat/agent-email-e2e.
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
            "connect_type": _connect_type(r.auth_scheme),
            "kind": "service",
        }
        for r in rows
    ]

    # Email services — union from email_permission_grants + email_services.
    email_result = await session.execute(
        text(
            "SELECT DISTINCT es.id, es.name, es.imap_host, es.smtp_host,"
            " es.auth_scheme, es.allowed_recipient_domains"
            " FROM email_services es"
            " JOIN email_permission_grants epg ON epg.email_service_id = es.id"
            " WHERE epg.agent_id = :agent_id AND es.deleted_at IS NULL"
        ),
        {"agent_id": agent_ctx["agent_id"]},
    )
    email_rows = email_result.fetchall()
    email_services = [
        {
            "id": db_uuid_to_wire(r.id, "svc"),
            "name": r.name,
            "imap_host": r.imap_host,
            "smtp_host": r.smtp_host,
            "auth_scheme": r.auth_scheme,
            "allowed_recipient_domains": r.allowed_recipient_domains,
            "connect_type": "email",
            "kind": "email_service",
        }
        for r in email_rows
    ]

    all_services = services + email_services
    payload: dict = {"services": all_services}
    if not all_services:
        payload["hint"] = (
            "You have no permission grants on any service. "
            "Ask your operator to add a Permission Grant in the admin UI: "
            "Permissions > New > pick this agent + a service + action. "
            "Once you have services, call discover for how_to_call hints or "
            "describe_service/{service_id} for full auth details and constraints."
        )
    else:
        payload["hint"] = (
            "Call discover for per-service how_to_call hints, or "
            "describe_service/{service_id} for full auth details, constraints, and OpenAPI availability."
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
    Includes both HTTP/SSH services and email_services — feat/agent-email-e2e.
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
            "connect_type": _connect_type(r.auth_scheme),
            "kind": "service",
            "how_to_call": _make_how_to_call(
                db_uuid_to_wire(r.id, "svc"), r.base_url, r.auth_scheme
            ),
        }
        for r in rows
    ]

    # Email services — union from email_permission_grants + email_services.
    email_result = await session.execute(
        text(
            "SELECT DISTINCT es.id, es.name, es.imap_host, es.smtp_host,"
            " es.auth_scheme, es.allowed_recipient_domains"
            " FROM email_services es"
            " JOIN email_permission_grants epg ON epg.email_service_id = es.id"
            " WHERE epg.agent_id = :agent_id AND es.deleted_at IS NULL"
        ),
        {"agent_id": agent_ctx["agent_id"]},
    )
    email_rows = email_result.fetchall()
    email_services_list = [
        {
            "id": db_uuid_to_wire(r.id, "svc"),
            "name": r.name,
            "imap_host": r.imap_host,
            "smtp_host": r.smtp_host,
            "auth_scheme": r.auth_scheme,
            "allowed_recipient_domains": r.allowed_recipient_domains,
            "connect_type": "email",
            "kind": "email_service",
            "how_to_call": _make_email_how_to_call(db_uuid_to_wire(r.id, "svc")),
        }
        for r in email_rows
    ]

    all_services = services + email_services_list
    payload: dict = {"services": all_services}
    if not all_services:
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

    # Fetch this agent's constraints for the service (task 3.2).
    # Bound params use distinct names (agent_id_ds, service_id_ds) to avoid
    # collision with existing fake sessions in tests.
    constraints_result = await session.execute(
        text(
            "SELECT constraints FROM permission_grants"
            " WHERE agent_id = :agent_id_ds AND service_id = :service_id_ds"
            " ORDER BY (action = 'call') DESC, created_at DESC"
            " LIMIT 1"
        ),
        {
            "agent_id_ds": agent_ctx["agent_id"],
            "service_id_ds": db_service_id,
        },
    )
    constraints_row = constraints_result.fetchone()
    constraints_raw = getattr(constraints_row, "constraints", None) if constraints_row else None

    ct = _connect_type(row.auth_scheme)
    proxy_url = resolve_proxy_public_url()
    wire_id = db_uuid_to_wire(row.id, "svc")
    openapi_url = getattr(row, "openapi_url", None)

    service_payload: dict = {
        "id": wire_id,
        "name": row.name,
        "slug": row.slug,
        "base_url": row.base_url,
        "auth_scheme": row.auth_scheme,
        "description": row.description,  # may be null
        "openapi_url": openapi_url,       # may be null
        "connect_type": ct,
        "explicit_proxy_url": f"{proxy_url}/v1/call/{wire_id}",
        "auth_scheme_details": _make_auth_scheme_details(row.auth_scheme),
        "your_constraints": _make_your_constraints(constraints_raw),
        "openapi": {
            "status": "available" if openapi_url else "not_registered",
            "url": openapi_url,
        },
    }
    if ct == "ssh":
        service_payload["agent_connection_guide"] = _ssh_agent_connection_guide()
    return JSONResponse({"service": service_payload})


@router.get("/get_openapi/{service_id}")
async def get_openapi(
    service_id: str,
    request: Request,
    inline: bool = Query(default=False),
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Return the service's OpenAPI document — URL or inline.

    Default (inline=false): returns {kind: url, openapi_url, etag}.
    inline=true: fetches server-side with If-None-Match from services.openapi_etag,
      1 MiB cap, 10 s timeout, no off-host redirects; updates etag on 200.
    No URL registered: {kind: not_registered}.
    Fetch failure: {kind: fetch_failed, openapi_url, reason} — tool never raises.
    Response content is passed through opaque; never logged (SSRF/plaintext gates).

    Source: Req 6 AC4; ADR-0008; design.md D4; spec openapi-exposure.
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
        text("SELECT openapi_url, openapi_etag FROM services WHERE id = :sid"),
        {"sid": db_service_id},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(status_code=404, content={"code": "mintkey:not_found"})

    openapi_url = getattr(row, "openapi_url", None)
    openapi_etag = getattr(row, "openapi_etag", None)

    if not openapi_url:
        return JSONResponse({
            "kind": "not_registered",
            "hint": (
                "The operator has not set an openapi_url for this service. "
                "Set it via PATCH /v1/tenants/{tenant_id}/services/{service_id} "
                "or the admin UI service registration form."
            ),
        })

    if not inline:
        return JSONResponse({
            "kind": "url",
            "openapi_url": openapi_url,
            "etag": openapi_etag,
        })

    # Inline mode: fetch server-side with etag-conditional request.
    fetch_headers: dict = {}
    if openapi_etag:
        fetch_headers["If-None-Match"] = openapi_etag

    try:
        async with httpx.AsyncClient(timeout=_OPENAPI_TIMEOUT_S) as client:
            resp = await client.get(
                openapi_url,
                headers=fetch_headers,
                follow_redirects=False,
            )
    except (_HttpxTooManyRedirects, _HttpxTimeoutException, _HttpxRequestError) as exc:
        return JSONResponse({
            "kind": "fetch_failed",
            "openapi_url": openapi_url,
            "reason": str(exc)[:200],
        })
    except Exception as exc:
        return JSONResponse({
            "kind": "fetch_failed",
            "openapi_url": openapi_url,
            "reason": f"unexpected error: {type(exc).__name__}",
        })

    if resp.status_code == 304:
        # Not Modified — cached version still valid; return url mode with stored etag.
        return JSONResponse({
            "kind": "url",
            "openapi_url": openapi_url,
            "etag": openapi_etag,
        })

    if resp.status_code != 200:
        return JSONResponse({
            "kind": "fetch_failed",
            "openapi_url": openapi_url,
            "reason": f"upstream returned HTTP {resp.status_code}",
        })

    # Size check: content-length header first, then actual body.
    content_length_header = resp.headers.get("content-length")
    if content_length_header:
        try:
            if int(content_length_header) > _OPENAPI_MAX_BYTES:
                return JSONResponse({
                    "kind": "fetch_failed",
                    "openapi_url": openapi_url,
                    "reason": f"document exceeds 1 MiB (content-length={content_length_header})",
                })
        except ValueError:
            pass

    body_bytes = resp.content
    if len(body_bytes) > _OPENAPI_MAX_BYTES:
        return JSONResponse({
            "kind": "fetch_failed",
            "openapi_url": openapi_url,
            "reason": f"document exceeds 1 MiB ({len(body_bytes)} bytes)",
        })

    # Persist updated etag (best-effort; do not fail the request if this fails).
    new_etag = resp.headers.get("etag") or openapi_etag
    if new_etag and new_etag != openapi_etag:
        try:
            await session.execute(
                text("UPDATE services SET openapi_etag = :etag WHERE id = :sid"),
                {"etag": new_etag, "sid": db_service_id},
            )
        except Exception:
            pass  # non-fatal; etag column update is best-effort caching only

    content_type_header = resp.headers.get("content-type", "")
    if "yaml" in content_type_header:
        ct_out = "application/yaml"
    else:
        ct_out = "application/json"

    return JSONResponse({
        "kind": "inline",
        "content_type": ct_out,
        "etag": new_etag,
        "document": resp.text,
    })
