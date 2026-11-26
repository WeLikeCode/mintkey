"""
Unit tests: the one write path that creates and removes permission grants.

Requirement: grant-expiry › One write path creates and removes grants

  - an operator and an agent write grants (`write_grant`)
  - an identical grant is returned, another is refused, an expired one is
    replaced (`write_grant`, `GrantConflict`)
  - two concurrent writes of one grant (`write_grant` and the advisory lock)
  - a rule violation writes nothing (`write_grant`)
  - delete returns the record or nothing (`delete_grant`)
  - the payload builders (`grant_granted_audit_payload`,
    `grant_revoked_audit_payload`, `grant_wire_fields`)
  - the NOTIFY payload pins the revoked_at format
    (`grant_revoked_notify_payload`)

The fake session answers any SELECT that reads ``FROM permission_grants`` with
the stored row or None, records every statement in order, and (in the
concurrency test) shares one table with another session while holding an
``asyncio.Lock`` per advisory-lock key until ``commit()``.

Sources:
  - `openspec/changes/grant-expiry/spec.md` — One write path creates and
    removes grants
  - `openspec/changes/grant-expiry/design.md` — D6, D7, D7b, D8
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock
from uuid import UUID

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
if str(ADMIN_API_SRC) not in sys.path:
    sys.path.insert(0, str(ADMIN_API_SRC))

from admin_api.services.grant_expiry import GrantExpiryError  # noqa: E402
from admin_api.services.grants import (  # noqa: E402
    GrantConflict,
    Grantor,
    GrantRecord,
    delete_grant,
    grant_granted_audit_payload,
    grant_revoked_audit_payload,
    grant_revoked_notify_payload,
    grant_wire_fields,
    write_grant,
)
from admin_api.utils.wire_ids import db_uuid_to_wire  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_UUID = "11111111-1111-1111-1111-111111111111"
SERVICE_UUID = "22222222-2222-2222-2222-222222222222"
OPERATOR_UUID = "33333333-3333-3333-3333-333333333333"
GRANTOR_AGENT_UUID = "44444444-4444-4444-4444-444444444444"
PERM_UUID = "55555555-5555-5555-5555-555555555555"

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)
CAP_ENV = "MINTKEY_AGENT_GRANT_MAX_TTL"

CONSTRAINTS = {"rate_limit": {"requests_per_second": 10, "burst": 20}}
BUDGET_CONSTRAINTS = {"budget": {"ceiling": 100, "period": "daily"}}

_MISSING = object()


def _field(record: object, name: str) -> Any:
    """Read one record field, failing by assertion when the record lacks it."""
    value = getattr(record, name, _MISSING)
    assert value is not _MISSING, f"the grant record has no {name!r} field"
    return value


@dataclass
class _Row:
    """One stored permission_grants row, as the fake session returns it."""

    id: str = PERM_UUID
    tenant_id: str = str(TENANT_ID)
    agent_id: str = AGENT_UUID
    service_id: str = SERVICE_UUID
    action: str = "read"
    constraints: Any = None
    expires_at: Any = None
    grantor_type: Any = "operator"
    grantor_id: Any = None
    created_at: Any = NOW


class _Result:
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row

    def fetchall(self) -> list[Any]:
        return [] if self._row is None else [self._row]


class _Table:
    """One in-memory grant table shared by one or more fake sessions."""

    def __init__(self, rows: list[Any] | None = None) -> None:
        self.rows: list[Any] = list(rows or [])
        self._locks: dict[str, asyncio.Lock] = {}

    def lock_for(self, key: str) -> asyncio.Lock:
        lock = self._locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[key] = lock
        return lock


def _pick(params: dict[str, Any], *names: str) -> Any:
    for name in names:
        if name in params:
            return params[name]
    return None


def _row_from_params(params: dict[str, Any]) -> _Row:
    return _Row(
        id=str(_pick(params, "id")),
        tenant_id=str(_pick(params, "tenant_id", "tid")),
        agent_id=str(_pick(params, "agent_id", "aid")),
        service_id=str(_pick(params, "service_id", "sid")),
        action=str(_pick(params, "action")),
        constraints=_pick(params, "constraints"),
        expires_at=_pick(params, "expires_at"),
        grantor_type=_pick(params, "grantor_type") or "operator",
        grantor_id=_pick(params, "grantor_id"),
        created_at=_pick(params, "created_at"),
    )


class _Session:
    """A fake AsyncSession over one :class:`_Table`."""

    def __init__(self, table: _Table) -> None:
        self.table = table
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self._held: list[asyncio.Lock] = []

    async def execute(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> _Result:
        sql = str(statement)
        bound = dict(params or {})
        self.statements.append((sql, bound))
        lowered = sql.lower()

        if "pg_advisory_xact_lock" in lowered:
            lock = self.table.lock_for(str(bound.get("key")))
            await lock.acquire()
            self._held.append(lock)
            return _Result()

        if lowered.lstrip().startswith("select") and "from permission_grants" in lowered:
            return _Result(self._find(bound))

        if "delete from permission_grants" in lowered:
            self.table.rows = [
                row for row in self.table.rows if not self._matches(row, bound)
            ]
            return _Result()

        if "insert into permission_grants" in lowered:
            self.table.rows.append(_row_from_params(bound))
            return _Result()

        return _Result()

    async def flush(self) -> None:
        return None

    async def commit(self) -> None:
        for lock in self._held:
            lock.release()
        self._held.clear()

    def _find(self, params: dict[str, Any]) -> Any:
        for row in self.table.rows:
            if self._matches(row, params):
                return row
        return None

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
            "grant_id": "id",
            "id": "id",
        }
        for key, attr in aliases.items():
            if key not in params:
                continue
            if str(getattr(row, attr, None)) != str(params[key]):
                return False
        return True


def _matching(session: _Session, fragment: str) -> list[tuple[str, dict[str, Any]]]:
    needle = fragment.lower()
    return [
        (sql, params)
        for sql, params in session.statements
        if needle in sql.lower()
    ]


def _insert_params(session: _Session) -> dict[str, Any] | None:
    matches = _matching(session, "insert into permission_grants")
    assert len(matches) <= 1, f"expected at most one grant INSERT, saw {len(matches)}"
    return matches[0][1] if matches else None


async def _operator_write(
    session: _Session,
    *,
    expires_at: datetime | None,
    constraints: dict[str, Any] = CONSTRAINTS,
) -> Any:
    return await write_grant(
        session,
        tenant_id=TENANT_ID,
        agent_id=AGENT_UUID,
        service_id=SERVICE_UUID,
        action="read",
        constraints=constraints,
        expires_at=expires_at,
        grantor=Grantor(type="operator", id=OPERATOR_UUID),
        now=NOW,
    )


async def _locked_operator_write(
    session: _Session, *, expires_at: datetime | None
) -> Any:
    try:
        return await _operator_write(session, expires_at=expires_at)
    finally:
        await session.commit()


@pytest.mark.asyncio
@pytest.mark.l4("C-22b26d27")
async def test_C_22b26d27_operator_and_agent_write_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv(CAP_ENV, raising=False)

    operator_session = _Session(_Table())
    operator_record = await write_grant(
        operator_session,
        tenant_id=TENANT_ID,
        agent_id=AGENT_UUID,
        service_id=SERVICE_UUID,
        action="read",
        constraints=CONSTRAINTS,
        expires_at=None,
        grantor=Grantor(type="operator", id=OPERATOR_UUID),
        now=NOW,
    )

    operator_insert = _insert_params(operator_session)
    assert operator_insert is not None, "the operator grant ran no INSERT"
    assert _field(operator_record, "created") is True
    assert operator_insert.get("grantor_type") == "operator"
    assert operator_insert.get("grantor_id") == OPERATOR_UUID
    assert operator_insert.get("expires_at") is None
    assert operator_insert.get("created_by") == OPERATOR_UUID
    assert not _matching(operator_session, "budget_counters")

    expires_at = NOW + timedelta(days=1)
    agent_session = _Session(_Table())
    agent_record = await write_grant(
        agent_session,
        tenant_id=TENANT_ID,
        agent_id=AGENT_UUID,
        service_id=SERVICE_UUID,
        action="read",
        constraints=BUDGET_CONSTRAINTS,
        expires_at=expires_at,
        grantor=Grantor(type="agent", id=GRANTOR_AGENT_UUID),
        now=NOW,
    )

    agent_insert = _insert_params(agent_session)
    assert agent_insert is not None, "the agent grant ran no INSERT"
    assert _field(agent_record, "created") is True
    assert agent_insert.get("grantor_type") == "agent"
    assert agent_insert.get("grantor_id") == GRANTOR_AGENT_UUID
    assert agent_insert.get("expires_at") == expires_at
    assert agent_insert.get("created_by") == GRANTOR_AGENT_UUID
    budget_statements = _matching(agent_session, "budget_counters")
    assert budget_statements, "the budget grant ran no budget_counters statement"


@pytest.mark.asyncio
@pytest.mark.l4("C-a6b59772")
async def test_C_a6b59772_identical_returned_other_refused_expired_replaced() -> None:
    live = NOW + timedelta(days=1)

    identical = _Session(
        _Table(
            [
                _Row(
                    constraints=json.dumps(CONSTRAINTS),
                    expires_at=live,
                )
            ]
        )
    )
    record = await _operator_write(identical, expires_at=live)
    assert _field(record, "id") == PERM_UUID
    assert _field(record, "created") is False
    assert not _matching(identical, "insert into permission_grants")

    other_expiry = _Session(
        _Table(
            [
                _Row(
                    constraints=json.dumps(CONSTRAINTS),
                    expires_at=live,
                )
            ]
        )
    )
    with pytest.raises(GrantConflict):
        await _operator_write(other_expiry, expires_at=NOW + timedelta(days=2))
    assert not _matching(other_expiry, "insert into permission_grants")

    other_constraints = _Session(
        _Table(
            [
                _Row(
                    constraints=json.dumps(
                        {"rate_limit": {"requests_per_second": 1, "burst": 1}}
                    ),
                    expires_at=None,
                )
            ]
        )
    )
    with pytest.raises(GrantConflict):
        await _operator_write(other_constraints, expires_at=None)
    assert not _matching(other_constraints, "insert into permission_grants")

    expired = _Session(
        _Table(
            [
                _Row(
                    constraints=json.dumps(CONSTRAINTS),
                    expires_at=NOW - timedelta(seconds=10),
                )
            ]
        )
    )
    future = NOW + timedelta(days=1)
    replaced = await _operator_write(expired, expires_at=future)
    assert _field(replaced, "created") is True
    assert _field(replaced, "expires_at") == future
    assert len(_matching(expired, "delete from permission_grants")) == 1
    assert len(_matching(expired, "insert into permission_grants")) == 1
    assert len(expired.table.rows) == 1
    assert str(expired.table.rows[0].id) != PERM_UUID

    mock_row = MagicMock()
    mock_row.id = PERM_UUID
    mock_row.tenant_id = str(TENANT_ID)
    mock_row.agent_id = AGENT_UUID
    mock_row.service_id = SERVICE_UUID
    mock_row.action = "read"
    mock_row.constraints = json.dumps(CONSTRAINTS)
    magic = _Session(_Table([mock_row]))
    magic_record = await _operator_write(magic, expires_at=None)
    assert _field(magic_record, "created") is False
    assert _field(magic_record, "grantor_type") == "operator"
    assert _field(magic_record, "grantor_id") is None
    assert _field(magic_record, "expires_at") is None


@pytest.mark.asyncio
@pytest.mark.l4("C-1bd65fd0")
async def test_C_1bd65fd0_two_concurrent_writes_of_one_grant() -> None:
    expected_key = f"grant:{TENANT_ID}:{AGENT_UUID}:{SERVICE_UUID}:read"

    table = _Table()
    first = _Session(table)
    second = _Session(table)
    results = await asyncio.gather(
        _locked_operator_write(first, expires_at=None),
        _locked_operator_write(second, expires_at=None),
        return_exceptions=True,
    )

    assert len(table.rows) == 1, "the two writers stored more than one grant row"
    assert not any(isinstance(item, BaseException) for item in results)
    created = sorted(_field(item, "created") for item in results)
    assert created == [False, True]

    for session in (first, second):
        assert session.statements, "the session ran no statement"
        sql, params = session.statements[0]
        assert "pg_advisory_xact_lock" in sql
        assert params.get("key") == expected_key

    conflicting_table = _Table()
    third = _Session(conflicting_table)
    fourth = _Session(conflicting_table)
    conflicting = await asyncio.gather(
        _locked_operator_write(third, expires_at=NOW + timedelta(days=1)),
        _locked_operator_write(fourth, expires_at=NOW + timedelta(days=2)),
        return_exceptions=True,
    )

    assert len(conflicting_table.rows) == 1, "the conflict stored a second grant row"
    conflicts = [item for item in conflicting if isinstance(item, GrantConflict)]
    records = [item for item in conflicting if not isinstance(item, BaseException)]
    assert len(conflicts) == 1
    assert len(records) == 1
    assert _field(records[0], "created") is True

    for session in (third, fourth):
        assert session.statements, "the session ran no statement"
        sql, params = session.statements[0]
        assert "pg_advisory_xact_lock" in sql
        assert params.get("key") == expected_key


@pytest.mark.asyncio
@pytest.mark.l4("C-bdb3718d")
@pytest.mark.parametrize(
    ("offset", "reason"),
    [
        (None, "expires_at_required"),
        (-10, "expires_at_in_past"),
        (604_801, "expires_at_too_far"),
    ],
)
async def test_C_bdb3718d_rule_violation_writes_nothing(
    monkeypatch: pytest.MonkeyPatch,
    offset: int | None,
    reason: str,
) -> None:
    monkeypatch.delenv(CAP_ENV, raising=False)
    session = _Session(_Table())
    expires_at = None if offset is None else NOW + timedelta(seconds=offset)

    raised: GrantExpiryError | None = None
    try:
        await write_grant(
            session,
            tenant_id=TENANT_ID,
            agent_id=AGENT_UUID,
            service_id=SERVICE_UUID,
            action="read",
            constraints=CONSTRAINTS,
            expires_at=expires_at,
            grantor=Grantor(type="agent", id=GRANTOR_AGENT_UUID),
            now=NOW,
        )
    except GrantExpiryError as exc:
        raised = exc

    assert raised is not None, "write_grant accepted a rule-violating expiry"
    assert raised.reason == reason
    assert session.statements == []


@pytest.mark.asyncio
@pytest.mark.l4("C-099f4d96")
async def test_C_099f4d96_delete_returns_record_or_nothing() -> None:
    stored = _Row(
        grantor_type="agent",
        grantor_id=GRANTOR_AGENT_UUID,
        expires_at=NOW + timedelta(days=1),
    )
    session = _Session(_Table([stored]))

    record = await delete_grant(session, tenant_id=TENANT_ID, grant_id=PERM_UUID)

    assert _field(record, "agent_id") == AGENT_UUID
    assert _field(record, "service_id") == SERVICE_UUID
    assert _field(record, "action") == "read"
    assert _field(record, "grantor_type") == "agent"
    assert _field(record, "grantor_id") == GRANTOR_AGENT_UUID
    assert len(_matching(session, "delete from permission_grants")) == 1
    assert session.table.rows == []

    missing = _Session(_Table())
    assert await delete_grant(missing, tenant_id=TENANT_ID, grant_id=PERM_UUID) is None
    assert not _matching(missing, "delete from permission_grants")


@pytest.mark.asyncio
@pytest.mark.l4("C-7a27cadf")
async def test_C_7a27cadf_payload_builders() -> None:
    past = NOW - timedelta(seconds=10)
    record = GrantRecord(
        id=PERM_UUID,
        wire_id=db_uuid_to_wire(PERM_UUID, "perm"),
        agent_id=AGENT_UUID,
        service_id=SERVICE_UUID,
        action="read",
        constraints=CONSTRAINTS,
        expires_at=past,
        grantor_type="agent",
        grantor_id=GRANTOR_AGENT_UUID,
        created_at=NOW - timedelta(days=2),
        created=True,
    )

    granted = grant_granted_audit_payload(record)
    assert isinstance(granted, dict)
    assert set(granted) == {
        "perm_id",
        "agent_id",
        "service_id",
        "action",
        "constraints",
        "expires_at",
        "grantor_type",
        "grantor_id",
    }
    assert granted.get("perm_id") == db_uuid_to_wire(PERM_UUID, "perm")
    assert granted.get("agent_id") == db_uuid_to_wire(AGENT_UUID, "agent")
    assert granted.get("service_id") == db_uuid_to_wire(SERVICE_UUID, "svc")
    assert granted.get("action") == "read"
    assert granted.get("constraints") == CONSTRAINTS
    assert granted.get("expires_at") == past.isoformat()
    assert granted.get("grantor_type") == "agent"
    assert granted.get("grantor_id") == db_uuid_to_wire(GRANTOR_AGENT_UUID, "agent")

    revoked = grant_revoked_audit_payload(record, Grantor("operator", OPERATOR_UUID))
    assert isinstance(revoked, dict)
    assert set(revoked) == {
        "permission_id",
        "agent_id",
        "service_id",
        "action",
        "grantor_type",
        "grantor_id",
        "revoked_by_type",
        "revoked_by_id",
    }
    assert revoked.get("permission_id") == db_uuid_to_wire(PERM_UUID, "perm")
    assert revoked.get("agent_id") == db_uuid_to_wire(AGENT_UUID, "agent")
    assert revoked.get("service_id") == db_uuid_to_wire(SERVICE_UUID, "svc")
    assert revoked.get("action") == "read"
    assert revoked.get("grantor_type") == "agent"
    assert revoked.get("grantor_id") == db_uuid_to_wire(GRANTOR_AGENT_UUID, "agent")
    assert revoked.get("revoked_by_type") == "operator"
    assert revoked.get("revoked_by_id") == OPERATOR_UUID

    wire = grant_wire_fields(record, NOW)
    assert isinstance(wire, dict)
    assert set(wire) == {"expires_at", "expired", "grantor_type", "grantor_id"}
    assert wire.get("expires_at") == past.isoformat()
    assert wire.get("expired") is True
    assert wire.get("grantor_type") == "agent"
    assert wire.get("grantor_id") == db_uuid_to_wire(GRANTOR_AGENT_UUID, "agent")

    operator_wire = grant_wire_fields(
        _Row(grantor_type="operator", grantor_id=OPERATOR_UUID, expires_at=None),
        NOW,
    )
    assert operator_wire.get("expires_at") is None
    assert operator_wire.get("expired") is False
    assert operator_wire.get("grantor_type") == "operator"
    assert operator_wire.get("grantor_id") == OPERATOR_UUID

    missing_type = grant_wire_fields(
        _Row(grantor_type=None, grantor_id=None, expires_at=None), NOW
    )
    assert missing_type.get("expires_at") is None
    assert missing_type.get("expired") is False
    assert missing_type.get("grantor_type") == "operator"
    assert missing_type.get("grantor_id") is None


@pytest.mark.asyncio
@pytest.mark.l4("C-20d077ee")
async def test_C_20d077ee_notify_payload_pins_the_revoked_at_format() -> None:
    record = GrantRecord(
        id=PERM_UUID,
        wire_id=db_uuid_to_wire(PERM_UUID, "perm"),
        agent_id=AGENT_UUID,
        service_id=SERVICE_UUID,
        action="read",
        constraints=CONSTRAINTS,
        expires_at=None,
        grantor_type="operator",
        grantor_id=OPERATOR_UUID,
        created_at=NOW,
        created=True,
    )
    cases = [
        (
            datetime(2026, 11, 25, 12, 0, tzinfo=timezone(timedelta(hours=2))),
            "2026-11-25T10:00:00+00:00",
        ),
        (
            datetime(2026, 11, 25, 10, 0, 0, 123456, tzinfo=timezone.utc),
            "2026-11-25T10:00:00.123456+00:00",
        ),
        (
            datetime(2026, 11, 25, 10, 0, 0),
            "2026-11-25T10:00:00+00:00",
        ),
    ]

    for revoked_at, expected in cases:
        payload = grant_revoked_notify_payload(TENANT_ID, record, revoked_at)
        assert isinstance(payload, dict)
        assert set(payload) == {
            "event",
            "tenant_id",
            "agent_id",
            "permission_id",
            "service_id",
            "revoked_at",
        }
        assert payload.get("event") == "agent.permission.revoked"
        assert payload.get("tenant_id") == str(TENANT_ID)
        assert payload.get("agent_id") == db_uuid_to_wire(AGENT_UUID, "agent")
        assert payload.get("permission_id") == db_uuid_to_wire(PERM_UUID, "perm")
        assert payload.get("service_id") == db_uuid_to_wire(SERVICE_UUID, "svc")
        assert payload.get("revoked_at") == expected
        json.dumps(payload)
