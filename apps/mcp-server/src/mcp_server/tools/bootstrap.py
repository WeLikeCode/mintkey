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
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Query, Request
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

_GUIDE_DIRS = [
    Path("/app/skills/guides"),
    Path(__file__).resolve().parents[3] / "skills" / "guides",
]
_QUICKREF_CANDIDATES = [
    Path("/app/skills/quick-reference.md"),
    Path(__file__).resolve().parents[3] / "skills" / "quick-reference.md",
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


def _load_guide(filename: str) -> str:
    """Load a guide file from the guides/ directory. Fails fast if absent."""
    for base in _GUIDE_DIRS:
        p = base / filename
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise FileNotFoundError(
        f"guide not found: {filename}. Checked: "
        + ", ".join(str(d / filename) for d in _GUIDE_DIRS)
    )


def _load_quickref() -> str:
    """Load quick-reference.md. Fails fast if absent."""
    for p in _QUICKREF_CANDIDATES:
        if p.exists():
            return p.read_text(encoding="utf-8")
    raise FileNotFoundError(
        "quick-reference.md not found. Checked: "
        + ", ".join(str(p) for p in _QUICKREF_CANDIDATES)
    )


# Cache the markdown at module load time (startup). KeyError here → container unhealthy → caught in CI.
_SKILL_MARKDOWN: str = _load_skill_markdown()

_PROXY_URL: str = resolve_proxy_public_url()
_MCP_URL: str = resolve_mcp_public_url()
_VERSION: str = "1.0"

# ---------------------------------------------------------------------------
# Bootstrap sectioning — XML-tagged blocks parsed once at import (FR-9, INV-5).
# Section names → XML tag names in agent-bootstrap.md (verified in requirements §1.1).
# ---------------------------------------------------------------------------

_SECTION_TAGS: dict[str, str] = {
    "auth": "authentication",
    "discover": "service_discovery",
    "proxy_call": "proxy_usage",
    "email": "email_services",
    "secrets": "agent_secrets",
    "quick_start": "quick_start",
    "use_cases": "use_cases",
    "anti_patterns": "anti_patterns",
}
_SECTION_NAMES: list[str] = [
    "index", "auth", "discover", "proxy_call", "email", "secrets",
    "quick_start", "use_cases", "anti_patterns",
    "rest-api", "ssh", "secrets-guide", "email-guide", "quick-reference",
    "full",
]
_RESOURCE_URI = "mintkey://skill/agent-bootstrap"
_BOOTSTRAP_VERSION = "2.0"

# Guide resource URIs (loaded once at startup — same fail-fast pattern).
_GUIDE_RESOURCES: dict[str, str] = {
    "mintkey://guides/rest-api": _load_guide("rest-api.md"),
    "mintkey://guides/ssh":      _load_guide("ssh.md"),
    "mintkey://guides/secrets":  _load_guide("secrets.md"),
    "mintkey://guides/email":    _load_guide("email.md"),
    "mintkey://quick-reference": _load_quickref(),
}

# Alias → guide resource URI (these return guide files, NOT XML blocks).
# "email" and "secrets" are kept pointing at the XML blocks for backward-compat.
# New distinct aliases "email-guide" and "secrets-guide" point to the guide files.
_SECTION_GUIDE_ALIASES: dict[str, str] = {
    "rest-api":       "mintkey://guides/rest-api",
    "ssh":            "mintkey://guides/ssh",
    "secrets-guide":  "mintkey://guides/secrets",
    "email-guide":    "mintkey://guides/email",
    "quick-reference": "mintkey://quick-reference",
}


def _extract_xml_block(markdown: str, tag: str) -> str:
    """Return the <tag>...</tag> block including the tags, or '' if absent."""
    pattern = re.compile(rf"<{tag}>.*?</{tag}>", re.DOTALL)
    m = pattern.search(markdown)
    return m.group(0) if m else ""


_SECTIONS: dict[str, str] = {
    name: _extract_xml_block(_SKILL_MARKDOWN, tag) for name, tag in _SECTION_TAGS.items()
}
_OVERVIEW: str = _extract_xml_block(_SKILL_MARKDOWN, "overview")

# Fail fast if agent-bootstrap.md is re-sectioned without updating these tags.
for _section_name, _section_block in _SECTIONS.items():
    assert _section_block, f"agent-bootstrap.md missing XML section for '{_section_name}'"
assert _OVERVIEW, "agent-bootstrap.md missing <overview> section"


def _bootstrap_payload(section: str | None) -> dict[str, object]:
    """Build the bootstrap response for the requested section.

    None/empty/unknown → 'index'. 'full' → legacy payload + bootstrap_version.
    Named XML section → that XML block only. Guide alias → guide file content.
    'index' → compact TOC + resource pointer.
    """
    sel = (section or "index").strip().lower()

    if sel == "full":
        return {
            "skill_markdown": _SKILL_MARKDOWN,
            "proxy_url": _PROXY_URL,
            "mcp_url": _MCP_URL,
            "version": _VERSION,
            "bootstrap_version": _BOOTSTRAP_VERSION,
        }

    if sel in _SECTIONS:
        return {
            "section": sel,
            "content": _SECTIONS[sel],
            "resource_uri": _RESOURCE_URI,
            "bootstrap_version": _BOOTSTRAP_VERSION,
        }

    if sel in _SECTION_GUIDE_ALIASES:
        uri = _SECTION_GUIDE_ALIASES[sel]
        return {
            "section": sel,
            "content": _GUIDE_RESOURCES[uri],
            "resource_uri": uri,
            "bootstrap_version": _BOOTSTRAP_VERSION,
        }

    # 'index' and any unknown value (FR-6 graceful fallback)
    return {
        "sections": _SECTION_NAMES,
        "resource_uri": _RESOURCE_URI,
        "overview": _OVERVIEW,
        "proxy_url": _PROXY_URL,
        "mcp_url": _MCP_URL,
        "bootstrap_version": _BOOTSTRAP_VERSION,
    }


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
async def bootstrap(
    request: Request, section: Optional[str] = Query(default=None)
) -> JSONResponse:
    """
    Return vendor-agnostic instructions for any AI agent to authenticate to
    Mintkey, discover services, and call the egress proxy.

    **No authentication required.** Call this first; it tells you how to get
    an API key and what to do next.

    Optional ?section= query parameter selects a bootstrap section:
      index (default when called via MCP tool) | auth | discover | proxy_call |
      email | secrets | full (returns the entire skill_markdown, backward-compat default).

    Tool name: mintkey_bootstrap
    Tool description: Returns vendor-agnostic instructions for any AI agent to
    authenticate to Mintkey, discover services, and call the egress proxy.
    Call first; no auth required.

    Source: R6 of action-grid remediation; ADR-0009; ADR-0017.
    """
    _emit_bootstrap_span(request)
    # REST default is 'full' for backward compatibility (Decision D-2).
    # The MCP tool dispatcher sends ?section=index by default (see jsonrpc.py).
    return JSONResponse(_bootstrap_payload(section or "full"))
