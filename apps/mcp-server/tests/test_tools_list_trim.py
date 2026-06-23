"""
T-C tests — tools/list trimming (P2, AC-6).

Tests that:
- Every TOOLS entry has no 'title' key.
- The four secret tool descriptions match the exact trimmed strings (FR-10–FR-13).

Source: .kiro/specs/mcp-token-optimization/ FR-10 through FR-14, AC-6.
"""
from __future__ import annotations

import asyncio


_SECRET_DESCRIPTIONS = {
    "secret_put": "Store (or overwrite) a named secret owned by the calling agent.",
    "secret_get": "Read the plaintext value of a secret you own or were granted read access to.",
    "secret_list": "List metadata for secrets you own or that are shared with you. Never returns values.",
    "secret_delete": "Delete a secret you own. Cascades share grants. Idempotent.",
}


def _get_tools_list() -> list[dict]:
    """Authenticate via JSON-RPC tools/list and return the tools array."""
    import mcp_server.main as _main_mod
    import mcp_server.tools.jsonrpc as _jsonrpc_mod
    _orig_main = _main_mod.validate_agent_key
    _orig_jrpc = _jsonrpc_mod.validate_agent_key

    async def _fake(key):
        return {"agent_id": "test-agent-id", "tenant_id": "00000000-0000-0000-0000-000000000001"}, None

    _main_mod.validate_agent_key = _fake
    _jsonrpc_mod.validate_agent_key = _fake
    try:
        from mcp_server.main import create_app
        from httpx import AsyncClient, ASGITransport
        app = create_app()

        async def _run():
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                return await client.post(
                    "/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                    headers={"Authorization": "Bearer mk_agent_testkey"},
                )

        resp = asyncio.run(_run())
    finally:
        _main_mod.validate_agent_key = _orig_main
        _jsonrpc_mod.validate_agent_key = _orig_jrpc

    assert resp.status_code == 200
    return resp.json()["result"]["tools"]


def test_tools_list_no_titles() -> None:
    """Every entry in tools/list must have no 'title' key (FR-14, AC-6)."""
    tools = _get_tools_list()
    assert tools, "tools/list returned empty list"
    titled = [t["name"] for t in tools if "title" in t]
    assert not titled, f"These tools still have 'title': {titled}"


def test_secret_descriptions_trimmed() -> None:
    """The four secret tools have the exact trimmed descriptions (FR-10–FR-13, AC-6)."""
    tools = _get_tools_list()
    by_name = {t["name"]: t for t in tools}
    for tool_name, expected_desc in _SECRET_DESCRIPTIONS.items():
        assert tool_name in by_name, f"Tool {tool_name!r} missing from tools/list"
        actual = by_name[tool_name]["description"]
        assert actual == expected_desc, (
            f"Description mismatch for {tool_name!r}:\n"
            f"  expected: {expected_desc!r}\n"
            f"  actual:   {actual!r}"
        )
