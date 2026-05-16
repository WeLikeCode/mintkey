"""Resolver helpers for operator-facing public URLs (admin-api side).

Both MCP and proxy URLs can be configured per-deployment via env vars.
See docs/NETWORK.md for the full taxonomy + LAN/cloud setup notes.

Precedence (highest first):
  1. MINTKEY_MCP_PUBLIC_URL (canonical, new)
  2. MCP_BASE_URL (legacy alias — accepted with deprecation log)
  3. Default "http://localhost:8082"

Trailing slashes are stripped so callers can interpolate `f"{url}/v1/..."`.

Logged once at startup if a legacy alias is in effect:
  WARN mintkey.public_url.legacy_env_var_used name=MCP_BASE_URL canonical=MINTKEY_MCP_PUBLIC_URL
"""
import os
import logging
from typing import Optional

_logger = logging.getLogger(__name__)
_warned: set[str] = set()

_DEFAULT_MCP = "http://localhost:8082"


def _read_with_fallback(canonical: str, legacy_names: list[str], default: str) -> str:
    val = os.getenv(canonical)
    if val:
        return val.rstrip("/")
    for name in legacy_names:
        val = os.getenv(name)
        if val:
            if name not in _warned:
                _warned.add(name)
                _logger.warning(
                    "mintkey.public_url.legacy_env_var_used name=%s canonical=%s",
                    name, canonical,
                )
            return val.rstrip("/")
    return default.rstrip("/")


def resolve_mcp_public_url() -> str:
    """Return the URL agents should use to reach the MCP server.

    URL is snapshotted at agent creation time; changing MINTKEY_MCP_PUBLIC_URL
    later does not retroactively update existing rows. See docs/NETWORK.md.
    """
    return _read_with_fallback(
        canonical="MINTKEY_MCP_PUBLIC_URL",
        legacy_names=["MCP_BASE_URL"],
        default=_DEFAULT_MCP,
    )
