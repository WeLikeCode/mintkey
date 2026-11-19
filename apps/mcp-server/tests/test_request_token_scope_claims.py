"""
The MCP server passes optional token scope limits to the broker.

Source: specs/token-scope-claims/spec.md — "The MCP server passes the limits to
the broker"; openspec/changes/token-request-scope-claims/tasks.md §3.1.
"""
from __future__ import annotations

import asyncio
import json
import types
import uuid
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
import yaml
from fastapi.responses import JSONResponse

import mcp_server.tools.jsonrpc as jsonrpc_module
import mcp_server.tools.request_token as request_token_module
from mcp_server.tools.request_token import TokenRequest

_AGENT_ID = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
_TENANT_ID = "11111111-2222-3333-4444-555555555555"
_SERVICE_UUID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_AGENT_CTX = {"agent_id": _AGENT_ID, "tenant_id": _TENANT_ID}

_BROKER_TITLE = (
    "methods may contain only GET, HEAD, POST, PUT, PATCH, DELETE and OPTIONS"
)


class _FakeResponse:
    def __init__(self, status_code: int, body: dict) -> None:
        self.status_code = status_code
        self._body = body

    def json(self) -> dict:
        return self._body


def _fake_httpx(monkeypatch, responses: list[_FakeResponse]) -> list[dict]:
    calls: list[dict] = []

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc_info):
            return False

        async def post(self, url, **kwargs):
            calls.append({"url": url, **kwargs})
            return responses.pop(0)

    monkeypatch.setattr(
        request_token_module, "httpx", types.SimpleNamespace(AsyncClient=FakeClient)
    )
    return calls


def _result(row):
    result = MagicMock()
    result.fetchone.return_value = row
    return result


def _session(*rows):
    session = MagicMock()
    session.execute = AsyncMock(side_effect=[_result(row) for row in rows])
    return session


def _mock_resolution(monkeypatch, *, email_service_uuid=None) -> None:
    monkeypatch.setattr(request_token_module, "set_tenant_context", AsyncMock())
    monkeypatch.setattr(
        request_token_module,
        "resolve_service_id",
        AsyncMock(return_value=_SERVICE_UUID),
    )
    monkeypatch.setattr(
        request_token_module,
        "resolve_email_service_id",
        AsyncMock(return_value=email_service_uuid),
    )


def _grant() -> MagicMock:
    grant = MagicMock()
    grant.constraints = {}
    return grant


def _service(auth_scheme: str) -> MagicMock:
    service = MagicMock()
    service.auth_scheme = auth_scheme
    return service


def _call_request_token(body: TokenRequest, session) -> JSONResponse:
    return asyncio.run(
        request_token_module.request_token(
            request=MagicMock(),
            body=body,
            session=session,
            agent_ctx=dict(_AGENT_CTX),
        )
    )


@pytest.mark.l4("C-8bb63508")
def test_C_8bb63508_request_token_forwards_scope_claims_only_when_given(
    monkeypatch,
) -> None:
    """C-8bb63508: the broker body carries the limits only when the caller gave them."""
    calls = _fake_httpx(
        monkeypatch,
        [
            _FakeResponse(200, {"token": "t", "expires_at": 1}),
            _FakeResponse(200, {"token": "t", "expires_at": 1}),
        ],
    )
    _mock_resolution(monkeypatch)

    with_limits = _call_request_token(
        TokenRequest(
            service_id=str(_SERVICE_UUID),
            action="call",
            methods=["GET"],
            path_prefix="/v1/messages",
        ),
        _session(_grant(), _service("api_key_header")),
    )
    without_limits = _call_request_token(
        TokenRequest(service_id=str(_SERVICE_UUID), action="call"),
        _session(_grant(), _service("api_key_header")),
    )

    assert isinstance(with_limits, JSONResponse)
    assert isinstance(without_limits, JSONResponse)
    assert with_limits.status_code == 200
    assert without_limits.status_code == 200

    assert len(calls) == 2
    assert calls[0]["json"].get("methods") == ["GET"]
    assert calls[0]["json"].get("path_prefix") == "/v1/messages"
    assert "methods" not in calls[1]["json"]
    assert "path_prefix" not in calls[1]["json"]


@pytest.mark.l4("C-046d6912")
def test_C_046d6912_request_token_answers_broker_validation_error_with_400(
    monkeypatch,
) -> None:
    """C-046d6912: a broker 400 becomes a 400 with the broker's validation title."""
    _fake_httpx(
        monkeypatch,
        [
            _FakeResponse(
                400,
                {"mintkey:code": "validation_failed", "title": _BROKER_TITLE},
            )
        ],
    )
    _mock_resolution(monkeypatch)

    response = _call_request_token(
        TokenRequest(
            service_id=str(_SERVICE_UUID),
            action="call",
            methods=["FETCH"],
        ),
        _session(_grant(), _service("api_key_header")),
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 400
    body = json.loads(response.body)
    assert body["code"] == "mintkey:validation_failed"
    assert body["title"] == _BROKER_TITLE


@pytest.mark.l4("C-23b6e29a")
def test_C_23b6e29a_request_token_refuses_scope_claims_for_ssh_and_email_services(
    monkeypatch,
) -> None:
    """C-23b6e29a: SSH and email services refuse the limits before calling the broker."""
    calls = _fake_httpx(
        monkeypatch,
        [
            _FakeResponse(200, {"token": "t", "expires_at": 1}),
            _FakeResponse(200, {"token": "t", "expires_at": 1}),
        ],
    )
    _mock_resolution(monkeypatch, email_service_uuid=_SERVICE_UUID)

    ssh_response = _call_request_token(
        TokenRequest(
            service_id=str(_SERVICE_UUID),
            action="call",
            methods=["GET"],
        ),
        _session(_grant(), _service("ssh_private_key")),
    )
    email_response = _call_request_token(
        TokenRequest(
            service_id=str(_SERVICE_UUID),
            action="call",
            methods=["GET"],
        ),
        _session(None, _grant()),
    )

    assert isinstance(ssh_response, JSONResponse)
    assert isinstance(email_response, JSONResponse)

    assert ssh_response.status_code == 400
    ssh_body = json.loads(ssh_response.body)
    assert ssh_body["code"] == "mintkey:validation_failed"
    assert ssh_body["reason_code"] == "scope_claims_http_only"

    assert email_response.status_code == 400
    email_body = json.loads(email_response.body)
    assert email_body["code"] == "mintkey:validation_failed"
    assert email_body["reason_code"] == "scope_claims_http_only"

    assert calls == []


class _DispatchClient:
    def __init__(self) -> None:
        self.posts: list[dict] = []

    async def post(self, path, **kwargs):
        self.posts.append({"path": path, **kwargs})
        return _FakeResponse(200, {"token": "t", "expires_at": 1})


@pytest.mark.l4("C-408d5385")
def test_C_408d5385_jsonrpc_request_token_forwards_scope_claims() -> None:
    """C-408d5385: the JSON-RPC tool and the MCP contract carry both fields."""
    client = _DispatchClient()
    response = asyncio.run(
        jsonrpc_module._dispatch_tool(
            client,
            "mintkey_request_token",
            {
                "service_id": "svc_x",
                "methods": ["GET"],
                "path_prefix": "/v1/messages",
            },
            {},
        )
    )

    assert response is not None
    assert len(client.posts) == 1
    assert client.posts[0]["json"] == {
        "service_id": "svc_x",
        "action": "call",
        "methods": ["GET"],
        "path_prefix": "/v1/messages",
    }

    tool = next(
        entry for entry in jsonrpc_module.TOOLS
        if entry["name"] == "mintkey_request_token"
    )
    tool_schema = tool["inputSchema"]
    assert "methods" in tool_schema["properties"]
    assert "path_prefix" in tool_schema["properties"]
    assert "methods" not in tool_schema.get("required", [])
    assert "path_prefix" not in tool_schema.get("required", [])

    contract_path = (
        Path(__file__).resolve().parents[3]
        / "docs"
        / "architecture"
        / "contracts"
        / "mcp"
        / "tools.yaml"
    )
    contract = yaml.safe_load(contract_path.read_text())
    request_token_tool = next(
        entry for entry in contract["tools"] if entry["name"] == "request_token"
    )
    contract_schema = request_token_tool["input_schema"]
    assert "methods" in contract_schema["properties"]
    assert "path_prefix" in contract_schema["properties"]
    assert "methods" not in contract_schema.get("required", [])
    assert "path_prefix" not in contract_schema.get("required", [])
