"""
T-A tests — bootstrap sectioning (P1).

Tests that:
- section=index returns a compact TOC payload (no skill_markdown).
- section=full returns the full legacy payload (backward compat, INV-4).
- A named section returns only that XML block.
- An unknown section falls back to index.
- The MCP tools/call path forwards the section argument.

Source: .kiro/specs/mcp-token-optimization/ AC-1 through AC-4.
"""
from __future__ import annotations

import asyncio
import json

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_noop_auth():
    """Return a fake validate_agent_key that accepts anything."""
    async def _noop(key):
        return None, "no_key"
    return _noop


def _make_agent_auth():
    """Return a fake validate_agent_key that returns a valid agent context."""
    async def _fake(key):
        return {"agent_id": "test-agent-id", "tenant_id": "00000000-0000-0000-0000-000000000001"}, None
    return _fake


def _get_bootstrap(section: str | None = None) -> dict:
    """GET /v1/tools/bootstrap with optional ?section= param; return parsed body."""
    import mcp_server.auth.agent_key as _ak
    _orig = _ak.validate_agent_key
    _ak.validate_agent_key = _make_noop_auth()
    try:
        from mcp_server.main import create_app
        from httpx import AsyncClient, ASGITransport
        app = create_app()

        async def _run():
            params = {"section": section} if section else {}
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.get("/v1/tools/bootstrap", params=params)

        resp = asyncio.run(_run())
    finally:
        _ak.validate_agent_key = _orig
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_bootstrap_default_is_index() -> None:
    """?section=index returns compact index payload (no skill_markdown)."""
    body = _get_bootstrap("index")
    assert "sections" in body, f"Expected 'sections' key in index payload: {list(body)}"
    assert "resource_uri" in body, f"Expected 'resource_uri' key: {list(body)}"
    assert body["resource_uri"] == "mintkey://skill/agent-bootstrap"
    assert "bootstrap_version" in body
    assert body["bootstrap_version"] == "2.0"
    assert len(body["sections"]) == 7
    assert "skill_markdown" not in body, "Index payload must NOT include skill_markdown"


def test_bootstrap_section_full_matches_legacy() -> None:
    """?section=full returns legacy keys + bootstrap_version 2.0 (INV-4, AC-2)."""
    body = _get_bootstrap("full")
    assert "skill_markdown" in body, f"full section must have skill_markdown: {list(body)}"
    assert "proxy_url" in body
    assert "mcp_url" in body
    assert "version" in body
    assert body["version"] == "1.0"
    assert body.get("bootstrap_version") == "2.0"
    assert len(body["skill_markdown"]) > 1000, "skill_markdown should be non-trivial"


def test_bootstrap_section_auth_returns_only_auth() -> None:
    """?section=auth returns only the <authentication> XML block (AC-3)."""
    body = _get_bootstrap("auth")
    assert "content" in body, f"Named section must have 'content': {list(body)}"
    assert "section" in body
    assert body["section"] == "auth"
    content = body["content"]
    assert "<authentication>" in content, "Expected <authentication> tag in content"
    assert "<agent_secrets>" not in content, "auth section must NOT include <agent_secrets>"
    assert "skill_markdown" not in body


def test_bootstrap_unknown_section_is_index() -> None:
    """?section=bogus falls back to index payload (FR-6, AC-4)."""
    body = _get_bootstrap("bogus_section_xyz")
    assert "sections" in body, f"Unknown section should fall back to index: {list(body)}"
    assert "skill_markdown" not in body


def test_bootstrap_section_via_tools_call() -> None:
    """JSON-RPC tools/call mintkey_bootstrap with section=secrets returns <agent_secrets>."""
    import mcp_server.main as _main_mod
    import mcp_server.tools.jsonrpc as _jsonrpc_mod
    _orig_main = _main_mod.validate_agent_key
    _orig_jrpc = _jsonrpc_mod.validate_agent_key
    _vfn = _make_agent_auth()
    _main_mod.validate_agent_key = _vfn
    _jsonrpc_mod.validate_agent_key = _vfn
    try:
        from mcp_server.main import create_app
        from httpx import AsyncClient, ASGITransport
        app = create_app()

        async def _run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.post(
                    "/mcp",
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "mintkey_bootstrap",
                            "arguments": {"section": "secrets"},
                        },
                    },
                    headers={"Authorization": "Bearer mk_agent_testkey"},
                )

        resp = asyncio.run(_run())
    finally:
        _main_mod.validate_agent_key = _orig_main
        _jsonrpc_mod.validate_agent_key = _orig_jrpc

    assert resp.status_code == 200
    result = resp.json()
    content_blocks = result["result"]["content"]
    assert content_blocks, "Expected non-empty content blocks"
    text = content_blocks[0]["text"]
    parsed = json.loads(text)
    assert "<agent_secrets>" in parsed.get("content", ""), (
        f"Expected <agent_secrets> in section content, got: {parsed!r}"
    )
