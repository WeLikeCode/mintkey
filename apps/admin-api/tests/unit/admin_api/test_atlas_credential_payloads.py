"""
Unit tests for the MongoDB Atlas credential payloads — ADR-0029, C5.

Covers the two new structured credential schemes registered for the Atlas
Administration API:

  - oauth2_client_credentials (Service Accounts): OAuth2ClientCredentialsPayload
    { token_url (HTTPS + SSRF), client_id, client_secret, scope?, token_response_path? }
  - http_digest (Programmatic API Keys): HTTPDigestPayload { public_key, private_key }

Test dimensions per scheme:
  - Happy path: valid payload instantiates; to_vault_envelope() emits the exact
    JSON shape the Go proxy parses (design.md Component 1 / Component 2 field names).
  - Rejection: malformed JSON / non-HTTPS token_url / SSRF-blocked token_url /
    empty client_id / empty client_secret / empty public_key / empty private_key.
  - No-leak (S-SEC-1, ADR-0014.7): a unique marker planted in the secret-bearing
    field (client_secret / private_key) MUST NOT appear in the pydantic errors()
    output nor in the HTTP response body the endpoint returns.
  - Endpoint (create_credential): a valid payload yields a 201 whose body carries
    ONLY metadata (no plaintext), and the canonical envelope reaches vault.put_credential.

Source: openspec/changes/mongodb-atlas-admin-api/design.md; ADR-0029; S-SEC-1; ADR-0014.7.
"""
from __future__ import annotations

import json as _json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pydantic
import pytest

from admin_api.api.credentials import CredentialCreate, create_credential
from admin_api.services.credential_service import (
    HTTPDigestPayload,
    OAuth2ClientCredentialsPayload,
)
from admin_api.services.vault_client import _AUTH_SCHEME_MAP


def _marker() -> str:
    """Generate a unique secret-shaped marker per test run."""
    return f"LEAK-MARKER-{uuid.uuid4().hex}"


# ===========================================================================
# vault_client auth-scheme mapping — enum parity with vault.proto
# ===========================================================================


def test_http_digest_credential_scheme_maps_to_17() -> None:
    """http_digest must map to AUTH_SCHEME_HTTP_DIGEST = 17 (vault.proto)."""
    assert _AUTH_SCHEME_MAP["http_digest"] == 17


def test_oauth2_client_credentials_scheme_maps_to_5() -> None:
    """oauth2_client_credentials must already map to enum 5 (unchanged)."""
    assert _AUTH_SCHEME_MAP["oauth2_client_credentials"] == 5


# ===========================================================================
# OAuth2ClientCredentialsPayload — happy path
# ===========================================================================


def test_oauth2_client_credentials_happy_path() -> None:
    """Valid Service-Account payload instantiates with the default JSONPath."""
    payload = OAuth2ClientCredentialsPayload(
        token_url="https://cloud.mongodb.com/api/oauth/token",
        client_id="mdb_sa_id_abc",
        client_secret="mdb_sa_secret_xyz",
    )
    assert payload.token_response_path == "$.access_token"
    assert payload.scope is None


def test_oauth2_client_credentials_envelope_shape() -> None:
    """to_vault_envelope() emits exactly the keys the Go proxy parses (no scheme wrapper)."""
    payload = OAuth2ClientCredentialsPayload(
        token_url="https://cloud.mongodb.com/api/oauth/token",
        client_id="mdb_sa_id_abc",
        client_secret="mdb_sa_secret_xyz",
        scope="openid profile",
    )
    envelope = _json.loads(payload.to_vault_envelope())
    assert envelope == {
        "token_url": "https://cloud.mongodb.com/api/oauth/token",
        "client_id": "mdb_sa_id_abc",
        "client_secret": "mdb_sa_secret_xyz",
        "token_response_path": "$.access_token",
        "scope": "openid profile",
    }
    # design.md Component 1: bare object, NO {"scheme": ...} wrapper.
    assert "scheme" not in envelope


def test_oauth2_client_credentials_envelope_omits_absent_scope() -> None:
    """scope is omitted from the envelope when not supplied (Go omitempty parity)."""
    payload = OAuth2ClientCredentialsPayload(
        token_url="https://cloud.mongodb.com/api/oauth/token",
        client_id="mdb_sa_id_abc",
        client_secret="mdb_sa_secret_xyz",
    )
    envelope = _json.loads(payload.to_vault_envelope())
    assert "scope" not in envelope
    assert envelope["token_response_path"] == "$.access_token"


# ===========================================================================
# OAuth2ClientCredentialsPayload — rejection
# ===========================================================================


def test_oauth2_client_credentials_rejects_non_https_token_url() -> None:
    """http:// token_url is rejected (HTTPS required)."""
    with pytest.raises(pydantic.ValidationError, match="HTTPS"):
        OAuth2ClientCredentialsPayload(
            token_url="http://cloud.mongodb.com/api/oauth/token",
            client_id="id",
            client_secret="secret",
        )


def test_oauth2_client_credentials_rejects_ssrf_token_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A loopback token_url is blocked by the shared SSRF policy (S-SEC-1)."""
    monkeypatch.delenv("MINTKEY_SSRF_ALLOW_PRIVATE", raising=False)
    with pytest.raises(pydantic.ValidationError, match="SSRF"):
        OAuth2ClientCredentialsPayload(
            token_url="https://127.0.0.1/api/oauth/token",
            client_id="id",
            client_secret="secret",
        )


def test_oauth2_client_credentials_rejects_empty_client_id() -> None:
    """Empty client_id is rejected."""
    with pytest.raises(pydantic.ValidationError, match="client_id"):
        OAuth2ClientCredentialsPayload(
            token_url="https://cloud.mongodb.com/api/oauth/token",
            client_id="   ",
            client_secret="secret",
        )


def test_oauth2_client_credentials_rejects_empty_client_secret() -> None:
    """Empty client_secret is rejected."""
    with pytest.raises(pydantic.ValidationError, match="client_secret"):
        OAuth2ClientCredentialsPayload(
            token_url="https://cloud.mongodb.com/api/oauth/token",
            client_id="id",
            client_secret="",
        )


def test_oauth2_client_credentials_no_input_leak() -> None:
    """pydantic errors() must not echo the client_secret value (S-SEC-1)."""
    marker = _marker()
    with pytest.raises(pydantic.ValidationError) as exc_info:
        OAuth2ClientCredentialsPayload(
            # non-HTTPS triggers the error; client_secret is a valid-looking secret
            token_url="http://token.example.com/oauth/token",
            client_id="id",
            client_secret=marker,
        )
    errors = exc_info.value.errors(
        include_url=False, include_context=False, include_input=False
    )
    body = _json.dumps(
        {"type": "about:blank", "title": "validation error", "detail": errors}
    )
    assert marker not in body, (
        f"LEAK: client_secret marker appeared in oauth2_client_credentials error body:\n{body}"
    )


# ===========================================================================
# HTTPDigestPayload — happy path
# ===========================================================================


def test_http_digest_credential_happy_path() -> None:
    """Valid Programmatic API Key payload instantiates."""
    payload = HTTPDigestPayload(public_key="atlas-public-key", private_key="atlas-private-key")
    assert payload.public_key == "atlas-public-key"


def test_http_digest_credential_envelope_shape() -> None:
    """to_vault_envelope() emits exactly {"public_key","private_key"} (design.md Component 2)."""
    payload = HTTPDigestPayload(public_key="pub-abc", private_key="priv-xyz")
    envelope = _json.loads(payload.to_vault_envelope())
    assert envelope == {"public_key": "pub-abc", "private_key": "priv-xyz"}
    assert "scheme" not in envelope


# ===========================================================================
# HTTPDigestPayload — rejection
# ===========================================================================


def test_http_digest_credential_rejects_empty_public_key() -> None:
    """Empty public_key is rejected."""
    with pytest.raises(pydantic.ValidationError, match="public_key"):
        HTTPDigestPayload(public_key="", private_key="priv")


def test_http_digest_credential_rejects_empty_private_key() -> None:
    """Empty private_key is rejected."""
    with pytest.raises(pydantic.ValidationError, match="private_key"):
        HTTPDigestPayload(public_key="pub", private_key="   ")


def test_http_digest_credential_no_input_leak() -> None:
    """pydantic errors() must not echo the private_key value (S-SEC-1)."""
    marker = _marker()
    with pytest.raises(pydantic.ValidationError) as exc_info:
        HTTPDigestPayload(public_key="", private_key=marker)
    errors = exc_info.value.errors(
        include_url=False, include_context=False, include_input=False
    )
    body = _json.dumps(
        {"type": "about:blank", "title": "validation error", "detail": errors}
    )
    assert marker not in body, (
        f"LEAK: private_key marker appeared in http_digest error body:\n{body}"
    )


# ===========================================================================
# Endpoint (create_credential) — accept + reject, no plaintext in response
# ===========================================================================

_TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_SERVICE_UUID = "11111111-2222-3333-4444-555555555555"
_BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"


def _wire_to_db_side_effect(wire_id: str, prefix: str) -> str:
    """Mirror the harness in test_rotate_carry_forward: cred_ → valid UUID hex."""
    if wire_id.startswith("cred_"):
        return str(uuid.uuid5(uuid.NAMESPACE_OID, wire_id)).replace("-", "")
    return wire_id


_COMMON_PATCHES = [
    patch("admin_api.api.credentials.audit_emit", new_callable=AsyncMock),
    patch("admin_api.api.credentials.notify_change", new_callable=AsyncMock),
    patch("admin_api.api.credentials.set_tenant_context", new_callable=AsyncMock),
    patch(
        "admin_api.api.credentials._wire_to_db",
        side_effect=_wire_to_db_side_effect,
    ),
]


def _apply_patches(fn: Any) -> Any:
    for p in reversed(_COMMON_PATCHES):
        fn = p(fn)
    return fn


def _make_create_session() -> MagicMock:
    """Session whose execute() yields: SELECT services, sweep UPDATE, INSERT, UPDATE services."""
    session = MagicMock()
    session.execute = AsyncMock()

    svc_row = MagicMock()
    svc_row.base_url = _BASE_URL
    svc_result = MagicMock()
    svc_result.fetchone.return_value = svc_row

    empty_result = MagicMock()
    empty_result.fetchone.return_value = None
    empty_result.fetchall.return_value = []

    session.execute.side_effect = [svc_result, empty_result, empty_result, empty_result]
    return session


def _make_create_vault(new_key_version: int = 1) -> MagicMock:
    vault = MagicMock()
    vault.put_credential = AsyncMock(
        return_value={
            "credential_id": "cred_test_xxx",
            "key_version": new_key_version,
            "created_at": datetime.now(timezone.utc).timestamp(),
        }
    )
    return vault


@pytest.mark.asyncio
@_apply_patches
async def test_endpoint_oauth2_client_credentials_accepted_no_plaintext(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """Valid oauth2_client_credentials → 201 metadata-only; canonical envelope hits vault."""
    session = _make_create_session()
    vault = _make_create_vault()
    secret_marker = _marker()

    body = CredentialCreate(
        auth_scheme="oauth2_client_credentials",
        value=_json.dumps(
            {
                "token_url": "https://cloud.mongodb.com/api/oauth/token",
                "client_id": "mdb_sa_id",
                "client_secret": secret_marker,
            }
        ),
    )

    response = await create_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code == 201, f"expected 201, got {response.status_code}"
    # Response body must carry ONLY metadata — never the client_secret.
    assert secret_marker not in response.body.decode(), (
        "LEAK: client_secret appeared in the 201 response body"
    )
    # The canonical envelope (with the real fields) is what reaches the vault.
    vault.put_credential.assert_awaited_once()
    put_kwargs = vault.put_credential.call_args.kwargs
    assert put_kwargs["auth_scheme"] == "oauth2_client_credentials"
    envelope = _json.loads(put_kwargs["plaintext"])
    assert envelope["token_url"] == "https://cloud.mongodb.com/api/oauth/token"
    assert envelope["client_id"] == "mdb_sa_id"
    assert envelope["client_secret"] == secret_marker
    assert envelope["token_response_path"] == "$.access_token"


@pytest.mark.asyncio
@_apply_patches
async def test_endpoint_http_digest_accepted_no_plaintext(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """Valid http_digest → 201 metadata-only; {public_key,private_key} envelope hits vault."""
    session = _make_create_session()
    vault = _make_create_vault()
    private_marker = _marker()

    body = CredentialCreate(
        auth_scheme="http_digest",
        value=_json.dumps({"public_key": "atlas-pub", "private_key": private_marker}),
    )

    response = await create_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code == 201, f"expected 201, got {response.status_code}"
    assert private_marker not in response.body.decode(), (
        "LEAK: private_key appeared in the 201 response body"
    )
    put_kwargs = vault.put_credential.call_args.kwargs
    assert put_kwargs["auth_scheme"] == "http_digest"
    envelope = _json.loads(put_kwargs["plaintext"])
    assert envelope == {"public_key": "atlas-pub", "private_key": private_marker}


@pytest.mark.asyncio
@_apply_patches
async def test_endpoint_oauth2_client_credentials_non_https_rejected_no_leak(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """Non-HTTPS token_url → 400/422 with no submitted secret bytes in the body."""
    session = _make_create_session()
    vault = _make_create_vault()
    secret_marker = _marker()

    body = CredentialCreate(
        auth_scheme="oauth2_client_credentials",
        value=_json.dumps(
            {
                "token_url": f"http://token.example.com/{secret_marker}/oauth/token",
                "client_id": "id",
                "client_secret": secret_marker,
            }
        ),
    )

    response = await create_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code in (400, 422), f"got {response.status_code}"
    assert secret_marker not in response.body.decode(), (
        "LEAK: submitted secret bytes appeared in the rejection body"
    )
    vault.put_credential.assert_not_called()


@pytest.mark.asyncio
@_apply_patches
async def test_endpoint_oauth2_client_credentials_empty_secret_rejected_no_leak(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """Empty client_secret → 400/422; response body contains no submitted value."""
    session = _make_create_session()
    vault = _make_create_vault()
    id_marker = _marker()

    body = CredentialCreate(
        auth_scheme="oauth2_client_credentials",
        value=_json.dumps(
            {
                "token_url": "https://cloud.mongodb.com/api/oauth/token",
                "client_id": id_marker,
                "client_secret": "",
            }
        ),
    )

    response = await create_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code in (400, 422), f"got {response.status_code}"
    assert id_marker not in response.body.decode(), (
        "LEAK: submitted client_id bytes appeared in the rejection body"
    )
    vault.put_credential.assert_not_called()


@pytest.mark.asyncio
@_apply_patches
async def test_endpoint_http_digest_empty_private_key_rejected_no_leak(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """Empty private_key → 400/422; response body contains no submitted value."""
    session = _make_create_session()
    vault = _make_create_vault()
    pub_marker = _marker()

    body = CredentialCreate(
        auth_scheme="http_digest",
        value=_json.dumps({"public_key": pub_marker, "private_key": ""}),
    )

    response = await create_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code in (400, 422), f"got {response.status_code}"
    assert pub_marker not in response.body.decode(), (
        "LEAK: submitted public_key bytes appeared in the rejection body"
    )
    vault.put_credential.assert_not_called()


@pytest.mark.asyncio
@_apply_patches
async def test_endpoint_http_digest_malformed_json_rejected(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """A non-JSON http_digest value → 400/422; no vault write."""
    session = _make_create_session()
    vault = _make_create_vault()
    marker = _marker()

    body = CredentialCreate(auth_scheme="http_digest", value=f"not-json-{marker}")

    response = await create_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code in (400, 422), f"got {response.status_code}"
    assert marker not in response.body.decode(), (
        "LEAK: submitted bytes appeared in the malformed-JSON rejection body"
    )
    vault.put_credential.assert_not_called()
