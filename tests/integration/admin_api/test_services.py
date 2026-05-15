"""
Integration tests for service CRUD + single-get + test endpoints.

Covers:
  POST   /v1/tenants/{tenant_id}/services         — create (201)
  GET    /v1/tenants/{tenant_id}/services         — list (200)
  GET    /v1/tenants/{tenant_id}/services/{sid}   — get single (200 / 404)
  PATCH  /v1/tenants/{tenant_id}/services/{sid}   — update (200)
  DELETE /v1/tenants/{tenant_id}/services/{sid}   — delete (204)
  POST   /v1/tenants/{tenant_id}/services/{sid}/test — connectivity test (200)

Cross-tenant isolation: tenant A cannot read tenant B's services.

Architecture constraints honoured:
  ADR-0017.11 — ULID svc_ prefix IDs
  S-SEC-1     — SSRF: RFC1918 base_url → 422
  ADR-0014.7  — audit event emitted on every state change
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# CSRF helpers — double-submit cookie pattern.
# The middleware requires that the cookie `csrf_token` and header
# `x-mintkey-csrf` carry the same value.
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-token-abc123"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}
_PLATFORM_ADMIN_HEADER = {"X-Platform-Admin": "true"}


def _post(client: TestClient, url: str, **kwargs):
    """POST with CSRF cookie + header injected."""
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


def _patch(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.patch(url, headers=headers, cookies=cookies, **kwargs)


def _delete(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.delete(url, headers=headers, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _insert_tenant(postgres_container, slug: str) -> str:
    """Insert a tenant row directly and return its UUID string."""
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
    # Check if already exists (idempotent for module-scoped fixtures)
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


@pytest.fixture(scope="module")
def tenant_uuid(admin_app: TestClient, postgres_container) -> str:
    """Create a tenant directly in DB and return its internal UUID."""
    return _insert_tenant(postgres_container, "test-svc-tenant")


@pytest.fixture(scope="module")
def tenant_b_uuid(admin_app: TestClient, postgres_container) -> str:
    """A second tenant for cross-tenant isolation tests."""
    return _insert_tenant(postgres_container, "test-svc-tenant-b")


@pytest.fixture(scope="module")
def service_id(admin_app: TestClient, tenant_uuid: str) -> str:
    """
    Create a service and return the canonical wire ID from the list endpoint.

    We POST to create, then GET the list to obtain the hex-form svc_ ID that
    _service_row_to_dict produces — this is the ID the GET single route accepts.
    """
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_uuid}/services",
        json={
            "name": "test-service",
            "base_url": "https://example.com/api",
            "auth_scheme": "bearer_token",
            "display_name": "Test Service",
        },
    )
    assert resp.status_code == 201, f"Failed to create service: {resp.text}"

    # Fetch the canonical ID from the list endpoint (svc_<Crockford> form per ADR-0017.11 / #13)
    list_resp = admin_app.get(f"/v1/tenants/{tenant_uuid}/services")
    assert list_resp.status_code == 200
    services = list_resp.json()["services"]
    matches = [s for s in services if s["name"] == "test-service"]
    assert matches, f"Created service not found in list: {services}"
    return matches[0]["id"]


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


def test_create_service_returns_201(admin_app: TestClient, tenant_uuid: str) -> None:
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_uuid}/services",
        json={
            "name": "another-svc",
            "base_url": "https://other.example.com/api",
            "auth_scheme": "api_key",
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "another-svc"
    assert len(body["id"]) > 0


def test_create_service_ssrf_rejected(admin_app: TestClient, tenant_uuid: str) -> None:
    """RFC1918 base_url must be rejected with 422 — S-SEC-1."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_uuid}/services",
        json={
            "name": "evil",
            "base_url": "http://192.168.1.100/api",
            "auth_scheme": "bearer_token",
        },
    )
    assert resp.status_code == 422
    assert resp.json().get("mintkey:code") == "forbidden_destination"


# ---------------------------------------------------------------------------
# List
# ---------------------------------------------------------------------------


def test_list_services_returns_200(
    admin_app: TestClient, tenant_uuid: str, service_id: str
) -> None:
    resp = admin_app.get(f"/v1/tenants/{tenant_uuid}/services")
    assert resp.status_code == 200
    body = resp.json()
    assert "services" in body
    ids = [s["id"] for s in body["services"]]
    assert service_id in ids


# ---------------------------------------------------------------------------
# Get single — NEW ROUTE
# ---------------------------------------------------------------------------


def test_get_single_service_returns_200(
    admin_app: TestClient, tenant_uuid: str, service_id: str
) -> None:
    """GET /v1/tenants/{tenant_id}/services/{service_id} → 200 with the service."""
    resp = admin_app.get(f"/v1/tenants/{tenant_uuid}/services/{service_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == service_id
    assert body["name"] == "test-service"
    assert body["auth_scheme"] == "bearer_token"


def test_get_single_service_unknown_id_returns_404(
    admin_app: TestClient, tenant_uuid: str
) -> None:
    """GET with unknown service_id → 404."""
    # Use a valid UUID that doesn't exist
    fake_id = "svc_" + "0" * 32  # 32 hex chars → valid UUID form after conversion
    resp = admin_app.get(f"/v1/tenants/{tenant_uuid}/services/{fake_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


def test_update_service_returns_200(
    admin_app: TestClient, tenant_uuid: str, service_id: str
) -> None:
    resp = _patch(
        admin_app,
        f"/v1/tenants/{tenant_uuid}/services/{service_id}",
        json={"display_name": "Updated Name"},
    )
    assert resp.status_code == 200
    assert resp.json()["display_name"] == "Updated Name"


# ---------------------------------------------------------------------------
# Cross-tenant isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_get_returns_404(
    admin_app: TestClient,
    tenant_uuid: str,
    tenant_b_uuid: str,
    service_id: str,
) -> None:
    """Tenant B cannot read tenant A's service — must return 404."""
    resp = admin_app.get(f"/v1/tenants/{tenant_b_uuid}/services/{service_id}")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# POST /test — NEW ROUTE
# ---------------------------------------------------------------------------


def test_post_service_test_returns_ok(
    admin_app: TestClient, tenant_uuid: str, service_id: str
) -> None:
    """POST /…/test with a mocked outbound HTTP call → {"ok": true, "status_code": 200}."""
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"status":"ok"}'

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    # R14b fix: handler now calls client.request(...) instead of client.get(...)
    mock_client.request = AsyncMock(return_value=mock_response)

    with patch("admin_api.api.services.httpx.AsyncClient", return_value=mock_client):
        resp = _post(admin_app, f"/v1/tenants/{tenant_uuid}/services/{service_id}/test")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["status_code"] == 200


def test_post_service_test_unknown_service_returns_404(
    admin_app: TestClient, tenant_uuid: str
) -> None:
    """POST /test for unknown service_id → 404."""
    fake_id = "svc_" + "0" * 32
    resp = _post(admin_app, f"/v1/tenants/{tenant_uuid}/services/{fake_id}/test")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


def test_delete_service_returns_204(admin_app: TestClient, tenant_uuid: str) -> None:
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_uuid}/services",
        json={
            "name": "svc-to-delete",
            "base_url": "https://delete-me.example.com/api",
            "auth_scheme": "bearer_token",
        },
    )
    assert resp.status_code == 201

    # Get canonical ID from list
    list_resp = admin_app.get(f"/v1/tenants/{tenant_uuid}/services")
    services = list_resp.json()["services"]
    matches = [s for s in services if s["name"] == "svc-to-delete"]
    assert matches, "Service to delete not found"
    svc_id = matches[0]["id"]

    del_resp = _delete(admin_app, f"/v1/tenants/{tenant_uuid}/services/{svc_id}")
    assert del_resp.status_code == 204


# ---------------------------------------------------------------------------
# POST /test — UX-C5 Bug 2: api_key_header with specific header_name
# ---------------------------------------------------------------------------


def test_post_service_test_api_key_header_uses_header_name(
    admin_app: TestClient, tenant_uuid: str
) -> None:
    """
    POST /…/test for an api_key_header service must inject the credential
    under the header name specified in the vault response (header_name field).

    The mock vault client returns header_name="X-Custom-Auth"; the mock
    httpx client captures the headers passed to client.request() and asserts
    that "X-Custom-Auth" is present with the credential value.

    Source: UX-C5 Bug 2; Bug 3.
    """
    # Create a service with auth_scheme=api_key_header
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_uuid}/services",
        json={
            "name": "svc-api-key-header-test",
            "base_url": "https://echo.example.com/api",
            "auth_scheme": "api_key_header",
        },
    )
    assert create_resp.status_code == 201, f"create failed: {create_resp.text}"

    # Get canonical ID from list
    list_resp = admin_app.get(f"/v1/tenants/{tenant_uuid}/services")
    services = list_resp.json()["services"]
    matches = [s for s in services if s["name"] == "svc-api-key-header-test"]
    assert matches, f"Created service not found in list: {services}"
    svc_id = matches[0]["id"]

    # Track the headers that httpx would send outbound
    captured_headers: dict = {}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"status":"ok"}'

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def _capture_request(**kwargs):
        captured_headers.update(kwargs.get("headers", {}))
        return mock_response

    mock_client.request = _capture_request

    # Vault mock: returns plaintext + header_name="X-Custom-Auth"
    mock_vault = MagicMock()
    mock_vault.get_credential = AsyncMock(return_value={
        "plaintext": "my-secret-api-key",
        "auth_scheme": 1,
        "key_version": 1,
        "header_name": "X-Custom-Auth",
        "query_param": "",
    })

    with (
        patch("admin_api.api.services.httpx.AsyncClient", return_value=mock_client),
        # get_vault_client is imported locally inside test_service(), so patch
        # at the canonical module path rather than via the services module namespace.
        patch("admin_api.services.vault_client.get_vault_client", AsyncMock(return_value=mock_vault)),
    ):
        resp = _post(admin_app, f"/v1/tenants/{tenant_uuid}/services/{svc_id}/test")

    assert resp.status_code == 200, f"test endpoint failed: {resp.text}"
    body = resp.json()
    assert body["ok"] is True

    assert "X-Custom-Auth" in captured_headers, (
        f"Expected 'X-Custom-Auth' header in outbound request; got headers: {list(captured_headers.keys())}"
    )
    assert captured_headers["X-Custom-Auth"] == "my-secret-api-key", (
        f"Header value mismatch: {captured_headers.get('X-Custom-Auth')!r}"
    )
    # Ensure the old wrong header name is NOT present
    assert "X-Api-Key" not in captured_headers, (
        "Old bug: 'X-Api-Key' header must not be present after Bug 2 fix"
    )


def test_post_service_test_api_key_header_fallback_to_default(
    admin_app: TestClient, tenant_uuid: str
) -> None:
    """
    When vault returns an empty header_name for api_key_header, test_service
    must fall back to 'X-API-Key' and log a warning (safety net per UX-C5).

    Source: UX-C5 Bug 2 — fallback default.
    """
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_uuid}/services",
        json={
            "name": "svc-api-key-header-fallback",
            "base_url": "https://echo.example.com/api",
            "auth_scheme": "api_key_header",
        },
    )
    assert create_resp.status_code == 201

    list_resp = admin_app.get(f"/v1/tenants/{tenant_uuid}/services")
    services = list_resp.json()["services"]
    matches = [s for s in services if s["name"] == "svc-api-key-header-fallback"]
    assert matches
    svc_id = matches[0]["id"]

    captured_headers: dict = {}

    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.text = '{"status":"ok"}'

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    async def _capture_request(**kwargs):
        captured_headers.update(kwargs.get("headers", {}))
        return mock_response

    mock_client.request = _capture_request

    # Vault mock: empty header_name → should trigger fallback
    mock_vault = MagicMock()
    mock_vault.get_credential = AsyncMock(return_value={
        "plaintext": "fallback-key",
        "auth_scheme": 1,
        "key_version": 1,
        "header_name": "",
        "query_param": "",
    })

    with (
        patch("admin_api.api.services.httpx.AsyncClient", return_value=mock_client),
        patch("admin_api.services.vault_client.get_vault_client", AsyncMock(return_value=mock_vault)),
    ):
        resp = _post(admin_app, f"/v1/tenants/{tenant_uuid}/services/{svc_id}/test")

    assert resp.status_code == 200
    assert "X-API-Key" in captured_headers, (
        f"Expected fallback 'X-API-Key' header; got: {list(captured_headers.keys())}"
    )
    assert captured_headers["X-API-Key"] == "fallback-key"
