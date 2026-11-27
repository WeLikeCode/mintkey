"""
Unit tests: the transfer and role answers show the state after the change.

Requirement: agent-roles-and-ownership (feedback FB-001)
  - The transfer and role answers show the state after the change: a transfer
    answers with the new owner, the service's current key version and the
    updated_at of the change; a role PATCH answers with the new role and the
    updated_at of the change.

Sources:
  - `openspec/changes/agent-roles-and-ownership-fix-2/specs/agent-roles-and-ownership/spec.md`
  - `openspec/changes/agent-roles-and-ownership/feedback.md` — FB-001
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
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

from admin_api.utils.wire_ids import db_uuid_to_wire  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_TEXT = str(TENANT_ID)
OP_ID = UUID("00000000-0000-0000-0000-0000000000aa")
SESSION_TOKEN = "00000000-0000-0000-0000-0000000000bb"

AGENT_UUID = UUID("00000000-0000-0000-0000-0000000000a1")
AGENT_ID = db_uuid_to_wire(AGENT_UUID, "agent")

SERVICE_UUID = UUID("00000000-0000-0000-0000-0000000000c3")
SERVICE_ID = db_uuid_to_wire(SERVICE_UUID, "svc")

BASE_SERVICES_PATH = f"/v1/tenants/{TENANT_TEXT}/services"
BASE_AGENTS_PATH = f"/v1/tenants/{TENANT_TEXT}/agents"

OLD_UPDATED_AT = datetime(2020, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
CURRENT_KEY_VERSION = 4


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
    def __init__(self, session: "_StoredSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_StoredSession":
        return self._session

    async def __aexit__(self, *args: object) -> bool:
        return False


class _StoredSession:
    """A fake session that keeps mutable rows and answers snapshots of them.

    A read returns a fresh object holding the currently stored values, so a
    handler that answers with the pre-update row shows the old state. An UPDATE
    applies its bound values to the stored row; a later read therefore returns
    the state after the change. A services read that does not select
    ``current_key_version`` leaves the attribute off the row, as a real
    database result would.
    """

    def __init__(
        self,
        *,
        service_row: Any = None,
        agent_row: Any = None,
    ) -> None:
        self.service_row = service_row
        self.agent_row = agent_row
        self.statements: list[tuple[str, dict[str, Any]]] = []

    def _service_snapshot(self, sql: str) -> Any:
        if self.service_row is None:
            return None
        attrs = dict(vars(self.service_row))
        if "current_key_version" not in sql.lower():
            attrs.pop("current_key_version", None)
        return SimpleNamespace(**attrs)

    def _agent_snapshot(self) -> Any:
        if self.agent_row is None:
            return None
        return SimpleNamespace(**vars(self.agent_row))

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
            row = self._service_snapshot(sql)
            return _Result(rows=[row] if row is not None else [], one=row)
        if upper.startswith("SELECT") and "from agents" in lowered:
            row = self._agent_snapshot()
            return _Result(rows=[row] if row is not None else [], one=row)
        if upper.startswith("UPDATE SERVICES"):
            if self.service_row is not None:
                if "owner_agent_id" in bound:
                    self.service_row.owner_agent_id = bound["owner_agent_id"]
                if "now" in bound:
                    self.service_row.updated_at = bound["now"]
            if "returning" in lowered:
                row = self._service_snapshot(sql)
                return _Result(rows=[row] if row is not None else [], one=row)
            return _Result()
        if upper.startswith("UPDATE AGENTS"):
            if self.agent_row is not None:
                if "role" in bound:
                    self.agent_row.role = bound["role"]
                if "now" in bound:
                    self.agent_row.updated_at = bound["now"]
            if "returning" in lowered:
                row = self._agent_snapshot()
                return _Result(rows=[row] if row is not None else [], one=row)
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

    async def __aenter__(self) -> "_StoredSession":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False


class _SessionContext:
    def __init__(self) -> None:
        self.operator_id = OP_ID
        self.tenant_id = TENANT_ID


def _session_context() -> _SessionContext:
    return _SessionContext()


def _service_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=SERVICE_UUID,
        tenant_id=TENANT_ID,
        name="svc-one",
        slug="svc-one",
        display_name="Service One",
        description="test service",
        base_url="https://api.example.com",
        auth_scheme="bearer_token",
        openapi_url=None,
        status="active",
        current_key_version=CURRENT_KEY_VERSION,
        created_at=None,
        updated_at=OLD_UPDATED_AT,
        template_id=None,
        owner_agent_id=None,
        created_by_agent_id=None,
    )


def _agent_row(role: str = "consumer") -> SimpleNamespace:
    return SimpleNamespace(
        id=AGENT_UUID,
        tenant_id=TENANT_ID,
        name="agent-one",
        description="test agent",
        api_key_fingerprint="deadbeefdeadbeef",
        mcp_endpoint=f"http://localhost:8100/v1/agents/{AGENT_ID}",
        status="active",
        role=role,
        rate_limit_rps=None,
        created_at=None,
        updated_at=OLD_UPDATED_AT,
        grants_count=0,
        api_key_expires_at=None,
        api_key_version=1,
        api_key_last_rotated_at=None,
    )


def _make_services_app(session: _StoredSession) -> Any:
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

    async def _no_authz() -> None:
        return None

    async def _context() -> _SessionContext:
        return _session_context()

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[require_tenant_session] = _no_authz
    app.dependency_overrides[get_session_context] = _context

    csrf_exempt(BASE_SERVICES_PATH)
    app.add_middleware(CsrfMiddleware)
    return app


def _make_agents_app(session: _StoredSession) -> Any:
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

    async def _no_authz() -> None:
        return None

    async def _context() -> _SessionContext:
        return _session_context()

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[require_tenant_session] = _no_authz
    app.dependency_overrides[get_session_context] = _context

    csrf_exempt(BASE_AGENTS_PATH)
    app.add_middleware(CsrfMiddleware)
    return app


async def _transfer(session: _StoredSession, body: dict[str, Any]) -> Any:
    app = _make_services_app(session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            f"{BASE_SERVICES_PATH}/{SERVICE_ID}/transfer",
            json=body,
            cookies={"mintkey_session": SESSION_TOKEN},
        )


async def _patch_role(session: _StoredSession, body: dict[str, Any]) -> Any:
    app = _make_agents_app(session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.patch(
            f"{BASE_AGENTS_PATH}/{AGENT_ID}",
            json=body,
            cookies={"mintkey_session": SESSION_TOKEN},
        )


def _updates(
    session: _StoredSession, table: str
) -> list[tuple[str, dict[str, Any]]]:
    prefix = f"update {table}"
    return [
        (sql, params)
        for sql, params in session.statements
        if sql.lower().startswith(prefix)
    ]


@pytest.mark.asyncio
@pytest.mark.l4("C-1a3fd676")
async def test_C_1a3fd676_a_transfer_answers_with_the_stored_state_after_it() -> None:
    """To a publisher and back: the body shows the new owner, key version and time."""
    session = _StoredSession(
        service_row=_service_row(), agent_row=_agent_row("publisher")
    )

    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
    ):
        to_publisher = await _transfer(session, {"to_agent_id": AGENT_ID})
        to_operators = await _transfer(session, {"to_agent_id": None})

    updates = _updates(session, "services")
    assert len(updates) == 2, updates
    first_now = updates[0][1]["now"]
    second_now = updates[1][1]["now"]

    assert to_publisher.status_code == 200, to_publisher.text
    first_body = to_publisher.json()
    assert first_body.get("owner_agent_id") == AGENT_ID, first_body
    assert first_body.get("current_key_version") == CURRENT_KEY_VERSION, first_body
    assert first_body.get("updated_at") == first_now.isoformat(), first_body
    assert first_body.get("updated_at") != OLD_UPDATED_AT.isoformat(), first_body

    assert to_operators.status_code == 200, to_operators.text
    second_body = to_operators.json()
    assert "owner_agent_id" in second_body, second_body
    assert second_body.get("owner_agent_id") is None, second_body
    assert second_body.get("current_key_version") == CURRENT_KEY_VERSION, second_body
    assert second_body.get("updated_at") == second_now.isoformat(), second_body
    assert second_body.get("updated_at") != OLD_UPDATED_AT.isoformat(), second_body


@pytest.mark.asyncio
@pytest.mark.l4("C-1a3fd676")
async def test_C_1a3fd676_a_role_patch_answers_with_the_stored_state_after_it() -> None:
    """Promote and demote: the body shows the new role and the time of the change."""
    session = _StoredSession(agent_row=_agent_row("consumer"))

    with patch("admin_api.api.agents.audit_emit", new=AsyncMock()):
        promote = await _patch_role(session, {"role": "publisher"})
        demote = await _patch_role(session, {"role": "consumer"})

    updates = _updates(session, "agents")
    assert len(updates) == 2, updates
    first_now = updates[0][1]["now"]
    second_now = updates[1][1]["now"]

    assert promote.status_code == 200, promote.text
    promoted = promote.json()
    assert promoted.get("role") == "publisher", promoted
    assert promoted.get("updated_at") == first_now.isoformat(), promoted
    assert promoted.get("updated_at") != OLD_UPDATED_AT.isoformat(), promoted

    assert demote.status_code == 200, demote.text
    demoted = demote.json()
    assert demoted.get("role") == "consumer", demoted
    assert demoted.get("updated_at") == second_now.isoformat(), demoted
    assert demoted.get("updated_at") != OLD_UPDATED_AT.isoformat(), demoted
