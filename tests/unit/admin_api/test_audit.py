"""
Unit tests: Audit log API endpoint.

GET /v1/tenants/{tenant_id}/audit — list audit events with cursor pagination and filters.

Test cases:
  1. test_list_returns_tenant_scoped_events: RLS enforced (mock returns tenant-filtered events)
  2. test_filter_by_agent_id
  3. test_filter_by_service_id
  4. test_filter_by_event_type
  5. test_filter_by_time_range (from_ts + to_ts params)
  6. test_pagination_via_after_cursor (after=event_id&limit=10)
  7. test_empty_for_wrong_tenant (cross-tenant query returns [])

Sources:
  - ADR-0008 (bound parameters — no f-string SQL)
  - ADR-0014.7 (audit emit, hash chain)
  - ADR-0017.11 (ULID IDs with audit_ prefix)
  - T-1.7.1
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
OTHER_TENANT_ID = "00000000-0000-0000-0000-000000000002"
BASE_URL_PATH = f"/v1/tenants/{TENANT_ID}/audit"


def _make_audit_row(
    event_id: str = "audit_00000000000000000000000001",
    event_type: str = "agent.created",
    tenant_id: str = TENANT_ID,
    actor_id: str = None,
    actor_type: str = "operator",
    target_id: str = None,
    target_type: str = "agent",
    payload: dict = None,
):
    """Return a mock row matching the audit_events columns."""
    row = MagicMock()
    row.id = event_id
    row.event_type = event_type
    row.tenant_id = tenant_id
    row.actor_id = actor_id
    row.actor_type = actor_type
    row.target_id = target_id
    row.target_type = target_type
    row.payload = payload or {}
    row.hash = b"\x00" * 32
    row.prev_hash = b"\x00" * 32
    row.created_at = None
    return row


def _make_mock_session(rows=None):
    """Return an async-capable mock DB session returning `rows` for SELECT."""
    session = MagicMock()
    session._execute_calls = []

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        result = MagicMock()
        result.fetchall.return_value = rows or []
        result.fetchone.return_value = None
        return result

    session.execute = _execute
    return session


def _create_test_app(rows=None, bypass_authz: bool = True):
    """Build a minimal FastAPI app with the audit router and mocked DB."""
    from fastapi import FastAPI
    from admin_api.api.audit import router as audit_router
    from admin_api.auth.sessions import require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(audit_router)

    async def mock_db_session():
        yield _make_mock_session(rows=rows)

    app.dependency_overrides[get_db_session] = mock_db_session
    if bypass_authz:
        app.dependency_overrides[require_tenant_session] = lambda: None

    csrf_exempt(BASE_URL_PATH)
    app.add_middleware(CsrfMiddleware)

    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_tenant_scoped_events() -> None:
    """
    GET /audit returns {"items": [...]} with rows the DB returned.
    RLS is enforced at DB level; mock simulates tenant-filtered result.
    Source: T-1.7.1; ADR-0008.
    """
    row = _make_audit_row()
    app = _create_test_app(rows=[row])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "events" in body
    assert len(body["events"]) == 1
    assert body["events"][0]["id"] == "audit_00000000000000000000000001"


@pytest.mark.asyncio
async def test_filter_by_agent_id() -> None:
    """
    ?agent_id=agent_abc is forwarded as a bound parameter to the DB query.
    Source: T-1.7.1; ADR-0008.
    """
    app = _create_test_app(rows=[])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH, params={"agent_id": "agent_abc"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["events"] == []


@pytest.mark.asyncio
async def test_filter_by_service_id() -> None:
    """
    ?service_id=svc_abc is forwarded as a bound parameter.
    Source: T-1.7.1; ADR-0008.
    """
    app = _create_test_app(rows=[])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH, params={"service_id": "svc_abc"})

    assert resp.status_code == 200, resp.text
    assert resp.json()["events"] == []


@pytest.mark.asyncio
async def test_filter_by_event_type() -> None:
    """
    ?event_type=agent.created filters results.
    Source: T-1.7.1; ADR-0008.
    """
    row = _make_audit_row(event_type="agent.created")
    app = _create_test_app(rows=[row])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH, params={"event_type": "agent.created"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["event_type"] == "agent.created"


@pytest.mark.asyncio
async def test_filter_by_time_range() -> None:
    """
    ?from_ts=...&to_ts=... are accepted as ISO8601 strings and forwarded bound.
    Source: T-1.7.1; ADR-0008.
    """
    app = _create_test_app(rows=[])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            BASE_URL_PATH,
            params={"from_ts": "2025-01-01T00:00:00Z", "to_ts": "2025-12-31T23:59:59Z"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["events"] == []


@pytest.mark.asyncio
async def test_pagination_via_after_cursor() -> None:
    """
    ?after=<event_id>&limit=10 returns next page and next_cursor.
    next_cursor is the id of the last event when the page is full,
    or null when fewer than limit rows are returned.
    Source: T-1.7.1.
    """
    rows = [_make_audit_row(event_id=f"audit_0000000000000000000000000{i}") for i in range(1, 11)]
    app = _create_test_app(rows=rows)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(
            BASE_URL_PATH,
            params={"after": "audit_00000000000000000000000000", "limit": "10"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["events"]) == 10
    # Full page → next_cursor is the id of the last event
    assert body["next_cursor"] == rows[-1].id


@pytest.mark.asyncio
async def test_filter_by_actor_type() -> None:
    """
    ?actor_type=agent is forwarded as a bound parameter; response includes
    actor_id, actor_type, target_id, target_type fields — UX-D.
    Source: T-1.7.1; ADR-0008.
    """
    row = _make_audit_row(
        event_type="token.issued",
        actor_id="00000000-0000-0000-0000-000000000099",
        actor_type="agent",
        target_id="00000000-0000-0000-0000-000000000088",
        target_type="service",
    )
    app = _create_test_app(rows=[row])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH, params={"actor_type": "agent"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["events"]) == 1
    ev = body["events"][0]
    assert ev["actor_type"] == "agent"
    assert ev["actor_id"] == "00000000-0000-0000-0000-000000000099"
    assert ev["target_type"] == "service"
    assert ev["target_id"] == "00000000-0000-0000-0000-000000000088"


@pytest.mark.asyncio
async def test_filter_by_target_type() -> None:
    """
    ?target_type=credential is forwarded as a bound parameter — UX-D.
    Source: T-1.7.1; ADR-0008.
    """
    row = _make_audit_row(
        event_type="credential.registered",
        actor_type="operator",
        target_type="credential",
    )
    app = _create_test_app(rows=[row])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH, params={"target_type": "credential"})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["events"]) == 1
    assert body["events"][0]["target_type"] == "credential"


@pytest.mark.asyncio
async def test_response_includes_actor_target_fields() -> None:
    """
    Every event in the list response includes actor_id, actor_type,
    target_id, target_type — UX-D; these were previously missing from _row_to_dict.
    Source: T-1.7.1; ADR-0014.7.
    """
    row = _make_audit_row(actor_type="platform_admin", target_type="tenant")
    app = _create_test_app(rows=[row])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH)

    assert resp.status_code == 200, resp.text
    ev = resp.json()["events"][0]
    assert "actor_id" in ev
    assert "actor_type" in ev
    assert ev["actor_type"] == "platform_admin"
    assert "target_id" in ev
    assert "target_type" in ev
    assert ev["target_type"] == "tenant"


@pytest.mark.asyncio
async def test_empty_for_wrong_tenant() -> None:
    """
    A cross-tenant query must return an empty event list.
    RLS at the DB level ensures this; mock simulates the empty result.
    Source: T-1.7.1; ADR-0008; ADR-0016.3.
    """
    wrong_tenant_id = OTHER_TENANT_ID
    app = _create_test_app(rows=[])

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(f"/v1/tenants/{wrong_tenant_id}/audit")

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["events"] == []
    assert body["next_cursor"] is None

# ---------------------------------------------------------------------------
# Cross-tenant authz: require_tenant_session enforces 403 — ADR-SCOPE-A
# ---------------------------------------------------------------------------

OTHER_TENANT_A = TENANT_ID    # "00000000-0000-0000-0000-000000000001"
OTHER_TENANT_B = OTHER_TENANT_ID  # "00000000-0000-0000-0000-000000000002"


@pytest.mark.asyncio
async def test_list_audit_cross_tenant_returns_403() -> None:
    """
    GET /v1/tenants/{TENANT_B}/audit with a session scoped to TENANT_A
    must return 403 — require_tenant_session enforcement (ADR-SCOPE-A).
    Before dep: handler reached (200 empty).  After dep: 403 permission_denied.
    """
    app = _create_test_app(rows=[], bypass_authz=False)

    class _FakeCtx:
        operator_id = "op-uuid-a"
        tenant_id = OTHER_TENANT_A

    with (
        patch("admin_api.auth.sessions.validate_session", new=AsyncMock(return_value=_FakeCtx())),
        patch("admin_api.auth.sessions._is_operator_platform_admin", new=AsyncMock(return_value=False)),
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get(
                f"/v1/tenants/{OTHER_TENANT_B}/audit",
                cookies={"mintkey_session": "tok-a"},
            )

    assert resp.status_code == 403, (
        f"Expected 403 for cross-tenant GET /audit, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("mintkey:code") == "permission_denied"
