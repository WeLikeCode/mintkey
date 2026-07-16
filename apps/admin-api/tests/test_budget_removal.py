"""
TDD tests for budget removal via PATCH endpoint.

Verifies:
  - PATCH with `{ constraints: { budget: null } }` removes budget from stored constraints.
  - budget_counters rows are cleaned up on removal.
  - Audit event `budget.config_updated` emitted with action: "removed".
  - "budget absent from body" (not sent) leaves existing budget untouched.

These tests are written BEFORE the implementation (Task 1.2) and are expected
to fail until the handler is updated to distinguish "field not sent" vs
"field explicitly set to null" using `model_fields_set`.

Source: requirements 4.2, 4.3; design §5; T-BUD-2.2.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from admin_api.api.permissions import (
    Constraints,
    PermissionPatchRequest,
    update_permission,
)


# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_PERM_DB_ID = str(uuid.uuid4())
_AGENT_WIRE_ID = "agent_" + "0" * 26
_PERM_WIRE_ID = "perm_" + "0" * 26

_EXISTING_BUDGET = {
    "ceiling": 100,
    "period": "daily",
    "alert_thresholds": [50, 80, 100],
}

_EXISTING_CONSTRAINTS = {
    "budget": _EXISTING_BUDGET,
    "rate_limit": {"requests_per_second": 10, "burst": 20},
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session(*, constraints: dict[str, Any] | None = None) -> MagicMock:
    """Build a mock AsyncSession that returns a permission grant row."""
    session = MagicMock()
    session.execute = AsyncMock()

    # Row returned by SELECT permission_grants
    grant_row = MagicMock()
    grant_row.id = _PERM_DB_ID
    grant_row.constraints = constraints if constraints is not None else _EXISTING_CONSTRAINTS
    grant_row.tenant_id = str(_TENANT_ID)

    select_result = MagicMock()
    select_result.fetchone.return_value = grant_row

    # All subsequent execute calls (UPDATE, DELETE, etc.) return empty
    empty_result = MagicMock()
    empty_result.fetchone.return_value = None
    empty_result.fetchall.return_value = []

    # Side effects: first call = SELECT grant, rest = writes
    session.execute.side_effect = [
        select_result,  # SELECT FROM permission_grants
        empty_result,   # UPDATE permission_grants (constraints)
        empty_result,   # DELETE FROM budget_counters (cleanup)
        empty_result,   # INSERT audit_events (via audit_emit)
        empty_result,   # extra buffer
        empty_result,
        empty_result,
    ]

    return session


_COMMON_PATCHES = [
    patch("admin_api.api.permissions.audit_emit", new_callable=AsyncMock),
    patch("admin_api.api.permissions.notify_change", new_callable=AsyncMock),
    patch("admin_api.api.permissions.set_tenant_context", new_callable=AsyncMock),
]


def _apply_patches(fn):
    """Decorator that applies all common patches."""
    for p in reversed(_COMMON_PATCHES):
        fn = p(fn)
    return fn


def _wire_to_db_side_effect(wire_id: str, prefix: str) -> str:
    """Mock wire_to_db_uuid to return a deterministic DB UUID."""
    return _PERM_DB_ID


# ---------------------------------------------------------------------------
# Test 1: PATCH with budget: null removes budget from constraints
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
@patch(
    "admin_api.api.permissions._decode_agent_wire_id",
    return_value=str(uuid.uuid4()),
)
@patch(
    "admin_api.utils.wire_ids.wire_to_db_uuid",
    side_effect=_wire_to_db_side_effect,
)
async def test_patch_budget_null_removes_budget_from_constraints(
    mock_wire_decode: Any,
    mock_agent_decode: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """PATCH with `{constraints: {budget: null}}` must remove budget key from stored constraints.

    Currently the handler uses `model_dump(exclude_none=True)` which silently
    drops budget=None, leaving the existing budget in place. After Task 1.2,
    the handler should detect the explicit null and remove the budget key.

    Validates: Requirement 4.2.
    """
    session = _make_session(constraints=_EXISTING_CONSTRAINTS)

    # Build the PATCH body with budget explicitly set to None
    body = PermissionPatchRequest(constraints=Constraints(budget=None))
    # Explicitly mark 'budget' as set in the model (simulates JSON `{"budget": null}`)
    body.constraints.model_fields_set.add("budget")

    response = await update_permission(
        tenant_id=_TENANT_ID,
        agent_id=_AGENT_WIRE_ID,
        permission_id=_PERM_WIRE_ID,
        body=body,
        session=session,
    )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}"
    )

    # Parse the response body
    resp_body = json.loads(response.body)
    constraints = resp_body.get("constraints", {})

    # After removal, the budget key should NOT be present in the constraints
    assert "budget" not in constraints, (
        f"Budget should have been removed from constraints but got: {constraints}"
    )
    # Other constraints (rate_limit) should still be present
    assert "rate_limit" in constraints, (
        "Non-budget constraints should remain after budget removal"
    )


# ---------------------------------------------------------------------------
# Test 2: budget_counters rows cleaned up on removal
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
@patch(
    "admin_api.api.permissions._decode_agent_wire_id",
    return_value=str(uuid.uuid4()),
)
@patch(
    "admin_api.utils.wire_ids.wire_to_db_uuid",
    side_effect=_wire_to_db_side_effect,
)
async def test_patch_budget_null_cleans_up_budget_counters(
    mock_wire_decode: Any,
    mock_agent_decode: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """When budget is removed via PATCH, budget_counters rows for that permission must be deleted.

    The handler should execute a DELETE FROM budget_counters WHERE permission_id = :pid.

    Validates: Requirement 4.3.
    """
    session = _make_session(constraints=_EXISTING_CONSTRAINTS)

    body = PermissionPatchRequest(constraints=Constraints(budget=None))
    body.constraints.model_fields_set.add("budget")

    response = await update_permission(
        tenant_id=_TENANT_ID,
        agent_id=_AGENT_WIRE_ID,
        permission_id=_PERM_WIRE_ID,
        body=body,
        session=session,
    )

    assert response.status_code == 200

    # Find a DELETE FROM budget_counters statement in execute() calls
    delete_found = False
    for call_obj in session.execute.call_args_list:
        args = call_obj.args
        if args and hasattr(args[0], "text"):
            sql = str(args[0])
            if "DELETE" in sql.upper() and "budget_counters" in sql:
                # Verify it targets the correct permission_id
                params = args[1] if len(args) > 1 else {}
                assert params.get("pid") == _PERM_DB_ID, (
                    f"DELETE budget_counters should target pid={_PERM_DB_ID}, got {params}"
                )
                delete_found = True
                break

    assert delete_found, (
        "Expected DELETE FROM budget_counters when budget is removed. "
        f"SQL calls: {[str(c.args[0]) for c in session.execute.call_args_list if c.args and hasattr(c.args[0], 'text')]}"
    )


# ---------------------------------------------------------------------------
# Test 3: audit event emitted with action: "removed"
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
@patch(
    "admin_api.api.permissions._decode_agent_wire_id",
    return_value=str(uuid.uuid4()),
)
@patch(
    "admin_api.utils.wire_ids.wire_to_db_uuid",
    side_effect=_wire_to_db_side_effect,
)
async def test_patch_budget_null_emits_audit_event_with_removed_action(
    mock_wire_decode: Any,
    mock_agent_decode: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """When budget is removed, audit_emit must be called with event_type=budget.config_updated
    and payload containing action: "removed".

    Validates: Requirement 4.3 (audit trail for removal).
    """
    session = _make_session(constraints=_EXISTING_CONSTRAINTS)

    body = PermissionPatchRequest(constraints=Constraints(budget=None))
    body.constraints.model_fields_set.add("budget")

    response = await update_permission(
        tenant_id=_TENANT_ID,
        agent_id=_AGENT_WIRE_ID,
        permission_id=_PERM_WIRE_ID,
        body=body,
        session=session,
    )

    assert response.status_code == 200

    # audit_emit should have been called
    mock_audit.assert_awaited_once()

    # Check the audit call args
    audit_kwargs = mock_audit.call_args.kwargs
    assert audit_kwargs["event_type"] == "budget.config_updated", (
        f"Expected event_type='budget.config_updated', got '{audit_kwargs['event_type']}'"
    )
    assert audit_kwargs["tenant_id"] == _TENANT_ID

    # Payload must contain action: "removed"
    payload = audit_kwargs["payload"]
    assert payload.get("action") == "removed", (
        f"Expected payload.action='removed', got: {payload}"
    )
    # Payload should include old budget info for audit trail
    assert payload.get("old_ceiling") == _EXISTING_BUDGET["ceiling"], (
        f"Expected old_ceiling={_EXISTING_BUDGET['ceiling']}, got: {payload}"
    )


# ---------------------------------------------------------------------------
# Test 4: budget absent from body leaves existing budget untouched
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
@patch(
    "admin_api.api.permissions._decode_agent_wire_id",
    return_value=str(uuid.uuid4()),
)
@patch(
    "admin_api.utils.wire_ids.wire_to_db_uuid",
    side_effect=_wire_to_db_side_effect,
)
async def test_patch_without_budget_field_leaves_existing_budget(
    mock_wire_decode: Any,
    mock_agent_decode: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """PATCH with body that does NOT include budget key should NOT modify existing budget.

    When the body is `{constraints: {rate_limit: {...}}}` (budget not mentioned),
    the stored budget should remain untouched.

    Validates: Requirement 4.2 (distinguish "not sent" from "sent as null").
    """
    session = _make_session(constraints=_EXISTING_CONSTRAINTS)

    # Construct body WITHOUT budget field — only rate_limit
    from admin_api.api.permissions import RateLimitConstraint

    body = PermissionPatchRequest(
        constraints=Constraints(
            rate_limit=RateLimitConstraint(requests_per_second=20, burst=40)
        )
    )
    # budget is NOT in model_fields_set (it was never sent in the JSON)
    assert "budget" not in body.constraints.model_fields_set

    response = await update_permission(
        tenant_id=_TENANT_ID,
        agent_id=_AGENT_WIRE_ID,
        permission_id=_PERM_WIRE_ID,
        body=body,
        session=session,
    )

    assert response.status_code == 200

    resp_body = json.loads(response.body)
    constraints = resp_body.get("constraints", {})

    # The existing budget should still be there
    assert "budget" in constraints, (
        f"Existing budget should be preserved when not mentioned in PATCH body. "
        f"Got constraints: {constraints}"
    )
    assert constraints["budget"]["ceiling"] == _EXISTING_BUDGET["ceiling"], (
        f"Budget ceiling should be unchanged. Got: {constraints['budget']}"
    )
    assert constraints["budget"]["period"] == _EXISTING_BUDGET["period"], (
        f"Budget period should be unchanged. Got: {constraints['budget']}"
    )
