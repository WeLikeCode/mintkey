"""
Integration tests for GET /v1/service-templates (OPS-R).

Covers:
  GET /v1/service-templates          — returns 5 entries sorted by name
  GET /v1/service-templates/{slug}   — returns full template for each starter
  GET /v1/service-templates/unknown  — returns 404 with mintkey:code=not_found
  auth_scheme invariant              — each template's auth_scheme is valid
  base_url invariant                 — each template's base_url starts with https://
  test_path invariant                — each starter template has a non-empty test_path (OPS-JJ)
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

# Valid auth_scheme values per openapi.yaml AuthScheme enum.
AUTH_SCHEMES = {
    "api_key_header",
    "api_key_query",
    "bearer_token",
    "basic_auth",
    "oauth2_client_credentials",
    "oidc_client_secret",
}

# The 5 bundled starter slugs.
STARTER_SLUGS = {"github", "stripe", "openai", "slack", "twilio"}

# Required top-level fields on a full template document.
TEMPLATE_REQUIRED_FIELDS = {
    "slug",
    "name",
    "display_name",
    "description",
    "base_url",
    "auth_scheme",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_templates_returns_five_entries(admin_app: TestClient):
    """GET /v1/service-templates returns exactly 5 templates."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    body = resp.json()
    assert "templates" in body
    assert len(body["templates"]) == 5


def test_list_templates_sorted_by_name(admin_app: TestClient):
    """Templates are sorted ascending by name."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    names = [t["name"] for t in resp.json()["templates"]]
    assert names == sorted(names)


def test_list_templates_summary_fields(admin_app: TestClient):
    """Every summary entry contains the required summary fields."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    for tmpl in resp.json()["templates"]:
        for field in ("slug", "name", "display_name", "description"):
            assert field in tmpl, f"Missing field {field!r} in summary"


@pytest.mark.parametrize("slug", sorted(STARTER_SLUGS))
def test_get_template_full_shape(admin_app: TestClient, slug: str):
    """GET /v1/service-templates/{slug} returns all required fields."""
    resp = admin_app.get(f"/v1/service-templates/{slug}")
    assert resp.status_code == 200, f"slug={slug}: expected 200, got {resp.status_code}"
    body = resp.json()
    for field in TEMPLATE_REQUIRED_FIELDS:
        assert field in body, f"slug={slug}: missing field {field!r}"
    # slug in body must match the path parameter
    assert body["slug"] == slug


@pytest.mark.parametrize("slug", sorted(STARTER_SLUGS))
def test_get_template_auth_scheme_valid(admin_app: TestClient, slug: str):
    """Each template's auth_scheme is one of the defined AuthScheme values."""
    resp = admin_app.get(f"/v1/service-templates/{slug}")
    assert resp.status_code == 200
    assert resp.json()["auth_scheme"] in AUTH_SCHEMES, (
        f"slug={slug}: auth_scheme {resp.json()['auth_scheme']!r} not in AUTH_SCHEMES"
    )


@pytest.mark.parametrize("slug", sorted(STARTER_SLUGS))
def test_get_template_base_url_https(admin_app: TestClient, slug: str):
    """Each template's base_url is non-empty and starts with https://."""
    resp = admin_app.get(f"/v1/service-templates/{slug}")
    assert resp.status_code == 200
    base_url = resp.json()["base_url"]
    assert base_url, f"slug={slug}: base_url is empty"
    assert base_url.startswith("https://"), (
        f"slug={slug}: base_url {base_url!r} does not start with https://"
    )


def test_get_template_unknown_returns_404(admin_app: TestClient):
    """GET /v1/service-templates/unknown returns 404 with mintkey:code=not_found."""
    resp = admin_app.get("/v1/service-templates/unknown")
    assert resp.status_code == 404
    body = resp.json()
    assert body.get("mintkey:code") == "not_found"


def test_list_templates_slugs_match_starters(admin_app: TestClient):
    """The 5 returned slugs exactly match the expected starter set."""
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    slugs = {t["slug"] for t in resp.json()["templates"]}
    assert slugs == STARTER_SLUGS


# Expected test_path values per starter template (OPS-JJ).
EXPECTED_TEST_PATHS: dict[str, str] = {
    "github": "/user",
    "stripe": "/v1/charges?limit=1",
    "openai": "/models",
    "slack": "/api.test",
    "twilio": "/2010-04-01/Accounts.json?PageSize=1",
}


@pytest.mark.parametrize("slug", sorted(STARTER_SLUGS))
def test_get_template_has_test_path(admin_app: TestClient, slug: str):
    """Each starter template has a non-empty test_path field (OPS-JJ).

    The test_path is used by ServiceCreateForm instead of the hardcoded /health
    so that the Test connection button hits a real endpoint for each upstream.
    """
    resp = admin_app.get(f"/v1/service-templates/{slug}")
    assert resp.status_code == 200
    body = resp.json()
    assert "test_path" in body, f"slug={slug}: missing 'test_path' field"
    assert body["test_path"], f"slug={slug}: 'test_path' is empty"
    assert body["test_path"].startswith("/"), (
        f"slug={slug}: test_path {body['test_path']!r} must start with '/'"
    )
    assert body["test_path"] == EXPECTED_TEST_PATHS[slug], (
        f"slug={slug}: expected test_path {EXPECTED_TEST_PATHS[slug]!r}, "
        f"got {body['test_path']!r}"
    )
