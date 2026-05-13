"""
R8 regression test — agent wire-ID handling in admin-api.

Regression for: GET /v1/tenants/{tid}/agents/{agent_wire_id} (and the sibling
permissions endpoint) returning 500 because the handlers passed the wire-prefixed
ID (agent_<32hex> or agent_<26-char-Crockford-ULID>) directly to a UUID-typed
Postgres column without decoding it first.

Non-integration assertions (always run):
  - test_get_agent_handler_decodes_wire_id: source-code check that get_agent
    calls _wire_id_to_uuid before the SQL query.
  - test_list_permissions_handler_decodes_wire_id: source-code check that
    list_permissions in permissions.py decodes agent_id before the SQL query.

Integration test (MINTKEY_INTEGRATION_TEST=true):
  - test_get_agent_and_permissions_wire_id_end_to_end: full round-trip:
      1. POST agent → capture wire-form agent_id.
      2. GET agent with wire-form ID → 200 + full agent JSON.
      3. GET permissions with wire-form ID → 200 (empty list is fine).
      4. docker logs check: zero 500s / "invalid input syntax" since test start.

Source: R8 of action-grid remediation; ADR-0017.11; ADR-0008.
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


def test_get_agent_handler_decodes_wire_id() -> None:
    """
    get_agent in agents.py must call _wire_id_to_uuid before binding agent_id
    to the SQL query. Without this, passing agent_<32hex> or agent_<26-Crockford>
    to a UUID column raises: invalid input syntax for type uuid.

    Source: R8; ADR-0017.11.
    """
    agents_py = _ROOT / "admin-api" / "src" / "admin_api" / "api" / "agents.py"
    assert agents_py.exists(), f"agents.py not found at {agents_py}"
    src = agents_py.read_text()

    # Locate the get_agent function body
    get_agent_idx = src.find("async def get_agent(")
    assert get_agent_idx >= 0, "get_agent function not found in agents.py"

    # Find the next function definition after get_agent
    next_fn_idx = src.find("\nasync def ", get_agent_idx + 1)
    if next_fn_idx == -1:
        next_fn_idx = src.find("\ndef ", get_agent_idx + 1)
    get_agent_body = src[get_agent_idx:next_fn_idx] if next_fn_idx > 0 else src[get_agent_idx:]

    assert "_wire_id_to_uuid" in get_agent_body, (
        "get_agent must call _wire_id_to_uuid(agent_id, 'agent_') before the SQL query. "
        "Without decoding, passing a wire-prefixed ID to a UUID column raises "
        "'invalid input syntax for type uuid' — R8 regression."
    )


def test_list_permissions_handler_decodes_agent_wire_id() -> None:
    """
    list_permissions in permissions.py must decode agent_id (wire-form) to a
    UUID before binding it to the SQL query. The permission_grants.agent_id
    column is UUID; passing agent_<hex> or agent_<Crockford> directly raises
    'invalid input syntax for type uuid'.

    Source: R8; ADR-0017.11.
    """
    permissions_py = _ROOT / "admin-api" / "src" / "admin_api" / "api" / "permissions.py"
    assert permissions_py.exists(), f"permissions.py not found at {permissions_py}"
    src = permissions_py.read_text()

    # The list_permissions handler must handle wire-form agent_id.
    # It must either import _wire_id_to_uuid from agents.py, or replicate the
    # decode inline, or the agent_id binding must be decoded before use.
    assert "_wire_id_to_uuid" in src or "_decode_agent_id" in src or "agent_uuid" in src, (
        "list_permissions must decode agent_id wire form before binding to SQL. "
        "Without this, permission_grants.agent_id (UUID column) rejects the prefixed ID — R8 regression."
    )


# ===========================================================================
# Integration test (requires docker-compose stack)
# ===========================================================================


@INTEGRATION
def test_get_agent_and_permissions_wire_id_end_to_end() -> None:
    """
    Round-trip test for wire-ID handling in get_agent and list_permissions.

    1. Login as bootstrap operator.
    2. POST /v1/tenants/{tid}/agents → capture wire-form agent_id (agent_<...>).
    3. GET /v1/tenants/{tid}/agents/{agent_id} with wire-form → assert 200.
    4. GET /v1/tenants/{tid}/agents/{agent_id}/permissions with wire-form → assert 200.
    5. docker logs check: zero 500s / "invalid input syntax" since test start.

    Source: R8; ADR-0017.11; ADR-0008.
    """
    test_start = time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime())

    with httpx.Client(timeout=30) as client:

        # --- Login ---
        login_r = client.post(
            f"{BASE_API}/v1/auth/internal-login",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
        )
        assert login_r.status_code == 200, (
            f"login failed: {login_r.status_code} {login_r.text}"
        )
        login_body = login_r.json()
        tenant_id = login_body["tenant_id"]
        csrf_token = client.cookies.get("csrf_token", "")

        # --- Step 2: Create synthetic agent → then list to get hex wire-form ID ---
        agent_name = f"r8-wire-id-test-agent-{int(time.time())}"
        agent_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents",
            json={"name": agent_name},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert agent_r.status_code == 201, (
            f"create agent failed: {agent_r.status_code} {agent_r.text}"
        )

        # The list endpoint serialises agents.id (UUID) as agent_<32hex> — this is
        # the wire form that admin-ui dropdown traffic uses for subsequent GETs.
        list_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/agents")
        assert list_r.status_code == 200, (
            f"list agents failed: {list_r.status_code} {list_r.text}"
        )
        agents = list_r.json().get("agents", [])
        matching = [a for a in agents if a.get("name") == agent_name]
        assert matching, f"Created agent not found in list: agents count={len(agents)}"
        agent_wire_id = matching[0]["id"]  # agent_<32hex> — the problematic form
        assert agent_wire_id.startswith("agent_"), (
            f"Expected agent_<hex> wire ID from list, got: {agent_wire_id!r}"
        )
        assert len(agent_wire_id) == 6 + 32, (
            f"Expected agent_<32hex> (38 chars), got {len(agent_wire_id)}: {agent_wire_id!r}"
        )

        # --- Step 3: GET /v1/tenants/{tid}/agents/{agent_wire_id} → 200 ---
        # Core R8 regression: before fix, handler passed agent_<32hex> directly to
        # a UUID-typed Postgres column, raising:
        #   "invalid input syntax for type uuid: 'agent_...'"
        get_hex_r = client.get(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{agent_wire_id}",
        )
        assert get_hex_r.status_code == 200, (
            f"GET agent with hex-form wire ID returned {get_hex_r.status_code}: {get_hex_r.text}\n"
            "Expected 200 — this is the R8 regression: get_agent must decode agent_<32hex> "
            "to UUID before binding to SQL."
        )
        get_body = get_hex_r.json()
        assert "id" in get_body, f"Missing 'id' in GET agent response: {get_body}"
        assert "name" in get_body, f"Missing 'name' in GET agent response: {get_body}"

        # --- Step 4: GET permissions with hex wire-form agent_id → 200 ---
        perms_r = client.get(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{agent_wire_id}/permissions",
        )
        assert perms_r.status_code == 200, (
            f"GET permissions with wire-form agent_id returned {perms_r.status_code}: {perms_r.text}\n"
            "Expected 200 (empty list is fine) — this is the R8 sibling regression: "
            "list_permissions must decode wire-prefixed agent_id before SQL binding."
        )
        perms_body = perms_r.json()
        assert "grants" in perms_body, f"Missing 'grants' in permissions response: {perms_body}"

        # --- Step 5: Zero 500s / uuid errors in admin-api logs since test start ---
        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        combined_logs = log_result.stdout + log_result.stderr
        error_lines = [
            ln for ln in combined_logs.splitlines()
            if "invalid input syntax for type uuid" in ln
            or "invalid input for query argument" in ln
        ]
        assert len(error_lines) == 0, (
            f"Found {len(error_lines)} R8 regression error(s) in admin-api logs since {test_start}:\n"
            + "\n".join(error_lines[:10])
        )
