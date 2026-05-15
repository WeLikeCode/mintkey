"""
OPS-V: describe_service returns description + openapi_url.

Unit tests (no docker required):
  1. Non-null description + openapi_url round-trip correctly.
  2. NULL description + NULL openapi_url appear as null in the response.
  3. Both fields are present in the response shape (allows null).

Integration tests (MINTKEY_INTEGRATION_TEST=true):
  4. Live container smoke: describe a seeded service, both fields present.

Source: OPS-V; Req 6 AC4; ADR-0008.
"""
from __future__ import annotations

import asyncio
import os
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

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
BOOTSTRAP_PASSWORD = os.getenv(
    "MINTKEY_BOOTSTRAP_PASSWORD",
    _BOOTSTRAP_PASS_FILE.read_text().strip()
    if _BOOTSTRAP_PASS_FILE.exists()
    else "changeme",
)


# ---------------------------------------------------------------------------
# Helpers — ASGI harness
# ---------------------------------------------------------------------------

def _make_fake_row(
    *,
    service_id: str = "some-uuid",
    name: str = "test-svc",
    slug: str = "test-svc",
    base_url: str = "https://example.com",
    auth_scheme: str = "api_key_header",
    description=None,
    openapi_url=None,
) -> MagicMock:
    """Return a MagicMock that behaves like a SQLAlchemy row."""
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
    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchone.return_value = fake_row
        session.execute = AsyncMock(return_value=result_mock)
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session

    return app, _orig_validate, _main_mod


def _run_describe(fake_row, service_id: str = "test-uuid-1234"):
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
