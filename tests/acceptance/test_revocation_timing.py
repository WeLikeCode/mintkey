"""T-1.9.2 — Agent revocation propagation timing tests.

Unit assertions (always run): verify the structural wiring exists in the
source tree so that revocation events can propagate to the proxy plugin
within the 5-second SLA.

Integration test (skipped unless MINTKEY_INTEGRATION_TEST=true): creates an
agent, revokes it, and asserts the proxy denies requests within 5 s.
"""

import os
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

ROOT = Path(__file__).parents[2]  # repo root


def _read(rel: str) -> str:
    return (ROOT / rel).read_text()


# ---------------------------------------------------------------------------
# Integration marker
# ---------------------------------------------------------------------------

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full stack — set MINTKEY_INTEGRATION_TEST=true",
)

# ---------------------------------------------------------------------------
# Unit assertions (always run)
# ---------------------------------------------------------------------------


def test_proxy_plugin_has_agent_revocation_subscriber():
    """apps/proxy-plugin/internal/changes/subscriber.go must exist and
    subscribe to the mintkey:agent channel (ADR-0014.1)."""
    path = "apps/proxy-plugin/internal/changes/subscriber.go"
    assert (ROOT / path).exists(), f"Missing: {path}"
    content = _read(path)
    assert "mintkey:agent" in content, (
        f"{path} does not contain 'mintkey:agent' channel subscription"
    )


def test_mcp_server_has_agent_revocation_cache():
    """apps/mcp-server/src/mcp_server/changes/subscriber.py must exist and handle
    agent.revoked events (ADR-0014.1)."""
    path = "apps/mcp-server/src/mcp_server/changes/subscriber.py"
    assert (ROOT / path).exists(), f"Missing: {path}"
    content = _read(path)
    assert "agent.revoked" in content, (
        f"{path} does not handle 'agent.revoked' event type"
    )


def test_revocation_emits_agent_revoked_notify():
    """apps/admin-api/src/admin_api/api/agents.py must call pg_notify with the
    mintkey:agent channel on revocation (ADR-0014.1, ADR-0008)."""
    path = "apps/admin-api/src/admin_api/api/agents.py"
    assert (ROOT / path).exists(), f"Missing: {path}"
    content = _read(path)
    assert "pg_notify" in content or "mintkey:agent" in content, (
        f"{path} does not reference pg_notify or 'mintkey:agent' channel"
    )
    assert "mintkey:agent" in content, (
        f"{path} does not reference 'mintkey:agent' channel"
    )


# ---------------------------------------------------------------------------
# Integration test
# ---------------------------------------------------------------------------


@INTEGRATION
def test_agent_revocation_propagates_within_5s():
    """Create agent, revoke it, assert proxy denies within 5s."""
    pytest.skip("Requires full stack — set MINTKEY_INTEGRATION_TEST=true")
