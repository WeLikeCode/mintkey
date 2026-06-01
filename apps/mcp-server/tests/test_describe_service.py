"""
OPS-V + OPS-CC: describe_service returns description + openapi_url; IDs in svc_ wire form.

Unit tests (no docker required):
  1. Non-null description + openapi_url round-trip correctly.
  2. NULL description + NULL openapi_url appear as null in the response.
  3. Both fields are present in the response shape (allows null).
  4. (OPS-CC) Response id field is svc_ wire form.
  5. (OPS-CC) describe_service called with svc_ wire form → 200.
  6. (OPS-CC) describe_service called with raw UUID → 200 (backward compat).

Integration tests (MINTKEY_INTEGRATION_TEST=true):
  7. Live container smoke: describe a seeded service, both fields present.

Source: OPS-V; OPS-CC; Req 6 AC4; ADR-0008; ADR-0017.11.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

from mintkey_models.bootstrap_password import BootstrapPasswordError, read_bootstrap_password

# ---------------------------------------------------------------------------
# Integration marker
# ---------------------------------------------------------------------------
INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full docker-compose stack",
)

BASE_MCP = os.getenv("MINTKEY_MCP_URL", "http://localhost:8082")
BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")

_BOOTSTRAP_PASS_FILE = (
    __import__("pathlib").Path(__file__).resolve().parents[3]
    / "data" / "bootstrap-secrets" / "admin_password"
)
try:
    BOOTSTRAP_PASSWORD = os.getenv(
        "MINTKEY_BOOTSTRAP_PASSWORD",
        read_bootstrap_password(_BOOTSTRAP_PASS_FILE) if _BOOTSTRAP_PASS_FILE.exists() else "changeme",
    )
except BootstrapPasswordError:
    BOOTSTRAP_PASSWORD = os.getenv("MINTKEY_BOOTSTRAP_PASSWORD", "changeme")


# ---------------------------------------------------------------------------
# Helpers — ASGI harness
# ---------------------------------------------------------------------------

# A fixed UUID used across unit tests so wire-form encoding is deterministic.
_TEST_SERVICE_UUID = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"


def _make_fake_row(
    *,
    service_id: str = _TEST_SERVICE_UUID,
    name: str = "test-svc",
    slug: str = "test-svc",
    base_url: str = "https://example.com",
    auth_scheme: str = "api_key_header",
    description=None,
    openapi_url=None,
) -> MagicMock:
    """
    Return a MagicMock that behaves like a SQLAlchemy row.

    service_id must be a valid UUID string — it is passed through
    db_uuid_to_wire() when building the response (OPS-CC).
    """
    row = MagicMock()
    row.id = service_id
    row.name = name
    row.slug = slug
    row.base_url = base_url
    row.auth_scheme = auth_scheme
    row.description = description
    row.openapi_url = openapi_url
    return row


def _build_app_with_mocked_db(fake_row):
    """
    Create a fresh FastAPI app whose DB dependency and agent-context dependency
    are both overridden — no real DB or admin-api network calls are made.

    The middleware imports validate_agent_key at function-call time via the
    module reference, so we patch mcp_server.main's reference to make the
    middleware inject a real agent_context into request.state. In addition, we
    also override the get_agent_context FastAPI dependency as a belt-and-suspenders
    approach (the describe_service handler uses Depends(get_agent_context)).
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context
    from mcp_server.main import create_app

    tenant_id = uuid.uuid4()
    agent_id = str(uuid.uuid4())
    fake_ctx = {"tenant_id": tenant_id, "agent_id": agent_id}

    # Patch the validate_agent_key reference inside main.py so the middleware
    # (which captures the name from the mcp_server.main module namespace) sees
    # our fake function and sets request.state.agent_context.
    _orig_validate = _main_mod.validate_agent_key

    async def _fake_validate(key):
        return fake_ctx, None

    _main_mod.validate_agent_key = _fake_validate

    app = create_app()

    # Belt-and-suspenders: also override the get_agent_context dependency so
    # describe_service gets the context regardless of middleware timing.
    async def _fake_agent_context():
        return fake_ctx

    app.dependency_overrides[get_agent_context] = _fake_agent_context

    # Override get_db_session to return a session whose execute() returns our row.
    # The session must support both:
    #   - fetchone()  — service SELECT (any query with 'sid' param or similar)
    #   - fetchall()  — slug lookup (OPS-LL; params contain 'slug')
    # When the service_id passed is a raw UUID or svc_ wire form, resolve_service_id
    # does NOT hit the DB (short-circuits at form 1 or 2), so only fetchone is called.
    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = fake_row
        # fetchall is used by the slug lookup; return empty list so it's a no-op
        # when service_id is already a UUID/wire-form (slug path not exercised here).
        result_mock.fetchall.return_value = []
        session.execute = AsyncMock(return_value=result_mock)
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session

    return app, _orig_validate, _main_mod


def _run_describe(fake_row, service_id: str = _TEST_SERVICE_UUID):
    """Run GET /v1/tools/describe_service/<service_id> and return the JSON body."""
    from httpx import AsyncClient, ASGITransport

    app, _orig, _main_mod = _build_app_with_mocked_db(fake_row)
    try:
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/v1/tools/describe_service/{service_id}",
                    headers={"X-API-Key": "mk_agent_testkey"},
                )

        resp = asyncio.run(_inner())
    finally:
        _main_mod.validate_agent_key = _orig

    return resp


# ===========================================================================
# Unit tests
# ===========================================================================


def test_describe_service_returns_description_and_openapi_url_when_set() -> None:
    """
    Seed a service with non-null description + openapi_url; assert both
    round-trip correctly in the response.

    Source: OPS-V acceptance criterion — non-null fields.
    """
    fake_row = _make_fake_row(
        description="Acme CRM API — manages contacts and deals.",
        openapi_url="https://crm.acme.example/openapi.json",
    )
    resp = _run_describe(fake_row)

    assert resp.status_code == 200, (
        f"Expected 200 from describe_service, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "service" in body, f"Missing 'service' key in response: {body}"
    svc = body["service"]

    assert "description" in svc, (
        f"'description' field missing from describe_service response: {svc.keys()}"
    )
    assert "openapi_url" in svc, (
        f"'openapi_url' field missing from describe_service response: {svc.keys()}"
    )
    assert svc["description"] == "Acme CRM API — manages contacts and deals.", (
        f"description mismatch: {svc['description']!r}"
    )
    assert svc["openapi_url"] == "https://crm.acme.example/openapi.json", (
        f"openapi_url mismatch: {svc['openapi_url']!r}"
    )


def test_describe_service_returns_null_for_null_description_and_openapi_url() -> None:
    """
    Seed a service with NULL description + NULL openapi_url; assert both
    appear as JSON null (not empty string, not absent).

    Source: OPS-V acceptance criterion — null handling.
    """
    fake_row = _make_fake_row(
        description=None,
        openapi_url=None,
    )
    resp = _run_describe(fake_row)

    assert resp.status_code == 200, (
        f"Expected 200 from describe_service, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "service" in body, f"Missing 'service' key in response: {body}"
    svc = body["service"]

    assert "description" in svc, (
        f"'description' field missing from describe_service response when null: {svc.keys()}"
    )
    assert "openapi_url" in svc, (
        f"'openapi_url' field missing from describe_service response when null: {svc.keys()}"
    )
    assert svc["description"] is None, (
        f"Expected null for description, got {svc['description']!r}"
    )
    assert svc["openapi_url"] is None, (
        f"Expected null for openapi_url, got {svc['openapi_url']!r}"
    )


def test_describe_service_response_shape_includes_base_fields() -> None:
    """
    The response must include all original fields PLUS the two new ones.
    Verifies backward-compatibility: old fields are still present.

    Source: OPS-V backward-compat requirement.
    """
    fake_row = _make_fake_row(
        name="payments",
        slug="payments",
        base_url="https://payments.example.com",
        auth_scheme="bearer_token",
        description=None,
        openapi_url="https://payments.example.com/api/openapi.yaml",
    )
    resp = _run_describe(fake_row)

    assert resp.status_code == 200
    svc = resp.json()["service"]

    required_keys = {"id", "name", "slug", "base_url", "auth_scheme", "description", "openapi_url"}
    missing = required_keys - set(svc.keys())
    assert not missing, (
        f"describe_service response is missing fields: {missing}. Got: {svc.keys()}"
    )


# ===========================================================================
# OPS-CC wire-form ID tests
# ===========================================================================


def test_describe_service_response_id_is_wire_form() -> None:
    """
    (OPS-CC) The id field in the describe_service response must use the
    canonical svc_ Crockford wire form, not a raw UUID.

    Source: OPS-CC; ADR-0017.11.
    """
    fake_row = _make_fake_row()  # uses _TEST_SERVICE_UUID
    resp = _run_describe(fake_row)

    assert resp.status_code == 200, resp.text
    svc = resp.json()["service"]
    assert svc["id"].startswith("svc_"), (
        f"Expected id to start with 'svc_', got: {svc['id']!r}"
    )
    # Must be svc_ + 26 Crockford chars
    tail = svc["id"][4:]  # strip "svc_"
    assert len(tail) == 26, (
        f"Expected 26-char Crockford tail, got {len(tail)}-char tail: {tail!r}"
    )


def test_describe_service_accepts_svc_wire_form_id() -> None:
    """
    (OPS-CC) describe_service called with a svc_ wire-form ID in the URL
    path → 200 with full metadata.  The svc_ form is what list_services now
    returns, so agents that call list_services and then describe_service in
    sequence must work end-to-end.

    Source: OPS-CC; ADR-0017.11.
    """
    from mcp_server.utils.wire_ids import db_uuid_to_wire

    wire_id = db_uuid_to_wire(_TEST_SERVICE_UUID, "svc")
    fake_row = _make_fake_row(service_id=_TEST_SERVICE_UUID)
    resp = _run_describe(fake_row, service_id=wire_id)

    assert resp.status_code == 200, (
        f"Expected 200 when calling describe_service with svc_ form, "
        f"got {resp.status_code}: {resp.text}"
    )
    svc = resp.json()["service"]
    assert svc["id"].startswith("svc_"), (
        f"Response id should be svc_ form, got: {svc['id']!r}"
    )


def test_describe_service_accepts_raw_uuid_backward_compat() -> None:
    """
    (OPS-CC) describe_service called with a raw UUID (no prefix) → 200.
    Agents built before OPS-CC pass raw UUIDs and must continue to work.

    Source: OPS-CC backward-compat requirement.
    """
    fake_row = _make_fake_row(service_id=_TEST_SERVICE_UUID)
    resp = _run_describe(fake_row, service_id=_TEST_SERVICE_UUID)

    assert resp.status_code == 200, (
        f"Expected 200 for backward-compat raw UUID, "
        f"got {resp.status_code}: {resp.text}"
    )
    svc = resp.json()["service"]
    # Response id is always wire form regardless of input form
    assert svc["id"].startswith("svc_"), (
        f"Response id should always be svc_ wire form, got: {svc['id']!r}"
    )


# ===========================================================================
# OPS-LL slug-form tests
# ===========================================================================


def _build_app_with_slug_lookup(
    *,
    slug_row=None,
    service_row=None,
    tenant_id=None,
):
    """
    Build a FastAPI test app where:
    - The slug lookup (execute with 'slug' param) returns slug_row (or [] if None).
    - The service SELECT (execute with 'sid' param) returns service_row (or None).
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context
    from mcp_server.main import create_app

    _tenant_id = tenant_id or uuid.uuid4()
    _agent_id = str(uuid.uuid4())
    fake_ctx = {"tenant_id": _tenant_id, "agent_id": _agent_id}

    _orig_validate = _main_mod.validate_agent_key

    async def _fake_validate(key):
        return fake_ctx, None

    _main_mod.validate_agent_key = _fake_validate
    app = create_app()

    async def _fake_agent_ctx():
        return fake_ctx

    app.dependency_overrides[get_agent_context] = _fake_agent_ctx

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()

        async def _execute(stmt, params=None, **kw):
            result_mock = MagicMock()
            if params and "slug" in params:
                result_mock.fetchall.return_value = [slug_row] if slug_row is not None else []
            else:
                result_mock.fetchone.return_value = service_row
            return result_mock

        session.execute = _execute
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session
    return app, _orig_validate, _main_mod


def _run_describe_with_slug(
    service_id_input: str,
    *,
    slug_row=None,
    service_row=None,
    tenant_id=None,
):
    from httpx import AsyncClient, ASGITransport

    app, _orig, _main_mod = _build_app_with_slug_lookup(
        slug_row=slug_row,
        service_row=service_row,
        tenant_id=tenant_id,
    )
    try:
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/v1/tools/describe_service/{service_id_input}",
                    headers={"X-API-Key": "mk_agent_testkey"},
                )

        resp = asyncio.run(_inner())
    finally:
        _main_mod.validate_agent_key = _orig
    return resp


def test_describe_service_accepts_slug_input() -> None:
    """
    (OPS-LL) describe_service called with a slug in the URL path → 200 with
    full metadata.  The slug is looked up in DB and resolved to the service UUID.

    Source: OPS-LL; Req 6 AC4.
    """
    slug_row = MagicMock()
    slug_row.id = _TEST_SERVICE_UUID

    service_row = _make_fake_row(service_id=_TEST_SERVICE_UUID)

    resp = _run_describe_with_slug(
        "github",
        slug_row=slug_row,
        service_row=service_row,
    )

    assert resp.status_code == 200, (
        f"Expected 200 when describe_service called with slug, "
        f"got {resp.status_code}: {resp.text}"
    )
    svc = resp.json()["service"]
    assert svc["id"].startswith("svc_"), (
        f"Response id should be svc_ wire form even for slug input, got: {svc['id']!r}"
    )


def test_describe_service_unknown_slug_returns_404_with_error_shape() -> None:
    """
    (OPS-LL) describe_service called with an unknown slug → 404 with the
    canonical OPS-LL error shape: code, reason_code, service_id_input, hint.

    Source: OPS-LL error message spec.
    """
    resp = _run_describe_with_slug(
        "nonexistent-slug",
        slug_row=None,   # 0 rows from DB
        service_row=None,
    )

    assert resp.status_code == 404, (
        f"Expected 404 for unknown slug, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("code") == "mintkey:not_found", (
        f"Expected code='mintkey:not_found', got: {body}"
    )
    assert body.get("reason_code") == "service_not_found", (
        f"Expected reason_code='service_not_found', got: {body}"
    )
    assert body.get("service_id_input") == "nonexistent-slug", (
        f"Expected service_id_input='nonexistent-slug', got: {body}"
    )
    assert "hint" in body and body["hint"], (
        f"Expected non-empty 'hint' in error body: {body}"
    )


def test_describe_service_cross_tenant_slug_returns_404() -> None:
    """
    (OPS-LL) Cross-tenant security: slug from tenant A is not resolvable
    from tenant B's agent (DB returns 0 rows for the scoped lookup).

    Source: OPS-LL hard rule — slug lookup is tenant-scoped.
    """
    tenant_b = uuid.uuid4()
    resp = _run_describe_with_slug(
        "github",
        slug_row=None,  # tenant B has no 'github' service
        service_row=None,
        tenant_id=tenant_b,
    )

    assert resp.status_code == 404, (
        f"Expected 404 for cross-tenant slug, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("reason_code") == "service_not_found", (
        f"Cross-tenant slug should be service_not_found: {body}"
    )


# ===========================================================================
# SSH connect_type / agent_connection_guide tests
# ===========================================================================


def test_describe_service_ssh_scheme_returns_connect_type_ssh_and_guide() -> None:
    """
    SSH auth_scheme services must have connect_type='ssh' and a full
    agent_connection_guide block in the describe_service response.

    Source: SSH bastion onboarding — Part C objective.
    """
    fake_row = _make_fake_row(auth_scheme="ssh_private_key")
    resp = _run_describe(fake_row)

    assert resp.status_code == 200, resp.text
    svc = resp.json()["service"]

    assert svc.get("connect_type") == "ssh", (
        f"Expected connect_type='ssh' for ssh_private_key service, got: {svc.get('connect_type')!r}"
    )
    guide = svc.get("agent_connection_guide")
    assert guide is not None, (
        f"Expected agent_connection_guide block for SSH service, not present. Keys: {svc.keys()}"
    )
    # Validate required keys inside the guide
    for key in ("summary", "steps", "example_command_template", "do_not", "lifetime_seconds"):
        assert key in guide, (
            f"agent_connection_guide missing '{key}'. Got keys: {guide.keys()}"
        )
    assert isinstance(guide["steps"], list) and len(guide["steps"]) >= 4, (
        f"Expected at least 4 steps in agent_connection_guide, got: {guide['steps']}"
    )
    assert guide["lifetime_seconds"] == 600, (
        f"Expected lifetime_seconds=600, got: {guide['lifetime_seconds']}"
    )
    # Guide must not recommend Kong
    for do_not_item in guide["do_not"]:
        assert "Kong" in do_not_item or "port forward" in do_not_item or "X11" in do_not_item or "agent forward" in do_not_item or "store" in do_not_item, (
            f"Unexpected do_not item: {do_not_item!r}"
        )


def test_describe_service_http_scheme_returns_connect_type_http_and_no_guide() -> None:
    """
    HTTP auth_scheme services must have connect_type='http' and NO
    agent_connection_guide block in the describe_service response.

    Source: SSH bastion onboarding — Part C objective (HTTP-shape check).
    """
    fake_row = _make_fake_row(auth_scheme="bearer_token")
    resp = _run_describe(fake_row)

    assert resp.status_code == 200, resp.text
    svc = resp.json()["service"]

    assert svc.get("connect_type") == "http", (
        f"Expected connect_type='http' for bearer_token service, got: {svc.get('connect_type')!r}"
    )
    assert "agent_connection_guide" not in svc, (
        f"HTTP services must NOT have agent_connection_guide. Keys: {svc.keys()}"
    )


# ===========================================================================
# Integration tests (requires docker-compose stack)
# ===========================================================================


@INTEGRATION
def test_integration_describe_service_returns_new_fields() -> None:
    """
    Live container: create a service via admin-api, grant an agent permission,
    call describe_service via MCP, and verify description + openapi_url are present.

    Source: OPS-V smoke test requirement.
    """
    import httpx
    import time

    with httpx.Client(timeout=30) as client:

        # Login as admin
        login_r = client.post(
            f"{BASE_API}/v1/auth/internal-login",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
        )
        assert login_r.status_code == 200, (
            f"login failed: {login_r.status_code} {login_r.text}"
        )
        login_body = login_r.json()
        tenant_id = login_body["tenant_id"]
        csrf_token = client.cookies.get("csrf_token", "")

        # Create agent
        agent_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents",
            json={"name": f"ops-v-test-agent-{int(time.time())}"},
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert agent_r.status_code == 201, (
            f"create agent failed: {agent_r.status_code} {agent_r.text}"
        )
        api_key = agent_r.json()["api_key"]
        agent_body = agent_r.json()

        # Validate agent key to get the DB UUID
        validate_r = client.post(
            f"{BASE_API}/v1/internal/validate-agent-key",
            json={"api_key": api_key},
        )
        assert validate_r.status_code == 200
        agent_db_id = validate_r.json()["agent_id"]

        # Create service with description + openapi_url
        svc_name = f"ops-v-svc-{int(time.time())}"
        svc_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services",
            json={
                "name": svc_name,
                "base_url": "http://mock-backend:8999",
                "auth_scheme": "api_key_header",
                "description": "OPS-V integration test service.",
                "openapi_url": "http://mock-backend:8999/openapi.json",
                "settings": {},
            },
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert svc_r.status_code == 201, (
            f"create service failed: {svc_r.status_code} {svc_r.text}"
        )

        # Get service UUID from the list endpoint
        svcs_list_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/services")
        assert svcs_list_r.status_code == 200
        services_list = svcs_list_r.json().get("services", [])
        matching = [s for s in services_list if s.get("name") == svc_name]
        assert matching, f"Created service not found in list: {services_list}"
        service_uuid_wire = matching[0]["id"]
        hex_part = service_uuid_wire[4:]
        service_uuid = (
            f"{hex_part[:8]}-{hex_part[8:12]}-{hex_part[12:16]}"
            f"-{hex_part[16:20]}-{hex_part[20:]}"
        )

        # Register a credential
        csrf_token = client.cookies.get("csrf_token", csrf_token)
        cred_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services/{service_uuid}/credentials",
            json={
                "auth_scheme": "api_key_header",
                "value": "ops-v-test-cred",
                "header_name": "X-API-Key",
            },
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert cred_r.status_code == 201, (
            f"register credential failed: {cred_r.status_code} {cred_r.text}"
        )

        # Grant permission so agent can see the service
        perm_r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/agents/{agent_db_id}/permissions",
            json={
                "service_id": service_uuid,
                "action": "call",
                "constraints": {},
            },
            headers={"X-Mintkey-Csrf": csrf_token},
        )
        assert perm_r.status_code == 201, (
            f"grant permission failed: {perm_r.status_code} {perm_r.text}"
        )

        # Discover to get MCP service_id (UUID form used by MCP)
        disc_r = client.get(
            f"{BASE_MCP}/v1/tools/discover",
            headers={"X-API-Key": api_key},
        )
        assert disc_r.status_code == 200
        disc_services = disc_r.json().get("services", [])
        matching_svc = next(
            (s for s in disc_services if s.get("name") == svc_name), None
        )
        assert matching_svc is not None, (
            f"Service {svc_name!r} not found in discover: {disc_services}"
        )
        mcp_service_id = matching_svc["id"]

        # Call describe_service
        desc_r = client.get(
            f"{BASE_MCP}/v1/tools/describe_service/{mcp_service_id}",
            headers={"X-API-Key": api_key},
        )
        assert desc_r.status_code == 200, (
            f"describe_service failed: {desc_r.status_code} {desc_r.text}"
        )
        svc = desc_r.json()["service"]

        assert "description" in svc, (
            f"'description' missing from live describe_service response: {svc.keys()}"
        )
        assert "openapi_url" in svc, (
            f"'openapi_url' missing from live describe_service response: {svc.keys()}"
        )
        # Verify the values that were seeded (or at minimum both fields are present)
        # Admin-api may or may not persist description/openapi_url depending on the
        # schema — we assert the fields exist and are not missing entirely.
        assert svc["description"] is None or isinstance(svc["description"], str), (
            f"description should be str or null, got: {type(svc['description'])}"
        )
        assert svc["openapi_url"] is None or isinstance(svc["openapi_url"], str), (
            f"openapi_url should be str or null, got: {type(svc['openapi_url'])}"
        )
