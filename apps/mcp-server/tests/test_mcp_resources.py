"""
T-B tests — MCP resources/list + resources/read (FR-7, AC-5).

Tests that:
- resources/list returns the agent-bootstrap resource with correct URI.
- resources/read of that URI returns the full skill markdown.
- resources/read of an unknown URI returns JSON-RPC error -32602.

Resources are unauthenticated (consistent with GET /v1/tools/bootstrap bypass).
Source: .kiro/specs/mcp-token-optimization/ FR-7, AC-5.
"""
from __future__ import annotations

import asyncio


_RESOURCE_URI = "mintkey://skill/agent-bootstrap"


def _jsonrpc(app, method: str, params: dict | None = None) -> dict:
    """Send a JSON-RPC request to /mcp and return the parsed response body."""
    from httpx import AsyncClient, ASGITransport

    async def _run():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            return await client.post(
                "/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": method,
                    "params": params or {},
                },
            )

    resp = asyncio.run(_run())
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    return resp.json()


def _make_app():
    import mcp_server.auth.agent_key as _ak

    async def _noop(key):
        return None, "no_key"

    _orig = _ak.validate_agent_key
    _ak.validate_agent_key = _noop
    from mcp_server.main import create_app
    app = create_app()
    return app, _orig, _ak


def test_resources_list_and_read() -> None:
    """resources/list includes the bootstrap URI; resources/read returns full markdown."""
    app, _orig, _ak = _make_app()
    try:
        # --- resources/list ---
        list_resp = _jsonrpc(app, "resources/list")
        resources = list_resp["result"]["resources"]
        uris = [r["uri"] for r in resources]
        assert _RESOURCE_URI in uris, f"Expected {_RESOURCE_URI!r} in resources/list: {uris}"
        bootstrap_resource = next(r for r in resources if r["uri"] == _RESOURCE_URI)
        assert bootstrap_resource["mimeType"] == "text/markdown"

        # --- resources/read (valid URI) ---
        read_resp = _jsonrpc(app, "resources/read", {"uri": _RESOURCE_URI})
        contents = read_resp["result"]["contents"]
        assert contents, "resources/read should return non-empty contents"
        item = contents[0]
        assert item["uri"] == _RESOURCE_URI
        assert item["mimeType"] == "text/markdown"
        assert len(item["text"]) > 1000, "Full skill markdown should be non-trivial"
        assert "<authentication>" in item["text"], "Full markdown must contain <authentication>"

        # --- resources/read (unknown URI) ---
        err_resp = _jsonrpc(app, "resources/read", {"uri": "mintkey://unknown/resource"})
        assert "error" in err_resp, f"Unknown URI should return error: {err_resp}"
        assert err_resp["error"]["code"] == -32602
    finally:
        _ak.validate_agent_key = _orig
