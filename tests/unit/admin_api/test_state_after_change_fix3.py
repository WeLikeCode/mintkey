"""
Unit tests for FB-001: the transfer and role answers show the stored state after
the change, and the service read carries its key version from the key-version
subquery (not a column that does not exist on ``services``).

Requirement: agent-roles-and-ownership
  - The transfer and role answers show the state after the change (C-1a3fd676)

The fake session below is deliberately faithful to the schema: a ``services``
SELECT that asks for ``s.current_key_version`` (a column the table does not
have) yields a row without that attribute, while a SELECT that computes the
value with the ``MAX(c.key_version)`` subquery yields it. The handler must read
the stored state after its UPDATE and must use the subquery, so the answer
carries the new owner/new role, the current key version and the time of the
change.

Sources:
  - `openspec/changes/agent-roles-and-ownership-fix-3/specs/agent-roles-and-ownership/spec.md`
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

    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = list(rows or [])

    def fetchone(self) -> Any:
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
    def __init__(self, session: "_SchemaFaithfulSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_SchemaFaithfulSession":
        return self._session

    async def __aexit__(self, *args: object) -> bool:
        return False


class _SchemaFaithfulSession:
    """A fake session whose services rows follow the real table's columns.

    ``services`` has no ``current_key_version`` column. Its value is the
    ``MAX(c.key_version)`` subquery. A SELECT that names the non-existent
    column therefore returns a row without the attribute, as the real database
    would fail to return one. An UPDATE applies its bound values to the stored
    row, so a later SELECT returns the state after the change.
    """

    def __init__(
        self,
        *,
        service_row: SimpleNamespace,
        agent_row: SimpleNamespace,
    ) -> None:
        self.service_row = service_row
        self.agent_row = agent_row
        self.statements: list[tuple[str, dict[str, Any]]] = []

    def _service_snapshot(self, sql: str) -> Any:
        attrs = dict(vars(self.service_row))
        if "max(c.key_version)" not in sql.lower():
            # ``s.current_key_version`` is not a real column: a SELECT for it
            # cannot produce the attribute.
            attrs.pop("current_key_version", None)
        return SimpleNamespace(**attrs)

    async def execute(
        self,
        statement: Any,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _Result:
        sql = " ".join(str(statement).split())
        bound = dict(params or {})
        self.statements.append((sql, bound))
        lowered = sql.lower()
        upper = sql.lstrip().upper()

        if "set_config" in lowered or "pg_notify" in lowered:
            return _Result()
        if upper.startswith("SELECT") and "from services" in lowered:
            return _Result(rows=[self._service_snapshot(sql)])
        if upper.startswith("SELECT") and "from agents" in lowered:
            return _Result(rows=[SimpleNamespace(**vars(self.agent_row))])
        if upper.startswith("UPDATE SERVICES"):
            if "owner_agent_id" in bound:
                self.service_row.owner_agent_id = bound["owner_agent_id"]
            if "now" in bound:
                self.service_row.updated_at = bound["now"]
            return _Result()
        if upper.startswith("UPDATE AGENTS"):
            if "role" in bound:
                self.agent_row.role = bound["role"]
            if "now" in bound:
                self.agent_row.updated_at = bound["now"]
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

    async def __aenter__(self) -> "_SchemaFaithfulSession":
        return self

    async def __aexit__(self, *args: object) -> bool:
        return False


class _SessionContext:
    def __init__(self) -> None:
        self.operator_id = OP_ID
        self.tenant_id = TENANT_ID


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


def _agent_row(role: str = "publisher") -> SimpleNamespace:
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


def _make_app(
    session: _SchemaFaithfulSession, *, services: bool
) -> Any:
    from fastapi import FastAPI

    from admin_api.api.permissions import validation_error_handler
    from admin_api.auth.sessions import get_session_context, require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    if services:
        from admin_api.api.services import router as api_router

        csrf_base = BASE_SERVICES_PATH
    else:
        from admin_api.api.agents import router as api_router

        csrf_base = BASE_AGENTS_PATH

    app = FastAPI()
    app.include_router(api_router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    async def _db() -> Any:
        yield session

    async def _no_authz() -> None:
        return None

    async def _context() -> _SessionContext:
        return _SessionContext()

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[require_tenant_session] = _no_authz
    app.dependency_overrides[get_session_context] = _context

    csrf_exempt(csrf_base)
    app.add_middleware(CsrfMiddleware)
    return app


async def _transfer(
    session: _SchemaFaithfulSession, body: dict[str, Any]
) -> Any:
    app = _make_app(session, services=True)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        return await client.post(
            f"{BASE_SERVICES_PATH}/{SERVICE_ID}/transfer",
            json=body,
            cookies={"mintkey_session": SESSION_TOKEN},
        )


async def _patch_role(
    session: _SchemaFaithfulSession, body: dict[str, Any]
) -> Any:
    app = _make_app(session, services=False)
    async with AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    ) as client:
        return await client.patch(
            f"{BASE_AGENTS_PATH}/{AGENT_ID}",
            json=body,
            cookies={"mintkey_session": SESSION_TOKEN},
        )


def _updates(
    session: _SchemaFaithfulSession, table: str
) -> list[tuple[str, dict[str, Any]]]:
    prefix = f"update {table}"
    return [
        (sql, params)
        for sql, params in session.statements
        if sql.lower().startswith(prefix)
    ]


@pytest.mark.asyncio
@pytest.mark.l4("C-1a3fd676")
async def test_C_1a3fd676_transfer_and_role_answers_show_the_stored_state() -> None:
    """Both answers come from the row after the change and a read that carries the key version."""
    session = _SchemaFaithfulSession(
        service_row=_service_row(), agent_row=_agent_row("publisher")
    )

    with (
        patch("admin_api.api.services.audit_emit", new=AsyncMock()),
        patch("admin_api.api.services.notify_change", new=AsyncMock()),
        patch("admin_api.api.agents.audit_emit", new=AsyncMock()),
    ):
        to_publisher = await _transfer(session, {"to_agent_id": AGENT_ID})
        to_operators = await _transfer(session, {"to_agent_id": None})
        demote = await _patch_role(session, {"role": "consumer"})
        promote = await _patch_role(session, {"role": "publisher"})

    service_updates = _updates(session, "services")
    assert len(service_updates) == 2, service_updates
    first_transfer_at = service_updates[0][1]["now"]
    second_transfer_at = service_updates[1][1]["now"]

    assert to_publisher.status_code == 200, to_publisher.text
    first_body = to_publisher.json()
    assert first_body.get("owner_agent_id") == AGENT_ID, first_body
    assert first_body.get("current_key_version") == CURRENT_KEY_VERSION, first_body
    assert first_body.get("updated_at") == first_transfer_at.isoformat(), first_body
    assert first_body.get("updated_at") != OLD_UPDATED_AT.isoformat(), first_body

    assert to_operators.status_code == 200, to_operators.text
    second_body = to_operators.json()
    assert "owner_agent_id" in second_body, second_body
    assert second_body.get("owner_agent_id") is None, second_body
    assert second_body.get("current_key_version") == CURRENT_KEY_VERSION, second_body
    assert second_body.get("updated_at") == second_transfer_at.isoformat(), second_body
    assert second_body.get("updated_at") != OLD_UPDATED_AT.isoformat(), second_body

    service_selects = [
        sql
        for sql, _params in session.statements
        if sql.lower().startswith("select") and "from services" in sql.lower()
    ]
    assert service_selects, session.statements
    for sql in service_selects:
        lowered = sql.lower()
        assert "max(c.key_version)" in lowered, sql
        assert "s.current_key_version" not in lowered, sql

    agent_updates = _updates(session, "agents")
    assert len(agent_updates) == 2, agent_updates
    first_role_at = agent_updates[0][1]["now"]
    second_role_at = agent_updates[1][1]["now"]

    assert demote.status_code == 200, demote.text
    demoted = demote.json()
    assert demoted.get("role") == "consumer", demoted
    assert demoted.get("updated_at") == first_role_at.isoformat(), demoted
    assert demoted.get("updated_at") != OLD_UPDATED_AT.isoformat(), demoted

    assert promote.status_code == 200, promote.text
    promoted = promote.json()
    assert promoted.get("role") == "publisher", promoted
    assert promoted.get("updated_at") == second_role_at.isoformat(), promoted
    assert promoted.get("updated_at") != OLD_UPDATED_AT.isoformat(), promoted
