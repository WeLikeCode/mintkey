"""
Integration tests for GET /v1/service-templates.

Covers:
  GET /v1/service-templates              — returns all 16 templates sorted by name
  GET /v1/service-templates/{template_id} — returns full template for each entry
  GET /v1/service-templates/unknown      — returns 404 with mintkey:code=template_not_found
  auth_type invariant                    — each template's auth_type is valid
  base_url invariant                     — each template's base_url starts with https://
  test_path invariant                    — each template has a non-empty test_path
  category filter                        — ?category= returns correct subset
  search filter                          — ?search= is case-insensitive across name/display_name/description
  Req 23.5 — from-template returns credential_hint for oauth2_password_grant templates

Source: Requirements 1.1-1.4, 2.1-2.4, 3.1-3.2, 18.3, 23.5.
"""
from __future__ import annotations

import uuid as _uuid_mod
from datetime import datetime, timedelta, timezone

import psycopg2
import pytest
from starlette.testclient import TestClient

# Valid auth_type values per the design document.
AUTH_TYPES = {
    "api_key_header",
    "api_key_query",
    "bearer_token",
    "basic_auth",
    "oauth2_client_credentials",
    "oidc_client_secret",
    "oauth2_password_grant",
}

# The 16 bundled template IDs from service_templates.yaml.
TEMPLATE_IDS = {
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
    "spotus-dashboard-api",
    "github",
    "openai",
    "slack",
}

# Required fields on a list-item wire representation (Req 2.2, 18.3).
LIST_ITEM_FIELDS = {
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

# Expected test_path values per template.
EXPECTED_TEST_PATHS: dict[str, str] = {
    "gitlab": "/version",
    "apple-app-store-connect": "/apps",
    "google-play-developer": "/androidpublisher/v3/applications",
    "azure-devops": "/_apis/projects?api-version=7.0",
    "heroku": "/account",
    "brave-search": "/web/search?q=test&count=1",
    "sendgrid": "/user/profile",
    "twilio": "/Accounts.json",
    "stripe": "/charges?limit=1",
    "cloudflare": "/user/tokens/verify",
    "datadog": "/api/v2/validate",
    "pagerduty": "/abilities",
    "spotus-dashboard-api": "/api/v1/Identity/me",
    "github": "/user",
    "openai": "/models",
    "slack": "/api.test",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_templates_returns_sixteen_entries(admin_app: TestClient):
    """GET /v1/service-templates returns exactly 16 templates."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    body = resp.json()
    assert "templates" in body
    assert len(body["templates"]) == 16


def test_list_templates_all_have_unique_names(admin_app: TestClient):
    """All templates have unique names."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()["templates"]]
    assert len(names) == len(set(names)), "Duplicate template names found"


def test_list_templates_summary_fields(admin_app: TestClient):
    """Every list entry contains all required fields (Req 2.2, 18.3)."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    for tmpl in resp.json()["templates"]:
        for field in LIST_ITEM_FIELDS:
            assert field in tmpl, f"Missing field {field!r} in list item"


def test_list_templates_ids_match_catalog(admin_app: TestClient):
    """The returned template_ids exactly match the expected catalog set."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    ids = {t["template_id"] for t in resp.json()["templates"]}
    assert ids == TEMPLATE_IDS


@pytest.mark.parametrize("template_id", sorted(TEMPLATE_IDS))
def test_get_template_full_shape(admin_app: TestClient, template_id: str):
    """GET /v1/service-templates/{template_id} returns all required fields."""
    resp = admin_app.get(f"/v1/service-templates/{template_id}")
    assert resp.status_code == 200, (
        f"template_id={template_id}: expected 200, got {resp.status_code}"
    )
    body = resp.json()
    for field in LIST_ITEM_FIELDS:
        assert field in body, f"template_id={template_id}: missing field {field!r}"
    # template_id in body must match the path parameter
    assert body["template_id"] == template_id


@pytest.mark.parametrize("template_id", sorted(TEMPLATE_IDS))
def test_get_template_auth_type_valid(admin_app: TestClient, template_id: str):
    """Each template's auth_type is one of the defined values."""
    resp = admin_app.get(f"/v1/service-templates/{template_id}")
    assert resp.status_code == 200
    assert resp.json()["auth_type"] in AUTH_TYPES, (
        f"template_id={template_id}: auth_type {resp.json()['auth_type']!r} not in AUTH_TYPES"
    )


@pytest.mark.parametrize("template_id", sorted(TEMPLATE_IDS))
def test_get_template_base_url_https(admin_app: TestClient, template_id: str):
    """Each template's base_url is non-empty and starts with https://."""
    resp = admin_app.get(f"/v1/service-templates/{template_id}")
    assert resp.status_code == 200
    base_url = resp.json()["base_url"]
    assert base_url, f"template_id={template_id}: base_url is empty"
    assert base_url.startswith("https://"), (
        f"template_id={template_id}: base_url {base_url!r} does not start with https://"
    )


def test_get_template_unknown_returns_404(admin_app: TestClient):
    """GET /v1/service-templates/unknown returns 404 with mintkey:code=template_not_found."""
    resp = admin_app.get("/v1/service-templates/unknown")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("mintkey:code") == "template_not_found"


@pytest.mark.parametrize("template_id", sorted(TEMPLATE_IDS))
def test_get_template_has_test_path(admin_app: TestClient, template_id: str):
    """Each template has a non-empty test_path field.

    The test_path is used by the Admin UI to test connectivity to the upstream.
    """
    resp = admin_app.get(f"/v1/service-templates/{template_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "test_path" in body, f"template_id={template_id}: missing 'test_path' field"
    assert body["test_path"], f"template_id={template_id}: 'test_path' is empty"
    assert body["test_path"] == EXPECTED_TEST_PATHS[template_id], (
        f"template_id={template_id}: expected test_path {EXPECTED_TEST_PATHS[template_id]!r}, "
        f"got {body['test_path']!r}"
    )


def test_list_templates_filter_by_category(admin_app: TestClient):
    """GET /v1/service-templates?category=ci_cd returns only CI/CD templates."""
    resp = admin_app.get("/v1/service-templates?category=ci_cd")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    ids = {t["template_id"] for t in templates}
    assert ids == {"gitlab", "azure-devops"}


def test_list_templates_filter_by_search(admin_app: TestClient):
    """GET /v1/service-templates?search=stripe returns the Stripe template."""
    resp = admin_app.get("/v1/service-templates?search=stripe")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    assert len(templates) == 1
    assert templates[0]["template_id"] == "stripe"


def test_list_templates_search_case_insensitive(admin_app: TestClient):
    """Search is case-insensitive (Req 2.4)."""
    resp = admin_app.get("/v1/service-templates?search=GITLAB")
    assert resp.status_code == 200
    templates = resp.json()["templates"]
    assert len(templates) == 1
    assert templates[0]["template_id"] == "gitlab"


def test_list_templates_version_field_present(admin_app: TestClient):
    """Every template includes a version field (Req 18.3)."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    for tmpl in resp.json()["templates"]:
        assert "version" in tmpl, f"Missing 'version' in template {tmpl.get('template_id')}"
        assert tmpl["version"], f"Empty 'version' in template {tmpl.get('template_id')}"


# ---------------------------------------------------------------------------
# Req 23.5 — from-template credential_hint pre-population
#
# Criterion (verbatim): "WHEN an operator instantiates the Azure Dashboard API
# template, THE Admin_API SHALL pre-populate the credential structure with the
# correct token_url, field names, and token_response_path so the operator only
# needs to supply the actual username and password values."
#
# Implementation: the 201 response from POST /v1/tenants/{tid}/services/from-template
# MUST include a `credential_hint` object when the template carries one, so the
# UI can render the expected credential structure to the operator.  No secret is
# persisted — the hint is informational only.
# ---------------------------------------------------------------------------

_CSRF_TOKEN_23_5 = "test-csrf-23-5-abc"


def _seed_tenant_23_5(postgres_container) -> str:
    """Insert a tenant for Req-23.5 tests; return its UUID string."""
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
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", ("00000000-0000-0000-0000-000000000000",))
            cur.execute("SELECT set_config('app.platform_admin_view', 'on', false)")
            cur.execute(
                "INSERT INTO tenants (slug, display_name, isolation_mode, status)"
                " VALUES (%s, %s, 'row', 'active') ON CONFLICT (slug) DO NOTHING RETURNING id",
                ("req-23-5-tenant", "Req 23.5 Test Tenant"),
            )
            row = cur.fetchone()
            if row is None:
                cur.execute("SELECT id FROM tenants WHERE slug = %s", ("req-23-5-tenant",))
                row = cur.fetchone()
        conn.commit()
    finally:
        conn.close()
    assert row is not None
    return str(row[0])


def _seed_session_23_5(postgres_container, tenant_id: str) -> str:
    """Insert an operator + session for the given tenant; return session_id."""
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
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (tenant_id,))
            cur.execute("SELECT set_config('app.platform_admin_view', 'on', false)")
            cur.execute(
                "INSERT INTO operators"
                " (id, tenant_id, email, display_name, internal_password_hash,"
                " is_platform_admin, status, created_at)"
                " VALUES (%s, %s, %s, %s, NULL, %s, 'active', now())"
                " ON CONFLICT (id) DO NOTHING",
                (
                    operator_id,
                    tenant_id,
                    f"req-23-5-{operator_id[:8]}@mintkey.internal",
                    f"req-23-5-{operator_id[:8]}",
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


@pytest.fixture(scope="module")
def tenant_23_5(admin_app: TestClient, postgres_container) -> str:
    """Tenant UUID for Req-23.5 tests."""
    return _seed_tenant_23_5(postgres_container)


@pytest.fixture(scope="module")
def session_23_5(admin_app: TestClient, postgres_container, tenant_23_5: str) -> str:
    """Session ID for Req-23.5 tests."""
    return _seed_session_23_5(postgres_container, tenant_23_5)


def test_from_template_oauth2_includes_credential_hint(
    admin_app: TestClient,
    tenant_23_5: str,
    session_23_5: str,
) -> None:
    """
    Req 23.5: POST /from-template for spotus-dashboard-api returns credential_hint
    with token_url, credential_fields (userName + password keys), and
    token_response_path so the operator knows the credential structure they must supply.

    No secret is persisted; the hint fields are informational only.
    """
    resp = admin_app.post(
        f"/v1/tenants/{tenant_23_5}/services/from-template",
        json={"template_id": "spotus-dashboard-api"},
        headers={"x-mintkey-csrf": _CSRF_TOKEN_23_5},
        cookies={"csrf_token": _CSRF_TOKEN_23_5, "mintkey_session": session_23_5},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()

    # The response must carry credential_hint — Req 23.5
    assert "credential_hint" in body, (
        "Req 23.5: from-template response must include 'credential_hint' "
        "for oauth2_password_grant templates"
    )
    hint = body["credential_hint"]
    assert hint is not None, "credential_hint must not be null"

    # token_url must be present and match the staging template
    assert "token_url" in hint, "credential_hint must include 'token_url'"
    assert hint["token_url"] == "https://dashboard-api-ps-stag.azurewebsites.net/api/v1/Token"

    # credential_fields must expose the expected field names (userName + password)
    assert "credential_fields" in hint, "credential_hint must include 'credential_fields'"
    fields = hint["credential_fields"]
    assert isinstance(fields, dict), "credential_fields must be a dict"
    assert "userName" in fields, "credential_fields must have 'userName' key"
    assert "password" in fields, "credential_fields must have 'password' key"

    # token_response_path must be present
    assert "token_response_path" in hint, "credential_hint must include 'token_response_path'"
    assert hint["token_response_path"] == "$.data.token"

    # Cross-check: the service itself is created correctly (audit/RLS still intact)
    assert body["auth_scheme"] == "oauth2_password_grant"
    assert body["template_id"] == "spotus-dashboard-api"


def test_from_template_no_credential_hint_for_bearer_token_templates(
    admin_app: TestClient,
    tenant_23_5: str,
    session_23_5: str,
) -> None:
    """
    For templates without an oauth2_password_grant credential_hint (e.g. stripe),
    the from-template response either omits credential_hint or returns null/None.
    Ensures Req 23.5 is scoped correctly and does not regress plain bearer templates.
    """
    resp = admin_app.post(
        f"/v1/tenants/{tenant_23_5}/services/from-template",
        json={"template_id": "stripe", "overrides": {"name": "stripe-no-hint-test"}},
        headers={"x-mintkey-csrf": _CSRF_TOKEN_23_5},
        cookies={"csrf_token": _CSRF_TOKEN_23_5, "mintkey_session": session_23_5},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    # For bearer_token templates, credential_hint is a simple dict or absent —
    # it must NOT be an oauth2_password_grant hint (no token_url)
    hint = body.get("credential_hint")
    if hint is not None and isinstance(hint, dict):
        assert "token_url" not in hint or hint.get("token_url") is None, (
            "stripe (bearer_token) must not carry an oauth2 token_url in credential_hint"
        )


def test_from_template_cross_tenant_still_403(
    admin_app: TestClient,
    tenant_23_5: str,
    session_23_5: str,
) -> None:
    """
    CO-6 (tightened): Cross-tenant request with a REAL tenant-A session against
    tenant-B path must return 403 permission_denied — NOT 401.

    Tenant-A is tenant_23_5 (session_23_5 belongs to it).
    Tenant-B is a random UUID that exists in no tenant row — so the auth guard
    sees a valid session for tenant-A trying to touch tenant-B and must reject
    it with 403, not fall back to 401 (which only means unauthenticated).

    Previous version sent NO session and accepted 401, so it did NOT test
    tenant scoping at all.
    """
    # Use a random UUID as tenant-B — it exists in no tenant row
    tenant_b = str(_uuid_mod.uuid4())

    resp = admin_app.post(
        f"/v1/tenants/{tenant_b}/services/from-template",
        json={"template_id": "spotus-dashboard-api"},
        headers={"x-mintkey-csrf": _CSRF_TOKEN_23_5},
        cookies={
            "csrf_token": _CSRF_TOKEN_23_5,
            "mintkey_session": session_23_5,  # tenant-A session
        },
    )
    # Authenticated (tenant-A) but requesting tenant-B path → 403
    assert resp.status_code == 403, (
        f"Cross-tenant from-template with tenant-A session must return 403, "
        f"got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    # FastAPI wraps HTTPException detail under a "detail" key — extract from either location.
    code = body.get("mintkey:code") or (
        body.get("detail", {}).get("mintkey:code") if isinstance(body.get("detail"), dict) else None
    )
    assert code == "permission_denied", (
        f"Expected mintkey:code=permission_denied, got: {body}"
    )
