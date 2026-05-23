"""
Discovery tool tests — proxy_url_pattern reflects canonical and legacy env vars.

Tests:
  - MINTKEY_PROXY_PUBLIC_URL=... → proxy_url_pattern uses canonical value.
  - Legacy MINTKEY_PROXY_URL=... honored when canonical is absent.
  - Legacy KONG_PROXY_URL=... honored when both canonical and first legacy are absent.
  - Trailing slash on canonical env var is stripped.

Source: NET-B; ADR-NETWORK.
"""
from __future__ import annotations

import importlib
import os
import sys
import types
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _fresh_resolver():
    """
    Return freshly-imported resolver module so each test starts with an empty
    _warned set and unpatched os.getenv state.
    """
    mod_name = "mcp_server.config.public_urls"
    if mod_name in sys.modules:
        del sys.modules[mod_name]
    import mcp_server.config.public_urls as m
    return m


# ---------------------------------------------------------------------------
# Unit tests — resolver only (no ASGI stack needed)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("env_vars,expected_proxy", [
    # canonical wins
    (
        {"MINTKEY_PROXY_PUBLIC_URL": "https://proxy.example.com"},
        "https://proxy.example.com",
    ),
    # canonical trailing slash stripped
    (
        {"MINTKEY_PROXY_PUBLIC_URL": "https://proxy.example.com/"},
        "https://proxy.example.com",
    ),
    # legacy MINTKEY_PROXY_URL when canonical absent
    (
        {"MINTKEY_PROXY_URL": "https://legacy-proxy.example.com"},
        "https://legacy-proxy.example.com",
    ),
    # legacy KONG_PROXY_URL when both canonical and MINTKEY_PROXY_URL absent
    (
        {"KONG_PROXY_URL": "http://kong.test:8000"},
        "http://kong.test:8000",
    ),
    # default when all absent
    (
        {},
        "http://localhost:8000",
    ),
])
def test_resolve_proxy_public_url(monkeypatch, env_vars, expected_proxy):
    """resolve_proxy_public_url() returns correct value for each env configuration."""
    # Clear relevant env vars then set the ones under test
    for key in ("MINTKEY_PROXY_PUBLIC_URL", "MINTKEY_PROXY_URL", "KONG_PROXY_URL"):
        monkeypatch.delenv(key, raising=False)
    for key, val in env_vars.items():
        monkeypatch.setenv(key, val)

    resolver = _fresh_resolver()
    assert resolver.resolve_proxy_public_url() == expected_proxy


def test_legacy_proxy_url_warns(monkeypatch, caplog):
    """Using MINTKEY_PROXY_URL emits a WARNING log mentioning the canonical name."""
    import logging

    for key in ("MINTKEY_PROXY_PUBLIC_URL", "MINTKEY_PROXY_URL", "KONG_PROXY_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MINTKEY_PROXY_URL", "http://legacy.example.com")

    resolver = _fresh_resolver()
    with caplog.at_level(logging.WARNING, logger="mcp_server.config.public_urls"):
        resolver.resolve_proxy_public_url()

    assert any(
        "MINTKEY_PROXY_URL" in r.message and "MINTKEY_PROXY_PUBLIC_URL" in r.message
        for r in caplog.records
    ), f"Expected legacy-env-var warning in log records: {[r.message for r in caplog.records]}"


def test_legacy_kong_proxy_url_warns(monkeypatch, caplog):
    """Using KONG_PROXY_URL emits a WARNING log mentioning the canonical name."""
    import logging

    for key in ("MINTKEY_PROXY_PUBLIC_URL", "MINTKEY_PROXY_URL", "KONG_PROXY_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("KONG_PROXY_URL", "http://kong.test:8000")

    resolver = _fresh_resolver()
    with caplog.at_level(logging.WARNING, logger="mcp_server.config.public_urls"):
        resolver.resolve_proxy_public_url()

    assert any(
        "KONG_PROXY_URL" in r.message and "MINTKEY_PROXY_PUBLIC_URL" in r.message
        for r in caplog.records
    ), f"Expected legacy-env-var warning in log records: {[r.message for r in caplog.records]}"


def test_canonical_proxy_does_not_warn(monkeypatch, caplog):
    """Using the canonical MINTKEY_PROXY_PUBLIC_URL emits NO warning."""
    import logging

    for key in ("MINTKEY_PROXY_PUBLIC_URL", "MINTKEY_PROXY_URL", "KONG_PROXY_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("MINTKEY_PROXY_PUBLIC_URL", "https://proxy.example.com")

    resolver = _fresh_resolver()
    with caplog.at_level(logging.WARNING, logger="mcp_server.config.public_urls"):
        resolver.resolve_proxy_public_url()

    assert not caplog.records, (
        f"Unexpected warning when canonical env var is set: {[r.message for r in caplog.records]}"
    )
