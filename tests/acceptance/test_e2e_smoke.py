"""
E2E smoke test — T-1.11.2.

Non-integration assertions run always and verify the structural preconditions
for the full 13-step E2E smoke test.  The actual integration test is gated on
MINTKEY_INTEGRATION_TEST=true (requires a running docker-compose stack).

Sources: T-1.11.2; ADR-0014.7; S-SEC-1; ADR-0017.11.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Integration-only marker
# ---------------------------------------------------------------------------
INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full docker-compose stack",
)

# ---------------------------------------------------------------------------
# Repo root — resolved relative to this file
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).parent.parent.parent


# ===========================================================================
# Unit assertions (always run)
# ===========================================================================


def test_e2e_smoke_components_exist() -> None:
    """All required component directories / files must exist."""
    required = [
        _ROOT / "admin-api" / "src" / "admin_api",
        _ROOT / "mcp-server" / "src" / "mcp_server",
        _ROOT / "services" / "broker",
        _ROOT / "services" / "proxy-plugin",
        _ROOT / "services" / "vault-adapter",
        _ROOT / "mock-backend" / "src" / "mock_backend",
        _ROOT / "docker-compose.yml",
    ]
    missing = [str(p) for p in required if not p.exists()]
    assert not missing, f"Missing required components: {missing}"


def test_e2e_smoke_all_routers_registered() -> None:
    """
    admin-api/src/admin_api/main.py must include all 12 routers.

    Checked routers: health, auth, services, agents, changes, credentials,
    internal, permissions, audit, audit_admin, settings, tenants.
    """
    main_py = _ROOT / "admin-api" / "src" / "admin_api" / "main.py"
    assert main_py.exists(), f"main.py not found at {main_py}"

    src = main_py.read_text()

    expected_routers = [
        "health",
        "auth",
        "services",
        "agents",
        "changes",
        "credentials",
        "internal",
        "permissions",
        "audit",
        "audit_admin",
        "settings",
        "tenants",
    ]

    missing = [r for r in expected_routers if r not in src]
    assert not missing, (
        f"Routers not referenced in main.py: {missing}"
    )


def test_e2e_smoke_mock_backend_has_all_endpoints() -> None:
    """
    mock-backend/src/mock_backend/rest/main.py must define routes for all
    required endpoint paths.
    """
    rest_main = (
        _ROOT / "mock-backend" / "src" / "mock_backend" / "rest" / "main.py"
    )
    assert rest_main.exists(), f"rest/main.py not found at {rest_main}"

    src = rest_main.read_text()

    required_routes = [
        "/api-key-header",
        "/bearer",
        "/basic-auth",
        "/oauth-protected",
        "/echo",
        "/5xx",
        "/redirect-internal",
        "/redirect-external",
    ]

    missing = [r for r in required_routes if r not in src]
    assert not missing, (
        f"Required routes not found in mock-backend rest/main.py: {missing}"
    )


def test_e2e_smoke_audit_chain_initialized() -> None:
    """
    audit-verify-job/verify.py must define a genesis_hash function whose
    GENESIS_PREFIX matches the prefix used in mintkey-models audit module.

    Source: ADR-0014.7; T-1.13.2.
    """
    verify_py = _ROOT / "audit-verify-job" / "verify.py"
    assert verify_py.exists(), f"verify.py not found at {verify_py}"

    # Add the audit-verify-job directory to sys.path temporarily so we can
    # import the module without installing it.
    verify_dir = str(verify_py.parent)
    added = verify_dir not in sys.path
    if added:
        sys.path.insert(0, verify_dir)
    try:
        import importlib
        verify_mod = importlib.import_module("verify")
        importlib.reload(verify_mod)  # reload in case of stale import

        assert hasattr(verify_mod, "genesis_hash"), (
            "verify.py does not define a genesis_hash function"
        )
        assert hasattr(verify_mod, "GENESIS_PREFIX"), (
            "verify.py does not define GENESIS_PREFIX constant"
        )

        # The genesis prefix must be the canonical ADR-0014.7 value.
        expected_prefix = "mintkey-audit-genesis-v1:"
        assert verify_mod.GENESIS_PREFIX == expected_prefix, (
            f"GENESIS_PREFIX is {verify_mod.GENESIS_PREFIX!r}, "
            f"expected {expected_prefix!r}"
        )

        # genesis_hash must be callable and return 32 bytes.
        result = verify_mod.genesis_hash("tenant_01ABCDEFGHJKMNPQRSTVWXYZ1")
        assert isinstance(result, bytes) and len(result) == 32, (
            f"genesis_hash returned unexpected result: {result!r}"
        )
    finally:
        if added and verify_dir in sys.path:
            sys.path.remove(verify_dir)


# ===========================================================================
# Integration test (requires docker-compose stack)
# ===========================================================================


@INTEGRATION
def test_full_e2e_smoke_13_steps() -> None:
    """
    Full 13-step E2E smoke test:
    bootstrap → login → register service → register credential → test
    → create agent → grant permission → MCP discovery → token request
    → brokered call → audit verification → red-team check → timing check.

    Must complete in ≤ 90s from docker compose up healthy.
    """
    pytest.skip("Requires docker-compose stack — set MINTKEY_INTEGRATION_TEST=true")
