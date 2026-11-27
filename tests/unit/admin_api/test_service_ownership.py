"""
Unit tests: a service's owner in the operator API, and the transfer route.

Requirement: agent-roles-and-ownership
  - Service responses carry the owner (owner fields on the wire, the owner
    filter, an operator-created service has no owner)
  - An operator transfers a service's ownership (to a publisher and back,
    unsuitable targets, the same owner is nothing to do, a missing key)
  - Operators keep full control of every service (editing an agent-owned
    service)
  - The operator routes answer errors in one flat shape (the transfer half)

Sources:
  - `openspec/changes/agent-roles-and-ownership/spec.md`
  - `openspec/changes/agent-roles-and-ownership/design.md` — D2, D5, D6, D9
"""
from __future__ import annotations

import json
import os
import re
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
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

from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_TEXT = str(TENANT_ID)
OP_ID = UUID("00000000-0000-0000-0000-0000000000aa")
SESSION_TOKEN = "00000000-0000-0000-0000-0000000000bb"

AGENT_A_UUID = UUID("00000000-0000-0000-0000-0000000000a1")
AGENT_B_UUID = UUID("00000000-0000-0000-0000-0000000000b2")
AGENT_A = db_uuid_to_wire(AGENT_A_UUID, "agent")
AGENT_B = db_uuid_to_wire(AGENT_B_UUID, "agent")

SERVICE_UUID = UUID("00000000-0000-0000-0000-0000000000c3")
SERVICE_A_UUID = UUID("00000000-0000-0000-0000-0000000000c4")
SERVICE_B_UUID = UUID("00000000-0000-0000-0000-0000000000c5")
SERVICE_NONE_UUID = UUID("00000000-0000-0000-0000-0000000000c6")
SERVICE_ID = db_uuid_to_wire(SERVICE_UUID, "svc")
UNDECODABLE_SERVICE_ID = "svc_" + "I" * 26

BASE_SERVICES_PATH = f"/v1/tenants/{TENANT_TEXT}/services"

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

    def one_or_none(self) -> Any:
        return self.fetchone()

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

    The service row is mutable: an executed ``UPDATE services`` that binds an
    owner updates the row in place, so a second transfer sees the owner the
    first one wrote.
    """

    def __init__(
        self,
        *,
        service_row: Any = None,
        service_rows: list[Any] | None = None,
        agent_row: Any = None,
    ) -> None:
        self.service_row = service_row
        self.service_rows = service_rows
        self.agent_row = agent_row
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
        if upper.startswith("SELECT") and "from services" in lowered:
            if "for update" in lowered:
                row = self.service_row
                return _Result(rows=[row] if row is not None else [], one=row)
            rows = (
                self.service_rows
                if self.service_rows is not None
                else ([self.service_row] if self.service_row is not None else [])
            )
            return _Result(rows=rows, one=rows[0] if rows else None)
        if upper.startswith("SELECT") and "from agents" in lowered:
            row = self.agent_row
            return _Result(rows=[row] if row is not None else [], one=row)
        if upper.startswith("UPDATE SERVICES"):
            owner_values = [
                value for key, value in bound.items() if "owner" in key.lower()
            ]
            if self.service_row is not None and owner_values:
                self.service_row.owner_agent_id = owner_values[0]
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


def _service_row(
    *,
    row_id: UUID = SERVICE_UUID,
    owner: object = _MISSING,
    created_by: object = _MISSING,
) -> SimpleNamespace:
    attrs: dict[str, Any] = {
        "id": row_id,
        "tenant_id": TENANT_ID,
        "name": "svc-one",
        "slug": "svc-one",
        "display_name": "Service One",
        "description": "test service",
        "base_url": "https://api.example.com",
        "auth_scheme": "bearer_token",
        "openapi_url": None,
        "status": "active",
        "current_key_version": 0,
        "created_at": None,
        "updated_at": None,
        "template_id": None,
    }
    if owner is not _MISSING:
        attrs["owner_agent_id"] = owner
    if created_by is not _MISSING:
        attrs["created_by_agent_id"] = created_by
    return SimpleNamespace(**attrs)


def _agent_row(status: str = "active", role: str = "publisher") -> SimpleNamespace:
    return SimpleNamespace(
        id=AGENT_A_UUID,
        tenant_id=TENANT_ID,
        status=status,
        role=role,
    )


def _make_app(session: _RecordingSession, *, bypass_auth: bool) -> Any:
    from fastapi import FastAPI

    from admin_api.api.permissions import validation_error_handler
    from admin_api.api.services import router as services_router
    from admin_api.auth.sessions import get_session_context, require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(services_router)
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

    csrf_exempt(BASE_SERVICES_PATH)
    csrf_exempt(f"{BASE_SERVICES_PATH}/{SERVICE_ID}/transfer")
    app.add_middleware(CsrfMiddleware)
    return app


async def _transfer(
    session: _RecordingSession,
    body: dict[str, Any],
    *,
    service_id: str = SERVICE_ID,
    bypass_auth: bool = True,
) -> Any:
    app = _make_app(session, bypass_auth=bypass_auth)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        kwargs: dict[str, Any] = {"json": body}
        if bypass_auth:
            kwargs["cookies"] = {"mintkey_session": SESSION_TOKEN}
        return await client.post(
            f"{BASE_SERVICES_PATH}/{service_id}/transfer", **kwargs
        )


def _write_statements(session: _RecordingSession) -> list[str]:
    return [
        sql
        for sql, _params in session.statements
        if re.match(r"^(UPDATE|INSERT|DELETE)\b", sql, re.IGNORECASE)
    ]


def _service_updates(
    session: _RecordingSession,
) -> list[tuple[str, dict[str, Any]]]:
    return [
        (sql, params)
        for sql, params in session.statements
        if sql.lower().startswith("update services")
    ]


def _update_statements(session: _RecordingSession) -> list[str]:
    return [
        sql
        for sql, _params in session.statements
        if sql.lower().startswith("update")
    ]


def _notify_parts(call: Any) -> tuple[Any, Any]:
    """Return (channel, payload) whether notify_change was called by args or kwargs."""
    if len(call.args) >= 3:
        return call.args[1], call.args[2]
    return call.kwargs.get("channel"), call.kwargs.get("payload")


# ---------------------------------------------------------------------------
# Service responses carry the owner
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-653b35d0")
async def test_C_653b35d0_owner_fields_on_the_wire() -> None:
    """The list shows the owner as a wire id, null when absent, and selects both columns."""
    with_owner = _service_row(owner=AGENT_A_UUID, created_by=AGENT_B_UUID)
    without_owner = _service_row(
        row_id=SERVICE_NONE_UUID, owner=_MISSING, created_by=_MISSING
    )
    session = _RecordingSession(service_rows=[with_owner, without_owner])
    app = _make_app(session, bypass_auth=True)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            BASE_SERVICES_PATH, cookies={"mintkey_session": SESSION_TOKEN}
        )

    assert response.status_code == 200, response.text
    services = response.json()["services"]
    assert len(services) == 2

    assert services[0].get("owner_agent_id") == AGENT_A
    assert services[0].get("created_by_agent_id") == AGENT_B
    assert "owner_agent_id" in services[1], services[1]
    assert "created_by_agent_id" in services[1], services[1]
    assert services[1]["owner_agent_id"] is None
    assert services[1]["created_by_agent_id"] is None

    selects = [
        sql for sql, _params in session.statements if "from services" in sql.lower()
    ]
    assert selects, "the list must select services"
    for sql in selects:
        assert "owner_agent_id" in sql.lower(), sql
        assert "created_by_agent_id" in sql.lower(), sql


@pytest.mark.asyncio
@pytest.mark.l4("C-552cb965")
async def test_C_552cb965_the_owner_filter() -> None:
    """?owner_agent_id filters by owner, `operators` selects null, anything else is 422."""
    rows = [
        _service_row(row_id=SERVICE_A_UUID, owner=AGENT_A_UUID, created_by=None),
        _service_row(row_id=SERVICE_B_UUID, owner=AGENT_B_UUID, created_by=None),
        _service_row(
            row_id=SERVICE_NONE_UUID, owner=None, created_by=None
        ),
    ]
    app = _make_app(_RecordingSession(service_rows=rows), bypass_auth=True)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        agent_a = await client.get(
            BASE_SERVICES_PATH,
            params={"owner_agent_id": AGENT_A},
            cookies={"mintkey_session": SESSION_TOKEN},
        )
        operators = await client.get(
            BASE_SERVICES_PATH,
            params={"owner_agent_id": "operators"},
            cookies={"mintkey_session": SESSION_TOKEN},
        )
        invalid = await client.get(
            BASE_SERVICES_PATH,
            params={"owner_agent_id": "not-an-id"},
            cookies={"mintkey_session": SESSION_TOKEN},
        )

    assert agent_a.status_code == 200, agent_a.text
    assert [s["id"] for s in agent_a.json()["services"]] == [
        db_uuid_to_wire(SERVICE_A_UUID, "svc")
    ]

    assert operators.status_code == 200, operators.text
    assert [s["id"] for s in operators.json()["services"]] == [
        db_uuid_to_wire(SERVICE_NONE_UUID, "svc")
    ]

    assert invalid.status_code == 422, invalid.text
    body = invalid.json()
    assert body.get("mintkey:code") == "invalid_id", body
    assert body.get("title") == "Invalid owner_agent_id", body
    assert "detail" not in body, body


@pytest.mark.asyncio
@pytest.mark.l4("C-7a95ce0a")
async def test_C_7a95ce0a_an_operator_created_service_has_no_owner() -> None:
    """The INSERT names no owner columns and the created object carries both as null."""
    session = _RecordingSession()
    app = _make_app(session, bypass_auth=True)

    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                BASE_SERVICES_PATH,
                json={
                    "name": "openai",
                    "base_url": "https://api.openai.com",
                    "auth_scheme": "bearer_token",
                },
                cookies={"mintkey_session": SESSION_TOKEN},
            )

    assert response.status_code == 201, response.text
    body = response.json()
    assert "owner_agent_id" in body, body
    assert "created_by_agent_id" in body, body
    assert body["owner_agent_id"] is None, body
    assert body["created_by_agent_id"] is None, body

    inserts = [
        sql
        for sql, _params in session.statements
        if sql.lower().startswith("insert into services")
    ]
    assert inserts, "creating a service must insert it"
    for sql in inserts:
        lowered = sql.lower()
        assert "owner_agent_id" not in lowered, sql
        assert "created_by_agent_id" not in lowered, sql


# ---------------------------------------------------------------------------
# An operator transfers a service's ownership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-4e0f1239")
async def test_C_4e0f1239_to_a_publisher_and_back_to_operators() -> None:
    """Two transfers write the owner, audit both movements and publish both NOTIFYs."""
    service = _service_row(owner=None, created_by=None)
    session = _RecordingSession(service_row=service, agent_row=_agent_row())

    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
        patch("admin_api.api.services.notify_change", new=AsyncMock()) as notify_mock,
    ):
        first = await _transfer(session, {"to_agent_id": AGENT_A})
        second = await _transfer(session, {"to_agent_id": None})

    assert first.status_code == 200, first.text
    assert first.json().get("owner_agent_id") == AGENT_A, first.text
    assert second.status_code == 200, second.text
    second_body = second.json()
    assert "owner_agent_id" in second_body, second_body
    assert second_body["owner_agent_id"] is None, second_body

    updates = _service_updates(session)
    assert len(updates) == 2, updates
    expected_owner = wire_to_db_uuid(AGENT_A, "agent")
    expected_service = wire_to_db_uuid(SERVICE_ID, "svc")
    assert expected_owner in updates[0][1].values(), updates[0]
    assert expected_service in updates[0][1].values(), updates[0]
    assert None in updates[1][1].values(), updates[1]
    assert expected_owner not in updates[1][1].values(), updates[1]

    events = audit_mock.call_args_list
    assert len(events) == 2, events
    for call, from_agent, to_agent in (
        (events[0], None, AGENT_A),
        (events[1], AGENT_A, None),
    ):
        kwargs = call.kwargs
        assert kwargs.get("event_type") == "service.ownership_transferred", kwargs
        assert kwargs.get("actor_type") == "operator", kwargs
        assert kwargs.get("target_type") == "service", kwargs
        payload = kwargs.get("payload", {})
        assert payload.get("service_id") == SERVICE_ID, payload
        assert payload.get("from_agent_id") == from_agent, payload
        assert payload.get("to_agent_id") == to_agent, payload

    first_payload = {
        "event": "service.ownership_transferred",
        "tenant_id": TENANT_TEXT,
        "service_id": SERVICE_ID,
        "from_agent_id": None,
        "to_agent_id": AGENT_A,
    }
    second_payload = {
        "event": "service.ownership_transferred",
        "tenant_id": TENANT_TEXT,
        "service_id": SERVICE_ID,
        "from_agent_id": AGENT_A,
        "to_agent_id": None,
    }
    notify_calls = notify_mock.call_args_list
    assert len(notify_calls) == 2, notify_calls
    for call, expected_payload in zip(
        notify_calls, (first_payload, second_payload), strict=True
    ):
        channel, payload = _notify_parts(call)
        assert channel == "mintkey:service", call
        assert payload == expected_payload, call
        json.dumps(payload)

    service_selects = [
        sql
        for sql, _params in session.statements
        if sql.lower().startswith("select") and "from services" in sql.lower()
    ]
    assert any("for update" in sql.lower() for sql in service_selects), service_selects

    for sql, _params in session.statements:
        lowered = sql.lower()
        assert "credentials" not in lowered, sql
        assert "permission_grants" not in lowered, sql


@pytest.mark.asyncio
@pytest.mark.l4("C-2e9cfe5e")
async def test_C_2e9cfe5e_unsuitable_targets() -> None:
    """A consumer, a revoked publisher or consumer, a missing agent and a missing service all refuse."""
    cases: list[tuple[str, Any, Any, int, str, str | None]] = [
        (
            "active consumer",
            _service_row(owner=None, created_by=None),
            _agent_row(status="active", role="consumer"),
            422,
            "agent_not_publisher",
            "agent_not_publisher",
        ),
        (
            "revoked publisher",
            _service_row(owner=None, created_by=None),
            _agent_row(status="revoked", role="publisher"),
            422,
            "agent_not_active",
            "agent_not_active",
        ),
        (
            "revoked consumer",
            _service_row(owner=None, created_by=None),
            _agent_row(status="revoked", role="consumer"),
            422,
            "agent_not_active",
            "agent_not_active",
        ),
        (
            "agent of another tenant",
            _service_row(owner=None, created_by=None),
            None,
            404,
            "not_found",
            None,
        ),
        (
            "unknown service",
            None,
            _agent_row(),
            404,
            "not_found",
            None,
        ),
    ]

    for name, service, agent, status_code, code, reason in cases:
        session = _RecordingSession(service_row=service, agent_row=agent)
        with (
            patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
            patch(
                "admin_api.api.services.notify_change", new=AsyncMock()
            ) as notify_mock,
        ):
            response = await _transfer(session, {"to_agent_id": AGENT_A})

        assert response.status_code == status_code, (name, response.text)
        body = response.json()
        assert body.get("mintkey:code") == code, (name, body)
        if reason is not None:
            assert body.get("reason") == reason, (name, body)
            assert body.get("title") == "Transfer target not allowed", (name, body)
        assert "detail" not in body, (name, body)

        assert _update_statements(session) == [], (name, session.statements)
        audit_mock.assert_not_called()
        notify_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.l4("C-8c6159c9")
async def test_C_8c6159c9_the_same_owner_is_nothing_to_do() -> None:
    """Transferring to the current owner answers 200 and writes nothing, even when demoted."""
    owned = _service_row(owner=AGENT_A_UUID, created_by=None)
    owned_session = _RecordingSession(
        service_row=owned, agent_row=_agent_row(status="revoked", role="consumer")
    )
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
        patch("admin_api.api.services.notify_change", new=AsyncMock()) as notify_mock,
    ):
        same_owner = await _transfer(owned_session, {"to_agent_id": AGENT_A})

    assert same_owner.status_code == 200, same_owner.text
    assert same_owner.json().get("owner_agent_id") == AGENT_A, same_owner.text
    assert _write_statements(owned_session) == [], owned_session.statements
    agent_selects = [
        sql
        for sql, _params in owned_session.statements
        if "from agents" in sql.lower()
    ]
    assert agent_selects == [], agent_selects
    audit_mock.assert_not_called()
    notify_mock.assert_not_called()

    unowned = _service_row(owner=None, created_by=None)
    unowned_session = _RecordingSession(service_row=unowned, agent_row=_agent_row())
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
        patch("admin_api.api.services.notify_change", new=AsyncMock()) as notify_mock,
    ):
        to_operators = await _transfer(unowned_session, {"to_agent_id": None})

    assert to_operators.status_code == 200, to_operators.text
    to_operators_body = to_operators.json()
    assert "owner_agent_id" in to_operators_body, to_operators_body
    assert to_operators_body["owner_agent_id"] is None, to_operators_body
    assert _write_statements(unowned_session) == [], unowned_session.statements
    audit_mock.assert_not_called()
    notify_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.l4("C-2d4dae42")
async def test_C_2d4dae42_a_missing_key_is_refused() -> None:
    """A body without the key or with a non-string id is 422; no cookie is 401 before any statement."""
    bodies: list[dict[str, Any]] = [{}, {"to_agent_id": 7}]
    for body in bodies:
        session = _RecordingSession(
            service_row=_service_row(owner=None, created_by=None),
            agent_row=_agent_row(),
        )
        with (
            patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
            patch(
                "admin_api.api.services.notify_change", new=AsyncMock()
            ) as notify_mock,
        ):
            response = await _transfer(session, body)

        assert response.status_code == 422, (body, response.text)
        answer = response.json()
        assert answer.get("mintkey:code") == "validation_failed", (body, answer)
        assert "detail" not in answer, (body, answer)
        assert isinstance(answer.get("title"), str) and answer["title"], (body, answer)
        assert _write_statements(session) == [], (body, session.statements)
        audit_mock.assert_not_called()
        notify_mock.assert_not_called()

    session = _RecordingSession(
        service_row=_service_row(owner=None, created_by=None),
        agent_row=_agent_row(),
    )
    anonymous = await _transfer(
        session, {"to_agent_id": AGENT_A}, bypass_auth=False
    )

    assert anonymous.status_code == 401, anonymous.text
    body = anonymous.json()
    assert body.get("detail", {}).get("mintkey:code") == "unauthenticated", body
    assert session.statements == []


# ---------------------------------------------------------------------------
# Operators keep full control of every service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-717163aa")
async def test_C_717163aa_an_operator_edits_an_agent_owned_service() -> None:
    """Patching the description keeps the owner and the UPDATE never writes it."""
    service = _service_row(owner=AGENT_A_UUID, created_by=AGENT_B_UUID)
    session = _RecordingSession(service_row=service)
    app = _make_app(session, bypass_auth=True)

    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.patch(
                f"{BASE_SERVICES_PATH}/{SERVICE_ID}",
                json={"description": "a new description"},
                cookies={"mintkey_session": SESSION_TOKEN},
            )

    assert response.status_code == 200, response.text
    assert response.json().get("owner_agent_id") == AGENT_A, response.text

    updates = _service_updates(session)
    assert len(updates) == 1, updates
    assert "owner_agent_id" not in updates[0][0].lower(), updates[0]


# ---------------------------------------------------------------------------
# The operator routes answer errors in one flat shape (the transfer half)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-cdc7f907")
async def test_C_cdc7f907_the_transfer_error_bodies_are_flat() -> None:
    """A consumer target, an unknown service and an undecodable service id answer flat."""
    consumer_session = _RecordingSession(
        service_row=_service_row(owner=None, created_by=None),
        agent_row=_agent_row(status="active", role="consumer"),
    )
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        consumer_target = await _transfer(
            consumer_session, {"to_agent_id": AGENT_A}
        )

    assert consumer_target.status_code == 422, consumer_target.text
    consumer_body = consumer_target.json()
    assert consumer_body.get("mintkey:code") == "invalid_transfer_target", consumer_body
    assert consumer_body.get("title") == "Transfer target not allowed", consumer_body
    assert consumer_body.get("reason") == "agent_not_publisher", consumer_body
    assert "detail" not in consumer_body, consumer_body

    unknown_session = _RecordingSession(
        service_row=None, agent_row=_agent_row()
    )
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        unknown_service = await _transfer(
            unknown_session, {"to_agent_id": AGENT_A}
        )

    assert unknown_service.status_code == 404, unknown_service.text
    unknown_body = unknown_service.json()
    assert unknown_body.get("mintkey:code") == "not_found", unknown_body
    assert unknown_body.get("title") == "Service not found", unknown_body
    assert "detail" not in unknown_body, unknown_body

    invalid_session = _RecordingSession(
        service_row=_service_row(owner=None, created_by=None),
        agent_row=_agent_row(),
    )
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        invalid_service = await _transfer(
            invalid_session,
            {"to_agent_id": AGENT_A},
            service_id=UNDECODABLE_SERVICE_ID,
        )

    assert invalid_service.status_code == 422, invalid_service.text
    invalid_body = invalid_service.json()
    assert invalid_body.get("mintkey:code") == "invalid_id", invalid_body
    assert invalid_body.get("title") == "Invalid service_id", invalid_body
    assert "detail" not in invalid_body, invalid_body
    assert _write_statements(invalid_session) == [], invalid_session.statements


# ---------------------------------------------------------------------------
# This step's red tests (new names). The frozen tests above keep their bodies;
# these restate the same scenarios, with the unsuitable-target bodies per the
# answered Q-002: an unsuitable target answers invalid_transfer_target with its
# reason. They reuse the helpers of this file and add no module-level code.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-653b35d0")
async def test_C_653b35d0_owner_fields_are_on_the_service_objects() -> None:
    """A set owner shows as the agent_ wire id; a row without the columns shows null twice."""
    with_owner = _service_row(owner=AGENT_A_UUID)
    without_columns = _service_row(row_id=SERVICE_NONE_UUID)
    session = _RecordingSession(service_rows=[with_owner, without_columns])
    app = _make_app(session, bypass_auth=True)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get(
            BASE_SERVICES_PATH, cookies={"mintkey_session": SESSION_TOKEN}
        )

    assert response.status_code == 200, response.text
    services = response.json()["services"]
    assert len(services) == 2

    assert "owner_agent_id" in services[0], services[0]
    assert services[0].get("owner_agent_id") == AGENT_A, services[0]
    assert "created_by_agent_id" in services[0], services[0]
    assert services[0].get("created_by_agent_id") is None, services[0]

    assert "owner_agent_id" in services[1], services[1]
    assert services[1].get("owner_agent_id") is None, services[1]
    assert "created_by_agent_id" in services[1], services[1]
    assert services[1].get("created_by_agent_id") is None, services[1]

    selects = [
        sql for sql, _params in session.statements if "from services" in sql.lower()
    ]
    assert selects, "the list must select services"
    for sql in selects:
        assert "owner_agent_id" in sql.lower(), sql
        assert "created_by_agent_id" in sql.lower(), sql


@pytest.mark.asyncio
@pytest.mark.l4("C-552cb965")
async def test_C_552cb965_owner_agent_id_filter_answers() -> None:
    """?owner_agent_id keeps one owner's rows, `operators` the null ones, else 422 invalid_id."""
    rows = [
        _service_row(row_id=SERVICE_A_UUID, owner=AGENT_A_UUID, created_by=None),
        _service_row(row_id=SERVICE_B_UUID, owner=AGENT_B_UUID, created_by=None),
        _service_row(row_id=SERVICE_NONE_UUID, owner=None, created_by=None),
    ]
    session = _RecordingSession(service_rows=rows)
    app = _make_app(session, bypass_auth=True)

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        agent_a = await client.get(
            BASE_SERVICES_PATH,
            params={"owner_agent_id": AGENT_A},
            cookies={"mintkey_session": SESSION_TOKEN},
        )
        operators = await client.get(
            BASE_SERVICES_PATH,
            params={"owner_agent_id": "operators"},
            cookies={"mintkey_session": SESSION_TOKEN},
        )
        invalid = await client.get(
            BASE_SERVICES_PATH,
            params={"owner_agent_id": "not-an-id"},
            cookies={"mintkey_session": SESSION_TOKEN},
        )

    assert agent_a.status_code == 200, agent_a.text
    assert [s["id"] for s in agent_a.json()["services"]] == [
        db_uuid_to_wire(SERVICE_A_UUID, "svc")
    ], agent_a.text

    assert operators.status_code == 200, operators.text
    assert [s["id"] for s in operators.json()["services"]] == [
        db_uuid_to_wire(SERVICE_NONE_UUID, "svc")
    ], operators.text

    assert invalid.status_code == 422, invalid.text
    body = invalid.json()
    assert body.get("mintkey:code") == "invalid_id", body
    assert body.get("title") == "Invalid owner_agent_id", body
    assert "detail" not in body, body


@pytest.mark.asyncio
@pytest.mark.l4("C-7a95ce0a")
async def test_C_7a95ce0a_create_service_inserts_no_owner_columns() -> None:
    """The create INSERT names no owner column and the created object carries both as null."""
    session = _RecordingSession()
    app = _make_app(session, bypass_auth=True)

    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                BASE_SERVICES_PATH,
                json={
                    "name": "stripe",
                    "base_url": "https://api.stripe.com",
                    "auth_scheme": "bearer_token",
                },
                cookies={"mintkey_session": SESSION_TOKEN},
            )

    assert response.status_code == 201, response.text
    body = response.json()
    assert "owner_agent_id" in body, body
    assert body.get("owner_agent_id") is None, body
    assert "created_by_agent_id" in body, body
    assert body.get("created_by_agent_id") is None, body

    inserts = [
        sql
        for sql, _params in session.statements
        if sql.lower().startswith("insert into services")
    ]
    assert inserts, "creating a service must insert it"
    for sql in inserts:
        lowered = sql.lower()
        assert "owner_agent_id" not in lowered, sql
        assert "created_by_agent_id" not in lowered, sql


@pytest.mark.asyncio
@pytest.mark.l4("C-4e0f1239")
async def test_C_4e0f1239_transfer_moves_ownership_to_publisher_and_back() -> None:
    """To an active publisher then to operators: two UPDATEs, two events, two NOTIFYs."""
    service = _service_row(owner=None, created_by=None)
    session = _RecordingSession(service_row=service, agent_row=_agent_row())

    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
        patch("admin_api.api.services.notify_change", new=AsyncMock()) as notify_mock,
    ):
        to_publisher = await _transfer(session, {"to_agent_id": AGENT_A})
        to_operators = await _transfer(session, {"to_agent_id": None})

    assert to_publisher.status_code == 200, to_publisher.text
    assert to_publisher.json().get("owner_agent_id") == AGENT_A, to_publisher.text
    assert to_operators.status_code == 200, to_operators.text
    assert to_operators.json().get("owner_agent_id") is None, to_operators.text

    updates = _service_updates(session)
    assert len(updates) == 2, updates
    owner_uuid = wire_to_db_uuid(AGENT_A, "agent")
    assert owner_uuid in updates[0][1].values(), updates[0]
    assert wire_to_db_uuid(SERVICE_ID, "svc") in updates[0][1].values(), updates[0]
    assert "tenant_id" in updates[0][0].lower(), updates[0]
    assert None in updates[1][1].values(), updates[1]
    assert owner_uuid not in updates[1][1].values(), updates[1]

    events = audit_mock.call_args_list
    assert len(events) == 2, events
    for call, from_agent, to_agent in (
        (events[0], None, AGENT_A),
        (events[1], AGENT_A, None),
    ):
        kwargs = call.kwargs
        assert kwargs.get("event_type") == "service.ownership_transferred", kwargs
        assert kwargs.get("actor_type") == "operator", kwargs
        assert kwargs.get("target_type") == "service", kwargs
        payload = kwargs.get("payload", {})
        assert payload.get("service_id") == SERVICE_ID, payload
        assert payload.get("from_agent_id") == from_agent, payload
        assert payload.get("to_agent_id") == to_agent, payload

    expected_notify_payloads = (
        {
            "event": "service.ownership_transferred",
            "tenant_id": TENANT_TEXT,
            "service_id": SERVICE_ID,
            "from_agent_id": None,
            "to_agent_id": AGENT_A,
        },
        {
            "event": "service.ownership_transferred",
            "tenant_id": TENANT_TEXT,
            "service_id": SERVICE_ID,
            "from_agent_id": AGENT_A,
            "to_agent_id": None,
        },
    )
    notify_calls = notify_mock.call_args_list
    assert len(notify_calls) == 2, notify_calls
    for call, expected_payload in zip(
        notify_calls, expected_notify_payloads, strict=True
    ):
        channel, payload = _notify_parts(call)
        assert channel == "mintkey:service", call
        assert payload == expected_payload, call
        json.dumps(payload)

    service_selects = [
        sql
        for sql, _params in session.statements
        if sql.lower().startswith("select") and "from services" in sql.lower()
    ]
    assert service_selects, session.statements
    assert any("for update" in sql.lower() for sql in service_selects), (
        service_selects
    )

    for sql, _params in session.statements:
        lowered = sql.lower()
        assert "credentials" not in lowered, sql
        assert "permission_grants" not in lowered, sql


@pytest.mark.asyncio
@pytest.mark.l4("C-2e9cfe5e")
async def test_C_2e9cfe5e_transfer_rejects_unsuitable_targets_flat() -> None:
    """A consumer, a revoked agent, a foreign agent and an unknown service write nothing.

    Per the answered Q-002 the three 422 bodies carry mintkey:code
    invalid_transfer_target with the reason kept.
    """
    cases: list[tuple[str, Any, Any, int, str | None, str | None]] = [
        (
            "active consumer",
            _service_row(owner=None, created_by=None),
            _agent_row(status="active", role="consumer"),
            422,
            "invalid_transfer_target",
            "agent_not_publisher",
        ),
        (
            "revoked publisher",
            _service_row(owner=None, created_by=None),
            _agent_row(status="revoked", role="publisher"),
            422,
            "invalid_transfer_target",
            "agent_not_active",
        ),
        (
            "revoked consumer",
            _service_row(owner=None, created_by=None),
            _agent_row(status="revoked", role="consumer"),
            422,
            "invalid_transfer_target",
            "agent_not_active",
        ),
        (
            "agent of another tenant",
            _service_row(owner=None, created_by=None),
            None,
            404,
            "not_found",
            None,
        ),
        (
            "unknown service",
            None,
            _agent_row(),
            404,
            "not_found",
            None,
        ),
    ]

    for name, service, agent, status_code, code, reason in cases:
        session = _RecordingSession(service_row=service, agent_row=agent)
        with (
            patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
            patch(
                "admin_api.api.services.notify_change", new=AsyncMock()
            ) as notify_mock,
        ):
            response = await _transfer(session, {"to_agent_id": AGENT_A})

        assert response.status_code == status_code, (name, response.text)
        body = response.json()
        assert body.get("mintkey:code") == code, (name, body)
        assert "detail" not in body, (name, body)
        if reason is not None:
            assert body.get("title") == "Transfer target not allowed", (name, body)
            assert body.get("reason") == reason, (name, body)

        assert _update_statements(session) == [], (name, session.statements)
        audit_mock.assert_not_called()
        notify_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.l4("C-8c6159c9")
async def test_C_8c6159c9_transfer_to_the_same_owner_writes_nothing() -> None:
    """The current owner (even a revoked consumer) and `null` both answer 200 and write nothing."""
    owned = _service_row(owner=AGENT_A_UUID, created_by=None)
    owned_session = _RecordingSession(
        service_row=owned, agent_row=_agent_row(status="revoked", role="consumer")
    )
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
        patch("admin_api.api.services.notify_change", new=AsyncMock()) as notify_mock,
    ):
        same_owner = await _transfer(owned_session, {"to_agent_id": AGENT_A})

    assert same_owner.status_code == 200, same_owner.text
    assert same_owner.json().get("owner_agent_id") == AGENT_A, same_owner.text
    assert _write_statements(owned_session) == [], owned_session.statements
    assert not any(
        "from agents" in sql.lower() for sql, _params in owned_session.statements
    ), owned_session.statements
    audit_mock.assert_not_called()
    notify_mock.assert_not_called()

    unowned = _service_row(owner=None, created_by=None)
    unowned_session = _RecordingSession(service_row=unowned, agent_row=_agent_row())
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
        patch("admin_api.api.services.notify_change", new=AsyncMock()) as notify_mock,
    ):
        to_operators = await _transfer(unowned_session, {"to_agent_id": None})

    assert to_operators.status_code == 200, to_operators.text
    assert to_operators.json().get("owner_agent_id") is None, to_operators.text
    assert _write_statements(unowned_session) == [], unowned_session.statements
    assert not any(
        "from agents" in sql.lower() for sql, _params in unowned_session.statements
    ), unowned_session.statements
    audit_mock.assert_not_called()
    notify_mock.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.l4("C-2d4dae42")
async def test_C_2d4dae42_transfer_without_to_agent_id_is_refused() -> None:
    """A body without the key, a non-string id and a missing session all stop before a statement."""
    for body in ({}, {"to_agent_id": 7}):
        session = _RecordingSession(
            service_row=_service_row(owner=None, created_by=None),
            agent_row=_agent_row(),
        )
        with (
            patch("admin_api.api.services.audit_emit", new=AsyncMock()) as audit_mock,
            patch(
                "admin_api.api.services.notify_change", new=AsyncMock()
            ) as notify_mock,
        ):
            response = await _transfer(session, body)

        assert response.status_code == 422, (body, response.text)
        answer = response.json()
        assert answer.get("mintkey:code") == "validation_failed", (body, answer)
        assert isinstance(answer.get("title"), str) and answer["title"], (body, answer)
        assert "detail" not in answer, (body, answer)
        assert _write_statements(session) == [], (body, session.statements)
        audit_mock.assert_not_called()
        notify_mock.assert_not_called()

    session = _RecordingSession(
        service_row=_service_row(owner=None, created_by=None),
        agent_row=_agent_row(),
    )
    anonymous = await _transfer(session, {"to_agent_id": AGENT_A}, bypass_auth=False)

    assert anonymous.status_code == 401, anonymous.text
    body = anonymous.json()
    assert body.get("detail", {}).get("mintkey:code") == "unauthenticated", body
    assert session.statements == [], session.statements


@pytest.mark.asyncio
@pytest.mark.l4("C-717163aa")
async def test_C_717163aa_operator_service_update_never_writes_the_owner() -> None:
    """Patching the description of an agent-owned service answers 200 without writing the owner."""
    service = _service_row(owner=AGENT_A_UUID, created_by=AGENT_B_UUID)
    session = _RecordingSession(service_row=service)
    app = _make_app(session, bypass_auth=True)

    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.patch(
                f"{BASE_SERVICES_PATH}/{SERVICE_ID}",
                json={"description": "owned but still editable"},
                cookies={"mintkey_session": SESSION_TOKEN},
            )

    assert response.status_code == 200, response.text
    assert response.json().get("owner_agent_id") == AGENT_A, response.text

    updates = _service_updates(session)
    assert len(updates) == 1, updates
    assert "owner_agent_id" not in updates[0][0].lower(), updates[0]


@pytest.mark.asyncio
@pytest.mark.l4("C-cdc7f907")
async def test_C_cdc7f907_transfer_errors_answer_flat_at_top_level() -> None:
    """A consumer target, an unknown service and an undecodable id answer flat JSON objects."""
    consumer_session = _RecordingSession(
        service_row=_service_row(owner=None, created_by=None),
        agent_row=_agent_row(status="active", role="consumer"),
    )
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        consumer_target = await _transfer(consumer_session, {"to_agent_id": AGENT_A})

    assert consumer_target.status_code == 422, consumer_target.text
    consumer_body = consumer_target.json()
    assert consumer_body.get("mintkey:code") == "invalid_transfer_target", (
        consumer_body
    )
    assert consumer_body.get("title") == "Transfer target not allowed", consumer_body
    assert consumer_body.get("reason") == "agent_not_publisher", consumer_body
    assert "detail" not in consumer_body, consumer_body

    unknown_session = _RecordingSession(service_row=None, agent_row=_agent_row())
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        unknown_service = await _transfer(unknown_session, {"to_agent_id": AGENT_A})

    assert unknown_service.status_code == 404, unknown_service.text
    unknown_body = unknown_service.json()
    assert unknown_body.get("mintkey:code") == "not_found", unknown_body
    assert unknown_body.get("title") == "Service not found", unknown_body
    assert "detail" not in unknown_body, unknown_body

    invalid_session = _RecordingSession(
        service_row=_service_row(owner=None, created_by=None),
        agent_row=_agent_row(),
    )
    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        invalid_service = await _transfer(
            invalid_session,
            {"to_agent_id": AGENT_A},
            service_id=UNDECODABLE_SERVICE_ID,
        )

    assert invalid_service.status_code == 422, invalid_service.text
    invalid_body = invalid_service.json()
    assert invalid_body.get("mintkey:code") == "invalid_id", invalid_body
    assert invalid_body.get("title") == "Invalid service_id", invalid_body
    assert "detail" not in invalid_body, invalid_body
    assert _write_statements(invalid_session) == [], invalid_session.statements
