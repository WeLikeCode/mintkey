"""
Unit tests for admin_api.api.email_permission_grants (feat/email-permission-grants).

Tests:
  T-01  test_create_grant_happy_path              — POST returns 201, row inserted, audit row emitted.
  T-02  test_create_grant_duplicate_returns_409   — unique constraint violation handled cleanly.
  T-03  test_create_grant_nonexistent_agent_returns_422
  T-04  test_create_grant_nonexistent_email_service_returns_422
  T-05  test_create_grant_cross_tenant_rejected   — agent in tenant A, email_service in tenant B → 422.
  T-06  test_list_grants_scoped_to_tenant         — list returns only tenant's grants.
  T-07  test_delete_grant                         — 204, audit row emitted.

Source: feat/email-permission-grants.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers: minimal async DB session mock (mirrors test_email_services.py style)
# ---------------------------------------------------------------------------


class _FakeRow:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeResult:
    def __init__(self, row: Any = None, rows: list[Any] | None = None) -> None:
        self._row = row
        self._rows = rows or ([] if row is None else [row])

    def fetchone(self) -> Any:
        return self._row

    def fetchall(self) -> list[Any]:
        return self._rows

    def one_or_none(self) -> Any:
        return self._row


class _FakeSession:
    def __init__(self, query_results: dict[str, Any] | None = None) -> None:
        self._results = query_results or {}
        self.executed_sql: list[tuple[str, dict[str, Any]]] = []
        self.audit_calls: list[dict[str, Any]] = []

    async def execute(self, stmt: Any, params: Any = None) -> Any:
        sql: str = str(stmt) if not hasattr(stmt, "text") else stmt.text
        self.executed_sql.append((sql, params or {}))
        for fragment, result in self._results.items():
            if fragment in sql:
                return result
        return _FakeResult(None)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


def _make_session(**results: Any) -> _FakeSession:
    return _FakeSession(query_results=results)


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from admin_api.api.email_permission_grants import (
    EmailPermissionGrantCreate,
    create_email_permission_grant,
    list_email_permission_grants,
    delete_email_permission_grant,
)


# ---------------------------------------------------------------------------
# Shared UUIDs
# ---------------------------------------------------------------------------

TENANT_A = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
AGENT_ID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
ESVC_ID = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
GRANT_ID = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


# ---------------------------------------------------------------------------
# T-01: Create grant — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_grant_happy_path() -> None:
    """
    T-01: POST /v1/tenants/{tid}/email-permission-grants with a valid agent + email_service
    returns 201, inserts a row, and emits an email_permission_grant.created audit event.
    """
    agent_row = _FakeRow(id=str(AGENT_ID))
    esvc_row = _FakeRow(id=str(ESVC_ID))
    session = _make_session(
        **{
            "SELECT id FROM agents": _FakeResult(agent_row),
            "SELECT id FROM email_services": _FakeResult(esvc_row),
        }
    )

    body = EmailPermissionGrantCreate(
        agent_id=str(AGENT_ID),
        email_service_id=str(ESVC_ID),
    )

    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with (
        patch("admin_api.api.email_permission_grants.audit_emit", side_effect=fake_audit_emit),
        patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant),
    ):
        response = await create_email_permission_grant(
            tenant_id=TENANT_A,
            body=body,
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 201
    content = response.body.decode()
    assert str(AGENT_ID) in content
    assert str(ESVC_ID) in content

    # Verify INSERT was executed
    insert_sqls = [sql for sql, _ in session.executed_sql if "INSERT INTO email_permission_grants" in sql]
    assert len(insert_sqls) == 1, f"Expected 1 INSERT, got {insert_sqls}"

    # Verify audit event was emitted
    assert len(audit_calls) == 1
    assert audit_calls[0]["event_type"] == "email_permission_grant.created"
    assert str(AGENT_ID) in str(audit_calls[0]["payload"])
    assert str(ESVC_ID) in str(audit_calls[0]["payload"])


# ---------------------------------------------------------------------------
# T-02: Duplicate grant → 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_grant_duplicate_returns_409() -> None:
    """
    T-02: A second POST with the same (agent_id, email_service_id) raises a unique constraint
    violation — the endpoint should return 409 Conflict.
    """
    agent_row = _FakeRow(id=str(AGENT_ID))
    esvc_row = _FakeRow(id=str(ESVC_ID))

    class UniqueViolationSession(_FakeSession):
        _first_execute = True

        async def execute(self, stmt: Any, params: Any = None) -> Any:
            sql = str(stmt) if not hasattr(stmt, "text") else stmt.text
            if "INSERT INTO email_permission_grants" in sql:
                raise Exception("duplicate key value violates unique constraint uq_email_permission_grants")
            return await super().execute(stmt, params)

    session = UniqueViolationSession(
        query_results={
            "SELECT id FROM agents": _FakeResult(agent_row),
            "SELECT id FROM email_services": _FakeResult(esvc_row),
        }
    )

    body = EmailPermissionGrantCreate(agent_id=str(AGENT_ID), email_service_id=str(ESVC_ID))

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant):
        response = await create_email_permission_grant(
            tenant_id=TENANT_A,
            body=body,
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 409
    assert b"already_exists" in response.body


# ---------------------------------------------------------------------------
# T-03: Nonexistent agent → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_grant_nonexistent_agent_returns_422() -> None:
    """
    T-03: When the agent does not exist in the tenant, POST returns 422.
    """
    # Agent lookup returns None; email_service not queried
    session = _make_session(
        **{
            "SELECT id FROM agents": _FakeResult(None),
        }
    )

    body = EmailPermissionGrantCreate(agent_id=str(AGENT_ID), email_service_id=str(ESVC_ID))

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant):
        response = await create_email_permission_grant(
            tenant_id=TENANT_A,
            body=body,
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 422
    assert b"Agent not found" in response.body


# ---------------------------------------------------------------------------
# T-04: Nonexistent email_service → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_grant_nonexistent_email_service_returns_422() -> None:
    """
    T-04: When the email service does not exist in the tenant, POST returns 422.
    """
    agent_row = _FakeRow(id=str(AGENT_ID))
    session = _make_session(
        **{
            "SELECT id FROM agents": _FakeResult(agent_row),
            "SELECT id FROM email_services": _FakeResult(None),
        }
    )

    body = EmailPermissionGrantCreate(agent_id=str(AGENT_ID), email_service_id=str(ESVC_ID))

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant):
        response = await create_email_permission_grant(
            tenant_id=TENANT_A,
            body=body,
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 422
    assert b"Email service not found" in response.body


# ---------------------------------------------------------------------------
# T-05: Cross-tenant rejection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_grant_cross_tenant_rejected() -> None:
    """
    T-05: Agent and email_service belong to different tenants. RLS + explicit check
    ensures the email_service from TENANT_B is not found when context is TENANT_A.
    """
    agent_row = _FakeRow(id=str(AGENT_ID))
    # email_service lookup for TENANT_A returns None (it's in TENANT_B)
    session = _make_session(
        **{
            "SELECT id FROM agents": _FakeResult(agent_row),
            "SELECT id FROM email_services": _FakeResult(None),
        }
    )

    body = EmailPermissionGrantCreate(agent_id=str(AGENT_ID), email_service_id=str(ESVC_ID))

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant):
        response = await create_email_permission_grant(
            tenant_id=TENANT_A,  # context is TENANT_A; email_service is in TENANT_B
            body=body,
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 422
    assert b"Email service not found" in response.body


# ---------------------------------------------------------------------------
# T-06: List grants scoped to tenant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_grants_scoped_to_tenant() -> None:
    """
    T-06: GET /v1/tenants/{tid}/email-permission-grants returns only grants for this tenant.
    RLS prevents cross-tenant leak.
    """
    now = datetime.now(timezone.utc)
    row = _FakeRow(
        id=GRANT_ID,
        tenant_id=TENANT_A,
        agent_id=AGENT_ID,
        email_service_id=ESVC_ID,
        created_at=now,
        updated_at=now,
    )
    session = _make_session(
        **{
            "SELECT id, tenant_id, agent_id, email_service_id, created_at, updated_at": _FakeResult(
                None, rows=[row]
            ),
        }
    )

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant):
        response = await list_email_permission_grants(
            tenant_id=TENANT_A,
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 200
    import json as _json
    body = _json.loads(response.body)
    assert "grants" in body
    assert len(body["grants"]) == 1
    assert body["grants"][0]["agent_id"] == str(AGENT_ID)
    assert body["grants"][0]["email_service_id"] == str(ESVC_ID)


# ---------------------------------------------------------------------------
# T-07: Delete grant — 204 + audit emitted
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_grant() -> None:
    """
    T-07: DELETE /v1/tenants/{tid}/email-permission-grants/{gid} returns 204
    and emits email_permission_grant.revoked audit event.
    """
    row = _FakeRow(id=GRANT_ID, agent_id=AGENT_ID, email_service_id=ESVC_ID)
    session = _make_session(
        **{
            "SELECT id, agent_id, email_service_id": _FakeResult(row),
        }
    )

    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with (
        patch("admin_api.api.email_permission_grants.audit_emit", side_effect=fake_audit_emit),
        patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant),
    ):
        response = await delete_email_permission_grant(
            tenant_id=TENANT_A,
            grant_id=str(GRANT_ID),
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 204

    # Verify DELETE SQL was executed
    delete_sqls = [sql for sql, _ in session.executed_sql if "DELETE FROM email_permission_grants" in sql]
    assert len(delete_sqls) == 1, f"Expected 1 DELETE, got {delete_sqls}"

    # Verify audit event
    assert len(audit_calls) == 1
    assert audit_calls[0]["event_type"] == "email_permission_grant.revoked"
    assert str(GRANT_ID) in str(audit_calls[0]["payload"])


# ---------------------------------------------------------------------------
# T-08: create_email_permission_grant emits notify_change('mintkey:agent', ...)
#       — invalidates mcp-server discovery cache. Mirrors permissions.py:633.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_email_permission_grant_emits_notify() -> None:
    """
    T-08: After a successful create, the handler MUST fire pg_notify on the
    'mintkey:agent' channel so mcp-server's discovery cache is invalidated
    (subscriber.py:122 keys off tenant_id).
    """
    agent_row = _FakeRow(id=str(AGENT_ID))
    esvc_row = _FakeRow(id=str(ESVC_ID))
    session = _make_session(
        **{
            "SELECT id FROM agents": _FakeResult(agent_row),
            "SELECT id FROM email_services": _FakeResult(esvc_row),
        }
    )

    body = EmailPermissionGrantCreate(
        agent_id=str(AGENT_ID),
        email_service_id=str(ESVC_ID),
    )

    notify_calls: list[tuple[Any, str, dict[str, Any]]] = []

    async def fake_notify_change(session: Any, channel: str, payload: dict[str, Any]) -> None:
        notify_calls.append((session, channel, payload))

    async def fake_audit_emit(**kwargs: Any) -> None:
        pass

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with (
        patch("admin_api.api.email_permission_grants.notify_change", side_effect=fake_notify_change),
        patch("admin_api.api.email_permission_grants.audit_emit", side_effect=fake_audit_emit),
        patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant),
    ):
        response = await create_email_permission_grant(
            tenant_id=TENANT_A,
            body=body,
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 201
    assert len(notify_calls) == 1, f"Expected exactly 1 notify_change call, got {len(notify_calls)}"

    _sess, channel, payload = notify_calls[0]
    assert channel == "mintkey:agent"
    assert payload["event"] == "email_permission_grant.created"
    assert payload["tenant_id"] == str(TENANT_A)
    assert payload["agent_id"] == str(AGENT_ID)
    assert payload["email_service_id"] == str(ESVC_ID)
    assert "grant_id" in payload
    # grant_id is server-generated; just confirm it's a non-empty string
    assert isinstance(payload["grant_id"], str) and len(payload["grant_id"]) > 0


# ---------------------------------------------------------------------------
# T-09: NFR-17 — NOTIFY payload contains identifiers only, no PII / no secrets.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_email_permission_grant_notify_payload_no_pii_no_secrets() -> None:
    """
    T-09 (NFR-17 belt-and-suspenders): The pg_notify payload MUST NOT contain
    any credential material (tokens, passwords, client_secret) or PII
    (email_address, username). Only opaque identifiers may flow over the
    cross-process notify channel.
    """
    agent_row = _FakeRow(id=str(AGENT_ID))
    esvc_row = _FakeRow(id=str(ESVC_ID))
    session = _make_session(
        **{
            "SELECT id FROM agents": _FakeResult(agent_row),
            "SELECT id FROM email_services": _FakeResult(esvc_row),
        }
    )

    body = EmailPermissionGrantCreate(
        agent_id=str(AGENT_ID),
        email_service_id=str(ESVC_ID),
    )

    captured_payloads: list[dict[str, Any]] = []

    async def fake_notify_change(session: Any, channel: str, payload: dict[str, Any]) -> None:
        captured_payloads.append(payload)

    async def fake_audit_emit(**kwargs: Any) -> None:
        pass

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with (
        patch("admin_api.api.email_permission_grants.notify_change", side_effect=fake_notify_change),
        patch("admin_api.api.email_permission_grants.audit_emit", side_effect=fake_audit_emit),
        patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant),
    ):
        await create_email_permission_grant(
            tenant_id=TENANT_A,
            body=body,
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert len(captured_payloads) == 1
    payload = captured_payloads[0]

    forbidden_keys = {
        "email_address",
        "username",
        "password",
        "refresh_token",
        "client_secret",
        "access_token",
    }
    leaked = forbidden_keys & set(payload.keys())
    assert not leaked, f"NFR-17 violation: NOTIFY payload leaked {leaked!r}"

    # Defence in depth: also walk values stringified, to catch a hypothetical
    # nested dict that someone might add later.
    blob = str(payload).lower()
    for term in ("password", "refresh_token", "client_secret", "access_token"):
        assert term not in blob, f"NFR-17 violation: payload contains '{term}': {payload!r}"


# ---------------------------------------------------------------------------
# T-10: delete_email_permission_grant emits notify_change('mintkey:agent', ...)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_email_permission_grant_emits_notify() -> None:
    """
    T-10: After a successful delete, the handler MUST fire pg_notify on
    'mintkey:agent' so mcp-server's discovery cache is invalidated.
    """
    row = _FakeRow(id=GRANT_ID, agent_id=AGENT_ID, email_service_id=ESVC_ID)
    session = _make_session(
        **{
            "SELECT id, agent_id, email_service_id": _FakeResult(row),
        }
    )

    notify_calls: list[tuple[Any, str, dict[str, Any]]] = []

    async def fake_notify_change(session: Any, channel: str, payload: dict[str, Any]) -> None:
        notify_calls.append((session, channel, payload))

    async def fake_audit_emit(**kwargs: Any) -> None:
        pass

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with (
        patch("admin_api.api.email_permission_grants.notify_change", side_effect=fake_notify_change),
        patch("admin_api.api.email_permission_grants.audit_emit", side_effect=fake_audit_emit),
        patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant),
    ):
        response = await delete_email_permission_grant(
            tenant_id=TENANT_A,
            grant_id=str(GRANT_ID),
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 204
    assert len(notify_calls) == 1, f"Expected exactly 1 notify_change call, got {len(notify_calls)}"

    _sess, channel, payload = notify_calls[0]
    assert channel == "mintkey:agent"
    assert payload["event"] == "email_permission_grant.revoked"
    assert payload["tenant_id"] == str(TENANT_A)
    assert payload["agent_id"] == str(AGENT_ID)
    assert payload["email_service_id"] == str(ESVC_ID)
    assert payload["grant_id"] == str(GRANT_ID)


# ---------------------------------------------------------------------------
# T-11: Delete is idempotent — NOTIFY still fires when row is missing.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_email_permission_grant_idempotent_notify_even_when_row_missing() -> None:
    """
    T-11: If the grant row doesn't exist (SELECT returns None), the audit
    event already fires (existing line 311 behaviour); the NOTIFY must too,
    for idempotency parity. The mcp-server's invalidation is keyed by
    tenant_id, so an extra invalidation on an idempotent revoke is safe.
    """
    # SELECT returns None — the row is gone (or never existed).
    session = _make_session()  # no query results → fetchone() returns None

    notify_calls: list[tuple[Any, str, dict[str, Any]]] = []

    async def fake_notify_change(session: Any, channel: str, payload: dict[str, Any]) -> None:
        notify_calls.append((session, channel, payload))

    async def fake_audit_emit(**kwargs: Any) -> None:
        pass

    async def fake_set_tenant(session: Any, tenant_id: Any) -> None:
        pass

    with (
        patch("admin_api.api.email_permission_grants.notify_change", side_effect=fake_notify_change),
        patch("admin_api.api.email_permission_grants.audit_emit", side_effect=fake_audit_emit),
        patch("admin_api.api.email_permission_grants.set_tenant_context", side_effect=fake_set_tenant),
    ):
        response = await delete_email_permission_grant(
            tenant_id=TENANT_A,
            grant_id=str(GRANT_ID),
            session=session,  # type: ignore[arg-type]
            _authz=None,
        )

    assert response.status_code == 204
    assert len(notify_calls) == 1, (
        f"NOTIFY must fire even when the row was already absent (got {len(notify_calls)} calls)"
    )

    _sess, channel, payload = notify_calls[0]
    assert channel == "mintkey:agent"
    assert payload["event"] == "email_permission_grant.revoked"
    assert payload["tenant_id"] == str(TENANT_A)
    assert payload["grant_id"] == str(GRANT_ID)
    # When the row was missing, the handler falls back to grant_id for agent_id_val
    # and "" for esvc_id_val — assert the keys are present, content is best-effort.
    assert "agent_id" in payload
    assert "email_service_id" in payload


# ---------------------------------------------------------------------------
# T-AUTHZ: cross-tenant 403 via require_tenant_session (Chunk C, AC-2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_email_permission_grant_cross_tenant_session_403() -> None:
    """
    T-AUTHZ: A session scoped to TENANT_A hitting TENANT_B's
    email-permission-grants/create endpoint → 403.

    Before fix: no require_tenant_session dep — any operator could POST to any tenant.
    After fix:  require_tenant_session raises HTTPException(403) before the handler body runs.

    Uses FastAPI TestClient so Depends() is actually resolved.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from unittest.mock import AsyncMock, patch as _patch
    from types import SimpleNamespace
    from uuid import UUID

    from admin_api.api.email_permission_grants import router as grants_router
    from admin_api.db.deps import get_db_session
    from admin_api.auth.sessions import require_tenant_session

    TENANT_A_ID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
    TENANT_B_ID = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")

    test_app = FastAPI()
    test_app.include_router(grants_router)

    # DB session override — should never be reached (403 fires first)
    async def _override_session():
        yield _make_session()

    test_app.dependency_overrides[get_db_session] = _override_session

    # Simulate session belonging to TENANT_A
    ctx = SimpleNamespace(operator_id=uuid.uuid4(), tenant_id=TENANT_A_ID)

    with _patch("admin_api.auth.sessions.validate_session", new_callable=AsyncMock, return_value=ctx), \
         _patch("admin_api.auth.sessions._is_operator_platform_admin", new_callable=AsyncMock, return_value=False):
        with TestClient(test_app, raise_server_exceptions=False) as client:
            # Cookie present (non-empty triggers the session check)
            resp = client.post(
                f"/v1/tenants/{TENANT_B_ID}/email-permission-grants",
                json={
                    "agent_id": str(uuid.uuid4()),
                    "email_service_id": str(uuid.uuid4()),
                },
                cookies={"mintkey_session": "tok-tenant-a"},
            )

    assert resp.status_code == 403, (
        f"Expected 403 cross-tenant, got {resp.status_code}: {resp.text}"
    )
