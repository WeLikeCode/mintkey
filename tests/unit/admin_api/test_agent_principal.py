"""
Tests for the agent principal dependency.

Requirement: agent-principal, "An agent key yields a principal" — the five
scenarios of the spec.

Sources:
  - `openspec/changes/agent-principal-and-egress/specs/agent-principal/spec.md`
  - `openspec/changes/agent-principal-and-egress/design.md` — D1, D2, D7
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import AsyncIterator
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.responses import JSONResponse
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from starlette.requests import Request

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from admin_api.api import internal  # noqa: E402
from admin_api.auth import agent_principal  # noqa: E402
from admin_api.auth.agent_principal import (  # noqa: E402
    AgentApiError,
    AgentPrincipal,
    agent_api_error_handler,
)
from admin_api.db.deps import get_db_session  # noqa: E402
from mintkey_models.tenant_ctx import set_tenant_context  # noqa: E402

# Built at run time so no test file holds a token-shaped value whole.
API_KEY = "mk_" + "agent_" + "A" * 24
NOT_A_KEY = "mk_" + "agent_" + "x"

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")

EXPIRES_AT = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
EXPIRED_HINT = (
    f"This agent's API key expired on {EXPIRES_AT.isoformat()}. "
    "Operator must rotate the key via the admin UI Rotate Key action."
)

INVALID_KEY_BODY: dict[str, Any] = {
    "type": "https://mintkey.internal/errors/invalid-agent-key",
    "title": "Invalid agent key",
    "status": 401,
    "mintkey:code": "mintkey:invalid_agent_key",
}

EXPIRED_KEY_BODY: dict[str, Any] = {
    "type": "https://mintkey.internal/errors/agent-key-expired",
    "title": "API key expired",
    "status": 401,
    "mintkey:code": "agent_api_key_expired",
    "hint": EXPIRED_HINT,
}

VERIFY_UNAVAILABLE_BODY: dict[str, Any] = {
    "mintkey:code": "mintkey:verify_unavailable",
}

REJECTED_CASES = [
    pytest.param(
        401,
        INVALID_KEY_BODY,
        {
            "type": "https://mintkey.internal/errors/invalid-agent-key",
            "title": "Invalid agent key",
            "status": 401,
            "code": "mintkey:invalid_agent_key",
        },
        id="unknown_key_401",
    ),
    pytest.param(
        401,
        EXPIRED_KEY_BODY,
        {
            "type": "https://mintkey.internal/errors/agent-key-expired",
            "title": "API key expired",
            "status": 401,
            "code": "mintkey:agent_api_key_expired",
            "hint": EXPIRED_HINT,
        },
        id="expired_key_401",
    ),
    pytest.param(
        503,
        VERIFY_UNAVAILABLE_BODY,
        {"code": "mintkey:verify_unavailable", "title": "Key check unavailable"},
        id="verify_unavailable_503",
    ),
]

NO_CREDENTIAL_CASES = [
    pytest.param({}, id="no_header"),
    pytest.param({"authorization": "Basic x"}, id="basic_auth"),
    pytest.param(
        {"authorization": "Bearer not_an_agent_key"}, id="bearer_not_an_agent_key"
    ),
    pytest.param({"x-api-key": NOT_A_KEY}, id="x_api_key_only"),
    pytest.param({"cookie": "mintkey_session=" + "abc"}, id="cookie_only"),
]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    """The slice of a SQLAlchemy result the key check reads."""

    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row


class _RecordingSession:
    """An async-context-manager session recording statements and closes."""

    def __init__(
        self,
        *,
        name: str = "key",
        events: list[tuple[Any, ...]] | None = None,
        row: Any = None,
    ) -> None:
        self.name = name
        self.events: list[tuple[Any, ...]] = events if events is not None else []
        self.row = row
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.closed = False
        self.commits = 0

    async def __aenter__(self) -> "_RecordingSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    async def close(self) -> None:
        if not self.closed:
            self.closed = True
            self.events.append((self.name, "close"))

    async def commit(self) -> None:
        self.commits += 1
        self.events.append((self.name, "commit"))

    async def execute(
        self,
        statement: Any,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _Result:
        sql = " ".join(str(statement).split())
        bound = dict(params or {})
        self.statements.append((sql, bound))
        self.events.append((self.name, "execute", sql, bound))
        if "from agents" in sql.lower():
            return _Result(self.row)
        return _Result()


class _RecordingFactory:
    """Stand-in for ``AsyncSessionLocal`` that hands out one session."""

    def __init__(self, session: _RecordingSession) -> None:
        self.session = session
        self.calls = 0

    def __call__(self) -> _RecordingSession:
        self.calls += 1
        return self.session


def _raising_factory() -> _RecordingSession:
    raise RuntimeError("database unavailable")


async def _verify_ok(_stored_hash: str, _secret: str) -> None:
    return None


def _active_row(
    *, role: str = "publisher", expires_at: datetime | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        id=AGENT_ID,
        tenant_id=TENANT_ID,
        api_key_hash="$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        status="active",
        api_key_expires_at=expires_at,
        api_key_fingerprint="deadbeefdeadbeef",
        role=role,
    )


def _request(headers: dict[str, str] | None = None) -> Request:
    raw = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/agent/probe",
            "raw_path": b"/v1/agent/probe",
            "query_string": b"",
            "headers": raw,
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        }
    )


def _compact(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).replace(", ", ",")


def _make_auth_app() -> FastAPI:
    """A probe route behind only the principal dependency."""

    app = FastAPI()
    app.add_exception_handler(AgentApiError, agent_api_error_handler)

    @app.post("/v1/agent/probe")
    async def probe(
        principal: AgentPrincipal = Depends(agent_principal.require_agent_principal),
    ) -> dict[str, str]:
        assert principal is not None
        return {"agent_id": str(principal.agent_id)}

    return app


def _make_route_session_app(route_session: _RecordingSession) -> FastAPI:
    """A probe route with the principal and a route session of its own."""

    app = FastAPI()
    app.add_exception_handler(AgentApiError, agent_api_error_handler)

    async def _route_db() -> AsyncIterator[_RecordingSession]:
        yield route_session

    app.dependency_overrides[get_db_session] = _route_db

    @app.post("/v1/agent/probe")
    async def probe(
        principal: AgentPrincipal = Depends(agent_principal.require_agent_principal),
        session: Any = Depends(get_db_session),
    ) -> dict[str, str]:
        assert principal is not None
        await set_tenant_context(session, principal.tenant_id)
        await session.execute(text("SELECT 1"))
        return {"status": "ok"}

    return app


# ---------------------------------------------------------------------------
# C-3c508836 — a publisher key
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-3c508836")
async def test_C_3c508836_publisher_key_yields_the_principal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _active_row(role="publisher")
    session = _RecordingSession(row=row)
    factory = _RecordingFactory(session)
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
    check = AsyncMock(return_value=(row, None))
    monkeypatch.setattr(internal, "check_agent_key", check)

    principal = await agent_principal.require_agent_principal(
        _request({"authorization": f"Bearer {API_KEY}"})
    )

    assert principal is not None
    assert isinstance(principal, AgentPrincipal)
    assert principal.tenant_id == TENANT_ID
    assert principal.agent_id == AGENT_ID
    assert principal.role == "publisher"

    check.assert_awaited_once()
    assert check.await_args.args[0] is session
    assert check.await_args.args[1] == API_KEY
    assert factory.calls == 1
    assert session.closed is True


# ---------------------------------------------------------------------------
# C-5b21f986 — no usable credential
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-5b21f986")
@pytest.mark.parametrize("headers", NO_CREDENTIAL_CASES)
async def test_C_5b21f986_no_usable_credential_is_401_without_a_session(
    monkeypatch: pytest.MonkeyPatch,
    headers: dict[str, str],
) -> None:
    session = _RecordingSession()
    factory = _RecordingFactory(session)
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
    check = AsyncMock()
    monkeypatch.setattr(internal, "check_agent_key", check)

    with pytest.raises(AgentApiError) as exc_info:
        await agent_principal.require_agent_principal(_request(headers))

    exc = exc_info.value
    assert exc.status_code == 401
    assert exc.body == {
        "code": "mintkey:auth_required",
        "title": "Agent key required",
    }
    check.assert_not_awaited()
    assert factory.calls == 0


# ---------------------------------------------------------------------------
# C-5861b2ec — rejected keys
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-5861b2ec")
@pytest.mark.parametrize("status, response_body, expected_body", REJECTED_CASES)
async def test_C_5861b2ec_rejected_key_raises_agent_api_error(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    response_body: dict[str, Any],
    expected_body: dict[str, Any],
) -> None:
    session = _RecordingSession()
    monkeypatch.setattr(
        agent_principal, "AsyncSessionLocal", _RecordingFactory(session)
    )
    check = AsyncMock(
        return_value=(None, JSONResponse(status_code=status, content=response_body))
    )
    monkeypatch.setattr(internal, "check_agent_key", check)

    with pytest.raises(AgentApiError) as exc_info:
        await agent_principal.require_agent_principal(
            _request({"authorization": f"Bearer {API_KEY}"})
        )

    exc = exc_info.value
    assert exc.status_code == status
    assert exc.body == expected_body
    assert "mintkey:code" not in exc.body
    check.assert_awaited_once()
    assert session.closed is True


@pytest.mark.asyncio
@pytest.mark.l4("C-5861b2ec")
@pytest.mark.parametrize("status, response_body, expected_body", REJECTED_CASES)
async def test_C_5861b2ec_handler_answers_the_same_http_response(
    monkeypatch: pytest.MonkeyPatch,
    status: int,
    response_body: dict[str, Any],
    expected_body: dict[str, Any],
) -> None:
    session = _RecordingSession()
    monkeypatch.setattr(
        agent_principal, "AsyncSessionLocal", _RecordingFactory(session)
    )
    check = AsyncMock(
        return_value=(None, JSONResponse(status_code=status, content=response_body))
    )
    monkeypatch.setattr(internal, "check_agent_key", check)

    app = _make_auth_app()
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/agent/probe", headers={"Authorization": f"Bearer {API_KEY}"}
        )

    assert response.status_code == status
    assert response.json() == expected_body
    assert "mintkey:code" not in response.json()
    assert response.headers["content-type"] == "application/json"


# ---------------------------------------------------------------------------
# C-70750b4d — the database fails while the key is checked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-70750b4d")
async def test_C_70750b4d_session_factory_failure_is_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", _raising_factory)

    with pytest.raises(AgentApiError) as exc_info:
        await agent_principal.require_agent_principal(
            _request({"authorization": f"Bearer {API_KEY}"})
        )

    exc = exc_info.value
    assert exc.status_code == 503
    assert exc.body == {
        "code": "mintkey:verify_unavailable",
        "title": "Key check unavailable",
    }


@pytest.mark.asyncio
@pytest.mark.l4("C-70750b4d")
async def test_C_70750b4d_key_check_failure_is_503_and_closes_the_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _RecordingSession()
    factory = _RecordingFactory(session)
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
    check = AsyncMock(side_effect=RuntimeError("key check failed"))
    monkeypatch.setattr(internal, "check_agent_key", check)

    with pytest.raises(AgentApiError) as exc_info:
        await agent_principal.require_agent_principal(
            _request({"authorization": f"Bearer {API_KEY}"})
        )

    exc = exc_info.value
    assert exc.status_code == 503
    assert exc.body == {
        "code": "mintkey:verify_unavailable",
        "title": "Key check unavailable",
    }
    assert factory.calls == 1
    assert session.closed is True


# ---------------------------------------------------------------------------
# C-acbb978c — the route's session never sees the platform view
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-acbb978c")
async def test_C_acbb978c_route_session_never_sees_the_platform_view(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    events: list[tuple[Any, ...]] = []
    key_session = _RecordingSession(
        name="key", events=events, row=_active_row(role="publisher")
    )
    route_session = _RecordingSession(name="route", events=events)

    monkeypatch.setattr(
        agent_principal, "AsyncSessionLocal", _RecordingFactory(key_session)
    )
    monkeypatch.setattr(internal, "_verify_argon2", _verify_ok)

    app = _make_route_session_app(route_session)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/v1/agent/probe", headers={"Authorization": f"Bearer {API_KEY}"}
        )

    assert response.status_code == 200, response.text

    key_execs = [event for event in events if event[0] == "key" and event[1] == "execute"]
    assert key_execs, events
    assert (
        "set_config('app.platform_admin_view','on',true)"
        in _compact(key_execs[0][2])
    )
    key_closes = [
        index
        for index, event in enumerate(events)
        if event[0] == "key" and event[1] == "close"
    ]
    assert key_closes, events
    assert key_session.closed is True

    assert route_session is not key_session
    route_execs = [
        (index, event)
        for index, event in enumerate(events)
        if event[0] == "route" and event[1] == "execute"
    ]
    assert route_execs, events
    assert route_execs[0][0] > key_closes[0]
    assert "app.current_tenant" in route_execs[0][1][2]
    assert route_execs[0][1][3] == {"tid": str(TENANT_ID)}

    for _index, event in route_execs:
        sql = event[2]
        params = json.dumps(event[3], sort_keys=True)
        assert "platform_admin_view" not in sql
        assert "'on'" not in sql
        assert "platform_admin_view" not in params
        assert "'on'" not in params
