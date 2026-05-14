"""
WS-5 acceptance test — classical service API keys (ADR-0018).

Non-integration assertions run always and verify the structural preconditions.
The full integration test is gated on MINTKEY_INTEGRATION_TEST=true (requires
a running docker-compose stack).

Source: ADR-0018; design §2; T long-lived-api-keys.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
import pytest

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full docker-compose stack",
)

_ROOT = Path(__file__).parent.parent.parent


# ===========================================================================
# Unit assertions (always run)
# ===========================================================================


def test_classical_key_schema_exists() -> None:
    """Liquibase changeset 012-service-api-keys.yaml must exist."""
    changelog = _ROOT / "admin-api" / "db" / "changelog" / "012-service-api-keys.yaml"
    assert changelog.exists(), f"Missing: {changelog}"


def test_classical_key_admin_api_routers_exist() -> None:
    """admin-api/main.py must import api_keys routers."""
    main_py = _ROOT / "admin-api" / "src" / "admin_api" / "main.py"
    src = main_py.read_text()
    assert "api_keys_router" in src, "api_keys_router not wired in main.py"
    assert "api_keys_shortcut_router" in src, "api_keys_shortcut_router not wired"


def test_classical_key_prefix() -> None:
    """classicalkey.IsClassicalKey must recognise mk_svckey_ prefix."""
    # Verify the Go code has the prefix check (structural)
    handler_go = (
        _ROOT / "services" / "proxy-plugin" / "internal" / "classicalkey" / "handler.go"
    )
    src = handler_go.read_text()
    assert 'HasPrefix(cred, "mk_svckey_")' in src, (
        "IsClassicalKey check missing in handler.go"
    )


def test_classical_key_request_transformer_in_yaml_generator() -> None:
    """kong-syncer YAML generator must inject X-Mintkey-Service-ID header."""
    yaml_go = (
        _ROOT / "services" / "kong-syncer" / "internal" / "kong" / "yaml.go"
    )
    src = yaml_go.read_text()
    assert "request-transformer" in src, "request-transformer plugin missing from yaml.go"
    assert "X-Mintkey-Service-ID" in src, "X-Mintkey-Service-ID header injection missing"
    assert "X-Mintkey-Tenant-ID" in src, "X-Mintkey-Tenant-ID header injection missing"


def test_proxy_plugin_classical_key_dispatch() -> None:
    """proxy-plugin main.go must dispatch mk_svckey_ tokens to handleClassicalKey."""
    main_go = (
        _ROOT / "services" / "proxy-plugin" / "cmd" / "proxy-plugin" / "main.go"
    )
    src = main_go.read_text()
    assert "IsClassicalKey" in src, "IsClassicalKey dispatch missing from main.go"
    assert "handleClassicalKey" in src, "handleClassicalKey not referenced in main.go"


# ===========================================================================
# Integration test (requires docker-compose stack)
# ===========================================================================


@INTEGRATION
def test_classical_key_full_flow() -> None:
    """
    Full classical key flow:
    1. Login as operator
    2. Create service + credential
    3. Create agent + grant permission
    4. Create classical API key (allowed_actions=["call"])
    5. Poll for Kong route to become active
    6. Call /v1/call/<svc>/api-key-header with the classical key
    7. Assert 200 + mock backend sees the real credential (not the key)
    8. Revoke the key
    9. Assert denial within min(5s, cache_ttl)
    """
    BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")
    BASE_KONG = os.getenv("MINTKEY_KONG_URL", "http://localhost:8000")
    BOOTSTRAP_PASSWORD = os.getenv("MINTKEY_BOOTSTRAP_PASSWORD", "changeme")
    REAL_CRED = "sk-classical-key-test-12345"

    with httpx.Client(timeout=30) as client:
        # Step 1 — login
        csrf_r = client.get(f"{BASE_API}/v1/auth/csrf")
        assert csrf_r.status_code == 200
        csrf_token = csrf_r.json()["csrf_token"]

        login_r = client.post(
            f"{BASE_API}/v1/auth/session",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
            headers={"X-CSRF-Token": csrf_token},
        )
        assert login_r.status_code == 200, f"login: {login_r.status_code} {login_r.text}"

        def get_csrf() -> str:
            r = client.get(f"{BASE_API}/v1/auth/csrf")
            assert r.status_code == 200
            return r.json()["csrf_token"]

        # Step 2 — create service
        svc_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/services",
            json={
                "name": "classical-key-test-backend",
                "base_url": "http://mock-backend:8999",
                "auth_scheme": "api_key_header",
                "settings": {},
            },
            headers={"X-CSRF-Token": get_csrf()},
        )
        assert svc_r.status_code == 201, f"create service: {svc_r.status_code} {svc_r.text}"
        service_id = svc_r.json()["id"]

        # Register credential
        cred_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/services/{service_id}/credentials",
            json={
                "auth_scheme": "api_key_header",
                "value": REAL_CRED,
                "header_name": "X-API-Key",
            },
            headers={"X-CSRF-Token": get_csrf()},
        )
        assert cred_r.status_code == 201, f"register cred: {cred_r.status_code} {cred_r.text}"

        # Step 3 — create agent
        agent_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/agents",
            json={"name": "classical-key-test-agent"},
            headers={"X-CSRF-Token": get_csrf()},
        )
        assert agent_r.status_code == 201, f"create agent: {agent_r.status_code} {agent_r.text}"
        agent_id = agent_r.json()["id"]

        # Grant permission (action=call)
        perm_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/permissions",
            json={"agent_id": agent_id, "service_id": service_id, "action": "call"},
            headers={"X-CSRF-Token": get_csrf()},
        )
        assert perm_r.status_code == 201, f"grant perm: {perm_r.status_code} {perm_r.text}"

        # Step 4 — create classical API key
        key_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/agents/{agent_id}/api-keys",
            json={
                "service_id": service_id,
                "allowed_actions": ["call"],
            },
            headers={"X-CSRF-Token": get_csrf()},
        )
        assert key_r.status_code == 201, f"create key: {key_r.status_code} {key_r.text}"
        key_body = key_r.json()
        plaintext_key = key_body["plaintext_key"]
        api_key_id = key_body["api_key_id"]

        # Verify key has mk_svckey_ prefix
        assert plaintext_key.startswith("mk_svckey_"), (
            f"Unexpected key prefix: {plaintext_key[:20]!r}"
        )

        # Step 5 — wait for kong-syncer to push the route (≤ 15s)
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            probe = httpx.get(
                f"{BASE_KONG}/v1/call/{service_id}/api-key-header",
                headers={"Authorization": f"Bearer {plaintext_key}"},
                timeout=5,
            )
            if probe.status_code != 404:
                break
            time.sleep(1)
        # We proceed even if probe is non-404 (may still be 401/503 before broker resolves)

        # Step 6 — call the proxy with the classical key
        proxy_r = httpx.get(
            f"{BASE_KONG}/v1/call/{service_id}/api-key-header",
            headers={"Authorization": f"Bearer {plaintext_key}"},
            timeout=15,
        )
        assert proxy_r.status_code == 200, (
            f"classical key proxy call: {proxy_r.status_code} {proxy_r.text}"
        )

        # Step 7 — mock backend must see the real credential (not the API key)
        received = proxy_r.json().get("received_key")
        assert received == REAL_CRED, (
            f"Mock backend received wrong credential: {received!r} (expected {REAL_CRED!r})"
        )
        assert plaintext_key not in proxy_r.text, (
            "Classical key plaintext leaked in response"
        )

        # Step 8 — revoke the key
        revoke_r = client.post(
            f"{BASE_API}/v1/tenants/t_default/agents/{agent_id}/api-keys/{api_key_id}/revoke",
            json={"reason": "test revocation"},
            headers={"X-CSRF-Token": get_csrf()},
        )
        assert revoke_r.status_code in (200, 204), (
            f"revoke: {revoke_r.status_code} {revoke_r.text}"
        )

        # Step 9 — verify denial within 5s (cache eviction via mintkey:agent NOTIFY)
        t0 = time.monotonic()
        denied = False
        while time.monotonic() - t0 < 5:
            deny_r = httpx.get(
                f"{BASE_KONG}/v1/call/{service_id}/api-key-header",
                headers={"Authorization": f"Bearer {plaintext_key}"},
                timeout=5,
            )
            if deny_r.status_code in (401, 403):
                denied = True
                break
            time.sleep(0.5)

        assert denied, (
            f"Revoked classical key still accepted after 5s "
            f"(last status: {deny_r.status_code})"
        )
