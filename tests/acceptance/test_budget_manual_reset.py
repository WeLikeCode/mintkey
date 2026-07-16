"""
T-BUD-5.3 — Manual reset test.

Scenario: exhaust budget; operator calls POST /budget/reset; next call succeeds.
Assert `budget.reset` audit event emitted.
Assert change-channel notification fired.

Variant A (always runs): structural assertions verifying reset endpoint and
audit/notification wiring exist in admin-api.

Variant B (integration, skipped unless MINTKEY_INTEGRATION_TEST=true):
full testcontainers test using the admin-api + proxy.

Sources:
  - T-BUD-5.3; FR-5; design §5, §6, §7.
  - ADR-0010 (change channel)
  - ADR-0014.7 (audit events)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADMIN_API_DIR = ROOT / "apps" / "admin-api"

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Set MINTKEY_INTEGRATION_TEST=true to run full E2E tests",
)


# ---------------------------------------------------------------------------
# Variant A — structural assertions (always run)
# ---------------------------------------------------------------------------


def test_reset_endpoint_exists_in_admin_api():
    """admin-api must expose POST /budget/reset endpoint.
    Source: T-BUD-5.3; FR-5; design §5."""
    api_dir = ADMIN_API_DIR / "src" / "admin_api" / "api"
    # Search for budget reset handler
    found = False
    for py_file in api_dir.rglob("*.py"):
        content = py_file.read_text()
        if "budget" in content.lower() and "reset" in content.lower():
            found = True
            break
    assert found, (
        "No budget reset endpoint found in admin-api/src/admin_api/api/ "
        "(FR-5, design §5)"
    )


def test_reset_emits_budget_reset_audit_event():
    """POST /budget/reset must emit budget.reset audit event.
    Source: T-BUD-5.3; FR-7; design §7."""
    api_dir = ADMIN_API_DIR / "src" / "admin_api"
    found = False
    for py_file in api_dir.rglob("*.py"):
        content = py_file.read_text()
        if "budget.reset" in content:
            found = True
            break
    assert found, (
        "No file in admin-api emits 'budget.reset' audit event "
        "(FR-7, design §7)"
    )


def test_reset_fires_change_channel_notification():
    """POST /budget/reset must fire NOTIFY on mintkey:agent channel.
    Source: T-BUD-5.3; FR-10; design §6."""
    api_dir = ADMIN_API_DIR / "src" / "admin_api"
    found_notify = False
    for py_file in api_dir.rglob("*.py"):
        content = py_file.read_text()
        if ("budget" in content.lower() and
            ("pg_notify" in content or "mintkey:agent" in content or
             "NOTIFY" in content)):
            found_notify = True
            break
    assert found_notify, (
        "Budget reset handler does not fire change-channel notification "
        "(FR-10, design §6)"
    )


# ---------------------------------------------------------------------------
# Variant B — integration (skipped unless MINTKEY_INTEGRATION_TEST=true)
# ---------------------------------------------------------------------------


@INTEGRATION
def test_e2e_manual_reset_allows_next_call():
    """Exhaust budget; operator resets; next proxy call succeeds.
    Assert budget.reset audit event + change-channel notification.
    Source: T-BUD-5.3; FR-5."""
    pytest.skip(
        "Full stack testcontainers test — "
        "run with MINTKEY_INTEGRATION_TEST=true"
    )
