"""
Tests for the canonical audit hash form and chain verification.

The events are written by ``audit_emit`` through a fake session; their INSERT
parameters become rows shaped as Postgres returns them (UUID ids, the payload
JSON text parsed, the bound ``at`` datetime, ``request_id`` and ``trace_id``
NULL).  Verification then runs against those stored rows only.

Source: specs/audit-chain/spec.md — "One canonical form for the audit event
hash", "The chain is verified from the stored columns by its links" and
"Altering any stored field of an event fails its verification";
design.md D1-D6; ADR-0014.7.
"""
from __future__ import annotations

import asyncio
import dataclasses
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any

import pytest

from mintkey_models.audit import audit_emit, compute_hash
from mintkey_models.audit_hash import (
    canonical_at,
    canonical_event_fields,
    canonical_id,
    canonical_json_bytes,
    chain_event_from_row,
    chain_hash,
    event_hash,
    genesis_hash,
    verify_events,
)

TENANT = uuid.UUID("5f1c2d3e-4a5b-4c6d-8e7f-90a1b2c3d4e5")
ACTOR = uuid.UUID("7d9e8f10-1a2b-4c3d-9e4f-5a6b7c8d9e0f")
TARGET = uuid.UUID("c3a1e2f4-5b6c-4d7e-8f90-a1b2c3d4e5f6")
NEW_ID = uuid.UUID("aaaaaaaa-bbbb-4ccc-8ddd-eeeeeeeeeeee")

GOLDEN_TENANT = "5f1c2d3e-4a5b-4c6d-8e7f-90a1b2c3d4e5"
GOLDEN_BYTES = (
    b'{"actor_id":"7d9e8f10-1a2b-4c3d-9e4f-5a6b7c8d9e0f",'
    b'"actor_type":"operator",'
    b'"at":"2026-10-25T09:30:00.123456+00:00",'
    b'"event_type":"service.created",'
    b'"id":"0b0e7c51-3a52-4c5e-9d5b-2f4f6f3f9a10",'
    b'"payload":{"count":2,"name":"svc-a"},'
    b'"target_id":"c3a1e2f4-5b6c-4d7e-8f90-a1b2c3d4e5f6",'
    b'"target_type":"service",'
    b'"tenant_id":"5f1c2d3e-4a5b-4c6d-8e7f-90a1b2c3d4e5"}'
)
GOLDEN_GENESIS_HEX = (
    "58d21bc79de12e830899d1008e35c0fe27d883946121948b6cb5ee78820d8a89"
)
GOLDEN_CHAIN_HEX = (
    "d653e8c4e55acddea203e75f389c0f5d4b631d4d78426fa6a6d013c669e22372"
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


# ---------------------------------------------------------------------------
# One canonical form for the audit event hash
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-f7069358")
def test_C_f7069358_canonical_bytes_of_a_fixed_event() -> None:
    fields = canonical_event_fields(
        event_id="0b0e7c51-3a52-4c5e-9d5b-2f4f6f3f9a10",
        tenant_id=GOLDEN_TENANT,
        event_type="service.created",
        actor_id="7d9e8f10-1a2b-4c3d-9e4f-5a6b7c8d9e0f",
        actor_type="operator",
        target_id="c3a1e2f4-5b6c-4d7e-8f90-a1b2c3d4e5f6",
        target_type="service",
        payload={"name": "svc-a", "count": 2},
        at=datetime(2026, 10, 25, 9, 30, 0, 123456, tzinfo=timezone.utc),
    )
    canonical = canonical_json_bytes(fields)
    assert canonical == GOLDEN_BYTES
    genesis = genesis_hash(GOLDEN_TENANT)
    assert genesis.hex() == GOLDEN_GENESIS_HEX
    assert chain_hash(canonical, genesis).hex() == GOLDEN_CHAIN_HEX


@pytest.mark.l4("C-f3d1852b")
def test_C_f3d1852b_writers_hash_function_keeps_its_result() -> None:
    event_dict = {
        "id": "0b0e7c51-3a52-4c5e-9d5b-2f4f6f3f9a10",
        "tenant_id": GOLDEN_TENANT,
        "event_type": "service.created",
        "actor_id": "7d9e8f10-1a2b-4c3d-9e4f-5a6b7c8d9e0f",
        "actor_type": "operator",
        "target_id": "c3a1e2f4-5b6c-4d7e-8f90-a1b2c3d4e5f6",
        "target_type": "service",
        "payload": {"name": "svc-a", "count": 2},
        "at": "2026-10-25T09:30:00.123456+00:00",
    }
    genesis = bytes.fromhex(GOLDEN_GENESIS_HEX)
    digest = compute_hash(event_dict, genesis)
    assert digest.hex() == GOLDEN_CHAIN_HEX
    assert digest == chain_hash(canonical_json_bytes(event_dict), genesis)


@pytest.mark.l4("C-7c9b66d2")
def test_C_7c9b66d2_forms_of_a_time() -> None:
    assert (
        canonical_at(datetime(2026, 10, 25, 9, 30, 0, 123456, tzinfo=timezone.utc))
        == "2026-10-25T09:30:00.123456+00:00"
    )
    assert (
        canonical_at(datetime(2026, 10, 25, 9, 30, tzinfo=timezone.utc))
        == "2026-10-25T09:30:00+00:00"
    )
    assert (
        canonical_at(
            datetime(2026, 10, 25, 12, 30, tzinfo=timezone(timedelta(hours=3)))
        )
        == "2026-10-25T09:30:00+00:00"
    )
    with pytest.raises(ValueError):
        canonical_at(datetime(2026, 10, 25, 9, 30))


@pytest.mark.l4("C-17e74dc9")
def test_C_17e74dc9_forms_of_an_id() -> None:
    expected = "0b0e7c51-3a52-4c5e-9d5b-2f4f6f3f9a10"
    assert canonical_id(uuid.UUID(expected)) == expected
    assert canonical_id("0B0E7C51-3A52-4C5E-9D5B-2F4F6F3F9A10") == expected
    assert canonical_id("tenant_ABC") == "tenant_ABC"
    assert canonical_id(None) is None


# ---------------------------------------------------------------------------
# The chain is verified from the stored columns by its links
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3aaa99e2")
def test_C_3aaa99e2_event_written_by_audit_emit_verifies_from_its_row() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    row = _stored_rows(session)[0]

    event = chain_event_from_row(row)
    assert event is not None
    result = verify_events([event])
    assert result is not None

    assert result.ok is True
    assert result.chain_length == 1
    assert result.last_event_id == str(row.id)


@pytest.mark.l4("C-5090a0a4")
def test_C_5090a0a4_chain_of_three_verifies_in_any_order() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    _run(_write_event(session))
    _run(_write_event(session))
    rows = _stored_rows(session)
    expected_last = str(rows[-1].id)

    events = [chain_event_from_row(row) for row in reversed(rows)]
    assert all(event is not None for event in events)
    result = verify_events(events)
    assert result is not None

    assert result.ok is True
    assert result.chain_length == 3
    assert result.last_event_id == expected_last


@pytest.mark.l4("C-80a7cb05")
def test_C_80a7cb05_time_read_back_in_another_zone_verifies() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    row = _stored_rows(session)[0]
    row.at = row.at.astimezone(timezone(timedelta(hours=3)))

    event = chain_event_from_row(row)
    assert event is not None
    result = verify_events([event])
    assert result is not None

    assert result.ok is True


@pytest.mark.l4("C-e60cb8cf")
def test_C_e60cb8cf_payload_read_back_as_json_text_verifies() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    row = _stored_rows(session)[0]
    row.payload = session.inserts[0]["payload"]

    event = chain_event_from_row(row)
    assert event is not None
    result = verify_events([event])
    assert result is not None

    assert result.ok is True


@pytest.mark.l4("C-2113cf48")
def test_C_2113cf48_event_that_does_not_follow_the_chain() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    _run(_write_event(session))
    second = _stored_rows(session)[1]

    event = chain_event_from_row(second)
    assert event is not None
    result = verify_events([event])
    assert result is not None

    assert result.ok is False
    assert result.first_bad_event_id == str(second.id)
    assert result.expected_hash == _genesis(str(TENANT))
    assert result.actual_hash == second.prev_hash
    assert result.chain_length == 0
    assert result.last_event_id is None


@pytest.mark.l4("C-8fdf2bca")
def test_C_8fdf2bca_two_events_that_follow_the_same_hash() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    _run(_write_event(session))
    first_row, second_row = _stored_rows(session)
    first = chain_event_from_row(first_row)
    second = chain_event_from_row(second_row)
    assert first is not None
    assert second is not None
    copy = dataclasses.replace(second, id=str(NEW_ID))
    copy = dataclasses.replace(copy, hash=event_hash(copy))

    result = verify_events([first, second, copy])
    assert result is not None

    assert result.ok is False
    assert result.first_bad_event_id == copy.id


@pytest.mark.l4("C-7b97d875")
def test_C_7b97d875_no_events() -> None:
    result = verify_events([])
    assert result is not None

    assert result.ok is True
    assert result.chain_length == 0
    assert result.last_event_id is None
    assert result.message == "empty chain"


# ---------------------------------------------------------------------------
# Altering any stored field of an event fails its verification
# ---------------------------------------------------------------------------


_ALTERATIONS = [
    ("id", lambda fields: NEW_ID),
    ("tenant_id", lambda fields: NEW_ID),
    ("actor_id", lambda fields: NEW_ID),
    ("target_id", lambda fields: NEW_ID),
    ("request_id", lambda fields: NEW_ID),
    ("event_type", lambda fields: "other.type"),
    ("actor_type", lambda fields: "agent"),
    ("target_type", lambda fields: "service"),
    ("payload", lambda fields: {"name": "svc-b", "count": 2}),
    ("at", lambda fields: fields["at"] + timedelta(microseconds=1)),
    ("prev_hash", lambda fields: b"\x01" * 32),
    ("hash", lambda fields: b"\x02" * 32),
    ("trace_id", lambda fields: "trace-1"),
]


@pytest.mark.l4("C-3c3643e2")
@pytest.mark.parametrize(
    ("column", "change"),
    _ALTERATIONS,
    ids=[column for column, _ in _ALTERATIONS],
)
def test_C_3c3643e2_altering_one_stored_field_fails(
    column: str, change: Any
) -> None:
    session = _seeded_session()
    _run(_write_event(session))
    fields = _row_fields(session.inserts[0])
    fields[column] = change(fields)
    row = SimpleNamespace(**fields)

    event = chain_event_from_row(row)
    assert event is not None
    result = verify_events([event])
    assert result is not None

    assert result.ok is False
    assert result.first_bad_event_id == str(fields["id"])


@pytest.mark.l4("C-7537b2bd")
def test_C_7537b2bd_payload_change_reports_both_hashes() -> None:
    session = _seeded_session()
    _run(_write_event(session))
    fields = _row_fields(session.inserts[0])
    stored_hash = fields["hash"]
    fields["payload"] = {"name": "svc-b", "count": 2}
    changed = chain_event_from_row(SimpleNamespace(**fields))
    assert changed is not None

    result = verify_events([changed])
    assert result is not None

    assert result.ok is False
    assert result.expected_hash == event_hash(changed)
    assert result.actual_hash == stored_hash
