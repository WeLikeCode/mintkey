"""
Unit tests: Credential endpoints (session 1).

POST /v1/tenants/{tid}/services/{sid}/credentials — register credential (201)
GET  /v1/tenants/{tid}/services/{sid}/credentials — list versions (200)

Sources:
  - ADR-0014.4 (no plaintext in logs/responses/audit)
  - ADR-0014.7 (audit emit on every state change)
  - ADR-0017.11 (ULID IDs with cred_ prefix)
  - S-SEC-1 (plaintext credential never echoed back)
  - T-1.3.2 (credential CRUD session 1)
"""
from __future__ import annotations

import json
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
SERVICE_ID = "00000000-0000-0000-0000-000000000002"
BASE_URL_PATH = f"/v1/tenants/{TENANT_ID}/services/{SERVICE_ID}/credentials"

_PLAINTEXT_VALUE = "sk-secret-test-credential-value-xyz"


def _make_mock_session():
    """Return an async-capable mock DB session."""
    session = MagicMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def create_test_app():
    """
    Create an app with:
      - credentials router included
      - get_db_session overridden to a mock (no real DB)
      - get_vault_client overridden to a mock (no real gRPC)
      - CSRF middleware present but credentials paths registered as exempt
    """
    from fastapi import FastAPI
    from admin_api.api.health import router as health_router
    from admin_api.api.credentials import router as credentials_router
    from admin_api.db.deps import get_db_session
    from admin_api.services.vault_client import get_vault_client, VaultAdapterClient
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(health_router)
    app.include_router(credentials_router)

    # Override DB dependency with mock
    async def mock_db_session():
        yield _make_mock_session()

    app.dependency_overrides[get_db_session] = mock_db_session

    # Override vault client with mock that returns stable metadata
    class _MockVaultClient(VaultAdapterClient):
        async def put_credential(self, tenant_id, service_id, auth_scheme, plaintext):
            return {
                "credential_id": "cred_abc123xyz00000000000000001",
                "key_version": 1,
                "created_at": 1_700_000_000.0,
            }

        async def list_versions(self, tenant_id, service_id):
            return [{"key_version": 1, "status": "active"}]

    _mock_vault = _MockVaultClient()

    async def mock_vault_client():
        return _mock_vault

    app.dependency_overrides[get_vault_client] = mock_vault_client

    # Register credentials paths as CSRF-exempt for unit tests
    csrf_exempt(BASE_URL_PATH)

    app.add_middleware(CsrfMiddleware)

    return app


@pytest.fixture()
def app():
    return create_test_app()


@pytest.fixture()
def mock_audit():
    """Patch audit_emit so unit tests don't hit the DB hash-chain logic."""
    with patch("admin_api.api.credentials.audit_emit", new=AsyncMock()) as m:
        yield m


# ---------------------------------------------------------------------------
# POST — create credential
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_credential_returns_201_with_metadata(app, mock_audit) -> None:
    """
    POST /v1/tenants/{tid}/services/{sid}/credentials → 201.
    Response contains id, key_version, auth_scheme, created_at.
    Source: T-1.3.2; ADR-0017.11.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "id" in body, f"Missing 'id' in response: {body}"
    assert "key_version" in body, f"Missing 'key_version' in response: {body}"
    assert "auth_scheme" in body, f"Missing 'auth_scheme' in response: {body}"
    assert "created_at" in body, f"Missing 'created_at' in response: {body}"
    assert body["auth_scheme"] == "bearer_token"
    assert body["key_version"] == 1


@pytest.mark.asyncio
async def test_create_credential_response_has_no_plaintext(app, mock_audit) -> None:
    """
    POST response JSON must NOT contain the plaintext credential value.
    Source: S-SEC-1; ADR-0014.4.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"auth_scheme": "api_key_header", "value": _PLAINTEXT_VALUE},
        )

    assert resp.status_code == 201, resp.text
    response_text = resp.text
    assert _PLAINTEXT_VALUE not in response_text, (
        f"Plaintext credential leaked in response body! Found '{_PLAINTEXT_VALUE}' in: {response_text}"
    )
    # Also assert 'value' key is not present
    body = resp.json()
    assert "value" not in body, f"'value' key present in response — must not echo plaintext: {body}"


@pytest.mark.asyncio
async def test_audit_credential_registered_emitted(app, mock_audit) -> None:
    """
    audit_emit is called with event_type="credential.registered" on POST.
    Source: ADR-0014.7; Req AUD-3.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
        )

    assert resp.status_code == 201, resp.text
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs.get("event_type") == "credential.registered", (
        f"Expected event_type='credential.registered', got: {call_kwargs.get('event_type')}"
    )


@pytest.mark.asyncio
async def test_audit_payload_has_no_plaintext(app, mock_audit) -> None:
    """
    audit_emit payload must NOT contain the plaintext credential value.
    Source: ADR-0014.4; S-SEC-1.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
        )

    assert resp.status_code == 201, resp.text
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    payload = call_kwargs.get("payload", {})
    # Serialize payload to string and check for plaintext
    payload_str = json.dumps(payload)
    assert _PLAINTEXT_VALUE not in payload_str, (
        f"Plaintext credential leaked in audit payload! "
        f"Found '{_PLAINTEXT_VALUE}' in payload: {payload_str}"
    )


# ---------------------------------------------------------------------------
# GET — list credential versions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_credential_versions_returns_200(app) -> None:
    """
    GET /v1/tenants/{tid}/services/{sid}/credentials → 200 with {"versions": [...]}.
    Source: T-1.3.2.
    """
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(BASE_URL_PATH)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "versions" in body, f"Missing 'versions' key in response: {body}"
    assert isinstance(body["versions"], list)
