"""
MCP bootstrap tool — unauthenticated.

GET /v1/tools/bootstrap

Returns the full contents of mcp-server/skills/agent-bootstrap.md so that ANY
AI agent (Claude, GPT, Gemini, custom) can self-onboard to Mintkey without a
pre-installed skill.  This is the ONLY tool in mcp-server that requires no
authentication — it is the entry point before an agent has any credentials.

Auth bypass rationale: every other /v1/tools/* route reads `request.state.agent_context`
and returns 401 when it is absent.  This route explicitly skips that check — that
is intentional and scoped.  See main.py where /v1/tools/bootstrap is listed in the
same bypass whitelist as /health and /v1/tools/instructions.

Design notes:
- The skill markdown is loaded ONCE at import time (module-level cache).
- If the file is missing at import, we raise immediately so the container fails
  the health check and the missing skill is caught in CI before any request is served.
- proxy_url / mcp_url are read from env at import time with documented defaults.
- An OTel span `mcp.bootstrap.requested` is emitted per request (no tenant context).

Source: R6 of action-grid remediation; ADR-0009; ADR-0017.
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from mcp_server.config.public_urls import resolve_mcp_public_url, resolve_proxy_public_url

# Use structlog if available (production container), otherwise fall back to stdlib logging
try:
    import structlog as _structlog
    logger = _structlog.get_logger(__name__)
except ImportError:
    logger = logging.getLogger(__name__)  # type: ignore[assignment]

router = APIRouter(prefix="/v1/tools")

# ---------------------------------------------------------------------------
# Module-level constants — read once at startup; never re-read per request.
# ---------------------------------------------------------------------------

# Candidate paths for agent-bootstrap.md, tried in order:
#   1. /app/skills/... — Docker WORKDIR (/app), skills/ copied alongside src/ (Dockerfile R6)
#   2. parents[3]/skills/ — local dev: mcp-server/src/mcp_server/tools/../../.. = mcp-server/skills/
_SKILL_FILE_CANDIDATES = [
    Path("/app/skills/agent-bootstrap.md"),                                # Docker
    Path(__file__).resolve().parents[3] / "skills" / "agent-bootstrap.md",  # local dev
]


def _load_skill_markdown() -> str:
    """
    Load agent-bootstrap.md verbatim.  Fails fast if the file is absent so
    that startup/CI surfaces the problem before any request is served.
    """
    for candidate in _SKILL_FILE_CANDIDATES:
        if candidate.exists():
            content = candidate.read_text(encoding="utf-8")
            logger.info("mintkey_bootstrap.skill_loaded", path=str(candidate), bytes=len(content))
            return content
    paths = "\n  ".join(str(c) for c in _SKILL_FILE_CANDIDATES)
    raise FileNotFoundError(
        f"agent-bootstrap.md not found. Checked:\n  {paths}\n"
        "Ensure mcp-server/skills/agent-bootstrap.md is present before starting the server."
    )


# Cache the markdown at module load time (startup). KeyError here → container unhealthy → caught in CI.
_SKILL_MARKDOWN: str = _load_skill_markdown()

_PROXY_URL: str = resolve_proxy_public_url()
_MCP_URL: str = resolve_mcp_public_url()
_VERSION: str = "1.0"

# ---------------------------------------------------------------------------
# OTel — optional; if opentelemetry not installed we emit a structured log instead.
# ---------------------------------------------------------------------------
try:
    from opentelemetry import trace as _otel_trace
    _tracer = _otel_trace.get_tracer("mintkey.mcp-server")
    _OTEL_AVAILABLE = True
except ImportError:
    _tracer = None
    _OTEL_AVAILABLE = False


def _emit_bootstrap_span(request: Request) -> None:
    """Emit OTel span mcp.bootstrap.requested with pre-auth metadata."""
    client_ip = request.client.host if request.client else "unknown"
    user_agent = request.headers.get("user-agent", "")
    if _OTEL_AVAILABLE and _tracer:
        with _tracer.start_as_current_span("mcp.bootstrap.requested") as span:
            span.set_attribute("http.client_ip", client_ip)
            span.set_attribute("http.user_agent", user_agent)
            span.set_attribute("mintkey.pre_auth", True)
    else:
        logger.info(
            "mcp.bootstrap.requested",
            client_ip=client_ip,
            user_agent=user_agent,
            pre_auth=True,
        )


# ---------------------------------------------------------------------------
# Route — no auth required (see bypass in main.py agent_key_middleware)
# ---------------------------------------------------------------------------


@router.get("/bootstrap")
async def bootstrap(request: Request) -> JSONResponse:
    """
    Return vendor-agnostic instructions for any AI agent to authenticate to
    Mintkey, discover services, and call the egress proxy.

    **No authentication required.** Call this first; it tells you how to get
    an API key and what to do next.

    Tool name: mintkey_bootstrap
    Tool description: Returns vendor-agnostic instructions for any AI agent to
    authenticate to Mintkey, discover services, and call the egress proxy.
    Call first; no auth required.

    Input schema: {} (no body for GET)

    Output:
      skill_markdown  — full contents of mcp-server/skills/agent-bootstrap.md (verbatim)
      proxy_url       — Mintkey egress proxy URL (MINTKEY_PROXY_URL env / default)
      mcp_url         — this MCP server's URL (MINTKEY_MCP_URL env / default)
      version         — skill version ("1.0")

    Source: R6 of action-grid remediation; ADR-0009; ADR-0017.
    """
    _emit_bootstrap_span(request)
    return JSONResponse(
        {
            "skill_markdown": _SKILL_MARKDOWN,
            "proxy_url": _PROXY_URL,
            "mcp_url": _MCP_URL,
            "version": _VERSION,
        }
    )
