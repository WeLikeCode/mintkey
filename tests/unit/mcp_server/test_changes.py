"""
Unit tests: MCP Server change channel subscriber (T-1.5.6).

Tests:
  1. test_service_change_invalidates_discovery_cache
     mock payload {"event_type": "service.registered", "tenant_id": "tenant_01ABC"}
     → discovery cache invalidated for that tenant.
  2. test_agent_revoked_adds_to_revoked_set
     mock payload {"event_type": "agent.revoked", "agent_id": "agent_01DEF",
                   "tenant_id": "tenant_01ABC"}
     → agent_id present in revoked_agents set.
  3. test_discovery_cache_ttl
     set a value, advance time past TTL, get returns None.
  4. test_discovery_cache_invalidate_tenant
     set values for two tenants, invalidate one, other remains.

Sources: ADR-0014.1 (global channels); T-1.5.6 (subscriber spec).
"""
from __future__ import annotations

import json
import sys
import os
import time
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
MCP_SERVER_SRC = os.path.join(REPO_ROOT, "mcp-server", "src")
if MCP_SERVER_SRC not in sys.path:
    sys.path.insert(0, MCP_SERVER_SRC)

from mcp_server.cache.discovery import DiscoveryCache
from mcp_server.changes.subscriber import ChangeSubscriber

TENANT_A = "tenant_01AAAAAAAAAAAAAAAAAAAAAAAAA"
TENANT_B = "tenant_01BBBBBBBBBBBBBBBBBBBBBBBBB"
AGENT_ID = "agent_01DEFDEFDEFDEFDEFDEFDEFDEF"


# ---------------------------------------------------------------------------
# DiscoveryCache tests
# ---------------------------------------------------------------------------


def test_discovery_cache_set_and_get() -> None:
    """set then get returns the stored value within TTL."""
    cache = DiscoveryCache(ttl_seconds=300)
    value = [{"id": "svc_1", "name": "openai"}]
    cache.set(TENANT_A, AGENT_ID, value)
    assert cache.get(TENANT_A, AGENT_ID) == value


def test_discovery_cache_ttl() -> None:
    """get returns None after TTL has elapsed (time.monotonic advanced past TTL)."""
    cache = DiscoveryCache(ttl_seconds=60)
    value = [{"id": "svc_1"}]
    cache.set(TENANT_A, AGENT_ID, value)

    # Advance monotonic clock past TTL
    with patch("mcp_server.cache.discovery.time") as mock_time:
        mock_time.monotonic.return_value = time.monotonic() + 61
        result = cache.get(TENANT_A, AGENT_ID)

    assert result is None


def test_discovery_cache_invalidate_tenant() -> None:
    """invalidate(tenant_A) removes only tenant_A entries; tenant_B entries survive."""
    cache = DiscoveryCache(ttl_seconds=300)
    value_a = [{"id": "svc_a"}]
    value_b = [{"id": "svc_b"}]

    cache.set(TENANT_A, AGENT_ID, value_a)
    cache.set(TENANT_B, AGENT_ID, value_b)

    cache.invalidate(TENANT_A)

    assert cache.get(TENANT_A, AGENT_ID) is None
    assert cache.get(TENANT_B, AGENT_ID) == value_b


def test_discovery_cache_get_missing_returns_none() -> None:
    """get on an empty cache returns None."""
    cache = DiscoveryCache(ttl_seconds=300)
    assert cache.get(TENANT_A, AGENT_ID) is None


# ---------------------------------------------------------------------------
# ChangeSubscriber callback tests
# ---------------------------------------------------------------------------


def test_service_change_invalidates_discovery_cache() -> None:
    """
    _on_service_change with a service.registered payload calls
    discovery_cache.invalidate(tenant_id) — ADR-0014.1; T-1.5.6.
    """
    mock_cache = MagicMock()
    revoked: set = set()
    subscriber = ChangeSubscriber(
        dsn="postgresql://unused/unused",
        discovery_cache=mock_cache,
        revoked_agents=revoked,
    )

    payload = json.dumps({"event_type": "service.registered", "tenant_id": TENANT_A})
    subscriber._on_service_change(conn=None, pid=1234, channel="mintkey:service", payload=payload)

    mock_cache.invalidate.assert_called_once_with(TENANT_A)


def test_service_change_bad_json_does_not_raise() -> None:
    """_on_service_change with malformed JSON logs and returns without raising."""
    mock_cache = MagicMock()
    subscriber = ChangeSubscriber(
        dsn="postgresql://unused/unused",
        discovery_cache=mock_cache,
        revoked_agents=set(),
    )
    # Must not raise
    subscriber._on_service_change(conn=None, pid=1234, channel="mintkey:service", payload="{bad}")
    mock_cache.invalidate.assert_not_called()


def test_agent_revoked_adds_to_revoked_set() -> None:
    """
    _on_agent_change with event_type=agent.revoked adds agent_id to
    revoked_agents — T-1.5.6.
    """
    mock_cache = MagicMock()
    revoked: set = set()
    subscriber = ChangeSubscriber(
        dsn="postgresql://unused/unused",
        discovery_cache=mock_cache,
        revoked_agents=revoked,
    )

    payload = json.dumps(
        {
            "event_type": "agent.revoked",
            "agent_id": AGENT_ID,
            "tenant_id": TENANT_A,
        }
    )
    subscriber._on_agent_change(conn=None, pid=1234, channel="mintkey:agent", payload=payload)

    assert AGENT_ID in revoked


def test_agent_non_revoked_event_ignored() -> None:
    """_on_agent_change with event_type != agent.revoked does NOT touch revoked_agents."""
    mock_cache = MagicMock()
    revoked: set = set()
    subscriber = ChangeSubscriber(
        dsn="postgresql://unused/unused",
        discovery_cache=mock_cache,
        revoked_agents=revoked,
    )

    payload = json.dumps(
        {
            "event_type": "agent.updated",
            "agent_id": AGENT_ID,
            "tenant_id": TENANT_A,
        }
    )
    subscriber._on_agent_change(conn=None, pid=1234, channel="mintkey:agent", payload=payload)

    assert AGENT_ID not in revoked


def test_agent_change_bad_json_does_not_raise() -> None:
    """_on_agent_change with malformed JSON logs and returns without raising."""
    subscriber = ChangeSubscriber(
        dsn="postgresql://unused/unused",
        discovery_cache=MagicMock(),
        revoked_agents=set(),
    )
    subscriber._on_agent_change(conn=None, pid=1234, channel="mintkey:agent", payload="{bad}")
