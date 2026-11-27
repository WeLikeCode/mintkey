"""
Unit tests: an agent's role in the operator API and in the key check.

Requirement: agent-roles-and-ownership
  - Agent responses carry the role (a new agent is a consumer, list and get
    show the stored role, the role filter)
  - An operator sets an agent's role (promote/demote, the same role is nothing
    to do, invalid bodies and unknown agents, no session)
  - A demotion changes nothing else
  - The operator routes answer errors in one flat shape (the role-PATCH half)
  - The agent-key check reports the role (the answer names the role)

Sources:
  - `openspec/changes/agent-roles-and-ownership/spec.md`
  - `openspec/changes/agent-roles-and-ownership/design.md` — D1, D5, D6, D8, D9
"""
from __future__ import annotations

import json
import os
import re
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest
from fastapi.exceptions import RequestValidationError
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_TEXT = str(TENANT_ID)
AGENT_ID = "agent_00000000000000000000000001"
UNKNOWN_AGENT_ID = "agent_00000000000000000000000002"
UNDECODABLE_AGENT_ID = "agent_" + "I" * 26
OP_ID = UUID("00000000-0000-0000-0000-0000000000aa")
SESSION_TOKEN = "00000000-0000-0000-0000-0000000000bb"
BASE_URL_PATH = f"/v1/tenants/{TENANT_TEXT}/agents"

# Built at run time so no test file holds a token-shaped value whole.
API_KEY = "mk_" + "agent_" + "A" * 24

_MISSING = object()


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    """The small slice of a SQLAlchemy result the handlers use."""

    def __init__(self, rows: list[Any] | None = None, one: Any = None) -> None:
        self._rows = list(rows or [])
        self._one = one

    def fetchone(self) -> Any:
        if self._one is not None:
            return self._one
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return list(self._rows)

    def all(self) -> list[Any]:
        return list(self._rows)

    def first(self) -> Any:
        return self.fetchone()

    def mappings(self) -> "_Result":
        return self


class _AsyncContext:
    def __init__(self, session: "_RecordingSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_RecordingSession":
        return self._session

    async def __aexit__(self, *args: object) -> bool:
        return False


class _RecordingSession:
    """Records every statement and answers the reads the handlers perform.

    The fake agent row is mutable: an executed ``UPDATE agents`` with a role
    bound updates the row in place, so a handler that re-reads the row and one
    that keeps it in memory both answer the new role.
    """

    def __init__(self, row: Any = None, list_rows: list[Any] | None = None) -> None:
        self.row = row
        self.list_rows = list_rows
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def execute(
        self, statement: Any, params: dict[str, Any] | None = None, **kwargs: Any
    ) -> _Result:
        sql = " ".join(str(statement).split())
        bound = dict(params or {})
        self.statements.append((sql, bound))
        lowered = sql.lower()
        upper = sql.lstrip().upper()

        if "set_config" in lowered or "pg_notify" in lowered:
            return _Result()
        if upper.startswith("SELECT") and "from agents" in lowered:
            rows = (
                self.list_rows
                if self.list_rows is not None
                else ([self.row] if self.row is not None else [])
            )
            return _Result(rows=rows, one=self.row)
        if upper.startswith("UPDATE AGENTS"):
            role_values = [
                value for value in bound.values() if value in ("consumer", "publisher")
            ]
            if self.row is not None and len(role_values) == 1:
                self.row.role = role_values[0]
            return _Result()
        return _Result()

    def begin(self) -> _AsyncContext:
        return _AsyncContext(self)

    def begin_nested(self) -> _AsyncContext:
        return _AsyncContext(self)

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def __aenter__(self) -> "_RecordingSession":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False


class _SessionContext:
    def __init__(self) -> None:
        self.operator_id = OP_ID
        self.tenant_id = TENANT_ID


def _session_context() -> _SessionContext:
    return _SessionContext()


def _agent_row(role: object = _MISSING) -> SimpleNamespace:
    attrs: dict[str, Any] = {
        "id": UUID("00000000-0000-0000-0000-000000000022"),
        "tenant_id": TENANT_ID,
        "name": "agent-one",
        "description": "test agent",
        "api_key_fingerprint": "deadbeefdeadbeef",
        "mcp_endpoint": f"http://localhost:8100/v1/agents/{AGENT_ID}",
        "status": "active",
        "rate_limit_rps": None,
        "created_at": None,
        "updated_at": None,
        "grants_count": 0,
        "api_key_expires_at": None,
        "api_key_version": 1,
        "api_key_last_rotated_at": None,
    }
    if role is not _MISSING:
        attrs["role"] = role
    return SimpleNamespace(**attrs)


def _write_statements(session: _RecordingSession) -> list[str]:
    return [
        sql
        for sql, _params in session.statements
        if re.match(r"^(UPDATE|INSERT|DELETE)\b", sql, re.IGNORECASE)
    ]


def _update_calls(session: _RecordingSession) -> list[tuple[str, dict[str, Any]]]:
    return [
        (sql, params)
        for sql, params in session.statements
        if sql.lower().startswith("update agents")
    ]


def _agent_statements(session: _RecordingSession) -> list[str]:
    return [sql for sql, _params in session.statements if "agents" in sql.lower()]


def _make_app(session: _RecordingSession, *, bypass_auth: bool) -> Any:
    from fastapi import FastAPI

    from admin_api.api.agents import router as agents_router
    from admin_api.api.permissions import validation_error_handler
    from admin_api.auth.sessions import get_session_context, require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(agents_router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    async def _db() -> Any:
        yield session

    app.dependency_overrides[get_db_session] = _db

    if bypass_auth:
        async def _no_authz() -> None:
            return None

        async def _context() -> _SessionContext:
            return _session_context()

        app.dependency_overrides[require_tenant_session] = _no_authz
        app.dependency_overrides[get_session_context] = _context

    csrf_exempt(BASE_URL_PATH)
    app.add_middleware(CsrfMiddleware)
    return app


async def _patch_agent(
    session: _RecordingSession,
    body: dict[str, Any],
    *,
    agent_id: str = AGENT_ID,
) -> Any:
    app = _make_app(session, bypass_auth=False)
    with patch(
        "admin_api.auth.sessions.validate_session",
        new=AsyncMock(return_value=_session_context()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.patch(
                f"{BASE_URL_PATH}/{agent_id}",
                json=body,
                cookies={"mintkey_session": SESSION_TOKEN},
            )


# ---------------------------------------------------------------------------
# Agent responses carry the role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-9e9c8771")
async def test_C_9e9c8771_a_new_agent_is_a_consumer() -> None:
    """A created agent answers 201 with role consumer."""
    session = _RecordingSession()
    app = _make_app(session, bypass_auth=True)

    with (
        patch("admin_api.api.agents.audit_emit", new=AsyncMock()),
        patch("admin_api.api.agents.notify_change", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(BASE_URL_PATH, json={"name": "agent-one"})

    assert response.status_code == 201, response.text
    assert response.json().get("role") == "consumer"


@pytest.mark.asyncio
@pytest.mark.l4("C-c082d5b5")
async def test_C_c082d5b5_list_and_get_show_the_stored_role() -> None:
    """List maps the stored role; get defaults a missing role to consumer."""
    publisher = _agent_row("publisher")
    no_role = _agent_row()
    session = _RecordingSession(row=no_role, list_rows=[publisher, no_role])
    app = _make_app(session, bypass_auth=True)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        list_response = await client.get(BASE_URL_PATH)
        default_get = await client.get(f"{BASE_URL_PATH}/{AGENT_ID}")

    assert list_response.status_code == 200, list_response.text
    roles = [agent.get("role") for agent in list_response.json()["agents"]]
    assert roles == ["publisher", "consumer"]

    assert default_get.status_code == 200, default_get.text
    assert default_get.json().get("role") == "consumer"

    publisher_session = _RecordingSession(row=publisher)
    publisher_app = _make_app(publisher_session, bypass_auth=True)
    async with AsyncClient(
        transport=ASGITransport(app=publisher_app), base_url="http://test"
    ) as client:
        publisher_get = await client.get(f"{BASE_URL_PATH}/{AGENT_ID}")

    assert publisher_get.status_code == 200, publisher_get.text
    assert publisher_get.json().get("role") == "publisher"

    agent_selects = [
        sql
        for current in (session, publisher_session)
        for sql, _params in current.statements
        if "from agents" in sql.lower()
    ]
    assert agent_selects, "list and get must select agents"
    assert all("a.role" in sql.lower() for sql in agent_selects), agent_selects


@pytest.mark.asyncio
@pytest.mark.l4("C-d5e95bfc")
async def test_C_d5e95bfc_the_role_filter() -> None:
    """?role=publisher filters the fetched rows; an unknown role is a 422."""
    session = _RecordingSession(
        list_rows=[_agent_row("publisher"), _agent_row("consumer")]
    )
    app = _make_app(session, bypass_auth=True)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        filtered = await client.get(BASE_URL_PATH, params={"role": "publisher"})
        invalid = await client.get(BASE_URL_PATH, params={"role": "admin"})

    assert filtered.status_code == 200, filtered.text
    agents = filtered.json()["agents"]
    assert [agent.get("role") for agent in agents] == ["publisher"]

    assert invalid.status_code == 422, invalid.text
    body = invalid.json()
    assert body.get("mintkey:code") == "validation_failed", body
    assert "detail" not in body, body
    assert isinstance(body.get("title"), str) and body["title"], body


# ---------------------------------------------------------------------------
# An operator sets an agent's role
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-ff21e25a")
async def test_C_ff21e25a_promote_and_demote() -> None:
    """Each change answers 200, runs one UPDATE and writes one audit event."""
    row = _agent_row("consumer")
    session = _RecordingSession(row=row)

    with patch("admin_api.api.agents.audit_emit", new=AsyncMock()) as audit_mock:
        first = await _patch_agent(session, {"role": "publisher"})
        second = await _patch_agent(session, {"role": "consumer"})

    assert first.status_code == 200, first.text
    assert first.json().get("role") == "publisher"
    assert second.status_code == 200, second.text
    assert second.json().get("role") == "consumer"

    writes = _write_statements(session)
    assert len(writes) == 2, writes
    for statement in writes:
        assert statement.lower().startswith("update agents"), statement
        assert "role" in statement.lower(), statement

    updates = _update_calls(session)
    assert len(updates) == 2, updates
    assert "publisher" in updates[0][1].values(), updates[0]
    assert "consumer" in updates[1][1].values(), updates[1]

    assert audit_mock.call_count == 2
    first_event, second_event = audit_mock.call_args_list
    expected = [
        (first_event, "consumer", "publisher"),
        (second_event, "publisher", "consumer"),
    ]
    for call, from_role, to_role in expected:
        assert call.kwargs.get("event_type") == "agent.role.changed"
        assert call.kwargs.get("actor_type") == "operator"
        assert call.kwargs.get("actor_id") == OP_ID
        assert call.kwargs.get("target_type") == "agent"
        payload = call.kwargs.get("payload", {})
        assert payload.get("agent_id") == AGENT_ID
        assert payload.get("from_role") == from_role
        assert payload.get("to_role") == to_role


@pytest.mark.asyncio
@pytest.mark.l4("C-49ba65d0")
async def test_C_49ba65d0_the_same_role_is_nothing_to_do() -> None:
    """Patching a publisher to publisher writes nothing and audits nothing."""
    session = _RecordingSession(row=_agent_row("publisher"))

    with patch("admin_api.api.agents.audit_emit", new=AsyncMock()) as audit_mock:
        response = await _patch_agent(session, {"role": "publisher"})

    assert response.status_code == 200, response.text
    assert response.json().get("role") == "publisher"
    assert _write_statements(session) == []
    audit_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.l4("C-e0cd5c40", "C-cdc7f907")
async def test_C_e0cd5c40_C_cdc7f907_invalid_bodies_are_rejected_flat() -> None:
    """An invalid or over-specified body answers 422 and runs no agent statement."""
    bodies: list[dict[str, Any]] = [
        {"role": "admin"},
        {},
        {"role": "publisher", "status": "revoked"},
    ]

    for body in bodies:
        session = _RecordingSession(row=_agent_row("consumer"))
        response = await _patch_agent(session, body)

        assert response.status_code == 422, (body, response.text)
        answer = response.json()
        assert answer.get("mintkey:code") == "validation_failed", (body, answer)
        assert "detail" not in answer, (body, answer)
        assert isinstance(answer.get("title"), str) and answer["title"], (body, answer)
        assert _agent_statements(session) == [], (body, session.statements)


@pytest.mark.asyncio
@pytest.mark.l4("C-e0cd5c40", "C-cdc7f907")
async def test_C_e0cd5c40_C_cdc7f907_unknown_and_undecodable_agent_ids() -> None:
    """An unknown id is 404 not_found; an undecodable id is 422 invalid_id."""
    unknown_session = _RecordingSession(row=None)
    unknown = await _patch_agent(
        unknown_session, {"role": "publisher"}, agent_id=UNKNOWN_AGENT_ID
    )
    assert unknown.status_code == 404, unknown.text
    unknown_body = unknown.json()
    assert unknown_body.get("mintkey:code") == "not_found", unknown_body
    assert unknown_body.get("title") == "Agent not found", unknown_body
    assert "detail" not in unknown_body, unknown_body
    assert _write_statements(unknown_session) == []

    invalid_session = _RecordingSession(row=_agent_row("consumer"))
    invalid = await _patch_agent(
        invalid_session, {"role": "publisher"}, agent_id=UNDECODABLE_AGENT_ID
    )
    assert invalid.status_code == 422, invalid.text
    invalid_body = invalid.json()
    assert invalid_body.get("mintkey:code") == "invalid_id", invalid_body
    assert invalid_body.get("title") == "Invalid agent_id", invalid_body
    assert "detail" not in invalid_body, invalid_body
    assert _agent_statements(invalid_session) == []


@pytest.mark.asyncio
@pytest.mark.l4("C-0258cfe0")
async def test_C_0258cfe0_no_session_is_401_before_any_statement() -> None:
    """The real session dependency answers 401 and the fake session sees nothing."""
    session = _RecordingSession(row=_agent_row("consumer"))
    app = _make_app(session, bypass_auth=False)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.patch(
            f"{BASE_URL_PATH}/{AGENT_ID}", json={"role": "publisher"}
        )

    assert response.status_code == 401, response.text
    body = response.json()
    assert body.get("detail", {}).get("mintkey:code") == "unauthenticated", body
    assert session.statements == []


# ---------------------------------------------------------------------------
# A demotion changes nothing else
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-3134f611")
async def test_C_3134f611_a_demoted_publisher_keeps_its_services() -> None:
    """Demotion writes only the agents row; services and grants are untouched."""
    row = _agent_row("publisher")
    session = _RecordingSession(row=row)

    with patch("admin_api.api.agents.audit_emit", new=AsyncMock()) as audit_mock:
        response = await _patch_agent(session, {"role": "consumer"})

    assert response.status_code == 200, response.text
    assert response.json().get("role") == "consumer"
    assert audit_mock.call_count == 1
    assert audit_mock.call_args.kwargs.get("event_type") == "agent.role.changed"

    writes = _write_statements(session)
    assert len(writes) == 1, writes
    assert writes[0].lower().startswith("update agents"), writes
    for statement in writes:
        lowered = statement.lower()
        assert "services" not in lowered, statement
        assert "permission_grants" not in lowered, statement

    updates = _update_calls(session)
    assert len(updates) == 1, updates
    assert "consumer" in updates[0][1].values(), updates[0]


# ---------------------------------------------------------------------------
# The agent-key check reports the role
# ---------------------------------------------------------------------------


def _key_check_session(row: Any) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = row
    session.execute = AsyncMock(side_effect=[MagicMock(), result])
    return session


def _key_row(role: object = _MISSING) -> SimpleNamespace:
    attrs: dict[str, Any] = {
        "id": UUID("00000000-0000-0000-0000-000000000022"),
        "tenant_id": TENANT_ID,
        "api_key_hash": "$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        "status": "active",
        "api_key_expires_at": None,
        "api_key_fingerprint": "deadbeefdeadbeef",
    }
    if role is not _MISSING:
        attrs["role"] = role
    return SimpleNamespace(**attrs)


@pytest.mark.asyncio
@pytest.mark.l4("C-284df559")
async def test_C_284df559_validate_agent_key_names_the_role(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An active publisher answers publisher; a row without role answers consumer."""
    from admin_api.api import internal

    async def _verify_ok(_stored_hash: str, _secret: str) -> None:
        return None

    monkeypatch.setattr(internal, "_verify_argon2", _verify_ok)

    publisher_session = _key_check_session(_key_row("publisher"))
    publisher_response = await internal.validate_agent_key(
        internal.ValidateAgentKeyRequest(api_key=API_KEY), publisher_session
    )
    assert publisher_response.status_code == 200
    publisher_body = json.loads(publisher_response.body)
    assert publisher_body.get("role") == "publisher", publisher_body
    assert publisher_session.execute.await_count == 2

    default_session = _key_check_session(_key_row())
    default_response = await internal.validate_agent_key(
        internal.ValidateAgentKeyRequest(api_key=API_KEY), default_session
    )
    assert default_response.status_code == 200
    default_body = json.loads(default_response.body)
    assert default_body.get("role") == "consumer", default_body
    assert default_session.execute.await_count == 2
