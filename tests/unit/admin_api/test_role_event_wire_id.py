"""
Unit tests: ``agent.role.changed`` names the agent in its canonical wire form.

Requirement: agent-roles-and-ownership (feedback FB-002)
  - When an operator changes an agent's role and names the agent in the path by
    its UUID or by a legacy wire id, the ``agent.role.changed`` event's
    ``agent_id`` is the agent's canonical wire id (``agent_`` followed by 26
    characters), as the event's schema requires.

Sources:
  - `openspec/changes/agent-roles-and-ownership-fix-2/specs/agent-roles-and-ownership/spec.md`
  - `openspec/changes/agent-roles-and-ownership/feedback.md` — FB-002
  - `docs/architecture/contracts/events/audit-event.schema.json` — `$defs/agent_id`
"""
from __future__ import annotations

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

from admin_api.utils.wire_ids import db_uuid_to_wire  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
TENANT_TEXT = str(TENANT_ID)
OP_ID = UUID("00000000-0000-0000-0000-0000000000aa")
SESSION_TOKEN = "00000000-0000-0000-0000-0000000000bb"
AGENT_UUID = UUID("00000000-0000-0000-0000-0000000000a1")
BASE_URL_PATH = f"/v1/tenants/{TENANT_TEXT}/agents"

# The wire-id pattern from the audit contract's `$defs/agent_id`.
CANONICAL_AGENT_ID = re.compile(r"^agent_[0-9A-HJKMNP-TV-Z]{26}$")


class _Result:
    """The small slice of a SQLAlchemy result the role handler uses."""

    def __init__(self, one: Any = None) -> None:
        self._one = one

    def fetchone(self) -> Any:
        return self._one


class _AsyncContext:
    def __init__(self, session: "_RecordingSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_RecordingSession":
        return self._session

    async def __aexit__(self, *args: object) -> bool:
        return False


class _RecordingSession:
    """Answers the role handler's reads and records every statement."""

    def __init__(self, row: Any) -> None:
        self.row = row
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
            return _Result(self.row)
        if upper.startswith("UPDATE AGENTS"):
            role_values = [
                value for value in bound.values() if value in ("consumer", "publisher")
            ]
            if len(role_values) == 1:
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


class _SessionContext:
    def __init__(self) -> None:
        self.operator_id = OP_ID
        self.tenant_id = TENANT_ID


def _agent_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=AGENT_UUID,
        tenant_id=TENANT_ID,
        name="agent-one",
        description="test agent",
        api_key_fingerprint="deadbeefdeadbeef",
        mcp_endpoint="http://localhost:8100/v1/agents/placeholder",
        status="active",
        role="consumer",
        rate_limit_rps=None,
        created_at=None,
        updated_at=None,
        grants_count=0,
        api_key_expires_at=None,
        api_key_version=1,
        api_key_last_rotated_at=None,
    )


def _make_app(session: _RecordingSession) -> Any:
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
        return _SessionContext()

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[require_tenant_session] = _no_authz
    app.dependency_overrides[get_session_context] = _context

    csrf_exempt(BASE_URL_PATH)
    app.add_middleware(CsrfMiddleware)
    return app


async def _patch_role(session: _RecordingSession, agent_path_id: str) -> Any:
    app = _make_app(session)
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.patch(
            f"{BASE_URL_PATH}/{agent_path_id}",
            json={"role": "publisher"},
            cookies={"mintkey_session": SESSION_TOKEN},
        )


@pytest.mark.asyncio
@pytest.mark.l4("C-8c0a2e07")
async def test_C_8c0a2e07_uuid_path_writes_the_canonical_agent_id() -> None:
    """Naming the agent by its UUID still audits its canonical wire id."""
    session = _RecordingSession(_agent_row())

    with patch("admin_api.api.agents.audit_emit", new=AsyncMock()) as audit_mock:
        response = await _patch_role(session, str(AGENT_UUID))

    assert response.status_code == 200, response.text
    assert audit_mock.call_count == 1
    payload = audit_mock.call_args.kwargs.get("payload", {})
    assert payload.get("agent_id") == db_uuid_to_wire(AGENT_UUID, "agent"), payload
    assert CANONICAL_AGENT_ID.match(payload.get("agent_id", "")), payload
    assert payload.get("agent_id") != str(AGENT_UUID), payload


@pytest.mark.asyncio
@pytest.mark.l4("C-8c0a2e07")
async def test_C_8c0a2e07_legacy_wire_path_writes_the_canonical_agent_id() -> None:
    """Naming the agent by its legacy hex wire id still audits the canonical id."""
    session = _RecordingSession(_agent_row())
    legacy_wire_id = "agent_" + AGENT_UUID.hex

    with patch("admin_api.api.agents.audit_emit", new=AsyncMock()) as audit_mock:
        response = await _patch_role(session, legacy_wire_id)

    assert response.status_code == 200, response.text
    assert audit_mock.call_count == 1
    payload = audit_mock.call_args.kwargs.get("payload", {})
    assert payload.get("agent_id") == db_uuid_to_wire(AGENT_UUID, "agent"), payload
    assert CANONICAL_AGENT_ID.match(payload.get("agent_id", "")), payload
    assert payload.get("agent_id") != legacy_wire_id, payload
