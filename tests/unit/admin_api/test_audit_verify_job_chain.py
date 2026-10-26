"""
Unit tests: the verify job checks a chain with the canonical form.

Events are written by ``audit_emit`` through a fake session; the INSERT
parameters become rows shaped as Postgres returns them (UUID ids, the payload
JSON text parsed, the bound ``at`` datetime, ``request_id`` and ``trace_id``
NULL).  ``verify_rows``, ``verify_chain`` and ``main._run`` are then checked
against those stored rows.

Source: specs/audit-chain/spec.md — "The verify job checks a chain with the
canonical form"; design.md D4-D6; ADR-0014.7.
"""
from __future__ import annotations

import asyncio
import hashlib
import importlib.util
import json
import os
import sys
import uuid
from datetime import timedelta
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
VERIFY_JOB_DIR = os.path.join(REPO_ROOT, "apps/audit-verify-job")
for _path in (ADMIN_API_SRC, MODELS_SRC, VERIFY_JOB_DIR):
    if _path not in sys.path:
        sys.path.insert(0, _path)

import verify  # noqa: E402
from mintkey_models.audit import audit_emit  # noqa: E402

TENANT = uuid.UUID("5f1c2d3e-4a5b-4c6d-8e7f-90a1b2c3d4e5")
ACTOR = uuid.UUID("7d9e8f10-1a2b-4c3d-9e4f-5a6b7c8d9e0f")
TARGET = uuid.UUID("c3a1e2f4-5b6c-4d7e-8f90-a1b2c3d4e5f6")
NEW_ID = uuid.UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")

EVENTS_SELECT = (
    "SELECT id, tenant_id, event_type, actor_id, actor_type, target_id,"
    " target_type, payload, at, prev_hash, hash, request_id, trace_id"
    " FROM audit_events WHERE tenant_id = :tid ORDER BY at ASC, id ASC"
)


class _Result:
    def __init__(self, rows: list[Any] | None = None, row: Any = None) -> None:
        self._rows = rows or []
        self._row = row

    def fetchall(self) -> list[Any]:
        return self._rows

    def fetchone(self) -> Any:
        return self._row


class _FakeSession:
    """The four statements ``audit_emit`` runs, without a database."""

    def __init__(self) -> None:
        self.heads: dict[str, bytes] = {}
        self.inserts: list[dict[str, Any]] = []

    async def execute(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> _Result:
        sql = " ".join(str(statement).split())
        values = params or {}
        if "pg_advisory_xact_lock" in sql:
            return _Result()
        if sql.startswith("SELECT head_hash"):
            head = self.heads.get(values["tid"])
            return _Result(row=(head,) if head is not None else None)
        if sql.startswith("INSERT INTO audit_events"):
            self.inserts.append(dict(values))
            return _Result()
        if sql.startswith("UPDATE audit_chain_state"):
            self.heads[values["tid"]] = values["hash"]
            return _Result()
        raise AssertionError(f"unexpected statement: {sql}")


class _FakeRows:
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return self._rows


class _FakeBegin:
    def __init__(self, connection: "_FakeConnection") -> None:
        self._connection = connection

    async def __aenter__(self) -> "_FakeConnection":
        return self._connection

    async def __aexit__(self, *exc_info: Any) -> bool:
        return False


class _FakeConnection:
    def __init__(
        self,
        statements: list[str],
        tenants: list[Any],
        rows: list[Any],
    ) -> None:
        self.statements = statements
        self.tenants = tenants
        self.rows = rows

    async def execute(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> _FakeRows:
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if "FROM tenants" in sql:
            return _FakeRows(self.tenants)
        if "FROM audit_events" in sql:
            return _FakeRows(self.rows)
        raise AssertionError(f"unexpected statement: {sql}")


class _FakeEngine:
    def __init__(
        self, statements: list[str], tenants: list[Any], rows: list[Any]
    ) -> None:
        self._connection = _FakeConnection(statements, tenants, rows)

    def begin(self) -> _FakeBegin:
        return _FakeBegin(self._connection)

    async def dispose(self) -> None:
        return None


def _engine_factory(
    statements: list[str], tenants: list[Any], rows: list[Any]
) -> Any:
    def _create(url: str) -> _FakeEngine:
        return _FakeEngine(statements, tenants, rows)

    return _create


def _genesis(tenant_id: str) -> bytes:
    return hashlib.sha256(
        ("mintkey-audit-genesis-v1:" + tenant_id).encode()
    ).digest()


def _run(coro: Any) -> Any:
    """Run one coroutine on a fresh loop without touching the policy's loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _seeded_session(tenant: uuid.UUID = TENANT) -> _FakeSession:
    session = _FakeSession()
    session.heads[str(tenant)] = _genesis(str(tenant))
    return session


async def _write_event(
    session: _FakeSession,
    *,
    tenant: uuid.UUID = TENANT,
    event_type: str = "service.created",
    actor_type: str = "operator",
    target_type: str = "agent",
    payload: dict[str, Any] | None = None,
) -> None:
    await audit_emit(
        session=session,
        tenant_id=tenant,
        event_type=event_type,
        actor_id=ACTOR,
        actor_type=actor_type,
        target_id=TARGET,
        target_type=target_type,
        payload={"name": "svc-a", "count": 2} if payload is None else payload,
    )


def _row_fields(insert: dict[str, Any]) -> dict[str, Any]:
    """The 13 columns as Postgres returns them for a written event."""
    return {
        "id": uuid.UUID(str(insert["id"])),
        "tenant_id": uuid.UUID(str(insert["tenant_id"])),
        "event_type": insert["event_type"],
        "actor_id": (
            uuid.UUID(str(insert["actor_id"]))
            if insert["actor_id"] is not None
            else None
        ),
        "actor_type": insert["actor_type"],
        "target_id": (
            uuid.UUID(str(insert["target_id"]))
            if insert["target_id"] is not None
            else None
        ),
        "target_type": insert["target_type"],
        "payload": json.loads(insert["payload"]),
        "at": insert["at"],
        "prev_hash": insert["prev_hash"],
        "hash": insert["hash"],
        "request_id": None,
        "trace_id": None,
    }


def _stored_rows(session: _FakeSession) -> list[SimpleNamespace]:
    return [SimpleNamespace(**_row_fields(insert)) for insert in session.inserts]


def _changed_row(row: Any, column: str, value: Any) -> SimpleNamespace:
    fields = dict(vars(row))
    fields[column] = value
    return SimpleNamespace(**fields)


def _audit_event_from_row(row: Any) -> Any:
    """An ``AuditEvent`` carrying every field of a stored row."""
    event = verify.AuditEvent(
        id=str(row.id),
        event_type=row.event_type,
        tenant_id=str(row.tenant_id),
        payload=row.payload,
        hash=row.hash,
        prev_hash=row.prev_hash,
    )
    event.actor_id = row.actor_id
    event.actor_type = row.actor_type
    event.target_id = row.target_id
    event.target_type = row.target_type
    event.at = row.at
    event.request_id = row.request_id
    event.trace_id = row.trace_id
    return event


def _load_job_main() -> ModuleType:
    path = os.path.join(VERIFY_JOB_DIR, "main.py")
    spec = importlib.util.spec_from_file_location("audit_verify_job_main", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.l4("C-eaabd043")
def test_C_eaabd043_job_verifies_an_event_written_by_audit_emit() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    row = _stored_rows(session)[0]

    result = verify.verify_rows([row])
    assert result is not None

    assert isinstance(result, verify.VerifyResult)
    assert result.ok is True
    assert result.chain_length == 1


@pytest.mark.l4("C-6e72b396")
def test_C_6e72b396_job_reports_an_altered_field() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    row = _stored_rows(session)[0]

    alterations = [
        ("payload", {"name": "svc-b", "count": 2}),
        ("at", row.at + timedelta(microseconds=1)),
        ("actor_id", NEW_ID),
        ("request_id", NEW_ID),
    ]
    for column, value in alterations:
        changed = _changed_row(row, column, value)
        result = verify.verify_rows([changed])
        assert result is not None
        assert result.ok is False, column
        assert result.first_bad_event_id == str(row.id), column


@pytest.mark.l4("C-7a6282bc")
def test_C_7a6282bc_dataclass_chain_verifies_and_event_without_time_is_refused() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    _run(_write_event(session))
    rows = _stored_rows(session)

    events = [_audit_event_from_row(row) for row in rows]
    result = verify.verify_chain(events)
    assert result is not None

    assert result.ok is True
    assert result.chain_length == 2

    no_time = _audit_event_from_row(rows[0])
    no_time.at = None
    with pytest.raises(ValueError):
        verify.compute_event_hash(no_time, rows[0].prev_hash)


@pytest.mark.l4("C-7d0c268b")
def test_C_7d0c268b_main_reads_the_13_columns_and_exits_by_the_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _seeded_session()
    _run(_write_event(session))
    row = _stored_rows(session)[0]
    altered = _changed_row(row, "payload", {"name": "svc-b", "count": 2})

    job_main = _load_job_main()
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://unused")

    import sqlalchemy.ext.asyncio as sa_asyncio

    intact_statements: list[str] = []
    monkeypatch.setattr(
        sa_asyncio,
        "create_async_engine",
        _engine_factory(intact_statements, [(TENANT,)], [row]),
    )
    assert asyncio.run(job_main._run(None)) == 0
    assert EVENTS_SELECT in intact_statements

    altered_statements: list[str] = []
    monkeypatch.setattr(
        sa_asyncio,
        "create_async_engine",
        _engine_factory(altered_statements, [(TENANT,)], [altered]),
    )
    assert asyncio.run(job_main._run(None)) == 1
    assert EVENTS_SELECT in altered_statements
