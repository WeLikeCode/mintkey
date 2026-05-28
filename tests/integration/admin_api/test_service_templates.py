"""
Integration tests for GET /v1/service-templates.

Covers:
  GET /v1/service-templates              — returns all 13 templates sorted by name
  GET /v1/service-templates/{template_id} — returns full template for each entry
  GET /v1/service-templates/unknown      — returns 404 with mintkey:code=template_not_found
  auth_type invariant                    — each template's auth_type is valid
  base_url invariant                     — each template's base_url starts with https://
  test_path invariant                    — each template has a non-empty test_path
  category filter                        — ?category= returns correct subset
  search filter                          — ?search= is case-insensitive across name/display_name/description

Source: Requirements 1.1-1.4, 2.1-2.4, 3.1-3.2, 18.3.
"""
from __future__ import annotations

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

# The 13 bundled template IDs from service_templates.yaml.
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
    "azure-dashboard-api",
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
    "azure-dashboard-api": "/health",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_templates_returns_thirteen_entries(admin_app: TestClient):
    """GET /v1/service-templates returns exactly 13 templates."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    body = resp.json()
    assert "templates" in body
    assert len(body["templates"]) == 13


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
