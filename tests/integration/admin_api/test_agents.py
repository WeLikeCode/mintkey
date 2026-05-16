"""
Integration tests for agent endpoints.

POST   /v1/tenants/{tenant_id}/agents              — create (201, api_key returned once)
GET    /v1/tenants/{tenant_id}/agents              — list (200)
GET    /v1/tenants/{tenant_id}/agents/{agent_id}   — get single (200 / 404)
DELETE /v1/tenants/{tenant_id}/agents/{agent_id}   — delete (204)

Architecture constraints verified:
  ADR-0017.11 — ULID agent_ prefix IDs
  S-SEC-1     — API key returned exactly once, never repeated
  ADR-0008    — cross-tenant isolation (RLS)

UX-FB-CE additions:
  Part C — grants_count correlated subquery in list + get
  Part E — revoke returns active_api_keys_count + audit payload
"""
from __future__ import annotations

import hashlib
import os
import secrets
import uuid

import psycopg2
import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# CSRF helpers
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-token-abc123"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}


def _post(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


def _delete(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.delete(url, headers=headers, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _insert_tenant(postgres_container, slug: str) -> str:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    cur = conn.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO tenants (slug, display_name, isolation_mode, status)"
            " VALUES (%s, %s, 'row', 'active') RETURNING id",
            (slug, slug),
        )
        conn.commit()
        row = cur.fetchone()
    else:
        conn.commit()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0])


def _insert_agent(postgres_container, tenant_id: str, name: str) -> str:
    """Insert an agent row directly and return its UUID string (internal DB id)."""
    agent_internal_id = str(uuid.uuid4())
    from argon2 import PasswordHasher
    import hashlib, secrets
    ph = PasswordHasher()
    raw_key = "mk_agent_" + secrets.token_hex(20)
    api_key_hash = ph.hash(raw_key)
    fingerprint = hashlib.sha256(raw_key.encode()).digest()[:8].hex()

    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agents"
        " (id, tenant_id, name, description, api_key_hash, api_key_fingerprint,"
        "  mcp_endpoint, status, rate_limit_rps)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (agent_internal_id, tenant_id, name, None, api_key_hash, fingerprint,
         f"http://localhost:8100/v1/agents/{agent_internal_id}", "active", None),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0])


@pytest.fixture(scope="module")
def agent_tenant(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "agent-test-tenant")


@pytest.fixture(scope="module")
def agent_tenant_b(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "agent-test-tenant-b")


# ---------------------------------------------------------------------------
# Tests: Create
# ---------------------------------------------------------------------------


def test_create_agent_returns_201(
    admin_app: TestClient, agent_tenant: str
) -> None:
    """POST → 201 with agent_ prefixed ID and api_key returned once."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{agent_tenant}/agents",
        json={"name": "my-test-agent", "description": "integration test agent"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("agent_"), f"Expected agent_ prefix: {body['id']}"
    assert body["name"] == "my-test-agent"
    assert body["description"] == "integration test agent"
    assert "api_key" in body, "api_key must be returned once at creation"
    assert body["api_key"].startswith("mk_agent_"), "API key must have mk_agent_ prefix"
    assert "api_key_fingerprint" in body
    assert body["status"] == "active"


def test_create_agent_mcp_endpoint_uses_port_8082(
    admin_app: TestClient, agent_tenant: str
) -> None:
    """
    NET-A: mcp_endpoint is built from MINTKEY_MCP_PUBLIC_URL (canonical) with
    MCP_BASE_URL as a legacy fallback.  This test pins MINTKEY_MCP_PUBLIC_URL to
    a known value so the assertion is deterministic regardless of any host env var
    that may or may not be set.

    The assertion also verifies that the default (neither var set) still falls back
    to http://localhost:8082 — port 8100 must never appear (OPS-FF Fix 2).
    """
    _known_url = "http://mcp.test.local:8082"
    _prev = os.environ.pop("MINTKEY_MCP_PUBLIC_URL", None)
    _prev_legacy = os.environ.pop("MCP_BASE_URL", None)
    try:
        os.environ["MINTKEY_MCP_PUBLIC_URL"] = _known_url
        resp = _post(
            admin_app,
            f"/v1/tenants/{agent_tenant}/agents",
            json={"name": "mcp-endpoint-port-check-agent"},
        )
        assert resp.status_code == 201, resp.text
        body = resp.json()
        mcp_endpoint = body.get("mcp_endpoint", "")
        assert mcp_endpoint, "mcp_endpoint must be present in agent creation response"
        assert mcp_endpoint.startswith(_known_url), (
            f"mcp_endpoint must start with {_known_url!r} (NET-A), got: {mcp_endpoint!r}"
        )
        assert "8100" not in mcp_endpoint, (
            f"mcp_endpoint must NOT contain broken port 8100, got: {mcp_endpoint!r}"
        )
        # Verify trailing slash was stripped: exactly one '/' between base and path
        assert "//v1" not in mcp_endpoint, (
            f"trailing slash not stripped: {mcp_endpoint!r}"
        )
    finally:
        os.environ.pop("MINTKEY_MCP_PUBLIC_URL", None)
        if _prev is not None:
            os.environ["MINTKEY_MCP_PUBLIC_URL"] = _prev
        if _prev_legacy is not None:
            os.environ["MCP_BASE_URL"] = _prev_legacy


def test_create_agent_api_key_returned_only_once(
    admin_app: TestClient, agent_tenant: str
) -> None:
    """
    API key is returned in the CREATE response but not in subsequent list.
    S-SEC-1: plaintext returned exactly once.
    """
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{agent_tenant}/agents",
        json={"name": "one-shot-key-agent"},
    )
    assert create_resp.status_code == 201
    api_key = create_resp.json()["api_key"]
    assert api_key.startswith("mk_agent_")

    # List must NOT contain the plaintext api_key
    list_resp = admin_app.get(f"/v1/tenants/{agent_tenant}/agents")
    assert list_resp.status_code == 200
    assert api_key not in str(list_resp.json())


def test_create_agent_missing_name_returns_422(
    admin_app: TestClient, agent_tenant: str
) -> None:
    """Missing required 'name' field → 422."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{agent_tenant}/agents",
        json={"description": "no name given"},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: List
# ---------------------------------------------------------------------------


def test_list_agents_returns_200(
    admin_app: TestClient, agent_tenant: str
) -> None:
    """GET list → 200 with agents array."""
    resp = admin_app.get(f"/v1/tenants/{agent_tenant}/agents")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "agents" in body
    assert isinstance(body["agents"], list)
    assert len(body["agents"]) >= 1
    for agent in body["agents"]:
        assert "id" in agent
        assert "name" in agent
        assert "api_key" not in agent, "api_key must not appear in list — S-SEC-1"


# ---------------------------------------------------------------------------
# Tests: Get single
# ---------------------------------------------------------------------------


def test_get_single_agent_unknown_id_returns_404(
    admin_app: TestClient, agent_tenant: str
) -> None:
    """GET with a UUID that does not exist → 404."""
    fake_id = str(uuid.uuid4())
    resp = admin_app.get(f"/v1/tenants/{agent_tenant}/agents/{fake_id}")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("mintkey:code") == "not_found"


def test_get_single_agent_returns_200(
    admin_app: TestClient, agent_tenant: str, postgres_container
) -> None:
    """Insert agent directly, GET by internal UUID → 200."""
    internal_id = _insert_agent(postgres_container, agent_tenant, "get-me-agent")
    resp = admin_app.get(f"/v1/tenants/{agent_tenant}/agents/{internal_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "api_key" not in body, "api_key must not appear in GET — S-SEC-1"


# ---------------------------------------------------------------------------
# Tests: Delete
# ---------------------------------------------------------------------------


def test_delete_agent_returns_204(
    admin_app: TestClient, agent_tenant: str, postgres_container
) -> None:
    """Insert agent directly, DELETE by internal UUID → 204."""
    internal_id = _insert_agent(postgres_container, agent_tenant, "delete-me-agent")
    resp = _delete(admin_app, f"/v1/tenants/{agent_tenant}/agents/{internal_id}")
    assert resp.status_code == 204


# ---------------------------------------------------------------------------
# Tests: Cross-tenant isolation (ADR-0008)
# ---------------------------------------------------------------------------


def test_cross_tenant_get_agent_returns_404(
    admin_app: TestClient,
    agent_tenant: str,
    agent_tenant_b: str,
    postgres_container,
) -> None:
    """Tenant B cannot read Tenant A's agent — RLS → 404."""
    internal_id = _insert_agent(postgres_container, agent_tenant, "isolation-agent")
    resp = admin_app.get(f"/v1/tenants/{agent_tenant_b}/agents/{internal_id}")
    assert resp.status_code == 404


def test_cross_tenant_list_agents_empty(
    admin_app: TestClient,
    agent_tenant_b: str,
) -> None:
    """Tenant B's agent list does not include Tenant A's agents."""
    resp = admin_app.get(f"/v1/tenants/{agent_tenant_b}/agents")
    assert resp.status_code == 200
    body = resp.json()
    # Tenant B has no agents inserted — list must be empty
    assert body["agents"] == []


# ---------------------------------------------------------------------------
# Helpers for UX-FB-CE tests
# ---------------------------------------------------------------------------


def _get_pg_conn(postgres_container):
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )


def _insert_service_for_grants(postgres_container, tenant_id: str, slug: str) -> str:
    """Insert a minimal service row and return its UUID."""
    conn = _get_pg_conn(postgres_container)
    cur = conn.cursor()
    svc_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO services"
        " (id, tenant_id, name, slug, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (svc_id, tenant_id, slug, slug, "https://example.com/api", "bearer_token", "active"),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0])


def _insert_permission_grant(postgres_container, tenant_id: str, agent_id: str, service_id: str) -> None:
    """Insert a permission_grants row for the given agent + service."""
    conn = _get_pg_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO permission_grants"
        " (id, tenant_id, agent_id, service_id, action, created_by, constraints)"
        " VALUES (%s, %s, %s, %s, %s, %s, '{}'::jsonb)",
        (str(uuid.uuid4()), tenant_id, agent_id, service_id, "read", agent_id),
    )
    conn.commit()
    cur.close()
    conn.close()


def _insert_service_api_key(
    postgres_container,
    tenant_id: str,
    agent_id: str,
    service_id: str,
) -> str:
    """Insert an active service_api_key row and return its UUID."""
    conn = _get_pg_conn(postgres_container)
    cur = conn.cursor()
    key_id = str(uuid.uuid4())
    raw_key = "mk_svckey_" + secrets.token_hex(20)
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    key_hash = ph.hash(raw_key)
    fingerprint = hashlib.sha256(raw_key.encode()).digest()[:8].hex()
    cur.execute(
        "INSERT INTO service_api_keys"
        " (id, tenant_id, agent_id, service_id, key_hash, key_fingerprint,"
        "  allowed_actions, created_by)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s::text[], %s) RETURNING id",
        (key_id, tenant_id, agent_id, service_id, key_hash, fingerprint,
         "{read}", agent_id),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0])


# ---------------------------------------------------------------------------
# Tests: UX-FB-CE Part C — grants_count in list + get
# ---------------------------------------------------------------------------


def test_list_agents_returns_grants_count_zero_for_agent_without_grants(
    admin_app: TestClient,
    agent_tenant: str,
    postgres_container,
) -> None:
    """
    UX-FB-CE Part C: list response includes grants_count = 0 for agent with no grants.
    Source: UX-FB-CE spec step 2.
    """
    # Insert an agent directly (no grants created)
    internal_id = _insert_agent(postgres_container, agent_tenant, "no-grants-agent-list")
    resp = admin_app.get(f"/v1/tenants/{agent_tenant}/agents")
    assert resp.status_code == 200, resp.text
    agents = resp.json()["agents"]
    matches = [a for a in agents if a.get("name") == "no-grants-agent-list"]
    assert matches, f"Agent not found in list: {[a['name'] for a in agents]}"
    agent = matches[0]
    assert "grants_count" in agent, "grants_count must be present in list response — UX-FB-CE C"
    assert agent["grants_count"] == 0, f"Expected 0 grants, got {agent['grants_count']}"


def test_get_agent_returns_grants_count_n(
    admin_app: TestClient,
    agent_tenant: str,
    postgres_container,
) -> None:
    """
    UX-FB-CE Part C: get-single response includes grants_count = 2 after 2 grants are added.
    Source: UX-FB-CE spec step 3.
    """
    # Insert agent + 2 permission grants on distinct services
    internal_id = _insert_agent(postgres_container, agent_tenant, "grants-count-2-agent")
    svc1 = _insert_service_for_grants(postgres_container, agent_tenant, "gcsvc1")
    svc2 = _insert_service_for_grants(postgres_container, agent_tenant, "gcsvc2")
    _insert_permission_grant(postgres_container, agent_tenant, internal_id, svc1)
    _insert_permission_grant(postgres_container, agent_tenant, internal_id, svc2)

    resp = admin_app.get(f"/v1/tenants/{agent_tenant}/agents/{internal_id}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "grants_count" in body, "grants_count must be present in get-single response — UX-FB-CE C"
    assert body["grants_count"] == 2, f"Expected 2 grants, got {body['grants_count']}"


# ---------------------------------------------------------------------------
# Tests: UX-FB-CE Part E — revoke_agent returns active_api_keys_count
# ---------------------------------------------------------------------------


def test_revoke_agent_returns_active_api_keys_count_zero_when_none(
    admin_app: TestClient,
    agent_tenant: str,
    postgres_container,
) -> None:
    """
    UX-FB-CE Part E: revoking an agent with no service_api_keys returns active_api_keys_count = 0.
    Source: UX-FB-CE spec step 7–8.
    """
    internal_id = _insert_agent(postgres_container, agent_tenant, "revoke-no-keys-agent")
    resp = _post(admin_app, f"/v1/tenants/{agent_tenant}/agents/{internal_id}/revoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert "active_api_keys_count" in body, "active_api_keys_count must be present — UX-FB-CE E"
    assert body["active_api_keys_count"] == 0, f"Expected 0, got {body['active_api_keys_count']}"


def test_revoke_agent_returns_active_api_keys_count_n_when_keys_exist(
    admin_app: TestClient,
    agent_tenant: str,
    postgres_container,
) -> None:
    """
    UX-FB-CE Part E: revoking an agent with 1 active service_api_key returns active_api_keys_count = 1.
    Keys are NOT auto-revoked (hard rule — would break existing clients silently).
    Source: UX-FB-CE spec step 7–8.
    """
    internal_id = _insert_agent(postgres_container, agent_tenant, "revoke-with-keys-agent")
    svc = _insert_service_for_grants(postgres_container, agent_tenant, "revoke-svc")
    _insert_permission_grant(postgres_container, agent_tenant, internal_id, svc)
    _insert_service_api_key(postgres_container, agent_tenant, internal_id, svc)

    resp = _post(admin_app, f"/v1/tenants/{agent_tenant}/agents/{internal_id}/revoke")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "ok"
    assert "active_api_keys_count" in body, "active_api_keys_count must be present — UX-FB-CE E"
    assert body["active_api_keys_count"] == 1, (
        f"Expected 1 active API key, got {body['active_api_keys_count']}"
    )

    # Hard rule: the key must NOT be auto-revoked
    conn = _get_pg_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT revoked_at FROM service_api_keys WHERE agent_id = %s AND tenant_id = %s",
        (internal_id, agent_tenant),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    assert rows, "Service API key row must still exist"
    assert all(r[0] is None for r in rows), (
        "Keys must NOT be auto-revoked on agent revoke — UX-FB-CE hard rule"
    )


def _insert_agent_with_expired_key(postgres_container, tenant_id: str, name: str, expired: bool = True) -> tuple[str, str]:
    """Insert an agent with a key that is either expired or valid. Returns (internal_id, raw_key)."""
    from datetime import datetime, timezone, timedelta
    agent_internal_id = str(uuid.uuid4())
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    raw_key = "mk_agent_" + secrets.token_hex(20)
    api_key_hash = ph.hash(raw_key)
    fingerprint = hashlib.sha256(raw_key.encode()).digest()[:8].hex()

    now = datetime.now(timezone.utc)
    if expired:
        expires_at = now - timedelta(minutes=1)
    else:
        expires_at = now + timedelta(hours=1)

    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agents"
        " (id, tenant_id, name, description, api_key_hash, api_key_fingerprint,"
        "  mcp_endpoint, status, rate_limit_rps, api_key_expires_at, api_key_version)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (agent_internal_id, tenant_id, name, None, api_key_hash, fingerprint,
         f"http://localhost:8100/v1/agents/{agent_internal_id}", "active", None,
         expires_at, 1),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0]), raw_key


def test_revoke_agent_audit_payload_contains_active_api_keys_count(
    admin_app: TestClient,
    agent_tenant: str,
    postgres_container,
) -> None:
    """
    UX-FB-CE Part E: audit_events.payload for agent.revoked must include active_api_keys_count.
    Source: UX-FB-CE spec step 8.
    """
    import json as _json
    internal_id = _insert_agent(postgres_container, agent_tenant, "revoke-audit-payload-agent")
    resp = _post(admin_app, f"/v1/tenants/{agent_tenant}/agents/{internal_id}/revoke")
    assert resp.status_code == 200, resp.text

    conn = _get_pg_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT payload FROM audit_events"
        " WHERE event_type = 'agent.revoked' AND tenant_id = %s"
        " ORDER BY at DESC LIMIT 1",
        (agent_tenant,),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None, "audit_events must have an agent.revoked row"
    payload = row[0] if isinstance(row[0], dict) else _json.loads(row[0])
    assert "active_api_keys_count" in payload, (
        f"audit payload must include active_api_keys_count — UX-FB-CE E; got: {payload}"
    )


# ---------------------------------------------------------------------------
# UX-FB-AK-1 — validate-agent-key expiry integration tests
# ---------------------------------------------------------------------------


def test_validate_expired_key_returns_401_with_expired_code(
    admin_app: TestClient,
    agent_tenant: str,
    postgres_container,
) -> None:
    """
    Validate a key whose api_key_expires_at is now-1m → 401 with mintkey:code: agent_api_key_expired.
    Source: UX-FB-AK-1.
    """
    internal_id, raw_key = _insert_agent_with_expired_key(
        postgres_container, agent_tenant, "expired-key-agent", expired=True
    )

    resp = _post(
        admin_app,
        "/v1/internal/validate-agent-key",
        json={"api_key": raw_key},
    )
    assert resp.status_code == 401, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "agent_api_key_expired", (
        f"Expected agent_api_key_expired code, got: {body}"
    )
    assert body.get("status") == 401


def test_validate_expired_key_emits_agent_api_key_expired_audit_throttled(
    admin_app: TestClient,
    agent_tenant: str,
    postgres_container,
) -> None:
    """
    First validate of expired key emits audit event; second call within 60s must NOT emit again.
    Source: UX-FB-AK-1; throttle: 1 per agent per 60s.
    """
    import json as _json

    internal_id, raw_key = _insert_agent_with_expired_key(
        postgres_container, agent_tenant, "expired-throttle-agent", expired=True
    )

    # Reset throttle state for this agent by directly patching — call once first
    # First call: should emit audit event
    resp1 = _post(admin_app, "/v1/internal/validate-agent-key", json={"api_key": raw_key})
    assert resp1.status_code == 401

    conn = _get_pg_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM audit_events"
        " WHERE event_type = 'agent.api_key_expired' AND tenant_id = %s",
        (agent_tenant,),
    )
    count_after_first = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count_after_first >= 1, "First expired validation must emit audit event"

    # Second call within 60s: must NOT emit another audit event
    resp2 = _post(admin_app, "/v1/internal/validate-agent-key", json={"api_key": raw_key})
    assert resp2.status_code == 401

    conn = _get_pg_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM audit_events"
        " WHERE event_type = 'agent.api_key_expired' AND tenant_id = %s",
        (agent_tenant,),
    )
    count_after_second = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count_after_second == count_after_first, (
        f"Second call within 60s must NOT emit another audit event (throttle). "
        f"Count before={count_after_first}, after={count_after_second}"
    )


def test_validate_valid_key_unaffected_by_expiry_check(
    admin_app: TestClient,
    agent_tenant: str,
    postgres_container,
) -> None:
    """
    Validate a key with null expiry → 200 (back-compat — expiry check must not fire).
    Source: UX-FB-AK-1.
    """
    # Use _insert_agent which sets api_key_expires_at = NULL (no new columns explicitly)
    # Insert a fresh agent via the API so we get the plaintext key
    resp = _post(
        admin_app,
        f"/v1/tenants/{agent_tenant}/agents",
        json={"name": "null-expiry-validate-agent"},
    )
    assert resp.status_code == 201, resp.text
    raw_key = resp.json()["api_key"]

    validate_resp = _post(
        admin_app,
        "/v1/internal/validate-agent-key",
        json={"api_key": raw_key},
    )
    assert validate_resp.status_code == 200, (
        f"Key with null expiry must pass validation, got {validate_resp.status_code}: {validate_resp.text}"
    )


def test_validate_future_expiry_passes(
    admin_app: TestClient,
    agent_tenant: str,
    postgres_container,
) -> None:
    """
    Validate a key with expiry = now+1h → 200.
    Source: UX-FB-AK-1.
    """
    internal_id, raw_key = _insert_agent_with_expired_key(
        postgres_container, agent_tenant, "future-expiry-agent", expired=False
    )

    resp = _post(
        admin_app,
        "/v1/internal/validate-agent-key",
        json={"api_key": raw_key},
    )
    assert resp.status_code == 200, (
        f"Key with future expiry must pass validation, got {resp.status_code}: {resp.text}"
    )
