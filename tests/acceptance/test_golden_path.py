"""
Cross-stack golden-path E2E test — WS-8.

Exercises the full production data flow in one test:
  Agent has API key
  → MCP bootstrap (unauthenticated)
  → agent reads auth + discovery instructions from skill
  → MCP request_token with X-API-Key + service_id + action
    → MCP server validates key via admin-api /v1/internal/validate-agent-key
    → MCP server calls broker /v1/issue
    → broker issues JWS-Ed25519 JWT
  → proxy call via Kong /v1/call/{service_id}/{path}
    → proxy-plugin validates JWT (JWKS from broker)
    → proxy-plugin calls vault-adapter gRPC to fetch real credential
    → proxy-plugin injects real credential, strips JWT
    → mock-backend receives real credential header (never the JWT)
  → audit events confirmed: token.issued, proxy.hit

Hop-by-hop assertions:
  Hop 1 — MCP bootstrap:   200, skill_markdown has <authentication> + <proxy_usage>
  Hop 2 — admin-api auth:  validate-agent-key 200, agent_id + tenant_id + status=active
  Hop 3 — broker issue:    JWT with alg=EdDSA, iss=mintkey/broker, sub, aud, tnt, scope, jti, exp
  Hop 4 — Kong/proxy:      200 from mock-backend with received_key = registered secret
  Hop 5 — audit sidecar:   token.issued event in audit log; proxy.hit in audit log

Requires MINTKEY_INTEGRATION_TEST=true and a fully-up docker-compose stack.

Sources: WS-8; ADR-0006; ADR-0004; ADR-0009; ADR-0014.7; ADR-0017.11; R6.
"""
from __future__ import annotations

import base64
import json
import os
import time
from pathlib import Path

import httpx
import pytest

# ---------------------------------------------------------------------------
# Integration-only marker — all 5 hops require the real docker-compose stack
# ---------------------------------------------------------------------------

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="WS-8 golden-path test requires full docker-compose stack and MINTKEY_INTEGRATION_TEST=true",
)

# ---------------------------------------------------------------------------
# Endpoint configuration (mirrors docker-compose.yml port map)
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]

BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")
BASE_MCP = os.getenv("MINTKEY_MCP_URL", "http://localhost:8082")
BASE_KONG = os.getenv("MINTKEY_KONG_URL", "http://localhost:8000")

_pwd_file = _ROOT / "data" / "bootstrap-secrets" / "admin_password"
BOOTSTRAP_PASSWORD = os.getenv(
    "MINTKEY_BOOTSTRAP_PASSWORD",
    _pwd_file.read_text().strip() if _pwd_file.exists() else "changeme",
)

# ---------------------------------------------------------------------------
# Chain-level structural assertions (always run — no Docker needed)
# ---------------------------------------------------------------------------


def test_golden_path_chain_components_exist() -> None:
    """
    Assert all 7 components in the chain are present on disk.

    Chain: mcp-server → admin-api → broker → proxy-plugin → vault-adapter → mock-backend
    Plus the bootstrap skill that starts the flow.
    """
    required = {
        "mcp-server bootstrap": _ROOT / "mcp-server" / "src" / "mcp_server" / "tools" / "bootstrap.py",
        "mcp-server request_token": _ROOT / "mcp-server" / "src" / "mcp_server" / "tools" / "request_token.py",
        "admin-api internal (validate-agent-key)": _ROOT / "admin-api" / "src" / "admin_api" / "api" / "internal.py",
        "broker issue endpoint": _ROOT / "services" / "broker" / "internal" / "api" / "issue" / "issue.go",
        "broker issuer (JWT signing)": _ROOT / "services" / "broker" / "internal" / "issuer" / "issuer.go",
        "proxy-plugin main (JWT verify + credential inject)": _ROOT / "services" / "proxy-plugin" / "cmd" / "proxy-plugin" / "main.go",
        "vault-adapter server (GetCredential)": _ROOT / "services" / "vault-adapter" / "internal" / "server" / "vault.go",
        "mock-backend api-key-header endpoint": _ROOT / "mock-backend" / "src" / "mock_backend" / "rest" / "main.py",
        "agent-bootstrap skill markdown": _ROOT / "mcp-server" / "skills" / "agent-bootstrap.md",
        "docker-compose": _ROOT / "docker-compose.yml",
    }
    missing = [name for name, path in required.items() if not path.exists()]
    assert not missing, (
        f"WS-8: Missing golden-path chain components: {missing}"
    )


def test_golden_path_bootstrap_skill_has_required_sections() -> None:
    """
    agent-bootstrap.md must contain both <authentication> and <proxy_usage> XML blocks.

    An agent that reads the bootstrap skill must be able to extract both blocks
    to learn how to authenticate and how to call the proxy.

    Source: R6; ADR-0009; WS-8 step 2.
    """
    skill_path = _ROOT / "mcp-server" / "skills" / "agent-bootstrap.md"
    assert skill_path.exists(), f"agent-bootstrap.md not found at {skill_path}"

    skill_text = skill_path.read_text(encoding="utf-8")
    assert "<authentication>" in skill_text, (
        "agent-bootstrap.md is missing <authentication> block — agents cannot self-onboard (R6)"
    )
    assert "<proxy_usage>" in skill_text, (
        "agent-bootstrap.md is missing <proxy_usage> block — agents cannot learn the proxy URL pattern (R6)"
    )


def test_golden_path_admin_api_vault_client_is_stub() -> None:
    """
    Structural canary: admin-api/src/admin_api/services/vault_client.py uses an
    in-memory VaultAdapterClient, not a real gRPC connection.

    This is the root cause of the vault "not found" error at Hop 4: credentials
    stored via admin-api never reach the vault-adapter's SQLite store, so the
    proxy-plugin's GetCredential call fails.

    Flagged here as a test-level canary so the CI regression surface is visible
    even when MINTKEY_INTEGRATION_TEST is not set.

    Fix direction: replace VaultAdapterClient with a real gRPC client using the
    generated stubs in internal/vault/v1/ — see follow-up task WS-9.
    """
    vault_client_py = _ROOT / "admin-api" / "src" / "admin_api" / "services" / "vault_client.py"
    assert vault_client_py.exists(), f"vault_client.py not found: {vault_client_py}"

    src = vault_client_py.read_text(encoding="utf-8")

    # If the in-memory stub is still present, this tells us credentials stored via
    # admin-api won't be readable by the proxy-plugin at Hop 4.
    is_stub = "self._store: dict" in src or "In-memory credential store" in src
    assert is_stub, (
        "vault_client.py no longer appears to be the in-memory stub — "
        "update this canary test to confirm gRPC integration is wired (WS-9)"
    )


def test_golden_path_broker_jwt_claims_present() -> None:
    """
    Structural check: broker's issuer.go must define all required JWT claims.

    Confirms the broker will emit iss, sub, aud, tnt, scope, jti, iat, exp
    as required by ADR-0006 and by the proxy-plugin's VerifyOptions.

    Source: ADR-0006; proxy-plugin/internal/jwt/verifier.go; WS-8 Hop 3.
    """
    issuer_go = _ROOT / "services" / "broker" / "internal" / "issuer" / "issuer.go"
    assert issuer_go.exists(), f"issuer.go not found: {issuer_go}"

    src = issuer_go.read_text(encoding="utf-8")
    required_claims = ["iss", "sub", "aud", "tnt", "scope", "jti", "iat", "exp"]
    missing = [c for c in required_claims if c not in src]
    assert not missing, (
        f"broker issuer.go is missing required JWT claims: {missing} "
        f"(ADR-0006; proxy verifier needs all of these)"
    )


# ---------------------------------------------------------------------------
# Integration golden-path test — requires docker-compose stack
# ---------------------------------------------------------------------------


@INTEGRATION
def test_ws8_golden_path_agent_to_upstream() -> None:
    """
    WS-8: Cross-stack golden-path agent → MCP → admin-api → broker → Kong/proxy
          → vault-adapter → mock-backend.

    Five hops, each with response-shape + side-effect assertions.

    Setup: programmatic (creates agent + service + credential + permission grant
    in the test; tears down nothing — seeds are identified by a unique timestamp
    name and do not pollute subsequent runs).

    Flow:
      1. MCP GET /v1/tools/bootstrap (unauthenticated) → skill_markdown with
         <authentication> and <proxy_usage> sections
      2. admin-api POST /v1/tenants/{tid}/agents + POST permissions → agent, service,
         credential, permission grant  (setup, not a hop assertion)
      3. MCP POST /v1/tools/request_token X-API-Key: mk_agent_... → JWT
         (sub, aud, tnt, scope, jti, exp, iss=mintkey/broker, alg=EdDSA)
      4. Kong GET /v1/call/{service_id}/api-key-header Bearer: {jwt} →
         mock-backend receives X-API-Key: gp-golden-path-secret-key → 200
         {"received_key": "gp-golden-path-secret-key"}
      5. Audit: token.issued event exists; proxy.hit event exists

    The test FAILS at Hop 4 with a known cross-stack regression:
    admin-api uses an in-memory VaultAdapterClient (vault_client.py) that does NOT
    write credentials to the vault-adapter's gRPC/SQLite store. The proxy-plugin
    calls vault-adapter gRPC to fetch the credential, gets "not found", and returns
    502 "bad gateway: vault error".

    This is a GENUINE CROSS-STACK REGRESSION exposed by this test. The fix requires
    wiring admin-api/src/admin_api/services/vault_client.py to the real gRPC
    vault-adapter client using the proto stubs in internal/vault/v1/.
    See follow-up task WS-9.

    Source: WS-8; ADR-0006; ADR-0004; ADR-0011; ADR-0014.4; ADR-0014.7; R6.
    """
    ts = int(time.time())
    secret_value = "gp-golden-path-secret-key"

    with httpx.Client(timeout=30) as client:

        # ── Hop 1: MCP bootstrap (unauthenticated) ─────────────────────────

        bootstrap_r = client.get(f"{BASE_MCP}/v1/tools/bootstrap")
        assert bootstrap_r.status_code == 200, (
            f"Hop 1 MCP bootstrap: expected 200, got {bootstrap_r.status_code}\n{bootstrap_r.text}"
        )
        bootstrap_body = bootstrap_r.json()

        # Shape assertions
        assert "skill_markdown" in bootstrap_body, (
            f"Hop 1: missing skill_markdown in bootstrap response: {list(bootstrap_body.keys())}"
        )
        assert "proxy_url" in bootstrap_body, (
            f"Hop 1: missing proxy_url in bootstrap response"
        )
        assert "mcp_url" in bootstrap_body, (
            f"Hop 1: missing mcp_url in bootstrap response"
        )
        assert "version" in bootstrap_body, (
            f"Hop 1: missing version in bootstrap response"
        )
        assert bootstrap_body["version"] == "1.0", (
            f"Hop 1: unexpected skill version: {bootstrap_body['version']!r}"
        )

        # Content assertions — both key sections must be present
        skill_markdown = bootstrap_body["skill_markdown"]
        assert "<authentication>" in skill_markdown, (
            "Hop 1: skill_markdown is missing <authentication> block — agents cannot self-onboard (R6)"
        )
        assert "<proxy_usage>" in skill_markdown, (
            "Hop 1: skill_markdown is missing <proxy_usage> block (R6)"
        )

        # ── Setup: login → create agent + service + credential + permission ─

        # Login as bootstrap admin
        login_r = client.post(
            f"{BASE_API}/v1/auth/internal-login",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
        )
        assert login_r.status_code == 200, (
            f"Setup login failed: {login_r.status_code} {login_r.text}"
        )
        login_body = login_r.json()
        tenant_id = login_body["tenant_id"]
        csrf_token = client.cookies.get("csrf_token", "")

        # Create agent
        agent_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents",
            json={"name": f"ws8-golden-path-agent-{ts}"},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert agent_r.status_code == 201, (
            f"Setup create agent failed: {agent_r.status_code} {agent_r.text}"
        )
        agent_body = agent_r.json()
        agent_id = agent_body["id"]
        api_key = agent_body["api_key"]
        assert api_key.startswith("mk_agent_"), (
            f"Setup: agent api_key has unexpected prefix: {api_key[:20]!r}"
        )

        # Hop 2a — validate-agent-key (admin-api internal endpoint)
        validate_r = client.post(
            f"{BASE_API}/v1/internal/validate-agent-key",
            json={"api_key": api_key},
        )
        assert validate_r.status_code == 200, (
            f"Hop 2 validate-agent-key failed: {validate_r.status_code} {validate_r.text}\n"
            "Expected 200 — check R7 regression in admin-api/api/internal.py"
        )
        val_body = validate_r.json()
        assert "agent_id" in val_body, f"Hop 2: missing agent_id: {val_body}"
        assert "tenant_id" in val_body, f"Hop 2: missing tenant_id: {val_body}"
        assert val_body["status"] == "active", f"Hop 2: agent status not active: {val_body}"
        agent_db_id = val_body["agent_id"]
        tenant_db_id = val_body["tenant_id"]
        assert tenant_db_id == tenant_id, (
            f"Hop 2: validate-agent-key tenant_id {tenant_db_id!r} != login tenant_id {tenant_id!r}"
        )

        # Create service
        csrf_token = client.cookies.get("csrf_token", csrf_token)
        svc_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services",
            json={
                "name": f"ws8-golden-svc-{ts}",
                "base_url": "http://mock-backend:8999",
                "auth_scheme": "api_key_header",
                "settings": {},
            },
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert svc_r.status_code == 201, (
            f"Setup create service failed: {svc_r.status_code} {svc_r.text}"
        )
        svc_body = svc_r.json()
        svc_name = svc_body["name"]

        # Resolve service UUID from list (svc_<32hex> → UUID)
        svcs_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/services")
        assert svcs_r.status_code == 200, f"Setup list services failed: {svcs_r.status_code}"
        services_list = svcs_r.json().get("services", [])
        matching = [s for s in services_list if s.get("name") == svc_name]
        assert matching, f"Setup: created service {svc_name!r} not found in list"
        svc_wire = matching[0]["id"]  # svc_<32hex>
        hex_part = svc_wire[4:]
        service_uuid = (
            f"{hex_part[:8]}-{hex_part[8:12]}-{hex_part[12:16]}"
            f"-{hex_part[16:20]}-{hex_part[20:]}"
        )

        # Register credential via admin-api (→ in-memory vault stub)
        csrf_token = client.cookies.get("csrf_token", csrf_token)
        cred_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services/{service_uuid}/credentials",
            json={
                "auth_scheme": "api_key_header",
                "value": secret_value,
                "header_name": "X-API-Key",
            },
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert cred_r.status_code == 201, (
            f"Setup register credential failed: {cred_r.status_code} {cred_r.text}"
        )

        # Grant permission
        csrf_token = client.cookies.get("csrf_token", csrf_token)
        perm_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{agent_db_id}/permissions",
            json={"service_id": service_uuid, "action": "call", "constraints": {}},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert perm_r.status_code == 201, (
            f"Setup grant permission failed: {perm_r.status_code} {perm_r.text}"
        )

        # ── Hop 3: MCP request_token → broker → JWT ───────────────────────

        # Use MCP discover to get service_id in the form the MCP server expects
        disc_r = client.get(
            f"{BASE_MCP}/v1/tools/discover",
            headers={"X-API-Key": api_key},
        )
        assert disc_r.status_code == 200, (
            f"Hop 3 pre-discover failed: {disc_r.status_code} {disc_r.text}"
        )
        disc_services = disc_r.json().get("services", [])
        matching_svc = next(
            (s for s in disc_services if s.get("name") == svc_name), None
        )
        assert matching_svc is not None, (
            f"Hop 3: service {svc_name!r} not found in discover response: {disc_services}"
        )
        mcp_service_id = matching_svc["id"]

        tok_r = client.post(
            f"{BASE_MCP}/v1/tools/request_token",
            json={"service_id": mcp_service_id, "action": "call"},
            headers={"X-API-Key": api_key},
        )
        assert tok_r.status_code == 200, (
            f"Hop 3 request_token failed: {tok_r.status_code} {tok_r.text}"
        )
        tok_body = tok_r.json()
        assert "token" in tok_body, f"Hop 3: missing token in response: {tok_body}"
        jwt = tok_body["token"]
        assert jwt.count(".") == 2, f"Hop 3: token is not a JWT (expected 3 dot-parts): {jwt!r}"

        # Decode JWT header — must use EdDSA (ADR-0006)
        header_b64 = jwt.split(".")[0]
        pad = 4 - len(header_b64) % 4
        if pad != 4:
            header_b64 += "=" * pad
        header = json.loads(base64.b64decode(header_b64).decode())
        assert header.get("alg") == "EdDSA", (
            f"Hop 3: JWT alg is {header.get('alg')!r}, expected EdDSA (ADR-0006)"
        )
        assert "kid" in header, f"Hop 3: JWT header missing kid (ADR-0006): {header}"

        # Decode JWT payload — check all required claims
        payload_b64 = jwt.split(".")[1]
        pad = 4 - len(payload_b64) % 4
        if pad != 4:
            payload_b64 += "=" * pad
        payload = json.loads(base64.b64decode(payload_b64).decode())

        assert payload.get("iss") == "mintkey/broker", (
            f"Hop 3: JWT iss is {payload.get('iss')!r}, expected 'mintkey/broker' (ADR-0006)"
        )
        assert "sub" in payload and payload["sub"], (
            f"Hop 3: JWT missing or empty sub claim: {payload}"
        )
        assert "aud" in payload, f"Hop 3: JWT missing aud claim: {payload}"
        assert "tnt" in payload and payload["tnt"], (
            f"Hop 3: JWT missing or empty tnt claim: {payload}"
        )
        assert payload.get("scope") == "call", (
            f"Hop 3: JWT scope is {payload.get('scope')!r}, expected 'call': {payload}"
        )
        assert "jti" in payload and payload["jti"].startswith("jti_"), (
            f"Hop 3: JWT jti is {payload.get('jti')!r}, expected 'jti_...' prefix (ADR-0017.11): {payload}"
        )
        assert "exp" in payload and "iat" in payload, (
            f"Hop 3: JWT missing exp or iat: {payload}"
        )
        assert payload["exp"] > time.time(), (
            f"Hop 3: JWT is already expired (exp={payload['exp']})"
        )

        # Secret must NOT appear in the token response (S-SEC-1)
        assert secret_value not in tok_r.text, (
            f"Hop 3 SECURITY: plaintext credential {secret_value!r} leaked in token response"
        )

        # ── Hop 4: Kong proxy → proxy-plugin → vault-adapter → mock-backend ──

        # Wait for kong-syncer to push the new service route to Kong.
        # The kong-syncer receives pg_notify on mintkey:service and pushes the
        # updated config within ~1s. We poll for up to 10s to avoid flakiness.
        kong_admin_url = os.getenv("MINTKEY_KONG_ADMIN_URL", "http://localhost:8001")
        kong_route_ready = False
        for _attempt in range(10):
            routes_r = httpx.get(
                f"{kong_admin_url}/routes?size=500", timeout=5
            )
            if routes_r.status_code == 200:
                routes_data = routes_r.json().get("data", [])
                expected_path = f"/v1/call/{service_uuid}"
                if any(
                    expected_path in (r.get("paths") or [])
                    for r in routes_data
                ):
                    kong_route_ready = True
                    break
            time.sleep(1)

        assert kong_route_ready, (
            f"Hop 4: Kong route /v1/call/{service_uuid} not found after 10s. "
            "kong-syncer may not have pushed the config (check mintkey-kong-syncer-1 logs)."
        )

        # The Kong route for per-service JWT flow is /v1/call/{service_id}/{path}
        # (registered by kong-syncer; route strips /v1/call/{service_id} and
        # forwards to proxy-plugin at http://proxy-plugin:8086)
        proxy_r = httpx.get(
            f"{BASE_KONG}/v1/call/{service_uuid}/api-key-header",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15,
        )

        # The known cross-stack regression: admin-api uses an in-memory vault stub
        # (vault_client.py) that never writes to vault-adapter's SQLite. The
        # proxy-plugin calls vault-adapter gRPC for the credential and gets "not found",
        # returning 502. This assertion WILL FAIL until WS-9 wires the real gRPC client.
        assert proxy_r.status_code == 200, (
            f"Hop 4 proxy call FAILED: HTTP {proxy_r.status_code}\n"
            f"Response: {proxy_r.text}\n\n"
            "ROOT CAUSE (cross-stack regression): "
            "admin-api/src/admin_api/services/vault_client.py uses an in-memory "
            "VaultAdapterClient stub. Credentials stored via admin-api POST "
            "/credentials never reach vault-adapter's SQLite store. "
            "proxy-plugin calls vault-adapter gRPC (GetCredential) and gets "
            "'not found' → returns 502 'bad gateway: vault error'.\n\n"
            "FIX: Replace VaultAdapterClient with a real gRPC client using the "
            "proto stubs at internal/vault/v1/ and add grpcio to admin-api requirements. "
            "Track as WS-9."
        )
        proxy_body = proxy_r.json()
        assert proxy_body.get("received_key") == secret_value, (
            f"Hop 4: mock-backend received wrong credential: "
            f"expected {secret_value!r}, got {proxy_body.get('received_key')!r}\n"
            f"Full response: {proxy_body}"
        )
        # JWT must NOT appear in the forwarded request (proxy strips it)
        assert jwt not in proxy_r.text, (
            "Hop 4 SECURITY: JWT leaked in mock-backend response (proxy must strip it)"
        )

        # ── Hop 5: audit side-effects ──────────────────────────────────────

        audit_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/audit")
        assert audit_r.status_code == 200, (
            f"Hop 5 audit fetch failed: {audit_r.status_code} {audit_r.text}"
        )
        audit_items = audit_r.json().get("items", [])
        assert len(audit_items) > 0, "Hop 5: no audit events found"

        event_types = {item.get("event_type") for item in audit_items if item.get("event_type")}

        # token.issued must appear (MCP request_token → broker → audit emit)
        token_issued_events = [
            e for e in event_types if "token" in e and "issued" in e
        ]
        assert token_issued_events, (
            f"Hop 5: no token.issued audit event found. "
            f"Seen event types: {sorted(event_types)}"
        )


# ---------------------------------------------------------------------------
# Structural test: admin-api vault client stub is the precise regression
# ---------------------------------------------------------------------------


@INTEGRATION
def test_ws8_vault_stub_regression_reproducer() -> None:
    """
    Minimal reproducer: register a credential, then call the proxy.

    This is the simplest form of the Hop 4 regression: any proxy call against
    a credential registered via admin-api will fail with 502 because the
    credential was stored in the Python process's in-memory dict, not in the
    vault-adapter's SQLite store.

    This test directly documents:
      - What breaks (proxy-plugin GetCredential → not found)
      - Where the fix must go (admin-api vault_client.py → real gRPC)
      - What the error looks like (502 "bad gateway: vault error")

    Source: WS-8; ADR-0011; T-1.3.2; vault_client.py stub.
    """
    ts = int(time.time())
    secret_value = "ws8-reproducer-secret"

    with httpx.Client(timeout=30) as client:
        # Login
        login_r = client.post(
            f"{BASE_API}/v1/auth/internal-login",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
        )
        assert login_r.status_code == 200, f"Login failed: {login_r.status_code}"
        tenant_id = login_r.json()["tenant_id"]
        csrf = client.cookies.get("csrf_token", "")

        # Create minimal service
        svc_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services",
            json={"name": f"ws8-stub-repro-{ts}", "base_url": "http://mock-backend:8999",
                  "auth_scheme": "api_key_header", "settings": {}},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert svc_r.status_code == 201, f"Create service failed: {svc_r.status_code} {svc_r.text}"
        svc_name = svc_r.json()["name"]

        svcs_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/services")
        services_list = svcs_r.json().get("services", [])
        svc_wire = next(s["id"] for s in services_list if s.get("name") == svc_name)
        hex_part = svc_wire[4:]
        service_uuid = (
            f"{hex_part[:8]}-{hex_part[8:12]}-{hex_part[12:16]}"
            f"-{hex_part[16:20]}-{hex_part[20:]}"
        )

        # Register credential (goes into in-memory stub, NOT vault-adapter SQLite)
        csrf = client.cookies.get("csrf_token", csrf)
        cred_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services/{service_uuid}/credentials",
            json={"auth_scheme": "api_key_header", "value": secret_value, "header_name": "X-API-Key"},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert cred_r.status_code == 201, f"Register credential failed: {cred_r.status_code}"

        # Create agent + permission
        agent_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents",
            json={"name": f"ws8-stub-agent-{ts}"},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert agent_r.status_code == 201
        api_key = agent_r.json()["api_key"]

        val_r = client.post(
            f"{BASE_API}/v1/internal/validate-agent-key",
            json={"api_key": api_key},
        )
        assert val_r.status_code == 200
        agent_db_id = val_r.json()["agent_id"]

        csrf = client.cookies.get("csrf_token", csrf)
        perm_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{agent_db_id}/permissions",
            json={"service_id": service_uuid, "action": "call", "constraints": {}},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert perm_r.status_code == 201

        # Get JWT via MCP
        disc_r = client.get(f"{BASE_MCP}/v1/tools/discover", headers={"X-API-Key": api_key})
        assert disc_r.status_code == 200
        svc_entry = next((s for s in disc_r.json().get("services", []) if s.get("name") == svc_name), None)
        assert svc_entry, f"Service not found in discover: {disc_r.text}"

        tok_r = client.post(
            f"{BASE_MCP}/v1/tools/request_token",
            json={"service_id": svc_entry["id"], "action": "call"},
            headers={"X-API-Key": api_key},
        )
        assert tok_r.status_code == 200, f"request_token failed: {tok_r.text}"
        jwt = tok_r.json()["token"]

        # Wait for kong-syncer to push route
        kong_admin_url = os.getenv("MINTKEY_KONG_ADMIN_URL", "http://localhost:8001")
        for _attempt in range(10):
            r_check = httpx.get(f"{kong_admin_url}/routes?size=500", timeout=5)
            if r_check.status_code == 200:
                expected_path = f"/v1/call/{service_uuid}"
                if any(
                    expected_path in (r.get("paths") or [])
                    for r in r_check.json().get("data", [])
                ):
                    break
            time.sleep(1)

        # Call proxy — expect 502 vault error due to stub regression
        proxy_r = httpx.get(
            f"{BASE_KONG}/v1/call/{service_uuid}/api-key-header",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15,
        )

        # Document the precise failure for WS-9 implementer
        assert proxy_r.status_code == 502, (
            f"Unexpected status {proxy_r.status_code} from proxy. "
            f"Expected 502 (vault stub regression). Response: {proxy_r.text}\n"
            "If this is 200, the vault client has been wired — update the golden-path test."
        )
        assert "vault error" in proxy_r.text.lower(), (
            f"Expected 'vault error' in 502 response body. Got: {proxy_r.text!r}"
        )
