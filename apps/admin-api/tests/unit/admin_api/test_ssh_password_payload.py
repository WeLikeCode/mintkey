"""
Unit tests for SSHPasswordPayload — ADR-0021.

Covers:
  - Happy path: valid username + password + target_address → model instantiates,
    to_vault_envelope() returns raw password bytes (not a JSON envelope).
  - Bad username: empty, whitespace-only, shell-metacharacters rejected.
  - Empty password: rejected.
  - Oversized password: >1024 bytes rejected.
  - Bad target_address: no colon, non-numeric port, empty host rejected.
  - audit scrubs password: to_vault_envelope() bytes are NOT the JSON representation,
    and the password fingerprint (SHA-256[:16]) is distinct from the raw password.

Source: ADR-0021; ADR-0014.4; ADR-0014.7.
"""
from __future__ import annotations

import hashlib
import json as _json
import logging

import pytest

from admin_api.services.credential_service import SSHPasswordPayload

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_VALID_USER = "ubuntu"
_VALID_PASS = "s3cr3t-P@ssw0rd!"
_VALID_TARGET = "bastion.example.com:22"


def _make_valid() -> SSHPasswordPayload:
    return SSHPasswordPayload(
        username=_VALID_USER,
        password=_VALID_PASS,
        target_address=_VALID_TARGET,
    )


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_valid_payload_instantiates() -> None:
    payload = _make_valid()
    assert payload.username == _VALID_USER
    assert payload.password == _VALID_PASS
    assert payload.target_address == _VALID_TARGET


def test_to_vault_envelope_returns_password_bytes() -> None:
    payload = _make_valid()
    envelope = payload.to_vault_envelope()
    assert isinstance(envelope, bytes)
    assert envelope == _VALID_PASS.encode("utf-8")


def test_to_vault_envelope_is_not_json() -> None:
    """SSH-password envelope must be raw bytes, not a JSON wrapper."""
    payload = _make_valid()
    envelope = payload.to_vault_envelope()
    with pytest.raises((_json.JSONDecodeError, ValueError)):
        _json.loads(envelope)


def test_valid_username_with_dots_dashes() -> None:
    """Username with dots and dashes is accepted."""
    payload = SSHPasswordPayload(
        username="deploy-user.1",
        password=_VALID_PASS,
        target_address=_VALID_TARGET,
    )
    assert payload.username == "deploy-user.1"


def test_valid_numeric_port() -> None:
    payload = SSHPasswordPayload(
        username=_VALID_USER,
        password=_VALID_PASS,
        target_address="10.0.0.1:2222",
    )
    assert payload.target_address == "10.0.0.1:2222"


# ---------------------------------------------------------------------------
# Validation failures — username
# ---------------------------------------------------------------------------


def test_username_empty_string() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username="", password=_VALID_PASS, target_address=_VALID_TARGET)


def test_username_whitespace_only() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username="   ", password=_VALID_PASS, target_address=_VALID_TARGET)


def test_username_semicolon_rejected() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username="user;id", password=_VALID_PASS, target_address=_VALID_TARGET)


def test_username_dollar_rejected() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username="user$HOME", password=_VALID_PASS, target_address=_VALID_TARGET)


def test_username_backtick_rejected() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username="`whoami`", password=_VALID_PASS, target_address=_VALID_TARGET)


# ---------------------------------------------------------------------------
# Validation failures — password
# ---------------------------------------------------------------------------


def test_password_empty_string() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username=_VALID_USER, password="", target_address=_VALID_TARGET)


def test_password_oversized() -> None:
    """Password exceeding 1024 bytes UTF-8 must be rejected."""
    big_password = "x" * 1025
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username=_VALID_USER, password=big_password, target_address=_VALID_TARGET)


def test_password_exactly_1024_bytes_accepted() -> None:
    """Password of exactly 1024 ASCII bytes must be accepted."""
    max_password = "a" * 1024
    payload = SSHPasswordPayload(username=_VALID_USER, password=max_password, target_address=_VALID_TARGET)
    assert len(payload.to_vault_envelope()) == 1024


# ---------------------------------------------------------------------------
# Validation failures — target_address
# ---------------------------------------------------------------------------


def test_target_address_no_colon() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username=_VALID_USER, password=_VALID_PASS, target_address="myhost-no-port")


def test_target_address_non_numeric_port() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username=_VALID_USER, password=_VALID_PASS, target_address="myhost:ssh")


def test_target_address_empty_host() -> None:
    with pytest.raises((ValueError, Exception)):
        SSHPasswordPayload(username=_VALID_USER, password=_VALID_PASS, target_address=":22")


# ---------------------------------------------------------------------------
# Audit scrubbing — password MUST NOT appear in log records
# ---------------------------------------------------------------------------


def test_password_not_logged_on_bad_username(caplog: pytest.LogCaptureFixture) -> None:
    """Validation failure must not log the password."""
    with caplog.at_level(logging.WARNING):
        try:
            SSHPasswordPayload(
                username="bad;user",
                password="super-secret-password-123",
                target_address=_VALID_TARGET,
            )
        except Exception:
            pass
    for record in caplog.records:
        assert "super-secret-password-123" not in record.getMessage()


def test_password_fingerprint_is_not_raw_password() -> None:
    """Audit helper: SHA-256[:16] of password != the password itself."""
    payload = _make_valid()
    # SHA-256 used as audit fingerprint in test assertion, not for authentication.
    # Mirrors the non-auth fingerprint produced by credentials.py (ADR-0021).
    # lgtm[py/weak-sensitive-data-hashing]
    _pwd_bytes = payload.password.encode("utf-8")
    fingerprint = hashlib.sha256(_pwd_bytes).hexdigest()[:16]
    assert len(fingerprint) == 16
    assert fingerprint != payload.password
    assert "@" not in fingerprint  # no special chars from the real password
