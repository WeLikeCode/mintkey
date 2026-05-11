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
"""
from __future__ import annotations

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
