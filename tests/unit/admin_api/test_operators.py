"""
Unit tests for admin_api.api.operators (feat/operator-management-api).

Tests:
  T-01  test_create_operator_happy_path          — 201, 1 operators INSERT + 1 membership INSERT,
                                                    operator.created emitted, no internal_password_hash,
                                                    id starts with op_.
  T-02  test_create_operator_duplicate_returns_409 — IntegrityError → 409 duplicate_resource.
  T-03  test_update_operator_sets_platform_admin  — PATCH sets is_platform_admin, operator.updated.
  T-04  test_update_operator_unknown_returns_404  — PATCH unknown id → 404 not_found.
  T-05  test_delete_operator_soft_deactivate      — DELETE 204, status→disabled, operator.deleted.
  T-06  test_delete_operator_idempotent           — already-disabled → 204, no audit, no UPDATE.
  T-07  test_audit_actor_type_is_platform_admin   — every write uses actor_type="platform_admin".

Source: ADR-0031; openspec/changes/operator-management.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import exc as sa_exc

from admin_api.utils.wire_ids import db_uuid_to_wire


# ---------------------------------------------------------------------------
# Helpers: minimal async DB session mock (mirrors test_email_permission_grants.py)
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

    async def execute(self, stmt: Any, params: Any = None) -> Any:
        sql: str = str(stmt) if not hasattr(stmt, "text") else stmt.text
        self.executed_sql.append((sql, params or {}))
        for fragment, result in self._results.items():
            if fragment in sql:
                return result
        return _FakeResult(None)


def _make_session(**results: Any) -> _FakeSession:
    return _FakeSession(query_results=results)


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from admin_api.api.operators import (  # noqa: E402
    CreateOperatorRequest,
    UpdateOperatorRequest,
    create_operator,
    delete_operator,
    list_operators,
    update_operator,
)


# ---------------------------------------------------------------------------
# Shared identifiers
# ---------------------------------------------------------------------------

TENANT_UUID = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
OPERATOR_UUID = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
TENANT_WIRE = db_uuid_to_wire(TENANT_UUID, "tenant")
OPERATOR_WIRE = db_uuid_to_wire(OPERATOR_UUID, "op")
SESSION_CTX = SimpleNamespace(operator_id=uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"))


def _operator_row(**overrides: Any) -> _FakeRow:
    base: dict[str, Any] = {
        "id": str(OPERATOR_UUID),
        "tenant_id": str(TENANT_UUID),
        "email": "ops@acme.example",
        "display_name": "Acme Ops",
        "oidc_sub": None,
        "oidc_provider": None,
        "is_platform_admin": False,
        "status": "active",
        "created_at": datetime.now(timezone.utc),
    }
    base.update(overrides)
    return _FakeRow(**base)


def _patch_rls() -> Any:
    """Patch the RLS GUC helper to a no-op (no real DB connection in unit tests)."""
    return patch(
        "admin_api.api.operators._set_platform_admin_rls",
        new_callable=AsyncMock,
    )


# ---------------------------------------------------------------------------
# T-01: Create — happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_operator_happy_path() -> None:
    session = _make_session(**{"INSERT INTO operators": _FakeResult(_operator_row())})

    body = CreateOperatorRequest(
        email="ops@acme.example",
        display_name="Acme Ops",
        tenant_id=TENANT_WIRE,
        is_platform_admin=False,
    )

    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    with _patch_rls(), patch(
        "admin_api.api.operators.audit_emit", side_effect=fake_audit_emit
    ):
        response = await create_operator(
            body=body,
            _authz=None,
            session=session,  # type: ignore[arg-type]
            ctx=SESSION_CTX,
        )

    assert response.status_code == 201
    body_text = response.body.decode()

    # Exactly one operators INSERT + one membership INSERT.
    op_inserts = [s for s, _ in session.executed_sql if "INSERT INTO operators" in s]
    mem_inserts = [
        s for s, _ in session.executed_sql if "INSERT INTO operator_tenant_memberships" in s
    ]
    assert len(op_inserts) == 1, session.executed_sql
    assert len(mem_inserts) == 1, session.executed_sql
    assert "'Admin'" in mem_inserts[0]

    # Audit: operator.created with platform_admin actor.
    assert len(audit_calls) == 1
    assert audit_calls[0]["event_type"] == "operator.created"
    assert audit_calls[0]["actor_type"] == "platform_admin"
    assert audit_calls[0]["actor_id"] == SESSION_CTX.operator_id

    # Response never leaks internal_password_hash and uses op_ wire id.
    assert "internal_password_hash" not in body_text
    import json as _json

    payload = _json.loads(body_text)
    assert payload["id"].startswith("op_")
    assert payload["id"] == OPERATOR_WIRE
    assert payload["tenant_id"] == TENANT_WIRE


# ---------------------------------------------------------------------------
# T-02: Create — duplicate → 409
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_operator_duplicate_returns_409() -> None:
    class DupSession(_FakeSession):
        async def execute(self, stmt: Any, params: Any = None) -> Any:
            sql = str(stmt) if not hasattr(stmt, "text") else stmt.text
            if "INSERT INTO operators" in sql:
                raise sa_exc.IntegrityError(
                    "INSERT INTO operators", {}, Exception("duplicate key")
                )
            return await super().execute(stmt, params)

    session = DupSession()
    body = CreateOperatorRequest(email="dup@acme.example", tenant_id=TENANT_WIRE)

    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    with _patch_rls(), patch(
        "admin_api.api.operators.audit_emit", side_effect=fake_audit_emit
    ):
        response = await create_operator(
            body=body,
            _authz=None,
            session=session,  # type: ignore[arg-type]
            ctx=SESSION_CTX,
        )

    assert response.status_code == 409
    assert b"duplicate_resource" in response.body
    # No membership INSERT, no audit event on the failure path.
    assert not any(
        "INSERT INTO operator_tenant_memberships" in s for s, _ in session.executed_sql
    )
    assert audit_calls == []


# ---------------------------------------------------------------------------
# T-03: Update — set is_platform_admin, operator.updated
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_operator_sets_platform_admin() -> None:
    existing = _operator_row(is_platform_admin=False)
    updated = _operator_row(is_platform_admin=True)
    session = _make_session(
        **{
            "FROM operators WHERE id = :oid": _FakeResult(existing),
            "UPDATE operators SET": _FakeResult(updated),
        }
    )

    body = UpdateOperatorRequest(is_platform_admin=True)

    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    with _patch_rls(), patch(
        "admin_api.api.operators.audit_emit", side_effect=fake_audit_emit
    ):
        response = await update_operator(
            operator_id=OPERATOR_WIRE,
            body=body,
            _authz=None,
            session=session,  # type: ignore[arg-type]
            ctx=SESSION_CTX,
        )

    assert response.status_code == 200
    import json as _json

    payload = _json.loads(response.body)
    assert payload["is_platform_admin"] is True

    assert len(audit_calls) == 1
    assert audit_calls[0]["event_type"] == "operator.updated"
    assert audit_calls[0]["actor_type"] == "platform_admin"

    updates = [s for s, _ in session.executed_sql if "UPDATE operators SET" in s]
    assert len(updates) == 1
    # No updated_at column is touched (ADR-0031 D5).
    assert "updated_at" not in updates[0]


# ---------------------------------------------------------------------------
# T-04: Update — unknown id → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_update_operator_unknown_returns_404() -> None:
    session = _make_session()  # SELECT returns None

    body = UpdateOperatorRequest(display_name="X")

    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    with _patch_rls(), patch(
        "admin_api.api.operators.audit_emit", side_effect=fake_audit_emit
    ):
        response = await update_operator(
            operator_id=OPERATOR_WIRE,
            body=body,
            _authz=None,
            session=session,  # type: ignore[arg-type]
            ctx=SESSION_CTX,
        )

    assert response.status_code == 404
    assert b"not_found" in response.body
    assert audit_calls == []
    assert not any("UPDATE operators SET" in s for s, _ in session.executed_sql)


# ---------------------------------------------------------------------------
# T-05: Delete — soft-deactivate active operator
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_operator_soft_deactivate() -> None:
    row = _FakeRow(id=str(OPERATOR_UUID), tenant_id=str(TENANT_UUID), status="active")
    session = _make_session(**{"SELECT id, tenant_id, status": _FakeResult(row)})

    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    with _patch_rls(), patch(
        "admin_api.api.operators.audit_emit", side_effect=fake_audit_emit
    ):
        response = await delete_operator(
            operator_id=OPERATOR_WIRE,
            _authz=None,
            session=session,  # type: ignore[arg-type]
            ctx=SESSION_CTX,
        )

    assert response.status_code == 204

    updates = [s for s, _ in session.executed_sql if "UPDATE operators SET status = 'disabled'" in s]
    assert len(updates) == 1

    assert len(audit_calls) == 1
    assert audit_calls[0]["event_type"] == "operator.deleted"
    assert audit_calls[0]["actor_type"] == "platform_admin"


# ---------------------------------------------------------------------------
# T-06: Delete — idempotent (already disabled → 204, no audit, no UPDATE)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_operator_idempotent() -> None:
    row = _FakeRow(id=str(OPERATOR_UUID), tenant_id=str(TENANT_UUID), status="disabled")
    session = _make_session(**{"SELECT id, tenant_id, status": _FakeResult(row)})

    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    with _patch_rls(), patch(
        "admin_api.api.operators.audit_emit", side_effect=fake_audit_emit
    ):
        response = await delete_operator(
            operator_id=OPERATOR_WIRE,
            _authz=None,
            session=session,  # type: ignore[arg-type]
            ctx=SESSION_CTX,
        )

    assert response.status_code == 204
    assert audit_calls == []
    assert not any("UPDATE operators SET" in s for s, _ in session.executed_sql)


# ---------------------------------------------------------------------------
# T-07: List — no internal_password_hash, op_ wire ids
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_operators_serializes_wire_ids() -> None:
    session = _make_session(
        **{"FROM operators": _FakeResult(None, rows=[_operator_row()])}
    )

    with _patch_rls():
        response = await list_operators(
            q=None,
            tenant_id=None,
            _authz=None,
            session=session,  # type: ignore[arg-type]
        )

    assert response.status_code == 200
    import json as _json

    body = _json.loads(response.body)
    assert body["next_cursor"] is None
    assert len(body["data"]) == 1
    assert body["data"][0]["id"].startswith("op_")
    assert "internal_password_hash" not in response.body.decode()


# ---------------------------------------------------------------------------
# T-08: Emitted audit payloads conform to audit-event.schema.json
# ---------------------------------------------------------------------------
#
# The three operator writes each emit a hash-chained audit event whose payload
# MUST match the corresponding ev_operator_* definition in the contract
# (docs/architecture/contracts/events/audit-event.schema.json) — correct keys,
# all required keys present, no extras.  When `jsonschema` is importable in the
# env we validate the payload fully against the sub-schema (this also enforces
# the operator_id `^operator_…` pattern); otherwise we fall back to a strict
# key-set check against the schema's `required` / `properties`.

import json as _json_schema
from pathlib import Path as _Path

_AUDIT_SCHEMA_PATH = (
    _Path(__file__).resolve().parents[3]
    / "docs"
    / "architecture"
    / "contracts"
    / "events"
    / "audit-event.schema.json"
)


def _load_audit_schema() -> dict[str, Any]:
    with open(_AUDIT_SCHEMA_PATH, encoding="utf-8") as fh:
        return _json_schema.load(fh)


def _assert_payload_conforms(def_name: str, payload: dict[str, Any]) -> None:
    schema = _load_audit_schema()
    payload_schema = schema["$defs"][def_name]["properties"]["payload"]
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:
        required = set(payload_schema["required"])
        allowed = set(payload_schema["properties"].keys())
        emitted = set(payload.keys())
        assert required <= emitted, f"{def_name}: missing required keys {required - emitted}"
        assert emitted <= allowed, f"{def_name}: unexpected keys {emitted - allowed}"
    else:
        # Carry $defs so $ref (e.g. #/$defs/operator_id) resolves during validation.
        jsonschema.validate(
            instance=payload,
            schema={**payload_schema, "$defs": schema["$defs"]},
        )


async def _capture_create_payload() -> dict[str, Any]:
    session = _make_session(**{"INSERT INTO operators": _FakeResult(_operator_row())})
    body = CreateOperatorRequest(
        email="ops@acme.example",
        display_name="Acme Ops",
        tenant_id=TENANT_WIRE,
        is_platform_admin=True,
    )
    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    with _patch_rls(), patch(
        "admin_api.api.operators.audit_emit", side_effect=fake_audit_emit
    ):
        await create_operator(
            body=body, _authz=None, session=session, ctx=SESSION_CTX  # type: ignore[arg-type]
        )
    return audit_calls[0]["payload"]


async def _capture_update_payload() -> dict[str, Any]:
    existing = _operator_row(is_platform_admin=False)
    updated = _operator_row(is_platform_admin=True)
    session = _make_session(
        **{
            "FROM operators WHERE id = :oid": _FakeResult(existing),
            "UPDATE operators SET": _FakeResult(updated),
        }
    )
    body = UpdateOperatorRequest(is_platform_admin=True)
    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    with _patch_rls(), patch(
        "admin_api.api.operators.audit_emit", side_effect=fake_audit_emit
    ):
        await update_operator(
            operator_id=OPERATOR_WIRE,
            body=body,
            _authz=None,
            session=session,  # type: ignore[arg-type]
            ctx=SESSION_CTX,
        )
    return audit_calls[0]["payload"]


async def _capture_delete_payload() -> dict[str, Any]:
    row = _FakeRow(id=str(OPERATOR_UUID), tenant_id=str(TENANT_UUID), status="active")
    session = _make_session(**{"SELECT id, tenant_id, status": _FakeResult(row)})
    audit_calls: list[dict[str, Any]] = []

    async def fake_audit_emit(**kwargs: Any) -> None:
        audit_calls.append(kwargs)

    with _patch_rls(), patch(
        "admin_api.api.operators.audit_emit", side_effect=fake_audit_emit
    ):
        await delete_operator(
            operator_id=OPERATOR_WIRE,
            _authz=None,
            session=session,  # type: ignore[arg-type]
            ctx=SESSION_CTX,
        )
    return audit_calls[0]["payload"]


@pytest.mark.asyncio
async def test_audit_payloads_conform_to_schema() -> None:
    _assert_payload_conforms("ev_operator_created", await _capture_create_payload())
    _assert_payload_conforms("ev_operator_updated", await _capture_update_payload())
    _assert_payload_conforms("ev_operator_deleted", await _capture_delete_payload())
