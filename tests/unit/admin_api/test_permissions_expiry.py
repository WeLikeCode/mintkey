"""
Unit tests: the operator API takes an expiry and records the grantor.

Requirement: grant-expiry › The operator API takes an expiry and records the
grantor

  - a grant with an expiry (C-c997909a)
  - invalid and conflicting requests (C-b2b19611)
  - the lists and the single grant show the new fields (C-52a42138)
  - the grantor filter and the unchanged bodies (C-c4e8685f)
  - revoke names what it revoked (C-31cf8071)

The fake session answers the route's tenant-context, agent and service
checks, the grant write path (advisory lock, select, insert, delete, budget)
and the grant reads. Every statement is recorded so a test can read the SQL
text and the values bound to it.

Sources:
  - `openspec/changes/grant-expiry/spec.md` — The operator API takes an expiry
    and records the grantor
  - `openspec/changes/grant-expiry/design.md` — D2, D6, D8, Interfaces
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from admin_api.utils.wire_ids import db_uuid_to_wire  # noqa: E402

TENANT_ID = "00000000-0000-0000-0000-000000000001"
AGENT_UUID = "11111111-1111-1111-1111-111111111111"
SERVICE_UUID = "22222222-2222-2222-2222-222222222222"
OPERATOR_UUID = "33333333-3333-3333-3333-333333333333"
GRANTOR_AGENT_UUID = "44444444-4444-4444-4444-444444444444"
PERM1_UUID = "55555555-5555-5555-5555-555555555555"
PERM2_UUID = "66666666-6666-6666-6666-666666666666"
PERM3_UUID = "77777777-7777-7777-7777-777777777777"
MISSING_PERM_UUID = "88888888-8888-8888-8888-888888888888"

AGENT_WIRE = db_uuid_to_wire(AGENT_UUID, "agent")
SERVICE_WIRE = db_uuid_to_wire(SERVICE_UUID, "svc")
GRANTOR_AGENT_WIRE = db_uuid_to_wire(GRANTOR_AGENT_UUID, "agent")

AGENT_LIST_URL = f"/v1/tenants/{TENANT_ID}/agents/{AGENT_WIRE}/permissions"
TENANT_LIST_URL = f"/v1/tenants/{TENANT_ID}/permissions"
GRANT_URL = AGENT_LIST_URL

CONSTRAINTS = {"rate_limit": {"requests_per_second": 10, "burst": 20}}


# ---------------------------------------------------------------------------
# Fake session — enough of the SQL surface for the grant routes
# ---------------------------------------------------------------------------


class _Result:
    def __init__(self, rows: list[Any] | None = None) -> None:
        self._rows = list(rows or [])

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Any]:
        return list(self._rows)

    def one_or_none(self) -> Any:
        return self.fetchone()


def _statement_sql(statement: Any) -> str:
    """The statement text, with bound values inlined when SQLAlchemy can."""
    if hasattr(statement, "compile"):
        try:
            return str(statement.compile(compile_kwargs={"literal_binds": True}))
        except Exception:  # pragma: no cover - a type that cannot be literal
            return str(statement)
    return str(statement)


def _grant_row(
    *,
    perm_id: str,
    expires_at: datetime | None = None,
    grantor_type: str = "operator",
    grantor_id: str | None = None,
    constraints: Any = None,
    action: str = "read",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=perm_id,
        tenant_id=TENANT_ID,
        agent_id=AGENT_UUID,
        service_id=SERVICE_UUID,
        action=action,
        constraints={} if constraints is None else constraints,
        created_at=datetime(2026, 11, 20, 10, 0, tzinfo=timezone.utc),
        created_by=OPERATOR_UUID,
        expires_at=expires_at,
        grantor_type=grantor_type,
        grantor_id=grantor_id,
        service_name="Demo service",
        service_slug="demo-service",
        agent_name="Demo agent",
    )


class _GrantSession:
    """An in-memory AsyncSession over a list of grant rows."""

    def __init__(
        self,
        rows: list[Any] | None = None,
        *,
        agent_exists: bool = True,
        service_exists: bool = True,
    ) -> None:
        self.rows: list[Any] = list(rows or [])
        self.agent_exists = agent_exists
        self.service_exists = service_exists
        self.statements: list[tuple[str, dict[str, Any], Any]] = []

    async def execute(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> _Result:
        raw_sql = str(statement)
        sql = _statement_sql(statement)
        bound = dict(params or {})
        self.statements.append((sql, bound, statement))
        lowered = raw_sql.lower()

        if "set_config" in lowered or "pg_notify" in lowered:
            return _Result()

        if "pg_advisory_xact_lock" in lowered:
            return _Result()

        if "permission_grants" not in lowered:
            if "from agents" in lowered:
                if self.agent_exists:
                    return _Result([SimpleNamespace(id=AGENT_UUID)])
                return _Result()
            if "from services" in lowered:
                if self.service_exists:
                    return _Result([SimpleNamespace(id=SERVICE_UUID)])
                return _Result()
            return _Result()

        if "delete from permission_grants" in lowered:
            self.rows = [
                row for row in self.rows if not self._matches(row, bound)
            ]
            return _Result()

        if "insert into permission_grants" in lowered:
            self.rows.append(self._row_from_params(bound))
            return _Result()

        return _Result(self.rows)

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        return None

    def _grant_statements(self, fragment: str) -> list[tuple[str, dict[str, Any], Any]]:
        needle = fragment.lower()
        return [item for item in self.statements if needle in item[0].lower()]

    def _row_from_params(self, params: dict[str, Any]) -> SimpleNamespace:
        return SimpleNamespace(
            id=str(params.get("id")),
            tenant_id=str(params.get("tenant_id")),
            agent_id=str(params.get("agent_id")),
            service_id=str(params.get("service_id")),
            action=str(params.get("action")),
            constraints=params.get("constraints"),
            created_at=params.get("created_at"),
            created_by=params.get("created_by"),
            expires_at=params.get("expires_at"),
            grantor_type=params.get("grantor_type"),
            grantor_id=params.get("grantor_id"),
            service_name=None,
            service_slug=None,
            agent_name=None,
        )

    @staticmethod
    def _matches(row: Any, params: dict[str, Any]) -> bool:
        aliases = {
            "tenant_id": "tenant_id",
            "tid": "tenant_id",
            "agent_id": "agent_id",
            "aid": "agent_id",
            "service_id": "service_id",
            "sid": "service_id",
            "action": "action",
            "pid": "id",
            "id": "id",
        }
        for key, attr in aliases.items():
            if key not in params:
                continue
            if str(getattr(row, attr, None)) != str(params[key]):
                return False
        return True


def _combined_statement_text(
    sql: str, params: dict[str, Any]
) -> str:
    """SQL text plus every bound value, lowercased and without UUID dashes."""
    values = " ".join(str(value) for value in params.values())
    combined = f"{sql} {values}".lower().replace("-", "")
    return combined


def _build_app(
    session: _GrantSession,
    *,
    operator_id: str | None = OPERATOR_UUID,
):
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError

    from admin_api.api.permissions import (
        router as permissions_router,
        tenant_permissions_router,
        validation_error_handler,
    )
    from admin_api.auth.sessions import get_session_context, require_tenant_session
    from admin_api.db.deps import get_db_session

    app = FastAPI()
    app.include_router(permissions_router)
    app.include_router(tenant_permissions_router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    async def _db_session():
        yield session

    app.dependency_overrides[get_db_session] = _db_session
    app.dependency_overrides[require_tenant_session] = lambda: None
    ctx = SimpleNamespace(
        operator_id=operator_id,
        tenant_id=TENANT_ID,
    )
    app.dependency_overrides[get_session_context] = lambda: ctx
    return app


async def _client(app: Any) -> AsyncClient:
    return AsyncClient(
        transport=ASGITransport(app=app, raise_app_exceptions=False),
        base_url="http://test",
    )


@pytest.fixture()
def mock_audit():
    with patch("admin_api.api.permissions.audit_emit", new=AsyncMock()) as emit:
        yield emit


@pytest.fixture()
def mock_notify():
    with patch("admin_api.api.permissions.notify_change", new=AsyncMock()) as notify:
        yield notify


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


# ---------------------------------------------------------------------------
# C-c997909a — a grant with an expiry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-c997909a")
async def test_C_c997909a_a_grant_with_an_expiry(mock_audit, mock_notify) -> None:
    session = _GrantSession()
    app = _build_app(session)
    expires_at = _now() + timedelta(days=1)
    body = {
        "service_id": SERVICE_WIRE,
        "action": "read",
        "expires_at": expires_at.isoformat(),
        "granted_by": "agent_other",
    }

    async with await _client(app) as client:
        resp = await client.post(GRANT_URL, json=body)

    assert resp.status_code == 201, resp.text
    answer = resp.json()
    assert answer.get("expires_at") == expires_at.isoformat(), answer
    assert answer.get("expired") is False, answer
    assert answer.get("grantor_type") == "operator", answer
    assert answer.get("grantor_id") == OPERATOR_UUID, answer

    inserts = session._grant_statements("insert into permission_grants")
    assert len(inserts) == 1, "the grant ran no INSERT"
    insert_params = inserts[0][1]
    assert insert_params.get("created_by") == OPERATOR_UUID, insert_params
    assert insert_params.get("created_by") != "agent_other", insert_params
    assert insert_params.get("grantor_type") == "operator", insert_params
    assert insert_params.get("grantor_id") == OPERATOR_UUID, insert_params
    assert insert_params.get("expires_at") == expires_at, insert_params

    mock_audit.assert_called_once()
    payload = mock_audit.call_args.kwargs.get("payload", {})
    assert payload.get("expires_at") == expires_at.isoformat(), payload
    assert payload.get("grantor_type") == "operator", payload
    assert payload.get("grantor_id") == OPERATOR_UUID, payload


# ---------------------------------------------------------------------------
# C-b2b19611 — invalid and conflicting requests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-b2b19611")
async def test_C_b2b19611_invalid_and_conflicting_requests(
    mock_audit, mock_notify
) -> None:
    past = _now() - timedelta(hours=1)
    future = _now() + timedelta(days=3)
    live = _now() + timedelta(days=2)

    past_session = _GrantSession()
    past_app = _build_app(past_session)
    past_body = {
        "service_id": SERVICE_WIRE,
        "action": "read",
        "expires_at": past.isoformat(),
    }
    async with await _client(past_app) as client:
        past_resp = await client.post(GRANT_URL, json=past_body)

    assert past_resp.status_code == 422, past_resp.text
    assert past_resp.json() == {
        "mintkey:code": "invalid_expires_at",
        "title": "Invalid expires_at",
        "reason": "expires_at_in_past",
    }, past_resp.text
    assert not past_session._grant_statements("insert into permission_grants"), (
        "a past expiry reached the INSERT"
    )

    naive_session = _GrantSession()
    naive_app = _build_app(naive_session)
    naive_body = {
        "service_id": SERVICE_WIRE,
        "action": "read",
        "expires_at": "2030-01-01T00:00:00",
    }
    async with await _client(naive_app) as client:
        naive_resp = await client.post(GRANT_URL, json=naive_body)

    assert naive_resp.status_code == 422, naive_resp.text
    assert naive_resp.json() == {
        "mintkey:code": "invalid_expires_at",
        "title": "Invalid expires_at",
        "reason": "expires_at_timezone_required",
    }, naive_resp.text
    assert not naive_session._grant_statements("insert into permission_grants"), (
        "a naive expiry reached the INSERT"
    )

    existing = _grant_row(
        perm_id=PERM1_UUID,
        expires_at=live,
        grantor_type="operator",
        grantor_id=OPERATOR_UUID,
        constraints=json.dumps(CONSTRAINTS),
    )
    conflict_session = _GrantSession(rows=[existing])
    conflict_app = _build_app(conflict_session)
    conflict_body = {
        "service_id": SERVICE_WIRE,
        "action": "read",
        "constraints": CONSTRAINTS,
        "expires_at": future.isoformat(),
    }
    async with await _client(conflict_app) as client:
        conflict_resp = await client.post(GRANT_URL, json=conflict_body)

    assert conflict_resp.status_code == 409, conflict_resp.text
    assert conflict_resp.json() == {
        "mintkey:code": "permission_constraints_conflict",
        "title": "A permission grant with different constraints already exists",
    }, conflict_resp.text
    assert not conflict_session._grant_statements("insert into permission_grants"), (
        "a conflicting grant reached the INSERT"
    )


# ---------------------------------------------------------------------------
# C-52a42138 — the lists and the single grant show the new fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-52a42138")
async def test_C_52a42138_the_lists_and_the_single_grant_show_the_new_fields(
    mock_audit, mock_notify
) -> None:
    past = _now() - timedelta(hours=2)
    future = _now() + timedelta(days=1)
    cases = [
        (
            _grant_row(
                perm_id=PERM1_UUID,
                expires_at=past,
                grantor_type="operator",
                grantor_id=OPERATOR_UUID,
            ),
            {
                "expires_at": past.isoformat(),
                "expired": True,
                "grantor_type": "operator",
                "grantor_id": OPERATOR_UUID,
            },
        ),
        (
            _grant_row(
                perm_id=PERM2_UUID,
                expires_at=None,
                grantor_type="operator",
                grantor_id=None,
            ),
            {
                "expires_at": None,
                "expired": False,
                "grantor_type": "operator",
                "grantor_id": None,
            },
        ),
        (
            _grant_row(
                perm_id=PERM3_UUID,
                expires_at=future,
                grantor_type="agent",
                grantor_id=GRANTOR_AGENT_UUID,
            ),
            {
                "expires_at": future.isoformat(),
                "expired": False,
                "grantor_type": "agent",
                "grantor_id": GRANTOR_AGENT_WIRE,
            },
        ),
    ]

    for row, expected in cases:
        session = _GrantSession(rows=[row])
        app = _build_app(session)

        async with await _client(app) as client:
            agent_resp = await client.get(AGENT_LIST_URL)
            tenant_resp = await client.get(TENANT_LIST_URL)
            single_resp = await client.get(
                f"{TENANT_LIST_URL}/{db_uuid_to_wire(row.id, 'perm')}"
            )

        assert agent_resp.status_code == 200, agent_resp.text
        assert tenant_resp.status_code == 200, tenant_resp.text
        assert single_resp.status_code == 200, single_resp.text

        objects = [
            agent_resp.json()["grants"][0],
            tenant_resp.json()["permissions"][0],
            single_resp.json(),
        ]
        for obj in objects:
            for key, value in expected.items():
                assert obj.get(key) == value, f"{key}: {obj}"

        selects = [
            item
            for item in session.statements
            if "permission_grants" in item[0].lower()
            and item[0].lstrip().lower().startswith("select")
        ]
        assert len(selects) >= 3, "the three reads did not run a grant SELECT each"
        for sql, _params, _statement in selects:
            lowered = sql.lower()
            assert "expires_at" in lowered, sql
            assert "grantor_type" in lowered, sql
            assert "grantor_id" in lowered, sql


# ---------------------------------------------------------------------------
# C-c4e8685f — the grantor filter and the unchanged bodies
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-c4e8685f")
async def test_C_c4e8685f_grantor_filter_and_unchanged_bodies(
    mock_audit, mock_notify
) -> None:
    stored = _grant_row(
        perm_id=PERM3_UUID,
        expires_at=_now() + timedelta(days=1),
        grantor_type="agent",
        grantor_id=GRANTOR_AGENT_UUID,
        constraints={"budget": {"ceiling": 10, "period": "daily"}},
    )
    session = _GrantSession(rows=[stored])
    app = _build_app(session)

    async with await _client(app) as client:
        filtered = await client.get(
            TENANT_LIST_URL, params={"grantor_agent_id": GRANTOR_AGENT_WIRE}
        )
        invalid = await client.get(
            TENANT_LIST_URL, params={"grantor_agent_id": "x"}
        )

    assert filtered.status_code == 200, filtered.text
    filter_selects = [
        item
        for item in session.statements
        if "permission_grants" in item[0].lower()
        and item[0].lstrip().lower().startswith("select")
    ]
    assert filter_selects, "the tenant list ran no grant SELECT"
    combined = " ".join(
        _combined_statement_text(sql, params)
        for sql, params, _statement in filter_selects
    )
    assert "grantor_type = 'agent'" in combined, combined
    assert GRANTOR_AGENT_UUID.replace("-", "") in combined, combined

    assert invalid.status_code == 422, invalid.text
    assert invalid.json().get("mintkey:code") == "invalid_id", invalid.text

    async with await _client(app) as client:
        patch_resp = await client.patch(
            f"{GRANT_URL}/{db_uuid_to_wire(stored.id, 'perm')}",
            json={"constraints": {}},
        )
        reset_resp = await client.post(
            f"{GRANT_URL}/{db_uuid_to_wire(stored.id, 'perm')}/budget/reset"
        )

    assert patch_resp.status_code == 200, patch_resp.text
    assert set(patch_resp.json()) == {
        "id",
        "tenant_id",
        "constraints",
        "updated_at",
    }, patch_resp.text
    for field in ("expires_at", "expired", "grantor_type", "grantor_id"):
        assert field not in patch_resp.json(), patch_resp.text

    assert reset_resp.status_code == 200, reset_resp.text
    assert set(reset_resp.json()) == {"permission_id", "used", "reset_at"}, (
        reset_resp.text
    )
    for field in ("expires_at", "expired", "grantor_type", "grantor_id"):
        assert field not in reset_resp.json(), reset_resp.text


# ---------------------------------------------------------------------------
# C-31cf8071 — revoke names what it revoked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-31cf8071")
async def test_C_31cf8071_revoke_names_what_it_revoked(
    mock_audit, mock_notify
) -> None:
    stored = _grant_row(
        perm_id=PERM3_UUID,
        expires_at=None,
        grantor_type="agent",
        grantor_id=GRANTOR_AGENT_UUID,
        constraints={},
    )
    session = _GrantSession(rows=[stored])
    app = _build_app(session)

    async with await _client(app) as client:
        first = await client.delete(f"{GRANT_URL}/{db_uuid_to_wire(stored.id, 'perm')}")

    assert first.status_code == 204, first.text
    assert len(session._grant_statements("delete from permission_grants")) == 1

    mock_audit.assert_called_once()
    audit_kwargs = mock_audit.call_args.kwargs
    assert audit_kwargs.get("event_type") == "agent.permission.revoked", audit_kwargs
    payload = audit_kwargs.get("payload", {})
    assert payload.get("service_id") == db_uuid_to_wire(SERVICE_UUID, "svc"), payload
    assert payload.get("action") == "read", payload
    assert payload.get("grantor_type") == "agent", payload
    assert payload.get("grantor_id") == GRANTOR_AGENT_WIRE, payload

    mock_notify.assert_called_once()
    notify_call = mock_notify.call_args
    notify_payload = notify_call.kwargs.get("payload")
    if notify_payload is None:
        notify_args = notify_call.args
        assert "mintkey:agent" in notify_args, notify_args
        notify_payload = notify_args[-1]
    else:
        assert (
            notify_call.kwargs.get("channel") == "mintkey:agent"
            or "mintkey:agent" in notify_call.args
        ), notify_call
    assert notify_payload.get("service_id") == db_uuid_to_wire(
        SERVICE_UUID, "svc"
    ), notify_payload
    revoked_at = notify_payload.get("revoked_at")
    assert isinstance(revoked_at, str), notify_payload
    assert revoked_at.endswith("+00:00"), notify_payload

    mock_audit.reset_mock()
    mock_notify.reset_mock()

    async with await _client(app) as client:
        second = await client.delete(
            f"{GRANT_URL}/{db_uuid_to_wire(MISSING_PERM_UUID, 'perm')}"
        )

    assert second.status_code == 204, second.text
    assert not mock_audit.called, "a revoke with no row emitted an audit event"
    assert not mock_notify.called, "a revoke with no row sent a NOTIFY"
