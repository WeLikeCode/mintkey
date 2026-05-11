"""
Unit tests: Agent CRUD endpoints.

POST   /v1/tenants/{tid}/agents           — create (201, api_key shown once)
GET    /v1/tenants/{tid}/agents           — list (200)
GET    /v1/tenants/{tid}/agents/{aid}     — get (200, no api_key)
DELETE /v1/tenants/{tid}/agents/{aid}     — delete (204)

Sources:
  - ADR-0008 (bound parameters — no f-string SQL)
  - ADR-0014.7 (audit emit on every state change)
  - ADR-0017.11 (ULID IDs with agent_ prefix)
  - S-SEC-1 (no plaintext API key in DB or audit)
  - T-1.4.1 (Agent CRUD with API key generation)
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
AGENT_ID = "agent_00000000000000000000000001"
BASE_URL_PATH = f"/v1/tenants/{TENANT_ID}/agents"


def _make_mock_session():
    """Return an async-capable mock DB session."""
    session = MagicMock()

    # Track execute calls for assertion
    session._execute_calls = []

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def create_test_app():
    """
    Create an app with:
      - agents router included
      - get_db_session overridden to a mock (no real DB)
      - CSRF middleware present but agents paths registered as exempt
    """
    from fastapi import FastAPI
    from admin_api.api.health import router as health_router
    from admin_api.api.agents import router as agents_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(health_router)
    app.include_router(agents_router)

    # Override DB dependency with mock
    async def mock_db_session():
        yield _make_mock_session()

    app.dependency_overrides[get_db_session] = mock_db_session

    # Register agent paths as CSRF-exempt for unit tests
    csrf_exempt(BASE_URL_PATH)
    csrf_exempt(f"{BASE_URL_PATH}/{AGENT_ID}")

    app.add_middleware(CsrfMiddleware)

    return app


@pytest.fixture()
def app():
    return create_test_app()


@pytest.fixture()
def mock_audit():
    """Patch audit_emit so unit tests don't hit the DB hash-chain logic."""
    with patch("admin_api.api.agents.audit_emit", new=AsyncMock()) as m:
        yield m


@pytest.fixture()
def mock_notify():
    """Patch notify_change so unit tests don't hit a real DB."""
    with patch("admin_api.api.agents.notify_change", new=AsyncMock()) as m:
        yield m


# ---------------------------------------------------------------------------
# POST — create agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_returns_201_with_api_key(app, mock_audit, mock_notify) -> None:
    """
    POST /v1/tenants/{tid}/agents with valid payload returns 201.
    Response id starts with 'agent_' — ADR-0017.11.
    Response includes api_key starting with 'mk_agent_' — shown once.
    Source: T-1.4.1; ADR-0017.11.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"name": "my-agent", "description": "A test agent"},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("agent_"), f"Expected agent_ prefix, got: {body['id']}"
    assert "api_key" in body, "api_key must be present on create"
    assert body["api_key"].startswith("mk_agent_"), f"Expected mk_agent_ prefix, got: {body['api_key']}"
    assert "mcp_endpoint" in body


@pytest.mark.asyncio
async def test_create_agent_api_key_not_stored_plaintext(app, mock_audit, mock_notify) -> None:
    """
    The INSERT executed for agent creation must NOT contain the plaintext api_key.
    DB stores only Argon2id hash and fingerprint — S-SEC-1, T-1.4.1.
    """
    executed_params: list = []

    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    local_app = FastAPI()
    local_app.include_router(agents_router)

    async def mock_db_session():
        session = MagicMock()

        async def _execute(*args, **kwargs):
            # Capture all args/kwargs
            executed_params.append((args, kwargs))
            result = MagicMock()
            result.fetchone.return_value = None
            result.fetchall.return_value = []
            return result

        session.execute = _execute
        yield session

    local_app.dependency_overrides[get_db_session] = mock_db_session
    csrf_exempt(BASE_URL_PATH)
    local_app.add_middleware(CsrfMiddleware)

    async with AsyncClient(transport=ASGITransport(app=local_app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"name": "my-agent"},
        )

    assert resp.status_code == 201, resp.text
    api_key = resp.json()["api_key"]
    assert api_key.startswith("mk_agent_")

    # Verify the plaintext key does not appear in any execute call
    for call_args, call_kwargs in executed_params:
        for arg in call_args:
            if isinstance(arg, dict):
                for v in arg.values():
                    assert api_key not in str(v), "Plaintext API key found in DB execute args"
        for v in call_kwargs.values():
            if isinstance(v, dict):
                for val in v.values():
                    assert api_key not in str(val), "Plaintext API key found in DB execute kwargs"


@pytest.mark.asyncio
async def test_get_agent_does_not_return_api_key(app, mock_audit, mock_notify) -> None:
    """
    GET /v1/tenants/{tid}/agents/{aid} returns 200 without api_key field.
    Plaintext key is shown exactly once on creation — S-SEC-1, T-1.4.1.
    """
    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt
    from unittest.mock import MagicMock

    local_app = FastAPI()
    local_app.include_router(agents_router)

    # Return a mock agent row on SELECT
    mock_row = MagicMock()
    mock_row.id = "00000000-0000-0000-0000-000000000099"
    mock_row.tenant_id = TENANT_ID
    mock_row.name = "existing-agent"
    mock_row.description = "desc"
    mock_row.api_key_fingerprint = "abcd1234"
    mock_row.mcp_endpoint = "http://localhost:8100/v1/agents/agent_test"
    mock_row.status = "active"
    mock_row.rate_limit_rps = None
    mock_row.created_at = None
    mock_row.updated_at = None

    async def mock_db_session():
        session = MagicMock()

        async def _execute(*args, **kwargs):
            result = MagicMock()
            result.fetchone.return_value = mock_row
            result.fetchall.return_value = [mock_row]
            return result

        session.execute = _execute
        yield session

    local_app.dependency_overrides[get_db_session] = mock_db_session
    csrf_exempt(f"{BASE_URL_PATH}/{AGENT_ID}")
    local_app.add_middleware(CsrfMiddleware)

    async with AsyncClient(transport=ASGITransport(app=local_app), base_url="http://test") as client:
        resp = await client.get(f"{BASE_URL_PATH}/{AGENT_ID}")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "api_key" not in body, "api_key must NOT be present on GET"
    assert "api_key_hash" not in body, "api_key_hash must NOT be present on GET"


@pytest.mark.asyncio
async def test_create_agent_audit_carries_fingerprint_not_plaintext(app, mock_audit, mock_notify) -> None:
    """
    audit_emit is called with event_type="agent.created" and payload containing
    api_key_fingerprint but NOT the plaintext api_key — S-SEC-1, ADR-0014.7, T-1.4.1.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"name": "audited-agent"},
        )

    assert resp.status_code == 201, resp.text
    api_key = resp.json()["api_key"]
    assert api_key.startswith("mk_agent_")

    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs.get("event_type") == "agent.created"

    payload = call_kwargs.get("payload", {})
    assert "api_key_fingerprint" in payload, "audit payload must contain api_key_fingerprint"
    # The plaintext key must NOT appear anywhere in the audit payload
    payload_str = str(payload)
    assert "mk_agent_" not in payload_str, "Plaintext api_key must NOT appear in audit payload"


@pytest.mark.asyncio
async def test_delete_agent_returns_204(app, mock_audit, mock_notify) -> None:
    """
    DELETE /v1/tenants/{tid}/agents/{aid} returns 204.
    Source: T-1.4.1; ADR-0014.7.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.delete(f"{BASE_URL_PATH}/{AGENT_ID}")

    assert resp.status_code == 204, resp.text


@pytest.mark.asyncio
async def test_list_agents_returns_200(app) -> None:
    """
    GET /v1/tenants/{tid}/agents returns 200 with {"agents": [...]}.
    Source: T-1.4.1.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "agents" in body
    assert isinstance(body["agents"], list)
