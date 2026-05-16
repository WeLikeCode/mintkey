"""
R6 bootstrap tool tests — unauthenticated mintkey_bootstrap endpoint.

Tests:
  1. GET /v1/tools/bootstrap without any auth header → 200 + JSON with skill_markdown.
  2. Response markdown contains verbatim XML-tagged section markers and opening sentence.
  3. GET /v1/tools/discover without auth → 401 (proves bootstrap bypass is scoped).
  4. (NET-B) Canonical MINTKEY_MCP_PUBLIC_URL and MINTKEY_PROXY_PUBLIC_URL reflected.
  5. (NET-B) Legacy MINTKEY_MCP_URL and MINTKEY_PROXY_URL / KONG_PROXY_URL honored.
  6. (NET-B) Trailing slash stripped from canonical env vars.

Unit tests (always run — use ASGI test client; no docker required).
Integration tests (MINTKEY_INTEGRATION_TEST=true) — probe the live container.

Source: R6 of action-grid remediation; ADR-0009; ADR-0017; NET-B.
"""
from __future__ import annotations

import importlib
import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Integration marker (matches pattern in tests/acceptance/test_mcp_auth_chain.py)
# ---------------------------------------------------------------------------
INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full docker-compose stack",
)

_REPO_ROOT = Path(__file__).resolve().parents[3]  # mintkey/
_SKILLS_FILE = _REPO_ROOT / "mcp-server" / "skills" / "agent-bootstrap.md"

BASE_MCP = os.getenv("MINTKEY_MCP_URL", "http://localhost:8082")


# ===========================================================================
# Unit tests — ASGI client; no real DB/auth needed
# ===========================================================================


def test_bootstrap_route_exists_and_returns_200() -> None:
    """
    GET /v1/tools/bootstrap without any auth header must return 200.

    Fails (404) before the bootstrap tool is registered.
    Source: R6 AC5a.
    """
    from httpx import AsyncClient, ASGITransport
    import asyncio

    # Patch validate_agent_key to avoid real network call inside middleware
    import mcp_server.auth.agent_key as _ak
    _orig = _ak.validate_agent_key

    async def _noop(key):  # middleware calls this if a key is present; no key here
        return None, "no_key"

    _ak.validate_agent_key = _noop
    try:
        from mcp_server.main import create_app
        app = create_app()

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get("/v1/tools/bootstrap")
                return r

        resp = asyncio.run(_run())
    finally:
        _ak.validate_agent_key = _orig

    assert resp.status_code == 200, (
        f"Expected 200 from /v1/tools/bootstrap (no auth), got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "skill_markdown" in body, f"Missing 'skill_markdown' key: {body.keys()}"
    assert "proxy_url" in body, f"Missing 'proxy_url' key: {body.keys()}"
    assert "mcp_url" in body, f"Missing 'mcp_url' key: {body.keys()}"
    assert "version" in body, f"Missing 'version' key: {body.keys()}"


def test_bootstrap_markdown_contains_required_sections() -> None:
    """
    The returned skill_markdown must contain the verbatim XML-tagged section
    markers that agents parse, and the opening agent-directed sentence.

    Source: R6 AC5b.
    """
    from httpx import AsyncClient, ASGITransport
    import asyncio

    import mcp_server.auth.agent_key as _ak
    _orig = _ak.validate_agent_key

    async def _noop(key):
        return None, "no_key"

    _ak.validate_agent_key = _noop
    try:
        from mcp_server.main import create_app
        app = create_app()

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get("/v1/tools/bootstrap")
                return r

        resp = asyncio.run(_run())
    finally:
        _ak.validate_agent_key = _orig

    assert resp.status_code == 200
    body = resp.json()
    md = body["skill_markdown"]

    # XML-tagged sections from the canonical skill file
    for tag in ("<authentication>", "<proxy_usage>", "<service_discovery>", "<overview>"):
        assert tag in md, f"Verbatim section tag {tag!r} missing from skill_markdown"

    # Opening sentence (verbatim from agent-bootstrap.md)
    assert "You are an AI agent" in md, (
        "Expected opening phrase 'You are an AI agent' in skill_markdown"
    )


def test_discover_without_auth_returns_401() -> None:
    """
    GET /v1/tools/discover without any auth must return 401.
    Proves the auth bypass is scoped only to /v1/tools/bootstrap.

    Source: R6 AC5c.
    """
    from httpx import AsyncClient, ASGITransport
    import asyncio

    import mcp_server.auth.agent_key as _ak
    _orig = _ak.validate_agent_key

    async def _noop(key):
        return None, "no_key"

    _ak.validate_agent_key = _noop
    try:
        from mcp_server.main import create_app
        app = create_app()

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                r = await client.get("/v1/tools/discover")
                return r

        resp = asyncio.run(_run())
    finally:
        _ak.validate_agent_key = _orig

    assert resp.status_code == 401, (
        f"Expected 401 from /v1/tools/discover (no auth), got {resp.status_code}: {resp.text}"
    )


# ===========================================================================
# NET-B unit tests — public URL resolver reflected in bootstrap response
# ===========================================================================

def _fresh_resolver():
    """Re-import the resolver module so _warned state and module-level cache are clean."""
    mod_name = "mcp_server.config.public_urls"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    import mcp_server.config.public_urls as m
    return m


def _bootstrap_response_with_env(monkeypatch, env_vars: dict) -> dict:
    """
    Run the ASGI bootstrap endpoint with patched environment and a freshly loaded
    resolver module, returning the parsed JSON body.
    """
    from httpx import AsyncClient, ASGITransport
    import asyncio

    # Clear all URL-related env vars, then set the ones under test
    for key in ("MINTKEY_MCP_PUBLIC_URL", "MINTKEY_MCP_URL",
                "MINTKEY_PROXY_PUBLIC_URL", "MINTKEY_PROXY_URL", "KONG_PROXY_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, val in env_vars.items():
        monkeypatch.setenv(key, val)

    # Reload the resolver so it picks up the new env
    _fresh_resolver()

    # Reload bootstrap module so module-level _MCP_URL/_PROXY_URL are recomputed
    bootstrap_mod_name = "mcp_server.tools.bootstrap"
    if bootstrap_mod_name in sys.modules:
        del sys.modules[bootstrap_mod_name]

    import mcp_server.auth.agent_key as _ak
    _orig = _ak.validate_agent_key

    async def _noop(key):
        return None, "no_key"

    _ak.validate_agent_key = _noop
    try:
        from mcp_server.main import create_app
        # Reload main too so router registration picks up the reloaded bootstrap
        main_mod_name = "mcp_server.main"
        if main_mod_name in sys.modules:
            del sys.modules[main_mod_name]
        from mcp_server.main import create_app
        app = create_app()

        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get("/v1/tools/bootstrap")

        resp = asyncio.run(_run())
    finally:
        _ak.validate_agent_key = _orig

    assert resp.status_code == 200, f"Expected 200 from bootstrap, got {resp.status_code}: {resp.text}"
    return resp.json()


@pytest.mark.parametrize("env_vars,expected_mcp,expected_proxy", [
    # canonical MCP URL wins
    (
        {"MINTKEY_MCP_PUBLIC_URL": "https://mcp.example.com"},
        "https://mcp.example.com",
        "http://localhost:8000",
    ),
    # canonical proxy URL wins
    (
        {"MINTKEY_PROXY_PUBLIC_URL": "https://proxy.example.com"},
        "http://localhost:8082",
        "https://proxy.example.com",
    ),
    # canonical trailing slash stripped
    (
        {"MINTKEY_MCP_PUBLIC_URL": "https://mcp.example.com/"},
        "https://mcp.example.com",
        "http://localhost:8000",
    ),
    # legacy MINTKEY_MCP_URL honored
    (
        {"MINTKEY_MCP_URL": "https://legacy-mcp.example.com"},
        "https://legacy-mcp.example.com",
        "http://localhost:8000",
    ),
    # legacy MINTKEY_PROXY_URL honored
    (
        {"MINTKEY_PROXY_URL": "https://legacy-proxy.example.com"},
        "http://localhost:8082",
        "https://legacy-proxy.example.com",
    ),
    # legacy KONG_PROXY_URL honored (lowest priority)
    (
        {"KONG_PROXY_URL": "http://kong.test:8000"},
        "http://localhost:8082",
        "http://kong.test:8000",
    ),
    # both canonical set — both reflected
    (
        {
            "MINTKEY_MCP_PUBLIC_URL": "https://mcp.example.com",
            "MINTKEY_PROXY_PUBLIC_URL": "https://proxy.example.com",
        },
        "https://mcp.example.com",
        "https://proxy.example.com",
    ),
])
def test_bootstrap_url_env_vars(monkeypatch, env_vars, expected_mcp, expected_proxy):
    """
    bootstrap response reflects canonical and legacy env vars for mcp_url and proxy_url.
    Source: NET-B.
    """
    body = _bootstrap_response_with_env(monkeypatch, env_vars)
    assert body["mcp_url"] == expected_mcp, (
        f"mcp_url mismatch: got {body['mcp_url']!r}, expected {expected_mcp!r}"
    )
    assert body["proxy_url"] == expected_proxy, (
        f"proxy_url mismatch: got {body['proxy_url']!r}, expected {expected_proxy!r}"
    )


# ===========================================================================
# Integration tests (requires docker-compose stack)
# ===========================================================================


@INTEGRATION
def test_integration_bootstrap_unauthenticated() -> None:
    """
    Live container: GET /v1/tools/bootstrap without any auth → 200 + skill_markdown.
    Source: R6 AC7.
    """
    import httpx

    with httpx.Client(timeout=15) as client:
        r = client.get(f"{BASE_MCP}/v1/tools/bootstrap")
    assert r.status_code == 200, (
        f"Bootstrap returned {r.status_code}: {r.text}"
    )
    body = r.json()
    assert "skill_markdown" in body
    assert "<authentication>" in body["skill_markdown"]
    assert "<proxy_usage>" in body["skill_markdown"]


@INTEGRATION
def test_integration_discover_without_auth_is_401() -> None:
    """
    Live container: GET /v1/tools/discover without auth → 401.
    Source: R6 AC8.
    """
    import httpx

    with httpx.Client(timeout=15) as client:
        r = client.get(f"{BASE_MCP}/v1/tools/discover")
    assert r.status_code == 401, (
        f"Discover without auth returned {r.status_code} (expected 401): {r.text}"
    )
