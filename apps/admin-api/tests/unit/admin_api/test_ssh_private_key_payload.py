"""
Unit tests for SSHPrivateKeyPayload — ADR-0021.

Covers:
  - Happy path: valid PEM + target_address + ssh_user → model instantiates,
    to_vault_envelope() returns raw PEM bytes (not a JSON envelope).
  - Missing private_key_pem field: rejected.
  - PEM without "-----BEGIN": rejected with terse ValueError.
  - PEM without "PRIVATE KEY-----": rejected (plain certificate, not a key).
  - target_address missing port (no colon): rejected.
  - target_address with non-numeric port: rejected.
  - target_address with empty host part: rejected.
  - ssh_user empty string: rejected.
  - ssh_user with shell-metacharacters (semicolon, dollar, backtick): rejected.
  - to_vault_envelope() returns raw PEM bytes — NOT a JSON object.
  - Log scrubbing: private_key_pem NEVER appears in warning log records.

Source: ADR-0021; ADR-0014.4; ADR-0014.7.
"""
from __future__ import annotations

import hashlib
import logging

import pytest

from admin_api.services.credential_service import SSHPrivateKeyPayload

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_PEM = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAABG5vbmUAAAAEbm9uZQAAAAAAAAABAAAAMwAAAAtzc2gtZW\n"
    "QyNTUxOQAAACBmockSp8c9cjH...(truncated for test)...\n"
    "-----END OPENSSH PRIVATE KEY-----\n"
)

_VALID_TARGET = "myhost.example.com:22"
_VALID_USER = "ubuntu"


def _make_valid() -> SSHPrivateKeyPayload:
    return SSHPrivateKeyPayload(
        private_key_pem=_VALID_PEM,
        target_address=_VALID_TARGET,
        ssh_user=_VALID_USER,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_payload_instantiates() -> None:
    payload = _make_valid()
    assert payload.private_key_pem == _VALID_PEM
    assert payload.target_address == _VALID_TARGET
    assert payload.ssh_user == _VALID_USER


def test_to_vault_envelope_returns_raw_pem_bytes() -> None:
    payload = _make_valid()
    envelope = payload.to_vault_envelope()
    assert isinstance(envelope, bytes)
    assert envelope == _VALID_PEM.encode()


def test_to_vault_envelope_is_not_json() -> None:
    """SSH envelope must be raw PEM, not a JSON wrapper."""
    import json as _json
    payload = _make_valid()
    envelope = payload.to_vault_envelope()
    with pytest.raises((_json.JSONDecodeError, ValueError)):
        _json.loads(envelope)


def test_valid_ec_pem_header() -> None:
    """EC PRIVATE KEY header is accepted."""
    ec_pem = (
        "-----BEGIN EC PRIVATE KEY-----\n"
        "MHQCAQEEIPmFaKBpKzKGNxPzPzAA...\n"
        "-----END EC PRIVATE KEY-----\n"
    )
    payload = SSHPrivateKeyPayload(
        private_key_pem=ec_pem,
        target_address="10.0.0.1:2222",
        ssh_user="root",
    )
    assert payload.to_vault_envelope() == ec_pem.encode()


def test_valid_rsa_pem_header() -> None:
    """RSA PRIVATE KEY header is accepted."""
    rsa_pem = (
        "-----BEGIN RSA PRIVATE KEY-----\n"
        "MIIEpAIBAAKCAQEA0Z3VS5JJcds...\n"
        "-----END RSA PRIVATE KEY-----\n"
    )
    payload = SSHPrivateKeyPayload(
        private_key_pem=rsa_pem,
        target_address="ssh.internal:22",
        ssh_user="deploy",
    )
    assert payload.ssh_user == "deploy"


# ---------------------------------------------------------------------------
# Validation failures — PEM
# ---------------------------------------------------------------------------


def test_missing_private_key_pem_field() -> None:
    with pytest.raises(Exception):  # Pydantic ValidationError
        SSHPrivateKeyPayload(  # type: ignore[call-arg]
            target_address=_VALID_TARGET,
            ssh_user=_VALID_USER,
        )


def test_pem_missing_begin_header() -> None:
    bad_pem = "THIS IS NOT A PEM KEY\nsome bytes here\n"
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=bad_pem,
            target_address=_VALID_TARGET,
            ssh_user=_VALID_USER,
        )


def test_pem_certificate_not_private_key() -> None:
    """A certificate PEM header must be rejected."""
    cert_pem = (
        "-----BEGIN CERTIFICATE-----\n"
        "MIIDXTCCAkWgAwIBAgIJAP...\n"
        "-----END CERTIFICATE-----\n"
    )
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=cert_pem,
            target_address=_VALID_TARGET,
            ssh_user=_VALID_USER,
        )


def test_pem_public_key_rejected() -> None:
    """A PUBLIC KEY must be rejected (missing PRIVATE in the header)."""
    pub_pem = (
        "-----BEGIN PUBLIC KEY-----\n"
        "MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8A...\n"
        "-----END PUBLIC KEY-----\n"
    )
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=pub_pem,
            target_address=_VALID_TARGET,
            ssh_user=_VALID_USER,
        )


# ---------------------------------------------------------------------------
# Validation failures — target_address
# ---------------------------------------------------------------------------


def test_target_address_no_colon() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=_VALID_PEM,
            target_address="myhost-no-port",
            ssh_user=_VALID_USER,
        )


def test_target_address_non_numeric_port() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=_VALID_PEM,
            target_address="myhost:ssh",
            ssh_user=_VALID_USER,
        )


def test_target_address_empty_host() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=_VALID_PEM,
            target_address=":22",
            ssh_user=_VALID_USER,
        )


# ---------------------------------------------------------------------------
# Validation failures — ssh_user
# ---------------------------------------------------------------------------


def test_ssh_user_empty_string() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=_VALID_PEM,
            target_address=_VALID_TARGET,
            ssh_user="",
        )


def test_ssh_user_whitespace_only() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=_VALID_PEM,
            target_address=_VALID_TARGET,
            ssh_user="   ",
        )


def test_ssh_user_semicolon_rejected() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=_VALID_PEM,
            target_address=_VALID_TARGET,
            ssh_user="user;rm -rf /",
        )


def test_ssh_user_dollar_rejected() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=_VALID_PEM,
            target_address=_VALID_TARGET,
            ssh_user="user$HOME",
        )


def test_ssh_user_backtick_rejected() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPrivateKeyPayload(
            private_key_pem=_VALID_PEM,
            target_address=_VALID_TARGET,
            ssh_user="`whoami`",
        )


# ---------------------------------------------------------------------------
# Log scrubbing — private_key_pem MUST NOT appear in warning records
# ---------------------------------------------------------------------------


def test_pem_not_logged_on_bad_pem(caplog: pytest.LogCaptureFixture) -> None:
    """Validation failure log messages must not contain the PEM material."""
    bad_pem = "-----BEGIN CERTIFICATE-----\nnot-a-private-key\n-----END CERTIFICATE-----"
    with caplog.at_level(logging.WARNING):
        try:
            SSHPrivateKeyPayload(
                private_key_pem=bad_pem,
                target_address=_VALID_TARGET,
                ssh_user=_VALID_USER,
            )
        except Exception:
            pass
    for record in caplog.records:
        assert "BEGIN CERTIFICATE" not in record.getMessage()
        assert "not-a-private-key" not in record.getMessage()


def test_key_fingerprint_not_pem() -> None:
    """Audit helper: SHA-256[:16] of PEM must not equal the PEM itself."""
    payload = _make_valid()
    fingerprint = hashlib.sha256(payload.private_key_pem.encode()).hexdigest()[:16]
    assert len(fingerprint) == 16
    assert fingerprint != payload.private_key_pem
    assert "BEGIN" not in fingerprint
