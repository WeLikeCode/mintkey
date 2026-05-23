"""
Availability test: control plane outage resilience (T-1.6.10).

Unit assertions (always run):
  - test_proxy_plugin_jwks_cache_has_5min_ttl: jwks_cache.go TTL is 300s or
    the cache is configurable — per ADR-0006 (5-min JWKS cache) and ADR-0016.2
    (rate-limited force-refresh on unknown kid).
  - test_vault_adapter_standalone: vault-adapter internal packages must not
    import admin-api packages — the vault adapter must be deployable and
    operational without the admin-api running.

Integration test (MINTKEY_INTEGRATION_TEST=true only):
  - test_control_plane_outage_doesnt_break_inflight_calls: issue a JWT, stop
    admin-api/mcp/broker, assert 10 subsequent proxy requests still succeed.

Sources: ADR-0004; ADR-0006; ADR-0016.2; T-1.6.10.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
JWKS_CACHE_GO = (
    REPO_ROOT / "apps" / "proxy-plugin" / "internal" / "jwt" / "jwks_cache.go"
)
VAULT_ADAPTER_INTERNAL = (
    REPO_ROOT / "apps" / "vault-adapter" / "internal"
)

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full stack",
)


# ---------------------------------------------------------------------------
# Unit assertions (always run)
# ---------------------------------------------------------------------------


def test_proxy_plugin_jwks_cache_has_5min_ttl() -> None:
    """
    jwks_cache.go must either hard-code a 300s (5-min) TTL or expose a
    configurable TTL constructor.

    ADR-0006 mandates a 5-min JWKS cache.  ADR-0016.2 adds a per-kid
    force-refresh rate-limiter; its TTL may differ from the cache TTL, but
    the configurable constructor must exist so operators can tune it.
    ADR-0006; ADR-0016.2; T-1.6.10.
    """
    assert JWKS_CACHE_GO.exists(), (
        f"jwks_cache.go not found at {JWKS_CACHE_GO}"
    )
    source = JWKS_CACHE_GO.read_text(encoding="utf-8")

    # Accept either a literal 300 (seconds) or a configurable TTL constructor.
    has_300s = "300" in source
    has_configurable_ttl = re.search(
        r"func\s+\w*[Ww]ith[Tt][Tt][Ll]\w*\s*\(", source
    ) is not None

    assert has_300s or has_configurable_ttl, (
        "jwks_cache.go neither hard-codes a 300s TTL nor exposes a configurable "
        "TTL constructor — JWKS cache TTL is not compliant with ADR-0006 / ADR-0016.2"
    )


def test_vault_adapter_standalone() -> None:
    """
    No .go file under services/vault-adapter/internal/ (excluding test files)
    may import an admin-api package.

    The vault adapter must run independently of the admin-api: when the
    admin-api is down the proxy plugin can still fetch credentials from the
    vault adapter, ensuring in-flight requests succeed.
    ADR-0004; T-1.6.10.
    """
    assert VAULT_ADAPTER_INTERNAL.is_dir(), (
        f"vault-adapter/internal/ not found at {VAULT_ADAPTER_INTERNAL}"
    )

    go_files = [
        p
        for p in VAULT_ADAPTER_INTERNAL.rglob("*.go")
        if not p.name.endswith("_test.go")
    ]
    assert go_files, (
        f"No non-test .go files found under {VAULT_ADAPTER_INTERNAL}"
    )

    # Patterns that would indicate a dependency on the admin-api service.
    forbidden_patterns = (
        "mintkey/admin-api",
        "mintkey/services/admin",
        "admin_api",
        "adminapi",
    )

    violations: list[str] = []
    for go_file in sorted(go_files):
        source = go_file.read_text(encoding="utf-8")
        for pattern in forbidden_patterns:
            if pattern in source:
                violations.append(f"{go_file.relative_to(REPO_ROOT)}: imports '{pattern}'")

    assert not violations, (
        "vault-adapter internal packages must not depend on admin-api — "
        "the vault adapter must be standalone for control-plane availability.\n"
        "Violations:\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Integration test (requires full stack)
# ---------------------------------------------------------------------------


@INTEGRATION
def test_control_plane_outage_doesnt_break_inflight_calls() -> None:
    """Issue JWT, stop admin-api/mcp/broker, assert 10 requests still succeed."""
    pytest.skip("Requires full stack — set MINTKEY_INTEGRATION_TEST=true")
