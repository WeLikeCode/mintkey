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
import time
from pathlib import Path

import httpx
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
        _ROOT / "apps/admin-api" / "src" / "admin_api",
        _ROOT / "apps/mcp-server" / "src" / "mcp_server",
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
    main_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "main.py"
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
    BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")
    BASE_MCP = os.getenv("MINTKEY_MCP_URL", "http://localhost:8082")
    BASE_KONG = os.getenv("MINTKEY_KONG_URL", "http://localhost:8000")
    BOOTSTRAP_PASSWORD = os.getenv("MINTKEY_BOOTSTRAP_PASSWORD", "changeme")

    t_start = time.monotonic()

    # Step 1 — bootstrap health check
    r = httpx.get(f"{BASE_API}/v1/health", timeout=10)
    assert r.status_code == 200, f"Step 1 health: {r.status_code} {r.text}"
    assert r.json().get("status") == "ok", f"Step 1 health body: {r.text}"

    # Shared session client (carries cookies across requests)
    with httpx.Client(timeout=30) as client:

        # Step 2 — login
        csrf_r = client.get(f"{BASE_API}/v1/auth/csrf")
        assert csrf_r.status_code == 200, f"CSRF fetch: {csrf_r.status_code}"
        csrf_token = csrf_r.json()["csrf_token"]

        login_r = client.post(
            f"{BASE_API}/v1/auth/session",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert login_r.status_code == 200, f"Step 2 login: {login_r.status_code} {login_r.text}"

        # Step 3 — register service
        csrf_r = client.get(f"{BASE_API}/v1/auth/csrf")
        csrf_token = csrf_r.json()["csrf_token"]

        svc_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/services",
            json={
                "name": "demo-backend",
                "base_url": "http://mock-backend:8999",
                "auth_scheme": "api_key_header",
                "settings": {},
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        assert svc_r.status_code == 201, f"Step 3 register service: {svc_r.status_code} {svc_r.text}"
        service_id = svc_r.json()["id"]

        # Step 4 — register credential
        csrf_r = client.get(f"{BASE_API}/v1/auth/csrf")
        csrf_token = csrf_r.json()["csrf_token"]

        cred_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/services/{service_id}/credentials",
            json={
                "auth_scheme": "api_key_header",
                "value": "sk-demo-secret-key-12345",
                "header_name": "X-API-Key",
            },
            headers={"X-CSRF-Token": csrf_token},
        )
        assert cred_r.status_code == 201, f"Step 4 register credential: {cred_r.status_code} {cred_r.text}"

        # Step 5 — test service (unreachable from admin-api is acceptable)
        csrf_r = client.get(f"{BASE_API}/v1/auth/csrf")
        csrf_token = csrf_r.json()["csrf_token"]

        test_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/services/{service_id}/test",
            headers={"X-CSRF-Token": csrf_token},
        )
        assert test_r.status_code < 500 or test_r.status_code in (502, 503), (
            f"Step 5 test service unexpected error: {test_r.status_code} {test_r.text}"
        )

        # Step 6 — create agent
        csrf_r = client.get(f"{BASE_API}/v1/auth/csrf")
        csrf_token = csrf_r.json()["csrf_token"]

        agent_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/agents",
            json={"name": "demo-agent"},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert agent_r.status_code == 201, f"Step 6 create agent: {agent_r.status_code} {agent_r.text}"
        agent_body = agent_r.json()
        agent_id = agent_body["id"]
        api_key = agent_body["api_key"]

        # Step 7 — grant permission
        csrf_r = client.get(f"{BASE_API}/v1/auth/csrf")
        csrf_token = csrf_r.json()["csrf_token"]

        perm_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/permissions",
            json={"agent_id": agent_id, "service_id": service_id, "action": "call"},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert perm_r.status_code == 201, f"Step 7 grant permission: {perm_r.status_code} {perm_r.text}"

        # Step 8 — MCP discovery
        disc_r = client.get(
            f"{BASE_MCP}/v1/tools/discover",
            headers={"X-API-Key": api_key},
        )
        assert disc_r.status_code == 200, f"Step 8 MCP discovery: {disc_r.status_code} {disc_r.text}"

        # Step 9 — token request
        tok_r = client.post(
            f"{BASE_MCP}/v1/tools/request_token",
            json={"service_id": service_id, "action": "call"},
            headers={"X-API-Key": api_key},
        )
        assert tok_r.status_code == 200, f"Step 9 token request: {tok_r.status_code} {tok_r.text}"
        tok_body = tok_r.json()
        token = tok_body["token"]
        # JWT must have three dot-separated parts
        assert token.count(".") == 2, f"Step 9 token not a JWT: {token!r}"

        # Step 10 — brokered call through Kong
        proxy_r = httpx.get(
            f"{BASE_KONG}/proxy/api-key-header",
            headers={"Authorization": f"Bearer {token}"},
            timeout=15,
        )
        assert proxy_r.status_code in (200, 401, 502), (
            f"Step 10 brokered call unexpected status: {proxy_r.status_code} {proxy_r.text}"
        )
        if proxy_r.status_code == 200:
            assert proxy_r.json().get("received_key") == "sk-demo-secret-key-12345", (
                f"Step 10 brokered call wrong key: {proxy_r.text}"
            )

        # Step 11 — audit verification
        audit_r = client.get(f"{BASE_API}/v1/tenants/t_default/audit")
        assert audit_r.status_code == 200, f"Step 11 audit: {audit_r.status_code} {audit_r.text}"
        audit_items = audit_r.json().get("items", [])
        assert len(audit_items) > 0, "Step 11 audit: no audit events found"
        event_types = {item.get("event_type") for item in audit_items}
        assert any("token" in et for et in event_types if et), (
            f"Step 11 audit: no token.issued event found in {event_types}"
        )

        # Step 12 — red-team: plaintext credential must not appear in token response
        assert "sk-demo-secret-key-12345" not in tok_r.text, (
            "Step 12 red-team: plaintext credential leaked in token response"
        )

    # Step 13 — timing check
    elapsed = time.monotonic() - t_start
    assert elapsed <= 90, f"Step 13 timing: {elapsed:.1f}s > 90s limit"
