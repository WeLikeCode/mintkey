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


# ---------------------------------------------------------------------------
# Tests: POST .../credentials/rotate — R14a (ADR-0013 §3.1)
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def cred_service_for_rotate(admin_app: TestClient, postgres_container, cred_tenant: str) -> str:
    """Separate service so rotate tests don't interfere with other test modules."""
    return _insert_service(postgres_container, cred_tenant, slug="cred-svc-rotate")


@pytest.fixture(scope="module")
def cred_service_for_rotate_b(admin_app: TestClient, postgres_container, cred_tenant_b: str) -> str:
    """Cross-tenant isolation service — belongs to tenant B."""
    return _insert_service(postgres_container, cred_tenant_b, slug="cred-svc-rotate-b")


def test_rotate_credential_happy_path(
    admin_app: TestClient, cred_tenant: str, cred_service_for_rotate: str
) -> None:
    """
    Happy path: register a credential, rotate it.
    Old credential → superseded; new credential → active.
    Response carries new cred_ ID and effective_at — ADR-0013 §3.1.
    """
    # Register initial credential
    reg = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_rotate}/credentials",
        json={"auth_scheme": "bearer_token", "value": "initial-key"},
    )
    assert reg.status_code == 201, reg.text
    initial_version = reg.json()["key_version"]

    # Rotate
    rot = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_rotate}/credentials/rotate",
        json={"auth_scheme": "bearer_token", "value": "rotated-key"},
    )
    assert rot.status_code == 200, rot.text
    body = rot.json()
    assert body["id"].startswith("cred_"), f"Expected cred_ prefix: {body['id']}"
    assert body["auth_scheme"] == "bearer_token"
    assert body["key_version"] > initial_version
    assert "effective_at" in body
    # ADR-0014.4: plaintext must not appear in response
    assert "rotated-key" not in str(body)
    assert "value" not in body

    # Verify via list: old is superseded, new is active
    lst = admin_app.get(
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_rotate}/credentials"
    )
    assert lst.status_code == 200
    versions = lst.json()["versions"]
    statuses = {v["key_version"]: v["status"] for v in versions}
    assert statuses.get(initial_version) == "superseded", (
        f"Old credential (key_version={initial_version}) must be superseded; statuses={statuses}"
    )
    new_version = body["key_version"]
    assert statuses.get(new_version) == "active", (
        f"New credential (key_version={new_version}) must be active; statuses={statuses}"
    )


def test_rotate_credential_uuid_service_id(
    admin_app: TestClient, cred_tenant: str, postgres_container
) -> None:
    """
    Rotation works when service_id in path is a raw UUID string (not svc_ wire form).
    The route accepts str; raw UUID passes through _svc_wire_to_db_uuid unchanged.
    """
    raw_uuid_svc = _insert_service(postgres_container, cred_tenant, slug="cred-svc-uuid-rot")

    # Register
    _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{raw_uuid_svc}/credentials",
        json={"auth_scheme": "api_key_header", "value": "uuid-initial"},
    )

    # Rotate using raw UUID service_id
    rot = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{raw_uuid_svc}/credentials/rotate",
        json={"auth_scheme": "api_key_header", "value": "uuid-rotated"},
    )
    assert rot.status_code == 200, rot.text
    assert rot.json()["auth_scheme"] == "api_key_header"


def test_rotate_credential_svc_hex_wire_form(
    admin_app: TestClient, cred_tenant: str, postgres_container
) -> None:
    """
    Rotation works with svc_<32-hex> wire form — the old serialised form per ADR-0017.11.
    """
    raw_uuid_svc = _insert_service(postgres_container, cred_tenant, slug="cred-svc-hex-rot")

    # Build the svc_<32-hex> wire form from the UUID
    hex_form = "svc_" + raw_uuid_svc.replace("-", "")

    # Register using raw UUID (existing endpoint only accepts UUID path param)
    _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{raw_uuid_svc}/credentials",
        json={"auth_scheme": "bearer_token", "value": "hex-initial"},
    )

    # Rotate using svc_<32-hex> wire form
    rot = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{hex_form}/credentials/rotate",
        json={"auth_scheme": "bearer_token", "value": "hex-rotated"},
    )
    assert rot.status_code == 200, rot.text
    assert rot.json()["id"].startswith("cred_")


def test_rotate_credential_service_not_found_returns_404(
    admin_app: TestClient, cred_tenant: str
) -> None:
    """Rotate with a nonexistent service → 404."""
    import uuid as _uuid
    fake_svc = str(_uuid.uuid4())
    rot = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{fake_svc}/credentials/rotate",
        json={"auth_scheme": "bearer_token", "value": "x"},
    )
    assert rot.status_code == 404
    assert rot.json()["mintkey:code"] == "not_found"


def test_rotate_credential_no_active_credential_returns_404(
    admin_app: TestClient, cred_tenant: str, postgres_container
) -> None:
    """Rotate when no active credential exists for the given scheme → 404."""
    svc = _insert_service(postgres_container, cred_tenant, slug="cred-svc-noactive-rot")
    rot = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{svc}/credentials/rotate",
        json={"auth_scheme": "bearer_token"},
    )
    assert rot.status_code == 404
    assert rot.json()["mintkey:code"] == "not_found"


def test_rotate_credential_malformed_body_returns_422(
    admin_app: TestClient, cred_tenant: str, cred_service_for_rotate: str
) -> None:
    """Missing required auth_scheme field → 422."""
    rot = _post(
        admin_app,
        f"/v1/tenants/{cred_tenant}/services/{cred_service_for_rotate}/credentials/rotate",
        json={"value": "no-scheme"},  # missing auth_scheme
    )
    assert rot.status_code == 422


def test_rotate_credential_cross_tenant_rls(
    admin_app: TestClient,
    cred_tenant_b: str,
    cred_service_for_rotate: str,
) -> None:
    """
    Tenant B cannot rotate credentials belonging to Tenant A's service.
    RLS causes the service lookup to return 0 rows → 404 (not 403, preserving
    information-hiding — the service doesn't "exist" from tenant B's view).
    """
    rot = _post(
        admin_app,
        # Use tenant_b's tenant_id but Tenant A's service_id
        f"/v1/tenants/{cred_tenant_b}/services/{cred_service_for_rotate}/credentials/rotate",
        json={"auth_scheme": "bearer_token", "value": "cross-tenant-attempt"},
    )
    # Service not visible under tenant B → 404
    assert rot.status_code == 404
    assert rot.json()["mintkey:code"] == "not_found"
