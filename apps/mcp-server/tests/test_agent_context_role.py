"""
The MCP client keeps the agent's role from the admin-api key check.

Requirement: agent-roles-and-ownership › The agent-key check reports the role

  - the MCP client keeps the role (C-16761723)

`AdminApiClient.validate_agent_key` turns a 200 answer into an `AgentContext`.
The role travels in that context; an answer without a role (an older admin-api)
falls back to the less powerful role, `consumer`.

Sources:
  - `openspec/changes/agent-roles-and-ownership/spec.md` — The agent-key check
    reports the role
  - `openspec/changes/agent-roles-and-ownership/design.md` — D3, Interfaces
"""
from __future__ import annotations

import asyncio
import types

import mcp_server.admin_api_client as admin_api_client

_AGENT_ID = "agent_00000000000000000000000000"
_TENANT_ID = "11111111-2222-3333-4444-555555555555"


class _FakeResponse:
    """A 200 answer with a JSON body, as `httpx.Response` would give."""

    def __init__(self, body: dict) -> None:
        self.status_code = 200
        self._body = body

    def json(self) -> dict:
        return self._body


def _answer_with(monkeypatch, body: dict) -> None:
    """Install a fake `httpx.AsyncClient` that posts back `body`."""

    class FakeClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, **kwargs):
            return _FakeResponse(body)

    monkeypatch.setattr(
        admin_api_client, "httpx", types.SimpleNamespace(AsyncClient=FakeClient)
    )


def _validate_agent_key():
    client = admin_api_client.AdminApiClient(base_url="http://admin-api:8080")
    return asyncio.run(client.validate_agent_key("test-api-key"))


def test_C_16761723_mcp_context_keeps_publisher_role(monkeypatch) -> None:
    _answer_with(
        monkeypatch,
        {
            "agent_id": _AGENT_ID,
            "tenant_id": _TENANT_ID,
            "status": "active",
            "role": "publisher",
        },
    )

    context = _validate_agent_key()

    assert context is not None
    assert context.agent_id == _AGENT_ID
    assert context.tenant_id == _TENANT_ID
    assert getattr(context, "role", None) == "publisher"


def test_C_16761723_mcp_context_defaults_missing_role_to_consumer(monkeypatch) -> None:
    _answer_with(
        monkeypatch,
        {
            "agent_id": _AGENT_ID,
            "tenant_id": _TENANT_ID,
            "status": "active",
        },
    )

    context = _validate_agent_key()

    assert context is not None
    assert context.agent_id == _AGENT_ID
    assert getattr(context, "role", None) == "consumer"
