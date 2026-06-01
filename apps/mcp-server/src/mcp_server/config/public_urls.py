"""Resolver helpers for operator-facing public URLs (mcp-server side).

Mirrors admin-api/src/admin_api/config/public_urls.py — keep precedence in sync.

Precedence:
  MCP URL:   MINTKEY_MCP_PUBLIC_URL → MINTKEY_MCP_URL → http://localhost:8082
  Proxy URL: MINTKEY_PROXY_PUBLIC_URL → MINTKEY_PROXY_URL → KONG_PROXY_URL → http://localhost:8000

Trailing slashes stripped. Legacy aliases logged once at first use.

See docs/NETWORK.md.
"""
import os
import logging

_logger = logging.getLogger(__name__)
_warned: set[str] = set()


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
    return _read_with_fallback(
        canonical="MINTKEY_MCP_PUBLIC_URL",
        legacy_names=["MINTKEY_MCP_URL"],
        default="http://localhost:8082",
    )


def resolve_proxy_public_url() -> str:
    return _read_with_fallback(
        canonical="MINTKEY_PROXY_PUBLIC_URL",
        legacy_names=["MINTKEY_PROXY_URL", "KONG_PROXY_URL"],
        default="http://localhost:8000",
    )


def resolve_ssh_proxy_public_host() -> tuple[str, int]:
    """
    Return (external_host, external_port) for the SSH bastion reachable by
    agents that run outside the Docker network (e.g. on the operator workstation).

    Precedence:
      1. MINTKEY_SSH_PROXY_PUBLIC_URL  — full URL form: "ssh://host:port" or "host:port"
      2. Derive from MINTKEY_MCP_PUBLIC_URL / MINTKEY_KEYCLOAK_PUBLIC_URL hostname,
         port 2222.
      3. Internal-only fallback: host="ssh-proxy", port=2222.

    The internal Docker hostname is always "ssh-proxy" port 2222.
    """
    import re as _re
    raw = os.getenv("MINTKEY_SSH_PROXY_PUBLIC_URL", "")
    if raw:
        raw = raw.strip()
        # Strip ssh:// scheme if present
        raw = _re.sub(r"^ssh://", "", raw)
        if ":" in raw:
            host_part, port_part = raw.rsplit(":", 1)
            try:
                return host_part.strip(), int(port_part.strip())
            except ValueError:
                pass
        return raw, 2222
    # Derive from MCP or Keycloak public URL hostname
    for env_name in ("MINTKEY_MCP_PUBLIC_URL", "MINTKEY_KEYCLOAK_PUBLIC_URL"):
        val = os.getenv(env_name, "")
        if val:
            # Extract hostname from http(s)://host:port or http://host
            m = _re.match(r"https?://([^/:]+)", val)
            if m:
                return m.group(1), 2222
    # Internal-only fallback
    return "ssh-proxy", 2222
