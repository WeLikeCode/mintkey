"""
Unit tests: Service CRUD endpoints.

POST   /v1/tenants/{tid}/services       — register (201)
GET    /v1/tenants/{tid}/services       — list (200)
PATCH  /v1/tenants/{tid}/services/{sid} — update (200)
DELETE /v1/tenants/{tid}/services/{sid} — delete (204)

Sources:
  - Req 3 (service CRUD)
  - ADR-0008 (bound parameters — no f-string SQL)
  - ADR-0014.7 (audit emit on every state change)
  - ADR-0017.11 (ULID IDs with svc_ prefix)
  - S-SEC-1 (forbidden destination validation)
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
BASE_URL_PATH = f"/v1/tenants/{TENANT_ID}/services"

# CSRF token used in all mutating requests
CSRF_TOKEN = "test-csrf-token"


def _make_mock_session():
    """Return an async-capable mock DB session."""
    import uuid
    session = MagicMock()

    # Stub row returned by RETURNING clause and other fetchone calls
    _stub_row = MagicMock()
    _stub_row.id = str(uuid.UUID("00000000-0000-0000-0000-000000000001"))
    _stub_row.created_at = None
    _stub_row.updated_at = None

    # execute returns an awaitable that yields a mock result
    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.fetchone.return_value = _stub_row
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def create_test_app():
    """
    Create an app with:
      - services router included
      - get_db_session overridden to a mock (no real DB)
      - CSRF middleware present but services paths registered as exempt
    """
    from fastapi import FastAPI
    from admin_api.api.health import router as health_router
    from admin_api.api.services import router as services_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(health_router)
    app.include_router(services_router)

    # Override DB dependency with mock
    async def mock_db_session():
        yield _make_mock_session()

    app.dependency_overrides[get_db_session] = mock_db_session

    # Register service paths as CSRF-exempt for unit tests
    csrf_exempt(BASE_URL_PATH)
    csrf_exempt(f"{BASE_URL_PATH}/some-service-id")

    app.add_middleware(CsrfMiddleware)

    return app


@pytest.fixture()
def app():
    return create_test_app()


@pytest.fixture()
def mock_audit():
    """Patch audit_emit so unit tests don't hit the DB hash-chain logic."""
    with patch("admin_api.api.services.audit_emit", new=AsyncMock()) as m:
        yield m


# ---------------------------------------------------------------------------
# POST — create service
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_service_returns_201_with_svc_id(app, mock_audit) -> None:
    """
    POST /v1/tenants/{tid}/services with valid payload returns 201.
    Response id starts with 'svc_' — ADR-0017.11.
    Source: Req 3 AC1; ADR-0017.11.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={
                "name": "openai",
                "base_url": "https://api.openai.com",
                "auth_scheme": "bearer_token",
            },
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("svc_"), f"Expected svc_ prefix, got: {body['id']}"
    assert body["name"] == "openai"
    assert body["auth_scheme"] == "bearer_token"


@pytest.mark.asyncio
async def test_create_service_rejects_rfc1918_base_url(app, mock_audit) -> None:
    """
    POST with RFC1918 base_url → 422 mintkey:forbidden_destination.
    Source: S-SEC-1.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={
                "name": "private",
                "base_url": "http://192.168.1.1/api",
                "auth_scheme": "bearer_token",
            },
        )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "forbidden_destination"


@pytest.mark.asyncio
async def test_create_service_rejects_localhost_base_url(app, mock_audit) -> None:
    """
    POST with loopback base_url → 422 mintkey:forbidden_destination.
    Source: S-SEC-1.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={
                "name": "local",
                "base_url": "http://127.0.0.1/api",
                "auth_scheme": "bearer_token",
            },
        )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "forbidden_destination"


@pytest.mark.asyncio
async def test_create_service_rejects_metadata_ip_base_url(app, mock_audit) -> None:
    """
    POST with cloud metadata IP (169.254.169.254) → 422 mintkey:forbidden_destination.
    Source: S-SEC-1.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={
                "name": "metadata",
                "base_url": "http://169.254.169.254/latest/meta-data/",
                "auth_scheme": "bearer_token",
            },
        )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "forbidden_destination"


@pytest.mark.asyncio
async def test_create_service_rejects_10_0_0_0_network(app, mock_audit) -> None:
    """
    POST with 10.x.x.x base_url → 422 mintkey:forbidden_destination.
    Source: S-SEC-1 (RFC1918 10/8 block).
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={
                "name": "internal",
                "base_url": "http://10.0.0.1/api",
                "auth_scheme": "bearer_token",
            },
        )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body.get("mintkey:code") == "forbidden_destination"


# ---------------------------------------------------------------------------
# GET — list services
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_services_returns_200(app) -> None:
    """
    GET /v1/tenants/{tid}/services returns 200 with {"services": [...]}.
    Source: Req 3.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "services" in body
    assert isinstance(body["services"], list)


# ---------------------------------------------------------------------------
# Audit emit called on create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_audit_emit_called_on_create(app, mock_audit) -> None:
    """
    audit_emit is called with event_type="service.registered" on POST.
    Source: ADR-0014.7, Req AUD-3.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={
                "name": "stripe",
                "base_url": "https://api.stripe.com",
                "auth_scheme": "bearer_token",
            },
        )

    assert resp.status_code == 201, resp.text
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs.get("event_type") == "service.registered"


# ---------------------------------------------------------------------------
# S8-codeql: py/stack-trace-exposure — test_service unexpected exception
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_forbidden_destination_check_rejects_rfc1918() -> None:
    """
    _is_forbidden_destination returns True for private/loopback addresses.
    This is a unit check for S-SEC-1 already covered above; kept as a smoke test
    to ensure the validator itself hasn't regressed under the S8 changes.
    """
    from admin_api.api.services import _is_forbidden_destination
    assert _is_forbidden_destination("http://192.168.1.1/api") is True
    assert _is_forbidden_destination("http://10.0.0.1/api") is True
    assert _is_forbidden_destination("http://127.0.0.1/api") is True
    assert _is_forbidden_destination("https://api.openai.com") is False


# ---------------------------------------------------------------------------
# S8-codeql: py/stack-trace-exposure — test_service unexpected exception path
# (services.py:802)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_test_service_unexpected_exception_returns_generic_error(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """
    POST /{service_id}/test: when httpx.AsyncClient.request raises an unexpected
    Exception containing a sensitive message, the HTTP response body must contain
    only the static string "internal_error" (not the exception text), and the
    sensitive detail must appear in server logs.

    Closes CodeQL alert py/stack-trace-exposure @ services.py:802.
    Source: S8-codeql; CWE-209; O2 (strike-2 test gap).
    """
    import uuid
    from fastapi import FastAPI
    from admin_api.api.services import router as services_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    # Build a minimal DB session that returns a valid service row with an
    # external (non-RFC1918) base_url so the SSRF guardrail passes.
    service_db_uuid = str(uuid.UUID("00000000-0000-0000-0000-000000000002"))

    def _make_session_with_service():
        session = MagicMock()
        stub_row = MagicMock()
        stub_row.id = service_db_uuid
        stub_row.base_url = "https://api.openai.com"
        stub_row.auth_scheme = "bearer_token"

        async def _execute(*args, **kwargs):
            result = MagicMock()
            result.fetchone.return_value = stub_row
            return result

        session.execute = _execute
        return session

    local_app = FastAPI()
    local_app.include_router(services_router)

    async def mock_db():
        yield _make_session_with_service()

    local_app.dependency_overrides[get_db_session] = mock_db

    # Register the test-service path as CSRF-exempt
    test_path = f"{BASE_URL_PATH}/svc_00000000000000000000000002/test"
    csrf_exempt(test_path)
    local_app.add_middleware(CsrfMiddleware)

    SENSITIVE_MSG = "DB password=hunter2 leaked"

    # Mock the httpx.AsyncClient used *inside* the services module so only the
    # outbound call to the external service is intercepted — not the ASGI test
    # transport (which is also httpx-based).
    mock_httpx_client = MagicMock()
    mock_httpx_client.__aenter__ = AsyncMock(return_value=mock_httpx_client)
    mock_httpx_client.__aexit__ = AsyncMock(return_value=False)
    mock_httpx_client.request = AsyncMock(side_effect=Exception(SENSITIVE_MSG))

    with (
        patch(
            "admin_api.services.vault_client.get_vault_client",
            new=AsyncMock(return_value=AsyncMock(get_credential=AsyncMock(return_value=None))),
        ),
        patch(
            "admin_api.api.services.audit_emit",
            new=AsyncMock(),
        ),
        patch(
            "admin_api.api.services.httpx.AsyncClient",
            return_value=mock_httpx_client,
        ),
        caplog.at_level("WARNING", logger="admin_api.api.services"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=local_app), base_url="http://test"
        ) as client:
            resp = await client.post(test_path, json={"method": "GET", "path": "/health"})

    # HTTP response must use the static error string — not the exception message.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body.get("error") == "internal_error", (
        f"Stack-trace exposure: expected 'internal_error', got: {body.get('error')!r}"
    )
    assert SENSITIVE_MSG not in resp.text, (
        f"Stack-trace exposure: sensitive exception text appeared in HTTP response body: {resp.text!r}"
    )

    # Sensitive detail must appear in server-side logs (so operators can diagnose).
    assert any(SENSITIVE_MSG in record.message for record in caplog.records), (
        "Expected sensitive error detail to appear in server logs via logger.warning, "
        f"but log records were: {[r.message for r in caplog.records]}"
    )
