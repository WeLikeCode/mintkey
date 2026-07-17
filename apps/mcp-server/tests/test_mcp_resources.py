"""
T-B tests — MCP resources/list + resources/read (FR-7, AC-5).

Tests that:
- resources/list returns the agent-bootstrap resource with correct URI.
- resources/read of that URI returns the full skill markdown.
- The 5 new guide resources are present in resources/list.
- resources/read of each guide URI returns non-empty markdown with required keywords.
- resources/read of an unknown URI returns JSON-RPC error -32602.

Resources are unauthenticated (consistent with GET /v1/tools/bootstrap bypass).
Source: .kiro/specs/mcp-token-optimization/ FR-7, AC-5.
"""
from __future__ import annotations

import asyncio


_RESOURCE_URI = "mintkey://skill/agent-bootstrap"

_GUIDE_REQUIRED_KEYWORDS: dict[str, list[str]] = {
    "mintkey://guides/rest-api": ["mintkey_request_token", "proxy"],
    "mintkey://guides/ssh": ["bastion", "2222"],
    "mintkey://guides/secrets": ["secret_put", "operator"],
    "mintkey://guides/email": ["email_list_mailboxes", "email-proxy"],
    "mintkey://quick-reference": ["svc_"],
}


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
    """resources/list includes the bootstrap URI + 5 guide URIs; resources/read returns each."""
    app, _orig, _ak = _make_app()
    try:
        # --- resources/list ---
        list_resp = _jsonrpc(app, "resources/list")
        resources = list_resp["result"]["resources"]
        uris = [r["uri"] for r in resources]
        assert _RESOURCE_URI in uris, f"Expected {_RESOURCE_URI!r} in resources/list: {uris}"
        bootstrap_resource = next(r for r in resources if r["uri"] == _RESOURCE_URI)
        assert bootstrap_resource["mimeType"] == "text/markdown"

        # All 5 new guide URIs must be present.
        for guide_uri in _GUIDE_REQUIRED_KEYWORDS:
            assert guide_uri in uris, f"Expected guide URI {guide_uri!r} in resources/list: {uris}"
            guide_resource = next(r for r in resources if r["uri"] == guide_uri)
            assert guide_resource["mimeType"] == "text/markdown", (
                f"Guide {guide_uri!r} must have mimeType text/markdown"
            )

        # --- resources/read (valid bootstrap URI) ---
        read_resp = _jsonrpc(app, "resources/read", {"uri": _RESOURCE_URI})
        contents = read_resp["result"]["contents"]
        assert contents, "resources/read should return non-empty contents"
        item = contents[0]
        assert item["uri"] == _RESOURCE_URI
        assert item["mimeType"] == "text/markdown"
        assert len(item["text"]) > 1000, "Full skill markdown should be non-trivial"
        assert "<authentication>" in item["text"], "Full markdown must contain <authentication>"

        # --- resources/read of each guide URI — check required keywords ---
        for guide_uri, keywords in _GUIDE_REQUIRED_KEYWORDS.items():
            guide_read = _jsonrpc(app, "resources/read", {"uri": guide_uri})
            guide_contents = guide_read["result"]["contents"]
            assert guide_contents, f"resources/read {guide_uri!r} returned no contents"
            guide_text = guide_contents[0]["text"]
            assert len(guide_text) > 200, f"Guide {guide_uri!r} must be non-trivial"
            for kw in keywords:
                assert kw in guide_text, (
                    f"Guide {guide_uri!r} must contain keyword {kw!r}"
                )

        # --- resources/read (unknown URI) ---
        err_resp = _jsonrpc(app, "resources/read", {"uri": "mintkey://unknown/resource"})
        assert "error" in err_resp, f"Unknown URI should return error: {err_resp}"
        assert err_resp["error"]["code"] == -32602
    finally:
        _ak.validate_agent_key = _orig
