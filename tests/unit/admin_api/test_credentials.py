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
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
SERVICE_ID = "00000000-0000-0000-0000-000000000002"
BASE_URL_PATH = f"/v1/tenants/{TENANT_ID}/services/{SERVICE_ID}/credentials"
ROTATE_URL_PATH = f"{BASE_URL_PATH}/rotate"

# Wire-form variants for SERVICE_ID (for rotate path tests)
_SVC_32HEX = "svc_" + SERVICE_ID.replace("-", "")  # svc_ + 32 hex chars

_PLAINTEXT_VALUE = "sk-secret-test-credential-value-xyz"


def _make_mock_session(active_credential=None):
    """Return an async-capable mock DB session.

    For create_credential: call sequence is
      0: set_tenant_context (SELECT set_config)
      1: SELECT base_url FROM services (WS-9 target_url lookup) → fake service row
      2+: INSERT, notify, etc. → None

    active_credential: if set (for rotate tests), fetchone() returns the right
    rows for the rotate endpoint's service-lookup and credential-lookup.
    Expects dict with keys: id, key_version, status.
    """
    session = MagicMock()

    _call_count = {"n": 0}

    async def _execute(*args, **kwargs):
        result = MagicMock()
        _call_count["n"] += 1
        n = _call_count["n"]
        if active_credential is not None and n == 1:
            # First execute (rotate path): service existence check → fake service row
            svc_row = MagicMock()
            svc_row.id = SERVICE_ID
            svc_row.base_url = "http://mock-backend:8999"
            result.fetchone.return_value = svc_row
        elif active_credential is not None and n == 2:
            # Second execute (rotate path): credential lookup → fake active credential
            cred_row = MagicMock()
            cred_row.id = active_credential.get("id", "some-uuid")
            cred_row.key_version = active_credential.get("key_version", 1)
            cred_row.status = active_credential.get("status", "active")
            result.fetchone.return_value = cred_row
        elif active_credential is None and n == 2:
            # create_credential path: second execute is SELECT base_url FROM services
            # (call_n 1 = set_tenant_context, call_n 2 = service lookup)
            svc_row = MagicMock()
            svc_row.id = SERVICE_ID
            svc_row.base_url = "http://mock-backend:8999"
            result.fetchone.return_value = svc_row
        else:
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
        async def put_credential(
            self, tenant_id, service_id, auth_scheme, plaintext, target_url="",
            header_name="", query_param=""
        ):
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
# POST with svc_ wire-form service_id — OPS-AA Bug 1 regression guard
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_credential_svc_hex_wire_form_returns_201(mock_audit) -> None:
    """
    POST .../credentials with svc_<32-hex> service_id in path → 201.

    This is the OPS-AA Bug 1 regression guard: before the fix, service_id was
    declared as `UUID` in the FastAPI path parameter, causing Pydantic to reject
    svc_<wire> forms with a 422 validation_failed.  After the fix (service_id: str
    + _svc_wire_to_db_uuid decoder), the wire form is decoded to a UUID before
    the DB query, and the handler should return 201.

    Source: OPS-AA #2; R12/R14a; ADR-0017.11.
    """
    svc_wire_path = f"/v1/tenants/{TENANT_ID}/services/{_SVC_32HEX}/credentials"

    # The app fixture hard-codes SERVICE_ID in the mock session, but we need a
    # fresh app whose session mock maps svc_<32-hex> → the same decoded UUID.
    # We reuse create_test_app() which already wires the mock session where
    # call-2 returns the service row — the decoded uuid matches SERVICE_ID.
    test_app = create_test_app()

    from admin_api.middleware.csrf import csrf_exempt
    csrf_exempt(svc_wire_path)

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        resp = await client.post(
            svc_wire_path,
            json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
        )

    assert resp.status_code == 201, (
        f"Expected 201 for svc_ wire-form service_id, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body["id"].startswith("cred_"), f"Expected cred_ prefix: {body.get('id')}"
    assert body["key_version"] == 1
    assert body["auth_scheme"] == "bearer_token"


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


# ---------------------------------------------------------------------------
# POST /rotate — rotate credential (R14a, ADR-0013 §3.1)
# ---------------------------------------------------------------------------


def _make_rotate_mock_session():
    """
    Mock session for rotate tests.

    Call sequence in rotate_credential():
      0: set_tenant_context → SELECT set_config(...)
      1: service existence check → SELECT id FROM services WHERE ...
      2: credential lookup    → SELECT id, key_version, status FROM credentials WHERE ...
      3: UPDATE credentials SET status = 'superseded' WHERE ...
      4: INSERT INTO credentials ...
      (+ audit_emit calls if not mocked separately)
    """
    session = MagicMock()
    _calls = []

    async def _execute(*args, **kwargs):
        result = MagicMock()
        call_n = len(_calls)
        _calls.append(1)
        if call_n == 0:
            # set_tenant_context: SELECT set_config — return doesn't matter
            result.fetchone.return_value = None
        elif call_n == 1:
            # service existence check (now also fetches base_url for WS-9 target_url)
            svc_row = MagicMock()
            svc_row.id = SERVICE_ID
            svc_row.base_url = "http://mock-backend:8999"
            result.fetchone.return_value = svc_row
        elif call_n == 2:
            # credential lookup → return fake active credential
            cred_row = MagicMock()
            cred_row.id = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
            cred_row.key_version = 1
            cred_row.status = "active"
            result.fetchone.return_value = cred_row
        else:
            # UPDATE, INSERT, notify — return value irrelevant
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def create_rotate_test_app():
    """
    App with rotate endpoint and a session mock that simulates an active credential.
    Service and credential lookups both succeed.
    """
    from fastapi import FastAPI
    from admin_api.api.credentials import router as credentials_router
    from admin_api.db.deps import get_db_session
    from admin_api.services.vault_client import get_vault_client, VaultAdapterClient
    from admin_api.middleware.csrf import csrf_exempt

    app = FastAPI()
    app.include_router(credentials_router)

    async def mock_db_session():
        yield _make_rotate_mock_session()

    app.dependency_overrides[get_db_session] = mock_db_session

    class _MockVaultClient(VaultAdapterClient):
        async def put_credential(
            self, tenant_id, service_id, auth_scheme, plaintext, target_url=""
        ):
            return {"credential_id": "cred_rotate_mock", "key_version": 2, "created_at": 1_700_000_000.0}

        async def list_versions(self, tenant_id, service_id):
            return [{"key_version": 1, "status": "active"}]

    _mock_vault = _MockVaultClient()

    async def mock_vault_client():
        return _mock_vault

    app.dependency_overrides[get_vault_client] = mock_vault_client

    csrf_exempt(BASE_URL_PATH)
    csrf_exempt(ROTATE_URL_PATH)

    return app


@pytest.fixture()
def rotate_app():
    return create_rotate_test_app()


@pytest.fixture()
def mock_audit_rotate():
    with patch("admin_api.api.credentials.audit_emit", new=AsyncMock()) as m:
        yield m


@pytest.mark.asyncio
async def test_rotate_credential_returns_200(rotate_app, mock_audit_rotate) -> None:
    """
    POST .../credentials/rotate → 200 with cred_ ID, key_version, effective_at.
    Source: ADR-0013 §3.1; R14a.
    """
    async with AsyncClient(transport=ASGITransport(app=rotate_app), base_url="http://test") as client:
        resp = await client.post(
            ROTATE_URL_PATH,
            json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"].startswith("cred_"), f"Expected cred_ prefix: {body['id']}"
    assert "key_version" in body
    assert "auth_scheme" in body
    assert "effective_at" in body
    assert body["auth_scheme"] == "bearer_token"


@pytest.mark.asyncio
async def test_rotate_credential_no_plaintext_in_response(rotate_app, mock_audit_rotate) -> None:
    """
    Rotate response must NOT contain the plaintext value — ADR-0014.4, S-SEC-1.
    """
    async with AsyncClient(transport=ASGITransport(app=rotate_app), base_url="http://test") as client:
        resp = await client.post(
            ROTATE_URL_PATH,
            json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
        )

    assert resp.status_code == 200, resp.text
    assert _PLAINTEXT_VALUE not in resp.text
    assert "value" not in resp.json()


@pytest.mark.asyncio
async def test_rotate_credential_svc_hex_wire_form(rotate_app, mock_audit_rotate) -> None:
    """
    POST .../credentials/rotate with svc_<32-hex> service_id in path → 200.
    The wire form is decoded by _svc_wire_to_db_uuid in credentials.py (R14a).
    """
    rotate_url_hex = f"/v1/tenants/{TENANT_ID}/services/{_SVC_32HEX}/credentials/rotate"
    async with AsyncClient(transport=ASGITransport(app=rotate_app), base_url="http://test") as client:
        resp = await client.post(
            rotate_url_hex,
            json={"auth_scheme": "bearer_token"},
        )

    assert resp.status_code == 200, resp.text
    assert resp.json()["id"].startswith("cred_")


@pytest.mark.asyncio
async def test_rotate_credential_missing_auth_scheme_returns_422(rotate_app) -> None:
    """
    Missing required auth_scheme → 422 validation error.
    """
    async with AsyncClient(transport=ASGITransport(app=rotate_app), base_url="http://test") as client:
        resp = await client.post(ROTATE_URL_PATH, json={"value": "some-value"})

    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_rotate_credential_audit_emitted(rotate_app, mock_audit_rotate) -> None:
    """
    audit_emit is called with event_type='credential.rotated' — ADR-0014.7.
    """
    async with AsyncClient(transport=ASGITransport(app=rotate_app), base_url="http://test") as client:
        resp = await client.post(
            ROTATE_URL_PATH,
            json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
        )

    assert resp.status_code == 200, resp.text
    mock_audit_rotate.assert_called_once()
    call_kwargs = mock_audit_rotate.call_args.kwargs
    assert call_kwargs.get("event_type") == "credential.rotated"
    # Verify plaintext NOT in audit payload — ADR-0014.4
    payload_str = json.dumps(call_kwargs.get("payload", {}))
    assert _PLAINTEXT_VALUE not in payload_str


# ---------------------------------------------------------------------------
# POST /rotate with rotate_from — C1 unit tests (R14a)
# ---------------------------------------------------------------------------

_KNOWN_CRED_ID = "aaaabbbb-cccc-dddd-eeee-ffffffffffff"  # valid UUID returned by _make_rotate_mock_session


@pytest.mark.asyncio
async def test_rotate_with_rotate_from_matching_id_returns_200(
    rotate_app, mock_audit_rotate
) -> None:
    """
    C1: rotate_from set to the ID that the mock session returns → 200.
    The WHERE clause filters on rotate_from; mock returns the matching row.
    """
    async with AsyncClient(transport=ASGITransport(app=rotate_app), base_url="http://test") as client:
        resp = await client.post(
            ROTATE_URL_PATH,
            json={
                "auth_scheme": "bearer_token",
                "value": _PLAINTEXT_VALUE,
                "rotate_from": _KNOWN_CRED_ID,
            },
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"].startswith("cred_")
    assert "effective_at" in body


def _make_rotate_no_cred_session():
    """Mock session where the credential lookup returns None (rotate_from not found)."""
    session = MagicMock()
    _calls = []

    async def _execute(*args, **kwargs):
        result = MagicMock()
        call_n = len(_calls)
        _calls.append(1)
        if call_n == 0:
            # set_tenant_context
            result.fetchone.return_value = None
        elif call_n == 1:
            # service existence check → service found
            svc_row = MagicMock()
            svc_row.id = SERVICE_ID
            svc_row.base_url = "http://mock-backend:8999"
            result.fetchone.return_value = svc_row
        else:
            # credential lookup → no row (rotate_from does not match)
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def create_rotate_no_cred_app():
    """App whose credential lookup returns None — simulates rotate_from not found."""
    from fastapi import FastAPI
    from admin_api.api.credentials import router as credentials_router
    from admin_api.db.deps import get_db_session
    from admin_api.services.vault_client import get_vault_client, VaultAdapterClient
    from admin_api.middleware.csrf import csrf_exempt

    app = FastAPI()
    app.include_router(credentials_router)

    async def mock_db_session():
        yield _make_rotate_no_cred_session()

    app.dependency_overrides[get_db_session] = mock_db_session

    class _MockVaultClient(VaultAdapterClient):
        async def put_credential(
            self, tenant_id, service_id, auth_scheme, plaintext, target_url="",
            header_name="", query_param=""
        ):
            return {"credential_id": "cred_mock", "key_version": 2, "created_at": 0.0}

        async def list_versions(self, tenant_id, service_id):
            return []

    app.dependency_overrides[get_vault_client] = lambda: _MockVaultClient()
    csrf_exempt(BASE_URL_PATH)
    csrf_exempt(ROTATE_URL_PATH)
    return app


@pytest.fixture()
def rotate_no_cred_app():
    return create_rotate_no_cred_app()


@pytest.mark.asyncio
async def test_rotate_with_rotate_from_nonexistent_returns_404(
    rotate_no_cred_app,
) -> None:
    """
    C1: rotate_from pointing at a valid UUID that has no matching row → 404 not_found.
    Uses a proper UUID string so it passes the wire-ID validator; mock session returns None.
    """
    # A syntactically valid UUID that the mock returns no row for
    valid_but_absent = "00000000-0000-0000-0000-000000000099"
    async with AsyncClient(
        transport=ASGITransport(app=rotate_no_cred_app), base_url="http://test"
    ) as client:
        resp = await client.post(
            ROTATE_URL_PATH,
            json={
                "auth_scheme": "bearer_token",
                "value": "irrelevant",
                "rotate_from": valid_but_absent,
            },
        )

    assert resp.status_code == 404, resp.text
    assert resp.json()["mintkey:code"] == "not_found"


# ---------------------------------------------------------------------------
# oauth2_password_grant payload validation — BUG-2/BUG-9 regression guard
# Requirements: 19.2, 19.4, 19.5, 19.6 / S-SEC-1
# ---------------------------------------------------------------------------

import json as _json


def _valid_oauth2_payload() -> dict:
    """Minimal valid oauth2_password_grant value (JSON-encoded as str)."""
    return {
        "token_url": "https://auth.example.com/token",
        "credential_fields": {"client_id": "abc", "client_secret": "xyz"},
    }


@pytest.mark.asyncio
async def test_oauth2_password_grant_valid_returns_201(app, mock_audit) -> None:
    """
    POST with auth_scheme=oauth2_password_grant and a valid JSON payload → 201.
    token_response_path must default to $.access_token in the accepted payload.
    DNS resolution is mocked so the SSRF validator sees a public (non-forbidden) IP.
    Requirement 19.6.
    """
    payload = _valid_oauth2_payload()
    # Patch socket.getaddrinfo so the SSRF validator sees a real public IP (8.8.8.8)
    # rather than a DNS-resolution failure in the sandboxed test environment.
    with patch(
        "admin_api.services.credential_service.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("8.8.8.8", 0))],
    ):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                BASE_URL_PATH,
                json={"auth_scheme": "oauth2_password_grant", "value": _json.dumps(payload)},
            )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["auth_scheme"] == "oauth2_password_grant"


@pytest.mark.asyncio
async def test_oauth2_password_grant_non_https_token_url_rejected(app, mock_audit) -> None:
    """
    oauth2_password_grant with http:// token_url → 422.
    Requirement 19.4 / S-SEC-1.
    This test FAILS without validation wired in.
    """
    payload = _valid_oauth2_payload()
    payload["token_url"] = "http://auth.example.com/token"  # non-HTTPS
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"auth_scheme": "oauth2_password_grant", "value": _json.dumps(payload)},
        )

    assert resp.status_code == 422, (
        f"Expected 422 for non-HTTPS token_url, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_oauth2_password_grant_loopback_token_url_rejected(app, mock_audit) -> None:
    """
    oauth2_password_grant with loopback IP in token_url → 422 (SSRF block).
    S-SEC-1 / Requirement 19.4.
    This test FAILS without SSRF validation wired in.
    """
    payload = _valid_oauth2_payload()
    payload["token_url"] = "https://127.0.0.1/token"
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"auth_scheme": "oauth2_password_grant", "value": _json.dumps(payload)},
        )

    assert resp.status_code == 422, (
        f"Expected 422 for loopback token_url, got {resp.status_code}: {resp.text}"
    )


@pytest.mark.asyncio
async def test_oauth2_password_grant_private_ip_token_url_rejected(app, mock_audit) -> None:
    """
    oauth2_password_grant with RFC1918 IP in token_url → 422.
    S-SEC-1 / Requirement 19.4.
    This test FAILS without SSRF validation wired in.
    """
    for private_ip in ["10.0.0.1", "172.16.0.1", "192.168.1.1", "169.254.1.1"]:
        payload = _valid_oauth2_payload()
        payload["token_url"] = f"https://{private_ip}/token"
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post(
                BASE_URL_PATH,
                json={"auth_scheme": "oauth2_password_grant", "value": _json.dumps(payload)},
            )
        assert resp.status_code == 422, (
            f"Expected 422 for private IP {private_ip} in token_url, "
            f"got {resp.status_code}: {resp.text}"
        )


@pytest.mark.asyncio
async def test_oauth2_password_grant_empty_credential_fields_rejected(app, mock_audit) -> None:
    """
    oauth2_password_grant with empty credential_fields → 422.
    Requirement 19.2 / 19.5.
    This test FAILS without validation wired in.
    """
    payload = _valid_oauth2_payload()
    payload["credential_fields"] = {}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            BASE_URL_PATH,
            json={"auth_scheme": "oauth2_password_grant", "value": _json.dumps(payload)},
        )

    assert resp.status_code == 422, (
        f"Expected 422 for empty credential_fields, got {resp.status_code}: {resp.text}"
    )
