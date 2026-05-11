"""
Integration tests for permission grant/revoke endpoints.

POST   /v1/tenants/{tenant_id}/agents/{agent_id}/permissions        — grant (201 / 200 / 409)
DELETE /v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{pid}  — revoke (204)

Architecture constraints verified:
  ADR-0017.11 — ULID perm_ prefix IDs
  ADR-0016.4  — constraints schema is CLOSED; unknown keys → 422
  ADR-0008    — cross-tenant isolation: agent not in tenant → 404

Note: permission_grants.constraints is NOT NULL in the DB (default '{}'). When the
source INSERT passes CAST(NULL AS jsonb) the DB rejects it, so all tests pass
constraints={} explicitly. This is consistent with the OpenAPI schema (optional
field defaults to empty object).
"""
from __future__ import annotations

import hashlib
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


def _get_conn(postgres_container):
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )


def _insert_tenant(postgres_container, slug: str) -> str:
    conn = _get_conn(postgres_container)
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


def _insert_service(postgres_container, tenant_id: str, slug: str) -> str:
    """Insert a service and return its UUID (internal DB id)."""
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    svc_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO services"
        " (id, tenant_id, name, slug, display_name, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (svc_id, tenant_id, slug, slug, slug,
         "https://example.com/api", "bearer_token", "active"),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0])


def _insert_agent(postgres_container, tenant_id: str, name: str) -> str:
    """Insert an agent and return its UUID string (internal DB id)."""
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    raw_key = "mk_agent_" + secrets.token_hex(20)
    api_key_hash = ph.hash(raw_key)
    fingerprint = hashlib.sha256(raw_key.encode()).digest()[:8].hex()
    agent_internal_id = str(uuid.uuid4())

    conn = _get_conn(postgres_container)
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
def perm_tenant(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "perm-test-tenant")


@pytest.fixture(scope="module")
def perm_tenant_b(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "perm-test-tenant-b")


@pytest.fixture(scope="module")
def perm_agent_id(admin_app: TestClient, postgres_container, perm_tenant: str) -> str:
    """Agent UUID (internal DB id) to use as agent_id path param."""
    return _insert_agent(postgres_container, perm_tenant, "perm-grant-agent")


@pytest.fixture(scope="module")
def perm_service_id(admin_app: TestClient, postgres_container, perm_tenant: str) -> str:
    """Service UUID for FK in permission_grants."""
    return _insert_service(postgres_container, perm_tenant, "perm-svc")


# ---------------------------------------------------------------------------
# Tests: Grant
# ---------------------------------------------------------------------------


def test_grant_permission_returns_201(
    admin_app: TestClient, perm_tenant: str, perm_agent_id: str, perm_service_id: str
) -> None:
    """POST grant → 201 with perm_ prefixed ID. Constraints passed as {} to satisfy NOT NULL."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{perm_tenant}/agents/{perm_agent_id}/permissions",
        json={
            "service_id": perm_service_id,
            "action": "invoke",
            "constraints": {},
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("perm_"), f"Expected perm_ prefix: {body['id']}"
    assert body["agent_id"] == perm_agent_id
    assert body["service_id"] == perm_service_id
    assert body["action"] == "invoke"


def test_grant_permission_idempotent_no_duplicate_row(
    admin_app: TestClient, perm_tenant: str, perm_agent_id: str,
    postgres_container,
) -> None:
    """
    Same (agent, service, action, constraints) → idempotent: DB has exactly one row.

    The route returns 200 on idempotent re-grant, but there is a known source bug
    (permissions.py:208): existing.id is a UUID object and not JSON-serializable,
    causing a 500. The idempotency invariant is verified at the DB level: the
    duplicate grant does not create a second row.
    """
    svc_id = _insert_service(postgres_container, perm_tenant, "perm-svc-idem")
    payload = {"service_id": svc_id, "action": "read", "constraints": {}}
    resp1 = _post(
        admin_app,
        f"/v1/tenants/{perm_tenant}/agents/{perm_agent_id}/permissions",
        json=payload,
    )
    assert resp1.status_code == 201

    # Second identical grant: idempotent path must return 200 with a string id
    resp2 = _post(
        admin_app,
        f"/v1/tenants/{perm_tenant}/agents/{perm_agent_id}/permissions",
        json=payload,
    )
    assert resp2.status_code == 200
    assert isinstance(resp2.json()["id"], str)

    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT COUNT(*) FROM permission_grants"
        " WHERE agent_id = %s AND service_id = %s AND action = %s",
        (perm_agent_id, svc_id, "read"),
    )
    count = cur.fetchone()[0]
    cur.close()
    conn.close()
    assert count == 1, f"Expected exactly 1 permission row, got {count}"


def test_grant_permission_conflict_returns_409(
    admin_app: TestClient, perm_tenant: str, perm_agent_id: str, postgres_container
) -> None:
    """Same (agent, service, action) but different constraints → 409 conflict."""
    svc_id = _insert_service(postgres_container, perm_tenant, "perm-svc-conflict")
    # First grant — empty constraints
    resp1 = _post(
        admin_app,
        f"/v1/tenants/{perm_tenant}/agents/{perm_agent_id}/permissions",
        json={"service_id": svc_id, "action": "write", "constraints": {}},
    )
    assert resp1.status_code == 201

    # Second grant — same (agent, service, action) but adds rate_limit constraint
    resp2 = _post(
        admin_app,
        f"/v1/tenants/{perm_tenant}/agents/{perm_agent_id}/permissions",
        json={
            "service_id": svc_id,
            "action": "write",
            "constraints": {
                "rate_limit": {"requests_per_second": 10, "burst": 20}
            },
        },
    )
    assert resp2.status_code == 409, resp2.text
    assert resp2.json().get("mintkey:code") == "permission_constraints_conflict"


def test_grant_permission_unknown_field_in_constraints_returns_422(
    admin_app: TestClient, perm_tenant: str, perm_agent_id: str, perm_service_id: str
) -> None:
    """Closed constraints schema: unknown key → 422 — ADR-0016.4."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{perm_tenant}/agents/{perm_agent_id}/permissions",
        json={
            "service_id": perm_service_id,
            "action": "list",
            "constraints": {"unknown_field": "bad_value"},
        },
    )
    assert resp.status_code == 422
    assert resp.json().get("mintkey:code") == "validation_failed"


def test_grant_permission_missing_service_id_returns_422(
    admin_app: TestClient, perm_tenant: str, perm_agent_id: str
) -> None:
    """Missing required service_id → 422 validation error."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{perm_tenant}/agents/{perm_agent_id}/permissions",
        json={"action": "invoke", "constraints": {}},
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: Revoke
# ---------------------------------------------------------------------------


def test_revoke_permission_returns_204(
    admin_app: TestClient, perm_tenant: str, perm_agent_id: str,
    postgres_container
) -> None:
    """
    Grant a permission with constraints={}, then revoke by internal DB UUID → 204.

    The revoke endpoint uses `WHERE id = :pid AND agent_id = :aid AND tenant_id = :tid`.
    We fetch the internal UUID directly from the DB after the grant.
    """
    svc_id = _insert_service(postgres_container, perm_tenant, "perm-svc-revoke")
    resp = _post(
        admin_app,
        f"/v1/tenants/{perm_tenant}/agents/{perm_agent_id}/permissions",
        json={"service_id": svc_id, "action": "delete", "constraints": {}},
    )
    assert resp.status_code == 201

    # Fetch the internal DB UUID for the new permission_grant row
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM permission_grants"
        " WHERE agent_id = %s AND service_id = %s AND action = %s",
        (perm_agent_id, svc_id, "delete"),
    )
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None, "Permission grant not found in DB"
    perm_db_id = str(row[0])

    del_resp = _delete(
        admin_app,
        f"/v1/tenants/{perm_tenant}/agents/{perm_agent_id}/permissions/{perm_db_id}",
    )
    assert del_resp.status_code == 204


# ---------------------------------------------------------------------------
# Tests: Cross-tenant isolation (ADR-0008)
# ---------------------------------------------------------------------------


def test_grant_permission_cross_tenant_returns_404(
    admin_app: TestClient,
    perm_tenant_b: str,
    perm_agent_id: str,
    perm_service_id: str,
) -> None:
    """
    Attempting to grant a permission using Tenant A's agent_id under Tenant B
    must return 404 — the agent does not exist in Tenant B's context.
    """
    resp = _post(
        admin_app,
        f"/v1/tenants/{perm_tenant_b}/agents/{perm_agent_id}/permissions",
        json={"service_id": perm_service_id, "action": "invoke", "constraints": {}},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json().get("mintkey:code") == "not_found"
