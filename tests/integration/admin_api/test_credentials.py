"""
Integration tests for credential endpoints.

POST   /v1/tenants/{tenant_id}/services/{service_id}/credentials — create (201)
GET    /v1/tenants/{tenant_id}/services/{service_id}/credentials — list (200)

Architecture constraints verified:
  ADR-0017.11 — ULID cred_ prefix IDs
  ADR-0014.4  — plaintext credential NEVER returned
  ADR-0008    — cross-tenant isolation (RLS)
"""
from __future__ import annotations

import psycopg2
import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# CSRF helpers — double-submit cookie pattern (matches test_services.py)
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-token-abc123"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}


def _post(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# Fixtures — direct DB inserts (bypasses create_tenant/create_service route
# which have pre-existing name/display_name column mismatches).
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


def _insert_service(postgres_container, tenant_id: str, slug: str = "cred-svc") -> str:
    """Insert a service row and return its UUID string."""
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
    svc_id = str(_uuid.uuid4())
    cur.execute(
        "INSERT INTO services"
        " (id, tenant_id, name, slug, display_name, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (svc_id, tenant_id, "cred-test-svc", slug, "Cred Test Svc",
         "https://example.com/api", "bearer_token", "active"),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0])


@pytest.fixture(scope="module")
def cred_tenant(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "cred-test-tenant")


@pytest.fixture(scope="module")
def cred_tenant_b(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "cred-test-tenant-b")


@pytest.fixture(scope="module")
def cred_service(admin_app: TestClient, postgres_container, cred_tenant: str) -> str:
    return _insert_service(postgres_container, cred_tenant)


@pytest.fixture(scope="module")
def cred_service_b(admin_app: TestClient, postgres_container, cred_tenant_b: str) -> str:
    return _insert_service(postgres_container, cred_tenant_b)


# ---------------------------------------------------------------------------
# Tests: Create
# ---------------------------------------------------------------------------


def test_create_credential_returns_201(
    admin_app: TestClient, cred_tenant: str, cred_service: str
) -> None:
    """POST → 201 with cred_ ULID ID, no plaintext value returned."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{cred_service}/credentials",
        json={"auth_scheme": "bearer_token", "value": "super-secret-key"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("cred_"), f"Expected cred_ prefix: {body['id']}"
    assert body["auth_scheme"] == "bearer_token"
    assert body["key_version"] == 1
    # ADR-0014.4: plaintext MUST NOT be in response
    assert "super-secret-key" not in str(body)
    assert "value" not in body


def test_create_credential_rotation_increments_key_version(
    admin_app: TestClient, cred_tenant: str, cred_service: str
) -> None:
    """Second POST to same service increments key_version to 2."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{cred_service}/credentials",
        json={"auth_scheme": "bearer_token", "value": "rotated-key"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["key_version"] == 2


def test_create_credential_missing_auth_scheme_returns_422(
    admin_app: TestClient, cred_tenant: str, cred_service: str
) -> None:
    """Missing required field → 422 validation error."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{cred_service}/credentials",
        json={"value": "some-key"},  # missing auth_scheme
    )
    assert resp.status_code == 422


def test_create_credential_missing_value_returns_422(
    admin_app: TestClient, cred_tenant: str, cred_service: str
) -> None:
    """Missing credential value → 422 validation error."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{cred_service}/credentials",
        json={"auth_scheme": "bearer_token"},  # missing value
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests: List
# ---------------------------------------------------------------------------


def test_list_credentials_returns_200(
    admin_app: TestClient, cred_tenant: str, cred_service: str
) -> None:
    """GET → 200 with versions array, no plaintext."""
    resp = admin_app.get(
        f"/v1/tenants/{cred_tenant}/services/{cred_service}/credentials"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "versions" in body
    assert isinstance(body["versions"], list)
    assert len(body["versions"]) >= 1
    for v in body["versions"]:
        assert "key_version" in v
        assert "auth_scheme" in v
        assert "status" in v
        # ADR-0014.4: no plaintext
        assert "value" not in v


def test_list_credentials_empty_for_new_service(
    admin_app: TestClient, cred_tenant: str, postgres_container
) -> None:
    """Listing credentials for a service with no credentials returns empty list."""
    empty_svc_id = _insert_service(postgres_container, cred_tenant, slug="cred-svc-empty")
    resp = admin_app.get(
        f"/v1/tenants/{cred_tenant}/services/{empty_svc_id}/credentials"
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["versions"] == []


# ---------------------------------------------------------------------------
# Tests: Cross-tenant isolation (ADR-0008)
# ---------------------------------------------------------------------------


def test_cross_tenant_list_credentials_returns_empty(
    admin_app: TestClient,
    cred_tenant_b: str,
    cred_service: str,
) -> None:
    """
    Tenant B cannot see credentials for Tenant A's service.
    RLS filters the rows → returns empty list (not 404, since the
    credential route does not verify service ownership separately).
    """
    resp = admin_app.get(
        f"/v1/tenants/{cred_tenant_b}/services/{cred_service}/credentials"
    )
    assert resp.status_code == 200
    body = resp.json()
    # RLS isolation: no versions visible to tenant B
    assert body["versions"] == []


# ---------------------------------------------------------------------------
# Tests: DELETE /v1/tenants/{tid}/services/{sid}/credentials/{key_version}
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cred_service_for_delete(admin_app: TestClient, postgres_container, cred_tenant: str) -> str:
    """Separate service so delete tests don't interfere with list/create tests."""
    return _insert_service(postgres_container, cred_tenant, slug="cred-svc-delete")


def test_delete_credential_version_returns_204(
    admin_app: TestClient, cred_tenant: str, cred_service_for_delete: str
) -> None:
    """DELETE /credentials/{key_version} → 204 revokes the version."""
    # First create a credential so key_version=1 exists
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_delete}/credentials",
        json={"auth_scheme": "bearer_token", "value": "delete-test-key"},
    )
    assert create_resp.status_code == 201, create_resp.text
    key_version = create_resp.json()["key_version"]

    resp = admin_app.delete(
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_delete}/credentials/{key_version}",
        headers=_CSRF_HEADERS,
        cookies=_CSRF_COOKIES,
    )
    assert resp.status_code == 204, resp.text


def test_delete_credential_version_not_found_returns_404(
    admin_app: TestClient, cred_tenant: str, cred_service_for_delete: str
) -> None:
    """DELETE /credentials/{key_version} with nonexistent version → 404."""
    resp = admin_app.delete(
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_delete}/credentials/9999",
        headers=_CSRF_HEADERS,
        cookies=_CSRF_COOKIES,
    )
    assert resp.status_code == 404
    assert resp.json()["mintkey:code"] == "not_found"


def test_delete_credential_version_already_revoked_returns_409(
    admin_app: TestClient, cred_tenant: str, cred_service_for_delete: str
) -> None:
    """DELETE /credentials/{key_version} twice → 409 on second call."""
    # Create a credential
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_delete}/credentials",
        json={"auth_scheme": "bearer_token", "value": "delete-409-key"},
    )
    assert create_resp.status_code == 201, create_resp.text
    key_version = create_resp.json()["key_version"]

    # First delete succeeds
    r1 = admin_app.delete(
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_delete}/credentials/{key_version}",
        headers=_CSRF_HEADERS,
        cookies=_CSRF_COOKIES,
    )
    assert r1.status_code == 204

    # Second delete → 409
    r2 = admin_app.delete(
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_delete}/credentials/{key_version}",
        headers=_CSRF_HEADERS,
        cookies=_CSRF_COOKIES,
    )
    assert r2.status_code == 409
    assert r2.json()["mintkey:code"] == "already_revoked"
