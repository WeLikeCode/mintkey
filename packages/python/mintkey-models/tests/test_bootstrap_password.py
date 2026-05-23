"""
Unit tests for mintkey_models.bootstrap_password.

Covers:
    1. Happy path: read_bootstrap_password returns correct plaintext string.
    2. Happy path: read_bootstrap_password_bytes returns correct plaintext bytes.
    3. Missing KEK raises BootstrapPasswordError with clear message.
    4. Malformed KEK raises BootstrapPasswordError with clear message.
    5. Bad ciphertext (tampered) raises BootstrapPasswordError with clear message.
    6. Missing file raises BootstrapPasswordError with clear message.
    7. Wrong KEK raises BootstrapPasswordError with clear message.
    8. Return type is stripped (no trailing newline).

Source: S6 CodeQL cleartext-storage fix (strike-2).
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from cryptography.fernet import Fernet


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_encrypted(tmp_path: Path, plaintext: str, key: bytes) -> Path:
    """Write a Fernet-encrypted file and return its path."""
    f = Fernet(key)
    p = tmp_path / "admin_password"
    p.write_bytes(f.encrypt(plaintext.encode()))
    return p


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


class TestReadBootstrapPassword:
    """read_bootstrap_password happy-path and error cases."""

    def test_happy_path_returns_plaintext_str(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Encrypted file + correct KEK → correct plaintext string."""
        key = Fernet.generate_key()
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", key.decode())
        pw_file = _write_encrypted(tmp_path, "super-secret-123", key)

        from mintkey_models.bootstrap_password import read_bootstrap_password
        result = read_bootstrap_password(pw_file)
        assert result == "super-secret-123"
        assert isinstance(result, str)

    def test_happy_path_strips_trailing_whitespace(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """strip() is applied so a newline-terminated plaintext is returned clean."""
        key = Fernet.generate_key()
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", key.decode())
        f = Fernet(key)
        pw_file = tmp_path / "admin_password"
        pw_file.write_bytes(f.encrypt(b"my-password\n"))

        from mintkey_models.bootstrap_password import read_bootstrap_password
        result = read_bootstrap_password(pw_file)
        assert result == "my-password"

    def test_accepts_path_object(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Path object and str path are both accepted."""
        key = Fernet.generate_key()
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", key.decode())
        pw_file = _write_encrypted(tmp_path, "password-abc", key)

        from mintkey_models.bootstrap_password import read_bootstrap_password
        # str path
        assert read_bootstrap_password(str(pw_file)) == "password-abc"
        # Path path
        assert read_bootstrap_password(pw_file) == "password-abc"


class TestReadBootstrapPasswordBytes:
    """read_bootstrap_password_bytes happy path."""

    def test_returns_bytes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Returns raw bytes — useful for callers that need non-str input."""
        key = Fernet.generate_key()
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", key.decode())
        pw_file = _write_encrypted(tmp_path, "bytes-password-xyz", key)

        from mintkey_models.bootstrap_password import read_bootstrap_password_bytes
        result = read_bootstrap_password_bytes(pw_file)
        assert isinstance(result, bytes)
        assert result == b"bytes-password-xyz"


class TestMissingKek:
    """Tests for missing / malformed MINTKEY_BOOTSTRAP_KEK."""

    def test_missing_kek_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No MINTKEY_BOOTSTRAP_KEK → BootstrapPasswordError with clear message."""
        monkeypatch.delenv("MINTKEY_BOOTSTRAP_KEK", raising=False)
        key = Fernet.generate_key()
        pw_file = _write_encrypted(tmp_path, "irrelevant", key)

        from mintkey_models.bootstrap_password import (
            BootstrapPasswordError,
            read_bootstrap_password,
        )
        with pytest.raises(BootstrapPasswordError, match="MINTKEY_BOOTSTRAP_KEK env var is not set"):
            read_bootstrap_password(pw_file)

    def test_malformed_kek_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Gibberish KEK → BootstrapPasswordError explaining key is malformed."""
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", "not-a-valid-fernet-key!!!")
        key = Fernet.generate_key()
        pw_file = _write_encrypted(tmp_path, "irrelevant", key)

        from mintkey_models.bootstrap_password import (
            BootstrapPasswordError,
            read_bootstrap_password,
        )
        with pytest.raises(BootstrapPasswordError, match="not a valid Fernet key"):
            read_bootstrap_password(pw_file)

    def test_wrong_kek_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Correct Fernet key but different from the one used to encrypt → BootstrapPasswordError."""
        encrypt_key = Fernet.generate_key()
        wrong_key = Fernet.generate_key()
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", wrong_key.decode())
        pw_file = _write_encrypted(tmp_path, "some-password", encrypt_key)

        from mintkey_models.bootstrap_password import (
            BootstrapPasswordError,
            read_bootstrap_password,
        )
        with pytest.raises(BootstrapPasswordError, match="invalid ciphertext or wrong KEK"):
            read_bootstrap_password(pw_file)


class TestBadCiphertext:
    """Tests for invalid ciphertext scenarios."""

    def test_tampered_ciphertext_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Corrupted ciphertext → BootstrapPasswordError with operator-friendly message."""
        key = Fernet.generate_key()
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", key.decode())
        pw_file = tmp_path / "admin_password"
        pw_file.write_bytes(b"this-is-not-fernet-ciphertext")

        from mintkey_models.bootstrap_password import (
            BootstrapPasswordError,
            read_bootstrap_password,
        )
        with pytest.raises(BootstrapPasswordError, match="Failed to decrypt"):
            read_bootstrap_password(pw_file)

    def test_plaintext_file_rejected(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A legacy plaintext admin_password file is rejected, not silently read."""
        key = Fernet.generate_key()
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", key.decode())
        pw_file = tmp_path / "admin_password"
        pw_file.write_text("cleartext-password")

        from mintkey_models.bootstrap_password import (
            BootstrapPasswordError,
            read_bootstrap_password,
        )
        with pytest.raises(BootstrapPasswordError, match="Failed to decrypt"):
            read_bootstrap_password(pw_file)


class TestMissingFile:
    """Tests for missing password file."""

    def test_missing_file_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-existent file → BootstrapPasswordError with clear path in the message."""
        key = Fernet.generate_key()
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", key.decode())
        pw_file = tmp_path / "admin_password"
        # Do not write the file

        from mintkey_models.bootstrap_password import (
            BootstrapPasswordError,
            read_bootstrap_password,
        )
        with pytest.raises(BootstrapPasswordError, match="Bootstrap password file not found"):
            read_bootstrap_password(pw_file)

    def test_missing_file_message_contains_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Error message contains the attempted path so operators can diagnose quickly."""
        key = Fernet.generate_key()
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", key.decode())
        pw_file = tmp_path / "admin_password"

        from mintkey_models.bootstrap_password import (
            BootstrapPasswordError,
            read_bootstrap_password,
        )
        with pytest.raises(BootstrapPasswordError) as exc_info:
            read_bootstrap_password(pw_file)
        assert str(pw_file) in str(exc_info.value)
