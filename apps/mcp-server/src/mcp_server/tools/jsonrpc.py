"""
MCP-over-HTTP JSON-RPC dispatcher.

Registers POST routes at /, /mcp, and /v1/mcp that implement the MCP 2025-06-18
protocol over plain HTTP (no SSE).  GET routes on those paths are already handled
by landing.py (MCP-D-A) and are intentionally kept — clients that probe GET first
see a structured discovery doc, which is more helpful than a 405.

Supported methods
-----------------
  initialize              — unauthenticated; returns protocolVersion, capabilities,
                            serverInfo, instructions
  notifications/initialized — unauthenticated; returns HTTP 202 (no body)
  tools/list              — requires Bearer / X-API-Key; returns 6 Mintkey tools
  tools/call              — requires Bearer / X-API-Key; translates to the
                            existing /v1/tools/* REST handlers via an in-process
                            httpx loopback (httpx.AsyncClient(app=app, ...))

Error conventions
-----------------
  JSON-RPC protocol errors  → {"jsonrpc":"2.0","id":…,"error":{"code":…,"message":…}}
  Tool execution failures   → HTTP 200, {"result":{"content":[…],"isError":true}}
  Notifications (no id)     → HTTP 202, empty body

Source: MCP-DISCOVER-DESIGN Section 6 MCP-D-BE; MCP spec 2025-06-18 lifecycle,
        tools, transports; user decision D1 = Option B (full MCP).
"""
from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from mcp_server.auth.agent_key import validate_agent_key
from mcp_server.tools.bootstrap import (
    _RESOURCE_URI,
    _SKILL_MARKDOWN as _BOOTSTRAP_FULL_MD,
    _GUIDE_RESOURCES,
)

router = APIRouter()

# ---------------------------------------------------------------------------
# MCP protocol constants
# ---------------------------------------------------------------------------

_PROTOCOL_VERSION = "2025-06-18"

_INSTRUCTIONS = """\
You are connected to Mintkey, a credential broker for AI agents. Capabilities:

1. Brokered service calls — mintkey_discover lists services you may call
   (with per-auth-scheme injection hints); mintkey_describe_service returns
   full auth details, your constraints, and the exact proxy URL;
   mintkey_request_token exchanges a service_id for a short-lived JWT; then
   call the service via the proxy URL with the JWT as Bearer. The proxy
   injects the real credential — never send your own upstream auth header.
2. Agent secret storage — store your OWN credentials (DB passwords,
   service-account JSON, SSH keys) encrypted at rest and read them back:
   secret_put / secret_get / secret_list / secret_delete. Secrets are
   private to you unless an operator shares one with another agent.
3. Upstream API specs — mintkey_get_openapi returns a service's OpenAPI
   document (url or inline) when the operator registered one.
4. Email — email_* tools (send, list mailboxes/messages, attachments) for
   granted email services, via the REST endpoints listed at GET /v1/tools.

For the full onboarding skill (markdown), call mintkey_bootstrap.
Auth: send `Authorization: Bearer mk_agent_<your-key>` on every tools/* call.
"""

_SERVER_INFO = {
    "name": "mintkey-mcp-server",
    "title": "Mintkey Credential Broker",
    "version": "0.1.0-experimental",
}

_CAPABILITIES = {
    "tools": {"listChanged": False},
    "resources": {"listChanged": False, "subscribe": False},
    "experimental": {
        "mintkey.rest_endpoints": {
            "bootstrap": "/v1/tools/bootstrap",
            "discover": "/v1/tools/discover",
            "request_token": "/v1/tools/request_token",
        }
    },
}

# ---------------------------------------------------------------------------
# Tool descriptors (static; returned by tools/list)
# ---------------------------------------------------------------------------

TOOLS: list[dict] = [
    {
        "name": "mintkey_bootstrap",
        "description": (
            "Onboarding skill for the credential broker. By default returns a compact "
            "index (section table + resource URI). Pass section to fetch one block: "
            "index|quick_start|use_cases|anti_patterns|auth|discover|proxy_call|email|secrets"
            "|rest-api|ssh|secrets-guide|email-guide|quick-reference|full. "
            "Use 'full' for the entire skill, or read the MCP resource "
            "mintkey://skill/agent-bootstrap."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "section": {
                    "type": "string",
                    "enum": [
                        "index", "quick_start", "use_cases", "anti_patterns",
                        "auth", "discover", "proxy_call", "email", "secrets",
                        "rest-api", "ssh", "secrets-guide", "email-guide",
                        "quick-reference", "full",
                    ],
                    "default": "index",
                    "description": "Which bootstrap section to return. Default 'index'.",
                }
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "mintkey_list_services",
        "description": (
            "List services the calling agent has permission to call "
            "(with metadata + how_to_call hints)."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "mintkey_discover",
        "description": (
            "Same as list_services but with detailed how_to_call hints. "
            "Use this for first-time agent discovery."
        ),
        "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
    },
    {
        "name": "mintkey_describe_service",
        "description": "Full metadata for one service.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_id": {
                    "type": "string",
                    "description": "Service ID in wire form (svc_<crockford>) or UUID.",
                }
            },
            "required": ["service_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mintkey_get_openapi",
        "description": "Returns the OpenAPI spec URL for one service (or null if none).",
        "inputSchema": {
            "type": "object",
            "properties": {"service_id": {"type": "string"}},
            "required": ["service_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mintkey_request_token",
        "description": (
            "Exchange the agent's API key + a service_id for a short-lived brokered JWT "
            "(default 10 minute TTL). Use the JWT as Authorization: Bearer on the proxy URL."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "service_id": {"type": "string"},
                "action": {
                    "type": "string",
                    "description": (
                        "Permission action. Use 'call' unless the operator specified otherwise."
                    ),
                    "default": "call",
                },
            },
            "required": ["service_id"],
            "additionalProperties": False,
        },
    },
    # Agent secret tools (ADR-0025)
    {
        "name": "secret_put",
        "description": "Store (or overwrite) a named secret owned by the calling agent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Secret name (unique per agent)."},
                "value": {"type": "string", "description": "Plaintext secret value (UTF-8)."},
                "content_type": {
                    "type": "string",
                    "description": "Optional free-text content-type hint.",
                },
            },
            "required": ["name", "value"],
            "additionalProperties": False,
        },
    },
    {
        "name": "secret_get",
        "description": "Read the plaintext value of a secret you own or were granted read access to.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "secret_id": {
                    "type": "string",
                    "description": "sec_ wire form of the secret ID.",
                }
            },
            "required": ["secret_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "secret_list",
        "description": "List metadata for secrets you own or that are shared with you. Never returns values.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "after": {
                    "type": "string",
                    "description": "Pagination cursor — sec_ wire ID from previous page.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Page size (1–200, default 50).",
                    "default": 50,
                },
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "secret_delete",
        "description": "Delete a secret you own. Cascades share grants. Idempotent.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "secret_id": {
                    "type": "string",
                    "description": "sec_ wire form of the secret ID.",
                }
            },
            "required": ["secret_id"],
            "additionalProperties": False,
        },
    },
]

# ---------------------------------------------------------------------------
# MCP Resource descriptors + handlers (FR-7)
# ---------------------------------------------------------------------------

_RESOURCES: list[dict] = [
    {
        "uri": _RESOURCE_URI,
        "name": "agent-bootstrap",
        "title": "Mintkey Agent Bootstrap Skill",
        "description": "Full vendor-agnostic onboarding skill (markdown).",
        "mimeType": "text/markdown",
    },
    {
        "uri": "mintkey://guides/rest-api",
        "name": "guide-rest-api",
        "title": "Mintkey REST/HTTP Service Guide",
        "description": "discover -> token -> proxy call; never add upstream auth.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "mintkey://guides/ssh",
        "name": "guide-ssh",
        "title": "Mintkey SSH Service Guide",
        "description": "SSH bastion, JWT-as-password, ssh:// base_url.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "mintkey://guides/secrets",
        "name": "guide-secrets",
        "title": "Mintkey Agent Secrets Guide",
        "description": "secret_put/get/list/delete; agent-owned vs operator-managed.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "mintkey://guides/email",
        "name": "guide-email",
        "title": "Mintkey Email Service Guide",
        "description": "9 email_* tools -> IMAP/SMTP via email-proxy.",
        "mimeType": "text/markdown",
    },
    {
        "uri": "mintkey://quick-reference",
        "name": "quick-reference",
        "title": "Mintkey Quick Reference",
        "description": "One-page cheat sheet.",
        "mimeType": "text/markdown",
    },
]

# Map of URI → text for resources/read dispatch.
_READABLE: dict[str, str] = {_RESOURCE_URI: _BOOTSTRAP_FULL_MD, **_GUIDE_RESOURCES}


def _handle_resources_list(request_id: Any) -> JSONResponse:
    return _jsonrpc_result(request_id, {"resources": _RESOURCES})


def _handle_resources_read(request_id: Any, params: dict) -> JSONResponse:
    uri = params.get("uri", "")
    text = _READABLE.get(uri)
    if text is None:
        return _jsonrpc_error(
            request_id, -32602, f"Unknown resource URI: {uri!r}",
            data={"hint": "Call resources/list for available resources."},
        )
    return _jsonrpc_result(
        request_id,
        {"contents": [{"uri": uri, "mimeType": "text/markdown", "text": text}]},
    )


# ---------------------------------------------------------------------------
# JSON-RPC helpers
# ---------------------------------------------------------------------------


def _jsonrpc_error(request_id: Any, code: int, message: str, data: Any = None) -> JSONResponse:
    """Return a well-formed JSON-RPC error envelope with HTTP 200."""
    body: dict = {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {"code": code, "message": message},
    }
    if data is not None:
        body["error"]["data"] = data
    return JSONResponse(content=body, status_code=200)


def _jsonrpc_result(request_id: Any, result: Any) -> JSONResponse:
    """Return a well-formed JSON-RPC success envelope with HTTP 200."""
    return JSONResponse(
        content={"jsonrpc": "2.0", "id": request_id, "result": result},
        status_code=200,
    )


def _tool_result(content_blocks: list[dict], *, is_error: bool = False) -> dict:
    """Build a tools/call result envelope."""
    r: dict = {"content": content_blocks}
    if is_error:
        r["isError"] = True
    return r


def _text_block(text: str) -> dict:
    return {"type": "text", "text": text}


def _helpful_400() -> JSONResponse:
    """Return HTTP 400 for POST bodies that are not JSON-RPC envelopes."""
    return JSONResponse(
        status_code=400,
        content={
            "error": "not_jsonrpc",
            "hint": (
                "This endpoint expects a JSON-RPC 2.0 request. "
                "For REST tools, see GET /v1/tools/ or GET / for the endpoint index."
            ),
            "expected_envelope": {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {},
            },
        },
    )


# ---------------------------------------------------------------------------
# Auth helper — mirrors main.py agent_key_middleware
# ---------------------------------------------------------------------------


async def _require_agent(request: Request) -> tuple[dict | None, str | None]:
    """
    Extract and validate the agent key from the incoming request.

    Tries Authorization: Bearer mk_agent_<key> first, then X-API-Key: mk_agent_<key>.
    Returns (agent_ctx, agent_key) on success, (None, None) on failure.

    Mirrors the prefix logic in main.py:agent_key_middleware so both paths
    always agree on which header takes precedence and which prefix is required.
    """
    token: str | None = None
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        candidate = auth[len("Bearer "):]
        if candidate.startswith("mk_agent_"):
            token = candidate
    if token is None:
        x_api_key = request.headers.get("X-API-Key", "")
        if x_api_key.startswith("mk_agent_"):
            token = x_api_key
    if token is None:
        return None, None
    ctx, _err = await validate_agent_key(token)
    if ctx is None:
        return None, None
    return ctx, token


# ---------------------------------------------------------------------------
# Method handlers
# ---------------------------------------------------------------------------


def _handle_initialize(request_id: Any, _params: dict) -> JSONResponse:
    """
    Return the MCP initialize response (unauthenticated).

    We always advertise 2025-06-18 regardless of what the client sent in
    params.protocolVersion — we speak one version and it is the latest.
    """
    return _jsonrpc_result(
        request_id,
        {
            "protocolVersion": _PROTOCOL_VERSION,
            "capabilities": _CAPABILITIES,
            "serverInfo": _SERVER_INFO,
            "instructions": _INSTRUCTIONS,
        },
    )


def _handle_tools_list(request_id: Any) -> JSONResponse:
    """Return the static list of Mintkey tools."""
    return _jsonrpc_result(request_id, {"tools": TOOLS})


async def _handle_tools_call(
    request_id: Any,
    params: dict,
    agent_ctx: dict,
    agent_key: str,
    request: Request,
) -> JSONResponse:
    """
    Dispatch a tools/call method to the appropriate internal REST handler.

    Uses httpx.AsyncClient(app=app, base_url=...) for an in-process loopback
    so we reuse ALL existing logic: auth, RLS, audit, error handling, DB sessions.

    Tool-level errors (403, 404, 502 from upstream) become result.isError=true
    rather than JSON-RPC error envelopes — per spec §tools/call.
    """
    name = params.get("name", "")
    args = params.get("arguments") or {}

    if not name:
        return _jsonrpc_error(request_id, -32602, "Invalid params: 'name' is required")

    auth_header = {"Authorization": f"Bearer {agent_key}"}

    # Use request.app so that test dependency_overrides (DB mocks etc.) carry
    # through into the loopback, and to avoid importing the module-level
    # singleton which may not have the same overrides.
    _app = request.app

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=_app), base_url="http://internal"
    ) as client:
        upstream = await _dispatch_tool(client, name, args, auth_header)

    if upstream is None:
        return _jsonrpc_error(
            request_id,
            -32601,
            f"Unknown tool: {name}",
            data={
                "hint": (
                    "Call tools/list to see available tools. "
                    f"Received: {name!r}"
                )
            },
        )

    return _jsonrpc_result(request_id, _upstream_to_tool_result(upstream))


async def _dispatch_tool(
    client: httpx.AsyncClient,
    name: str,
    args: dict,
    auth_header: dict,
) -> httpx.Response | None:
    """
    Map a tool name to the corresponding internal REST call.

    Returns the httpx.Response from the loopback, or None if the tool name
    is not recognised.
    """
    if name == "mintkey_bootstrap":
        # MCP tool default is 'index' (compact); REST endpoint default is 'full' for compat.
        section_val: str = str(args.get("section") or "index")
        return await client.get("/v1/tools/bootstrap", params={"section": section_val})

    if name == "mintkey_list_services":
        return await client.get("/v1/tools/list_services", headers=auth_header)

    if name == "mintkey_discover":
        return await client.get("/v1/tools/discover", headers=auth_header)

    if name == "mintkey_describe_service":
        service_id = args.get("service_id")
        if not service_id:
            # Return a synthetic 422-like response — caller wraps it as isError
            return _synthetic_error_response(
                422,
                {"code": "mintkey:invalid_params", "detail": "'service_id' argument is required"},
            )
        return await client.get(
            f"/v1/tools/describe_service/{service_id}", headers=auth_header
        )

    if name == "mintkey_get_openapi":
        service_id = args.get("service_id")
        if not service_id:
            return _synthetic_error_response(
                422,
                {"code": "mintkey:invalid_params", "detail": "'service_id' argument is required"},
            )
        return await client.get(
            f"/v1/tools/get_openapi/{service_id}", headers=auth_header
        )

    if name == "mintkey_request_token":
        service_id = args.get("service_id")
        if not service_id:
            return _synthetic_error_response(
                422,
                {"code": "mintkey:invalid_params", "detail": "'service_id' argument is required"},
            )
        action = args.get("action", "call")
        return await client.post(
            "/v1/tools/request_token",
            headers=auth_header,
            json={"service_id": service_id, "action": action},
        )

    # Agent secret tools (ADR-0025)
    if name == "secret_put":
        name_arg = args.get("name")
        value_arg = args.get("value")
        if not name_arg or value_arg is None:
            return _synthetic_error_response(
                422,
                {"code": "mintkey:invalid_params", "detail": "'name' and 'value' arguments are required"},
            )
        body: dict = {"name": name_arg, "value": value_arg}
        if args.get("content_type"):
            body["content_type"] = args["content_type"]
        return await client.post(
            "/v1/tools/secret_put", headers=auth_header, json=body
        )

    if name == "secret_get":
        secret_id = args.get("secret_id")
        if not secret_id:
            return _synthetic_error_response(
                422,
                {"code": "mintkey:invalid_params", "detail": "'secret_id' argument is required"},
            )
        return await client.get(
            "/v1/tools/secret_get", headers=auth_header, params={"secret_id": secret_id}
        )

    if name == "secret_list":
        params: dict = {}
        if args.get("after"):
            params["after"] = args["after"]
        if args.get("limit") is not None:
            params["limit"] = args["limit"]
        return await client.get(
            "/v1/tools/secret_list", headers=auth_header, params=params
        )

    if name == "secret_delete":
        secret_id = args.get("secret_id")
        if not secret_id:
            return _synthetic_error_response(
                422,
                {"code": "mintkey:invalid_params", "detail": "'secret_id' argument is required"},
            )
        return await client.delete(
            "/v1/tools/secret_delete", headers=auth_header, params={"secret_id": secret_id}
        )

    return None  # unknown tool


class _synthetic_error_response:  # noqa: N801 (intentional lowercase)
    """Lightweight stand-in for httpx.Response when we need a synthetic error."""

    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:  # noqa: D102
        return self._body

    @property
    def text(self) -> str:  # noqa: D102
        return json.dumps(self._body)


def _upstream_to_tool_result(resp: httpx.Response | _synthetic_error_response) -> dict:
    """
    Translate an upstream REST response to an MCP tools/call result envelope.

    200 → isError=False, content=[text block of the JSON body]
    4xx/5xx → isError=True, content=[text block with error details]

    structuredContent is always included with the raw JSON so MCP clients that
    understand it can use the data directly without parsing the text block.
    """
    try:
        body = resp.json()
    except Exception:
        body = {"raw": getattr(resp, "text", str(resp))}

    is_error = resp.status_code >= 400

    if is_error:
        # Extract a human-readable message from Problem objects or Mintkey error envelopes.
        code = body.get("mintkey:code") or body.get("code", "")
        title = body.get("title", "")
        detail = body.get("detail", "")
        reason = body.get("reason_code", "")
        hint = body.get("hint", "")
        parts = [f"HTTP {resp.status_code}"]
        if code:
            parts.append(f"code={code}")
        if title:
            parts.append(title)
        if detail:
            parts.append(detail)
        if reason:
            parts.append(f"reason={reason}")
        if hint:
            parts.append(f"hint: {hint[:120]}")
        text = " | ".join(parts)
    else:
        text = json.dumps(body, indent=2)

    return _tool_result(
        [_text_block(text)],
        is_error=is_error,
    )


# ---------------------------------------------------------------------------
# Central dispatch
# ---------------------------------------------------------------------------


async def _dispatch(request: Request) -> Response:
    """
    Parse the JSON-RPC envelope and route to the appropriate handler.

    HTTP status is always 200 for valid JSON-RPC (errors live in error field).
    Exception: notifications/initialized returns 202.
    Malformed (non-JSON-RPC) POST bodies return 400 with a helpful hint.
    """
    # 1. Parse JSON body
    try:
        body = await request.json()
    except Exception:
        return _jsonrpc_error(None, -32700, "Parse error: invalid JSON")

    # 2. Validate envelope
    if (
        not isinstance(body, dict)
        or body.get("jsonrpc") != "2.0"
        or "method" not in body
    ):
        return _helpful_400()

    request_id = body.get("id")  # None is valid for notifications
    method: str = body["method"]
    params: dict = body.get("params") or {}

    # 3. Method dispatch
    if method == "initialize":
        return _handle_initialize(request_id, params)

    if method == "notifications/initialized":
        # Notification — no id, no response body; HTTP 202
        return Response(status_code=202)

    if method == "tools/list":
        agent_ctx, _key = await _require_agent(request)
        if agent_ctx is None:
            return _jsonrpc_error(
                request_id,
                -32001,
                "Unauthorized: Bearer mk_agent_<key> required",
            )
        return _handle_tools_list(request_id)

    if method == "resources/list":
        return _handle_resources_list(request_id)

    if method == "resources/read":
        return _handle_resources_read(request_id, params)

    if method == "tools/call":
        agent_ctx, agent_key = await _require_agent(request)
        if agent_ctx is None:
            return _jsonrpc_error(
                request_id,
                -32001,
                "Unauthorized: Bearer mk_agent_<key> required",
            )
        return await _handle_tools_call(request_id, params, agent_ctx, agent_key, request)

    # Unknown method
    return _jsonrpc_error(
        request_id,
        -32601,
        f"Method not found: {method}",
        data={
            "hint": (
                "Supported methods: initialize, notifications/initialized, "
                "tools/list, tools/call, resources/list, resources/read"
            ),
            "received": method,
        },
    )


# ---------------------------------------------------------------------------
# Routes — POST at all three MCP entry points
# ---------------------------------------------------------------------------


@router.post("/")
async def post_root(request: Request) -> Response:
    """JSON-RPC dispatcher at /."""
    return await _dispatch(request)


@router.post("/mcp")
async def post_mcp(request: Request) -> Response:
    """JSON-RPC dispatcher at /mcp (canonical MCP HTTP entry point)."""
    return await _dispatch(request)


@router.post("/v1/mcp")
async def post_v1_mcp(request: Request) -> Response:
    """JSON-RPC dispatcher at /v1/mcp (alias for /mcp)."""
    return await _dispatch(request)
