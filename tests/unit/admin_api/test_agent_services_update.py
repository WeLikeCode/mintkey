"""Unit tests: a publisher updates only its own services.

Task 3.1 of agent-service-routes. The five scenarios of "A publisher updates
only its own services" decide:

  1. a metadata edit keeps the credential and answers the row the UPDATE
     returned; a changed target (``base_url`` or ``auth_scheme``) deletes the
     vault and metadata credential rows, clears the flag and writes the clear
     event;
  2. a changed target without a credential deletes without the clear event; a
     repeated value is no change at all; a refused target writes nothing;
  3. a service of another agent or of none answers 403, one of another tenant
     or an unknown slug answers 404, and no UPDATE runs;
  4. a body that is empty, has an unknown key or an unsupported scheme answers
     the one 422 and runs no statement for the service;
  5. the first service statement after the tenant context locks the row
     (``FOR UPDATE``), and every UPDATE and DELETE comes after it.

Sources:
  - `openspec/changes/agent-service-routes/spec.md` — A publisher updates only
    its own services; Every error of the service routes has one body
  - `openspec/changes/agent-service-routes/design.md` — D3, D6, D7, D10, D11
"""

# ruff: noqa: E402 — the service packages are imported after sys.path setup.
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
MODELS_SRC = REPO_ROOT / "packages" / "python" / "mintkey-models"
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from admin_api.api import agent_services
from admin_api.auth.agent_principal import AgentApiError, AgentPrincipal
from admin_api.utils.wire_ids import db_uuid_to_wire
from mintkey_models.egress import TargetNotAllowed

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
OTHER_AGENT_ID = UUID("00000000-0000-0000-0000-000000000023")
SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ab")

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

    def __init__(self, row: Any | None = None) -> None:
        self._row = row

    def fetchone(self) -> Any | None:
        return self._row

    def fetchall(self) -> list[Any]:
        return [] if self._row is None else [self._row]


class _FakeSession:
    """Record every statement and answer the service reads like the database.

    The ownership SELECT returns ``service_row`` (or nothing), the services
    UPDATE returns ``updated_row``, the slug pre-check answers a row only when
    ``slug_taken`` is true, and deletes are recorded. ``audit_emit`` and
    ``notify_change`` run for real against this session, so their statements
    and parameters are recorded like every other statement.
    """

    def __init__(
        self,
        *,
        service_row: Any | None = None,
        updated_row: Any | None = None,
        slug_taken: bool = False,
    ) -> None:
        self.service_row = service_row
        self.updated_row = updated_row
        self.slug_taken = slug_taken
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.audit_events: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []

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

        if upper.startswith("UPDATE SERVICES"):
            if self.updated_row is not None:
                for key in ("updated_at", "now"):
                    if key in bound:
                        self.updated_row.updated_at = bound[key]
                        break
            return _Result(self.updated_row)

        if upper.startswith("DELETE"):
            return _Result()

        if upper.startswith("SELECT") and "FROM SERVICES" in upper:
            if "SLUG" in upper and "OWNER_AGENT_ID" not in upper:
                return _Result(
                    SimpleNamespace(id=SERVICE_ID) if self.slug_taken else None
                )
            return _Result(self.service_row)

        return _Result()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def flush(self) -> None:
        return None


def _principal() -> AgentPrincipal:
    return AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="publisher")


def _service_row(
    *,
    owner: UUID | None = AGENT_ID,
    credential_set: bool = True,
    base_url: str = "https://api.example.com",
    auth_scheme: str = "bearer_token",
    display_name: str = "My Service Display",
) -> SimpleNamespace:
    row = SimpleNamespace(
        id=SERVICE_ID,
        tenant_id=TENANT_ID,
        name="My Service",
        slug="my-service",
        display_name=display_name,
        description="A service",
        base_url=base_url,
        auth_scheme=auth_scheme,
        openapi_url=None,
        status="active",
        owner_agent_id=owner,
        created_by_agent_id=AGENT_ID,
        credential_set=credential_set,
    )
    row.created_at = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    row.updated_at = datetime(2026, 2, 3, 4, 5, 7, tzinfo=timezone.utc)
    return row


def _updated_row(
    source: SimpleNamespace,
    *,
    updated_at: datetime | None = None,
    **changes: Any,
) -> SimpleNamespace:
    values = vars(source).copy()
    values.update(changes)
    row = SimpleNamespace(**values)
    row.updated_at = updated_at or datetime(2026, 3, 1, 12, 0, 0, tzinfo=timezone.utc)
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


def _request(payload: Any) -> Request:
    """A PATCH request whose JSON body is ``payload``."""

    raw = json.dumps(payload).encode()
    return _raw_request(raw)


def _raw_request(raw: bytes) -> Request:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/v1/agent/services/my-service",
            "raw_path": b"/v1/agent/services/my-service",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        },
        receive,
    )


def _patch_target(
    monkeypatch: pytest.MonkeyPatch,
) -> list[str]:
    """Replace the egress check with a recorder that refuses http and 10/8."""
    calls: list[str] = []

    async def _check(url: str) -> None:
        calls.append(url)
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise TargetNotAllowed("not_https")
        host = parts.hostname or ""
        if host == "private.example.com" or host.startswith("10."):
            raise TargetNotAllowed("non_public_address")

    monkeypatch.setattr(agent_services, "check_agent_target_url", _check)
    return calls


async def _update(
    session: _FakeSession,
    body: Any,
    *,
    service_ref: str = "my-service",
    principal: AgentPrincipal | None = None,
    raw: bool = False,
) -> JSONResponse:
    """Call the PATCH handler directly with a fake session and principal."""
    request = _raw_request(body) if raw else _request(body)
    return await agent_services._update_agent_service(
        service_ref=service_ref,
        request=request,
        principal=principal or _principal(),
        session=session,
    )


def _answer(response: JSONResponse) -> dict[str, Any]:
    assert response is not None, "the PATCH handler returned no response"
    assert isinstance(response, JSONResponse), type(response)
    return json.loads(response.body)


def _statements_naming(session: _FakeSession, table: str) -> list[str]:
    needle = table.upper()
    return [sql for sql, _params in session.statements if needle in sql.upper()]


def _updates(session: _FakeSession) -> list[tuple[int, str, dict[str, Any]]]:
    return [
        (index, sql, params)
        for index, (sql, params) in enumerate(session.statements)
        if sql.upper().startswith("UPDATE SERVICES")
    ]


def _deletes(session: _FakeSession) -> list[tuple[int, str]]:
    return [
        (index, sql)
        for index, (sql, _params) in enumerate(session.statements)
        if sql.upper().startswith("DELETE")
    ]


def _events(session: _FakeSession, event_type: str) -> list[dict[str, Any]]:
    return [
        event for event in session.audit_events if event["event_type"] == event_type
    ]


# ---------------------------------------------------------------------------
# C-d225b1e7 — a metadata edit keeps the credential, a changed target clears it
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-d225b1e7")
@pytest.mark.asyncio
async def test_C_d225b1e7_metadata_edit_keeps_the_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _service_row(credential_set=True)
    updated = _updated_row(row, display_name="Renamed")
    session = _FakeSession(service_row=row, updated_row=updated)
    calls = _patch_target(monkeypatch)

    response = await _update(session, {"display_name": "Renamed"})

    body = _answer(response)
    assert response.status_code == 200, response.body
    assert body == {**_expected_view(updated), "credential_cleared": False}
    assert set(body) == VIEW_KEYS | {"credential_cleared"}
    assert body["credential_cleared"] is False
    assert body["credential_set"] is True
    assert body["updated_at"] == updated.updated_at.isoformat()

    updates = _updates(session)
    assert len(updates) == 1
    _index, update_sql, _update_params = updates[0]
    assert "UPDATED_AT" in update_sql.upper()
    assert "RETURNING" in update_sql.upper()
    assert _statements_naming(session, "vault.credentials") == []
    assert calls == []

    events = _events(session, "service.updated")
    assert len(events) == 1
    assert events[0]["actor_type"] == "agent"
    assert events[0]["actor_id"] == str(AGENT_ID)
    assert events[0]["payload"]["fields_changed"] == ["display_name"]
    assert _events(session, "service.credential.cleared") == []

    assert len(session.notifications) == 1
    assert session.notifications[0]["channel"] == "mintkey:service"
    assert session.notifications[0]["payload"]["event"] == "service.updated"


@pytest.mark.l4("C-d225b1e7")
@pytest.mark.asyncio
async def test_C_d225b1e7_base_url_change_clears_the_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _service_row(credential_set=True)
    updated = _updated_row(
        row,
        base_url="https://new.example.com",
        credential_set=False,
    )
    session = _FakeSession(service_row=row, updated_row=updated)
    calls = _patch_target(monkeypatch)

    response = await _update(session, {"base_url": "https://new.example.com"})

    body = _answer(response)
    assert response.status_code == 200, response.body
    assert body == {**_expected_view(updated), "credential_cleared": True}
    assert body["credential_cleared"] is True
    assert body["credential_set"] is False
    assert calls == ["https://new.example.com"]

    updates = _updates(session)
    assert len(updates) == 1
    deletes = _deletes(session)
    assert any("VAULT.CREDENTIALS" in sql.upper() for _i, sql in deletes)
    assert any(
        "DELETE FROM CREDENTIALS" in sql.upper() for _i, sql in deletes
    )

    events = _events(session, "service.updated")
    assert len(events) == 1
    assert events[0]["actor_type"] == "agent"
    assert events[0]["actor_id"] == str(AGENT_ID)
    assert events[0]["payload"]["fields_changed"] == ["base_url"]

    cleared = _events(session, "service.credential.cleared")
    assert len(cleared) == 1
    assert cleared[0]["actor_type"] == "agent"
    assert cleared[0]["actor_id"] == str(AGENT_ID)
    assert cleared[0]["payload"]["reason"] == "target_changed"

    assert len(session.notifications) == 1
    assert session.notifications[0]["payload"]["event"] == "service.updated"


@pytest.mark.l4("C-d225b1e7")
@pytest.mark.asyncio
async def test_C_d225b1e7_auth_scheme_change_clears_the_credential(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _service_row(credential_set=True, auth_scheme="bearer_token")
    updated = _updated_row(row, auth_scheme="basic_auth", credential_set=False)
    session = _FakeSession(service_row=row, updated_row=updated)
    calls = _patch_target(monkeypatch)

    response = await _update(session, {"auth_scheme": "basic_auth"})

    body = _answer(response)
    assert response.status_code == 200, response.body
    assert body == {**_expected_view(updated), "credential_cleared": True}
    assert body["credential_cleared"] is True
    assert body["credential_set"] is False
    assert calls == []

    deletes = _deletes(session)
    assert any("VAULT.CREDENTIALS" in sql.upper() for _i, sql in deletes)
    assert any(
        "DELETE FROM CREDENTIALS" in sql.upper() for _i, sql in deletes
    )

    events = _events(session, "service.updated")
    assert len(events) == 1
    assert events[0]["actor_type"] == "agent"
    assert events[0]["actor_id"] == str(AGENT_ID)
    assert events[0]["payload"]["fields_changed"] == ["auth_scheme"]

    cleared = _events(session, "service.credential.cleared")
    assert len(cleared) == 1
    assert cleared[0]["actor_type"] == "agent"
    assert cleared[0]["actor_id"] == str(AGENT_ID)
    assert cleared[0]["payload"]["reason"] == "target_changed"


# ---------------------------------------------------------------------------
# C-ce4c7660 — without a credential, nothing changed, refused
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ce4c7660")
@pytest.mark.asyncio
async def test_C_ce4c7660_changed_target_without_credential_deletes_without_event(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _service_row(credential_set=False)
    updated = _updated_row(
        row,
        base_url="https://new.example.com",
        credential_set=False,
    )
    session = _FakeSession(service_row=row, updated_row=updated)
    _patch_target(monkeypatch)

    response = await _update(session, {"base_url": "https://new.example.com"})

    body = _answer(response)
    assert response.status_code == 200, response.body
    assert body == {**_expected_view(updated), "credential_cleared": False}
    assert body["credential_cleared"] is False
    assert body["credential_set"] is False

    deletes = _deletes(session)
    assert any("VAULT.CREDENTIALS" in sql.upper() for _i, sql in deletes)
    assert any(
        "DELETE FROM CREDENTIALS" in sql.upper() for _i, sql in deletes
    )
    assert _events(session, "service.credential.cleared") == []


@pytest.mark.l4("C-ce4c7660")
@pytest.mark.asyncio
async def test_C_ce4c7660_repeated_value_is_no_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _service_row(credential_set=True, base_url="https://api.example.com")
    session = _FakeSession(service_row=row, updated_row=row)
    calls = _patch_target(monkeypatch)

    response = await _update(session, {"base_url": "https://api.example.com"})

    body = _answer(response)
    assert response.status_code == 200, response.body
    assert body == {**_expected_view(row), "credential_cleared": False}
    assert body["credential_cleared"] is False

    assert _updates(session) == []
    assert _events(session, "service.updated") == []
    assert _events(session, "service.credential.cleared") == []
    assert session.notifications == []
    assert calls == []


@pytest.mark.l4("C-ce4c7660")
@pytest.mark.asyncio
async def test_C_ce4c7660_refused_target_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _service_row(credential_set=True)
    session = _FakeSession(service_row=row, updated_row=row)
    _patch_target(monkeypatch)

    with pytest.raises(AgentApiError) as excinfo:
        await _update(session, {"base_url": "https://10.0.0.1/"})

    assert excinfo.value.status_code == 400
    assert excinfo.value.body["code"] == "mintkey:target_not_allowed"
    assert excinfo.value.body["title"] == "Target not allowed"
    assert excinfo.value.body["field"] == "base_url"
    assert excinfo.value.body.get("reason")
    assert _updates(session) == []
    assert _deletes(session) == []


# ---------------------------------------------------------------------------
# C-f996158c — not the owner
# ---------------------------------------------------------------------------


NOT_OWNER_BODY: dict[str, Any] = {
    "code": "mintkey:not_owner",
    "title": "Not the owner of this service",
}
NOT_FOUND_BODY: dict[str, Any] = {
    "code": "mintkey:not_found",
    "title": "Service not found",
}


@pytest.mark.l4("C-f996158c")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("service_row", "status", "expected_body"),
    [
        pytest.param(
            _service_row(owner=OTHER_AGENT_ID),
            403,
            NOT_OWNER_BODY,
            id="other_agent",
        ),
        pytest.param(_service_row(owner=None), 403, NOT_OWNER_BODY, id="no_owner"),
        pytest.param(None, 404, NOT_FOUND_BODY, id="other_tenant"),
        pytest.param(None, 404, NOT_FOUND_BODY, id="unknown_slug"),
    ],
)
async def test_C_f996158c_not_owned_patch_is_refused_without_update(
    monkeypatch: pytest.MonkeyPatch,
    service_row: Any | None,
    status: int,
    expected_body: dict[str, Any],
) -> None:
    session = _FakeSession(service_row=service_row)
    _patch_target(monkeypatch)

    with pytest.raises(AgentApiError) as excinfo:
        await _update(session, {"display_name": "Renamed"})

    assert excinfo.value.status_code == status
    assert excinfo.value.body == expected_body
    assert _updates(session) == []


# ---------------------------------------------------------------------------
# C-9092a793 — refused bodies
# ---------------------------------------------------------------------------


REFUSED_BODIES = [
    pytest.param({}, None, id="empty"),
    pytest.param({"name": "x"}, None, id="name_key"),
    pytest.param({"status": "disabled"}, None, id="status_key"),
    pytest.param({"auth_scheme": "ssh_private_key"}, "auth_scheme", id="ssh"),
    pytest.param(
        {"auth_scheme": "oauth2_client_credentials"},
        "auth_scheme",
        id="oauth2",
    ),
    pytest.param({"auth_scheme": "none"}, "auth_scheme", id="none"),
]


@pytest.mark.l4("C-9092a793")
@pytest.mark.asyncio
@pytest.mark.parametrize(("body", "field"), REFUSED_BODIES)
async def test_C_9092a793_refused_body_answers_422_and_runs_no_service_statement(
    monkeypatch: pytest.MonkeyPatch,
    body: dict[str, Any],
    field: str | None,
) -> None:
    session = _FakeSession(service_row=_service_row())
    _patch_target(monkeypatch)

    with pytest.raises(AgentApiError) as excinfo:
        await _update(session, body)

    assert excinfo.value.status_code == 422
    assert excinfo.value.body == {
        "code": "mintkey:validation_failed",
        "title": "Invalid request body",
        "field": field,
    }
    assert _statements_naming(session, "services") == []


# ---------------------------------------------------------------------------
# C-ec735b1d — the row is locked first
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-ec735b1d")
@pytest.mark.asyncio
async def test_C_ec735b1d_row_is_locked_before_every_update_and_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _service_row(credential_set=True)
    updated = _updated_row(row, display_name="Renamed")
    session = _FakeSession(service_row=row, updated_row=updated)
    _patch_target(monkeypatch)

    response = await _update(session, {"display_name": "Renamed"})

    body = _answer(response)
    assert response.status_code == 200, response.body
    assert body == {**_expected_view(updated), "credential_cleared": False}

    service_statements = [
        (index, sql)
        for index, (sql, _params) in enumerate(session.statements)
        if "SERVICES" in sql.upper()
    ]
    assert service_statements, "no statement named services"
    first_index, first_sql = service_statements[0]
    assert "FOR UPDATE" in first_sql.upper()

    updates = [index for index, _sql, _params in _updates(session)]
    deletes = [index for index, _sql in _deletes(session)]
    assert updates, "the changed display_name ran no UPDATE"
    assert all(index > first_index for index in updates + deletes)
