"""
Tests for the publisher-only dependency and the denied-operation record.

Requirement: agent-principal, "A role that is too low is refused and recorded"
— the two scenarios of the spec.

Sources:
  - `openspec/changes/agent-principal-and-egress/specs/agent-principal/spec.md`
  - `openspec/changes/agent-principal-and-egress/design.md` — D3, D4
"""

from __future__ import annotations

import logging
import os
import sys
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from admin_api.auth import agent_principal  # noqa: E402
from admin_api.auth.agent_principal import (  # noqa: E402
    AgentApiError,
    AgentPrincipal,
    agent_api_error_handler,
)
from admin_api.utils.wire_ids import db_uuid_to_wire  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
AGENT_WIRE_ID = db_uuid_to_wire(AGENT_ID, "agent")

CONSUMER = AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="consumer")
PUBLISHER = AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="publisher")

LOGGER_NAME = "admin_api.auth.agent_principal"


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    """The slice of a SQLAlchemy result a context statement returns."""

    def fetchone(self) -> Any:
        return None


class _RecordingSession:
    """An async-context-manager session recording statements and commits."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0
        self.closed = False

    async def __aenter__(self) -> "_RecordingSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    async def close(self) -> None:
        self.closed = True

    async def commit(self) -> None:
        self.commits += 1

    async def execute(
        self,
        statement: Any,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _Result:
        self.statements.append((" ".join(str(statement).split()), dict(params or {})))
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


def _make_app(principal: AgentPrincipal) -> FastAPI:
    """A probe route behind ``require_publisher_principal``."""

    app = FastAPI()
    app.add_exception_handler(AgentApiError, agent_api_error_handler)

    async def _principal() -> AgentPrincipal:
        return principal

    app.dependency_overrides[agent_principal.require_agent_principal] = _principal

    @app.post("/v1/agent/probe")
    async def probe(
        resolved: AgentPrincipal = Depends(
            agent_principal.require_publisher_principal
        ),
    ) -> dict[str, str]:
        return {"agent_id": str(resolved.agent_id), "role": resolved.role}

    return app


async def _post(app: FastAPI) -> Any:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post("/v1/agent/probe")


def _refusal_logged(caplog: pytest.LogCaptureFixture) -> bool:
    return any(
        record.name == LOGGER_NAME and record.levelno >= logging.WARNING
        for record in caplog.records
    )


# ---------------------------------------------------------------------------
# C-882edc8c — the wrong role is refused with a literal operation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-882edc8c")
async def test_C_882edc8c_consumer_is_refused_and_the_denial_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _RecordingSession()
    factory = _RecordingFactory(session)
    audit = AsyncMock()
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
    monkeypatch.setattr(agent_principal, "audit_emit", audit, raising=False)

    response = await _post(_make_app(CONSUMER))

    assert response.status_code == 403, response.text
    body = response.json()
    assert body["code"] == "mintkey:role_forbidden"
    assert body["title"] == "Role not allowed"
    assert body["role"] == "consumer"
    assert body["required_role"] == "publisher"
    assert set(body) == {"code", "title", "role", "required_role", "hint"}
    assert isinstance(body["hint"], str) and body["hint"]

    assert factory.calls == 1
    audit.assert_awaited_once()
    kwargs = audit.await_args.kwargs
    assert kwargs["session"] is session
    assert kwargs["tenant_id"] == TENANT_ID
    assert kwargs["event_type"] == "agent.operation.denied"
    assert kwargs["actor_id"] == AGENT_ID
    assert kwargs["actor_type"] == "agent"
    assert kwargs["target_id"] == AGENT_ID
    assert kwargs["target_type"] == "agent"
    assert kwargs["payload"] == {
        "agent_id": AGENT_WIRE_ID,
        "role": "consumer",
        "operation": "POST /v1/agent/probe",
    }

    assert session.statements, "the denied operation recorded no statement"
    first_sql, first_params = session.statements[0]
    assert "set_config('app.current_tenant'" in first_sql
    assert first_params == {"tid": str(TENANT_ID)}
    assert session.commits == 1

    for sql, params in session.statements:
        assert "platform_admin_view" not in sql
        assert "platform_admin_view" not in repr(params)


@pytest.mark.asyncio
@pytest.mark.l4("C-882edc8c")
async def test_C_882edc8c_publisher_passes_and_records_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _RecordingSession()
    factory = _RecordingFactory(session)
    audit = AsyncMock()
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
    monkeypatch.setattr(agent_principal, "audit_emit", audit, raising=False)

    response = await _post(_make_app(PUBLISHER))

    assert response.status_code == 200, response.text
    assert response.json() == {"agent_id": str(AGENT_ID), "role": "publisher"}
    audit.assert_not_awaited()
    assert factory.calls == 0
    assert session.statements == []


# ---------------------------------------------------------------------------
# C-aa34abc8 — the record itself fails
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-aa34abc8")
async def test_C_aa34abc8_audit_failure_still_answers_403_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    session = _RecordingSession()
    factory = _RecordingFactory(session)
    audit = AsyncMock(side_effect=RuntimeError("audit unavailable"))
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
    monkeypatch.setattr(agent_principal, "audit_emit", audit, raising=False)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        response = await _post(_make_app(CONSUMER))

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "mintkey:role_forbidden"
    assert audit.await_count == 1
    assert _refusal_logged(caplog), [record.message for record in caplog.records]


@pytest.mark.asyncio
@pytest.mark.l4("C-aa34abc8")
async def test_C_aa34abc8_session_failure_still_answers_403_and_logs(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    audit = AsyncMock()
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", _raising_factory)
    monkeypatch.setattr(agent_principal, "audit_emit", audit, raising=False)

    with caplog.at_level(logging.WARNING, logger=LOGGER_NAME):
        response = await _post(_make_app(CONSUMER))

    assert response.status_code == 403, response.text
    assert response.json()["code"] == "mintkey:role_forbidden"
    audit.assert_not_awaited()
    assert _refusal_logged(caplog), [record.message for record in caplog.records]
