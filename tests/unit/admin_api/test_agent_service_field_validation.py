"""Unit tests: invalid field values answer 422, never 500 or a silent 200.

Task 1.4 of agent-service-routes-fix-1, the criterion C-2a3254e4 of
"Invalid field values answer 422, never 500 or a silent 200":

  1. a create or PATCH whose ``display_name`` is longer than the stored column
     allows (VARCHAR(256), so 257 characters and more) answers 422
     ``mintkey:validation_failed`` with ``field`` ``display_name`` before any
     INSERT or UPDATE, so the service is unchanged (Q-001);
  2. an empty ``display_name`` answers the same 422 on create and on PATCH;
  3. a PATCH that sets any update field to null answers that 422 with the
     field's name instead of a silent 200 that changes nothing.

Q-001 settled that ``description``, ``base_url`` and ``openapi_url`` are TEXT
with no length limit, so no value can be longer than those columns allow and
only the ``display_name`` bound is asserted here.

Sources:
  - `openspec/changes/agent-service-routes-fix-1/spec.md` — Invalid field
    values answer 422, never 500 or a silent 200 — feedback FB-004
  - `openspec/changes/agent-service-routes-fix-1/questions.md` — Q-001
  - `apps/admin-api/db/changelog/004-services.yaml` — display_name VARCHAR(256)
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

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ab")

VALIDATION_BODY = {
    "code": "mintkey:validation_failed",
    "title": "Invalid request body",
}

#: One character over VARCHAR(256).
TOO_LONG = "a" * 257


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

    The ownership SELECT returns ``service_row``, the create INSERT returns it
    too, and the services UPDATE returns ``updated_row``. Nothing here rejects
    an over-long value: a database would raise ``DataError``, which is exactly
    the 500 these tests keep from happening.
    """

    def __init__(
        self,
        *,
        service_row: Any | None = None,
        updated_row: Any | None = None,
    ) -> None:
        self.service_row = service_row
        self.updated_row = updated_row or service_row
        self.statements: list[tuple[str, dict[str, Any]]] = []

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

        if upper.startswith("INSERT INTO SERVICES"):
            return _Result(self.service_row)
        if upper.startswith("UPDATE SERVICES"):
            return _Result(self.updated_row)
        if upper.startswith("DELETE"):
            return _Result()
        if upper.startswith("SELECT") and "FROM SERVICES" in upper:
            if "OWNER_AGENT_ID" in upper:
                return _Result(self.service_row)
            if "SLUG" in upper:
                return _Result(None)
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


def _service_row(*, display_name: str = "My Service Display") -> SimpleNamespace:
    row = SimpleNamespace(
        id=SERVICE_ID,
        tenant_id=TENANT_ID,
        name="My Service",
        slug="my-service",
        display_name=display_name,
        description="A service",
        base_url="https://api.example.com",
        auth_scheme="bearer_token",
        openapi_url=None,
        status="active",
        owner_agent_id=AGENT_ID,
        created_by_agent_id=AGENT_ID,
        credential_set=True,
    )
    row.created_at = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    row.updated_at = datetime(2026, 2, 3, 4, 5, 7, tzinfo=timezone.utc)
    return row


def _request(payload: Any) -> Request:
    raw = json.dumps(payload).encode()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "PATCH",
            "path": "/v1/agent/services",
            "raw_path": b"/v1/agent/services",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        },
        receive,
    )


def _noop_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Accept every target: this task is about field validation only."""

    async def _check(url: str) -> None:
        return None

    monkeypatch.setattr(agent_services, "check_agent_target_url", _check)


def _create_body(**overrides: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "name": "My Service",
        "base_url": "https://api.example.com",
        "auth_scheme": "bearer_token",
        "display_name": "My Service Display",
    }
    body.update(overrides)
    return body


async def _capture(coro: Any) -> tuple[int, dict[str, Any]]:
    try:
        response = await coro
    except AgentApiError as exc:
        return exc.status_code, exc.body
    assert response is not None, "the handler returned no response"
    assert isinstance(response, JSONResponse), type(response)
    return response.status_code, json.loads(response.body)


async def _create(
    session: _FakeSession,
    payload: Any,
) -> tuple[int, dict[str, Any]]:
    return await _capture(
        agent_services.create_agent_service(
            request=_request(payload),
            principal=_principal(),
            session=session,
        )
    )


async def _patch(
    session: _FakeSession,
    payload: Any,
) -> tuple[int, dict[str, Any]]:
    return await _capture(
        agent_services._update_agent_service(
            service_ref="my-service",
            request=_request(payload),
            principal=_principal(),
            session=session,
        )
    )


def _service_writes(session: _FakeSession) -> list[str]:
    return [
        sql
        for sql, _params in session.statements
        if sql.upper().startswith("INSERT INTO SERVICES")
        or sql.upper().startswith("UPDATE SERVICES")
        or sql.upper().startswith("DELETE")
    ]


# ---------------------------------------------------------------------------
# C-2a3254e4 — an over-long or empty display_name is refused on create
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2a3254e4")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("display_name", "case"),
    [
        pytest.param(TOO_LONG, "too_long", id="257_chars"),
        pytest.param("", "empty", id="empty"),
    ],
)
async def test_C_2a3254e4_create_refuses_bad_display_name_without_insert(
    monkeypatch: pytest.MonkeyPatch,
    display_name: str,
    case: str,
) -> None:
    _noop_target(monkeypatch)
    session = _FakeSession(service_row=_service_row())

    status, body = await _create(
        session, _create_body(display_name=display_name)
    )

    assert status == 422, (case, body)
    assert body == {**VALIDATION_BODY, "field": "display_name"}
    assert _service_writes(session) == []


# ---------------------------------------------------------------------------
# C-2a3254e4 — an over-long or empty display_name is refused on PATCH
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2a3254e4")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("display_name", "case"),
    [
        pytest.param(TOO_LONG, "too_long", id="257_chars"),
        pytest.param("", "empty", id="empty"),
    ],
)
async def test_C_2a3254e4_patch_refuses_bad_display_name_without_update(
    monkeypatch: pytest.MonkeyPatch,
    display_name: str,
    case: str,
) -> None:
    _noop_target(monkeypatch)
    row = _service_row()
    session = _FakeSession(service_row=row, updated_row=row)

    status, body = await _patch(session, {"display_name": display_name})

    assert status == 422, (case, body)
    assert body == {**VALIDATION_BODY, "field": "display_name"}
    assert _service_writes(session) == []


# ---------------------------------------------------------------------------
# C-2a3254e4 — a PATCH that sets a field to null is refused, not a silent 200
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-2a3254e4")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    ["base_url", "auth_scheme", "display_name", "description", "openapi_url"],
)
async def test_C_2a3254e4_patch_refuses_a_null_field_without_update(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    _noop_target(monkeypatch)
    row = _service_row()
    session = _FakeSession(service_row=row, updated_row=row)

    status, body = await _patch(session, {field: None})

    assert status == 422, body
    assert body == {**VALIDATION_BODY, "field": field}
    assert _service_writes(session) == []
