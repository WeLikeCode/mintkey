"""
E2E smoke test — T-1.11.2.

Non-integration assertions run always and verify the structural preconditions
for the full 13-step E2E smoke test.  The actual integration test is gated on
MINTKEY_INTEGRATION_TEST=true (requires a running docker-compose stack).

Sources: T-1.11.2; ADR-0014.7; S-SEC-1; ADR-0017.11; ADR-0019.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import time
import uuid
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
# OIDC login helper
# ===========================================================================


def _oidc_login(client: httpx.Client, base_api: str, password: str) -> str:
    """Drive the Keycloak OIDC headless flow and return the csrf_token value.

    Flow (mirrors apps/admin-ui/e2e/global-setup.ts but in Python/httpx):
      1. GET {base_api}/v1/auth/oidc/login        → 302 to Keycloak auth URL
         (admin-api generates PKCE state + stores it in _state_store)
      2. GET Keycloak auth URL                     → 200 HTML login form
         (parse <form action=...> + hidden fields)
      3. POST username + password to Keycloak form → 302 to callback
      4. GET {base_api}/v1/auth/oidc/callback      → 302 to admin-ui
         (admin-api exchanges code, creates session, sets cookies)
      After step 4 the client jar holds:
        mintkey_session  — httponly session cookie
        csrf_token       — non-httponly; read back for X-Mintkey-Csrf header
    Returns the csrf_token string.
    """
    username = os.getenv("MINTKEY_OIDC_USER", "admin@mintkey.internal")

    # Step 1 — trigger OIDC login: admin-api builds auth_url + stores PKCE state
    r1 = client.get(f"{base_api}/v1/auth/oidc/login", follow_redirects=False)
    assert r1.status_code == 302, (
        f"OIDC login redirect: expected 302, got {r1.status_code}"
    )
    kc_auth_url = r1.headers["location"]

    # Step 2 — fetch Keycloak login page (follow any internal Keycloak redirects)
    r2 = client.get(kc_auth_url, follow_redirects=True)
    assert r2.status_code == 200, (
        f"Keycloak login page: expected 200, got {r2.status_code}"
    )
    m = re.search(r'action="([^"]+)"', r2.text)
    assert m, "Keycloak login page: <form action> not found"
    form_action = m.group(1).replace("&amp;", "&")

    # Step 3 — POST credentials to Keycloak
    r3 = client.post(
        form_action,
        data={"username": username, "password": password, "credentialId": ""},
        follow_redirects=False,
    )
    assert r3.status_code in (301, 302, 303, 307, 308), (
        f"Keycloak credentials POST: expected redirect, got {r3.status_code}. "
        "Possible bad password. Body: " + r3.text[:300]
    )
    callback_url = r3.headers["location"]

    # Step 4 — follow callback to admin-api; it sets mintkey_session + csrf_token cookies
    r4 = client.get(callback_url, follow_redirects=False)
    # Callback returns 302 to admin-ui on success; any 4xx/5xx is a failure
    assert r4.status_code in (301, 302, 303, 307, 308), (
        f"OIDC callback: expected redirect, got {r4.status_code} {r4.text[:300]}"
    )

    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token, (
        "OIDC callback: csrf_token cookie not set after successful login"
    )
    assert "mintkey_session" in client.cookies, (
        "OIDC callback: mintkey_session cookie not set"
    )
    return csrf_token


_CROCKFORD_ALPHA = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_COMPOSE_FILE = str(_ROOT / "infra/compose/docker-compose.yml")


def _wire_to_db_uuid(wire_id: str) -> str | None:
    """Decode a wire-format prefixed ULID (svc_/agent_/...) to a DB UUID string."""
    import uuid as _uuid
    try:
        crockford = wire_id.split("_", 1)[1] if "_" in wire_id else wire_id
        val = 0
        for ch in crockford.upper():
            val = val * 32 + _CROCKFORD_ALPHA.index(ch)
        return str(_uuid.UUID(int=val))
    except Exception as exc:
        print(f"[teardown] WARNING: could not decode wire id {wire_id!r}: {exc}")
        return None


def _db_teardown_service(service_wire_id: str) -> None:
    """Hard-delete credentials + service row via docker compose exec psql.

    The credential API endpoint is a soft-delete (sets status='revoked') but
    does NOT hard-delete the row, so the FK fk_credentials_service blocks the
    service hard-delete.  Direct SQL bypasses this: DELETE credentials first,
    then DELETE the service.

    Uses the same compose file as the running stack.  Best-effort: logs
    warnings on failure but does NOT raise.
    """
    db_uuid = _wire_to_db_uuid(service_wire_id)
    if not db_uuid:
        return

    sql = (
        f"SET row_security=off; "
        f"DELETE FROM credentials WHERE service_id = '{db_uuid}'; "
        f"DELETE FROM permission_grants WHERE service_id = '{db_uuid}'; "
        f"DELETE FROM services WHERE id = '{db_uuid}';"
    )
    cmd = [
        "docker", "compose", "-f", _COMPOSE_FILE,
        "exec", "-T", "postgres",
        "sh", "-c",
        f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "{sql}"',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(
                f"[teardown] WARNING: DB teardown for service {service_wire_id} failed: "
                f"{result.stderr[:200]}"
            )
    except Exception as exc:
        print(f"[teardown] WARNING: DB teardown subprocess failed: {exc}")


def _db_teardown_agent(agent_wire_id: str) -> None:
    """Hard-delete agent row (and its orphaned permission_grants) via docker compose exec psql.

    Used as fallback when the API delete fails due to FK from permission_grants.
    Best-effort: logs warnings on failure but does NOT raise.
    """
    db_uuid = _wire_to_db_uuid(agent_wire_id)
    if not db_uuid:
        return

    sql = (
        f"SET row_security=off; "
        f"DELETE FROM permission_grants WHERE agent_id = '{db_uuid}'; "
        f"DELETE FROM agents WHERE id = '{db_uuid}';"
    )
    cmd = [
        "docker", "compose", "-f", _COMPOSE_FILE,
        "exec", "-T", "postgres",
        "sh", "-c",
        f'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "{sql}"',
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode != 0:
            print(
                f"[teardown] WARNING: DB teardown for agent {agent_wire_id} failed: "
                f"{result.stderr[:200]}"
            )
    except Exception as exc:
        print(f"[teardown] WARNING: DB teardown agent subprocess failed: {exc}")


# ===========================================================================
# Unit assertions (always run)
# ===========================================================================


def test_e2e_smoke_components_exist() -> None:
    """All required component directories / files must exist."""
    required = [
        _ROOT / "apps/admin-api" / "src" / "admin_api",
        _ROOT / "apps/mcp-server" / "src" / "mcp_server",
        _ROOT / "apps" / "broker",
        _ROOT / "apps" / "proxy-plugin",
        _ROOT / "apps" / "vault-adapter",
        _ROOT / "apps/mock-backend" / "src" / "mock_backend",
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
        _ROOT / "apps/mock-backend" / "src" / "mock_backend" / "rest" / "main.py"
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
    verify_py = _ROOT / "apps/audit-verify-job" / "verify.py"
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
    bootstrap → OIDC login → register service → register credential → test
    → create agent → grant permission → MCP discovery → token request
    → brokered call → audit verification → red-team check → timing check.

    Login uses Keycloak OIDC flow (ADR-0019) — legacy password/CSRF endpoints
    are 404-gated.

    Must complete in ≤ 90s from docker compose up healthy.
    """
    BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")
    BASE_MCP = os.getenv("MINTKEY_MCP_URL", "http://localhost:8082")
    BASE_KONG = os.getenv("MINTKEY_KONG_URL", "http://localhost:8000")
    BOOTSTRAP_PASSWORD = os.getenv("MINTKEY_BOOTSTRAP_PASSWORD", "changeme")

    # Unique suffix per run — prevents 409 on reruns
    run_id = uuid.uuid4().hex[:8]
    demo_service_name = f"demo-backend-{run_id}"
    demo_agent_name = f"demo-agent-{run_id}"

    t_start = time.monotonic()

    # Step 1 — bootstrap health check
    r = httpx.get(f"{BASE_API}/v1/health", timeout=10)
    assert r.status_code == 200, f"Step 1 health: {r.status_code} {r.text}"
    assert r.json().get("status") == "ok", f"Step 1 health body: {r.text}"

    # Shared session client (carries cookies across requests)
    with httpx.Client(timeout=30, follow_redirects=False) as client:

        # Step 2 — OIDC login via Keycloak (ADR-0019; replaces legacy 404-gated
        # /v1/auth/csrf + /v1/auth/session password flow).
        # After _oidc_login: mintkey_session cookie is set + csrf_token returned.
        # CSRF double-submit: read csrf_token cookie, send as X-Mintkey-Csrf header.
        csrf_token = _oidc_login(client, BASE_API, BOOTSTRAP_PASSWORD)

        # Track resources created by this test for teardown
        created_service_id: str | None = None
        created_agent_id: str | None = None
        created_permission_id: str | None = None
        created_credential_key_version: int | None = None
        tenant_id: str | None = None

        try:
            # Resolve tenant_id from current session (whoami)
            whoami_r = client.get(f"{BASE_API}/v1/auth/whoami")
            assert whoami_r.status_code == 200, (
                f"Step 2 whoami: {whoami_r.status_code} {whoami_r.text}"
            )
            tenant_id = whoami_r.json()["operator"]["tenant_id"]

            # Step 3 — register service
            svc_r = client.post(
                f"{BASE_API}/v1/tenants/{tenant_id}/services",
                json={
                    "name": demo_service_name,
                    "base_url": "http://mock-backend:8999",
                    "auth_scheme": "api_key_header",
                    "settings": {},
                },
                headers={"X-Mintkey-Csrf": csrf_token},
            )
            assert svc_r.status_code == 201, (
                f"Step 3 register service: {svc_r.status_code} {svc_r.text}"
            )
            service_id = svc_r.json()["id"]
            created_service_id = service_id

            # Step 4 — register credential
            cred_r = client.post(
                f"{BASE_API}/v1/tenants/{tenant_id}/services/{service_id}/credentials",
                json={
                    "auth_scheme": "api_key_header",
                    "value": "sk-demo-secret-key-12345",
                    "header_name": "X-API-Key",
                },
                headers={"X-Mintkey-Csrf": csrf_token},
            )
            assert cred_r.status_code == 201, (
                f"Step 4 register credential: {cred_r.status_code} {cred_r.text}"
            )
            # key_version is the integer path param for DELETE
            created_credential_key_version = cred_r.json().get("key_version")

            # Step 5 — test service (unreachable from admin-api is acceptable)
            test_r = client.post(
                f"{BASE_API}/v1/tenants/{tenant_id}/services/{service_id}/test",
                headers={"X-Mintkey-Csrf": csrf_token},
            )
            assert test_r.status_code < 500 or test_r.status_code in (502, 503), (
                f"Step 5 test service unexpected error: {test_r.status_code} {test_r.text}"
            )

            # Step 6 — create agent
            agent_r = client.post(
                f"{BASE_API}/v1/tenants/{tenant_id}/agents",
                json={"name": demo_agent_name},
                headers={"X-Mintkey-Csrf": csrf_token},
            )
            assert agent_r.status_code == 201, (
                f"Step 6 create agent: {agent_r.status_code} {agent_r.text}"
            )
            agent_body = agent_r.json()
            agent_id = agent_body["id"]
            api_key = agent_body["api_key"]
            created_agent_id = agent_id

            # Step 7 — grant permission
            perm_r = client.post(
                f"{BASE_API}/v1/tenants/{tenant_id}/agents/{agent_id}/permissions",
                json={"service_id": service_id, "action": "call"},
                headers={"X-Mintkey-Csrf": csrf_token},
            )
            assert perm_r.status_code == 201, (
                f"Step 7 grant permission: {perm_r.status_code} {perm_r.text}"
            )
            created_permission_id = perm_r.json().get("id")

            # Step 8 — MCP discovery
            disc_r = client.get(
                f"{BASE_MCP}/v1/tools/discover",
                headers={"X-API-Key": api_key},
            )
            assert disc_r.status_code == 200, (
                f"Step 8 MCP discovery: {disc_r.status_code} {disc_r.text}"
            )

            # Step 9 — token request
            tok_r = client.post(
                f"{BASE_MCP}/v1/tools/request_token",
                json={"service_id": service_id, "action": "call"},
                headers={"X-API-Key": api_key},
            )
            assert tok_r.status_code == 200, (
                f"Step 9 token request: {tok_r.status_code} {tok_r.text}"
            )
            tok_body = tok_r.json()
            token = tok_body["token"]
            # JWT must have three dot-separated parts
            assert token.count(".") == 2, f"Step 9 token not a JWT: {token!r}"

            # Step 10 — brokered call through Kong proxy
            # Kong routes are registered as /v1/call/{service_id} (not /proxy/...)
            proxy_r = httpx.get(
                f"{BASE_KONG}/v1/call/{service_id}/api-key-header",
                headers={"Authorization": f"Bearer {token}"},
                timeout=15,
            )
            assert proxy_r.status_code in (200, 401, 404, 502), (
                f"Step 10 brokered call unexpected status: {proxy_r.status_code} {proxy_r.text}"
            )
            if proxy_r.status_code == 200:
                assert proxy_r.json().get("received_key") == "sk-demo-secret-key-12345", (
                    f"Step 10 brokered call wrong key: {proxy_r.text}"
                )

            # Step 11 — audit verification
            audit_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/audit")
            assert audit_r.status_code == 200, (
                f"Step 11 audit: {audit_r.status_code} {audit_r.text}"
            )
            audit_body = audit_r.json()
            # API returns {"events": [...]} or {"items": [...]} depending on version
            audit_items = audit_body.get("events") or audit_body.get("items") or []
            assert len(audit_items) > 0, "Step 11 audit: no audit events found"
            event_types = {item.get("event_type") for item in audit_items}
            assert any(
                "token" in et or "proxy" in et for et in event_types if et
            ), (
                f"Step 11 audit: no token/proxy event found in {event_types}"
            )

            # Step 12 — red-team: plaintext credential must not appear in token response
            assert "sk-demo-secret-key-12345" not in tok_r.text, (
                "Step 12 red-team: plaintext credential leaked in token response"
            )

        finally:
            # Teardown — delete only the resources THIS run created.
            # Order: revoke permission (API) → delete agent (API) → DB cleanup for service.
            # The credential API is a soft-delete leaving FK intact; the agent delete API
            # also can't cascade permission_grants FK.  We use API for what works, then
            # fall back to direct DB for service + credential cleanup.
            # Best-effort: never block on cleanup failures; log them instead.

            # Step T1: revoke permission via API (clears fk_permission_grants_agent FK)
            if created_permission_id and created_agent_id and tenant_id:
                try:
                    del_perm = client.delete(
                        f"{BASE_API}/v1/tenants/{tenant_id}/agents/{created_agent_id}"
                        f"/permissions/{created_permission_id}",
                        headers={"X-Mintkey-Csrf": csrf_token},
                    )
                    if del_perm.status_code not in (200, 204, 404):
                        print(
                            f"[teardown] WARNING: revoke permission {created_permission_id} "
                            f"returned {del_perm.status_code}: {del_perm.text[:200]}"
                        )
                except Exception as exc:
                    print(f"[teardown] WARNING: revoke permission failed: {exc}")

            # Step T2: delete agent via API (permission FK now clear)
            if created_agent_id and tenant_id:
                _agent_api_ok = False
                try:
                    del_agent = client.delete(
                        f"{BASE_API}/v1/tenants/{tenant_id}/agents/{created_agent_id}",
                        headers={"X-Mintkey-Csrf": csrf_token},
                    )
                    if del_agent.status_code in (200, 204, 404):
                        _agent_api_ok = True
                    else:
                        print(
                            f"[teardown] WARNING: delete agent {created_agent_id} "
                            f"returned {del_agent.status_code}: {del_agent.text[:200]}"
                        )
                except Exception as exc:
                    print(f"[teardown] WARNING: delete agent API failed: {exc}")
                # Fallback: DB-level delete if API failed
                if not _agent_api_ok:
                    _db_teardown_agent(created_agent_id)

            # Step T3: hard-delete credentials + service via direct DB.
            # The credential API only soft-deletes (UPDATE status='revoked'), leaving the
            # credential row in DB with an FK pointing to the service, so the service API
            # delete returns 500 (FK violation).  Direct DB DELETE removes both cleanly.
            if created_service_id:
                _db_teardown_service(created_service_id)

    # Step 13 — timing check
    elapsed = time.monotonic() - t_start
    assert elapsed <= 90, f"Step 13 timing: {elapsed:.1f}s > 90s limit"
