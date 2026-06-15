"""
Unit tests: apple_jwt credential validation — spec §4.2 / Chunk 4.

POST /v1/tenants/{tid}/services/{sid}/credentials with auth_scheme=apple_jwt

Verifies:
  - Valid apple_jwt envelope → 201 (vault-adapter call mocked)
  - Bad PEM (wrong header) → 400
  - Missing / empty key_id → 400
  - Missing / empty issuer_id → 400
  - p8_key_pem value never appears in any log output — ADR-0014.4 / ADR-0014.7
  - Audit payload includes key_id, issuer_id, p8_fingerprint; NEVER p8_key_pem

Sources: spec §4.2; ADR-0014.4; ADR-0014.7; S-SEC-1.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# ---------------------------------------------------------------------------
# sys.path setup — mirrors test_credentials.py
# ---------------------------------------------------------------------------
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _p in (ADMIN_API_SRC, MODELS_SRC):
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------
TENANT_ID = "00000000-0000-0000-0000-000000000001"
SERVICE_ID = "00000000-0000-0000-0000-000000000002"
BASE_URL_PATH = f"/v1/tenants/{TENANT_ID}/services/{SERVICE_ID}/credentials"

# Minimal valid PKCS#8 PEM — not a real key; starts with the required header.
_VALID_P8_PEM = (
    "-----BEGIN PRIVATE KEY-----\n"
    "MIGHAgEAMBMGByqGSM49AgEGCCqGSM49AwEHBG0wawIBAQQgevZzL1gdAFr88hD2\n"
    "hTsxreDuBBLSAFAghkiG9w0BBwGhRANCAARxy5u39/yTvKCS3nD1WrG/VyQLToyo\n"
    "-----END PRIVATE KEY-----\n"
)
_VALID_KEY_ID = "ABCD1234EF"
_VALID_ISSUER_ID = "a1b2c3d4-e5f6-7890-abcd-ef1234567890"

# Canonical envelope the vault adapter expects (Chunk 3 contract)
_VALID_ENVELOPE = json.dumps(
    {
        "scheme": "apple_jwt",
        "p8_key_pem": _VALID_P8_PEM,
        "key_id": _VALID_KEY_ID,
        "issuer_id": _VALID_ISSUER_ID,
    },
    separators=(",", ":"),
)

# UI-style payload (includes "scheme" field — must be accepted and stripped)
_VALID_UI_PAYLOAD = json.dumps(
    {
        "scheme": "apple_jwt",
        "p8_key_pem": _VALID_P8_PEM,
        "key_id": _VALID_KEY_ID,
        "issuer_id": _VALID_ISSUER_ID,
    }
)


# ---------------------------------------------------------------------------
# Mock session — mirrors _make_mock_session in test_credentials.py
# ---------------------------------------------------------------------------


def _make_mock_session() -> MagicMock:
    """Mock DB session for create_credential.

    Call sequence:
      1: set_tenant_context (SELECT set_config) → None
      2: SELECT base_url FROM services → fake service row
      3+: INSERT, notify → None
    """
    session = MagicMock()
    _call_count: dict[str, int] = {"n": 0}

    async def _execute(*args: object, **kwargs: object) -> MagicMock:
        result = MagicMock()
        _call_count["n"] += 1
        n = _call_count["n"]
        if n == 2:
            # Service lookup
            svc_row = MagicMock()
            svc_row.id = SERVICE_ID
            svc_row.base_url = "https://api.example.com"
            result.fetchone.return_value = svc_row
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


def _create_apple_jwt_app() -> object:
    """FastAPI test app with credentials router, mocked vault + DB."""
    from fastapi import FastAPI
    from admin_api.api.credentials import router as credentials_router
    from admin_api.auth.sessions import require_tenant_session
    from admin_api.db.deps import get_db_session
    from admin_api.services.vault_client import VaultAdapterClient, get_vault_client
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(credentials_router)

    async def _mock_db() -> object:
        yield _make_mock_session()

    app.dependency_overrides[get_db_session] = _mock_db

    class _MockVault(VaultAdapterClient):
        async def put_credential(  # type: ignore[override]
            self,
            tenant_id: str,
            service_id: str,
            auth_scheme: str,
            plaintext: str,
            target_url: str = "",
            header_name: str = "",
            query_param: str = "",
            target_address: str = "",
            ssh_user: str = "",
        ) -> dict[str, object]:
            return {
                "credential_id": "cred_apple_mock_0000000000000001",
                "key_version": 1,
                "created_at": 1_700_000_000.0,
            }

        async def list_versions(self, tenant_id: str, service_id: str) -> list[dict[str, object]]:
            return []

    _vault = _MockVault()

    async def _mock_vault() -> VaultAdapterClient:
        return _vault

    app.dependency_overrides[get_vault_client] = _mock_vault

    async def _noop_require_tenant_session() -> None:
        return None

    app.dependency_overrides[require_tenant_session] = _noop_require_tenant_session

    csrf_exempt(BASE_URL_PATH)
    app.add_middleware(CsrfMiddleware)

    return app


@pytest.fixture()
def apple_app() -> object:
    return _create_apple_jwt_app()


@pytest.fixture()
def mock_audit() -> object:
    """Patch audit_emit so tests don't need a real DB hash chain."""
    with patch("admin_api.api.credentials.audit_emit", new=AsyncMock()) as m:
        yield m


# ---------------------------------------------------------------------------
# Helper: POST a credential
# ---------------------------------------------------------------------------


async def _post_apple_jwt(
    client: AsyncClient,
    *,
    value: str,
) -> object:
    return await client.post(
        BASE_URL_PATH,
        json={"auth_scheme": "apple_jwt", "value": value},
    )


# ---------------------------------------------------------------------------
# Tests: valid payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apple_jwt_valid_envelope_returns_201(apple_app: object, mock_audit: object) -> None:
    """
    Valid apple_jwt envelope (UI-style, includes 'scheme' key) → 201.
    Response has cred_ ID, key_version=1, auth_scheme=apple_jwt.
    ADR-0017.11; spec §4.2.
    """
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=_VALID_UI_PAYLOAD)

    assert resp.status_code == 201, resp.text  # type: ignore[attr-defined]
    body = resp.json()  # type: ignore[attr-defined]
    assert body["id"].startswith("cred_"), f"Expected cred_ prefix: {body['id']}"
    assert body["auth_scheme"] == "apple_jwt"
    assert body["key_version"] == 1
    # ADR-0014.4: p8_key_pem must NOT appear in the response
    assert _VALID_P8_PEM not in resp.text  # type: ignore[attr-defined]
    assert "value" not in body


@pytest.mark.asyncio
async def test_apple_jwt_valid_plain_envelope_returns_201(apple_app: object, mock_audit: object) -> None:
    """
    Valid apple_jwt envelope without the outer 'scheme' key → 201.
    (Vault Adapter contract: value is the raw JSON envelope.)
    """
    plain_envelope = json.dumps(
        {
            "p8_key_pem": _VALID_P8_PEM,
            "key_id": _VALID_KEY_ID,
            "issuer_id": _VALID_ISSUER_ID,
        }
    )
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=plain_envelope)

    assert resp.status_code == 201, resp.text  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests: bad PEM header
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apple_jwt_bad_pem_header_returns_400(apple_app: object, mock_audit: object) -> None:
    """
    p8_key_pem that does NOT start with '-----BEGIN PRIVATE KEY-----' → 400.
    spec §4.2 PEM validator.
    """
    bad_pem = "-----BEGIN EC PRIVATE KEY-----\nAAAAAA==\n-----END EC PRIVATE KEY-----\n"
    payload = json.dumps(
        {"p8_key_pem": bad_pem, "key_id": _VALID_KEY_ID, "issuer_id": _VALID_ISSUER_ID}
    )
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=payload)

    assert resp.status_code == 400, f"Expected 400 for bad PEM header, got {resp.status_code}: {resp.text}"  # type: ignore[attr-defined]
    body = resp.json()  # type: ignore[attr-defined]
    assert body.get("mintkey:code") == "invalid_apple_jwt_payload"


@pytest.mark.asyncio
async def test_apple_jwt_empty_pem_returns_400(apple_app: object, mock_audit: object) -> None:
    """
    Empty p8_key_pem string → 400.
    """
    payload = json.dumps(
        {"p8_key_pem": "", "key_id": _VALID_KEY_ID, "issuer_id": _VALID_ISSUER_ID}
    )
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=payload)

    assert resp.status_code == 400, f"Expected 400 for empty pem, got {resp.status_code}: {resp.text}"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests: missing / empty key_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apple_jwt_missing_key_id_returns_400(apple_app: object, mock_audit: object) -> None:
    """
    Missing key_id field → 400.
    spec §4.2.
    """
    payload = json.dumps({"p8_key_pem": _VALID_P8_PEM, "issuer_id": _VALID_ISSUER_ID})
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=payload)

    assert resp.status_code == 400, f"Expected 400 for missing key_id, got {resp.status_code}: {resp.text}"  # type: ignore[attr-defined]
    body = resp.json()  # type: ignore[attr-defined]
    assert body.get("mintkey:code") == "invalid_apple_jwt_payload"


@pytest.mark.asyncio
async def test_apple_jwt_empty_key_id_returns_400(apple_app: object, mock_audit: object) -> None:
    """
    Empty key_id string → 400.
    """
    payload = json.dumps(
        {"p8_key_pem": _VALID_P8_PEM, "key_id": "   ", "issuer_id": _VALID_ISSUER_ID}
    )
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=payload)

    assert resp.status_code == 400, f"Expected 400 for empty key_id, got {resp.status_code}: {resp.text}"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests: missing / empty issuer_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apple_jwt_missing_issuer_id_returns_400(apple_app: object, mock_audit: object) -> None:
    """
    Missing issuer_id field → 400.
    spec §4.2.
    """
    payload = json.dumps({"p8_key_pem": _VALID_P8_PEM, "key_id": _VALID_KEY_ID})
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=payload)

    assert resp.status_code == 400, f"Expected 400 for missing issuer_id, got {resp.status_code}: {resp.text}"  # type: ignore[attr-defined]
    body = resp.json()  # type: ignore[attr-defined]
    assert body.get("mintkey:code") == "invalid_apple_jwt_payload"


@pytest.mark.asyncio
async def test_apple_jwt_empty_issuer_id_returns_400(apple_app: object, mock_audit: object) -> None:
    """
    Empty issuer_id string → 400.
    """
    payload = json.dumps(
        {"p8_key_pem": _VALID_P8_PEM, "key_id": _VALID_KEY_ID, "issuer_id": ""}
    )
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=payload)

    assert resp.status_code == 400, f"Expected 400 for empty issuer_id, got {resp.status_code}: {resp.text}"  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# Tests: non-JSON value
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apple_jwt_non_json_value_returns_400(apple_app: object, mock_audit: object) -> None:
    """
    Non-JSON string as apple_jwt value → 400.
    """
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value="not-json-at-all")

    assert resp.status_code == 400, f"Expected 400 for non-JSON value, got {resp.status_code}: {resp.text}"  # type: ignore[attr-defined]
    body = resp.json()  # type: ignore[attr-defined]
    assert body.get("mintkey:code") == "invalid_apple_jwt_payload"


# ---------------------------------------------------------------------------
# Tests: audit payload — key_id + issuer_id + fingerprint; NEVER p8_key_pem
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apple_jwt_audit_has_key_id_issuer_id_fingerprint(
    apple_app: object, mock_audit: object
) -> None:
    """
    audit_emit payload includes key_id, issuer_id, p8_fingerprint (SHA-256[:16]).
    NEVER includes p8_key_pem itself — ADR-0014.7.
    """
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=_VALID_UI_PAYLOAD)

    assert resp.status_code == 201, resp.text  # type: ignore[attr-defined]

    mock_audit.assert_called_once()  # type: ignore[attr-defined]
    call_kwargs = mock_audit.call_args.kwargs  # type: ignore[attr-defined]
    payload = call_kwargs.get("payload", {})

    # Required fields
    assert payload.get("key_id") == _VALID_KEY_ID, f"key_id missing/wrong in audit payload: {payload}"
    assert payload.get("issuer_id") == _VALID_ISSUER_ID, f"issuer_id missing/wrong in audit payload: {payload}"

    from admin_api.services.audit_fingerprint import audit_fingerprint
    expected_fp = audit_fingerprint(_VALID_P8_PEM.encode())
    assert payload.get("p8_fingerprint") == expected_fp, (
        f"p8_fingerprint wrong in audit payload: got {payload.get('p8_fingerprint')!r}, "
        f"expected {expected_fp!r}"
    )

    # p8_key_pem must NOT appear anywhere in the serialised audit payload
    payload_str = json.dumps(payload)
    assert _VALID_P8_PEM not in payload_str, (
        f"p8_key_pem leaked into audit payload! payload={payload_str[:200]}"
    )
    assert "BEGIN PRIVATE KEY" not in payload_str, (
        f"PEM material leaked into audit payload! payload={payload_str[:200]}"
    )


@pytest.mark.asyncio
async def test_apple_jwt_audit_no_p8_key_pem(apple_app: object, mock_audit: object) -> None:
    """
    The string 'p8_key_pem' as a key must not appear in the audit payload dict.
    Guards against accidental inclusion of the field itself — ADR-0014.4.
    """
    async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
        resp = await _post_apple_jwt(client, value=_VALID_UI_PAYLOAD)

    assert resp.status_code == 201, resp.text  # type: ignore[attr-defined]
    call_kwargs = mock_audit.call_args.kwargs  # type: ignore[attr-defined]
    payload = call_kwargs.get("payload", {})
    assert "p8_key_pem" not in payload, (
        f"'p8_key_pem' key found in audit payload — must be excluded: {list(payload.keys())}"
    )


# ---------------------------------------------------------------------------
# Tests: log scrubbing — p8_key_pem must not appear in any log record
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apple_jwt_p8_key_pem_not_in_logs(apple_app: object, mock_audit: object) -> None:
    """
    After registering an apple_jwt credential, p8_key_pem's value string must
    NOT appear in any log record emitted by admin_api.api.credentials.

    Captures log output via caplog (stdlib logging) — covers logger.warning calls
    inside the create_credential handler. The p8_key_pem is only ever written to
    the vault envelope string and passed to StoreCredential (never logged).

    ADR-0014.4; S-SEC-1.
    """
    import logging as _logging

    captured_records: list[str] = []

    class _CaptureHandler(_logging.Handler):
        def emit(self, record: _logging.LogRecord) -> None:
            captured_records.append(self.format(record))

    handler = _CaptureHandler()
    creds_logger = _logging.getLogger("admin_api.api.credentials")
    creds_logger.addHandler(handler)
    creds_logger.setLevel(_logging.DEBUG)

    try:
        async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
            resp = await _post_apple_jwt(client, value=_VALID_UI_PAYLOAD)

        assert resp.status_code == 201, resp.text  # type: ignore[attr-defined]

        all_log_output = "\n".join(captured_records)
        # The raw PEM value must not appear in any log line
        assert _VALID_P8_PEM not in all_log_output, (
            f"p8_key_pem value leaked into log output!\n"
            f"Log lines captured:\n{all_log_output}"
        )
        # Also check the PEM header string doesn't appear (defence-in-depth)
        assert "BEGIN PRIVATE KEY" not in all_log_output, (
            f"PEM header leaked into log output!\nLog:\n{all_log_output}"
        )
    finally:
        creds_logger.removeHandler(handler)


@pytest.mark.asyncio
async def test_apple_jwt_p8_key_pem_not_in_warning_logs_on_validation_failure(
    apple_app: object,
) -> None:
    """
    When apple_jwt validation fails, the warning log must NOT include p8_key_pem
    in its message — only the constraint description (no sensitive value).

    ADR-0014.7: log scrubbing at validation call site.
    """
    captured_records: list[str] = []

    class _CaptureHandler(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured_records.append(self.format(record))

    handler = _CaptureHandler()
    creds_logger = logging.getLogger("admin_api.api.credentials")
    creds_logger.addHandler(handler)
    creds_logger.setLevel(logging.DEBUG)

    # A PEM string that LOOKS like a real key (starts correctly) but has bad key_id
    bad_key_id_payload = json.dumps(
        {"p8_key_pem": _VALID_P8_PEM, "key_id": "", "issuer_id": _VALID_ISSUER_ID}
    )

    try:
        async with AsyncClient(transport=ASGITransport(app=apple_app), base_url="http://test") as client:  # type: ignore[arg-type]
            resp = await _post_apple_jwt(client, value=bad_key_id_payload)

        # Should be 400
        assert resp.status_code == 400, f"Expected 400 for empty key_id, got {resp.status_code}"  # type: ignore[attr-defined]

        all_log_output = "\n".join(captured_records)
        # p8_key_pem value must NOT appear in warning logs
        assert _VALID_P8_PEM not in all_log_output, (
            f"p8_key_pem leaked in warning log on validation failure!\n{all_log_output}"
        )
        assert "BEGIN PRIVATE KEY" not in all_log_output, (
            f"PEM header leaked in warning log!\n{all_log_output}"
        )
    finally:
        creds_logger.removeHandler(handler)
