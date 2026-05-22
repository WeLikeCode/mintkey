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
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
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
    mock_row.api_key_expires_at = None
    mock_row.api_key_version = 1
    mock_row.api_key_last_rotated_at = None

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


# ---------------------------------------------------------------------------
# UX-FB-AK-1 — expires_in on create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_default_expiry_is_null(app, mock_audit, mock_notify) -> None:
    """
    POST without expires_in → api_key_expires_at is None (back-compat).
    Source: UX-FB-AK-1.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"name": "no-expiry-agent"},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body.get("api_key_expires_at") is None, (
        f"Expected null api_key_expires_at for default create, got: {body.get('api_key_expires_at')}"
    )
    assert body.get("api_key_version") == 1
    assert body.get("api_key_last_rotated_at") is None


@pytest.mark.asyncio
async def test_create_agent_with_90d_expiry(app, mock_audit, mock_notify) -> None:
    """
    POST with expires_in='90d' → api_key_expires_at ≈ now+90d (within ±5s).
    Source: UX-FB-AK-1.
    """
    from datetime import datetime, timezone, timedelta

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        before = datetime.now(timezone.utc)
        resp = await client.post(
            BASE_URL_PATH,
            json={"name": "expiry-90d-agent", "expires_in": "90d"},
        )
        after = datetime.now(timezone.utc)

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body.get("api_key_expires_at") is not None, "api_key_expires_at must be set for 90d expiry"

    expires_at = datetime.fromisoformat(body["api_key_expires_at"])
    expected_min = before + timedelta(days=90) - timedelta(seconds=5)
    expected_max = after + timedelta(days=90) + timedelta(seconds=5)
    assert expected_min <= expires_at <= expected_max, (
        f"api_key_expires_at {expires_at} not within ±5s of now+90d"
    )


@pytest.mark.asyncio
async def test_create_agent_invalid_expires_in_returns_422(app, mock_audit, mock_notify) -> None:
    """
    POST with expires_in='garbage' → 422 with mintkey:code: invalid_expires_in.
    Source: UX-FB-AK-1.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"name": "bad-expiry-agent", "expires_in": "garbage"},
        )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "invalid_expires_in", f"Expected invalid_expires_in, got: {body}"


# ---------------------------------------------------------------------------
# UX-FB-AK-1 — rotate-key unit tests
# ---------------------------------------------------------------------------


def _make_mock_session_with_agent_row(agent_uuid_str: str, tenant_id: str, version: int = 1, expires_at=None):
    """Return a mock session that yields a known agent row on SELECT agents query."""
    from unittest.mock import MagicMock
    from datetime import datetime, timezone

    session = MagicMock()
    session._execute_calls = []

    mock_row = MagicMock()
    mock_row.id = agent_uuid_str
    mock_row.tenant_id = tenant_id
    mock_row.api_key_fingerprint = "oldfp0000deadbeef"
    mock_row.api_key_version = version
    mock_row.api_key_expires_at = expires_at
    mock_row.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        result = MagicMock()
        # Detect agent SELECT by checking if the SQL touches the agents table
        sql_str = str(args[0]) if args else ""
        if "FROM agents" in sql_str and "WHERE" in sql_str and "api_key_expires_at" in sql_str:
            result.fetchone.return_value = mock_row
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


@pytest.mark.asyncio
async def test_rotate_key_hard_cutover(mock_audit, mock_notify) -> None:
    """
    POST rotate-key returns 200 with new plaintext key; new key differs from any existing.
    Source: UX-FB-AK-1.
    """
    import sys, os
    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    # Derive a wire-form agent_id and its UUID for the mock session
    from admin_api.api.agents import _new_agent_id, _wire_id_to_uuid, _CROCKFORD
    import uuid

    wire_id = _new_agent_id()
    agent_uuid_str = _wire_id_to_uuid(wire_id, "agent_")

    mock_session = _make_mock_session_with_agent_row(agent_uuid_str, TENANT_ID, version=1)

    local_app = FastAPI()
    local_app.include_router(agents_router)

    async def mock_db():
        yield mock_session

    local_app.dependency_overrides[get_db_session] = mock_db
    rotate_path = f"{BASE_URL_PATH}/{wire_id}/rotate-key"
    csrf_exempt(rotate_path)
    local_app.add_middleware(CsrfMiddleware)

    async with AsyncClient(transport=ASGITransport(app=local_app), base_url="http://test") as client:
        resp = await client.post(rotate_path, json={})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "api_key" in body, "api_key must be returned on rotate"
    assert body["api_key"].startswith("mk_agent_"), "New key must have mk_agent_ prefix"
    assert body["api_key_version"] == 2, f"Expected version 2, got {body['api_key_version']}"


@pytest.mark.asyncio
async def test_rotate_key_bumps_version(mock_audit, mock_notify) -> None:
    """
    POST rotate-key increments version: 1→2.
    Source: UX-FB-AK-1.
    """
    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router, _new_agent_id, _wire_id_to_uuid
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    wire_id = _new_agent_id()
    agent_uuid_str = _wire_id_to_uuid(wire_id, "agent_")

    # Start at version 2 to verify the bump goes to 3
    mock_session = _make_mock_session_with_agent_row(agent_uuid_str, TENANT_ID, version=2)

    local_app = FastAPI()
    local_app.include_router(agents_router)

    async def mock_db():
        yield mock_session

    local_app.dependency_overrides[get_db_session] = mock_db
    rotate_path = f"{BASE_URL_PATH}/{wire_id}/rotate-key"
    csrf_exempt(rotate_path)
    local_app.add_middleware(CsrfMiddleware)

    async with AsyncClient(transport=ASGITransport(app=local_app), base_url="http://test") as client:
        resp = await client.post(rotate_path, json={})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["api_key_version"] == 3, f"Expected version 3 (bump from 2), got {body['api_key_version']}"


@pytest.mark.asyncio
async def test_rotate_key_preserves_expiry_policy_when_omitted(mock_audit, mock_notify) -> None:
    """
    POST rotate-key without expires_in, when agent had 30d expiry, sets new ≈now+30d.
    Source: UX-FB-AK-1.
    """
    from datetime import datetime, timezone, timedelta
    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router, _new_agent_id, _wire_id_to_uuid
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    wire_id = _new_agent_id()
    agent_uuid_str = _wire_id_to_uuid(wire_id, "agent_")

    # Agent was created on 2026-01-01 with expiry 30d later = 2026-01-31
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    original_expiry = created_at + timedelta(days=30)

    mock_session = _make_mock_session_with_agent_row(
        agent_uuid_str, TENANT_ID, version=1, expires_at=original_expiry
    )
    # Override created_at on the mock row (already set in helper)

    local_app = FastAPI()
    local_app.include_router(agents_router)

    async def mock_db():
        yield mock_session

    local_app.dependency_overrides[get_db_session] = mock_db
    rotate_path = f"{BASE_URL_PATH}/{wire_id}/rotate-key"
    csrf_exempt(rotate_path)
    local_app.add_middleware(CsrfMiddleware)

    before = datetime.now(timezone.utc)
    async with AsyncClient(transport=ASGITransport(app=local_app), base_url="http://test") as client:
        resp = await client.post(rotate_path, json={})
    after = datetime.now(timezone.utc)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("api_key_expires_at") is not None, "Expiry must be preserved (re-anchored)"

    new_exp = datetime.fromisoformat(body["api_key_expires_at"])
    expected_min = before + timedelta(days=30) - timedelta(seconds=5)
    expected_max = after + timedelta(days=30) + timedelta(seconds=5)
    assert expected_min <= new_exp <= expected_max, (
        f"Re-anchored expiry {new_exp} not within ±5s of now+30d"
    )


@pytest.mark.asyncio
async def test_rotate_key_explicit_empty_string_removes_expiry(mock_audit, mock_notify) -> None:
    """
    POST rotate-key with expires_in='' removes expiry (api_key_expires_at → null).
    Source: UX-FB-AK-1.
    """
    from datetime import datetime, timezone, timedelta
    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router, _new_agent_id, _wire_id_to_uuid
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    wire_id = _new_agent_id()
    agent_uuid_str = _wire_id_to_uuid(wire_id, "agent_")

    existing_expiry = datetime(2026, 6, 1, tzinfo=timezone.utc)
    mock_session = _make_mock_session_with_agent_row(
        agent_uuid_str, TENANT_ID, version=1, expires_at=existing_expiry
    )

    local_app = FastAPI()
    local_app.include_router(agents_router)

    async def mock_db():
        yield mock_session

    local_app.dependency_overrides[get_db_session] = mock_db
    rotate_path = f"{BASE_URL_PATH}/{wire_id}/rotate-key"
    csrf_exempt(rotate_path)
    local_app.add_middleware(CsrfMiddleware)

    async with AsyncClient(transport=ASGITransport(app=local_app), base_url="http://test") as client:
        resp = await client.post(rotate_path, json={"expires_in": ""})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("api_key_expires_at") is None, (
        f"Expected null api_key_expires_at after explicit '' removal, got: {body.get('api_key_expires_at')}"
    )


@pytest.mark.asyncio
async def test_rotate_key_audit_emitted_with_no_plaintext(mock_notify) -> None:
    """
    POST rotate-key emits audit with new_fingerprint but must NOT contain 'mk_agent_' plaintext.
    Source: UX-FB-AK-1; S-SEC-1; ADR-0014.7.
    """
    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router, _new_agent_id, _wire_id_to_uuid
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt
    from unittest.mock import AsyncMock, patch

    wire_id = _new_agent_id()
    agent_uuid_str = _wire_id_to_uuid(wire_id, "agent_")

    mock_session = _make_mock_session_with_agent_row(agent_uuid_str, TENANT_ID, version=1)

    local_app = FastAPI()
    local_app.include_router(agents_router)

    async def mock_db():
        yield mock_session

    local_app.dependency_overrides[get_db_session] = mock_db
    rotate_path = f"{BASE_URL_PATH}/{wire_id}/rotate-key"
    csrf_exempt(rotate_path)
    local_app.add_middleware(CsrfMiddleware)

    with patch("admin_api.api.agents.audit_emit", new=AsyncMock()) as mock_audit_fn:
        async with AsyncClient(transport=ASGITransport(app=local_app), base_url="http://test") as client:
            resp = await client.post(rotate_path, json={})

    assert resp.status_code == 200, resp.text
    api_key = resp.json()["api_key"]
    assert api_key.startswith("mk_agent_")

    # Verify audit was called and payload does NOT contain plaintext
    mock_audit_fn.assert_called_once()
    call_kwargs = mock_audit_fn.call_args.kwargs
    assert call_kwargs.get("event_type") == "agent.api_key_rotated"

    payload = call_kwargs.get("payload", {})
    payload_str = str(payload)
    assert "mk_agent_" not in payload_str, (
        f"Plaintext api_key must NOT appear in audit payload, got: {payload_str}"
    )


# ---------------------------------------------------------------------------
# S8-codeql: py/stack-trace-exposure — rotate-key invalid expires_in
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotate_key_invalid_expires_in_title_is_generic(mock_audit, mock_notify) -> None:
    """
    POST rotate-key with invalid expires_in must return 422 with:
      - mintkey:code: invalid_expires_in
      - title that does NOT echo back user-supplied input (no stack-trace exposure)

    Closes CodeQL alert py/stack-trace-exposure @ agents.py:641.
    Source: S8-codeql; CWE-209.
    """
    from fastapi import FastAPI
    from admin_api.api.agents import router as agents_router, _new_agent_id, _wire_id_to_uuid
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    wire_id = _new_agent_id()
    agent_uuid_str = _wire_id_to_uuid(wire_id, "agent_")
    mock_session = _make_mock_session_with_agent_row(agent_uuid_str, TENANT_ID, version=1)

    local_app = FastAPI()
    local_app.include_router(agents_router)

    async def mock_db():
        yield mock_session

    local_app.dependency_overrides[get_db_session] = mock_db
    rotate_path = f"{BASE_URL_PATH}/{wire_id}/rotate-key"
    csrf_exempt(rotate_path)
    local_app.add_middleware(CsrfMiddleware)

    # Use a value that would appear in the ValueError message to verify it isn't echoed
    malicious_input = "INJECTED_VALUE_12345"

    async with AsyncClient(transport=ASGITransport(app=local_app), base_url="http://test") as client:
        resp = await client.post(rotate_path, json={"expires_in": malicious_input})

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "invalid_expires_in", f"Expected invalid_expires_in, got: {body}"
    title = body.get("title", "")
    assert malicious_input not in title, (
        f"Stack-trace exposure: user input echoed back in error title: {title!r}"
    )
