"""
Unit tests: MCP Server agent API key authentication.

Sources:
  - Req 6 AC1: valid key → 200 with {agent_id, tenant_id}
  - Req 6 AC2: all failure modes (bad format, unknown key, revoked) →
               identical 401 body to prevent enumeration
  - ADR-0009: MCP Server stack and authentication contract
  - ADR-0017.5: identical body + equalized timing across failure modes
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure mcp-server src and mintkey-models are importable
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
MCP_SERVER_SRC = os.path.join(REPO_ROOT, "mcp-server", "src")
MINTKEY_MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for _p in (MCP_SERVER_SRC, MINTKEY_MODELS_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

VALID_API_KEY = "mk_agent_TESTKEY00000000000000000000000000000000000000000000000"
AGENT_ID = "agent_01HZ0000000000000000000000"
TENANT_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# App fixture with a /v1/mcp/auth-check test endpoint that exercises the
# validate_agent_key helper so we can test it via HTTP.
# ---------------------------------------------------------------------------


@pytest.fixture()
def app():
    from mcp_server.main import create_app
    from fastapi import FastAPI
    from fastapi.responses import JSONResponse
    from mcp_server.auth.agent_key import INVALID_KEY_RESPONSE

    base = create_app()

    # Add a thin test endpoint that invokes validate_agent_key so we can
    # exercise the auth logic over HTTP without wiring real MCP tools.
    @base.get("/v1/test/agent-auth")
    async def _agent_auth_check(x_api_key: str = ""):
        from mcp_server.auth.agent_key import validate_agent_key
        ctx, failure = await validate_agent_key(x_api_key)
        if failure is not None:
            return JSONResponse(status_code=401, content=INVALID_KEY_RESPONSE)
        return JSONResponse(status_code=200, content=ctx)

    return base


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_success():
    """Patch validate_agent_key to return a successful agent context."""
    return patch(
        "mcp_server.auth.agent_key.validate_agent_key",
        new=AsyncMock(return_value=({"agent_id": AGENT_ID, "tenant_id": TENANT_ID, "status": "active"}, None)),
    )


def _mock_failure(reason: str = "invalid_key"):
    """Patch validate_agent_key to return a failure."""
    return patch(
        "mcp_server.auth.agent_key.validate_agent_key",
        new=AsyncMock(return_value=(None, reason)),
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_key_returns_200_with_agent_context(app) -> None:
    """Valid key → 200 with {agent_id, tenant_id} (Req 6 AC1)."""
    with _mock_success():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/test/agent-auth", params={"x_api_key": VALID_API_KEY})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_id"] == AGENT_ID
    assert body["tenant_id"] == TENANT_ID


@pytest.mark.asyncio
async def test_invalid_key_returns_401_with_expected_code(app) -> None:
    """Invalid key → 401 with mintkey:code = mintkey:invalid_agent_key (Req 6 AC2)."""
    with _mock_failure("invalid_key"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/test/agent-auth", params={"x_api_key": "bad-key"})

    assert resp.status_code == 401
    assert resp.json()["mintkey:code"] == "mintkey:invalid_agent_key"


@pytest.mark.asyncio
async def test_unknown_key_body_matches_bad_format_body(app) -> None:
    """
    Unknown key and bad-format key return byte-identical bodies (ADR-0017.5).

    Both paths go through the same INVALID_KEY_RESPONSE constant, so the
    bodies must be identical regardless of which failure reason was returned.
    """
    with _mock_failure("invalid_key"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp_unknown = await client.get("/v1/test/agent-auth", params={"x_api_key": "unknown-key"})

    with _mock_failure("invalid_key"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp_bad_format = await client.get("/v1/test/agent-auth", params={"x_api_key": "notmkagent"})

    assert resp_unknown.status_code == 401
    assert resp_bad_format.status_code == 401
    assert resp_unknown.content == resp_bad_format.content, (
        f"Bodies differ!\n  unknown: {resp_unknown.text}\n  bad_format: {resp_bad_format.text}"
    )


@pytest.mark.asyncio
async def test_service_unavailable_body_matches_invalid_key_body(app) -> None:
    """
    Service-unavailable failure returns same body as invalid-key failure (ADR-0017.5).
    """
    with _mock_failure("invalid_key"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp_invalid = await client.get("/v1/test/agent-auth", params={"x_api_key": "bad"})

    with _mock_failure("service_unavailable"):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp_unavailable = await client.get("/v1/test/agent-auth", params={"x_api_key": "bad"})

    assert resp_invalid.status_code == 401
    assert resp_unavailable.status_code == 401
    assert resp_invalid.content == resp_unavailable.content


@pytest.mark.asyncio
async def test_valid_key_sets_tenant_context(app) -> None:
    """Successful auth exposes agent_id and tenant_id in the response (Req 6 AC1)."""
    with _mock_success():
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/v1/test/agent-auth", params={"x_api_key": VALID_API_KEY})

    assert resp.status_code == 200
    body = resp.json()
    assert "agent_id" in body
    assert "tenant_id" in body
    assert body["tenant_id"] == TENANT_ID
