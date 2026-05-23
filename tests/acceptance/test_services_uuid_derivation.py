"""
R12 regression tests — service UUID derivation + svc_ decode in create_api_key.

Covers:
  1. create_service (post-R12) derives internal_id UUID from ULID bits, so
     _wire_id_to_uuid(svc_wire, "svc_") resolves directly to the stored DB UUID.
  2. create_api_key with svc_ wire-form (was 500; now 201 + mk_svckey_...).
  3. grant_permission refactored to use shared _resolve_service_uuid helper (primary path
     via _wire_id_to_uuid for new services; audit fallback for old pre-R12 services).
  4. Full end-to-end chain: service → agent → grant (wire-form svc_) → api-key → 201.

Source: R12; ADR-0017.11; mirrors R8-redux for agents.
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


# ---------------------------------------------------------------------------
# Unit assertions (always run) — source-level checks
# ---------------------------------------------------------------------------


def test_create_service_derives_uuid_from_ulid() -> None:
    """
    create_service must derive internal_id from the ULID bits of _new_svc_id(),
    not from an independent uuid.uuid4().  Mirror of R8-redux for agents.

    Source: R12; services.py:214-226; ADR-0017.11.
    """
    services_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "services.py"
    assert services_py.exists(), f"services.py not found at {services_py}"
    src = services_py.read_text()

    create_fn_idx = src.find("async def create_service(")
    assert create_fn_idx >= 0, "create_service not found in services.py"
    next_fn_idx = src.find("\n@router.", create_fn_idx + 1)
    fn_body = src[create_fn_idx:next_fn_idx] if next_fn_idx > 0 else src[create_fn_idx:]

    # Must NOT assign internal_id via uuid.uuid4() (only acceptable usage is in comments)
    # Check actual assignment pattern - not in a comment
    import re
    bad_pattern = re.search(r"^\s+internal_id\s*=\s*uuid\.uuid4\(\)", fn_body, re.MULTILINE)
    assert bad_pattern is None, (
        "create_service must not assign internal_id = uuid.uuid4(). "
        "R12 requires deriving internal_id from the ULID bits of _new_svc_id() — R12."
    )
    # Must derive internal_id from _crockford_tail (or similar variable)
    assert "_crockford_tail" in fn_body or "svc_id[len" in fn_body, (
        "create_service must decode the Crockford tail of svc_id into the internal_id UUID — R12."
    )
    # Must use uuid.UUID(int=...) to derive internal_id
    assert "uuid.UUID(int=" in fn_body, (
        "create_service must call uuid.UUID(int=<decoded_val>) to derive internal_id — R12."
    )


def test_create_api_key_decodes_svc_wire_form() -> None:
    """
    create_api_key must decode the svc_ wire-form before binding to the permission-check
    SELECT and the INSERT.  Without this, passing svc_<26-Crockford> to a UUID column
    raises: ValueError: invalid UUID 'svc_...': length must be between 32..36 characters.

    Source: R12; api_keys.py create_api_key; ADR-0017.11.
    """
    api_keys_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "api_keys.py"
    assert api_keys_py.exists()
    src = api_keys_py.read_text()

    fn_idx = src.find("async def create_api_key(")
    assert fn_idx >= 0, "create_api_key not found in api_keys.py"
    next_fn_idx = src.find("\n@router.", fn_idx + 1)
    fn_body = src[fn_idx:next_fn_idx] if next_fn_idx > 0 else src[fn_idx:]

    # Must decode svc_ form; must not bind body.service_id directly to :sid
    assert "svc_uuid" in fn_body or "_decode_agent_wire_id" in fn_body, (
        "create_api_key must decode body.service_id (svc_ wire-form) before SQL binding — R12."
    )
    # The raw body.service_id must not be bound to SQL :sid
    assert '"sid": body.service_id' not in fn_body and "'sid': body.service_id" not in fn_body, (
        "create_api_key must NOT bind body.service_id directly to :sid — decode first — R12."
    )


def test_resolve_service_uuid_helper_exists() -> None:
    """
    _resolve_service_uuid must exist in permissions.py.
    It is the canonical svc_ → DB UUID translator used by grant_permission.

    Source: R12; permissions.py; ADR-0017.11.
    """
    permissions_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "permissions.py"
    assert permissions_py.exists()
    src = permissions_py.read_text()

    assert "_resolve_service_uuid" in src, (
        "_resolve_service_uuid helper must exist in permissions.py — R12."
    )
    # Must try _decode_agent_wire_id primary path
    helper_idx = src.find("async def _resolve_service_uuid(")
    assert helper_idx >= 0, "async def _resolve_service_uuid not found in permissions.py"
    next_fn_idx = src.find("\nasync def ", helper_idx + 1)
    helper_body = src[helper_idx:next_fn_idx] if next_fn_idx > 0 else src[helper_idx:]

    assert "_decode_agent_wire_id" in helper_body or "_wire_id_to_uuid" in helper_body, (
        "_resolve_service_uuid must call _decode_agent_wire_id / _wire_id_to_uuid for primary path — R12."
    )
    # Must have fallback audit_events lookup for pre-R12 services
    assert "audit_events" in helper_body, (
        "_resolve_service_uuid must have audit_events fallback for pre-R12 services — R12."
    )


def test_grant_permission_uses_resolve_helper() -> None:
    """
    grant_permission must call _resolve_service_uuid (not inline the audit SQL).

    Source: R12; permissions.py grant_permission; ADR-0017.11.
    """
    permissions_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "permissions.py"
    src = permissions_py.read_text()

    grant_fn_idx = src.find("async def grant_permission(")
    assert grant_fn_idx >= 0
    next_fn_idx = src.find("\n@router.", grant_fn_idx + 1)
    fn_body = src[grant_fn_idx:next_fn_idx] if next_fn_idx > 0 else src[grant_fn_idx:]

    assert "_resolve_service_uuid" in fn_body, (
        "grant_permission must call _resolve_service_uuid helper — R12."
    )
    # Must not have inline audit_events SQL (that's in the helper now, not inlined)
    # Specifically the old Crockford block that duplicated the helper logic should be gone
    assert "hex_part = svc_input[4:]" not in fn_body, (
        "grant_permission must not contain inline hex_part decoding — moved to _resolve_service_uuid — R12."
    )


# ===========================================================================
# Integration tests (requires docker-compose stack)
# ===========================================================================


def _login(client: httpx.Client) -> tuple[str, str]:
    """Login; return (tenant_id, csrf_token)."""
    r = client.post(
        f"{BASE_API}/v1/auth/internal-login",
        json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["tenant_id"], client.cookies.get("csrf_token", "")


def _decode_crockford_uuid(wire_id: str, prefix: str) -> str:
    """Replicate _wire_id_to_uuid for 26-char Crockford form."""
    _CK = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    tail = wire_id[len(prefix):]
    if len(tail) == 26:
        val = 0
        for ch in tail.upper():
            val = (val << 5) | _CK.index(ch)
        val &= (1 << 128) - 1
        h = f"{val:032x}"
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    if len(tail) == 32:
        return f"{tail[:8]}-{tail[8:12]}-{tail[12:16]}-{tail[16:20]}-{tail[20:]}"
    return wire_id


def _db_select(query: str) -> str:
    result = subprocess.run(
        ["docker", "exec", "mintkey-postgres-1",
         "psql", "-U", "mintkey_migrate", "-d", "mintkey",
         "-t", "-c", query],
        capture_output=True, text=True, timeout=15, check=True,
    )
    return result.stdout.strip()


@INTEGRATION
def test_create_service_uuid_derivation_probe() -> None:
    """
    Post-R12: synthesise a service; verify that the DB row's UUID equals what
    _wire_id_to_uuid(svc_wire, "svc_") would decode — no audit lookup needed.

    Source: R12 Change 1.
    """
    ts = int(time.time())
    with httpx.Client(timeout=30) as client:
        tenant_id, csrf = _login(client)
        r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services",
            json={
                "name": f"r12-probe-{ts}",
                "base_url": "https://r12-probe.example.com",
                "auth_scheme": "bearer",
            },
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert r.status_code == 201, f"create_service failed: {r.status_code} {r.text}"
        wire_svc_id = r.json()["id"]
        assert wire_svc_id.startswith("svc_"), f"Expected svc_ prefix: {wire_svc_id}"

        # Decode via our replicated helper
        decoded_uuid = _decode_crockford_uuid(wire_svc_id, "svc_")

        # Verify the row exists with that UUID
        row = _db_select(f"SELECT id FROM services WHERE id = '{decoded_uuid}';")
        assert row == decoded_uuid, (
            f"R12 derivation FAILED: decoded UUID {decoded_uuid!r} does not match "
            f"any row in services table. DB returned: {row!r}. "
            f"create_service must derive internal_id from the same ULID bits as the wire ID."
        )


@INTEGRATION
def test_create_api_key_with_svc_wire_form_post_r12() -> None:
    """
    Post-R12: create service (wire-form svc_<26-Crockford>) → agent → grant → api-key.
    create_api_key with svc_ wire-form must return 201 + mk_svckey_... (was 500 before R12).

    Source: R12 Change 2.
    """
    ts = int(time.time())
    test_start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    with httpx.Client(timeout=30) as client:
        tenant_id, csrf = _login(client)

        # Create service (post-R12)
        svc_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services",
            json={
                "name": f"r12-apikey-svc-{ts}",
                "base_url": "https://r12-apikey.example.com",
                "auth_scheme": "bearer",
            },
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert svc_r.status_code == 201, f"service: {svc_r.status_code} {svc_r.text}"
        wire_svc_id = svc_r.json()["id"]

        # Create agent
        agent_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents",
            json={"name": f"r12-apikey-agent-{ts}"},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert agent_r.status_code == 201, f"agent: {agent_r.status_code} {agent_r.text}"
        wire_agent_id = agent_r.json()["id"]

        # Grant with wire-form svc_ (Change 3 — uses _resolve_service_uuid primary path)
        grant_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/permissions",
            json={"service_id": wire_svc_id, "action": "read"},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert grant_r.status_code == 201, f"grant: {grant_r.status_code} {grant_r.text}"

        # Create API key with svc_ wire-form (was 500 before R12 — Change 2)
        apikey_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{wire_agent_id}/api-keys",
            json={"service_id": wire_svc_id, "allowed_actions": ["read"]},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert apikey_r.status_code == 201, (
            f"R12 REGRESSION: create_api_key returned {apikey_r.status_code} (expected 201).\n"
            f"Response: {apikey_r.text}\n"
            "Root cause (pre-fix): create_api_key did not decode svc_ wire-form before SQL — R12."
        )
        apikey_body = apikey_r.json()
        assert "plaintext_key" in apikey_body, f"Missing plaintext_key: {apikey_body}"
        assert apikey_body["plaintext_key"].startswith("mk_svckey_"), (
            f"plaintext_key must start with mk_svckey_: {apikey_body['plaintext_key']}"
        )

        # Zero 500s in logs for our test IDs
        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True, text=True, timeout=15,
        )
        combined = log_result.stdout + log_result.stderr
        error_lines = [
            ln for ln in combined.splitlines()
            if ("500" in ln or "invalid input syntax" in ln or "ValueError" in ln)
            and (wire_svc_id in ln or wire_agent_id in ln)
        ]
        assert len(error_lines) == 0, (
            f"Found {len(error_lines)} 500/error log lines for test IDs:\n"
            + "\n".join(error_lines[:5])
        )
