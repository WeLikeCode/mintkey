"""
Unit tests: MCP Server discovery tools (T-1.5.2).

Tests:
  1. list_services returns only services with permission grants for the agent.
  2. list_services returns empty list when the agent has no grants.
  3. describe_service returns full service metadata.
  4. describe_service returns 404 when service not found.
  5. get_openapi returns the OpenAPI URL when present.
  6. get_openapi returns {"openapi_url": null} when no URL is set (not 404).

Sources: Req 6 AC3, AC4; ADR-0008; ADR-0009.
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure mcp-server src and mintkey-models are importable
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
MCP_SERVER_SRC = os.path.join(REPO_ROOT, "mcp-server", "src")
MINTKEY_MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for _p in (MCP_SERVER_SRC, MINTKEY_MODELS_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

AGENT_ID = "agent_01HZ0000000000000000000000"
TENANT_ID = "00000000-0000-0000-0000-000000000001"
AGENT_CTX = {"agent_id": AGENT_ID, "tenant_id": TENANT_ID, "status": "active"}

SVC_ID_1 = str(uuid4())
SVC_ID_2 = str(uuid4())


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_service_row(svc_id: str, name: str, openapi_url=None, description=None):
    """Return a MagicMock that looks like a DB row for a service."""
    row = MagicMock()
    row.id = svc_id
    row.name = name
    row.slug = name.lower().replace(" ", "-")
    row.base_url = f"https://{name.lower()}.example.com"
    row.auth_scheme = "bearer_token"
    row.openapi_url = openapi_url
    row.description = description
    return row


def _mock_session_execute(return_rows):
    """
    Return an AsyncMock session whose execute() yields a result whose
    fetchall() and fetchone() methods return the given rows.
    """
    mock_result = MagicMock()
    mock_result.fetchall.return_value = return_rows
    mock_result.fetchone.return_value = return_rows[0] if return_rows else None

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


# ---------------------------------------------------------------------------
# App fixture with dependency overrides
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_with_overrides():
    """
    Factory that returns (app, override_session_fn).

    Callers pass the fake session they want injected.
    The agent context is always the test AGENT_CTX constant —
    auth is bypassed via dependency_overrides.
    """
    from mcp_server.main import create_app
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context

    def build(mock_session):
        test_app = create_app()

        async def _fake_session():
            yield mock_session

        async def _fake_agent_ctx():
            return AGENT_CTX

        test_app.dependency_overrides[get_db_session] = _fake_session
        test_app.dependency_overrides[get_agent_context] = _fake_agent_ctx
        return test_app

    return build


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_services_returns_only_permitted_services(app_with_overrides) -> None:
    """list_services returns exactly the services with permission grants (Req 6 AC3)."""
    rows = [
        _make_service_row(SVC_ID_1, "openai"),
        _make_service_row(SVC_ID_2, "anthropic"),
    ]
    mock_session = _mock_session_execute(rows)
    test_app = app_with_overrides(mock_session)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/v1/tools/list_services")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "services" in body
    assert len(body["services"]) == 2
    names = {s["name"] for s in body["services"]}
    assert names == {"openai", "anthropic"}


@pytest.mark.asyncio
async def test_list_services_empty_for_no_grants(app_with_overrides) -> None:
    """list_services returns empty list when the agent has no permission grants."""
    mock_session = _mock_session_execute([])
    test_app = app_with_overrides(mock_session)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get("/v1/tools/list_services")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"services": []}


@pytest.mark.asyncio
async def test_describe_service_returns_metadata(app_with_overrides) -> None:
    """describe_service returns id, name, slug, base_url, auth_scheme (Req 6 AC4)."""
    row = _make_service_row(SVC_ID_1, "openai")
    mock_session = _mock_session_execute([row])
    test_app = app_with_overrides(mock_session)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/v1/tools/describe_service/{SVC_ID_1}")

    assert resp.status_code == 200, resp.text
    svc = resp.json()["service"]
    assert svc["id"] == SVC_ID_1
    assert svc["name"] == "openai"
    assert svc["slug"] == "openai"
    assert svc["auth_scheme"] == "bearer_token"
    assert "base_url" in svc


@pytest.mark.asyncio
async def test_describe_service_not_found(app_with_overrides) -> None:
    """describe_service returns 404 when no service with that ID exists."""
    mock_session = _mock_session_execute([])
    test_app = app_with_overrides(mock_session)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/v1/tools/describe_service/{uuid4()}")

    assert resp.status_code == 404, resp.text
    assert resp.json()["code"] == "mintkey:not_found"


@pytest.mark.asyncio
async def test_get_openapi_returns_url(app_with_overrides) -> None:
    """get_openapi returns the openapi_url when the service has one."""
    openapi_url = "https://openai.example.com/openapi.json"
    row = _make_service_row(SVC_ID_1, "openai", openapi_url=openapi_url)
    mock_session = _mock_session_execute([row])
    test_app = app_with_overrides(mock_session)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/v1/tools/get_openapi/{SVC_ID_1}")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"openapi_url": openapi_url}


@pytest.mark.asyncio
async def test_get_openapi_returns_null_when_no_url(app_with_overrides) -> None:
    """get_openapi returns {"openapi_url": null} (not 404) when no URL is set."""
    row = _make_service_row(SVC_ID_1, "openai", openapi_url=None)
    mock_session = _mock_session_execute([row])
    test_app = app_with_overrides(mock_session)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.get(f"/v1/tools/get_openapi/{SVC_ID_1}")

    assert resp.status_code == 200, resp.text
    assert resp.json() == {"openapi_url": None}
