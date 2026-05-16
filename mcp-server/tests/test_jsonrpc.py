"""
MCP-D-BE: Full coverage tests for the JSON-RPC dispatcher.

Tests are organised into sections:

  A. initialize handshake (unauthenticated)
  B. notifications/initialized (unauthenticated, returns 202)
  C. tools/list (requires auth)
  D. tools/call dispatch (requires auth; loopback mocked via respx / httpx)
  E. Auth enforcement
  F. Error envelopes (bad method, bad parse, non-JSON-RPC body)
  G. Route aliases (/ and /v1/mcp behave identically to /mcp)
  H. Regressions (existing REST endpoints unaffected)

All tests are unit tests — no Docker, no DB.

Source: MCP-DISCOVER-DESIGN Section 6 MCP-D-BE; MCP spec 2025-06-18.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TEST_AGENT_ID = str(uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
_TEST_TENANT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_FAKE_KEY = "mk_agent_testjsonrpc"

_FAKE_CTX = {
    "agent_id": _TEST_AGENT_ID,
    "tenant_id": _TEST_TENANT_ID,
    "name": "test-agent",
    "status": "active",
}

_INIT_PARAMS = {
    "protocolVersion": "2025-06-18",
    "capabilities": {},
    "clientInfo": {"name": "test", "version": "0"},
}

# ---------------------------------------------------------------------------
# ASGI harness
# ---------------------------------------------------------------------------


def _make_app(validate_fn=None):
    """
    Build a fresh app with:
    - validate_agent_key replaced by `validate_fn` (or a noop if None)
    - get_db_session overridden with a lightweight AsyncMock
    """
    import mcp_server.main as _main_mod
    import mcp_server.tools.jsonrpc as _jsonrpc_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.main import create_app

    async def _default_validate(key):
        if key == _FAKE_KEY:
            return _FAKE_CTX, None
        return None, "invalid_key"

    _vfn = validate_fn or _default_validate

    # Patch in both locations so both the middleware and the dispatcher agree.
    _orig_main = _main_mod.validate_agent_key
    _orig_jsonrpc = _jsonrpc_mod.validate_agent_key
    _main_mod.validate_agent_key = _vfn
    _jsonrpc_mod.validate_agent_key = _vfn

    app = create_app()

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []
        result_mock.fetchone.return_value = None
        session.execute = AsyncMock(return_value=result_mock)
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session

    return app, (_orig_main, _orig_jsonrpc), (_main_mod, _jsonrpc_mod)


def _restore(originals, mods):
    orig_main, orig_jsonrpc = originals
    main_mod, jsonrpc_mod = mods
    main_mod.validate_agent_key = orig_main
    jsonrpc_mod.validate_agent_key = orig_jsonrpc


def _post(path: str, body: dict, headers: dict | None = None, validate_fn=None):
    """Send a single POST through the ASGI stack; return the httpx.Response."""
    app, originals, mods = _make_app(validate_fn)
    try:
        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    path,
                    content=json.dumps(body),
                    headers={"Content-Type": "application/json", **(headers or {})},
                )
        return asyncio.run(_run())
    finally:
        _restore(originals, mods)


def _post_raw(path: str, raw: str, headers: dict | None = None, validate_fn=None):
    """Send a raw-body POST (for testing invalid JSON)."""
    app, originals, mods = _make_app(validate_fn)
    try:
        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    path,
                    content=raw,
                    headers={"Content-Type": "application/json", **(headers or {})},
                )
        return asyncio.run(_run())
    finally:
        _restore(originals, mods)


def _get(path: str, validate_fn=None):
    """Send a single GET through the ASGI stack."""
    app, originals, mods = _make_app(validate_fn)
    try:
        async def _run():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(path)
        return asyncio.run(_run())
    finally:
        _restore(originals, mods)


# ===========================================================================
# A. initialize handshake (unauthenticated)
# ===========================================================================


def test_initialize_http_status():
    """initialize → HTTP 200."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS})
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"


def test_initialize_jsonrpc_envelope():
    """initialize response must be a JSON-RPC 2.0 envelope with id."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "id": 42, "method": "initialize", "params": _INIT_PARAMS})
    body = resp.json()
    assert body.get("jsonrpc") == "2.0"
    assert body.get("id") == 42
    assert "result" in body, f"No 'result' in envelope: {body}"


def test_initialize_protocol_version():
    """initialize result.protocolVersion must be 2025-06-18."""
    body = _post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS}).json()
    assert body["result"]["protocolVersion"] == "2025-06-18"


def test_initialize_server_info_name():
    """initialize result.serverInfo.name must be mintkey-mcp-server."""
    body = _post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS}).json()
    assert body["result"]["serverInfo"]["name"] == "mintkey-mcp-server"


def test_initialize_capabilities_tools():
    """initialize result.capabilities.tools must be present."""
    body = _post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS}).json()
    caps = body["result"]["capabilities"]
    assert "tools" in caps, f"Missing 'tools' in capabilities: {caps}"
    assert caps["tools"] == {"listChanged": False}


def test_initialize_instructions_present_and_long():
    """initialize result.instructions must be a non-empty string (>100 chars)."""
    body = _post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS}).json()
    instructions = body["result"].get("instructions", "")
    assert isinstance(instructions, str) and len(instructions) > 100, (
        f"instructions too short or missing: {instructions!r}"
    )


def test_initialize_unauthenticated():
    """initialize must work without any auth header."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS})
    body = resp.json()
    assert "result" in body, f"Expected result but got: {body}"
    assert "error" not in body


def test_initialize_experimental_rest_endpoints():
    """initialize capabilities.experimental must contain mintkey.rest_endpoints."""
    body = _post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS}).json()
    exp = body["result"]["capabilities"].get("experimental", {})
    assert "mintkey.rest_endpoints" in exp, f"Missing mintkey.rest_endpoints: {exp}"


# ===========================================================================
# B. notifications/initialized
# ===========================================================================


def test_notifications_initialized_returns_202():
    """notifications/initialized must return HTTP 202 (no id, no body required)."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp.status_code == 202, f"Expected 202, got {resp.status_code}: {resp.text}"


def test_notifications_initialized_no_body():
    """notifications/initialized HTTP 202 response has no meaningful body to parse."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})
    # body may be empty or minimal — the key assertion is the status code
    assert resp.status_code == 202


def test_notifications_initialized_unauthenticated():
    """notifications/initialized must work without auth (no auth headers)."""
    resp = _post(
        "/mcp",
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        headers={},  # explicitly no auth
    )
    assert resp.status_code == 202


# ===========================================================================
# C. tools/list (requires auth)
# ===========================================================================


def test_tools_list_without_auth_returns_jsonrpc_error():
    """tools/list without auth must return JSON-RPC error code -32001."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
    assert resp.status_code == 200  # JSON-RPC always 200
    body = resp.json()
    assert "error" in body, f"Expected error envelope: {body}"
    assert body["error"]["code"] == -32001


def test_tools_list_with_auth_returns_tools():
    """tools/list with valid auth must return a list of tools."""
    resp = _post(
        "/mcp",
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    body = resp.json()
    assert "result" in body, f"Expected result, got: {body}"
    tools = body["result"]["tools"]
    assert isinstance(tools, list)
    assert len(tools) == 6


def test_tools_list_count_is_6():
    """tools/list result.tools must contain exactly 6 entries."""
    resp = _post(
        "/mcp",
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    tools = resp.json()["result"]["tools"]
    assert len(tools) == 6, f"Expected 6 tools, got {len(tools)}: {[t['name'] for t in tools]}"


def test_tools_list_all_have_input_schema():
    """Every tool descriptor must include an inputSchema field."""
    resp = _post(
        "/mcp",
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    tools = resp.json()["result"]["tools"]
    for tool in tools:
        assert "inputSchema" in tool, f"Tool {tool['name']!r} missing inputSchema"


def test_tools_list_all_have_name_and_description():
    """Every tool descriptor must include name and description."""
    resp = _post(
        "/mcp",
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    tools = resp.json()["result"]["tools"]
    for tool in tools:
        assert tool.get("name"), f"Tool missing name: {tool}"
        assert tool.get("description"), f"Tool {tool.get('name')!r} missing description"


def test_tools_list_tool_names():
    """tools/list must contain all 6 expected tool names."""
    resp = _post(
        "/mcp",
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    names = {t["name"] for t in resp.json()["result"]["tools"]}
    expected = {
        "mintkey_bootstrap",
        "mintkey_list_services",
        "mintkey_discover",
        "mintkey_describe_service",
        "mintkey_get_openapi",
        "mintkey_request_token",
    }
    assert names == expected, f"Tool name mismatch. Got: {names}"


def test_tools_list_xapikey_auth():
    """tools/list must accept X-API-Key header as well as Bearer."""
    resp = _post(
        "/mcp",
        {"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
        headers={"X-API-Key": _FAKE_KEY},
    )
    body = resp.json()
    assert "result" in body, f"X-API-Key not accepted by tools/list: {body}"
    assert "tools" in body["result"]


# ===========================================================================
# D. tools/call (requires auth; loopback is tested via ASGI in-process)
# ===========================================================================


def test_tools_call_without_auth_returns_error():
    """tools/call without auth must return JSON-RPC error code -32001."""
    resp = _post(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "tools/call",
            "params": {"name": "mintkey_bootstrap", "arguments": {}},
        },
    )
    body = resp.json()
    assert "error" in body, f"Expected error, got: {body}"
    assert body["error"]["code"] == -32001


def test_tools_call_bootstrap_no_auth_needed_at_loopback():
    """
    tools/call mintkey_bootstrap with valid auth must return a result.
    The bootstrap handler is unauthenticated at the REST level — the loopback
    call succeeds without forwarding auth to the upstream route.
    """
    resp = _post(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "tools/call",
            "params": {"name": "mintkey_bootstrap", "arguments": {}},
        },
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    body = resp.json()
    assert "result" in body, f"Expected result, got: {body}"
    result = body["result"]
    assert "content" in result, f"Missing content in result: {result}"
    assert isinstance(result["content"], list) and len(result["content"]) > 0
    assert result.get("isError") is not True


def test_tools_call_unknown_tool_returns_jsonrpc_error():
    """tools/call with an unknown tool name must return JSON-RPC error -32601."""
    resp = _post(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "tools/call",
            "params": {"name": "mintkey_does_not_exist", "arguments": {}},
        },
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    body = resp.json()
    assert "error" in body, f"Expected error, got: {body}"
    assert body["error"]["code"] == -32601


def test_tools_call_missing_name_returns_invalid_params():
    """tools/call without 'name' must return JSON-RPC error -32602."""
    resp = _post(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 7,
            "method": "tools/call",
            "params": {"arguments": {}},
        },
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    body = resp.json()
    assert "error" in body, f"Expected error, got: {body}"
    assert body["error"]["code"] == -32602


def test_tools_call_describe_service_missing_service_id():
    """
    mintkey_describe_service without service_id argument must return a tool result
    with isError=True (tool-level error, NOT a JSON-RPC protocol error).
    """
    resp = _post(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 8,
            "method": "tools/call",
            "params": {"name": "mintkey_describe_service", "arguments": {}},
        },
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    body = resp.json()
    assert "result" in body, f"Expected result with isError, got: {body}"
    assert body["result"].get("isError") is True


def test_tools_call_list_services_with_auth():
    """
    tools/call mintkey_list_services with valid auth must return a result
    (empty service list is fine — we use a mock DB).
    """
    resp = _post(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 9,
            "method": "tools/call",
            "params": {"name": "mintkey_list_services", "arguments": {}},
        },
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    body = resp.json()
    assert "result" in body, f"Expected result, got: {body}"
    assert "content" in body["result"]


def test_tools_call_discover_with_auth():
    """
    tools/call mintkey_discover with valid auth must return a result.
    """
    resp = _post(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 10,
            "method": "tools/call",
            "params": {"name": "mintkey_discover", "arguments": {}},
        },
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    body = resp.json()
    assert "result" in body, f"Expected result, got: {body}"
    assert "content" in body["result"]


def test_tools_call_result_content_is_text():
    """tools/call result.content[0].type must be 'text'."""
    resp = _post(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 11,
            "method": "tools/call",
            "params": {"name": "mintkey_bootstrap", "arguments": {}},
        },
        headers={"Authorization": f"Bearer {_FAKE_KEY}"},
    )
    content = resp.json()["result"]["content"]
    assert content[0]["type"] == "text", f"Expected type=text, got: {content[0]}"
    assert isinstance(content[0]["text"], str) and content[0]["text"]


# ===========================================================================
# E. Auth enforcement
# ===========================================================================


def test_tools_list_invalid_key_returns_error():
    """tools/list with a bad key must return -32001, not a 200 with results."""
    async def _bad_validate(key):
        return None, "invalid_key"

    resp = _post(
        "/mcp",
        {"jsonrpc": "2.0", "id": 12, "method": "tools/list"},
        headers={"Authorization": "Bearer mk_agent_badkey"},
        validate_fn=_bad_validate,
    )
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32001


def test_tools_call_invalid_key_returns_error():
    """tools/call with a bad key must return -32001."""
    async def _bad_validate(key):
        return None, "invalid_key"

    resp = _post(
        "/mcp",
        {
            "jsonrpc": "2.0",
            "id": 13,
            "method": "tools/call",
            "params": {"name": "mintkey_bootstrap", "arguments": {}},
        },
        headers={"Authorization": "Bearer mk_agent_badkey"},
        validate_fn=_bad_validate,
    )
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32001


def test_initialize_works_without_any_auth():
    """initialize must never require auth."""
    async def _reject_all(key):
        return None, "invalid_key"

    resp = _post(
        "/mcp",
        {"jsonrpc": "2.0", "id": 99, "method": "initialize", "params": _INIT_PARAMS},
        validate_fn=_reject_all,
    )
    body = resp.json()
    assert "result" in body, f"initialize should not fail auth: {body}"


# ===========================================================================
# F. Error envelopes
# ===========================================================================


def test_invalid_json_returns_parse_error():
    """Completely invalid JSON must return JSON-RPC error -32700."""
    resp = _post_raw("/mcp", "{this is not json}")
    assert resp.status_code == 200  # JSON-RPC always 200
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32700


def test_non_jsonrpc_body_returns_400():
    """A JSON body without jsonrpc/method fields must return HTTP 400."""
    resp = _post("/mcp", {"foo": "bar"})
    assert resp.status_code == 400, f"Expected 400, got {resp.status_code}"
    body = resp.json()
    assert body.get("error") == "not_jsonrpc"
    assert "hint" in body


def test_missing_method_returns_400():
    """A JSON body with jsonrpc=2.0 but no method must return HTTP 400."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "id": 1})
    assert resp.status_code == 400


def test_unknown_method_returns_32601():
    """An unknown method name must return JSON-RPC error -32601."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "id": 99, "method": "random/nonexistent"})
    body = resp.json()
    assert "error" in body
    assert body["error"]["code"] == -32601


def test_unknown_method_error_includes_hint():
    """The -32601 error for unknown methods must include a 'data' hint."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "id": 99, "method": "some/unknown"})
    error = resp.json()["error"]
    assert "data" in error, f"Expected data hint in error: {error}"


def test_jsonrpc_error_has_id():
    """JSON-RPC error envelopes must echo the request id."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "id": 77, "method": "nope"})
    assert resp.json().get("id") == 77


def test_jsonrpc_error_content_type():
    """All JSON-RPC responses must set Content-Type: application/json."""
    resp = _post("/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS})
    assert "application/json" in resp.headers.get("content-type", "")


# ===========================================================================
# G. Route aliases
# ===========================================================================


def test_post_root_initialize():
    """POST / must handle initialize identically to POST /mcp."""
    resp = _post("/", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS})
    body = resp.json()
    assert body["result"]["serverInfo"]["name"] == "mintkey-mcp-server"


def test_post_v1_mcp_initialize():
    """POST /v1/mcp must handle initialize identically to POST /mcp."""
    resp = _post("/v1/mcp", {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": _INIT_PARAMS})
    body = resp.json()
    assert body["result"]["serverInfo"]["name"] == "mintkey-mcp-server"


def test_post_root_notifications():
    """POST / notifications/initialized → 202."""
    resp = _post("/", {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp.status_code == 202


def test_post_v1_mcp_notifications():
    """POST /v1/mcp notifications/initialized → 202."""
    resp = _post("/v1/mcp", {"jsonrpc": "2.0", "method": "notifications/initialized"})
    assert resp.status_code == 202


# ===========================================================================
# H. Regressions — existing REST endpoints must not be broken
# ===========================================================================


def test_health_still_200():
    """GET /health must return 200 (regression)."""
    resp = _get("/health")
    assert resp.status_code == 200
    assert resp.json().get("status") == "ok"


def test_bootstrap_endpoint_still_200():
    """GET /v1/tools/bootstrap must still return 200 with skill_markdown and version (regression)."""
    resp = _get("/v1/tools/bootstrap")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "skill_markdown" in body
    assert "version" in body


def test_list_services_without_auth_still_401():
    """GET /v1/tools/list_services without auth must still return 401 (regression)."""
    resp = _get("/v1/tools/list_services")
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}"


def test_get_mcp_still_landing():
    """GET /mcp must still return the landing JSON from MCP-D-A (not a 405)."""
    resp = _get("/mcp")
    assert resp.status_code == 200, f"Expected 200 from GET /mcp, got {resp.status_code}"
    body = resp.json()
    assert body.get("service") == "mintkey-mcp-server", f"Unexpected GET /mcp body: {body}"


def test_get_v1_mcp_still_landing():
    """GET /v1/mcp must still return the landing JSON from MCP-D-A."""
    resp = _get("/v1/mcp")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("service") == "mintkey-mcp-server"


def test_get_root_still_landing():
    """GET / must still return the landing JSON from MCP-D-A."""
    resp = _get("/")
    assert resp.status_code == 200
    body = resp.json()
    assert body.get("service") == "mintkey-mcp-server"
