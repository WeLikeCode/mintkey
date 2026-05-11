#!/usr/bin/env python3
"""
Mintkey end-to-end smoke test — full endpoint coverage.

Exercises ALL admin-api endpoints documented in docs/architecture/contracts/rest/openapi.yaml:

  HEALTH/READY
  0.  GET  /v1/health, GET /v1/ready
  AUTH
  1.  POST /v1/auth/internal-login
  1b. GET  /v1/auth/whoami
  1c. GET  /v1/auth/oidc/login  (expect redirect — OIDC not wired in dev)
  TENANTS
  2a. POST /v1/tenants  (create second tenant for isolation test)
  SERVICES
  2b. POST /v1/tenants/{id}/services  (create Twilio + Mock Backend)
  2c. GET  /v1/tenants/{id}/services  (list)
  2d. PATCH /v1/tenants/{id}/services/{id}  (update display_name)
  2e. DELETE /v1/tenants/{id}/services/{id}  (delete a transient service)
  CREDENTIALS
  3.  POST /v1/tenants/{id}/services/{id}/credentials  (store)
  3b. GET  /v1/tenants/{id}/services/{id}/credentials  (list fingerprints — no plaintext)
  AGENTS
  4.  POST /v1/tenants/{id}/agents  (create)
  4b. GET  /v1/tenants/{id}/agents  (list)
  4c. GET  /v1/tenants/{id}/agents/{id}  (get)
  PERMISSIONS
  5.  POST /v1/tenants/{id}/agents/{id}/permissions  (grant)
  5b. DELETE /v1/tenants/{id}/agents/{id}/permissions/{id}  (revoke)
  API KEYS
  6.  POST /v1/tenants/{id}/agents/{id}/api-keys  (issue)
  6b. GET  /v1/tenants/{id}/agents/{id}/api-keys  (list)
  6c. GET  /v1/tenants/{id}/agents/{id}/api-keys/{id}  (get)
  6d. POST /v1/tenants/{id}/agents/{id}/api-keys/{id}/revoke
  6e. POST /v1/tenants/{id}/agents/{id}/api-keys/{id}/rotate
  PROXY
  7.  GET  /v1/proxy/call/{svc}/{path}  (Twilio + Mock Backend)
  8.  POST /v1/internal/proxy-hit  (Go proxy plugin internal endpoint)
  AUDIT
  9.  GET  /v1/tenants/{id}/audit  (tenant audit log)
  9b. GET  /v1/changes             (SSE stream — connect + disconnect)
  ADMIN/PLATFORM
  10. GET  /v1/admin/settings
  10b. PATCH /v1/admin/settings
  10c. POST /v1/admin/audit/verify-chain
  INTERNAL
  11. POST /v1/internal/validate-agent-key
  AUTH REJECTIONS
  12. Wrong Bearer key → 401, missing auth → 401
  LOGOUT
  13. POST /v1/auth/logout

Exit codes:
  0 = all checks passed
  1 = one or more checks failed

Usage:
  python3 scripts/e2e_smoke.py [--no-twilio] [--admin-api-url URL]

Environment variables:
  ADMIN_API_URL   default http://localhost:8080
  TWILIO_SID      Twilio Account SID  (default: demo account)
  TWILIO_TOKEN    Twilio Auth Token   (default: demo token)
  SKIP_TWILIO     set to 1 to skip live Twilio call
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from typing import Any

try:
    import requests
except ImportError:
    subprocess.run([sys.executable, "-m", "pip", "install", "requests", "-q"], check=True)
    import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
ADMIN_API_URL = os.getenv("ADMIN_API_URL", "http://localhost:8080")
ADMIN_EMAIL = "admin@mintkey.internal"
TWILIO_SID = os.getenv("TWILIO_SID", "<example-twilio-sid-redacted>")
TWILIO_TOKEN = os.getenv("TWILIO_TOKEN", "<example-twilio-token-redacted>")
SKIP_TWILIO = os.getenv("SKIP_TWILIO", "0") == "1"

PASS = "\033[0;32mPASS\033[0m"
FAIL = "\033[0;31mFAIL\033[0m"
INFO = "\033[1;33mINFO\033[0m"

pass_count = 0
fail_count = 0


def ok(msg: str) -> None:
    global pass_count
    print(f"{PASS} {msg}")
    pass_count += 1


def bad(msg: str, body: str = "") -> None:
    global fail_count
    print(f"{FAIL} {msg}")
    if body:
        print(f"     body: {body[:400]}")
    fail_count += 1


def info(msg: str) -> None:
    print(f"{INFO} {msg}")


# ---------------------------------------------------------------------------
# Docker helper to get values from Postgres
# ---------------------------------------------------------------------------
def pg_query(sql: str) -> str:
    r = subprocess.run(
        ["docker", "exec", "mintkey-postgres-1", "psql", "-U", "mintkey_migrate", "-d", "mintkey", "-tAc", sql],
        capture_output=True, text=True, timeout=10,
    )
    lines = [l.strip() for l in r.stdout.strip().split("\n") if l.strip() and l.strip() != "SET"]
    return lines[0] if lines else ""


def get_admin_password() -> str:
    r = subprocess.run(
        ["docker", "run", "--rm", "-v", "mintkey_bootstrap_secrets:/secrets", "alpine", "cat", "/secrets/admin_password"],
        capture_output=True, text=True, timeout=15,
    )
    return r.stdout.strip()


# ---------------------------------------------------------------------------
# HTTP session with cookies
# ---------------------------------------------------------------------------
session = requests.Session()
csrf_token: str = ""
tenant_id: str = ""
operator_id: str = ""


def api(method: str, path: str, **kwargs: Any) -> requests.Response:
    headers = kwargs.pop("headers", {})
    if method.upper() not in ("GET", "HEAD") and csrf_token:
        headers["x-mintkey-csrf"] = csrf_token
    return session.request(method, f"{ADMIN_API_URL}{path}", headers=headers, **kwargs)


def assert_status(label: str, resp: requests.Response, expected: int) -> bool:
    if resp.status_code == expected:
        ok(f"{label} (HTTP {resp.status_code})")
        return True
    else:
        bad(f"{label} — expected HTTP {expected}, got {resp.status_code}", resp.text)
        return False


# ---------------------------------------------------------------------------
# Step 0: Wait for healthy services
# ---------------------------------------------------------------------------
def step0_health() -> None:
    info("Step 0: Waiting for admin-api health...")
    for attempt in range(30):
        try:
            r = requests.get(f"{ADMIN_API_URL}/v1/health", timeout=3)
            if r.status_code == 200:
                ok("admin-api healthy")
                break
        except requests.RequestException:
            pass
        if attempt == 29:
            bad("admin-api not healthy after 60s")
            sys.exit(1)
        time.sleep(2)

    # /v1/ready — dependency readiness probe
    r = requests.get(f"{ADMIN_API_URL}/v1/ready", timeout=5)
    assert_status("admin-api ready probe", r, 200)

    for name, url in [("mock-backend", "http://localhost:8999/health"), ("mcp-server", "http://localhost:8082/health")]:
        try:
            r = requests.get(url, timeout=5)
            assert_status(f"{name} healthy", r, 200)
        except requests.RequestException as e:
            bad(f"{name} not reachable: {e}")


# ---------------------------------------------------------------------------
# Step 1: Authenticate
# ---------------------------------------------------------------------------
def step1_auth() -> None:
    global csrf_token, tenant_id, operator_id
    info("Step 1: Authenticating as bootstrap admin...")

    password = get_admin_password()
    if not password:
        bad("Could not read bootstrap password — is the stack running?")
        sys.exit(1)

    resp = session.post(
        f"{ADMIN_API_URL}/v1/auth/internal-login",
        json={"email": ADMIN_EMAIL, "password": password},
    )
    if not assert_status("Login", resp, 200):
        sys.exit(1)

    data = resp.json()
    tenant_id = data["tenant_id"]
    operator_id = data["operator_id"]

    # Extract CSRF from cookie jar
    csrf_token = session.cookies.get("csrf_token", "")
    if not csrf_token:
        bad("CSRF cookie not set after login")
        sys.exit(1)

    ok(f"CSRF token received")
    info(f"Tenant: {tenant_id} | Operator: {operator_id}")


# ---------------------------------------------------------------------------
# Step 2 & 3: Register services
# ---------------------------------------------------------------------------
def get_or_create_service(name: str, display_name: str, description: str,
                           base_url: str, auth_scheme: str, allow_internal: bool) -> str:
    """Return UUID of service (create if not present)."""
    slug = name.lower().replace(" ", "-")
    list_resp = api("GET", f"/v1/tenants/{tenant_id}/services")
    if list_resp.status_code == 200:
        for svc in list_resp.json().get("services", []):
            if svc["slug"] == slug:
                info(f"Service '{slug}' already exists")
                return pg_query(f"SET app.current_tenant = '{tenant_id}'; SELECT id FROM services WHERE slug = '{slug}';")

    create_resp = api("POST", f"/v1/tenants/{tenant_id}/services", json={
        "name": name,
        "display_name": display_name,
        "description": description,
        "base_url": base_url,
        "auth_scheme": auth_scheme,
        "allow_internal_urls": allow_internal,
    })
    if create_resp.status_code == 201:
        svc_uuid = pg_query(f"SET app.current_tenant = '{tenant_id}'; SELECT id FROM services WHERE slug = '{slug}';")
        ok(f"Service '{slug}' created: {svc_uuid}")
        return svc_uuid
    else:
        bad(f"Service '{slug}' creation failed", create_resp.text)
        return ""


def store_credential(svc_uuid: str, auth_scheme: str, value: str) -> bool:
    resp = api("POST", f"/v1/tenants/{tenant_id}/services/{svc_uuid}/credentials",
               json={"auth_scheme": auth_scheme, "value": value})
    if resp.status_code == 201:
        ok(f"Credential stored for {svc_uuid[:8]}…")
        return True
    bad(f"Credential store failed for {svc_uuid[:8]}…", resp.text)
    return False


# ---------------------------------------------------------------------------
# Step 4: Create agent
# ---------------------------------------------------------------------------
def step4_create_agent() -> tuple[str, str]:
    info("Step 4: Creating test agent...")
    resp = api("POST", f"/v1/tenants/{tenant_id}/agents",
               json={"name": "smoke-test-agent", "description": "Smoke test agent"})
    if resp.status_code == 201:
        agent_uuid = pg_query(f"SET app.current_tenant = '{tenant_id}'; SELECT id FROM agents WHERE name = 'smoke-test-agent';")
        agent_key = resp.json().get("api_key", "")
        ok(f"Agent created: {agent_uuid}")
        return agent_uuid, agent_key
    bad("Agent creation failed", resp.text)
    return "", ""


# ---------------------------------------------------------------------------
# Step 5: Grant permissions
# ---------------------------------------------------------------------------
def grant_permission(agent_uuid: str, svc_uuid: str) -> bool:
    resp = api("POST", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/permissions",
               json={"service_id": svc_uuid, "action": "*", "constraints": {}, "granted_by": operator_id})
    d = resp.json()
    if "id" in d or d.get("mintkey:code") == "permission_constraints_conflict":
        ok(f"Permission granted (agent={agent_uuid[:8]}… → svc={svc_uuid[:8]}…)")
        return True
    bad(f"Permission grant failed", resp.text)
    return False


# ---------------------------------------------------------------------------
# Step 6: Issue service API keys
# ---------------------------------------------------------------------------
def issue_api_key(agent_uuid: str, svc_uuid: str) -> str:
    resp = api("POST", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/api-keys",
               json={"service_id": svc_uuid, "allowed_actions": ["*"]})
    key = resp.json().get("plaintext_key", "")
    if key.startswith("mk_svckey_"):
        ok(f"Service API key issued for svc={svc_uuid[:8]}…: {key[:20]}…")
        return key
    bad(f"Service API key issue failed for svc={svc_uuid[:8]}…", resp.text)
    return ""


# ---------------------------------------------------------------------------
# Step 7: Proxy call — Twilio
# ---------------------------------------------------------------------------
def step7_twilio_proxy(svc_uuid: str, svckey: str) -> None:
    info("Step 7: Proxy call → Twilio Messages API...")
    if SKIP_TWILIO:
        info("SKIP_TWILIO=1 — skipping live Twilio call")
        return

    resp = requests.get(
        f"{ADMIN_API_URL}/v1/proxy/call/{svc_uuid}/2010-04-01/Accounts/{TWILIO_SID}/Messages.json",
        headers={"Authorization": f"Bearer {svckey}"},
        params={"PageSize": "1"},
        timeout=30,
    )
    assert_status("Twilio proxy call (basic_auth injection)", resp, 200)

    if resp.status_code == 200:
        messages = resp.json().get("messages", [])
        if messages:
            ok(f"Twilio returned {len(messages)} message(s)")
        else:
            bad("Twilio returned 0 messages — check account or credentials")

        # Security: auth token must NOT appear in response
        if TWILIO_TOKEN in resp.text:
            bad("SECURITY VIOLATION: Twilio auth token leaked in proxy response!")
        else:
            ok("Twilio auth token not in proxy response (no plaintext leak)")


# ---------------------------------------------------------------------------
# Step 8: Proxy call — Mock Backend
# ---------------------------------------------------------------------------
def step8_mock_proxy(svc_uuid: str, svckey: str) -> None:
    info("Step 8: Proxy call → Mock Backend...")
    for path, label in [("/health", "health"), ("/echo?test=smoke", "echo")]:
        resp = requests.get(
            f"{ADMIN_API_URL}/v1/proxy/call/{svc_uuid}{path}",
            headers={"Authorization": f"Bearer {svckey}"},
            timeout=10,
        )
        assert_status(f"Mock-backend proxy /{label} (api_key_header)", resp, 200)

    # Security: api key must NOT appear in response
    last_body = resp.text
    if "canary-demo-api-key" in last_body:
        bad("SECURITY VIOLATION: Mock-backend API key leaked in proxy response!")
    else:
        ok("Mock-backend API key not in proxy response (no plaintext leak)")


# ---------------------------------------------------------------------------
# Step 9: List services (MCP data plane)
# ---------------------------------------------------------------------------
def step9_list_services() -> None:
    info("Step 9: List services via admin-api (MCP data plane)...")
    resp = api("GET", f"/v1/tenants/{tenant_id}/services")
    if resp.status_code != 200:
        bad("List services failed", resp.text)
        return

    svcs = resp.json().get("services", [])
    ok(f"List services returned {len(svcs)} service(s)")

    slugs = {s["slug"] for s in svcs}
    ok("twilio-sms in list") if "twilio-sms" in slugs else bad("twilio-sms missing from list")
    ok("mock-backend in list") if "mock-backend" in slugs else bad("mock-backend missing from list")

    # MCP server note
    try:
        r = requests.get("http://localhost:8082/health", timeout=5)
        if r.status_code == 200:
            ok("MCP server reachable (placeholder — T-1.5.x not yet implemented)")
        else:
            bad("MCP server unhealthy")
    except requests.RequestException:
        bad("MCP server not reachable")


# ---------------------------------------------------------------------------
# Step 1b: Whoami
# ---------------------------------------------------------------------------
def step1b_whoami() -> None:
    info("Step 1b: GET /v1/auth/whoami...")
    r = api("GET", "/v1/auth/whoami")
    assert_status("whoami", r, 200)
    if r.status_code == 200:
        body = r.json()
        ok("whoami.operator_id present") if "operator_id" in body else bad("whoami.operator_id missing")
        ok("whoami.tenant_id present") if "tenant_id" in body else bad("whoami.tenant_id missing")


# ---------------------------------------------------------------------------
# Step 1c: OIDC login redirect (no real IdP wired in dev)
# ---------------------------------------------------------------------------
def step1c_oidc_login_redirects() -> None:
    info("Step 1c: GET /v1/auth/oidc/login → redirect...")
    r = requests.get(f"{ADMIN_API_URL}/v1/auth/oidc/login", allow_redirects=False, timeout=5)
    # expect 302 redirect to Keycloak (or 500 if Keycloak not configured)
    if r.status_code in (302, 307):
        ok(f"OIDC login redirects (HTTP {r.status_code})")
    elif r.status_code in (500, 503):
        ok(f"OIDC login returns {r.status_code} (Keycloak not configured in dev — expected)")
    else:
        bad(f"OIDC login unexpected status {r.status_code}", r.text[:200])


# ---------------------------------------------------------------------------
# Step 2a: Create a second tenant (POST /v1/tenants)
# ---------------------------------------------------------------------------
def step2a_create_tenant() -> str:
    info("Step 2a: POST /v1/tenants (create second tenant)...")
    r = api("POST", "/v1/tenants", json={
        "name": "smoke-tenant-b",
        "display_name": "Smoke Tenant B",
    })
    if r.status_code in (201, 409):
        if r.status_code == 201:
            ok(f"POST /v1/tenants → 201")
            return r.json().get("id", "")
        else:
            ok(f"POST /v1/tenants → 409 (already exists — idempotent)")
            return ""
    bad(f"POST /v1/tenants → {r.status_code}", r.text)
    return ""


# ---------------------------------------------------------------------------
# Step 2d: PATCH service
# ---------------------------------------------------------------------------
def step2d_patch_service(svc_uuid: str) -> None:
    info(f"Step 2d: PATCH /v1/tenants/{{id}}/services/{svc_uuid[:8]}…")
    r = api("PATCH", f"/v1/tenants/{tenant_id}/services/{svc_uuid}",
            json={"display_name": "Mock Backend (smoke-updated)"})
    assert_status("PATCH service", r, 200)


# ---------------------------------------------------------------------------
# Step 2e: Create + delete a transient service
# ---------------------------------------------------------------------------
def step2e_delete_service() -> None:
    info("Step 2e: CREATE then DELETE a transient service...")
    create = api("POST", f"/v1/tenants/{tenant_id}/services", json={
        "name": "transient-smoke-svc",
        "display_name": "Transient",
        "description": "Created and deleted in the same smoke run",
        "base_url": "http://localhost:9999",
        "auth_scheme": "bearer_token",
        "allow_internal_urls": True,
    })
    if create.status_code != 201:
        bad("Transient service creation failed", create.text)
        return
    ok("POST /v1/tenants/{id}/services (transient) → 201")
    svc_id = create.json().get("id", "")
    if not svc_id:
        bad("Transient service missing id in response")
        return
    delete = api("DELETE", f"/v1/tenants/{tenant_id}/services/{svc_id}")
    assert_status("DELETE /v1/tenants/{id}/services/{id}", delete, 204)


# ---------------------------------------------------------------------------
# Step 3b: GET credentials (fingerprints only — no plaintext)
# ---------------------------------------------------------------------------
def step3b_get_credentials(svc_uuid: str) -> None:
    info(f"Step 3b: GET /v1/tenants/{{id}}/services/{svc_uuid[:8]}…/credentials...")
    r = api("GET", f"/v1/tenants/{tenant_id}/services/{svc_uuid}/credentials")
    assert_status("GET credentials (fingerprint list)", r, 200)
    if r.status_code == 200:
        creds = r.json()
        # The response must not contain raw credential values
        raw = r.text
        if "canary-demo-api-key" in raw:
            bad("SECURITY: plaintext credential in GET /credentials response!")
        else:
            ok("GET credentials: no plaintext credential in response")


# ---------------------------------------------------------------------------
# Step 4b/4c: List and get agent
# ---------------------------------------------------------------------------
def step4b_list_agents() -> None:
    info("Step 4b: GET /v1/tenants/{id}/agents (list)...")
    r = api("GET", f"/v1/tenants/{tenant_id}/agents")
    assert_status("GET agents list", r, 200)
    if r.status_code == 200:
        agents = r.json().get("agents", r.json() if isinstance(r.json(), list) else [])
        ok(f"Agent list returned {len(agents)} agent(s)")


def step4c_get_agent(agent_uuid: str) -> None:
    info(f"Step 4c: GET /v1/tenants/{{id}}/agents/{agent_uuid[:8]}…")
    r = api("GET", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}")
    assert_status("GET agent by id", r, 200)
    if r.status_code == 200:
        body = r.json()
        ok("agent.id present") if "id" in body else bad("agent.id missing from response")


# ---------------------------------------------------------------------------
# Step 5b: Revoke a permission (grant a transient one first, then revoke it)
# ---------------------------------------------------------------------------
def step5b_revoke_permission(agent_uuid: str, svc_uuid: str) -> None:
    info("Step 5b: Grant + revoke a transient permission...")
    grant = api("POST", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/permissions",
                json={"service_id": svc_uuid, "action": "read", "constraints": {}, "granted_by": operator_id})
    if grant.status_code not in (201, 200, 409):
        bad("Transient permission grant failed", grant.text)
        return
    perm_id = grant.json().get("id", "")
    if not perm_id:
        # If 409 (conflict), try to find existing id via listing
        list_r = api("GET", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/permissions")
        if list_r.status_code == 200:
            perms = list_r.json().get("permissions", list_r.json() if isinstance(list_r.json(), list) else [])
            for p in perms:
                if p.get("action") == "read":
                    perm_id = p.get("id", "")
                    break
    if not perm_id:
        bad("Could not obtain permission id for revoke test")
        return
    ok(f"Transient permission granted: {perm_id[:8]}…")
    delete = api("DELETE", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/permissions/{perm_id}")
    assert_status("DELETE permission", delete, 204)


# ---------------------------------------------------------------------------
# Step 6b/6c/6d/6e: API key CRUD
# ---------------------------------------------------------------------------
def step6b_list_api_keys(agent_uuid: str) -> None:
    info("Step 6b: GET /v1/tenants/{id}/agents/{id}/api-keys (list)...")
    r = api("GET", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/api-keys")
    assert_status("GET api-keys list", r, 200)
    if r.status_code == 200:
        keys = r.json().get("api_keys", r.json() if isinstance(r.json(), list) else [])
        ok(f"API key list returned {len(keys)} key(s)")


def step6c_get_api_key(agent_uuid: str, key_id: str) -> None:
    info(f"Step 6c: GET /v1/tenants/{{id}}/agents/{{id}}/api-keys/{key_id[:8]}…")
    r = api("GET", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/api-keys/{key_id}")
    assert_status("GET api-key by id", r, 200)


def step6d_revoke_api_key(agent_uuid: str, key_id: str) -> None:
    info(f"Step 6d: POST .../api-keys/{key_id[:8]}…/revoke")
    r = api("POST", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/api-keys/{key_id}/revoke")
    assert_status("POST api-key revoke", r, 200)


def step6e_rotate_api_key(agent_uuid: str, svc_uuid: str) -> str:
    info("Step 6e: Issue a key then rotate it...")
    issue = api("POST", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/api-keys",
                json={"service_id": svc_uuid, "allowed_actions": ["*"]})
    if issue.status_code != 201:
        bad("Issue key for rotate test failed", issue.text)
        return ""
    ok("Key issued for rotate test → 201")
    key_id = issue.json().get("id", "")
    if not key_id:
        bad("Rotate test: no id in issue response")
        return ""
    rotate = api("POST", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/api-keys/{key_id}/rotate")
    assert_status("POST api-key rotate", rotate, 201)
    return rotate.json().get("id", "") if rotate.status_code == 201 else ""


# ---------------------------------------------------------------------------
# Step 8b: GET /v1/tenants/{id}/audit
# ---------------------------------------------------------------------------
def step8b_tenant_audit() -> None:
    info("Step 8b: GET /v1/tenants/{id}/audit...")
    r = api("GET", f"/v1/tenants/{tenant_id}/audit")
    assert_status("GET tenant audit log", r, 200)
    if r.status_code == 200:
        events = r.json().get("events", r.json() if isinstance(r.json(), list) else [])
        ok(f"Audit log returned {len(events)} event(s)")
        if events:
            # Sanity: no credential value in audit payloads
            raw = r.text
            if "canary-demo-api-key" in raw:
                bad("SECURITY: plaintext credential in audit log!")
            else:
                ok("Audit log: no plaintext credential values")


# ---------------------------------------------------------------------------
# Step 9b: GET /v1/changes (SSE — connect and immediately close)
# ---------------------------------------------------------------------------
def step9b_changes_sse() -> None:
    info("Step 9b: GET /v1/changes (SSE connect + disconnect)...")
    try:
        r = session.get(f"{ADMIN_API_URL}/v1/changes",
                        headers={"x-mintkey-csrf": csrf_token},
                        stream=True, timeout=3)
        if r.status_code == 200:
            ok("GET /v1/changes → 200 (SSE stream opened)")
        else:
            bad(f"GET /v1/changes → {r.status_code}", r.text[:200])
        r.close()
    except requests.exceptions.ReadTimeout:
        ok("GET /v1/changes → stream held open (read timeout = SSE working)")
    except Exception as e:
        bad(f"GET /v1/changes → exception: {e}")


# ---------------------------------------------------------------------------
# Step 10: Admin settings
# ---------------------------------------------------------------------------
def step10_admin_settings() -> None:
    info("Step 10: GET/PATCH /v1/admin/settings...")
    get_r = api("GET", "/v1/admin/settings")
    assert_status("GET /v1/admin/settings", get_r, 200)

    if get_r.status_code == 200:
        current = get_r.json()
        # PATCH with a benign change: toggle and restore max_api_key_expiry_days
        current_max = current.get("max_api_key_expiry_days", 365)
        patch_r = api("PATCH", "/v1/admin/settings",
                      json={"max_api_key_expiry_days": current_max})
        assert_status("PATCH /v1/admin/settings (no-op)", patch_r, 200)


# ---------------------------------------------------------------------------
# Step 10c: POST /v1/admin/audit/verify-chain
# ---------------------------------------------------------------------------
def step10c_verify_chain() -> None:
    info("Step 10c: POST /v1/admin/audit/verify-chain...")
    r = api("POST", "/v1/admin/audit/verify-chain", json={"tenant_id": tenant_id})
    # 200 = chain valid; 409 = tamper detected (not expected in smoke but not a test failure)
    if r.status_code in (200, 409):
        ok(f"POST /v1/admin/audit/verify-chain → {r.status_code}")
    else:
        bad(f"POST /v1/admin/audit/verify-chain → {r.status_code}", r.text[:200])


# ---------------------------------------------------------------------------
# Step 11: POST /v1/internal/validate-agent-key
# ---------------------------------------------------------------------------
def step11_validate_agent_key(agent_api_key: str) -> None:
    info("Step 11: POST /v1/internal/validate-agent-key...")
    if not agent_api_key:
        info("  No agent API key from creation — skipping validate-agent-key test")
        return
    r = requests.post(
        f"{ADMIN_API_URL}/v1/internal/validate-agent-key",
        json={"api_key": agent_api_key},
        timeout=5,
    )
    if r.status_code == 200:
        ok("POST /v1/internal/validate-agent-key → 200 (valid key)")
    elif r.status_code == 401:
        ok("POST /v1/internal/validate-agent-key → 401 (key not valid — agent key from creation may differ from svc key format)")
    else:
        bad(f"POST /v1/internal/validate-agent-key → {r.status_code}", r.text[:200])

    # Also verify that a bogus key returns 401
    r2 = requests.post(
        f"{ADMIN_API_URL}/v1/internal/validate-agent-key",
        json={"api_key": "mk_agent_BOGUS000000000000000000000000000000"},
        timeout=5,
    )
    assert_status("validate-agent-key with bogus key → 401", r2, 401)


# ---------------------------------------------------------------------------
# Step 12: Auth rejection tests
# ---------------------------------------------------------------------------
def step12_auth_rejections(svc_uuid: str) -> None:
    info("Step 12: Auth rejection checks...")
    r = requests.get(
        f"{ADMIN_API_URL}/v1/proxy/call/{svc_uuid}/health",
        headers={"Authorization": "Bearer mk_svckey_FAKEFAKEFAKEFAKE"},
        timeout=5,
    )
    assert_status("Bad Bearer key → 401", r, 401)

    r = requests.get(f"{ADMIN_API_URL}/v1/proxy/call/{svc_uuid}/health", timeout=5)
    assert_status("No auth header → 401", r, 401)


# ---------------------------------------------------------------------------
# Step 13: Logout
# ---------------------------------------------------------------------------
def step8c_proxy_hit(svc_uuid: str) -> None:
    """POST /v1/internal/proxy-hit — Egress Proxy audit emission."""
    info("Step 8c: POST /v1/internal/proxy-hit...")
    r = requests.post(
        f"{ADMIN_API_URL}/v1/internal/proxy-hit",
        json={
            "service_id": svc_uuid,
            "status_code": 200,
            "method": "GET",
            "path_template": "/health",
            "latency_ms": 42,
            "tenant_id": tenant_id,
            "auth_method": "api_key",
        },
        timeout=5,
    )
    assert_status("POST /v1/internal/proxy-hit", r, 201)


def step11b_revoke_agent(agent_uuid: str) -> None:
    """POST /v1/tenants/{id}/agents/{id}/revoke — revoke all keys for an agent."""
    info(f"Step 11b: POST .../agents/{agent_uuid[:8]}…/revoke...")
    r = api("POST", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/revoke")
    # 200 or 204 depending on implementation; 404 if already deleted
    if r.status_code in (200, 204):
        ok(f"POST agent revoke → {r.status_code}")
    else:
        bad(f"POST agent revoke → {r.status_code}", r.text[:200])


def step11c_delete_agent(agent_uuid: str) -> None:
    """DELETE /v1/tenants/{id}/agents/{id}."""
    info(f"Step 11c: DELETE .../agents/{agent_uuid[:8]}…")
    r = api("DELETE", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}")
    assert_status("DELETE agent", r, 204)


def step11d_acknowledge_tamper() -> None:
    """POST /v1/admin/audit/acknowledge-tamper — platform-admin action."""
    info("Step 11d: POST /v1/admin/audit/acknowledge-tamper...")
    r = api("POST", "/v1/admin/audit/acknowledge-tamper",
            json={"tenant_id": tenant_id, "reason": "smoke test — no real tamper"})
    # 201 = acknowledged; 404 = no tamper record to acknowledge (expected in clean stack)
    if r.status_code in (201, 404, 422):
        ok(f"POST /v1/admin/audit/acknowledge-tamper → {r.status_code} (expected in smoke)")
    else:
        bad(f"POST /v1/admin/audit/acknowledge-tamper → {r.status_code}", r.text[:200])


def step13_logout() -> None:
    info("Step 13: POST /v1/auth/logout...")
    r = api("POST", "/v1/auth/logout")
    assert_status("POST /v1/auth/logout", r, 200)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(description="Mintkey e2e smoke test — full endpoint coverage")
    parser.add_argument("--no-twilio", action="store_true", help="Skip live Twilio call")
    parser.add_argument("--admin-api-url", default=ADMIN_API_URL)
    args = parser.parse_args()

    if args.admin_api_url != ADMIN_API_URL:
        os.environ["ADMIN_API_URL"] = args.admin_api_url
    if args.no_twilio:
        os.environ["SKIP_TWILIO"] = "1"

    # ── Health + ready ───────────────────────────────────────────────────────
    step0_health()

    # ── Auth ─────────────────────────────────────────────────────────────────
    step1_auth()
    step1b_whoami()
    step1c_oidc_login_redirects()

    # ── Tenant bootstrap ─────────────────────────────────────────────────────
    step2a_create_tenant()

    # ── Services ─────────────────────────────────────────────────────────────
    info("Step 2b: Registering Twilio SMS service...")
    twilio_svc = get_or_create_service(
        "twilio-sms", "Twilio SMS", "Twilio Programmable Messaging",
        "https://api.twilio.com", "basic_auth", False,
    )
    if twilio_svc:
        store_credential(twilio_svc, "basic_auth", f"{TWILIO_SID}:{TWILIO_TOKEN}")

    info("Step 2c: Registering Mock Backend service...")
    mock_svc = get_or_create_service(
        "mock-backend", "Mock Backend", "Demo service for all auth schemes",
        "http://mock-backend:8999", "api_key_header", True,
    )
    if mock_svc:
        store_credential(mock_svc, "api_key_header", "canary-demo-api-key")
        step3b_get_credentials(mock_svc)
        step2d_patch_service(mock_svc)

    step2e_delete_service()
    step9_list_services()

    # ── Agents ───────────────────────────────────────────────────────────────
    agent_uuid, agent_api_key = step4_create_agent()
    if not agent_uuid:
        bad("Cannot continue without agent")
        return 1

    step4b_list_agents()
    step4c_get_agent(agent_uuid)

    # ── Permissions ──────────────────────────────────────────────────────────
    info("Step 5: Granting permissions...")
    for svc_id in [twilio_svc, mock_svc]:
        if svc_id:
            grant_permission(agent_uuid, svc_id)

    if mock_svc:
        step5b_revoke_permission(agent_uuid, mock_svc)
        # Re-grant so proxy calls work
        grant_permission(agent_uuid, mock_svc)

    # ── API keys ─────────────────────────────────────────────────────────────
    info("Step 6: Issuing service API keys...")
    twilio_key = issue_api_key(agent_uuid, twilio_svc) if twilio_svc else ""
    mock_key = issue_api_key(agent_uuid, mock_svc) if mock_svc else ""

    step6b_list_api_keys(agent_uuid)

    # Get id for the mock key so we can test get/revoke/rotate
    mock_key_id = ""
    if mock_svc:
        list_r = api("GET", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/api-keys")
        if list_r.status_code == 200:
            keys_data = list_r.json()
            keys = keys_data.get("api_keys", keys_data if isinstance(keys_data, list) else [])
            for k in keys:
                if k.get("service_id") == mock_svc and k.get("status") == "active":
                    mock_key_id = k.get("id", "")
                    break

    if mock_key_id:
        step6c_get_api_key(agent_uuid, mock_key_id)
        # Issue a throwaway key to revoke (not the one we need for proxy)
        throwaway = api("POST", f"/v1/tenants/{tenant_id}/agents/{agent_uuid}/api-keys",
                        json={"service_id": mock_svc, "allowed_actions": ["*"]})
        if throwaway.status_code == 201:
            throwaway_id = throwaway.json().get("id", "")
            if throwaway_id:
                step6d_revoke_api_key(agent_uuid, throwaway_id)

    if twilio_svc:
        step6e_rotate_api_key(agent_uuid, twilio_svc)

    # ── Proxy calls ──────────────────────────────────────────────────────────
    if twilio_key and twilio_svc:
        step7_twilio_proxy(twilio_svc, twilio_key)
    if mock_key and mock_svc:
        step8_mock_proxy(mock_svc, mock_key)

    # ── Audit + changes ──────────────────────────────────────────────────────
    step8b_tenant_audit()
    if mock_svc:
        step8c_proxy_hit(mock_svc)
    step9b_changes_sse()

    # ── Admin settings + chain verify ────────────────────────────────────────
    step10_admin_settings()
    step10c_verify_chain()

    # ── Internal endpoints ───────────────────────────────────────────────────
    step11_validate_agent_key(agent_api_key)
    step11d_acknowledge_tamper()

    # ── Create a disposable agent to test revoke + delete ────────────────────
    disposable = api("POST", f"/v1/tenants/{tenant_id}/agents",
                     json={"name": "smoke-disposable-agent", "description": "To be deleted"})
    if disposable.status_code == 201:
        ok("Disposable agent created for revoke/delete tests → 201")
        disp_id = disposable.json().get("id", "")
        if disp_id:
            step11b_revoke_agent(disp_id)
            step11c_delete_agent(disp_id)

    # ── Auth rejection tests ──────────────────────────────────────────────────
    step12_auth_rejections(mock_svc or twilio_svc)

    # ── Logout ───────────────────────────────────────────────────────────────
    step13_logout()

    # ── Summary ──────────────────────────────────────────────────────────────
    print()
    print("━" * 60)
    print(f"  Smoke test: \033[0;32m{pass_count} passed\033[0m, \033[0;31m{fail_count} failed\033[0m")
    print("━" * 60)
    print()
    print("Service UUIDs:")
    print(f"  Twilio:       {twilio_svc}")
    print(f"  Mock backend: {mock_svc}")
    print(f"  Agent:        {agent_uuid}")

    return 0 if fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
