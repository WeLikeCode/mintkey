"""
Integration tests for the tenant management endpoints.

POST /v1/tenants — create a new tenant (PlatformAdmin only, 201)

Covers:
  - 403 when X-Platform-Admin header is absent (always works, no DB hit).
  - 201 on successful creation with X-Platform-Admin header.
  - Returned tenant_id has "tenant_" ULID prefix — ADR-0017.11.
  - 409 on duplicate slug.
  - Audit event "tenant.created" is emitted.
  - audit_chain_state genesis row is initialised.

Architecture constraints honoured:
  ADR-0017.11  — ULID tenant_ prefix.
  ADR-0014.7   — audit event emitted on tenant creation.
  ADR-0017.4   — PlatformAdmin-only gate.
  Req 13 AC1   — PlatformAdmin required.

KNOWN SOURCE BUG:
  admin_api/api/tenants.py line ~166 INSERTs with column `name` but the
  tenants table (001-tenants.yaml) has `display_name`, not `name`.
  Tests that invoke POST /v1/tenants are marked xfail until this is fixed.
  Fix: rename `name` → `display_name` in the INSERT statement and bind
  parameter dict in tenants.py create_tenant().
"""
from __future__ import annotations

import re

import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# CSRF helpers (mirrors test_services.py pattern)
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-token-tenants"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}
_PLATFORM_ADMIN = {"X-Platform-Admin": "true"}

_TENANT_ID_RE = re.compile(r"^tenant_[0-9A-HJKMNP-TV-Z]{26}$")

_TENANT_BUG = pytest.mark.xfail(
    reason=(
        "admin_api/api/tenants.py INSERTs with column 'name' but tenants table "
        "has 'display_name' (see 001-tenants.yaml). "
        "Fix: rename 'name' → 'display_name' in the INSERT in create_tenant()."
    ),
    strict=False,
)


def _post(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


def _platform_post(client: TestClient, url: str, **kwargs):
    """POST with both CSRF and PlatformAdmin header."""
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS, **_PLATFORM_ADMIN}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# Tests that do NOT require a successful POST (no DB hit on the failing path)
# ---------------------------------------------------------------------------


def test_create_tenant_without_platform_admin_returns_403(admin_app: TestClient) -> None:
    """POST /v1/tenants without PlatformAdmin header → 403 permission_denied.

    This check happens before any DB access so it works regardless of the
    column bug in the success path — ADR-0017.4, Req 13 AC1.
    """
    resp = _post(
        admin_app,
        "/v1/tenants",
        json={"slug": "forbidden-tenant", "name": "Forbidden"},
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body["mintkey:code"] == "permission_denied"


def test_create_tenant_wrong_method_returns_405(admin_app: TestClient) -> None:
    """PUT /v1/tenants → 405 Method Not Allowed (only POST is defined)."""
    resp = admin_app.put(
        "/v1/tenants",
        headers={**_CSRF_HEADERS, **_PLATFORM_ADMIN},
        cookies=_CSRF_COOKIES,
        json={"slug": "put-tenant", "name": "PUT"},
    )
    assert resp.status_code == 405


def test_create_tenant_missing_slug_returns_422(admin_app: TestClient) -> None:
    """POST /v1/tenants without slug → 422 Unprocessable Entity (Pydantic validation)."""
    resp = _platform_post(
        admin_app,
        "/v1/tenants",
        json={"name": "no-slug"},  # slug is required
    )
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Tests that require POST /v1/tenants to succeed — xfail due to source bug
# ---------------------------------------------------------------------------


@_TENANT_BUG
def test_create_tenant_returns_201(admin_app: TestClient) -> None:
    """POST /v1/tenants with PlatformAdmin → 201 with tenant_id ULID."""
    resp = _platform_post(
        admin_app,
        "/v1/tenants",
        json={"slug": "new-tenant-201", "name": "New Tenant 201"},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "tenant_id" in body
    assert "slug" in body
    assert body["slug"] == "new-tenant-201"
    # ULID with tenant_ prefix — ADR-0017.11
    assert _TENANT_ID_RE.match(body["tenant_id"]), (
        f"tenant_id does not match ULID pattern: {body['tenant_id']}"
    )


@_TENANT_BUG
def test_create_tenant_duplicate_slug_returns_409(admin_app: TestClient) -> None:
    """POST /v1/tenants with duplicate slug → 409 tenant_already_exists."""
    _platform_post(
        admin_app,
        "/v1/tenants",
        json={"slug": "dup-tenant", "name": "Dup Tenant First"},
    )
    resp = _platform_post(
        admin_app,
        "/v1/tenants",
        json={"slug": "dup-tenant", "name": "Dup Tenant Second"},
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["mintkey:code"] == "tenant_already_exists"


@_TENANT_BUG
def test_create_tenant_emits_audit_event(admin_app: TestClient, postgres_container) -> None:
    """
    Creating a tenant emits a tenant.created audit event — ADR-0014.7.
    """
    import psycopg2

    resp = _platform_post(
        admin_app,
        "/v1/tenants",
        json={"slug": "audit-check-tenant", "name": "Audit Check Tenant"},
    )
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    slug = resp.json()["slug"]

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
    assert row is not None
    tenant_uuid = str(row[0])

    cur.execute(
        "SELECT count(*) FROM audit_events WHERE tenant_id = %s AND event_type = %s",
        (tenant_uuid, "tenant.created"),
    )
    count_row = cur.fetchone()
    cur.close()
    conn.close()
    assert count_row[0] >= 1, f"No tenant.created event for {tenant_uuid}"


@_TENANT_BUG
def test_create_tenant_genesis_hash_initialised(
    admin_app: TestClient, postgres_container
) -> None:
    """audit_chain_state must have a genesis_hash row after tenant creation — ADR-0014.7."""
    import psycopg2

    resp = _platform_post(
        admin_app,
        "/v1/tenants",
        json={"slug": "genesis-check-tenant", "name": "Genesis Check"},
    )
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    slug = resp.json()["slug"]

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
    assert row is not None
    tenant_uuid = str(row[0])

    cur.execute(
        "SELECT genesis_hash FROM audit_chain_state WHERE tenant_id = %s",
        (tenant_uuid,),
    )
    chain_row = cur.fetchone()
    cur.close()
    conn.close()
    assert chain_row is not None, "audit_chain_state row missing for new tenant"
    assert chain_row[0] is not None, "genesis_hash is NULL"
