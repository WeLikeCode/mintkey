"""
Unit tests: an expired grant is absent for the agent and a token never outlives
its grant.

Requirement: grant-expiry › An expired grant is absent for the agent

  - an expired grant is denied (C-1494d103)
  - the grant select is ordered (C-18424d96)
  - a grant without an expiry behaves as before (C-9398f128)

Requirement: grant-expiry › A token never outlives its grant

  - the lifetime function (C-b4dd4c2b)
  - the broker receives the shortened lifetime (C-f1c29313)

The `request_token` set-up mirrors `test_request_token_scope_claims.py`: the
service id is resolved without a database round-trip, a fake `httpx` records the
broker payload, and `session.execute` answers the grant row and then the service
row.

Sources:
  - `openspec/changes/grant-expiry/spec.md` — An expired grant is absent for the
    agent; A token never outlives its grant
  - `openspec/changes/grant-expiry/design.md` — D3, D4
"""
from __future__ import annotations

import asyncio
import json
import types
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.responses import JSONResponse

import mcp_server.tools.request_token as request_token_module
from mcp_server.policy.grant_expiry import grant_ttl_seconds
from mcp_server.tools.request_token import TokenRequest

_AGENT_ID = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
_TENANT_ID = "11111111-2222-3333-4444-555555555555"
_SERVICE_UUID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
_AGENT_CTX = {"agent_id": _AGENT_ID, "tenant_id": _TENANT_ID}

_NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


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


def _mock_resolution(monkeypatch) -> None:
    monkeypatch.setattr(request_token_module, "set_tenant_context", AsyncMock())
    monkeypatch.setattr(
        request_token_module,
        "resolve_service_id",
        AsyncMock(return_value=_SERVICE_UUID),
    )
    monkeypatch.setattr(
        request_token_module,
        "resolve_email_service_id",
        AsyncMock(return_value=None),
    )


def _grant(**attributes) -> types.SimpleNamespace:
    """A grant row; `constraints` is always present, other columns optional."""
    return types.SimpleNamespace(constraints={}, **attributes)


def _service(auth_scheme: str = "api_key_header") -> types.SimpleNamespace:
    return types.SimpleNamespace(auth_scheme=auth_scheme)


def _call_request_token(body: TokenRequest, session) -> JSONResponse:
    return asyncio.run(
        request_token_module.request_token(
            request=MagicMock(),
            body=body,
            session=session,
            agent_ctx=dict(_AGENT_CTX),
        )
    )


def _token_body() -> TokenRequest:
    return TokenRequest(service_id=str(_SERVICE_UUID), action="call")


class _RecordingSession:
    """Records every statement and answers the grant and service reads."""

    def __init__(self, grant, service) -> None:
        self.statements: list[str] = []
        self._rows = [grant, service]

    async def execute(self, stmt, params=None, **kwargs):
        self.statements.append(str(stmt))
        row = self._rows.pop(0) if self._rows else None
        return _result(row)


def _statement_reading(session: _RecordingSession, table: str) -> str:
    statement = next(s for s in session.statements if table in s)
    return " ".join(statement.split())


@pytest.mark.l4("C-1494d103")
def test_C_1494d103_expired_grant_is_denied(monkeypatch) -> None:
    """A grant ten seconds past and one with two seconds left both deny."""
    calls = _fake_httpx(
        monkeypatch,
        [
            _FakeResponse(200, {"token": "t", "expires_at": 1}),
            _FakeResponse(200, {"token": "t", "expires_at": 1}),
        ],
    )
    _mock_resolution(monkeypatch)
    audit = AsyncMock()
    monkeypatch.setattr(request_token_module, "audit_emit", audit)

    now = datetime.now(timezone.utc)
    expired = _call_request_token(
        _token_body(),
        _session(
            _grant(expires_at=now - timedelta(seconds=10)),
            _service(),
        ),
    )
    almost = _call_request_token(
        _token_body(),
        _session(
            _grant(expires_at=now + timedelta(seconds=2)),
            _service(),
        ),
    )

    assert isinstance(expired, JSONResponse)
    assert isinstance(almost, JSONResponse)
    for response in (expired, almost):
        assert response.status_code == 403
        body = json.loads(response.body)
        assert body["code"] == "mintkey:not_authorized"
        assert body["reason_code"] == "grant_expired"
        assert body["hint"]

    assert calls == [], "the broker must not be called for an expired grant"

    denials = [call.kwargs for call in audit.call_args_list]
    assert [d["event_type"] for d in denials] == ["token.denied", "token.denied"]
    assert [d["payload"]["reason_code"] for d in denials] == [
        "grant_expired",
        "grant_expired",
    ]


@pytest.mark.l4("C-18424d96")
def test_C_18424d96_grant_select_is_ordered(monkeypatch) -> None:
    """The grant read orders live rows first and selects expires_at."""
    _fake_httpx(
        monkeypatch,
        [_FakeResponse(200, {"token": "t", "expires_at": 1})],
    )
    _mock_resolution(monkeypatch)

    session = _RecordingSession(_grant(expires_at=None), _service())
    response = _call_request_token(_token_body(), session)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200

    statement = _statement_reading(session, "permission_grants")
    assert (
        "ORDER BY (expires_at IS NULL) DESC, expires_at DESC, created_at DESC, id"
        in statement
    )
    assert "LIMIT 1" in statement
    select_list = statement.split("FROM permission_grants")[0]
    assert "expires_at" in select_list


@pytest.mark.l4("C-9398f128", "C-b4dd4c2b")
def test_C_9398f128_C_b4dd4c2b_no_expiry_behaves_as_before(monkeypatch) -> None:
    """Missing, null and non-datetime expiries keep the 600 s token."""
    calls = _fake_httpx(
        monkeypatch,
        [
            _FakeResponse(200, {"token": "t", "expires_at": 1}),
            _FakeResponse(200, {"token": "t", "expires_at": 1}),
            _FakeResponse(200, {"token": "t", "expires_at": 1}),
        ],
    )
    _mock_resolution(monkeypatch)

    no_attribute = _call_request_token(_token_body(), _session(_grant(), _service()))
    nulled = _call_request_token(
        _token_body(), _session(_grant(expires_at=None), _service())
    )
    not_a_datetime = _call_request_token(
        _token_body(), _session(_grant(expires_at="soon"), _service())
    )

    for response in (no_attribute, nulled, not_a_datetime):
        assert isinstance(response, JSONResponse)
        assert response.status_code == 200

    assert len(calls) == 3
    assert [call["json"]["ttl_seconds"] for call in calls] == [600, 600, 600]

    # The same rule read directly from the lifetime function: no expiry is 600.
    assert grant_ttl_seconds(None, _NOW) == 600


@pytest.mark.l4("C-b4dd4c2b")
def test_C_b4dd4c2b_lifetime_function() -> None:
    """The lifetime caps at 600 s and refuses anything under 5 s."""

    def at(seconds: float | None) -> int | None:
        expires_at = (
            None if seconds is None else _NOW + timedelta(seconds=seconds)
        )
        return grant_ttl_seconds(expires_at, _NOW)

    assert at(None) == 600
    assert at(3600) == 600
    assert at(600) == 600
    assert at(100.9) == 100
    assert at(5) == 5
    assert at(4.9) is None
    assert at(0) is None
    assert at(-1) is None


@pytest.mark.l4("C-f1c29313")
def test_C_f1c29313_broker_receives_shortened_lifetime(monkeypatch) -> None:
    """A grant about 120 s away sends that lifetime to the broker."""
    calls = _fake_httpx(
        monkeypatch,
        [_FakeResponse(200, {"token": "t", "expires_at": 1})],
    )
    _mock_resolution(monkeypatch)

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=120)
    response = _call_request_token(
        _token_body(),
        _session(_grant(expires_at=expires_at), _service()),
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 200
    assert len(calls) == 1
    ttl = calls[0]["json"]["ttl_seconds"]
    assert type(ttl) is int
    assert 100 <= ttl <= 120
