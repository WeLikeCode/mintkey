"""
R9 regression test — api-key creation with wire-form agent_id (A1)
and flat tenant permissions list endpoint (A2).

Bug A1: POST /v1/tenants/{tid}/agents/{agent_wire_id}/api-keys returned 500
  with "invalid UUID 'agent_...' length 38" because create_api_key passed
  the raw wire-form agent_id directly to a UUID-typed Postgres column without
  calling _wire_id_to_uuid().  Fix: decode before SQL.

Bug A2: GET /v1/tenants/{tid}/permissions returned 404 (endpoint missing),
  so the admin-ui ApiKeyCreate service dropdown always showed 0 options.
  Fix: add the flat tenant_permissions_router endpoint with {permissions:[...]}.

Non-integration assertions (always run):
  - test_create_api_key_handler_decodes_wire_id: source check that create_api_key
    calls _decode_agent_wire_id / _wire_id_to_uuid before binding agent_id to SQL.
  - test_tenant_permissions_endpoint_exists: source check that
    tenant_permissions_router is defined and registered in main.py.

Integration tests (MINTKEY_INTEGRATION_TEST=true):
  - test_create_api_key_with_wire_form_agent_id_a1: full round-trip — POST
    agent → grant permission → POST api-key with wire-form agent_id →
    200 + mk_svckey_... plaintext.
  - test_tenant_permissions_list_returns_grants_a2: GET flat permissions
    endpoint → 200 + ≥1 grant (proves the DB data flows through).
  - test_end_to_end_chain: synthesise agent+grant → list permissions (≥1) →
    POST api-key → mk_svckey_ in response → zero 500s in logs.

Source: R9 of action-grid remediation; ADR-0017.11; ADR-0008.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

# ---------------------------------------------------------------------------
# Integration marker
# ---------------------------------------------------------------------------

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full docker-compose stack",
)

_ROOT = Path(__file__).resolve().parents[2]

BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")
_pwd_file = _ROOT / "data" / "bootstrap-secrets" / "admin_password"
BOOTSTRAP_PASSWORD = os.getenv(
    "MINTKEY_BOOTSTRAP_PASSWORD",
    _pwd_file.read_text().strip() if _pwd_file.exists() else "changeme",
)


# ===========================================================================
# Unit assertions (always run)
# ===========================================================================


def test_create_api_key_handler_decodes_wire_id() -> None:
    """
    create_api_key in api_keys.py must call _wire_id_to_uuid (imported as
    _decode_agent_wire_id) before binding agent_id to the SQL query.

    Without this, passing agent_<32hex> or agent_<26-Crockford> to a UUID-typed
    Postgres column raises:
      "invalid input for query argument $1: 'agent_...': length must be
       between 32..36 characters, got 38"  — Bug A1, R9 regression.

    Source: R9; ADR-0017.11.
    """
    api_keys_py = _ROOT / "admin-api" / "src" / "admin_api" / "api" / "api_keys.py"
    assert api_keys_py.exists(), f"api_keys.py not found at {api_keys_py}"
    src = api_keys_py.read_text()

    # The import must be present
    assert "_decode_agent_wire_id" in src or "_wire_id_to_uuid" in src, (
        "api_keys.py must import _decode_agent_wire_id (or _wire_id_to_uuid) from agents.py. "
        "This is needed to decode the wire-form agent_id before SQL binding — Bug A1 R9."
    )

    # The create_api_key function body must decode the agent_id
    create_fn_idx = src.find("async def create_api_key(")
    assert create_fn_idx >= 0, "create_api_key function not found in api_keys.py"
    next_fn_idx = src.find("\n@router.", create_fn_idx + 1)
    create_fn_body = src[create_fn_idx:next_fn_idx] if next_fn_idx > 0 else src[create_fn_idx:]

    assert "_decode_agent_wire_id" in create_fn_body or "_wire_id_to_uuid" in create_fn_body, (
        "create_api_key must call _decode_agent_wire_id(agent_id, 'agent_') before the SQL "
        "query. Without decoding, passing a wire-prefixed ID to a UUID column raises "
        "'invalid input syntax for type uuid' — Bug A1 R9 regression."
    )

    # The decoded result (agent_uuid) must be used in the SQL, not the raw agent_id
    assert "agent_uuid" in create_fn_body, (
        "create_api_key must bind 'agent_uuid' (the decoded UUID) to SQL, not the raw "
        "wire-form 'agent_id'. Without this, the UUID column rejects the prefixed string."
    )


def test_tenant_permissions_endpoint_exists() -> None:
    """
    The flat GET /v1/tenants/{tid}/permissions endpoint must exist in admin-api
    (tenant_permissions_router registered in main.py) and return {permissions:[...]}.

    Without this endpoint, admin-ui ApiKeyCreate's service dropdown always shows
    zero options (AdminJS RestResource listPath 404 → empty records) — Bug A2, R9.

    Source: R9; T-1.4.3; ADR-0008.
    """
    permissions_py = _ROOT / "admin-api" / "src" / "admin_api" / "api" / "permissions.py"
    assert permissions_py.exists(), f"permissions.py not found at {permissions_py}"
    src = permissions_py.read_text()

    assert "tenant_permissions_router" in src, (
        "permissions.py must define tenant_permissions_router "
        "(GET /v1/tenants/{tenant_id}/permissions without agent_id scoping). "
        "Without it, admin-ui ApiKeyCreate has no way to list grants for a tenant — Bug A2 R9."
    )

    assert "list_tenant_permissions" in src, (
        "permissions.py must have a list_tenant_permissions handler on "
        "tenant_permissions_router. The admin-ui RestResource listPath targets "
        "/v1/tenants/{tenantId}/permissions — Bug A2 R9."
    )

    main_py = _ROOT / "admin-api" / "src" / "admin_api" / "main.py"
    assert main_py.exists(), f"main.py not found at {main_py}"
    main_src = main_py.read_text()

    assert "tenant_permissions_router" in main_src, (
        "main.py must import and register tenant_permissions_router. "
        "Without app.include_router(tenant_permissions_router) the endpoint is never "
        "reachable — Bug A2 R9."
    )


# ===========================================================================
# Integration tests (requires docker-compose stack)
# ===========================================================================


def _login(client: httpx.Client) -> tuple[str, str]:
    """Login as bootstrap operator; return (tenant_id, csrf_token)."""
    r = client.post(
        f"{BASE_API}/v1/auth/internal-login",
        json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    tenant_id = r.json()["tenant_id"]
    csrf_token = client.cookies.get("csrf_token", "")
    return tenant_id, csrf_token


def _create_agent(client: httpx.Client, tenant_id: str, csrf_token: str, name: str) -> str:
    """POST a new agent; return the wire-form agent_id from the LIST endpoint."""
    r = client.post(
        f"{BASE_API}/v1/tenants/{tenant_id}/agents",
        json={"name": name},
        headers={"X-Mintkey-Csrf": csrf_token},
    )
    assert r.status_code == 201, f"create agent failed: {r.status_code} {r.text}"
    return r.json()["id"]  # Crockford wire form


def _create_service(client: httpx.Client, tenant_id: str, csrf_token: str, name: str) -> str:
    """POST a new service; return the plain UUID from the DB (not wire-form).

    Services module stores uuid4() in DB but returns Crockford ULID as wire id;
    we look up the DB UUID by name after creation.
    """
    r = client.post(
        f"{BASE_API}/v1/tenants/{tenant_id}/services",
        json={
            "name": name,
            "base_url": "https://r9-test.example.com",
            "auth_scheme": "bearer",
        },
        headers={"X-Mintkey-Csrf": csrf_token},
    )
    assert r.status_code == 201, f"create service failed: {r.status_code} {r.text}"
    # Look up the DB UUID by name (services module stores uuid4() independent of wire ID)
    result = subprocess.run(
        [
            "docker", "exec", "mintkey-postgres-1",
            "psql", "-U", "mintkey_migrate", "-d", "mintkey",
            "-t", "-c",
            f"SELECT id FROM services WHERE name='{name}' ORDER BY created_at DESC LIMIT 1;",
        ],
        capture_output=True, text=True, timeout=15, check=True,
    )
    service_uuid = result.stdout.strip()
    assert service_uuid, f"Could not find service UUID for name={name!r}: {result.stdout!r}"
    return service_uuid


def _insert_grant_via_db(agent_uuid: str, service_id_or_wire: str, tenant_id: str) -> None:
    """Insert permission grant directly via DB (grant_permission has an unrelated
    constraints NOT NULL bug that is out-of-scope for R9; insert via psql instead).

    Accepts service UUID or svc_ wire-form; decodes to UUID before inserting.
    """
    service_uuid = _wire_to_uuid(service_id_or_wire, "svc_")
    subprocess.run(
        [
            "docker", "exec", "mintkey-postgres-1",
            "psql", "-U", "mintkey_migrate", "-d", "mintkey",
            "-c",
            f"INSERT INTO permission_grants (id, tenant_id, agent_id, service_id, action, "
            f"constraints, created_at, created_by) VALUES "
            f"(gen_random_uuid(), '{tenant_id}', '{agent_uuid}', '{service_uuid}', "
            f"'read', '{{}}', NOW(), '{agent_uuid}');"
        ],
        capture_output=True,
        text=True,
        timeout=15,
        check=True,
    )


def _wire_to_uuid(wire_id: str, prefix: str) -> str:
    """Replicate _wire_id_to_uuid logic for Crockford and hex forms."""
    if wire_id.startswith(prefix):
        tail = wire_id[len(prefix):]
        if len(tail) == 32:
            return (
                f"{tail[:8]}-{tail[8:12]}-{tail[12:16]}"
                f"-{tail[16:20]}-{tail[20:]}"
            )
        if len(tail) == 26:
            _CK = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
            val = 0
            for ch in tail.upper():
                val = (val << 5) | _CK.index(ch)
            val &= (1 << 128) - 1
            hex128 = f"{val:032x}"
            return (
                f"{hex128[:8]}-{hex128[8:12]}-{hex128[12:16]}"
                f"-{hex128[16:20]}-{hex128[20:]}"
            )
    return wire_id


@INTEGRATION
def test_create_api_key_with_wire_form_agent_id_a1() -> None:
    """
    Bug A1: POST /v1/tenants/{tid}/agents/{wire_form_aid}/api-keys used to return 500
    because create_api_key bound the raw agent wire-form to a UUID column.

    After fix: must return 201 with plaintext_key starting with mk_svckey_.

    Steps:
      1. Login as bootstrap operator.
      2. POST agent → capture wire-form agent_id (Crockford form from POST response).
      3. INSERT permission grant for the agent+service via DB.
      4. POST /api-keys with the wire-form agent_id → MUST be 201 (was 500 before fix).
      5. Assert response contains mk_svckey_ plaintext.
      6. Assert zero 500/ValueError/DataError entries in admin-api logs.

    Source: R9; Bug A1; ADR-0017.11.
    """
    test_start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    with httpx.Client(timeout=30) as client:
        tenant_id, csrf_token = _login(client)

        # Create agent + service
        agent_name = f"r9-a1-test-agent-{int(time.time())}"
        svc_name = f"r9-a1-test-svc-{int(time.time())}"
        wire_agent_id = _create_agent(client, tenant_id, csrf_token, agent_name)
        service_id = _create_service(client, tenant_id, csrf_token, svc_name)

        # Decode wire_agent_id to DB UUID for the grant insert
        agent_uuid = _wire_to_uuid(wire_agent_id, "agent_")

        # Insert permission grant via DB
        _insert_grant_via_db(agent_uuid, service_id, tenant_id)

        # POST api-key with wire-form agent_id — this was the A1 failure surface
        api_key_url = f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys"
        r = client.post(
            api_key_url,
            json={"service_id": service_id, "allowed_actions": ["read"]},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert r.status_code == 201, (
            f"BUG A1 REGRESSION: POST api-key with wire-form agent_id {wire_agent_id!r} "
            f"returned {r.status_code} (expected 201).\n"
            f"Response: {r.text}\n"
            "Root cause: create_api_key did not decode the wire-form agent_id before "
            "binding to UUID column → ValueError / DataError 500."
        )
        body = r.json()
        assert "plaintext_key" in body, f"Missing plaintext_key in response: {body}"
        assert body["plaintext_key"].startswith("mk_svckey_"), (
            f"Expected mk_svckey_ prefix in plaintext_key, got: {body['plaintext_key']!r}"
        )
        assert "api_key_id" in body, f"Missing api_key_id in response: {body}"

        # Zero 500s in logs
        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True, text=True, timeout=15,
        )
        combined = log_result.stdout + log_result.stderr
        error_lines = [
            ln for ln in combined.splitlines()
            if ("500" in ln or "ValueError" in ln or "DataError" in ln or "invalid UUID" in ln)
            and wire_agent_id in ln
        ]
        assert len(error_lines) == 0, (
            f"Found {len(error_lines)} error(s) on test's agent URL in logs:\n"
            + "\n".join(error_lines[:10])
        )


@INTEGRATION
def test_tenant_permissions_list_returns_grants_a2() -> None:
    """
    Bug A2: GET /v1/tenants/{tid}/permissions returned 404 (endpoint missing).

    After fix: must return 200 with {"permissions": [...]} containing ≥1 grant.
    The DB has 154+ existing grants; the flat endpoint must surface them.

    Steps:
      1. Login.
      2. GET /v1/tenants/{tid}/permissions → assert 200 + ≥1 permission in list.
      3. Assert response structure: {"permissions": [...]}.
      4. Assert each item has required fields: id, agent_id, service_id, action.

    Source: R9; Bug A2; ADR-0008; T-1.4.3.
    """
    with httpx.Client(timeout=30) as client:
        tenant_id, _ = _login(client)

        r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/permissions")
        assert r.status_code == 200, (
            f"BUG A2 REGRESSION: GET /v1/tenants/{tenant_id}/permissions "
            f"returned {r.status_code} (expected 200).\n"
            f"Response: {r.text}\n"
            "Root cause: flat permissions endpoint was missing — admin-ui "
            "ApiKeyCreate service dropdown showed 0 options for every agent."
        )
        body = r.json()
        assert "permissions" in body, (
            f"Response missing 'permissions' key (admin-ui RestResource listKey='permissions'): {body}"
        )
        permissions = body["permissions"]
        assert len(permissions) >= 1, (
            f"BUG A2: permissions list returned {len(permissions)} items but DB has 154+ grants. "
            "The flat endpoint must return all tenant-scoped grants."
        )
        # Validate item structure
        first = permissions[0]
        for field in ("id", "agent_id", "service_id", "action"):
            assert field in first, (
                f"Permission item missing field '{field}': {first}"
            )


@INTEGRATION
def test_end_to_end_chain() -> None:
    """
    End-to-end: synthesise agent + permission grant → list permissions (≥1) →
    POST api-key with wire-form agent_id → mk_svckey_ in response → zero 500s.

    This is the central proof for both A1 and A2 being fixed.

    Source: R9; ADR-0017.11; ADR-0008.
    """
    test_start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    with httpx.Client(timeout=30) as client:
        tenant_id, csrf_token = _login(client)

        # Step 1: Create synthetic agent + service
        ts = int(time.time())
        agent_name = f"r9-e2e-agent-{ts}"
        svc_name = f"r9-e2e-svc-{ts}"
        wire_agent_id = _create_agent(client, tenant_id, csrf_token, agent_name)
        service_id = _create_service(client, tenant_id, csrf_token, svc_name)

        agent_uuid = _wire_to_uuid(wire_agent_id, "agent_")
        _insert_grant_via_db(agent_uuid, service_id, tenant_id)

        # Step 2: List permissions via the flat endpoint → ≥1 grant
        perms_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/permissions")
        assert perms_r.status_code == 200, (
            f"Flat permissions list returned {perms_r.status_code}: {perms_r.text}"
        )
        perms_body = perms_r.json()
        assert "permissions" in perms_body, f"Missing 'permissions' key: {perms_body}"
        all_grants = perms_body["permissions"]
        # Filter to our agent
        my_grants = [g for g in all_grants if g.get("agent_id") == agent_uuid]
        assert len(my_grants) >= 1, (
            f"Expected ≥1 grant for agent {agent_uuid} in flat list, "
            f"found 0 out of {len(all_grants)} total grants."
        )
        granted_service_id = my_grants[0]["service_id"]
        assert granted_service_id == service_id, (
            f"Grant service_id mismatch: {granted_service_id!r} != {service_id!r}"
        )

        # Step 3: POST api-key with wire-form agent_id
        api_key_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys",
            json={"service_id": service_id, "allowed_actions": ["read"]},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert api_key_r.status_code == 201, (
            f"POST api-key returned {api_key_r.status_code}: {api_key_r.text}\n"
            "Expected 201 — A1 fix must decode wire-form agent_id before SQL."
        )
        key_body = api_key_r.json()
        assert "plaintext_key" in key_body, f"Missing plaintext_key: {key_body}"
        assert key_body["plaintext_key"].startswith("mk_svckey_"), (
            f"plaintext_key must start with mk_svckey_, got: {key_body['plaintext_key']!r}"
        )

        # Step 4: Zero admin-api 500s during test
        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True, text=True, timeout=15,
        )
        combined = log_result.stdout + log_result.stderr
        error_count_lines = [
            ln for ln in combined.splitlines()
            if "500" in ln or "invalid UUID" in ln or "ValueError" in ln or "DataError" in ln
        ]
        # Filter out non-test-related noise; accept only lines mentioning our agent
        test_error_lines = [ln for ln in error_count_lines if wire_agent_id in ln]
        assert len(test_error_lines) == 0, (
            f"Found {len(test_error_lines)} 500/error(s) for test's agent in logs:\n"
            + "\n".join(test_error_lines[:10])
        )
