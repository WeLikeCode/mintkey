"""
Unit tests: the readers outside discovery treat an expired grant as absent.

Requirement: grant-expiry › An expired grant is absent for the agent

  - the other readers ignore an expired grant (C-b5050c3c): a classical API
    key is created, then ``list_agents`` and ``get_agent`` run, and every
    statement that reads ``permission_grants`` filters on the expiry.

Each reader runs against a recording fake session so the test can read the
statements it executed.  The grant load in ``api_keys`` uses the bare column
names; the grant counts and the access filter in ``agents`` use the ``pg``
alias.

Sources:
  - `openspec/changes/grant-expiry/spec.md` — An expired grant is absent for the
    agent; the other readers ignore an expired grant
  - `openspec/changes/grant-expiry/design.md` — D3
  - `tests/unit/admin_api/test_api_keys.py` — the classical key creation setup
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
MODELS_SRC = REPO_ROOT / "packages" / "python" / "mintkey-models"
for _p in (ADMIN_API_SRC, MODELS_SRC):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = "agent_00000000000000000000000001"
SVC_ID = "svc_00000000000000000000000001"
AGENT_UUID = UUID("11111111-1111-1111-1111-111111111111")

BASE_URL = f"/v1/tenants/{TENANT_ID}/agents/{AGENT_ID}/api-keys"


class _Result:
    """The small slice of a SQLAlchemy result the handlers use."""

    def __init__(self, rows: list[object] | None = None) -> None:
        self._rows = list(rows or [])

    def fetchone(self) -> object | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[object]:
        return list(self._rows)


def _agent_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=AGENT_UUID,
        tenant_id=TENANT_ID,
        name="agent-one",
        description="test agent",
        api_key_fingerprint="abcd1234abcd1234",
        mcp_endpoint="http://localhost:8100/v1/agents/agent_one",
        status="active",
        rate_limit_rps=None,
        created_at=None,
        updated_at=None,
        grants_count=1,
        api_key_expires_at=None,
        api_key_version=1,
        api_key_last_rotated_at=None,
    )


class _RecordingSession:
    """Records every statement and answers the reads the handlers perform."""

    def __init__(self) -> None:
        self.statements: list[str] = []

    async def execute(self, statement, params=None, **kwargs):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if "set_config" in sql:
            return _Result()
        if "FROM agents" in sql:
            return _Result([_agent_row()])
        if "permission_grants" in sql:
            return _Result([SimpleNamespace(action="read:items")])
        if "FROM services" in sql:
            return _Result([SimpleNamespace(id=SVC_ID)])
        return _Result()

    def begin_nested(self):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _statements_reading_grants(session: _RecordingSession) -> list[str]:
    return [statement for statement in session.statements if "permission_grants" in statement]


def _assert_filters_expired(statements: list[str], source: str) -> None:
    assert statements, f"{source} must read permission_grants"
    for statement in statements:
        assert "expires_at IS NULL OR" in statement, (
            f"{source} grant read must keep grants without an expiry: {statement}"
        )
        assert "expires_at > now()" in statement, (
            f"{source} grant read must ignore an expired grant: {statement}"
        )


def _create_api_key_app():
    from fastapi import FastAPI
    from admin_api.api.api_keys import router as api_keys_router
    from admin_api.auth.sessions import require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(api_keys_router)

    session = _RecordingSession()

    async def mock_db():
        yield session

    app.dependency_overrides[get_db_session] = mock_db
    app.dependency_overrides[require_tenant_session] = lambda: None
    csrf_exempt(BASE_URL)
    app.add_middleware(CsrfMiddleware)
    return app, session


@pytest.mark.l4("C-b5050c3c")
@pytest.mark.asyncio
async def test_C_b5050c3c_other_readers_ignore_expired_grants() -> None:
    """Key creation, list_agents and get_agent only read live grants."""
    from admin_api.api.agents import get_agent, list_agents

    app, key_session = _create_api_key_app()
    with patch("admin_api.api.api_keys.audit_emit", new=AsyncMock()), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                BASE_URL,
                json={"service_id": SVC_ID, "allowed_actions": ["read:items"]},
            )
    assert resp.status_code == 201, resp.text

    list_session = _RecordingSession()
    await list_agents(
        tenant_id=TENANT_ID,
        q=None,
        has_access_to_service_id=None,
        session=list_session,
        _authz=None,
    )

    get_session = _RecordingSession()
    await get_agent(
        tenant_id=TENANT_ID,
        agent_id=AGENT_ID,
        session=get_session,
        _authz=None,
    )

    _assert_filters_expired(_statements_reading_grants(key_session), "classical key creation")
    _assert_filters_expired(_statements_reading_grants(list_session), "list_agents")
    _assert_filters_expired(_statements_reading_grants(get_session), "get_agent")
