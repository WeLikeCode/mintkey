"""
Integration tests for the service-template API endpoints.

Task 5.4 from the service-templates Kiro spec:
  - GET /v1/service-templates → 13 templates
  - GET with category filter → correct subset
  - GET with case-insensitive search
  - GET /v1/service-templates/{id} → full detail
  - GET /v1/service-templates/nonexistent → 404 template_not_found
  - POST /from-template → creates service with template values
  - POST /from-template with overrides → applies them
  - POST /from-template emits service.registered audit + change-channel payload
  - POST /from-template duplicate name → 409 service_name_taken
  - POST /from-template unknown template_id → 404 template_not_found

These tests use the shared `admin_app` + `postgres_container` fixtures from the
integration conftest (real DB, real app, real registry). No mocking of SUT.

Source: Requirements 2.1-2.4, 3.1-3.2, 4.1-4.5; design §§3-4.
"""
from __future__ import annotations

import uuid as _uuid_mod
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-tmpl-api-csrf-abc123"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}

# The 13 bundled template IDs expected in the catalog.
_EXPECTED_TEMPLATE_IDS = {
    "gitlab",
    "apple-app-store-connect",
    "google-play-developer",
    "azure-devops",
    "heroku",
    "brave-search",
    "sendgrid",
    "twilio",
    "stripe",
    "cloudflare",
    "datadog",
    "pagerduty",
    "azure-dashboard-api",
}

# Required fields on every list item (Req 2.2, 18.3).
_LIST_ITEM_FIELDS = {
    "template_id",
    "name",
    "display_name",
    "description",
    "base_url",
    "auth_type",
    "openapi_spec_url",
    "category",
    "version",
}


# ---------------------------------------------------------------------------
# DB helpers (mirror pattern from test_service_templates.py / test_fix10_bugs.py)
# ---------------------------------------------------------------------------

def _seed_tenant(postgres_container, slug: str) -> str:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_config('app.current_tenant', %s, false)",
                ("00000000-0000-0000-0000-000000000000",),
            )
            cur.execute("SELECT set_config('app.platform_admin_view', 'on', false)")
            cur.execute(
                "INSERT INTO tenants (slug, display_name, isolation_mode, status)"
                " VALUES (%s, %s, 'row', 'active') ON CONFLICT (slug) DO NOTHING RETURNING id",
                (slug, f"T-5.4 tenant {slug}"),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
                row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    assert row is not None
    return str(row[0])


def _seed_session(postgres_container, tenant_id: str) -> str:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    conn.autocommit = False
    operator_id = str(_uuid_mod.uuid4())
    session_id = str(_uuid_mod.uuid4())
    expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT set_config('app.current_tenant', %s, false)",
                (tenant_id,),
            )
            cur.execute("SELECT set_config('app.platform_admin_view', 'on', false)")
            cur.execute(
                "INSERT INTO operators"
                " (id, tenant_id, email, display_name, internal_password_hash,"
                "  is_platform_admin, status, created_at)"
                " VALUES (%s, %s, %s, %s, NULL, %s, 'active', now())"
                " ON CONFLICT (id) DO NOTHING",
                (
                    operator_id,
                    tenant_id,
                    f"t54-{operator_id[:8]}@mintkey.internal",
                    f"t54-{operator_id[:8]}",
                    False,
                ),
            )
            cur.execute(
                "INSERT INTO sessions"
                " (id, tenant_id, operator_id, expires_at, last_used_at, created_at, auth_method)"
                " VALUES (%s, %s, %s, %s, now(), now(), 'internal')"
                " ON CONFLICT (id) DO NOTHING",
                (session_id, tenant_id, operator_id, expires_at),
            )
        conn.commit()
    finally:
        conn.close()
    return session_id


def _read_audit_row(postgres_container, tenant_id: str, event_type: str) -> dict | None:
    """Return the latest audit event payload matching tenant + event_type, or None.

    The audit_events table uses `at` as its timestamp column (not `created_at`).
    """
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    try:
        with conn.cursor() as cur:
            # Must set platform admin view to bypass RLS so the helper can read audit rows
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (tenant_id,))
            cur.execute("SELECT set_config('app.platform_admin_view', 'on', false)")
            cur.execute(
                "SELECT payload FROM audit_events"
                " WHERE tenant_id = %s AND event_type = %s"
                " ORDER BY at DESC LIMIT 1",
                (tenant_id, event_type),
            )
            row = cur.fetchone()
    finally:
        conn.close()
    if row is None:
        return None
    import json
    return json.loads(row[0]) if isinstance(row[0], str) else row[0]


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def t54_tenant(admin_app: TestClient, postgres_container) -> str:
    return _seed_tenant(postgres_container, "t-5-4-template-api")


@pytest.fixture(scope="module")
def t54_session(admin_app: TestClient, postgres_container, t54_tenant: str) -> str:
    return _seed_session(postgres_container, t54_tenant)


# ---------------------------------------------------------------------------
# GET /v1/service-templates — list endpoint
# ---------------------------------------------------------------------------


def test_5_4_list_returns_13_templates(admin_app: TestClient):
    """GET /v1/service-templates returns exactly 13 templates."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    body = resp.json()
    assert "templates" in body
    assert len(body["templates"]) == 13, (
        f"Expected 13 templates, got {len(body['templates'])}"
    )


def test_5_4_list_all_template_ids_present(admin_app: TestClient):
    """All 13 expected template_ids are present in the list."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    ids = {t["template_id"] for t in resp.json()["templates"]}
    assert ids == _EXPECTED_TEMPLATE_IDS


def test_5_4_category_filter_ci_cd(admin_app: TestClient):
    """GET ?category=ci_cd returns exactly gitlab + azure-devops."""
    resp = admin_app.get("/v1/service-templates?category=ci_cd")
    assert resp.status_code == 200
    ids = {t["template_id"] for t in resp.json()["templates"]}
    assert ids == {"gitlab", "azure-devops"}, (
        f"Unexpected ci_cd results: {ids}"
    )


def test_5_4_category_filter_payments(admin_app: TestClient):
    """GET ?category=payments returns only stripe."""
    resp = admin_app.get("/v1/service-templates?category=payments")
    assert resp.status_code == 200
    ids = {t["template_id"] for t in resp.json()["templates"]}
    assert ids == {"stripe"}


def test_5_4_search_filter_case_insensitive_upper(admin_app: TestClient):
    """Search with UPPERCASE finds the matching template (case-insensitive)."""
    resp = admin_app.get("/v1/service-templates?search=STRIPE")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    assert len(templates) == 1
    assert templates[0]["template_id"] == "stripe"


def test_5_4_search_filter_case_insensitive_mixed(admin_app: TestClient):
    """Search with MiXeD case finds the matching template."""
    resp = admin_app.get("/v1/service-templates?search=GitLab")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    assert len(templates) == 1
    assert templates[0]["template_id"] == "gitlab"


def test_5_4_search_matches_description(admin_app: TestClient):
    """Search matches against the description field."""
    # "pagerduty" description contains "incident"
    resp = admin_app.get("/v1/service-templates?search=incident")
    assert resp.status_code == 200
    ids = {t["template_id"] for t in resp.json()["templates"]}
    assert "pagerduty" in ids, f"Expected pagerduty in description-search results: {ids}"


# ---------------------------------------------------------------------------
# GET /v1/service-templates/{template_id} — detail endpoint
# ---------------------------------------------------------------------------


def test_5_4_detail_returns_full_shape(admin_app: TestClient):
    """GET /v1/service-templates/gitlab returns all required fields + config_notes + test_path."""
    resp = admin_app.get("/v1/service-templates/gitlab")
    assert resp.status_code == 200
    body = resp.json()
    for field in _LIST_ITEM_FIELDS:
        assert field in body, f"Missing field {field!r} in detail response"
    assert "config_notes" in body, "Missing config_notes in detail"
    assert "test_path" in body, "Missing test_path in detail"
    assert body["template_id"] == "gitlab"


def test_5_4_detail_nonexistent_returns_404(admin_app: TestClient):
    """GET /v1/service-templates/nonexistent → 404 with mintkey:code=template_not_found."""
    resp = admin_app.get("/v1/service-templates/nonexistent-template-xyz")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("mintkey:code") == "template_not_found", (
        f"Expected template_not_found code, got: {body}"
    )


def test_5_4_detail_azure_dashboard_has_credential_hint(admin_app: TestClient):
    """GET /v1/service-templates/azure-dashboard-api includes credential_hint."""
    resp = admin_app.get("/v1/service-templates/azure-dashboard-api")
    assert resp.status_code == 200
    body = resp.json()
    assert "credential_hint" in body
    hint = body["credential_hint"]
    assert hint is not None
    assert "token_url" in hint
    assert "credential_fields" in hint
    assert "token_response_path" in hint


# ---------------------------------------------------------------------------
# POST /v1/tenants/{tid}/services/from-template — instantiation endpoint
# ---------------------------------------------------------------------------


def test_5_4_from_template_creates_service_with_template_values(
    admin_app: TestClient,
    t54_tenant: str,
    t54_session: str,
) -> None:
    """POST /from-template creates a service whose fields match the template."""
    resp = admin_app.post(
        f"/v1/tenants/{t54_tenant}/services/from-template",
        json={"template_id": "stripe"},
        headers=_CSRF_HEADERS,
        cookies={**_CSRF_COOKIES, "mintkey_session": t54_session},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    # Template values must be reflected
    assert body["auth_scheme"] == "bearer_token", (
        f"Expected auth_scheme=bearer_token, got {body.get('auth_scheme')!r}"
    )
    assert body["base_url"] == "https://api.stripe.com/v1", (
        f"Unexpected base_url: {body.get('base_url')!r}"
    )
    assert body["name"] == "stripe"
    assert body["template_id"] == "stripe"
    assert body["status"] == "active"
    assert body["id"].startswith("svc_")


def test_5_4_from_template_with_name_override(
    admin_app: TestClient,
    t54_tenant: str,
    t54_session: str,
) -> None:
    """POST /from-template with name override creates service with the override name."""
    resp = admin_app.post(
        f"/v1/tenants/{t54_tenant}/services/from-template",
        json={
            "template_id": "gitlab",
            "overrides": {"name": "my-gitlab-instance"},
        },
        headers=_CSRF_HEADERS,
        cookies={**_CSRF_COOKIES, "mintkey_session": t54_session},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["name"] == "my-gitlab-instance", (
        f"Name override not applied: {body.get('name')!r}"
    )
    # Non-overridden fields still come from template
    assert body["auth_scheme"] == "bearer_token"
    assert body["template_id"] == "gitlab"


def test_5_4_from_template_with_base_url_override(
    admin_app: TestClient,
    t54_tenant: str,
    t54_session: str,
) -> None:
    """POST /from-template with base_url override uses the provided URL."""
    resp = admin_app.post(
        f"/v1/tenants/{t54_tenant}/services/from-template",
        json={
            "template_id": "datadog",
            "overrides": {
                "name": "datadog-eu",
                "base_url": "https://api.datadoghq.eu",
            },
        },
        headers=_CSRF_HEADERS,
        cookies={**_CSRF_COOKIES, "mintkey_session": t54_session},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["base_url"] == "https://api.datadoghq.eu"
    assert body["name"] == "datadog-eu"


def test_5_4_from_template_emits_service_registered_audit(
    admin_app: TestClient,
    t54_tenant: str,
    t54_session: str,
    postgres_container,
) -> None:
    """POST /from-template emits service.registered audit event with template_id in payload."""
    resp = admin_app.post(
        f"/v1/tenants/{t54_tenant}/services/from-template",
        json={"template_id": "cloudflare", "overrides": {"name": "cloudflare-audit-test"}},
        headers=_CSRF_HEADERS,
        cookies={**_CSRF_COOKIES, "mintkey_session": t54_session},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"

    audit_payload = _read_audit_row(postgres_container, t54_tenant, "service.registered")
    assert audit_payload is not None, "No service.registered audit event found"
    assert "template_id" in audit_payload, (
        f"template_id missing from audit payload: {audit_payload}"
    )
    assert audit_payload["template_id"] == "cloudflare"


def test_5_4_from_template_duplicate_name_returns_409(
    admin_app: TestClient,
    t54_tenant: str,
    t54_session: str,
) -> None:
    """POST /from-template with duplicate service name → 409 service_name_taken."""
    common_body = {
        "template_id": "sendgrid",
        "overrides": {"name": "sendgrid-dup-test"},
    }
    headers = _CSRF_HEADERS
    cookies = {**_CSRF_COOKIES, "mintkey_session": t54_session}

    # First creation must succeed
    resp1 = admin_app.post(
        f"/v1/tenants/{t54_tenant}/services/from-template",
        json=common_body,
        headers=headers,
        cookies=cookies,
    )
    assert resp1.status_code == 201, f"First creation failed: {resp1.text}"

    # Second creation with same name must yield 409
    resp2 = admin_app.post(
        f"/v1/tenants/{t54_tenant}/services/from-template",
        json=common_body,
        headers=headers,
        cookies=cookies,
    )
    assert resp2.status_code == 409, (
        f"Expected 409 for duplicate name, got {resp2.status_code}: {resp2.text}"
    )
    body2 = resp2.json()
    assert body2.get("mintkey:code") == "service_name_taken", (
        f"Expected service_name_taken, got: {body2}"
    )


def test_5_4_from_template_unknown_template_id_returns_404(
    admin_app: TestClient,
    t54_tenant: str,
    t54_session: str,
) -> None:
    """POST /from-template with unknown template_id → 404 template_not_found."""
    resp = admin_app.post(
        f"/v1/tenants/{t54_tenant}/services/from-template",
        json={"template_id": "no-such-template-xyzzy"},
        headers=_CSRF_HEADERS,
        cookies={**_CSRF_COOKIES, "mintkey_session": t54_session},
    )
    assert resp.status_code == 404, (
        f"Expected 404 for unknown template_id, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("mintkey:code") == "template_not_found", (
        f"Expected template_not_found code, got: {body}"
    )
