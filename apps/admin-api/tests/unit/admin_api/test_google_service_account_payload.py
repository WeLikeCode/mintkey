"""
Unit tests for GoogleServiceAccountPayload — spec §4.3.

Covers:
  - Happy path: valid service-account JSON → model instantiates, to_vault_envelope()
    returns expected shape with 'json_key' (not 'service_account_json').
  - Bad JSON (not a dict): rejected with terse ValueError.
  - Missing required field (private_key): rejected.
  - Wrong type field (authorized_user): rejected.
  - Non-HTTPS token_uri: rejected.
  - Empty scope: rejected.
  - to_vault_envelope() envelope shape matches Go-side StoredBlob (json_key field name).
  - Log scrubbing: service_account_json never appears in warning log records during
    endpoint-level payload validation.

Source: spec §4.3; ADR-0014.4; ADR-0014.7.
"""
from __future__ import annotations

import hashlib
import json
import logging

import pytest

from admin_api.services.credential_service import GoogleServiceAccountPayload

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_SA_JSON: dict[str, str] = {
    "type": "service_account",
    "project_id": "my-project",
    "private_key_id": "key123",
    "private_key": (
        "-----BEGIN PRIVATE KEY-----\n"
        "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7o4...\n"
        "-----END PRIVATE KEY-----\n"
    ),
    "client_email": "mysa@my-project.iam.gserviceaccount.com",
    "token_uri": "https://oauth2.googleapis.com/token",
}

_VALID_SA_JSON_STR: str = json.dumps(_VALID_SA_JSON)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_happy_path_instantiates() -> None:
    """Valid Google SA JSON → no exception raised."""
    payload = GoogleServiceAccountPayload(service_account_json=_VALID_SA_JSON_STR)
    assert payload.scope == "https://www.googleapis.com/auth/androidpublisher"


def test_happy_path_custom_scope() -> None:
    """Custom scope is accepted and preserved."""
    payload = GoogleServiceAccountPayload(
        service_account_json=_VALID_SA_JSON_STR,
        scope="https://www.googleapis.com/auth/cloud-platform",
    )
    assert payload.scope == "https://www.googleapis.com/auth/cloud-platform"


def test_to_vault_envelope_shape() -> None:
    """to_vault_envelope() returns bytes with 'json_key' (not 'service_account_json')."""
    payload = GoogleServiceAccountPayload(service_account_json=_VALID_SA_JSON_STR)
    envelope_bytes = payload.to_vault_envelope()
    envelope = json.loads(envelope_bytes.decode())

    assert envelope["scheme"] == "google_service_account"
    assert "json_key" in envelope, "Go StoredBlob expects 'json_key', not 'service_account_json'"
    assert "service_account_json" not in envelope, "Raw field name must NOT appear in envelope"
    assert envelope["json_key"] == _VALID_SA_JSON_STR
    assert envelope["scope"] == "https://www.googleapis.com/auth/androidpublisher"


def test_to_vault_envelope_roundtrip() -> None:
    """json_key value in the envelope matches the original service_account_json input."""
    payload = GoogleServiceAccountPayload(service_account_json=_VALID_SA_JSON_STR)
    envelope = json.loads(payload.to_vault_envelope().decode())
    assert json.loads(envelope["json_key"]) == _VALID_SA_JSON


# ---------------------------------------------------------------------------
# Rejection: bad JSON input
# ---------------------------------------------------------------------------


def test_rejects_non_json_string() -> None:
    """Non-JSON string → ValueError with terse message."""
    with pytest.raises(ValueError, match="not valid JSON"):
        GoogleServiceAccountPayload(service_account_json="not-json-at-all")


def test_rejects_json_array() -> None:
    """JSON array (not a dict) → rejected."""
    with pytest.raises(ValueError, match="must be a JSON object"):
        GoogleServiceAccountPayload(service_account_json='["not", "a", "dict"]')


# ---------------------------------------------------------------------------
# Rejection: wrong type field
# ---------------------------------------------------------------------------


def test_rejects_authorized_user_type() -> None:
    """authorized_user blob → rejected; only service_account is accepted."""
    bad = dict(_VALID_SA_JSON)
    bad["type"] = "authorized_user"
    with pytest.raises(ValueError, match="type must be 'service_account'"):
        GoogleServiceAccountPayload(service_account_json=json.dumps(bad))


def test_rejects_missing_type() -> None:
    """Missing type field → rejected."""
    bad = {k: v for k, v in _VALID_SA_JSON.items() if k != "type"}
    with pytest.raises(ValueError, match="type must be 'service_account'"):
        GoogleServiceAccountPayload(service_account_json=json.dumps(bad))


# ---------------------------------------------------------------------------
# Rejection: missing required fields
# ---------------------------------------------------------------------------


def test_rejects_missing_private_key() -> None:
    """Missing private_key → rejected with field name in message."""
    bad = {k: v for k, v in _VALID_SA_JSON.items() if k != "private_key"}
    with pytest.raises(ValueError, match="private_key"):
        GoogleServiceAccountPayload(service_account_json=json.dumps(bad))


def test_rejects_missing_project_id() -> None:
    """Missing project_id → rejected."""
    bad = {k: v for k, v in _VALID_SA_JSON.items() if k != "project_id"}
    with pytest.raises(ValueError, match="project_id"):
        GoogleServiceAccountPayload(service_account_json=json.dumps(bad))


def test_rejects_missing_client_email() -> None:
    """Missing client_email → rejected."""
    bad = {k: v for k, v in _VALID_SA_JSON.items() if k != "client_email"}
    with pytest.raises(ValueError, match="client_email"):
        GoogleServiceAccountPayload(service_account_json=json.dumps(bad))


# ---------------------------------------------------------------------------
# Rejection: invalid field values
# ---------------------------------------------------------------------------


def test_rejects_private_key_without_pem_header() -> None:
    """private_key not starting with -----BEGIN → rejected."""
    bad = dict(_VALID_SA_JSON)
    bad["private_key"] = "MIIB...base64only"
    with pytest.raises(ValueError, match="-----BEGIN"):
        GoogleServiceAccountPayload(service_account_json=json.dumps(bad))


def test_rejects_non_https_token_uri() -> None:
    """HTTP token_uri → rejected (must be https://)."""
    bad = dict(_VALID_SA_JSON)
    bad["token_uri"] = "http://accounts.google.com/token"
    with pytest.raises(ValueError, match="token_uri must start with 'https://'"):
        GoogleServiceAccountPayload(service_account_json=json.dumps(bad))


def test_rejects_client_email_without_at() -> None:
    """client_email with no '@' → rejected."""
    bad = dict(_VALID_SA_JSON)
    bad["client_email"] = "notanemail"
    with pytest.raises(ValueError, match="client_email must contain '@'"):
        GoogleServiceAccountPayload(service_account_json=json.dumps(bad))


# ---------------------------------------------------------------------------
# Rejection: empty scope
# ---------------------------------------------------------------------------


def test_rejects_empty_scope() -> None:
    """Empty scope → rejected."""
    with pytest.raises(ValueError, match="scope must be a non-empty string"):
        GoogleServiceAccountPayload(service_account_json=_VALID_SA_JSON_STR, scope="")


def test_rejects_whitespace_only_scope() -> None:
    """Whitespace-only scope → rejected."""
    with pytest.raises(ValueError, match="scope must be a non-empty string"):
        GoogleServiceAccountPayload(service_account_json=_VALID_SA_JSON_STR, scope="   ")


# ---------------------------------------------------------------------------
# Fingerprint correctness
# ---------------------------------------------------------------------------


def test_json_key_fingerprint_value() -> None:
    """SHA-256[:16] of service_account_json matches expected fingerprint."""
    payload = GoogleServiceAccountPayload(service_account_json=_VALID_SA_JSON_STR)
    expected = hashlib.sha256(_VALID_SA_JSON_STR.encode()).hexdigest()[:16]
    envelope = json.loads(payload.to_vault_envelope().decode())
    actual = hashlib.sha256(envelope["json_key"].encode()).hexdigest()[:16]
    assert actual == expected


# ---------------------------------------------------------------------------
# Log scrubbing: service_account_json must never appear in warning log output
# ---------------------------------------------------------------------------


def test_validation_failure_log_does_not_contain_private_key(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """On validation failure, log records must not contain private_key text."""
    bad = dict(_VALID_SA_JSON)
    bad["token_uri"] = "http://insecure.example.com/token"
    bad_json_str = json.dumps(bad)
    private_key_fragment = "-----BEGIN PRIVATE KEY-----"

    with caplog.at_level(logging.WARNING):
        try:
            GoogleServiceAccountPayload(service_account_json=bad_json_str)
        except Exception:
            pass

    for record in caplog.records:
        assert private_key_fragment not in record.getMessage(), (
            "private_key material must not appear in any log record"
        )
        assert bad["private_key"] not in record.getMessage(), (
            "private_key value must not appear in any log record"
        )


def test_validation_failure_log_does_not_contain_service_account_json(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """On validation failure, the full service_account_json blob is not logged."""
    bad = dict(_VALID_SA_JSON)
    bad["type"] = "authorized_user"
    bad_json_str = json.dumps(bad)

    with caplog.at_level(logging.WARNING):
        try:
            GoogleServiceAccountPayload(service_account_json=bad_json_str)
        except Exception:
            pass

    for record in caplog.records:
        # The full SA JSON blob (which contains the private_key) must not appear.
        assert bad_json_str not in record.getMessage(), (
            "service_account_json blob must not appear in any log record"
        )
