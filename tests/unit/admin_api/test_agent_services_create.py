"""Unit tests: a publisher creates and lists its own services.

Task 2.1 of agent-service-routes. The three scenarios of "A publisher creates a
service" and the scenario of "A publisher lists its own services" decide:

  1. a valid create answers 201 with the view of the INSERT ... RETURNING row,
     binds the principal's tenant, agent (owner and creator) and derived slug,
     writes one ``service.registered`` event and one NOTIFY, and sets the
     tenant context first — with no SELECT after the INSERT;
  2. a refused body answers the one agent error body and runs no INSERT;
  3. a taken slug (a row exists, or the INSERT raises ``IntegrityError``)
     answers 409 ``mintkey:slug_conflict``;
  4. the list answers the view of every service the caller owns, with the
     principal's tenant and agent bound as owner, and ``{"services": []}``
     when there is none.

Sources:
  - `openspec/changes/agent-service-routes/spec.md` — A publisher creates a
    service; A publisher lists its own services; Every error of the service
    routes has one body
  - `openspec/changes/agent-service-routes/design.md` — D6, D10, D11
"""

# ruff: noqa: E402 — the service packages are imported after sys.path setup.
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi import FastAPI, Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy.exc import IntegrityError

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
MODELS_SRC = REPO_ROOT / "packages" / "python" / "mintkey-models"
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from admin_api.api import agent_services
from admin_api.auth.agent_principal import (
    AgentApiError,
    AgentPrincipal,
    agent_api_error_handler,
)
from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid
from mintkey_models import egress

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ab")
OTHER_SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ac")

VIEW_KEYS = {
    "id",
    "name",
    "slug",
    "display_name",
    "description",
    "base_url",
    "auth_scheme",
    "openapi_url",
    "status",
    "credential_set",
    "created_at",
    "updated_at",
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    """The slice of a SQLAlchemy result the handlers use."""

    def __init__(
        self,
        row: Any | None = None,
        rows: list[Any] | None = None,
    ) -> None:
        self._row = row
        self._rows = rows if rows is not None else ([] if row is None else [row])

    def fetchone(self) -> Any | None:
        return self._row

    def fetchall(self) -> list[Any]:
        return list(self._rows)


class _FakeSession:
    """Record every statement and answer the service reads like the database.

    The slug pre-check answers a row only when ``slug_taken`` is true; the
    services INSERT returns ``service_row`` or raises ``insert_error``; the
    list SELECT returns ``list_rows``. ``audit_emit`` and ``notify_change``
    run for real against this session, so their statements and parameters are
    recorded like every other statement.
    """

    def __init__(
        self,
        *,
        service_row: Any | None = None,
        slug_taken: bool = False,
        insert_error: Exception | None = None,
        list_rows: list[Any] | None = None,
    ) -> None:
        self.service_row = service_row
        self.slug_taken = slug_taken
        self.insert_error = insert_error
        self.list_rows = list_rows or []
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.audit_events: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []
        self.commits = 0

    async def execute(
        self,
        statement: Any,
        params: Any = None,
        **kwargs: Any,
    ) -> _Result:
        sql = " ".join(str(statement).split())
        bound: dict[str, Any] = params if isinstance(params, dict) else {}
        self.statements.append((sql, bound))
        upper = sql.upper()

        if "INSERT INTO AUDIT_EVENTS" in upper:
            self.audit_events.append(
                {
                    "event_type": bound.get("event_type"),
                    "actor_id": bound.get("actor_id"),
                    "actor_type": bound.get("actor_type"),
                    "payload": json.loads(bound.get("payload") or "{}"),
                }
            )
            return _Result()

        if "PG_NOTIFY" in upper:
            self.notifications.append(
                {
                    "channel": bound.get("channel"),
                    "payload": json.loads(bound.get("payload") or "{}"),
                }
            )
            return _Result()

        if "INSERT INTO SERVICES" in upper:
            if self.insert_error is not None:
                raise self.insert_error
            if self.service_row is not None and bound.get("id") is not None:
                # RETURNING gives back the id the handler generated and bound.
                self.service_row.id = UUID(str(bound["id"]))
            return _Result(row=self.service_row)

        if upper.startswith("SELECT") and "FROM SERVICES" in upper:
            if "OWNER_AGENT_ID" in upper:
                return _Result(rows=self.list_rows)
            if "SLUG" in upper:
                return _Result(
                    row=SimpleNamespace(id=SERVICE_ID) if self.slug_taken else None
                )
            return _Result(row=self.service_row)

        return _Result()

    async def commit(self) -> None:
        self.commits += 1

    async def rollback(self) -> None:
        return None

    async def flush(self) -> None:
        return None


def _principal() -> AgentPrincipal:
    return AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="publisher")


def _service_row(
    *,
    service_id: UUID = SERVICE_ID,
    name: str = "My Service",
    slug: str = "my-service",
    display_name: str | None = "My Service Display",
    credential_set: bool = False,
) -> SimpleNamespace:
    row = SimpleNamespace(
        id=service_id,
        tenant_id=TENANT_ID,
        name=name,
        slug=slug,
        display_name=display_name,
        description="A service",
        base_url="https://api.example.com",
        auth_scheme="bearer_token",
        openapi_url=None,
        status="active",
        owner_agent_id=AGENT_ID,
        created_by_agent_id=AGENT_ID,
        credential_set=credential_set,
    )
    row.created_at = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    row.updated_at = datetime(2026, 2, 3, 4, 5, 7, tzinfo=timezone.utc)
    return row


def _expected_view(row: Any) -> dict[str, Any]:
    return {
        "id": db_uuid_to_wire(row.id, "svc"),
        "name": row.name,
        "slug": row.slug,
        "display_name": row.display_name,
        "description": row.description,
        "base_url": row.base_url,
        "auth_scheme": row.auth_scheme,
        "openapi_url": row.openapi_url,
        "status": row.status,
        "credential_set": row.credential_set,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _client(session: _FakeSession, principal: AgentPrincipal) -> AsyncClient:
    """A bare app serving the two handlers under the real paths."""
    app = FastAPI()
    app.add_exception_handler(AgentApiError, agent_api_error_handler)

    @app.post("/v1/agent/services", status_code=201)
    async def _create(request: Request) -> Any:
        return await agent_services.create_agent_service(request, principal, session)

    @app.get("/v1/agent/services")
    async def _list() -> Any:
        return await agent_services.list_agent_services(principal, session)

    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


def _patch_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve public names publicly and ``private.example.com`` to RFC1918."""

    async def _resolve(host: str) -> list[str]:
        if host == "private.example.com":
            return ["10.0.0.1"]
        return ["93.184.216.34"]

    monkeypatch.setattr(egress, "resolve_host", _resolve)


def _valid_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "My Service",
        "base_url": "https://api.example.com",
        "auth_scheme": "bearer_token",
        "display_name": "My Service Display",
        "description": "A service",
    }
    body.update(overrides)
    return body


def _service_inserts(
    session: _FakeSession,
) -> list[tuple[int, str, dict[str, Any]]]:
    return [
        (index, sql, params)
        for index, (sql, params) in enumerate(session.statements)
        if sql.upper().startswith("INSERT INTO SERVICES")
    ]


# ---------------------------------------------------------------------------
# C-a7c250ac — a service is created
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-a7c250ac")
@pytest.mark.asyncio
async def test_C_a7c250ac_create_returns_returning_row_and_writes_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolver(monkeypatch)
    row = _service_row()
    session = _FakeSession(service_row=row)

    async with _client(session, _principal()) as client:
        response = await client.post("/v1/agent/services", json=_valid_body())

    assert response.status_code == 201, response.text
    body = response.json()
    assert body == _expected_view(row)
    assert set(body) == VIEW_KEYS
    assert body["id"].startswith("svc_")
    assert body["id"] == db_uuid_to_wire(row.id, "svc")
    assert body["credential_set"] is False
    assert body["status"] == "active"
    assert body["created_at"] == row.created_at.isoformat()
    assert body["updated_at"] == row.updated_at.isoformat()

    first_sql, first_params = session.statements[0]
    assert "set_config" in first_sql.lower()
    assert "app.current_tenant" in first_sql
    assert str(TENANT_ID) in first_params.values()

    inserts = _service_inserts(session)
    assert len(inserts) == 1
    insert_index, _insert_sql, insert_params = inserts[0]
    values = list(insert_params.values())
    assert str(TENANT_ID) in values
    assert str(insert_params.get("owner_agent_id")) == str(AGENT_ID)
    assert str(insert_params.get("created_by_agent_id")) == str(AGENT_ID)
    assert sum(1 for value in values if str(value) == str(AGENT_ID)) >= 2
    assert "my-service" in values
    assert wire_to_db_uuid(body["id"], "svc") in {str(value) for value in values}

    later_service_selects = [
        sql
        for sql, _params in session.statements[insert_index + 1 :]
        if sql.upper().startswith("SELECT") and "FROM SERVICES" in sql.upper()
    ]
    assert later_service_selects == []

    assert len(session.audit_events) == 1
    event = session.audit_events[0]
    assert event["event_type"] == "service.registered"
    assert event["actor_id"] == str(AGENT_ID)
    assert event["actor_type"] == "agent"
    assert event["payload"] == {
        "service_id": db_uuid_to_wire(row.id, "svc"),
        "name": "My Service",
        "base_url": "https://api.example.com",
        "auth_scheme": "bearer_token",
        "actions": [],
        "display_name": "My Service Display",
        "owner_agent_id": db_uuid_to_wire(AGENT_ID, "agent"),
    }

    assert len(session.notifications) == 1
    assert session.notifications[0]["channel"] == "mintkey:service"
    assert session.notifications[0]["payload"]["event"] == "service.registered"


@pytest.mark.l4("C-a7c250ac")
@pytest.mark.asyncio
async def test_C_a7c250ac_create_uses_the_name_as_display_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolver(monkeypatch)
    row = _service_row(display_name="My Service")
    session = _FakeSession(service_row=row)
    body = _valid_body()
    del body["display_name"]

    async with _client(session, _principal()) as client:
        response = await client.post("/v1/agent/services", json=body)

    assert response.status_code == 201, response.text
    assert session.audit_events[0]["payload"]["display_name"] == "My Service"


# ---------------------------------------------------------------------------
# C-b190eac4 — refused bodies
# ---------------------------------------------------------------------------


REFUSED_BODIES = [
    pytest.param(
        _valid_body(auth_scheme="ssh_private_key"),
        422,
        "mintkey:validation_failed",
        "Invalid request body",
        "auth_scheme",
        None,
        id="ssh_private_key",
    ),
    pytest.param(
        _valid_body(auth_scheme="oauth2_client_credentials"),
        422,
        "mintkey:validation_failed",
        "Invalid request body",
        "auth_scheme",
        None,
        id="oauth2_client_credentials",
    ),
    pytest.param(
        _valid_body(name="../x"),
        422,
        "mintkey:validation_failed",
        "Invalid request body",
        "name",
        None,
        id="bad_name",
    ),
    pytest.param(
        _valid_body(name="svc_0 x"),
        422,
        "mintkey:validation_failed",
        "Invalid request body",
        "name",
        None,
        id="svc_name",
    ),
    pytest.param(
        _valid_body(owner_agent_id=db_uuid_to_wire(AGENT_ID, "agent")),
        422,
        "mintkey:validation_failed",
        "Invalid request body",
        None,
        None,
        id="extra_owner",
    ),
    pytest.param(
        _valid_body(status="disabled"),
        422,
        "mintkey:validation_failed",
        "Invalid request body",
        None,
        None,
        id="extra_status",
    ),
    pytest.param(
        _valid_body(base_url="http://example.com"),
        400,
        "mintkey:target_not_allowed",
        "Target not allowed",
        "base_url",
        "not_https",
        id="http_url",
    ),
    pytest.param(
        _valid_body(base_url="https://private.example.com"),
        400,
        "mintkey:target_not_allowed",
        "Target not allowed",
        "base_url",
        "non_public_address",
        id="private_url",
    ),
]


@pytest.mark.l4("C-b190eac4")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("body", "status", "code", "title", "field", "reason"),
    REFUSED_BODIES,
)
async def test_C_b190eac4_refused_body_has_one_error_body_and_no_insert(
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, Any],
    status: int,
    code: str,
    title: str,
    field: str | None,
    reason: str | None,
) -> None:
    _patch_resolver(monkeypatch)
    session = _FakeSession(service_row=_service_row())

    async with _client(session, _principal()) as client:
        response = await client.post("/v1/agent/services", json=body)

    assert response.status_code == status, response.text
    answer = response.json()
    assert answer["code"] == code
    assert answer["title"] == title
    assert answer["field"] == field
    if reason is not None:
        assert answer["reason"] == reason
    assert _service_inserts(session) == []


# ---------------------------------------------------------------------------
# C-c7dc1fce — a taken slug
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-c7dc1fce")
@pytest.mark.asyncio
async def test_C_c7dc1fce_existing_slug_conflicts_without_an_insert(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolver(monkeypatch)
    session = _FakeSession(service_row=_service_row(), slug_taken=True)

    async with _client(session, _principal()) as client:
        response = await client.post("/v1/agent/services", json=_valid_body())

    assert response.status_code == 409, response.text
    assert response.json() == {
        "code": "mintkey:slug_conflict",
        "title": "Service name already in use",
    }
    assert _service_inserts(session) == []


@pytest.mark.l4("C-c7dc1fce")
@pytest.mark.asyncio
async def test_C_c7dc1fce_integrity_error_conflicts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_resolver(monkeypatch)
    session = _FakeSession(
        service_row=_service_row(),
        insert_error=IntegrityError("INSERT INTO services", {}, ValueError("taken")),
    )

    async with _client(session, _principal()) as client:
        response = await client.post("/v1/agent/services", json=_valid_body())

    assert response.status_code == 409, response.text
    assert response.json() == {
        "code": "mintkey:slug_conflict",
        "title": "Service name already in use",
    }
    assert len(_service_inserts(session)) == 1


# ---------------------------------------------------------------------------
# C-c4f8c198 — the list is the caller's
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-c4f8c198")
@pytest.mark.asyncio
async def test_C_c4f8c198_list_returns_the_callers_services() -> None:
    first = _service_row(credential_set=True)
    second = _service_row(
        service_id=OTHER_SERVICE_ID,
        name="Other Service",
        slug="other-service",
        display_name="Other Service",
        credential_set=False,
    )
    session = _FakeSession(list_rows=[first, second])

    async with _client(session, _principal()) as client:
        response = await client.get("/v1/agent/services")

    assert response.status_code == 200, response.text
    assert response.json() == {
        "services": [_expected_view(first), _expected_view(second)]
    }

    list_selects = [
        (sql, params)
        for sql, params in session.statements
        if sql.upper().startswith("SELECT") and "FROM SERVICES" in sql.upper()
    ]
    assert len(list_selects) == 1
    sql, params = list_selects[0]
    values = list(params.values())
    assert "OWNER_AGENT_ID" in sql.upper()
    assert str(TENANT_ID) in values
    assert str(AGENT_ID) in values
    assert "ORDER BY" in sql.upper()
    assert "CREATED_AT" in sql.upper()


@pytest.mark.l4("C-c4f8c198")
@pytest.mark.asyncio
async def test_C_c4f8c198_list_without_owned_services_is_empty() -> None:
    session = _FakeSession(list_rows=[])

    async with _client(session, _principal()) as client:
        response = await client.get("/v1/agent/services")

    assert response.status_code == 200, response.text
    assert response.json() == {"services": []}

    list_selects = [
        (sql, params)
        for sql, params in session.statements
        if sql.upper().startswith("SELECT") and "FROM SERVICES" in sql.upper()
    ]
    assert len(list_selects) == 1
    _sql, params = list_selects[0]
    values = list(params.values())
    assert str(TENANT_ID) in values
    assert str(AGENT_ID) in values
