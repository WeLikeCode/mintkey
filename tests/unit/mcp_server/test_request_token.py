"""
Unit tests: MCP Server request_token tool (T-1.5.4) + OPS-CC wire-form IDs.

Tests:
  1. Valid request with no constraints → returns token bundle.
  2. No permission_grant for (agent, service, action) → 403 not_authorized.
  3. Rate limit exceeded → 403 constraint_failed:rate_limit.
  4. Time window outside allowed hours → 403 constraint_failed:time_window.
  5. Denial emits token.denied audit event.
  6. (OPS-CC) request_token with svc_ wire form → 200; response service_id is svc_ form.
  7. (OPS-CC) request_token with raw UUID → 200 (backward compat); response service_id
     is svc_ form (canonicalised on the way out).
  8. (OPS-CC) Denial audit event service_id payload uses svc_ wire form.

Sources: Req 6 AC5, AC10; ADR-0016.4; ADR-0014.7; ADR-0008; ADR-0017.11; OPS-CC.
"""
from __future__ import annotations

import sys
import os
import time
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import respx
from httpx import ASGITransport, AsyncClient, Response

# Ensure mcp-server src and mintkey-models are importable
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
MCP_SERVER_SRC = os.path.join(REPO_ROOT, "apps/mcp-server", "src")
MINTKEY_MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for _p in (MCP_SERVER_SRC, MINTKEY_MODELS_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

AGENT_ID = "agent_01HZ0000000000000000000000"
TENANT_ID = "00000000-0000-0000-0000-000000000001"
AGENT_CTX = {"agent_id": AGENT_ID, "tenant_id": TENANT_ID, "status": "active"}
SERVICE_ID = "svc_01HZ0000000000000000000001"
ACTION = "call"

# Raw UUID that decodes to the same service as SERVICE_ID — for backward-compat tests.
# Derived: wire_to_db_uuid("svc_01HZ0000000000000000000001", "svc") == "018fc000-0000-0000-0000-000000000001"
SERVICE_UUID = "018fc000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# Row and session helpers
# ---------------------------------------------------------------------------


def _make_grant_row(constraints=None):
    """Return a MagicMock that looks like a permission_grants DB row."""
    row = MagicMock()
    row.agent_id = AGENT_ID
    row.service_id = SERVICE_ID
    row.action = ACTION
    row.constraints = constraints  # dict or None
    return row


def _mock_session_for_grant(grant_row):
    """
    Return an AsyncMock session whose execute() yields a result where
    fetchone() returns grant_row (or None for no-grant cases).
    """
    mock_result = MagicMock()
    mock_result.fetchone.return_value = grant_row

    mock_session = AsyncMock()
    mock_session.execute = AsyncMock(return_value=mock_result)
    return mock_session


# ---------------------------------------------------------------------------
# App fixture with dependency overrides
# ---------------------------------------------------------------------------


@pytest.fixture()
def app_factory():
    """
    Factory that returns a test app given a mock_session.
    Agent context is always AGENT_CTX (auth bypassed).
    audit_emit is always patched out (no real DB chain needed in unit tests).
    """
    from mcp_server.main import create_app
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context

    def build(mock_session):
        test_app = create_app()

        async def _fake_session():
            yield mock_session

        async def _fake_agent_ctx():
            return AGENT_CTX

        test_app.dependency_overrides[get_db_session] = _fake_session
        test_app.dependency_overrides[get_agent_context] = _fake_agent_ctx
        return test_app

    return build


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_request_returns_token_bundle(app_factory) -> None:
    """
    Agent has a permission grant with no constraints → returns token bundle.
    Source: Req 6 AC5; ADR-0016.4.
    """
    grant = _make_grant_row(constraints=None)
    mock_session = _mock_session_for_grant(grant)
    test_app = app_factory(mock_session)

    fake_token = "aGVhZA.Y2xhaW1z.c2ln"  # 3-part fake JWT
    fake_expires = int(time.time()) + 600

    with patch("mcp_server.tools.request_token.audit_emit", new=AsyncMock()):
        with respx.mock:
            respx.post("http://broker:8083/v1/issue").mock(
                return_value=Response(200, json={"token": fake_token, "expires_at": fake_expires})
            )
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/tools/request_token",
                    json={"service_id": SERVICE_ID, "action": ACTION},
                )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"] == fake_token
    assert body["expires_at"] == fake_expires
    assert body["service_id"] == SERVICE_ID


@pytest.mark.asyncio
async def test_unpermitted_service_returns_not_authorized(app_factory) -> None:
    """
    No permission_grant for (agent, service, action) → 403 permission_not_found.
    Source: Req 6 AC5; ADR-0016.4.
    """
    mock_session = _mock_session_for_grant(None)
    test_app = app_factory(mock_session)

    with patch("mintkey_models.audit.audit_emit", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            resp = await client.post(
                "/v1/tools/request_token",
                json={"service_id": SERVICE_ID, "action": ACTION},
            )

    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["code"] == "mintkey:not_authorized"
    assert body["reason_code"] == "permission_not_found"


@pytest.mark.asyncio
async def test_rate_limit_exceeded_returns_not_authorized(app_factory) -> None:
    """
    Permission has rate_limit: {requests_per_second: 1, burst: 1}.
    Two requests within 1 second → second returns 403 constraint_failed:rate_limit.
    Source: Req 6 AC10; ADR-0016.4.
    """
    constraints = {"rate_limit": {"requests_per_second": 1, "burst": 1}}
    grant = _make_grant_row(constraints=constraints)
    mock_session = _mock_session_for_grant(grant)
    test_app = app_factory(mock_session)

    fake_token = "aGVhZA.Y2xhaW1z.c2ln"
    fake_expires = int(time.time()) + 600

    with patch("mcp_server.tools.request_token.audit_emit", new=AsyncMock()):
        with respx.mock:
            respx.post("http://broker:8083/v1/issue").mock(
                return_value=Response(200, json={"token": fake_token, "expires_at": fake_expires})
            )
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                # First request: should succeed (burst allows 1)
                resp1 = await client.post(
                    "/v1/tools/request_token",
                    json={"service_id": SERVICE_ID, "action": ACTION},
                )
                # Second request: immediately after, should be rate-limited
                resp2 = await client.post(
                    "/v1/tools/request_token",
                    json={"service_id": SERVICE_ID, "action": ACTION},
                )

    assert resp1.status_code == 200, resp1.text
    assert resp2.status_code == 403, resp2.text
    body = resp2.json()
    assert body["code"] == "mintkey:not_authorized"
    assert body["reason_code"] == "constraint_failed:rate_limit"


@pytest.mark.asyncio
async def test_time_window_outside_returns_not_authorized(app_factory) -> None:
    """
    Permission has time_window constraint.
    Mock now() to be outside the allowed window → 403 constraint_failed:time_window.
    Source: Req 6 AC10; ADR-0016.4.
    """
    constraints = {
        "time_window": {
            "timezone": "UTC",
            "days": ["Mon", "Tue", "Wed", "Thu", "Fri"],
            "start_local": "09:00",
            "end_local": "17:00",
        }
    }
    grant = _make_grant_row(constraints=constraints)
    mock_session = _mock_session_for_grant(grant)
    test_app = app_factory(mock_session)

    # Inject a time that is outside the allowed window: Saturday at 23:00 UTC
    outside_window = datetime(2026, 5, 9, 23, 0, 0, tzinfo=timezone.utc)  # Saturday

    with patch("mcp_server.tools.request_token.audit_emit", new=AsyncMock()):
        with patch(
            "mcp_server.tools.request_token.evaluate_time_window",
            return_value=(False, "constraint_failed:time_window"),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/tools/request_token",
                    json={"service_id": SERVICE_ID, "action": ACTION},
                )

    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["code"] == "mintkey:not_authorized"
    assert body["reason_code"] == "constraint_failed:time_window"


@pytest.mark.asyncio
async def test_denial_emits_audit_event(app_factory) -> None:
    """
    On not_authorized, audit_emit is called with event_type='token.denied'.
    Source: ADR-0014.7; Req AUD-3.
    """
    mock_session = _mock_session_for_grant(None)
    test_app = app_factory(mock_session)

    mock_audit = AsyncMock()
    with patch("mcp_server.tools.request_token.audit_emit", new=mock_audit):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            await client.post(
                "/v1/tools/request_token",
                json={"service_id": SERVICE_ID, "action": ACTION},
            )

    assert mock_audit.called, "audit_emit was not called on denial"
    call_kwargs = mock_audit.call_args
    # The event_type argument is positional or keyword — check either form
    args = call_kwargs[0] if call_kwargs[0] else []
    kwargs = call_kwargs[1] if call_kwargs[1] else {}
    event_type = kwargs.get("event_type") or (args[2] if len(args) > 2 else None)
    assert event_type == "token.denied", (
        f"Expected event_type='token.denied', got {event_type!r}"
    )


# ---------------------------------------------------------------------------
# OPS-CC wire-form ID tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_request_token_with_svc_wire_form_succeeds(app_factory) -> None:
    """
    (OPS-CC) request_token body service_id in svc_ wire form → 200; response
    service_id is also in svc_ wire form.

    This is the primary post-OPS-CC flow: agents call list_services, get svc_
    IDs, and use them in request_token.

    Source: OPS-CC; ADR-0017.11.
    """
    grant = _make_grant_row(constraints=None)
    mock_session = _mock_session_for_grant(grant)
    test_app = app_factory(mock_session)

    fake_token = "aGVhZA.Y2xhaW1z.c2ln"
    fake_expires = int(time.time()) + 600

    with patch("mcp_server.tools.request_token.audit_emit", new=AsyncMock()):
        with respx.mock:
            respx.post("http://broker:8083/v1/issue").mock(
                return_value=Response(200, json={"token": fake_token, "expires_at": fake_expires})
            )
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/tools/request_token",
                    json={"service_id": SERVICE_ID, "action": ACTION},
                )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["service_id"].startswith("svc_"), (
        f"Response service_id should be svc_ wire form, got: {body['service_id']!r}"
    )


@pytest.mark.asyncio
async def test_request_token_with_raw_uuid_backward_compat(app_factory) -> None:
    """
    (OPS-CC) request_token body service_id as raw UUID → 200 (backward compat).
    Agents built before OPS-CC pass raw UUIDs; they must continue to work.
    Response service_id is canonicalised to svc_ form.

    Source: OPS-CC backward-compat requirement.
    """
    grant = _make_grant_row(constraints=None)
    mock_session = _mock_session_for_grant(grant)
    test_app = app_factory(mock_session)

    fake_token = "aGVhZA.Y2xhaW1z.c2ln"
    fake_expires = int(time.time()) + 600

    with patch("mcp_server.tools.request_token.audit_emit", new=AsyncMock()):
        with respx.mock:
            respx.post("http://broker:8083/v1/issue").mock(
                return_value=Response(200, json={"token": fake_token, "expires_at": fake_expires})
            )
            async with AsyncClient(
                transport=ASGITransport(app=test_app), base_url="http://test"
            ) as client:
                resp = await client.post(
                    "/v1/tools/request_token",
                    json={"service_id": SERVICE_UUID, "action": ACTION},
                )

    assert resp.status_code == 200, (
        f"Expected 200 for raw UUID (backward compat), got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    # Response service_id must be canonicalised to svc_ wire form.
    assert body["service_id"].startswith("svc_"), (
        f"Response service_id should be svc_ wire form even for raw-UUID input, "
        f"got: {body['service_id']!r}"
    )


@pytest.mark.asyncio
async def test_denial_audit_event_service_id_is_wire_form(app_factory) -> None:
    """
    (OPS-CC) When a request_token is denied, the audit event payload
    service_id uses svc_ wire form (operator-readable in audit_events).

    Source: OPS-CC; ADR-0014.7; ADR-0017.11.
    """
    mock_session = _mock_session_for_grant(None)
    test_app = app_factory(mock_session)

    mock_audit = AsyncMock()
    with patch("mcp_server.tools.request_token.audit_emit", new=mock_audit):
        async with AsyncClient(
            transport=ASGITransport(app=test_app), base_url="http://test"
        ) as client:
            await client.post(
                "/v1/tools/request_token",
                json={"service_id": SERVICE_UUID, "action": ACTION},
            )

    assert mock_audit.called, "audit_emit was not called on denial"
    kwargs = mock_audit.call_args[1] if mock_audit.call_args[1] else {}
    payload = kwargs.get("payload", {})
    audit_service_id = payload.get("service_id", "")
    assert audit_service_id.startswith("svc_"), (
        f"Audit event service_id should be svc_ wire form, got: {audit_service_id!r}"
    )
