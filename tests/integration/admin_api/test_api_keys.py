"""
Integration tests for service API key endpoints.

POST   /v1/tenants/{tid}/agents/{aid}/api-keys              — create (201)
GET    /v1/tenants/{tid}/agents/{aid}/api-keys              — list   (200)
GET    /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}        — get    (200/404)
POST   /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/revoke — revoke (200)

Architecture constraints honoured:
  ADR-0018 §1.3 — plaintext returned once at creation, never stored.
  ADR-0014.7    — audit event emitted on every state change.
  ADR-0008      — RLS tenant isolation; bound parameters.
  Req 1.3       — allowed_actions ⊆ agent's permission grants.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# CSRF helpers (mirrors test_services.py pattern)
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-token-apikeys"
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
# DB helpers
# ---------------------------------------------------------------------------


def _insert_tenant(postgres_container, slug: str) -> str:
    import psycopg2
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


def _insert_service(postgres_container, tenant_uuid: str, name: str) -> str:
    """Insert a service row directly and return its UUID string."""
    import psycopg2
    import uuid as _uuid
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    cur = conn.cursor()
    cur.execute("SELECT id FROM services WHERE name = %s AND tenant_id = %s", (name, tenant_uuid))
    row = cur.fetchone()
    if row is None:
        svc_id = str(_uuid.uuid4())
        slug = name.replace(" ", "-").lower()
        cur.execute(
            "INSERT INTO services (id, tenant_id, name, slug, base_url, auth_scheme, status)"
            " VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
            (svc_id, tenant_uuid, name, slug, "https://example.com/api", "bearer_token", "active"),
        )
        conn.commit()
        row = cur.fetchone()
    else:
        conn.commit()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0])


def _insert_permission_grant(postgres_container, tenant_uuid: str, agent_uuid: str,
                              service_uuid: str, action: str) -> None:
    """Insert a permission_grants row so api-keys creation can pass the subset check."""
    import psycopg2
    import uuid as _uuid
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
        "SELECT id FROM permission_grants WHERE agent_id = %s AND service_id = %s AND action = %s",
        (agent_uuid, service_uuid, action),
    )
    if cur.fetchone() is None:
        cur.execute(
            "INSERT INTO permission_grants"
            " (id, tenant_id, agent_id, service_id, action, created_by)"
            " VALUES (%s, %s, %s, %s, %s, %s)",
            (str(_uuid.uuid4()), tenant_uuid, agent_uuid, service_uuid, action,
             agent_uuid),
        )
        conn.commit()
    else:
        conn.commit()
    cur.close()
    conn.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ak_tenant_uuid(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "test-apikey-tenant")


@pytest.fixture(scope="module")
def ak_tenant_b_uuid(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "test-apikey-tenant-b")


@pytest.fixture(scope="module")
def ak_agent_uuid(admin_app: TestClient, ak_tenant_uuid: str) -> str:
    """Create an agent via API; return its internal UUID (from list)."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{ak_tenant_uuid}/agents",
        json={"name": "apikey-test-agent"},
    )
    assert resp.status_code == 201, f"Agent create failed: {resp.text}"

    # List to get the internal UUID (api_key endpoint uses it for WHERE id = :aid)
    list_resp = admin_app.get(f"/v1/tenants/{ak_tenant_uuid}/agents")
    assert list_resp.status_code == 200
    agents = list_resp.json()["agents"]
    matches = [a for a in agents if a["name"] == "apikey-test-agent"]
    assert matches, f"Agent not found: {agents}"
    # id is formatted as "agent_{hex_uuid}" — strip prefix and restore dashes
    hex_id = matches[0]["id"].replace("agent_", "")
    # UUID with dashes
    return f"{hex_id[:8]}-{hex_id[8:12]}-{hex_id[12:16]}-{hex_id[16:20]}-{hex_id[20:]}"


@pytest.fixture(scope="module")
def ak_service_uuid(admin_app: TestClient, ak_tenant_uuid: str, postgres_container) -> str:
    return _insert_service(postgres_container, ak_tenant_uuid, "apikey-test-svc")


@pytest.fixture(scope="module")
def ak_setup(
    ak_tenant_uuid: str,
    ak_agent_uuid: str,
    ak_service_uuid: str,
    postgres_container,
) -> None:
    """Ensure a permission grant exists so api_keys.create can pass subset check."""
    _insert_permission_grant(
        postgres_container, ak_tenant_uuid, ak_agent_uuid, ak_service_uuid, "read"
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_api_key_returns_201(
    admin_app: TestClient,
    ak_tenant_uuid: str,
    ak_agent_uuid: str,
    ak_service_uuid: str,
    ak_setup,
) -> None:
    """POST …/api-keys → 201 with plaintext_key shown once — ADR-0018 §1.3."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys",
        json={
            "service_id": ak_service_uuid,
            "allowed_actions": ["read"],
        },
    )
    assert resp.status_code == 201, f"Create api_key failed: {resp.text}"
    body = resp.json()
    assert "api_key_id" in body
    assert "plaintext_key" in body
    assert body["plaintext_key"].startswith("mk_svckey_")
    assert "key_fingerprint" in body
    # Plaintext is shown exactly once; fingerprint is safe to store
    assert len(body["key_fingerprint"]) == 16  # 8 bytes → 16 hex chars


def _get_latest_api_key_uuid(postgres_container, agent_uuid: str, tenant_uuid: str) -> str:
    """Fetch the internal UUID of the most-recently-created api key for the given agent."""
    import psycopg2
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
        "SELECT id FROM service_api_keys WHERE agent_id = %s AND tenant_id = %s"
        " ORDER BY created_at DESC LIMIT 1",
        (agent_uuid, tenant_uuid),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None, f"No api key found for agent {agent_uuid}"
    return str(row[0])


def test_list_api_keys_returns_200(
    admin_app: TestClient,
    ak_tenant_uuid: str,
    ak_agent_uuid: str,
    ak_service_uuid: str,
    ak_setup,
    postgres_container,
) -> None:
    """GET …/api-keys → 200 list; never contains plaintext — ADR-0018 §1.3."""
    # Ensure at least one key exists
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys",
        json={"service_id": ak_service_uuid, "allowed_actions": ["read"]},
    )
    assert create_resp.status_code == 201

    resp = admin_app.get(
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys"
    )
    assert resp.status_code == 200, (
        f"Expected 200 but got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "api_keys" in body, f"Expected 'api_keys' key, got: {body}"
    items = body["api_keys"]
    assert isinstance(items, list)
    assert len(items) >= 1
    for item in items:
        # Plaintext must NEVER appear in list response (ADR-0018 §1.3)
        assert "plaintext_key" not in item
        assert "key_hash" not in item
        assert "api_key_id" in item
        assert "key_fingerprint" in item
        assert "status" in item


def test_get_single_api_key_returns_200(
    admin_app: TestClient,
    ak_tenant_uuid: str,
    ak_agent_uuid: str,
    ak_service_uuid: str,
    ak_setup,
    postgres_container,
) -> None:
    """GET …/api-keys/{kid} → 200 with key details (no plaintext)."""
    # Create a key to fetch
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys",
        json={"service_id": ak_service_uuid, "allowed_actions": ["read"]},
    )
    assert create_resp.status_code == 201

    # Get internal UUID directly from DB
    kid = _get_latest_api_key_uuid(postgres_container, ak_agent_uuid, ak_tenant_uuid)

    resp = admin_app.get(
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys/{kid}"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["api_key_id"] == kid
    assert "plaintext_key" not in body
    assert body["status"] in ("active", "revoked", "expired")


def test_get_single_api_key_unknown_returns_404(
    admin_app: TestClient,
    ak_tenant_uuid: str,
    ak_agent_uuid: str,
    ak_setup,
) -> None:
    """GET with unknown key_id returns 404."""
    import uuid
    fake_kid = str(uuid.uuid4())
    resp = admin_app.get(
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys/{fake_kid}"
    )
    assert resp.status_code == 404
    assert resp.json()["mintkey:code"] == "not_found"


def test_revoke_api_key_returns_200(
    admin_app: TestClient,
    ak_tenant_uuid: str,
    ak_agent_uuid: str,
    ak_service_uuid: str,
    ak_setup,
    postgres_container,
) -> None:
    """POST …/revoke → 200 {status: revoked}; second revoke is idempotent."""
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys",
        json={"service_id": ak_service_uuid, "allowed_actions": ["read"]},
    )
    assert create_resp.status_code == 201

    # Get internal UUID from DB directly
    kid = _get_latest_api_key_uuid(postgres_container, ak_agent_uuid, ak_tenant_uuid)

    revoke_resp = _post(
        admin_app,
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys/{kid}/revoke",
        json={"reason": "test revocation"},
    )
    assert revoke_resp.status_code == 200
    body = revoke_resp.json()
    assert body["status"] in ("revoked", "already_revoked")

    # Idempotent second revoke
    second_revoke = _post(
        admin_app,
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys/{kid}/revoke",
        json={"reason": "test revocation again"},
    )
    assert second_revoke.status_code == 200
    assert second_revoke.json()["status"] == "already_revoked"


def test_create_api_key_actions_exceed_grant_returns_422(
    admin_app: TestClient,
    ak_tenant_uuid: str,
    ak_agent_uuid: str,
    ak_service_uuid: str,
    ak_setup,
) -> None:
    """allowed_actions exceeding grants → 422 api_key_actions_exceed_grant — Req 1.3."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{ak_tenant_uuid}/agents/{ak_agent_uuid}/api-keys",
        json={
            "service_id": ak_service_uuid,
            "allowed_actions": ["read", "write", "admin"],  # only "read" is granted
        },
    )
    assert resp.status_code == 422
    assert resp.json()["mintkey:code"] == "api_key_actions_exceed_grant"


def test_create_api_key_unknown_agent_returns_404(
    admin_app: TestClient,
    ak_tenant_uuid: str,
    ak_service_uuid: str,
    ak_setup,
) -> None:
    """Creating an api_key for a non-existent agent returns 404."""
    import uuid
    fake_agent = str(uuid.uuid4())
    resp = _post(
        admin_app,
        f"/v1/tenants/{ak_tenant_uuid}/agents/{fake_agent}/api-keys",
        json={"service_id": ak_service_uuid, "allowed_actions": ["read"]},
    )
    assert resp.status_code == 404
    assert resp.json()["mintkey:code"] == "not_found"
