"""
R6 bootstrap tool tests — unauthenticated mintkey_bootstrap endpoint.

Tests:
  1. GET /v1/tools/bootstrap without any auth header → 200 + JSON with skill_markdown.
  2. Response markdown contains verbatim XML-tagged section markers and opening sentence.
  3. GET /v1/tools/discover without auth → 401 (proves bootstrap bypass is scoped).

Unit tests (always run — use ASGI test client; no docker required).
Integration tests (MINTKEY_INTEGRATION_TEST=true) — probe the live container.

Source: R6 of action-grid remediation; ADR-0009; ADR-0017.
"""
from __future__ import annotations

import os
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
