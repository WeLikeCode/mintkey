"""
Data-plane smoke tests — WS-4.

Per-service happy-path smoke test for each of the four data-plane components:
  1. broker_smoke          — POST /v1/issue → EdDSA JWT shape
  2. vault_adapter_smoke   — gRPC PutCredential → GetCredential round-trip
  3. proxy_plugin_smoke    — JWT → Kong → proxy-plugin → credential injected → mock-backend 200
  4. kong_smoke            — Kong admin API responds and route table is reachable

All tests hit the real running docker-compose stack.
Gate: MINTKEY_INTEGRATION_TEST=true

Sources: WS-4; ADR-0006; ADR-0011; ADR-0004; ADR-0014.4.
"""
from __future__ import annotations

import base64
import json
import os
import sys
import time
from pathlib import Path

import grpc
import httpx
import pytest

# ---------------------------------------------------------------------------
# Import vault proto stubs from admin-api source tree (already generated)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADMIN_API_SRC = _REPO_ROOT / "admin-api" / "src"
if str(_ADMIN_API_SRC) not in sys.path:
    sys.path.insert(0, str(_ADMIN_API_SRC))

from admin_api.services import vault_pb2, vault_pb2_grpc  # noqa: E402

# ---------------------------------------------------------------------------
# Integration gate
# ---------------------------------------------------------------------------

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="WS-4 data-plane smoke tests require full docker-compose stack and MINTKEY_INTEGRATION_TEST=true",
)

# ---------------------------------------------------------------------------
# Service URLs (mirror docker-compose.yml port map)
# ---------------------------------------------------------------------------

BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")
BASE_MCP = os.getenv("MINTKEY_MCP_URL", "http://localhost:8082")
BASE_KONG = os.getenv("MINTKEY_KONG_URL", "http://localhost:8000")
KONG_ADMIN = os.getenv("MINTKEY_KONG_ADMIN_URL", "http://localhost:8001")
BROKER_URL = os.getenv("MINTKEY_BROKER_URL", "http://localhost:8083")
VAULT_GRPC = os.getenv("MINTKEY_VAULT_GRPC", "localhost:8084")

# Shared MCP service token injected by docker-compose.yml
MCP_SERVICE_TOKEN = os.getenv("MINTKEY_MCP_SERVICE_TOKEN", "dev-mcp-service-token")

_pwd_file = _REPO_ROOT / "data" / "bootstrap-secrets" / "admin_password"
BOOTSTRAP_PASSWORD = os.getenv(
    "MINTKEY_BOOTSTRAP_PASSWORD",
    _pwd_file.read_text().strip() if _pwd_file.exists() else "changeme",
)


# ---------------------------------------------------------------------------
# Helper: admin-api login + setup
# ---------------------------------------------------------------------------

def _admin_login(client: httpx.Client) -> tuple[str, str]:
    """Login as bootstrap admin. Returns (tenant_id, csrf_token)."""
    r = client.post(
        f"{BASE_API}/v1/auth/internal-login",
        json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
    )
    assert r.status_code == 200, f"admin login failed: {r.status_code} {r.text}"
    tenant_id = r.json()["tenant_id"]
    csrf = client.cookies.get("csrf_token", "")
    return tenant_id, csrf


def _create_agent_and_service(
    client: httpx.Client,
    tenant_id: str,
    csrf: str,
    ts: int,
    secret_value: str,
) -> tuple[str, str, str, str]:
    """
    Create an agent + service + credential + permission.
    Returns (api_key, agent_db_id, service_uuid, csrf_token).
    """
    # Create agent
    csrf = client.cookies.get("csrf_token", csrf)
    agent_r = client.post(
        f"{BASE_API}/v1/tenants/{tenant_id}/agents",
        json={"name": f"ws4-smoke-agent-{ts}"},
        headers={"X-Mintkey-Csrf": csrf},
    )
    assert agent_r.status_code == 201, f"create agent: {agent_r.status_code} {agent_r.text}"
    api_key = agent_r.json()["api_key"]

    val_r = client.post(
        f"{BASE_API}/v1/internal/validate-agent-key",
        json={"api_key": api_key},
    )
    assert val_r.status_code == 200
    agent_db_id = val_r.json()["agent_id"]

    # Create service
    csrf = client.cookies.get("csrf_token", csrf)
    svc_r = client.post(
        f"{BASE_API}/v1/tenants/{tenant_id}/services",
        json={
            "name": f"ws4-smoke-svc-{ts}",
            "base_url": "http://mock-backend:8999",
            "auth_scheme": "api_key_header",
            "settings": {},
        },
        headers={"X-Mintkey-Csrf": csrf},
    )
    assert svc_r.status_code == 201, f"create service: {svc_r.status_code} {svc_r.text}"
    svc_name = svc_r.json()["name"]

    svcs_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/services")
    services_list = svcs_r.json().get("services", [])
    svc_wire = next(s["id"] for s in services_list if s.get("name") == svc_name)
    hex_part = svc_wire[4:]
    service_uuid = (
        f"{hex_part[:8]}-{hex_part[8:12]}-{hex_part[12:16]}"
        f"-{hex_part[16:20]}-{hex_part[20:]}"
    )

    # Register credential
    csrf = client.cookies.get("csrf_token", csrf)
    cred_r = client.post(
        f"{BASE_API}/v1/tenants/{tenant_id}/services/{service_uuid}/credentials",
        json={"auth_scheme": "api_key_header", "value": secret_value, "header_name": "X-API-Key"},
        headers={"X-Mintkey-Csrf": csrf},
    )
    assert cred_r.status_code == 201, f"register credential: {cred_r.status_code} {cred_r.text}"

    # Grant permission
    csrf = client.cookies.get("csrf_token", csrf)
    perm_r = client.post(
        f"{BASE_API}/v1/tenants/{tenant_id}/agents/{agent_db_id}/permissions",
        json={"service_id": service_uuid, "action": "call", "constraints": {}},
        headers={"X-Mintkey-Csrf": csrf},
    )
    assert perm_r.status_code == 201, f"grant permission: {perm_r.status_code} {perm_r.text}"

    return api_key, agent_db_id, service_uuid, client.cookies.get("csrf_token", csrf)


def _wait_for_kong_route(service_uuid: str, timeout: int = 15) -> bool:
    """
    Poll Kong admin until the /v1/call/{service_uuid} route appears.

    Kong's route table is paginated (max 100/page). The kong-syncer may have
    pushed hundreds of routes already, so we paginate through all pages.
    """
    expected_path = f"/v1/call/{service_uuid}"
    for _ in range(timeout):
        try:
            found = _kong_route_exists(expected_path)
            if found:
                return True
        except httpx.RequestError:
            pass
        time.sleep(1)
    return False


def _kong_route_exists(expected_path: str) -> bool:
    """Return True if the expected_path appears in any page of Kong's route table."""
    url = f"{KONG_ADMIN}/routes?size=100"
    while url:
        r = httpx.get(url, timeout=5)
        if r.status_code != 200:
            return False
        body = r.json()
        if any(
            expected_path in (route.get("paths") or [])
            for route in body.get("data", [])
        ):
            return True
        # Follow pagination
        next_url = body.get("next")
        if next_url:
            # next is a relative path like "/routes?offset=...&size=100"
            url = f"{KONG_ADMIN}{next_url}" if next_url.startswith("/") else next_url
        else:
            url = None
    return False


def _decode_jwt_parts(jwt: str) -> tuple[dict, dict]:
    """Returns (header, payload) dicts decoded from a JWT string."""
    def _b64d(s: str) -> dict:
        pad = 4 - len(s) % 4
        if pad != 4:
            s += "=" * pad
        return json.loads(base64.b64decode(s).decode())

    parts = jwt.split(".")
    assert len(parts) == 3, f"token is not a JWT: {jwt!r}"
    return _b64d(parts[0]), _b64d(parts[1])


# ===========================================================================
# Smoke test 1: Broker
# ===========================================================================


@INTEGRATION
def test_broker_smoke() -> None:
    """
    Smoke: POST /v1/issue with valid X-Mintkey-Service-Token → JWT.

    Asserts:
      - HTTP 200
      - Response has {token, expires_at}
      - JWT header: alg=EdDSA, kid present
      - JWT payload: iss=mintkey/broker, sub, aud, tnt, scope, jti (jti_ prefix), exp in future

    Sources: WS-4; ADR-0006; T-1.5.3.
    """
    ts = int(time.time())
    # Manufacture a minimal issue request targeting a plausible agent/service/tenant.
    # We don't need these to exist in the DB for the broker to sign; it signs blindly.
    payload = {
        "agent_id": f"agent_WS4SMOKE{ts:020d}",
        "service_id": f"svc_WS4SMOKE{ts:020d}",
        "tenant_id": f"tenant_WS4SMOKE{ts:020d}",
        "scope": "call",
        "ttl_seconds": 60,
    }
    r = httpx.post(
        f"{BROKER_URL}/v1/issue",
        json=payload,
        headers={"X-Mintkey-Service-Token": MCP_SERVICE_TOKEN},
        timeout=10,
    )
    assert r.status_code == 200, (
        f"broker /v1/issue failed: {r.status_code} {r.text}"
    )
    body = r.json()
    assert "token" in body, f"broker response missing 'token': {body}"
    assert "expires_at" in body, f"broker response missing 'expires_at': {body}"

    jwt = body["token"]
    header, claims = _decode_jwt_parts(jwt)

    # Header assertions (ADR-0006)
    assert header.get("alg") == "EdDSA", (
        f"broker JWT alg={header.get('alg')!r}, expected EdDSA (ADR-0006)"
    )
    assert "kid" in header, f"broker JWT header missing kid: {header}"

    # Payload assertions (ADR-0006 / ADR-0017.11)
    assert claims.get("iss") == "mintkey/broker", (
        f"broker JWT iss={claims.get('iss')!r}, expected 'mintkey/broker'"
    )
    assert claims.get("sub"), f"broker JWT missing sub: {claims}"
    assert claims.get("aud"), f"broker JWT missing aud: {claims}"
    assert claims.get("tnt"), f"broker JWT missing tnt: {claims}"
    assert claims.get("scope") == "call", f"broker JWT scope unexpected: {claims}"
    jti = claims.get("jti", "")
    assert jti.startswith("jti_"), (
        f"broker JWT jti={jti!r}, expected 'jti_' prefix (ADR-0017.11)"
    )
    exp = claims.get("exp", 0)
    assert exp > time.time(), f"broker JWT already expired (exp={exp})"

    # Security: plaintext secret must not appear in token
    assert payload["agent_id"] not in jwt, "agent_id leaked into JWT token value"


# ===========================================================================
# Smoke test 2: Vault Adapter
# ===========================================================================


@INTEGRATION
def test_vault_adapter_smoke() -> None:
    """
    Smoke: gRPC PutCredential → GetCredential round-trip.

    Asserts:
      - PutCredential returns a key_version >= 1
      - GetCredential returns value == stored plaintext
      - Subsequent PutCredential increments key_version by exactly 1

    The vault-adapter is exposed on localhost:8084 (docker-compose port map).

    Sources: WS-4; ADR-0011; T-1.3.1.
    """
    ts = int(time.time())
    tenant_id = f"tenant_VAULTSMOKE{ts:015d}"
    service_id = f"svc_VAULTSMOKE{ts:015d}"
    plaintext = f"vault-smoke-secret-{ts}"

    channel = grpc.insecure_channel(VAULT_GRPC)
    stub = vault_pb2_grpc.VaultAdapterStub(channel)

    try:
        # --- Put v1 ---
        put1 = stub.PutCredential(
            vault_pb2.PutCredentialRequest(
                tenant_id=tenant_id,
                service_id=service_id,
                auth_scheme=vault_pb2.AUTH_SCHEME_API_KEY_HEADER,
                value=plaintext.encode(),
                caller_actor_id="ws4-smoke-test",
                target_url="http://mock-backend:8999",
            ),
            timeout=10,
        )
        assert put1.key_version >= 1, (
            f"PutCredential returned key_version={put1.key_version}, expected >= 1"
        )
        v1 = put1.key_version

        # --- Get v1 ---
        get1 = stub.GetCredential(
            vault_pb2.GetCredentialRequest(
                tenant_id=tenant_id,
                service_id=service_id,
                key_version=0,  # 0 = current
                caller_actor_id="ws4-smoke-test",
            ),
            timeout=10,
        )
        returned_plaintext = get1.value.decode()
        assert returned_plaintext == plaintext, (
            f"GetCredential returned {returned_plaintext!r}, expected {plaintext!r}"
        )
        assert get1.returned_key_version == v1, (
            f"returned_key_version={get1.returned_key_version}, expected {v1}"
        )

        # --- Put v2 (rotation) — key_version must increment by 1 ---
        plaintext2 = f"vault-smoke-secret-v2-{ts}"
        put2 = stub.PutCredential(
            vault_pb2.PutCredentialRequest(
                tenant_id=tenant_id,
                service_id=service_id,
                auth_scheme=vault_pb2.AUTH_SCHEME_API_KEY_HEADER,
                value=plaintext2.encode(),
                caller_actor_id="ws4-smoke-test",
                target_url="http://mock-backend:8999",
            ),
            timeout=10,
        )
        assert put2.key_version == v1 + 1, (
            f"Rotation: expected key_version={v1+1}, got {put2.key_version}"
        )

        # Confirm v2 is now current
        get2 = stub.GetCredential(
            vault_pb2.GetCredentialRequest(
                tenant_id=tenant_id,
                service_id=service_id,
                key_version=0,
                caller_actor_id="ws4-smoke-test",
            ),
            timeout=10,
        )
        assert get2.value.decode() == plaintext2, (
            f"After rotation, GetCredential returned {get2.value.decode()!r}, "
            f"expected {plaintext2!r}"
        )
        assert get2.returned_key_version == v1 + 1, (
            f"After rotation, returned_key_version={get2.returned_key_version}"
        )

    finally:
        channel.close()


# ===========================================================================
# Smoke test 3: Proxy Plugin (via Kong)
# ===========================================================================


@INTEGRATION
def test_proxy_plugin_smoke() -> None:
    """
    Smoke: JWT → Kong → proxy-plugin → vault-adapter → mock-backend returns 200.

    Asserts:
      - Kong route for the service exists after kong-syncer push
      - Proxy returns 200
      - mock-backend received_key == registered secret value (credential injected)
      - JWT is NOT echoed in the mock-backend response (proxy strips it)

    Sources: WS-4; ADR-0004; ADR-0006; ADR-0014.4; WS-9.
    """
    ts = int(time.time())
    secret_value = f"ws4-proxy-smoke-{ts}"

    with httpx.Client(timeout=30) as client:
        tenant_id, csrf = _admin_login(client)
        api_key, agent_db_id, service_uuid, csrf = _create_agent_and_service(
            client, tenant_id, csrf, ts, secret_value
        )

        # Request JWT via MCP
        disc_r = client.get(
            f"{BASE_MCP}/v1/tools/discover",
            headers={"X-API-Key": api_key},
        )
        assert disc_r.status_code == 200, f"discover failed: {disc_r.status_code} {disc_r.text}"
        disc_services = disc_r.json().get("services", [])
        svc_entry = next(
            (s for s in disc_services if service_uuid in str(s.get("id", ""))),
            None,
        )
        # Fallback: match by name prefix
        if svc_entry is None:
            svc_entry = next(
                (s for s in disc_services if str(s.get("name", "")).startswith("ws4-proxy-smoke-svc")),
                None,
            )
        assert svc_entry is not None, (
            f"Service {service_uuid!r} not found in discover response: {disc_services}"
        )

        tok_r = client.post(
            f"{BASE_MCP}/v1/tools/request_token",
            json={"service_id": svc_entry["id"], "action": "call"},
            headers={"X-API-Key": api_key},
        )
        assert tok_r.status_code == 200, f"request_token failed: {tok_r.status_code} {tok_r.text}"
        jwt = tok_r.json()["token"]

        # Wait for kong-syncer
        assert _wait_for_kong_route(service_uuid), (
            f"Kong route /v1/call/{service_uuid} not pushed after 10s (check kong-syncer logs)"
        )

        # Hit the proxy through Kong
        proxy_r = httpx.get(
            f"{BASE_KONG}/v1/call/{service_uuid}/api-key-header",
            headers={"Authorization": f"Bearer {jwt}"},
            timeout=15,
        )
        assert proxy_r.status_code == 200, (
            f"proxy_plugin_smoke: expected 200, got {proxy_r.status_code}\n{proxy_r.text}"
        )
        proxy_body = proxy_r.json()
        assert proxy_body.get("received_key") == secret_value, (
            f"mock-backend received wrong credential: "
            f"expected {secret_value!r}, got {proxy_body.get('received_key')!r}"
        )
        # JWT must NOT be echoed back (proxy strips the Authorization header)
        assert jwt not in proxy_r.text, (
            "SECURITY: JWT leaked in mock-backend response — proxy must strip Authorization"
        )


# ===========================================================================
# Smoke test 4: Kong admin / status
# ===========================================================================


@INTEGRATION
def test_kong_smoke() -> None:
    """
    Smoke: Kong admin API responds and route table is reachable.

    Asserts:
      - GET http://localhost:8001/ returns 200 (Kong root, no auth required in DB-less dev mode)
      - Response contains 'node_id' or 'version' (Kong admin root fields)
      - GET http://localhost:8001/routes returns 200 with a 'data' list
      - At least one /v1/call/<uuid> route is present (pushed by kong-syncer)

    Note: the static /proxy/ route from the initial kong.yml is replaced when
    kong-syncer pushes its dynamically-generated declarative config via PATCH /config.
    After a stack has been running with services, the route table contains only
    /v1/call/<uuid> entries; the /proxy/ bootstrap route is no longer present.

    Sources: WS-4; ADR-0007; services/kong-syncer/internal/kong/yaml.go.
    """
    # Kong admin root
    r = httpx.get(f"{KONG_ADMIN}/", timeout=10)
    assert r.status_code == 200, (
        f"kong_smoke: admin root returned {r.status_code}"
    )
    body = r.json()
    assert "version" in body or "node_id" in body, (
        f"kong_smoke: admin root missing 'version'/'node_id': {list(body.keys())}"
    )

    # Route table reachable
    routes_r = httpx.get(f"{KONG_ADMIN}/routes?size=100", timeout=10)
    assert routes_r.status_code == 200, (
        f"kong_smoke: GET /routes returned {routes_r.status_code}"
    )
    routes_body = routes_r.json()
    routes_data = routes_body.get("data", [])
    assert isinstance(routes_data, list), (
        f"kong_smoke: expected 'data' list in routes response"
    )
    assert len(routes_data) > 0, (
        f"kong_smoke: Kong route table is empty — kong-syncer may not have pushed routes yet"
    )

    # At least one /v1/call/<uuid> route must be present (kong-syncer generated)
    has_call_route = any(
        any("/v1/call/" in (p or "") for p in (route.get("paths") or []))
        for route in routes_data
    )
    assert has_call_route, (
        f"kong_smoke: no /v1/call/<uuid> route found in Kong route table. "
        f"kong-syncer may not have pushed any services yet. "
        f"Sample paths: {[route.get('paths') for route in routes_data[:5]]}"
    )
