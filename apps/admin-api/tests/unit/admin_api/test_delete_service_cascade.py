"""
Unit tests for transactional cascade delete in delete_service.

Verifies that DELETE /v1/tenants/{tid}/services/{sid} (handler: delete_service)
performs in-app transactional cascade before deleting the service row, and emits
the correct audit events.

Test cases:
  1. test_delete_service_cascades_credentials
       → credentials rows are deleted; service.credentials.cascade_deleted event emitted
         with correct service_id and count.
  2. test_delete_service_cascades_permission_grants
       → permission_grants rows deleted; service.permission_grants.cascade_deleted event
         emitted with correct service_id and count.
  3. test_delete_service_cascades_service_api_keys
       → service_api_keys rows deleted; service.api_keys.cascade_deleted event emitted
         with correct service_id and count.
  4. test_delete_service_cascade_all_atomic
       → All three child tables + service deleted in one session; all four audit events
         present and service.deleted appears AFTER the three cascade events.
  5. test_delete_nonexistent_service_returns_204
       → Handler returns 204 even when no rows are deleted (graceful empty cascade).

Source: Option-A cascade decision; ADR-0008; ADR-0014.7.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from admin_api.api.services import delete_service

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_SERVICE_ID_WIRE = "svc_01TEST0000000000000000000"
_DB_UUID = "11111111-2222-3333-4444-555555555555"

# ---------------------------------------------------------------------------
# Common patches applied to all tests
# ---------------------------------------------------------------------------

_COMMON_PATCHES = [
    patch("admin_api.api.services.audit_emit", new_callable=AsyncMock),
    patch("admin_api.api.services.notify_change", new_callable=AsyncMock),
    patch("admin_api.api.services.set_tenant_context", new_callable=AsyncMock),
    patch("admin_api.api.services.require_tenant_session"),
    patch(
        "admin_api.api.services._wire_id_to_db_uuid",
        side_effect=lambda x: _DB_UUID,
    ),
]


def _apply_patches(fn: Any) -> Any:
    """Decorator that applies all common patches in reverse order."""
    for p in reversed(_COMMON_PATCHES):
        fn = p(fn)
    return fn


# ---------------------------------------------------------------------------
# Session factory helpers
# ---------------------------------------------------------------------------


def _rows(n: int) -> list[MagicMock]:
    """Return n distinct MagicMock rows (used for RETURNING id result)."""
    return [MagicMock() for _ in range(n)]


def _execute_result(rows: list[MagicMock]) -> MagicMock:
    """Build a mock execute() result whose fetchall() returns `rows`."""
    r = MagicMock()
    r.fetchall.return_value = rows
    return r


def _empty_result() -> MagicMock:
    r = MagicMock()
    r.fetchall.return_value = []
    return r


def _make_session(
    sak_count: int = 0,
    pg_count: int = 0,
    cred_count: int = 0,
) -> MagicMock:
    """
    Build a mock AsyncSession whose execute() side-effects match the cascade
    order in delete_service:

      1. DELETE service_api_keys RETURNING id       → sak_count rows
      2. DELETE permission_grants RETURNING id       → pg_count rows
      3. DELETE credentials RETURNING id             → cred_count rows
      4. DELETE services                             → empty (no RETURNING)
    """
    session = MagicMock()
    session.execute = AsyncMock(
        side_effect=[
            _execute_result(_rows(sak_count)),    # service_api_keys
            _execute_result(_rows(pg_count)),     # permission_grants
            _execute_result(_rows(cred_count)),   # credentials
            _empty_result(),                       # services
        ]
    )
    return session


# ---------------------------------------------------------------------------
# Test 1: credentials cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_delete_service_cascades_credentials(
    mock_wire_to_db: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """DELETE emits service.credentials.cascade_deleted with correct count."""
    n = 3
    session = _make_session(cred_count=n)

    response = await delete_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID_WIRE,
        session=session,
        _authz=None,
    )

    assert response.status_code == 204

    # Find the cascade event for credentials
    audit_calls = [c.kwargs for c in mock_audit.call_args_list]
    cred_events = [
        c for c in audit_calls
        if c.get("event_type") == "service.credentials.cascade_deleted"
    ]
    assert len(cred_events) == 1, (
        f"Expected exactly 1 service.credentials.cascade_deleted event, "
        f"got {len(cred_events)}. All events: {[c.get('event_type') for c in audit_calls]}"
    )
    ev = cred_events[0]
    assert ev["payload"]["service_id"] == _SERVICE_ID_WIRE
    assert ev["payload"]["count"] == n


# ---------------------------------------------------------------------------
# Test 2: permission_grants cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_delete_service_cascades_permission_grants(
    mock_wire_to_db: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """DELETE emits service.permission_grants.cascade_deleted with correct count."""
    n = 5
    session = _make_session(pg_count=n)

    response = await delete_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID_WIRE,
        session=session,
        _authz=None,
    )

    assert response.status_code == 204

    audit_calls = [c.kwargs for c in mock_audit.call_args_list]
    pg_events = [
        c for c in audit_calls
        if c.get("event_type") == "service.permission_grants.cascade_deleted"
    ]
    assert len(pg_events) == 1, (
        f"Expected exactly 1 service.permission_grants.cascade_deleted event, "
        f"got {len(pg_events)}. All events: {[c.get('event_type') for c in audit_calls]}"
    )
    ev = pg_events[0]
    assert ev["payload"]["service_id"] == _SERVICE_ID_WIRE
    assert ev["payload"]["count"] == n


# ---------------------------------------------------------------------------
# Test 3: service_api_keys cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_delete_service_cascades_service_api_keys(
    mock_wire_to_db: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """DELETE emits service.api_keys.cascade_deleted with correct count."""
    n = 2
    session = _make_session(sak_count=n)

    response = await delete_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID_WIRE,
        session=session,
        _authz=None,
    )

    assert response.status_code == 204

    audit_calls = [c.kwargs for c in mock_audit.call_args_list]
    sak_events = [
        c for c in audit_calls
        if c.get("event_type") == "service.api_keys.cascade_deleted"
    ]
    assert len(sak_events) == 1, (
        f"Expected exactly 1 service.api_keys.cascade_deleted event, "
        f"got {len(sak_events)}. All events: {[c.get('event_type') for c in audit_calls]}"
    )
    ev = sak_events[0]
    assert ev["payload"]["service_id"] == _SERVICE_ID_WIRE
    assert ev["payload"]["count"] == n


# ---------------------------------------------------------------------------
# Test 4: all-child + ordering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_delete_service_cascade_all_atomic(
    mock_wire_to_db: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """
    All three child tables are deleted and all four audit events are emitted
    with service.deleted appearing AFTER the three cascade events.
    """
    session = _make_session(sak_count=2, pg_count=4, cred_count=3)

    response = await delete_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID_WIRE,
        session=session,
        _authz=None,
    )

    assert response.status_code == 204

    audit_calls = [c.kwargs for c in mock_audit.call_args_list]
    event_types_ordered = [c["event_type"] for c in audit_calls]

    # All four events present
    assert "service.api_keys.cascade_deleted" in event_types_ordered
    assert "service.permission_grants.cascade_deleted" in event_types_ordered
    assert "service.credentials.cascade_deleted" in event_types_ordered
    assert "service.deleted" in event_types_ordered

    # service.deleted must be the LAST audit event (ordering matters for replay)
    assert event_types_ordered[-1] == "service.deleted", (
        f"service.deleted must be last; got order: {event_types_ordered}"
    )

    # Cascade events precede service.deleted
    deleted_idx = event_types_ordered.index("service.deleted")
    for cascade_type in (
        "service.api_keys.cascade_deleted",
        "service.permission_grants.cascade_deleted",
        "service.credentials.cascade_deleted",
    ):
        cascade_idx = event_types_ordered.index(cascade_type)
        assert cascade_idx < deleted_idx, (
            f"{cascade_type} must come before service.deleted; "
            f"got order: {event_types_ordered}"
        )

    # Counts
    sak_ev = next(c for c in audit_calls if c["event_type"] == "service.api_keys.cascade_deleted")
    pg_ev = next(c for c in audit_calls if c["event_type"] == "service.permission_grants.cascade_deleted")
    cred_ev = next(c for c in audit_calls if c["event_type"] == "service.credentials.cascade_deleted")

    assert sak_ev["payload"]["count"] == 2
    assert pg_ev["payload"]["count"] == 4
    assert cred_ev["payload"]["count"] == 3

    # Verify the DELETEs were issued in the correct cascade order by checking
    # that all four execute calls were made.
    assert session.execute.call_count == 4, (
        f"Expected 4 execute() calls (3 child deletes + 1 service delete), "
        f"got {session.execute.call_count}"
    )

    # Verify tenant_id is pinned in every child DELETE (defence-in-depth)
    for i, c in enumerate(session.execute.call_args_list):
        params = c.args[1] if len(c.args) > 1 else {}
        assert params.get("tid") == str(_TENANT_ID), (
            f"execute() call #{i} missing tenant_id pin; params={params}"
        )


# ---------------------------------------------------------------------------
# Test 5: nonexistent service → 204 (graceful empty cascade)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_delete_nonexistent_service_returns_204(
    mock_wire_to_db: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """
    DELETE on a service_id that does not exist (all child deletes return 0 rows,
    parent DELETE is a no-op) still returns 204 — idempotent hard-delete.
    """
    session = _make_session(sak_count=0, pg_count=0, cred_count=0)

    response = await delete_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID_WIRE,
        session=session,
        _authz=None,
    )

    assert response.status_code == 204

    # All cascade events emitted even when count=0 (idempotent)
    audit_calls = [c.kwargs for c in mock_audit.call_args_list]
    event_types = {c["event_type"] for c in audit_calls}
    assert "service.api_keys.cascade_deleted" in event_types
    assert "service.permission_grants.cascade_deleted" in event_types
    assert "service.credentials.cascade_deleted" in event_types
    assert "service.deleted" in event_types

    # All counts are 0
    for c in audit_calls:
        if c["event_type"].endswith(".cascade_deleted"):
            assert c["payload"]["count"] == 0, (
                f"{c['event_type']} expected count=0 for nonexistent service, "
                f"got count={c['payload']['count']}"
            )
