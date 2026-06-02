"""
MCP landing pages — unauthenticated GET endpoints that return 200 JSON.

Vanilla MCP clients (Claude Code, Cursor, mcp-cli) probe /, /mcp, /v1, /v1/mcp,
and /v1/tools before trying the real JSON-RPC path.  Previously all of these
returned 404, forcing operators to read source to find the actual endpoints.

Each route returns a structured discovery document pointing at:
  - /mcp  — the standard MCP HTTP JSON-RPC entry point (added in MCP-D-BE)
  - /v1/tools/bootstrap  — the unauthenticated agent onboarding skill
  - all /v1/tools/* REST endpoints with their auth requirements

No authentication required for any route in this module.
No DB or external I/O.  All response bodies are module-level constants
(no per-request allocation).

Source: MCP-DISCOVER-DESIGN Section 4 Option C, Section 6 MCP-D-A.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()

# ---------------------------------------------------------------------------
# Module-level constants — built once at import; no per-request allocation.
# ---------------------------------------------------------------------------

_REST_ENDPOINTS: dict = {
    "bootstrap": {
        "method": "GET",
        "path": "/v1/tools/bootstrap",
        "auth": "none",
    },
    "instructions": {
        "method": "GET",
        "path": "/v1/tools/instructions",
        "auth": "none",
    },
    "list_services": {
        "method": "GET",
        "path": "/v1/tools/list_services",
        "auth": "bearer",
    },
    "discover": {
        "method": "GET",
        "path": "/v1/tools/discover",
        "auth": "bearer",
    },
    "describe_service": {
        "method": "GET",
        "path": "/v1/tools/describe_service/{service_id}",
        "auth": "bearer",
    },
    "get_openapi": {
        "method": "GET",
        "path": "/v1/tools/get_openapi/{service_id}",
        "auth": "bearer",
    },
    "request_token": {
        "method": "POST",
        "path": "/v1/tools/request_token",
        "auth": "bearer",
    },
    # Email tools — feat/agent-email-e2e
    "email_list_mailboxes": {
        "method": "GET",
        "path": "/v1/tools/email_list_mailboxes",
        "auth": "bearer",
    },
    "email_fetch_message": {
        "method": "GET",
        "path": "/v1/tools/email_fetch_message",
        "auth": "bearer",
    },
    "email_search_messages": {
        "method": "GET",
        "path": "/v1/tools/email_search_messages",
        "auth": "bearer",
    },
    "email_send": {
        "method": "POST",
        "path": "/v1/tools/email_send",
        "auth": "bearer",
    },
}

_AUTH_DOC: dict = {
    "schemes": ["bearer", "api_key"],
    "preferred_header": "Authorization: Bearer mk_agent_<key>",
    "legacy_header": "X-API-Key: mk_agent_<key>",
    "obtain_key": (
        "Operator issues an Agent API Key via admin-api; "
        "see GET /v1/tools/bootstrap for the onboarding skill."
    ),
}

_DOCS_DOC: dict = {
    "bootstrap_skill": "/v1/tools/bootstrap",
    "human_instructions": "/v1/tools/instructions",
}

# GET / and GET /v1 — top-level discovery document
_ROOT_DOC: dict = {
    "service": "mintkey-mcp-server",
    "version": "0.1.0-experimental",
    "protocolVersion": "2025-06-18",
    "hint": (
        "Vanilla MCP clients: POST /mcp with method=initialize. "
        "For the full credential-broker flow: GET /v1/tools/bootstrap."
    ),
    "endpoints": {
        "mcp_jsonrpc": {
            "url": "/mcp",
            "methods_supported": [
                "initialize",
                "notifications/initialized",
                "tools/list",
                "tools/call",
            ],
            "note": "Standard MCP HTTP transport (JSON-RPC 2.0).",
        },
        "rest": _REST_ENDPOINTS,
    },
    "auth": _AUTH_DOC,
    "documentation": _DOCS_DOC,
}

# GET /v1 — same shape with an alias note
_V1_DOC: dict = {
    **_ROOT_DOC,
    "endpoints": {
        "mcp_jsonrpc": {
            **_ROOT_DOC["endpoints"]["mcp_jsonrpc"],
            "note": (
                "Standard MCP HTTP transport (JSON-RPC 2.0). "
                "/v1/mcp is an alias for /mcp."
            ),
        },
        "rest": _REST_ENDPOINTS,
    },
}

# GET /mcp — emphasises JSON-RPC entry point
_MCP_DOC: dict = {
    **_ROOT_DOC,
    "endpoints": {
        "mcp_jsonrpc": {
            **_ROOT_DOC["endpoints"]["mcp_jsonrpc"],
            "note": "Standard MCP HTTP transport (JSON-RPC 2.0).",
            "jsonrpc_note": (
                "POST to this path with a JSON-RPC 2.0 envelope. "
                "See https://modelcontextprotocol.io/specification/2025-06-18 "
                "for the protocol."
            ),
        },
        "rest": _REST_ENDPOINTS,
    },
}

# GET /v1/tools — machine-readable tool index
_TOOLS_INDEX: dict = {
    "tools": {
        "bootstrap": {
            "method": "GET",
            "path": "/v1/tools/bootstrap",
            "auth": "none",
            "description": "Unauthenticated agent onboarding markdown",
        },
        "instructions": {
            "method": "GET",
            "path": "/v1/tools/instructions",
            "auth": "none",
            "description": "Unauthenticated human-facing usage guide",
        },
        "list_services": {
            "method": "GET",
            "path": "/v1/tools/list_services",
            "auth": "bearer",
            "description": "List services the agent has permission to call",
        },
        "discover": {
            "method": "GET",
            "path": "/v1/tools/discover",
            "auth": "bearer",
            "description": "list_services + how_to_call hints",
        },
        "describe_service": {
            "method": "GET",
            "path": "/v1/tools/describe_service/{service_id}",
            "auth": "bearer",
            "description": "Full service metadata",
        },
        "get_openapi": {
            "method": "GET",
            "path": "/v1/tools/get_openapi/{service_id}",
            "auth": "bearer",
            "description": "OpenAPI spec URL for a service",
        },
        "request_token": {
            "method": "POST",
            "path": "/v1/tools/request_token",
            "auth": "bearer",
            "description": "Exchange agent key for a short-lived brokered JWT",
        },
        # Email tools — feat/agent-email-e2e
        "email_list_mailboxes": {
            "method": "GET",
            "path": "/v1/tools/email_list_mailboxes",
            "auth": "bearer",
            "description": "List IMAP mailboxes for a granted email service",
        },
        "email_fetch_message": {
            "method": "GET",
            "path": "/v1/tools/email_fetch_message",
            "auth": "bearer",
            "description": "Fetch a single email message by UID",
        },
        "email_search_messages": {
            "method": "GET",
            "path": "/v1/tools/email_search_messages",
            "auth": "bearer",
            "description": "Search messages in an IMAP mailbox",
        },
        "email_send": {
            "method": "POST",
            "path": "/v1/tools/email_send",
            "auth": "bearer",
            "description": "Send an email via a granted email service",
        },
    }
}

# ---------------------------------------------------------------------------
# Routes — all GET, all unauthenticated, all return 200 application/json
# ---------------------------------------------------------------------------


@router.get("/")
async def root_landing() -> JSONResponse:
    """Top-level discovery document. No auth required."""
    return JSONResponse(_ROOT_DOC)


@router.get("/v1")
async def v1_landing() -> JSONResponse:
    """Version-prefixed discovery document. No auth required."""
    return JSONResponse(_V1_DOC)


@router.get("/mcp")
async def mcp_landing() -> JSONResponse:
    """MCP JSON-RPC entry point discovery document. No auth required."""
    return JSONResponse(_MCP_DOC)


@router.get("/v1/mcp")
async def v1_mcp_landing() -> JSONResponse:
    """Alias for GET /mcp. No auth required."""
    return JSONResponse(_MCP_DOC)


@router.get("/v1/tools")
async def tools_index() -> JSONResponse:
    """Machine-readable index of /v1/tools/* endpoints. No auth required."""
    return JSONResponse(_TOOLS_INDEX)
