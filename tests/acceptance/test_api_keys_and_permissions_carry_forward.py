"""
R11a carry-forward regression tests — wire-form decoder pattern applied to:
  Bug 1: permissions.py grant_permission passes raw svc_ wire-form to UUID column → 500.
          Also: missing constraints defaults to {} instead of NULL constraint violation.
  Bug 2: api_keys.py list_api_keys, get_api_key, revoke_api_key, rotate_api_key
          all bind raw wire-form agent_id to UUID column → 500.

Non-integration assertions (always run):
  - Source checks that grant_permission decodes service_id before SQL.
  - Source checks that the 4 api_keys handlers decode agent_id before SQL.

Integration tests (MINTKEY_INTEGRATION_TEST=true):
  - grant_permission with wire-form svc_ + no constraints → 201.
  - list_api_keys with wire-form agent_id → 200.
  - get_api_key with wire-form agent_id → 200.
  - revoke_api_key with wire-form agent_id → 200.
  - rotate_api_key with wire-form agent_id → 201.
  - Zero 500s in admin-api logs for all R11a-target URLs.

Source: R11a carry-forward of R9 reviewer findings; ADR-0017.11; ADR-0008.
"""
from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import httpx
import pytest

from mintkey_models.bootstrap_password import BootstrapPasswordError, read_bootstrap_password

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
try:
    BOOTSTRAP_PASSWORD = os.getenv(
        "MINTKEY_BOOTSTRAP_PASSWORD",
        read_bootstrap_password(_pwd_file) if _pwd_file.exists() else "changeme",
    )
except BootstrapPasswordError:
    BOOTSTRAP_PASSWORD = os.getenv("MINTKEY_BOOTSTRAP_PASSWORD", "changeme")


# ===========================================================================
# Unit assertions (always run) — source-level checks
# ===========================================================================


def test_grant_permission_decodes_service_wire_id() -> None:
    """
    grant_permission in permissions.py must call _wire_id_to_uuid (imported as
    _decode_agent_wire_id, or via the same helper) on body.service_id BEFORE
    binding to the SQL query.

    Without this, passing svc_<26-Crockford> to a UUID-typed Postgres column raises:
      ValueError: invalid UUID 'svc_...': length must be between 32..36 characters, got 30
    → Bug 1, R11a carry-forward.

    Source: R11a; permissions.py:345; ADR-0017.11.
    """
    permissions_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "permissions.py"
    assert permissions_py.exists(), f"permissions.py not found at {permissions_py}"
    src = permissions_py.read_text()

    # The decoder import must be present
    assert "_decode_agent_wire_id" in src or "_wire_id_to_uuid" in src, (
        "permissions.py must import _wire_id_to_uuid (or alias _decode_agent_wire_id) "
        "from agents.py to decode wire-form IDs — Bug 1 R11a."
    )

    # Locate grant_permission function body
    grant_fn_idx = src.find("async def grant_permission(")
    assert grant_fn_idx >= 0, "grant_permission function not found in permissions.py"
    next_fn_idx = src.find("\n@router.", grant_fn_idx + 1)
    grant_fn_body = src[grant_fn_idx:next_fn_idx] if next_fn_idx > 0 else src[grant_fn_idx:]

    # Must decode service_id before binding
    assert "_wire_id_to_uuid" in grant_fn_body or "_decode_agent_wire_id" in grant_fn_body or "svc_uuid" in grant_fn_body, (
        "grant_permission must call _wire_id_to_uuid(body.service_id, 'svc_') before SQL. "
        "Without decoding, svc_<ULID> passed to UUID column raises ValueError — Bug 1 R11a."
    )

    # Must bind decoded svc_uuid, not raw body.service_id
    assert "svc_uuid" in grant_fn_body, (
        "grant_permission must store decoded result in svc_uuid and bind that to SQL, "
        "not the raw body.service_id wire-form string — Bug 1 R11a."
    )


def test_grant_permission_defaults_constraints_to_empty_dict() -> None:
    """
    grant_permission must default constraints to {} when the caller omits the field,
    instead of inserting NULL which may fail or produce unexpected behaviour.

    Source: R11a carry-forward; permissions.py constraints handling.
    """
    permissions_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "permissions.py"
    src = permissions_py.read_text()

    grant_fn_idx = src.find("async def grant_permission(")
    assert grant_fn_idx >= 0
    next_fn_idx = src.find("\n@router.", grant_fn_idx + 1)
    grant_fn_body = src[grant_fn_idx:next_fn_idx] if next_fn_idx > 0 else src[grant_fn_idx:]

    # Must have fallback to {} when constraints is None/falsy
    assert "{}" in grant_fn_body or "or {}" in grant_fn_body or "if body.constraints" in grant_fn_body, (
        "grant_permission must default constraints to {} when caller omits the field. "
        "Inserting NULL can cause downstream serialization issues — Bug 1 R11a constraints."
    )


def test_list_api_keys_decodes_agent_wire_id() -> None:
    """
    list_api_keys must call _decode_agent_wire_id(agent_id, 'agent_') before binding
    agent_id to the :aid UUID column.

    Without this, passing agent_<26-Crockford> raises:
      ValueError: invalid UUID 'agent_...': length must be between 32..36 characters
    → Bug 2a, R11a carry-forward.

    Source: R11a; api_keys.py:~L351; ADR-0017.11.
    """
    api_keys_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "api_keys.py"
    assert api_keys_py.exists()
    src = api_keys_py.read_text()

    list_fn_idx = src.find("async def list_api_keys(")
    assert list_fn_idx >= 0, "list_api_keys function not found in api_keys.py"
    next_fn_idx = src.find("\n@router.", list_fn_idx + 1)
    fn_body = src[list_fn_idx:next_fn_idx] if next_fn_idx > 0 else src[list_fn_idx:]

    assert "_decode_agent_wire_id" in fn_body or "_wire_id_to_uuid" in fn_body, (
        "list_api_keys must call _decode_agent_wire_id(agent_id, 'agent_') before "
        "binding to SQL — Bug 2a R11a."
    )
    assert "agent_uuid" in fn_body, (
        "list_api_keys must bind agent_uuid (decoded) to SQL, not raw agent_id — Bug 2a R11a."
    )


def test_get_api_key_decodes_agent_wire_id() -> None:
    """
    get_api_key must decode wire-form agent_id before SQL bind — Bug 2b R11a.

    Source: R11a; api_keys.py:~L428; ADR-0017.11.
    """
    api_keys_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "api_keys.py"
    src = api_keys_py.read_text()

    fn_idx = src.find("async def get_api_key(")
    assert fn_idx >= 0
    next_fn_idx = src.find("\n@router.", fn_idx + 1)
    fn_body = src[fn_idx:next_fn_idx] if next_fn_idx > 0 else src[fn_idx:]

    assert "_decode_agent_wire_id" in fn_body or "_wire_id_to_uuid" in fn_body, (
        "get_api_key must call _decode_agent_wire_id(agent_id, 'agent_') before SQL — Bug 2b R11a."
    )
    assert "agent_uuid" in fn_body, (
        "get_api_key must bind agent_uuid to SQL — Bug 2b R11a."
    )


def test_revoke_api_key_decodes_agent_wire_id() -> None:
    """
    revoke_api_key must decode wire-form agent_id before SQL bind — Bug 2c R11a.

    Source: R11a; api_keys.py:~L480; ADR-0017.11.
    """
    api_keys_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "api_keys.py"
    src = api_keys_py.read_text()

    fn_idx = src.find("async def revoke_api_key(")
    assert fn_idx >= 0
    next_fn_idx = src.find("\n@router.", fn_idx + 1)
    fn_body = src[fn_idx:next_fn_idx] if next_fn_idx > 0 else src[fn_idx:]

    assert "_decode_agent_wire_id" in fn_body or "_wire_id_to_uuid" in fn_body, (
        "revoke_api_key must call _decode_agent_wire_id(agent_id, 'agent_') before SQL — Bug 2c R11a."
    )
    assert "agent_uuid" in fn_body, (
        "revoke_api_key must bind agent_uuid to SQL — Bug 2c R11a."
    )


def test_rotate_api_key_decodes_agent_wire_id() -> None:
    """
    rotate_api_key must decode wire-form agent_id before SQL bind — Bug 2d R11a.

    Source: R11a; api_keys.py:~L566; ADR-0017.11.
    """
    api_keys_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "api_keys.py"
    src = api_keys_py.read_text()

    fn_idx = src.find("async def rotate_api_key(")
    assert fn_idx >= 0
    next_fn_idx = src.find("\n@router.", fn_idx + 1)
    fn_body = src[fn_idx:next_fn_idx] if next_fn_idx > 0 else src[fn_idx:]

    assert "_decode_agent_wire_id" in fn_body or "_wire_id_to_uuid" in fn_body, (
        "rotate_api_key must call _decode_agent_wire_id(agent_id, 'agent_') before SQL — Bug 2d R11a."
    )
    assert "agent_uuid" in fn_body, (
        "rotate_api_key must bind agent_uuid to SQL — Bug 2d R11a."
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
    """POST a new agent; return the wire-form agent_id."""
    r = client.post(
        f"{BASE_API}/v1/tenants/{tenant_id}/agents",
        json={"name": name},
        headers={"X-Mintkey-Csrf": csrf_token},
    )
    assert r.status_code == 201, f"create agent failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _create_service_wire(client: httpx.Client, tenant_id: str, csrf_token: str, name: str) -> str:
    """POST a new service; return the wire-form svc_ ID."""
    r = client.post(
        f"{BASE_API}/v1/tenants/{tenant_id}/services",
        json={"name": name, "base_url": "https://r11a.example.com", "auth_scheme": "bearer"},
        headers={"X-Mintkey-Csrf": csrf_token},
    )
    assert r.status_code == 201, f"create service failed: {r.status_code} {r.text}"
    return r.json()["id"]


def _wire_to_uuid(wire_id: str, prefix: str) -> str:
    """Replicate _wire_id_to_uuid for Crockford and hex forms."""
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


def _get_service_db_uuid(svc_wire_id: str) -> str:
    """
    Look up the actual DB UUID for a service given its wire-form ID.

    Services store an independent uuid4() as the DB id; the wire ID (svc_<26-Crockford>
    ULID from create, or svc_<32-hex> from list) is not stored in services table.
    Resolves via audit_events payload svc_id field (same method as permissions.py R11a fix).
    """
    if svc_wire_id.startswith("svc_") and len(svc_wire_id) == 30:
        # 26-char Crockford ULID form from create endpoint — look up via audit_events
        result = subprocess.run(
            [
                "docker", "exec", "mintkey-postgres-1",
                "psql", "-U", "mintkey_migrate", "-d", "mintkey",
                "-t", "-c",
                f"SELECT target_id FROM audit_events WHERE event_type='service.registered'"
                f" AND payload->>'svc_id'='{svc_wire_id}' LIMIT 1;",
            ],
            capture_output=True, text=True, timeout=15, check=True,
        )
        return result.stdout.strip()
    # Otherwise decode as 32-hex or plain UUID
    return _wire_to_uuid(svc_wire_id, "svc_")


def _insert_grant_via_db(agent_uuid: str, service_wire_or_uuid: str, tenant_id: str) -> None:
    """Insert a permission grant directly via psql (bypasses grant_permission endpoint)."""
    # Resolve service wire-form to actual DB UUID
    if service_wire_or_uuid.startswith("svc_"):
        svc_uuid = _get_service_db_uuid(service_wire_or_uuid)
    else:
        svc_uuid = service_wire_or_uuid

    subprocess.run(
        [
            "docker", "exec", "mintkey-postgres-1",
            "psql", "-U", "mintkey_migrate", "-d", "mintkey",
            "-c",
            f"INSERT INTO permission_grants (id, tenant_id, agent_id, service_id, action, "
            f"constraints, created_at, created_by) VALUES "
            f"(gen_random_uuid(), '{tenant_id}', '{agent_uuid}', '{svc_uuid}', "
            f"'read', '{{}}', NOW(), '{agent_uuid}') ON CONFLICT DO NOTHING;",
        ],
        capture_output=True, text=True, timeout=15, check=True,
    )


@INTEGRATION
def test_grant_permission_wire_svc_no_constraints() -> None:
    """
    Bug 1: POST grant_permission with wire-form svc_ ID and no constraints field
    must return 201 (was 500: ValueError: invalid UUID 'svc_...').

    Source: R11a; permissions.py:345; ADR-0017.11.
    """
    test_start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    with httpx.Client(timeout=30) as client:
        tenant_id, csrf_token = _login(client)
        ts = int(time.time())
        wire_agent_id = _create_agent(client, tenant_id, csrf_token, f"r11a-perm-agent-{ts}")
        wire_svc_id = _create_service_wire(client, tenant_id, csrf_token, f"r11a-perm-svc-{ts}")

        # POST grant_permission with wire-form svc_ and NO constraints field
        grant_url = f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/permissions"
        r = client.post(
            grant_url,
            json={"service_id": wire_svc_id, "action": "call"},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert r.status_code == 201, (
            f"BUG 1 REGRESSION: POST grant_permission with wire svc_ returned "
            f"{r.status_code} (expected 201).\n"
            f"Response: {r.text}\n"
            "Root cause: grant_permission did not decode svc_ wire-form before SQL — R11a."
        )
        body = r.json()
        assert "id" in body, f"Missing 'id' in grant response: {body}"
        assert "service_id" in body, f"Missing 'service_id' in grant response: {body}"
        assert "action" in body, f"Missing 'action' in grant response: {body}"
        assert body["action"] == "call"

        # Constraints should be empty dict (not null)
        constraints_val = body.get("constraints")
        assert constraints_val is not None or constraints_val == {}, (
            f"constraints in response should be {{}} not null: {body}"
        )

        # Zero 500s in logs for this test's URLs
        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True, text=True, timeout=15,
        )
        combined = log_result.stdout + log_result.stderr
        error_lines = [
            ln for ln in combined.splitlines()
            if ("500" in ln or "ValueError" in ln or "invalid UUID" in ln)
            and (wire_svc_id in ln or wire_agent_id in ln)
        ]
        assert len(error_lines) == 0, (
            f"Found {len(error_lines)} 500/error(s) for test IDs in logs:\n"
            + "\n".join(error_lines[:5])
        )


@INTEGRATION
def test_list_api_keys_wire_agent_id() -> None:
    """
    Bug 2a: GET list_api_keys with wire-form agent_id must return 200 (was 500).

    Source: R11a; api_keys.py:~L351; ADR-0017.11.
    """
    test_start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    with httpx.Client(timeout=30) as client:
        tenant_id, csrf_token = _login(client)
        ts = int(time.time())
        wire_agent_id = _create_agent(client, tenant_id, csrf_token, f"r11a-list-agent-{ts}")
        wire_svc_id = _create_service_wire(client, tenant_id, csrf_token, f"r11a-list-svc-{ts}")

        agent_uuid = _wire_to_uuid(wire_agent_id, "agent_")
        _insert_grant_via_db(agent_uuid, wire_svc_id, tenant_id)

        list_url = f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys"
        r = client.get(list_url)
        assert r.status_code == 200, (
            f"BUG 2a REGRESSION: GET list_api_keys with wire agent_id returned "
            f"{r.status_code} (expected 200).\nResponse: {r.text}"
        )
        body = r.json()
        assert isinstance(body, list), f"Expected list response, got: {type(body)}"

        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True, text=True, timeout=15,
        )
        combined = log_result.stdout + log_result.stderr
        error_lines = [
            ln for ln in combined.splitlines()
            if ("500" in ln or "ValueError" in ln or "invalid UUID" in ln)
            and wire_agent_id in ln
        ]
        assert len(error_lines) == 0, (
            f"Found {len(error_lines)} 500/error(s) in logs:\n" + "\n".join(error_lines[:5])
        )


@INTEGRATION
def test_get_api_key_wire_agent_id() -> None:
    """
    Bug 2b: GET get_api_key with wire-form agent_id must return 200 (was 500).

    Source: R11a; api_keys.py:~L428; ADR-0017.11.
    """
    test_start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    with httpx.Client(timeout=30) as client:
        tenant_id, csrf_token = _login(client)
        ts = int(time.time())
        wire_agent_id = _create_agent(client, tenant_id, csrf_token, f"r11a-get-agent-{ts}")
        wire_svc_id = _create_service_wire(client, tenant_id, csrf_token, f"r11a-get-svc-{ts}")

        agent_uuid = _wire_to_uuid(wire_agent_id, "agent_")
        svc_db_uuid = _get_service_db_uuid(wire_svc_id)
        _insert_grant_via_db(agent_uuid, wire_svc_id, tenant_id)

        # Create key via create_api_key with plain DB UUID for service_id
        key_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys",
            json={"service_id": svc_db_uuid, "allowed_actions": ["read"]},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert key_r.status_code == 201, f"create_api_key failed: {key_r.status_code} {key_r.text}"

        # Get the key UUID from the list endpoint (list returns plain DB UUID)
        list_r = client.get(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys"
        )
        assert list_r.status_code == 200, f"list_api_keys failed: {list_r.status_code}"
        keys = list_r.json()
        assert len(keys) >= 1, f"Expected ≥1 key in list, got: {keys}"
        key_id = keys[0]["api_key_id"]  # plain DB UUID from list

        get_url = f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys/{key_id}"
        r = client.get(get_url)
        assert r.status_code == 200, (
            f"BUG 2b REGRESSION: GET get_api_key with wire agent_id returned "
            f"{r.status_code} (expected 200).\nResponse: {r.text}"
        )
        body = r.json()
        assert "api_key_id" in body, f"Missing api_key_id: {body}"

        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True, text=True, timeout=15,
        )
        combined = log_result.stdout + log_result.stderr
        error_lines = [
            ln for ln in combined.splitlines()
            if ("500" in ln or "ValueError" in ln or "invalid UUID" in ln)
            and wire_agent_id in ln
        ]
        assert len(error_lines) == 0, (
            f"Found {len(error_lines)} 500/error(s) in logs:\n" + "\n".join(error_lines[:5])
        )


@INTEGRATION
def test_revoke_api_key_wire_agent_id() -> None:
    """
    Bug 2c: POST revoke_api_key with wire-form agent_id must return 200 (was 500).

    Source: R11a; api_keys.py:~L480; ADR-0017.11.
    """
    test_start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    with httpx.Client(timeout=30) as client:
        tenant_id, csrf_token = _login(client)
        ts = int(time.time())
        wire_agent_id = _create_agent(client, tenant_id, csrf_token, f"r11a-revoke-agent-{ts}")
        wire_svc_id = _create_service_wire(client, tenant_id, csrf_token, f"r11a-revoke-svc-{ts}")

        agent_uuid = _wire_to_uuid(wire_agent_id, "agent_")
        svc_db_uuid = _get_service_db_uuid(wire_svc_id)
        _insert_grant_via_db(agent_uuid, wire_svc_id, tenant_id)

        key_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys",
            json={"service_id": svc_db_uuid, "allowed_actions": ["read"]},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert key_r.status_code == 201, f"create_api_key failed: {key_r.status_code} {key_r.text}"

        # Use key UUID from list (plain DB UUID form)
        list_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys")
        keys = list_r.json()
        key_id = keys[0]["api_key_id"]

        revoke_url = f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys/{key_id}/revoke"
        r = client.post(
            revoke_url,
            json={"reason": "r11a-revoke-test"},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert r.status_code == 200, (
            f"BUG 2c REGRESSION: POST revoke_api_key with wire agent_id returned "
            f"{r.status_code} (expected 200).\nResponse: {r.text}"
        )
        body = r.json()
        assert body.get("status") in ("revoked", "already_revoked"), (
            f"Unexpected revoke response: {body}"
        )

        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True, text=True, timeout=15,
        )
        combined = log_result.stdout + log_result.stderr
        error_lines = [
            ln for ln in combined.splitlines()
            if ("500" in ln or "ValueError" in ln or "invalid UUID" in ln)
            and wire_agent_id in ln
        ]
        assert len(error_lines) == 0, (
            f"Found {len(error_lines)} 500/error(s) in logs:\n" + "\n".join(error_lines[:5])
        )


@INTEGRATION
def test_rotate_api_key_wire_agent_id() -> None:
    """
    Bug 2d: POST rotate_api_key with wire-form agent_id must return 201 (was 500).

    Source: R11a; api_keys.py:~L566; ADR-0017.11.
    """
    test_start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    with httpx.Client(timeout=30) as client:
        tenant_id, csrf_token = _login(client)
        ts = int(time.time())
        wire_agent_id = _create_agent(client, tenant_id, csrf_token, f"r11a-rotate-agent-{ts}")
        wire_svc_id = _create_service_wire(client, tenant_id, csrf_token, f"r11a-rotate-svc-{ts}")

        agent_uuid = _wire_to_uuid(wire_agent_id, "agent_")
        svc_db_uuid = _get_service_db_uuid(wire_svc_id)
        _insert_grant_via_db(agent_uuid, wire_svc_id, tenant_id)

        key_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys",
            json={"service_id": svc_db_uuid, "allowed_actions": ["read"]},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert key_r.status_code == 201, f"create_api_key failed: {key_r.status_code} {key_r.text}"

        # Use key UUID from list (plain DB UUID form)
        list_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys")
        assert list_r.status_code == 200, f"list failed: {list_r.status_code} {list_r.text}"
        keys = list_r.json()
        assert len(keys) >= 1, f"Expected ≥1 key after create, got: {keys}\ncreate response was: {key_r.json()}"
        key_id = keys[0]["api_key_id"]

        rotate_url = f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys/{key_id}/rotate"
        r = client.post(rotate_url, headers={"X-Mintkey-Csrf": csrf_token})
        assert r.status_code == 201, (
            f"BUG 2d REGRESSION: POST rotate_api_key with wire agent_id returned "
            f"{r.status_code} (expected 201).\nResponse: {r.text}"
        )
        body = r.json()
        assert "plaintext_key" in body, f"Missing plaintext_key in rotate response: {body}"
        assert body["plaintext_key"].startswith("mk_svckey_"), (
            f"Expected mk_svckey_ prefix, got: {body['plaintext_key']!r}"
        )

        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True, text=True, timeout=15,
        )
        combined = log_result.stdout + log_result.stderr
        error_lines = [
            ln for ln in combined.splitlines()
            if ("500" in ln or "ValueError" in ln or "invalid UUID" in ln)
            and wire_agent_id in ln
        ]
        assert len(error_lines) == 0, (
            f"Found {len(error_lines)} 500/error(s) in logs:\n" + "\n".join(error_lines[:5])
        )
