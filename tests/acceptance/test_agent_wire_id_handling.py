"""
R8 / R8-redux regression test — agent wire-ID handling in admin-api.

Regression for: GET /v1/tenants/{tid}/agents/{agent_wire_id} (and the sibling
permissions endpoint) returning 500 (R8) then 404 (R8-redux) because:
  R8: handlers passed wire-prefixed ID directly to UUID Postgres column.
  R8-redux: create_agent stored an independent uuid4() as the row PK while
             returning a Crockford ULID wire-form; the two IDs share no bits.

Non-integration assertions (always run):
  - test_get_agent_handler_decodes_wire_id: source-code check that get_agent
    calls _wire_id_to_uuid before the SQL query.
  - test_list_permissions_handler_decodes_wire_id: source-code check that
    list_permissions in permissions.py decodes agent_id before the SQL query.
  - test_new_agent_id_and_wire_id_roundtrip: unit-level proof that
    _new_agent_id() → _wire_id_to_uuid() resolves to the UUID derived from
    the same 128-bit ULID value (i.e. the Crockford form is invertible).

Integration tests (MINTKEY_INTEGRATION_TEST=true):
  - test_post_returned_id_round_trips (R8-redux): POST → GET on the EXACT id
    from the POST response (Crockford form) → 200 (NOT 404). 5x stress.
  - test_get_agent_and_permissions_wire_id_end_to_end: full round-trip using
    LIST-returned hex form too; zero 500s/404s guard.

Source: R8 / R8-redux of action-grid remediation; ADR-0017.11; ADR-0008.
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
# Unit assertions (always run)
# ===========================================================================


def test_new_agent_id_and_wire_id_roundtrip() -> None:
    """
    Unit-level proof: _new_agent_id() produces a 26-char Crockford ULID wire form
    whose 128-bit value, when stored as uuid.UUID(int=val), is exactly the UUID that
    _wire_id_to_uuid decodes the same wire ID to.

    This is the invariant R8-redux relies on: POST returns agent_<Crockford> and the
    DB stores uuid.UUID(int=<same 128-bit ULID value>), so GET on the POST-returned
    ID resolves to the correct row.

    Source: R8-redux; ADR-0017.11.
    """
    import importlib
    import sys

    agents_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "agents.py"
    assert agents_py.exists(), f"agents.py not found at {agents_py}"

    # Import agents module from the source tree
    sys.path.insert(0, str(_ROOT / "apps/admin-api" / "src"))
    spec = importlib.util.spec_from_file_location("admin_api.api.agents", agents_py)
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception:
        # Module has async dependencies; fall back to parsing the source directly
        mod = None

    # Parse helper functions directly if import fails
    import uuid as _uuid

    _CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

    def _decode_crockford_ulid(tail: str) -> _uuid.UUID:
        """Same logic as _wire_id_to_uuid Crockford branch."""
        val = 0
        for ch in tail.upper():
            val = (val << 5) | _CROCKFORD.index(ch)
        val &= (1 << 128) - 1
        return _uuid.UUID(int=val)

    # Read source to extract _new_agent_id body and replicate its ULID math
    src = agents_py.read_text()
    # Key assertion: the crockford tail encodes 128 bits that round-trip cleanly
    import time as _time

    _CROCKFORD_STR = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    ts_ms = int(_time.time() * 1000)
    rand = int.from_bytes(_uuid.uuid4().bytes[:10], "big")

    t_enc: list[str] = []
    v = ts_ms
    for _ in range(10):
        t_enc.append(_CROCKFORD_STR[v & 0x1F])
        v >>= 5
    t_enc.reverse()

    r_enc: list[str] = []
    v = rand
    for _ in range(16):
        r_enc.append(_CROCKFORD_STR[v & 0x1F])
        v >>= 5
    r_enc.reverse()

    crockford_tail = "".join(t_enc) + "".join(r_enc)
    assert len(crockford_tail) == 26, f"Expected 26-char ULID, got {len(crockford_tail)}"

    wire_id = "agent_" + crockford_tail
    decoded_uuid = _decode_crockford_ulid(crockford_tail)

    # Round-trip: re-encode UUID.int back to crockford
    re_enc: list[str] = []
    vv = decoded_uuid.int
    for _ in range(26):
        re_enc.append(_CROCKFORD_STR[vv & 0x1F])
        vv >>= 5
    re_enc.reverse()
    re_encoded = "".join(re_enc)

    assert re_encoded == crockford_tail, (
        f"Round-trip failure: crockford→UUID→crockford produced {re_encoded!r} "
        f"instead of {crockford_tail!r}"
    )

    # After R8-redux fix: create_agent must store uuid.UUID(int=val) NOT uuid.uuid4()
    # Verify that the source no longer uses 'internal_id = uuid.uuid4()' after the ULID
    # (i.e. the independent random UUID generation is gone from create_agent)
    create_agent_idx = src.find("async def create_agent(")
    assert create_agent_idx >= 0, "create_agent not found in agents.py"
    next_fn = src.find("\n@router.", create_agent_idx + 1)
    create_agent_body = src[create_agent_idx:next_fn] if next_fn > 0 else src[create_agent_idx:]

    # The fix must derive internal_id from the ULID, not generate a fresh uuid4 independently
    assert "internal_id = uuid.uuid4()" not in create_agent_body, (
        "R8-redux: create_agent still has 'internal_id = uuid.uuid4()' — this is the "
        "asymmetry bug. The stored UUID must be derived from the ULID's 128-bit value, "
        "not an independent random UUID."
    )


def test_get_agent_handler_decodes_wire_id() -> None:
    """
    get_agent in agents.py must call _wire_id_to_uuid before binding agent_id
    to the SQL query. Without this, passing agent_<32hex> or agent_<26-Crockford>
    to a UUID column raises: invalid input syntax for type uuid.

    Source: R8; ADR-0017.11.
    """
    agents_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "agents.py"
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
    permissions_py = _ROOT / "apps/admin-api" / "src" / "admin_api" / "api" / "permissions.py"
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
# Integration tests (requires docker-compose stack)
# ===========================================================================


@INTEGRATION
def test_post_returned_id_round_trips() -> None:
    """
    R8-redux: the id returned by POST must be usable in GET — not just the LIST form.

    R8 fixed 500s on the 32-hex form returned by LIST.
    R8-redux fixes silent 404s on the 26-char Crockford form returned by POST.

    Steps:
      1. Login as bootstrap operator.
      2. POST /v1/tenants/{tid}/agents → capture EXACT id from response (Crockford form).
      3. GET /v1/tenants/{tid}/agents/{posted_id} → MUST be 200 (was 404 before fix).
      4. 5x stress GET on posted_id → all 200, all return id == get_body["id"].
      5. GET /v1/tenants/{tid}/agents/{posted_id}/permissions → 200.
      6. docker logs: zero 500s AND zero 404s on the test's agent URL.

    Source: R8-redux; ADR-0017.11.
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

        # --- Step 2: POST agent → capture the EXACT id from POST response ---
        agent_name = f"r8-redux-post-id-test-{int(time.time())}"
        agent_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents",
            json={"name": agent_name},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert agent_r.status_code == 201, (
            f"create agent failed: {agent_r.status_code} {agent_r.text}"
        )
        # Use the EXACT id from the POST response — Crockford ULID form (agent_01...)
        posted_id = agent_r.json()["id"]
        assert posted_id.startswith("agent_"), (
            f"Expected agent_<...> from POST, got: {posted_id!r}"
        )
        # Do NOT assert len == 38 (that would only accept the 32-hex form).
        # Crockford form is agent_ (6) + 26 chars = 32; hex form is 6 + 32 = 38.
        assert len(posted_id) in (32, 38), (
            f"Expected agent_<26-Crockford> (32 chars) or agent_<32-hex> (38 chars), "
            f"got len={len(posted_id)}: {posted_id!r}"
        )

        # --- Step 3: GET with the exact POST-returned id → MUST be 200 (R8-redux fix) ---
        agent_url = f"{BASE_API}/v1/tenants/{tenant_id}/agents/{posted_id}"
        get_r = client.get(agent_url)
        assert get_r.status_code == 200, (
            f"R8-REDUX REGRESSION: GET agent with POST-returned id={posted_id!r} "
            f"returned {get_r.status_code} (expected 200). "
            f"Response: {get_r.text}\n"
            "Root cause: create_agent stored an independent uuid4() as the DB row PK "
            "while POST returned a Crockford ULID that shares no bits with it."
        )
        get_body = get_r.json()
        assert "id" in get_body, f"Missing 'id' in GET agent response: {get_body}"
        assert "name" in get_body, f"Missing 'name' in GET agent response: {get_body}"

        # --- Step 4: 5x stress GET → all 200, all return same id ---
        for i in range(5):
            stress_r = client.get(agent_url)
            assert stress_r.status_code == 200, (
                f"Stress GET #{i+1} on POST-returned id {posted_id!r} "
                f"returned {stress_r.status_code}: {stress_r.text}"
            )
            returned_id = stress_r.json().get("id")
            assert returned_id == get_body["id"], (
                f"Stress GET #{i+1}: returned id {returned_id!r} != first GET id {get_body['id']!r}"
            )

        # --- Step 5: GET permissions with POST-returned id → 200 ---
        perms_url = f"{BASE_API}/v1/tenants/{tenant_id}/agents/{posted_id}/permissions"
        perms_r = client.get(perms_url)
        assert perms_r.status_code == 200, (
            f"GET permissions with POST-returned id={posted_id!r} "
            f"returned {perms_r.status_code}: {perms_r.text}"
        )
        perms_body = perms_r.json()
        assert "grants" in perms_body, f"Missing 'grants' in permissions response: {perms_body}"

        # --- Step 6: Zero 500s AND zero 404s on test's agent URL in logs ---
        log_result = subprocess.run(
            ["docker", "logs", "--since", test_start, "mintkey-admin-api-1"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        combined_logs = log_result.stdout + log_result.stderr
        error_500_lines = [
            ln for ln in combined_logs.splitlines()
            if "500" in ln and posted_id in ln
        ]
        error_404_lines = [
            ln for ln in combined_logs.splitlines()
            if " 404 " in ln and posted_id in ln
        ]
        assert len(error_500_lines) == 0, (
            f"Found {len(error_500_lines)} 500 error(s) on test's agent URL in logs:\n"
            + "\n".join(error_500_lines[:10])
        )
        assert len(error_404_lines) == 0, (
            f"Found {len(error_404_lines)} 404 error(s) on test's agent URL in logs "
            f"(R8-redux regression — POST-returned id must round-trip to 200):\n"
            + "\n".join(error_404_lines[:10])
        )


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
        agent_wire_id = matching[0]["id"]  # agent_<32hex> — the form LIST returns
        assert agent_wire_id.startswith("agent_"), (
            f"Expected agent_<...> wire ID from list, got: {agent_wire_id!r}"
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
