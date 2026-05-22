"""
Unit tests: Agent revocation endpoint.

POST /v1/tenants/{tid}/agents/{aid}/revoke — revoke agent (200)

Sources:
  - ADR-0008 (bound parameters — no f-string SQL)
  - ADR-0014.1 (global channel mintkey:agent)
  - ADR-0014.7 (audit emit on every state change)
  - T-1.9.1 (agent revocation endpoint)
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
AGENT_ID = "agent_00000000000000000000000001"
REVOKE_PATH = f"/v1/tenants/{TENANT_ID}/agents/{AGENT_ID}/revoke"


def _make_session_with_agent():
    """Return a mock session where the agent exists."""
    session = MagicMock()
    session._execute_calls = []

    mock_row = MagicMock()
    mock_row.id = AGENT_ID

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        result = MagicMock()
        result.fetchone.return_value = mock_row
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _make_session_without_agent():
    """Return a mock session where agent lookup returns None."""
    session = MagicMock()
    session._execute_calls = []

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _create_revoke_app(session_factory):
    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(agents_router)

    async def mock_db_session():
        yield session_factory()

    app.dependency_overrides[get_db_session] = mock_db_session
    csrf_exempt(REVOKE_PATH)
    app.add_middleware(CsrfMiddleware)
    return app


@pytest.fixture()
def app_with_agent():
    return _create_revoke_app(_make_session_with_agent)


@pytest.fixture()
def app_without_agent():
    return _create_revoke_app(_make_session_without_agent)


@pytest.fixture()
def mock_audit():
    with patch("admin_api.api.agents.audit_emit", new=AsyncMock()) as m:
        yield m


@pytest.fixture()
def mock_notify():
    with patch("admin_api.api.agents.notify_change", new=AsyncMock()) as m:
        yield m


# ---------------------------------------------------------------------------
# POST — revoke agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_agent_sets_status_revoked(app_with_agent, mock_audit, mock_notify) -> None:
    """
    POST /revoke on an existing agent returns 200 and confirms status='revoked'
    is set via an UPDATE execute call — T-1.9.1; ADR-0008.
    """
    captured_session = None

    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    local_app = FastAPI()
    local_app.include_router(agents_router)

    mock_row = MagicMock()
    mock_row.id = AGENT_ID
    executed_sqls: list[str] = []

    async def mock_db_session():
        nonlocal captured_session
        session = MagicMock()

        async def _execute(stmt, params=None, **kwargs):
            sql = str(stmt) if hasattr(stmt, "__str__") else stmt
            executed_sqls.append(sql)
            result = MagicMock()
            # First SELECT returns the agent row; subsequent calls return None/empty
            result.fetchone.return_value = mock_row
            result.fetchall.return_value = []
            return result

        session.execute = _execute
        captured_session = session
        yield session

    local_app.dependency_overrides[get_db_session] = mock_db_session
    csrf_exempt(REVOKE_PATH)
    local_app.add_middleware(CsrfMiddleware)

    async with AsyncClient(transport=ASGITransport(app=local_app), base_url="http://test") as client:
        resp = await client.post(REVOKE_PATH)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert body["agent_id"] == AGENT_ID

    # Confirm an UPDATE with 'revoked' was executed
    update_calls = [s for s in executed_sqls if "UPDATE" in s.upper() and "revoked" in s.lower()]
    assert update_calls, f"Expected UPDATE with 'revoked' in SQL, got: {executed_sqls}"


@pytest.mark.asyncio
async def test_revoke_agent_emits_audit_event(app_with_agent, mock_audit, mock_notify) -> None:
    """
    POST /revoke calls audit_emit with event_type="agent.revoked" — ADR-0014.7; T-1.9.1.
    """
    async with AsyncClient(transport=ASGITransport(app=app_with_agent), base_url="http://test") as client:
        resp = await client.post(REVOKE_PATH)

    assert resp.status_code == 200, resp.text
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs.get("event_type") == "agent.revoked"


@pytest.mark.asyncio
async def test_revoke_agent_notifies_global_channel(app_with_agent, mock_audit, mock_notify) -> None:
    """
    POST /revoke fires NOTIFY on the global mintkey:agent channel — ADR-0014.1; T-1.9.1.
    """
    async with AsyncClient(transport=ASGITransport(app=app_with_agent), base_url="http://test") as client:
        resp = await client.post(REVOKE_PATH)

    assert resp.status_code == 200, resp.text
    mock_notify.assert_called_once()
    call_args = mock_notify.call_args
    # Second positional arg is the channel name
    channel = call_args.args[1] if call_args.args else call_args.kwargs.get("channel")
    assert channel == "mintkey:agent", f"Expected mintkey:agent channel, got: {channel}"


@pytest.mark.asyncio
async def test_revoke_nonexistent_agent_returns_404(app_without_agent, mock_audit, mock_notify) -> None:
    """
    POST /revoke on a non-existent agent returns 404 — T-1.9.1.
    """
    async with AsyncClient(transport=ASGITransport(app=app_without_agent), base_url="http://test") as client:
        resp = await client.post(REVOKE_PATH)

    assert resp.status_code == 404, resp.text
    body = resp.json()
    assert "not_found" in str(body)
