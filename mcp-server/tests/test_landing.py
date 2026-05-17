"""
MCP-D-A landing page tests.

Verifies that GET /, /v1, /mcp, /v1/mcp, /v1/tools all return 200 JSON with
the expected structure.  Also includes regression tests for existing endpoints
that must not be broken by the new router.

All tests are unit tests — they use the ASGI test client; no docker required.

Source: MCP-DISCOVER-DESIGN Section 6 MCP-D-A.
"""
from __future__ import annotations

import asyncio
from urllib.parse import urlparse

import pytest
from httpx import ASGITransport, AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app():
    """
    Build a fresh app instance with validate_agent_key stubbed out so unit
    tests do not attempt real HTTP calls to admin-api.
    """
    import mcp_server.auth.agent_key as _ak

    async def _noop(key):
        return None, "no_key"

    _ak.validate_agent_key = _noop

    # Force a fresh create_app() so module-level state from other test modules
    # does not interfere.
    from mcp_server.main import create_app
    return create_app()


def _get(path: str):
    """Synchronous helper: send GET <path> against the ASGI app, return Response."""
    app = _make_app()

    async def _run():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(path)

    return asyncio.run(_run())


# ---------------------------------------------------------------------------
# Landing page — status codes
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", ["/", "/v1", "/mcp", "/v1/mcp", "/v1/tools"])
def test_landing_returns_200(path: str) -> None:
    """All five landing paths must return HTTP 200."""
    resp = _get(path)
    assert resp.status_code == 200, (
        f"Expected 200 from {path}, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.parametrize("path", ["/", "/v1", "/mcp", "/v1/mcp", "/v1/tools"])
def test_landing_content_type_json(path: str) -> None:
    """All landing pages must set Content-Type: application/json."""
    resp = _get(path)
    assert "application/json" in resp.headers.get("content-type", ""), (
        f"Expected application/json content-type from {path}, got: {resp.headers.get('content-type')}"
    )


# ---------------------------------------------------------------------------
# Root landing (GET /)
# ---------------------------------------------------------------------------

def test_root_service_field() -> None:
    """GET / must contain service=mintkey-mcp-server."""
    body = _get("/").json()
    assert body.get("service") == "mintkey-mcp-server", (
        f"Unexpected service field: {body.get('service')!r}"
    )


def test_root_protocol_version() -> None:
    """GET / must declare protocolVersion=2025-06-18."""
    body = _get("/").json()
    assert body.get("protocolVersion") == "2025-06-18", (
        f"Unexpected protocolVersion: {body.get('protocolVersion')!r}"
    )


def test_root_mcp_jsonrpc_endpoint() -> None:
    """GET / must point mcp_jsonrpc.url at /mcp."""
    body = _get("/").json()
    url = body["endpoints"]["mcp_jsonrpc"]["url"]
    assert url == "/mcp", f"Expected /mcp, got {url!r}"


def test_root_bootstrap_path() -> None:
    """GET / must list bootstrap path as /v1/tools/bootstrap with auth=none."""
    body = _get("/").json()
    entry = body["endpoints"]["rest"]["bootstrap"]
    assert entry["path"] == "/v1/tools/bootstrap", f"Unexpected path: {entry['path']!r}"
    assert entry["auth"] == "none", f"Unexpected auth: {entry['auth']!r}"


def test_root_auth_schemes() -> None:
    """GET / must list bearer and api_key auth schemes."""
    body = _get("/").json()
    schemes = body["auth"]["schemes"]
    assert "bearer" in schemes, f"Missing bearer in schemes: {schemes}"
    assert "api_key" in schemes, f"Missing api_key in schemes: {schemes}"


def test_root_hint_present() -> None:
    """GET / must include a hint field."""
    body = _get("/").json()
    assert "hint" in body and body["hint"], "Missing or empty hint field in /"


# ---------------------------------------------------------------------------
# /v1 landing
# ---------------------------------------------------------------------------

def test_v1_service_field() -> None:
    """GET /v1 must contain service=mintkey-mcp-server."""
    body = _get("/v1").json()
    assert body.get("service") == "mintkey-mcp-server"


def test_v1_mcp_alias_note() -> None:
    """GET /v1 mcp_jsonrpc.note must mention /v1/mcp alias."""
    body = _get("/v1").json()
    note = body["endpoints"]["mcp_jsonrpc"]["note"]
    assert "/v1/mcp" in note, f"Expected /v1/mcp alias mentioned in /v1 note, got: {note!r}"


def test_v1_rest_endpoints_present() -> None:
    """GET /v1 must list all 7 REST tool entries."""
    body = _get("/v1").json()
    rest = body["endpoints"]["rest"]
    expected = {
        "bootstrap", "instructions", "list_services", "discover",
        "describe_service", "get_openapi", "request_token",
    }
    assert set(rest.keys()) == expected, (
        f"REST endpoints mismatch in /v1. Got: {set(rest.keys())}"
    )


# ---------------------------------------------------------------------------
# /mcp landing
# ---------------------------------------------------------------------------

def test_mcp_jsonrpc_note_present() -> None:
    """GET /mcp must include jsonrpc_note field."""
    body = _get("/mcp").json()
    assert "jsonrpc_note" in body["endpoints"]["mcp_jsonrpc"], (
        "Expected jsonrpc_note key in /mcp mcp_jsonrpc endpoint"
    )


def _note_references_host(note: str, expected_host: str) -> bool:
    """Return True if *note* contains a URL whose hostname matches expected_host exactly."""
    for token in note.split():
        try:
            parsed = urlparse(token)
            if parsed.hostname == expected_host:
                return True
        except ValueError:
            pass
    return False


def test_mcp_jsonrpc_note_contains_spec_url() -> None:
    """GET /mcp jsonrpc_note must reference the MCP spec URL."""
    body = _get("/mcp").json()
    note = body["endpoints"]["mcp_jsonrpc"]["jsonrpc_note"]
    assert _note_references_host(note, "modelcontextprotocol.io"), (
        f"Expected spec URL with host modelcontextprotocol.io in jsonrpc_note, got: {note!r}"
    )


def test_mcp_service_field() -> None:
    """GET /mcp must contain service=mintkey-mcp-server."""
    body = _get("/mcp").json()
    assert body.get("service") == "mintkey-mcp-server"


# ---------------------------------------------------------------------------
# /v1/mcp landing (alias for /mcp)
# ---------------------------------------------------------------------------

def test_v1_mcp_identical_to_mcp() -> None:
    """GET /v1/mcp must return the same body as GET /mcp."""
    mcp_body = _get("/mcp").json()
    v1_mcp_body = _get("/v1/mcp").json()
    assert mcp_body == v1_mcp_body, (
        "GET /v1/mcp and GET /mcp must return identical bodies"
    )


# ---------------------------------------------------------------------------
# /v1/tools landing (tool index)
# ---------------------------------------------------------------------------

def test_tools_index_top_level_key() -> None:
    """GET /v1/tools must have a top-level 'tools' key."""
    body = _get("/v1/tools").json()
    assert "tools" in body, f"Missing 'tools' key. Got keys: {list(body.keys())}"


def test_tools_index_all_seven_tools() -> None:
    """GET /v1/tools must list exactly 7 tool entries."""
    body = _get("/v1/tools").json()
    tools = body["tools"]
    expected = {
        "bootstrap", "instructions", "list_services", "discover",
        "describe_service", "get_openapi", "request_token",
    }
    assert set(tools.keys()) == expected, (
        f"Tool index keys mismatch. Got: {set(tools.keys())}"
    )


def test_tools_index_unauth_entries() -> None:
    """bootstrap and instructions must have auth=none in /v1/tools."""
    body = _get("/v1/tools").json()
    tools = body["tools"]
    assert tools["bootstrap"]["auth"] == "none"
    assert tools["instructions"]["auth"] == "none"


def test_tools_index_bearer_entries() -> None:
    """Authenticated tools must declare auth=bearer in /v1/tools."""
    body = _get("/v1/tools").json()
    tools = body["tools"]
    for name in ("list_services", "discover", "describe_service", "get_openapi", "request_token"):
        assert tools[name]["auth"] == "bearer", (
            f"Expected bearer auth for {name}, got: {tools[name]['auth']!r}"
        )


def test_tools_index_descriptions_present() -> None:
    """Every tool entry in /v1/tools must have a non-empty description."""
    body = _get("/v1/tools").json()
    for name, entry in body["tools"].items():
        assert entry.get("description"), (
            f"Missing or empty description for tool {name!r}"
        )


# ---------------------------------------------------------------------------
# Regression: existing endpoints must not be broken
# ---------------------------------------------------------------------------

def test_health_still_200() -> None:
    """GET /health must return 200 with status=ok (regression)."""
    resp = _get("/health")
    assert resp.status_code == 200, f"Expected 200 from /health, got {resp.status_code}"
    body = resp.json()
    assert body.get("status") == "ok", f"Unexpected health body: {body}"


def test_bootstrap_endpoint_still_200() -> None:
    """GET /v1/tools/bootstrap must still return 200 (regression)."""
    resp = _get("/v1/tools/bootstrap")
    assert resp.status_code == 200, (
        f"Expected 200 from /v1/tools/bootstrap, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "skill_markdown" in body, f"Missing skill_markdown in bootstrap body: {list(body.keys())}"
    assert "version" in body, f"Missing version in bootstrap body: {list(body.keys())}"


def test_list_services_without_auth_returns_401() -> None:
    """GET /v1/tools/list_services without auth must return 401 (regression)."""
    resp = _get("/v1/tools/list_services")
    assert resp.status_code == 401, (
        f"Expected 401 from /v1/tools/list_services (no auth), got {resp.status_code}: {resp.text}"
    )


def test_unknown_path_returns_404() -> None:
    """GET /v1/asdf must return 404 (regression — landing pages must not swallow 404s)."""
    resp = _get("/v1/asdf")
    assert resp.status_code == 404, (
        f"Expected 404 from /v1/asdf, got {resp.status_code}: {resp.text}"
    )
