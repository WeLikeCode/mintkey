"""
Unit tests: the verify-chain endpoint checks a chain with the canonical form.

Events are written by ``audit_emit`` through a fake session; the INSERT
parameters become rows shaped as Postgres returns them (UUID ids, the payload
JSON text parsed, the bound ``at`` datetime, ``request_id`` and ``trace_id``
NULL).  The endpoint then reads those stored rows through a fake DB session
that records the statement it ran.

Source: specs/audit-chain/spec.md — "The verify-chain endpoint checks a chain
with the canonical form"; design.md D3-D4; ADR-0014.7.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import uuid
from types import SimpleNamespace
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from mintkey_models.audit import audit_emit  # noqa: E402
from mintkey_models.audit_hash import (  # noqa: E402
    chain_event_from_row,
    event_hash,
    genesis_hash,
)

VERIFY_URL = "/v1/admin/audit/verify-chain"
TENANT = uuid.UUID("5f1c2d3e-4a5b-4c6d-8e7f-90a1b2c3d4e5")
ACTOR = uuid.UUID("7d9e8f10-1a2b-4c3d-9e4f-5a6b7c8d9e0f")
TARGET = uuid.UUID("c3a1e2f4-5b6c-4d7e-8f90-a1b2c3d4e5f6")

EVENTS_SELECT = (
    "SELECT id, tenant_id, event_type, actor_id, actor_type, target_id,"
    " target_type, payload, at, prev_hash, hash, request_id, trace_id"
    " FROM audit_events WHERE tenant_id = :tenant_id"
    " ORDER BY at ASC, id ASC"
)


class _Result:
    def __init__(self, rows: list[Any] | None = None, row: Any = None) -> None:
        self._rows = rows or []
        self._row = row

    def fetchall(self) -> list[Any]:
        return self._rows

    def fetchone(self) -> Any:
        return self._row


class _WriterSession:
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


class _EndpointSession:
    """A DB session that records every statement and returns the stored rows."""

    def __init__(self, rows: list[Any]) -> None:
        self.rows = rows
        self.statements: list[str] = []

    async def execute(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> _Result:
        self.statements.append(" ".join(str(statement).split()))
        return _Result(rows=self.rows)


def _genesis(tenant_id: str) -> bytes:
    return hashlib.sha256(
        ("mintkey-audit-genesis-v1:" + tenant_id).encode()
    ).digest()


def _seeded_writer() -> _WriterSession:
    session = _WriterSession()
    session.heads[str(TENANT)] = _genesis(str(TENANT))
    return session


async def _write_event(session: _WriterSession) -> None:
    await audit_emit(
        session=session,
        tenant_id=TENANT,
        event_type="service.created",
        actor_id=ACTOR,
        actor_type="operator",
        target_id=TARGET,
        target_type="agent",
        payload={"name": "svc-a", "count": 2},
    )


def _row_fields(insert: dict[str, Any]) -> dict[str, Any]:
    """The 13 columns as Postgres returns them for a written event."""
    return {
        "id": uuid.UUID(str(insert["id"])),
        "tenant_id": uuid.UUID(str(insert["tenant_id"])),
        "event_type": insert["event_type"],
        "actor_id": uuid.UUID(str(insert["actor_id"])),
        "actor_type": insert["actor_type"],
        "target_id": uuid.UUID(str(insert["target_id"])),
        "target_type": insert["target_type"],
        "payload": json.loads(insert["payload"]),
        "at": insert["at"],
        "prev_hash": insert["prev_hash"],
        "hash": insert["hash"],
        "request_id": None,
        "trace_id": None,
    }


async def _write_events(count: int) -> list[SimpleNamespace]:
    session = _seeded_writer()
    for _ in range(count):
        await _write_event(session)
    return [SimpleNamespace(**_row_fields(insert)) for insert in session.inserts]


def _changed_row(row: Any, column: str, value: Any) -> SimpleNamespace:
    fields = dict(vars(row))
    fields[column] = value
    return SimpleNamespace(**fields)


async def _noop_platform_admin() -> None:
    return None


def _create_test_app(session: _EndpointSession) -> Any:
    from fastapi import FastAPI
    from admin_api.api.audit_admin import router as audit_admin_router
    from admin_api.auth.sessions import require_platform_admin_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(audit_admin_router)

    async def mock_db_session():
        yield session

    app.dependency_overrides[get_db_session] = mock_db_session
    app.dependency_overrides[require_platform_admin_session] = _noop_platform_admin

    csrf_exempt(VERIFY_URL)
    app.add_middleware(CsrfMiddleware)
    return app


async def _post_verify(session: _EndpointSession) -> Any:
    app = _create_test_app(session)
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(VERIFY_URL, params={"tenant_id": str(TENANT)})


@pytest.mark.asyncio
@pytest.mark.l4("C-7c6781a5")
async def test_C_7c6781a5_endpoint_verifies_event_written_by_audit_emit() -> None:
    rows = await _write_events(1)
    session = _EndpointSession(rows)

    resp = await _post_verify(session)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["chain_length"] == 1
    assert body["last_event_id"] == str(rows[0].id)
    assert EVENTS_SELECT in session.statements


@pytest.mark.asyncio
@pytest.mark.l4("C-e8293d4d")
async def test_C_e8293d4d_endpoint_reports_altered_payload() -> None:
    rows = await _write_events(1)
    changed = _changed_row(rows[0], "payload", {"name": "svc-b", "count": 2})
    expected = event_hash(chain_event_from_row(changed)).hex()
    actual = bytes(changed.hash).hex()

    resp = await _post_verify(_EndpointSession([changed]))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["first_bad_event_id"] == str(changed.id)
    assert body["expected_hash"] == expected
    assert body["actual_hash"] == actual


@pytest.mark.asyncio
@pytest.mark.l4("C-e5cc56fd")
async def test_C_e5cc56fd_endpoint_reports_event_that_does_not_follow_chain() -> None:
    rows = await _write_events(2)
    second = rows[1]

    resp = await _post_verify(_EndpointSession([second]))

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["first_bad_event_id"] == str(second.id)
    assert body["expected_hash"] == genesis_hash(str(TENANT)).hex()
    assert body["actual_hash"] == bytes(second.prev_hash).hex()
