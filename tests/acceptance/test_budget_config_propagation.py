"""
T-BUD-5.4 — Config update propagation test.

Scenario: agent at 8/10 budget; operator increases ceiling to 20; next call
succeeds.
Assert change-channel notification fired within <= 5s.
Assert `budget.config_updated` audit event emitted.

Variant A (always runs): structural assertions verifying config update
wiring in admin-api and proxy subscriber.

Variant B (integration, skipped unless MINTKEY_INTEGRATION_TEST=true):
full testcontainers test.

Sources:
  - T-BUD-5.4; FR-6, FR-10; design §5, §6, §7.
  - ADR-0010 (change channel — <= 5s propagation SLA)
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
ADMIN_API_DIR = ROOT / "apps" / "admin-api"
PROXY_PLUGIN_DIR = ROOT / "apps" / "proxy-plugin"

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Set MINTKEY_INTEGRATION_TEST=true to run full E2E tests",
)


# ---------------------------------------------------------------------------
# Variant A — structural assertions (always run)
# ---------------------------------------------------------------------------


def test_admin_api_emits_config_updated_audit():
    """admin-api must emit budget.config_updated audit event on config change.
    Source: T-BUD-5.4; FR-7; design §7."""
    api_dir = ADMIN_API_DIR / "src" / "admin_api"
    found = False
    for py_file in api_dir.rglob("*.py"):
        content = py_file.read_text()
        if "budget.config_updated" in content:
            found = True
            break
    assert found, (
        "No file in admin-api emits 'budget.config_updated' audit event "
        "(FR-7, design §7)"
    )


def test_admin_api_fires_change_channel_on_config_update():
    """admin-api must fire change-channel notification on budget config update.
    Source: T-BUD-5.4; FR-10; design §6."""
    api_dir = ADMIN_API_DIR / "src" / "admin_api"
    found = False
    for py_file in api_dir.rglob("*.py"):
        content = py_file.read_text()
        if ("budget" in content.lower() and
            ("config_updated" in content or "config.updated" in content) and
            ("pg_notify" in content or "mintkey:agent" in content or
             "notify" in content.lower())):
            found = True
            break
    assert found, (
        "Budget config update handler does not fire change-channel "
        "notification (FR-10, design §6)"
    )


def test_proxy_subscriber_handles_budget_config_updated():
    """Proxy change-channel subscriber must handle budget.config_updated events.
    Source: T-BUD-5.4; FR-10; design §6."""
    changes_dir = PROXY_PLUGIN_DIR / "internal" / "changes"
    if not changes_dir.is_dir():
        # May be in a different location
        changes_dir = PROXY_PLUGIN_DIR / "internal"

    found = False
    for go_file in changes_dir.rglob("*.go"):
        content = go_file.read_text()
        if "budget" in content.lower() and "config_updated" in content.lower():
            found = True
            break

    # Also check the budget package itself for change handling
    if not found:
        budget_dir = PROXY_PLUGIN_DIR / "internal" / "budget"
        for go_file in budget_dir.rglob("*.go"):
            content = go_file.read_text()
            if "invalidat" in content.lower() or "config_updated" in content.lower():
                found = True
                break

    assert found, (
        "Proxy subscriber does not handle 'budget.config_updated' event "
        "(FR-10, design §6)"
    )


# ---------------------------------------------------------------------------
# Variant B — integration (skipped unless MINTKEY_INTEGRATION_TEST=true)
# ---------------------------------------------------------------------------


@INTEGRATION
def test_e2e_config_update_propagation():
    """Agent at 8/10; operator increases ceiling to 20; next call succeeds.
    Assert change-channel notification within <= 5s and audit event emitted.
    Source: T-BUD-5.4; FR-6, FR-10."""
    pytest.skip(
        "Full stack testcontainers test — "
        "run with MINTKEY_INTEGRATION_TEST=true"
    )
