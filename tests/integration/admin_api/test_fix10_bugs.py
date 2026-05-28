"""
Tests for FIX-10 cleanups: BUG-13, BUG-15, BUG-18.

BUG-13: base_url SSRF validation must resolve DNS hostnames, not just check IP
        literals. A hostname that resolves to a private/loopback IP must be
        rejected with 422.

BUG-15: service_templates.yaml credential_hint entries must not contain the
        placeholder literal `"value"` for the `field` key. All 12 simple-auth
        templates must carry a real field-name hint; the YAML must still load
        with all 13 templates valid.

BUG-18: duplicate service name on POST /from-template must return 409 via a
        caught IntegrityError (atomic), not via a pre-check query that races the
        unique constraint.
"""
from __future__ import annotations

import uuid as _uuid_mod
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import psycopg2
import pytest
from starlette.testclient import TestClient

_CSRF_TOKEN = "test-fix10-csrf"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}


# ---------------------------------------------------------------------------
# Helpers: seed tenant + session
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
                (slug, f"Fix-10 tenant {slug}"),
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
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (tenant_id,))
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
                    f"fix10-{operator_id[:8]}@mintkey.internal",
                    f"fix10-{operator_id[:8]}",
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


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def fix10_tenant(admin_app: TestClient, postgres_container) -> str:
    return _seed_tenant(postgres_container, "fix10-test-tenant")


@pytest.fixture(scope="module")
def fix10_session(admin_app: TestClient, postgres_container, fix10_tenant: str) -> str:
    return _seed_session(postgres_container, fix10_tenant)


# ---------------------------------------------------------------------------
# BUG-13: DNS-resolved hostname SSRF — pure unit tests, no DB/FastAPI involved
#
# We test `_is_forbidden_destination` directly (the production function).
# We patch ONLY `admin_api.services.credential_service.socket.getaddrinfo`
# — the single narrow call site in the shared helper.  asyncpg / the test
# DB container never sees the mock.
# ---------------------------------------------------------------------------

def test_bug13_hostname_resolving_to_loopback_is_rejected() -> None:
    """BUG-13: _is_forbidden_destination must return True when the hostname
    DNS-resolves to 127.0.0.1 (loopback).

    Patching the shared helper's getaddrinfo only — no FastAPI/DB needed.
    """
    from admin_api.api.services import _is_forbidden_destination

    fake_addrs = [(2, 1, 6, "", ("127.0.0.1", 0))]

    with patch(
        "admin_api.services.credential_service.socket.getaddrinfo",
        return_value=fake_addrs,
    ):
        result = _is_forbidden_destination("https://internal.corp.example.com/api")

    assert result is True, (
        "BUG-13: hostname resolving to 127.0.0.1 must be a forbidden destination"
    )


def test_bug13_hostname_resolving_to_private_rfc1918_is_rejected() -> None:
    """BUG-13: _is_forbidden_destination must return True when the hostname
    DNS-resolves to 10.0.0.5 (RFC1918).
    """
    from admin_api.api.services import _is_forbidden_destination

    fake_addrs = [(2, 1, 6, "", ("10.0.0.5", 0))]

    with patch(
        "admin_api.services.credential_service.socket.getaddrinfo",
        return_value=fake_addrs,
    ):
        result = _is_forbidden_destination("https://internal2.corp.example.com/api")

    assert result is True, (
        "BUG-13: hostname resolving to 10.0.0.5 must be a forbidden destination"
    )


def test_bug13_hostname_resolving_to_public_ip_is_allowed() -> None:
    """BUG-13: _is_forbidden_destination must return False when the hostname
    DNS-resolves to a public IP (8.8.8.8).

    Confirms the SSRF fix is targeted — no regression for legitimate public services.
    """
    from admin_api.api.services import _is_forbidden_destination

    # 8.8.8.8 is globally routable — must not be blocked
    fake_addrs = [(2, 1, 6, "", ("8.8.8.8", 0))]

    with patch(
        "admin_api.services.credential_service.socket.getaddrinfo",
        return_value=fake_addrs,
    ):
        result = _is_forbidden_destination("https://public.example.com/api")

    assert result is False, (
        "BUG-13 regression: hostname resolving to public IP must not be blocked"
    )


def test_bug13_ip_literal_still_blocked() -> None:
    """BUG-13 regression: IP literals (192.168.x.x) must still be rejected.
    The DNS-resolution path must not break the existing literal check.
    No mock needed — IP literal is checked before DNS.
    """
    from admin_api.api.services import _is_forbidden_destination

    result = _is_forbidden_destination("http://192.168.1.50/api")

    assert result is True, "IP literal 192.168.1.50 must be a forbidden destination"


# ---------------------------------------------------------------------------
# BUG-15: No placeholder junk in credential_hint.field
# ---------------------------------------------------------------------------

# All template IDs with simple-auth credential hints that previously had field='value'
_SIMPLE_AUTH_TEMPLATE_IDS = [
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
]


def test_bug15_no_credential_hint_field_equals_value(admin_app: TestClient) -> None:
    """
    BUG-15: No template should have credential_hint.field == 'value' (literal
    placeholder junk). The YAML must carry real field-name hints.

    credential_hint is only returned by GET /v1/service-templates/{template_id},
    not by the list endpoint.
    """
    for template_id in _SIMPLE_AUTH_TEMPLATE_IDS:
        resp = admin_app.get(f"/v1/service-templates/{template_id}")
        assert resp.status_code == 200, f"template {template_id!r} returned {resp.status_code}"
        hint = resp.json().get("credential_hint")
        if hint and isinstance(hint, dict) and hint.get("field") is not None:
            assert hint["field"] != "value", (
                f"BUG-15: template {template_id!r} still has placeholder "
                f"credential_hint.field='value'"
            )


def test_bug15_all_thirteen_templates_load(admin_app: TestClient) -> None:
    """
    BUG-15: After fixing the YAML, the registry must still load all 13 templates.
    """
    resp = admin_app.get("/v1/service-templates")
    assert resp.status_code == 200
    assert len(resp.json()["templates"]) == 13, (
        f"BUG-15: expected 13 templates, got {len(resp.json()['templates'])}"
    )


def test_bug15_each_template_hint_field_is_meaningful(admin_app: TestClient) -> None:
    """
    BUG-15: Every simple-auth template's credential_hint has a non-empty,
    non-junk field name (not 'value', not empty, not None).

    credential_hint is returned by the per-template detail endpoint.
    """
    junk_values = {"value", "", None}
    for template_id in _SIMPLE_AUTH_TEMPLATE_IDS:
        resp = admin_app.get(f"/v1/service-templates/{template_id}")
        assert resp.status_code == 200
        body = resp.json()
        # oauth2_password_grant templates use credential_fields, not field
        if body.get("auth_type") == "oauth2_password_grant":
            continue
        hint = body.get("credential_hint")
        assert hint is not None, (
            f"BUG-15: template {template_id!r} missing credential_hint entirely"
        )
        field_val = hint.get("field")
        assert field_val not in junk_values, (
            f"BUG-15: template {template_id!r} has junk/missing field hint: "
            f"field={field_val!r}"
        )


# ---------------------------------------------------------------------------
# BUG-18: duplicate service name → 409 via IntegrityError (atomic)
# ---------------------------------------------------------------------------

def test_bug18_duplicate_name_returns_409(
    admin_app: TestClient,
    fix10_tenant: str,
    fix10_session: str,
) -> None:
    """
    BUG-18: Instantiating from a template with a name that already exists in
    the tenant must return 409 with mintkey:code=service_name_taken.

    This first call creates the service; the second must return 409.
    """
    # First call — must succeed (201)
    resp1 = admin_app.post(
        f"/v1/tenants/{fix10_tenant}/services/from-template",
        json={"template_id": "stripe", "overrides": {"name": "dup-name-test"}},
        headers=_CSRF_HEADERS,
        cookies={**_CSRF_COOKIES, "mintkey_session": fix10_session},
    )
    assert resp1.status_code == 201, f"First call must succeed; got {resp1.status_code}: {resp1.text}"

    # Second call — same name → 409
    resp2 = admin_app.post(
        f"/v1/tenants/{fix10_tenant}/services/from-template",
        json={"template_id": "stripe", "overrides": {"name": "dup-name-test"}},
        headers=_CSRF_HEADERS,
        cookies={**_CSRF_COOKIES, "mintkey_session": fix10_session},
    )
    assert resp2.status_code == 409, (
        f"BUG-18: duplicate name must return 409; got {resp2.status_code}: {resp2.text}"
    )
    body = resp2.json()
    assert body.get("mintkey:code") == "service_name_taken", (
        f"BUG-18: expected mintkey:code='service_name_taken'; got {body}"
    )


def test_bug18_409_comes_from_integrity_error_path(
    admin_app: TestClient,
    fix10_tenant: str,
    fix10_session: str,
) -> None:
    """
    BUG-18: Verify the 409 originates from the IntegrityError catch path (atomic),
    not a pre-check SELECT.

    Strategy: patch ``sqlalchemy.ext.asyncio.AsyncSession.execute`` on the
    from-template handler so that the INSERT raises IntegrityError even though
    the name has never been inserted before (simulating a lost race).  The
    endpoint must still return 409 with service_name_taken — proving it is the
    IntegrityError branch that fires, not a pre-check that would have returned
    False for a brand-new name.
    """
    from sqlalchemy.exc import IntegrityError as _IE
    import sqlalchemy.ext.asyncio as _aio

    unique_name = f"integrity-race-test-{_uuid_mod.uuid4().hex[:8]}"

    _original_execute = _aio.AsyncSession.execute
    _call_count = {"n": 0}

    async def _patched_execute(self, stmt, params=None, **kwargs):
        _call_count["n"] += 1
        # Let set_tenant_context and any other housekeeping calls through;
        # intercept only the INSERT (identified by the "template_id" param key).
        if isinstance(params, dict) and "template_id" in params and "id" in params:
            raise _IE(
                statement=None,
                params=None,
                orig=Exception("mock unique constraint violation"),
            )
        return await _original_execute(self, stmt, params, **kwargs)

    with patch.object(_aio.AsyncSession, "execute", _patched_execute):
        resp = admin_app.post(
            f"/v1/tenants/{fix10_tenant}/services/from-template",
            json={"template_id": "stripe", "overrides": {"name": unique_name}},
            headers=_CSRF_HEADERS,
            cookies={**_CSRF_COOKIES, "mintkey_session": fix10_session},
        )

    assert resp.status_code == 409, (
        f"BUG-18: IntegrityError on INSERT must produce 409; got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("mintkey:code") == "service_name_taken", (
        f"BUG-18: expected service_name_taken from IntegrityError path; got {body}"
    )
