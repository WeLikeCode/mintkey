"""
Unit tests for the SSH path of test_service_transient — OPS-T / ADR-0021.

Covers:
  1. test_ssh_private_key_happy_path     — asyncssh.connect returns fake conn → ok=True, status_code=200
  2. test_ssh_password_happy_path        — same with password cred
  3. test_ssh_private_key_bad_key        — PermissionDenied → ok=False, status_code=401
  4. test_ssh_password_bad_password      — PermissionDenied, password absent from response body
  5. test_ssh_timeout                    — asyncio.TimeoutError → ok=False, status_code=504
  6. test_ssh_connect_refused            — ConnectionRefusedError → ok=False, status_code=502
  7. test_ssh_no_private_key_field       — malformed cred (missing field) → status_code=400
  8. test_ssh_credential_never_logged    — log records must not contain key or password material

Source: OPS-T; ADR-0021; ADR-0014.4.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from admin_api.api._ssh_test import test_ssh_credential as _test_ssh_credential

# ---------------------------------------------------------------------------
# Shared fixtures / helpers
# ---------------------------------------------------------------------------

_FAKE_PEM = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAA fake key material for unit tests\n"
    "-----END OPENSSH PRIVATE KEY-----\n"
)

_HOST = "ssh-target"
_PORT = 2222
_TARGET = f"{_HOST}:{_PORT}"
_BASE_URL = f"ssh://{_HOST}:{_PORT}"
_USER = "testuser"
_PASS = "super-secret-password-xyz"


def _pk_cred(**overrides: Any) -> str:
    cred: dict[str, Any] = {
        "scheme": "ssh_private_key",
        "private_key_pem": _FAKE_PEM,
        "ssh_user": _USER,
        "target_address": _TARGET,
    }
    cred.update(overrides)
    return json.dumps(cred)


def _pw_cred(**overrides: Any) -> str:
    cred: dict[str, Any] = {
        "scheme": "ssh_password",
        "username": _USER,
        "password": _PASS,
        "target_address": _TARGET,
    }
    cred.update(overrides)
    return json.dumps(cred)


def _make_fake_conn() -> MagicMock:
    """Return a minimal asyncssh connection mock that satisfies context-manager + run."""
    conn = MagicMock()
    conn.__aenter__ = AsyncMock(return_value=conn)
    conn.__aexit__ = AsyncMock(return_value=False)
    conn.run = AsyncMock(return_value=MagicMock(exit_status=0))
    return conn


# ---------------------------------------------------------------------------
# 1. ssh_private_key happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_private_key_happy_path() -> None:
    fake_conn = _make_fake_conn()
    fake_key = MagicMock()

    with (
        patch("asyncssh.connect", return_value=fake_conn),
        patch("asyncssh.import_private_key", return_value=fake_key),
    ):
        result = await _test_ssh_credential(
            scheme="ssh_private_key",
            credential_value=_pk_cred(),
            base_url=_BASE_URL,
            timeout_ms=5000,
        )

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert "SSH connection succeeded" in result["response_body_truncated"]
    assert _USER in result["response_body_truncated"]
    assert _FAKE_PEM not in result["response_body_truncated"]


# ---------------------------------------------------------------------------
# 2. ssh_password happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_password_happy_path() -> None:
    fake_conn = _make_fake_conn()

    with patch("asyncssh.connect", return_value=fake_conn):
        result = await _test_ssh_credential(
            scheme="ssh_password",
            credential_value=_pw_cred(),
            base_url=_BASE_URL,
            timeout_ms=5000,
        )

    assert result["ok"] is True
    assert result["status_code"] == 200
    assert "SSH connection succeeded" in result["response_body_truncated"]
    assert _USER in result["response_body_truncated"]
    assert _PASS not in result["response_body_truncated"]


# ---------------------------------------------------------------------------
# 3. ssh_private_key — bad key (PermissionDenied)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_private_key_bad_key() -> None:
    import asyncssh

    fake_key = MagicMock()

    with (
        patch("asyncssh.connect", side_effect=asyncssh.PermissionDenied("publickey")),
        patch("asyncssh.import_private_key", return_value=fake_key),
    ):
        result = await _test_ssh_credential(
            scheme="ssh_private_key",
            credential_value=_pk_cred(),
            base_url=_BASE_URL,
            timeout_ms=5000,
        )

    assert result["ok"] is False
    assert result["status_code"] == 401
    assert "authentication failed" in result["response_body_truncated"].lower()


# ---------------------------------------------------------------------------
# 4. ssh_password — wrong password, verify no leak in response body
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_password_bad_password() -> None:
    import asyncssh

    with patch("asyncssh.connect", side_effect=asyncssh.PermissionDenied("password")):
        result = await _test_ssh_credential(
            scheme="ssh_password",
            credential_value=_pw_cred(),
            base_url=_BASE_URL,
            timeout_ms=5000,
        )

    assert result["ok"] is False
    assert result["status_code"] == 401
    # CRITICAL: password must NEVER appear in any response field
    body = result.get("response_body_truncated", "")
    assert _PASS not in body, f"Password leaked into response body: {body!r}"
    # Also check no other field leaks it
    for _k, v in result.items():
        assert _PASS not in str(v), f"Password leaked in field {_k!r}: {v!r}"


# ---------------------------------------------------------------------------
# 5. Timeout
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_timeout() -> None:
    fake_key = MagicMock()

    with (
        patch("asyncssh.connect", side_effect=asyncio.TimeoutError()),
        patch("asyncssh.import_private_key", return_value=fake_key),
    ):
        result = await _test_ssh_credential(
            scheme="ssh_private_key",
            credential_value=_pk_cred(),
            base_url=_BASE_URL,
            timeout_ms=5000,
        )

    assert result["ok"] is False
    assert result["status_code"] == 504
    assert "timed out" in result["response_body_truncated"].lower()


# ---------------------------------------------------------------------------
# 6. Connection refused
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_connect_refused() -> None:
    fake_key = MagicMock()

    with (
        patch("asyncssh.connect", side_effect=ConnectionRefusedError("Connection refused")),
        patch("asyncssh.import_private_key", return_value=fake_key),
    ):
        result = await _test_ssh_credential(
            scheme="ssh_private_key",
            credential_value=_pk_cred(),
            base_url=_BASE_URL,
            timeout_ms=5000,
        )

    assert result["ok"] is False
    assert result["status_code"] == 502
    assert "connect failed" in result["response_body_truncated"].lower()


# ---------------------------------------------------------------------------
# 7. Malformed credential — missing private_key_pem field
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_no_private_key_field() -> None:
    # Remove private_key_pem — should be caught before asyncssh is touched
    bad_cred = json.dumps({
        "scheme": "ssh_private_key",
        # private_key_pem intentionally absent
        "ssh_user": _USER,
        "target_address": _TARGET,
    })

    result = await _test_ssh_credential(
        scheme="ssh_private_key",
        credential_value=bad_cred,
        base_url=_BASE_URL,
        timeout_ms=5000,
    )

    assert result["ok"] is False
    assert result["status_code"] == 400
    assert "private_key_pem" in result["response_body_truncated"]


# ---------------------------------------------------------------------------
# 8. Credential material never appears in log records
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_ssh_credential_never_logged(caplog: pytest.LogCaptureFixture) -> None:
    """private_key_pem and password must NEVER appear in any log record."""
    import asyncssh

    fake_key = MagicMock()

    with caplog.at_level(logging.DEBUG, logger="admin_api"):
        # Test with ssh_private_key — simulate a connect failure
        with (
            patch("asyncssh.connect", side_effect=asyncssh.PermissionDenied("publickey")),
            patch("asyncssh.import_private_key", return_value=fake_key),
        ):
            await _test_ssh_credential(
                scheme="ssh_private_key",
                credential_value=_pk_cred(),
                base_url=_BASE_URL,
                timeout_ms=5000,
            )

        # Test with ssh_password — simulate a connect failure
        with patch("asyncssh.connect", side_effect=asyncssh.PermissionDenied("password")):
            await _test_ssh_credential(
                scheme="ssh_password",
                credential_value=_pw_cred(),
                base_url=_BASE_URL,
                timeout_ms=5000,
            )

    # Check every log record for credential leaks
    pem_marker = "OPENSSH PRIVATE KEY"  # distinctive substring from our fake PEM
    for record in caplog.records:
        msg = record.getMessage()
        assert pem_marker not in msg, f"PEM material leaked in log: {msg!r}"
        assert _FAKE_PEM not in msg, f"Full PEM leaked in log: {msg!r}"
        assert _PASS not in msg, f"Password leaked in log: {msg!r}"
