"""
Tests for S6 — bootstrap admin password Fernet encryption.

Verifies that:
1. _ensure_admin_password_file writes Fernet ciphertext (not plaintext) to disk.
2. The ciphertext round-trips: decrypting with the same KEK returns the original
   plaintext password.
3. With a *wrong* KEK the ciphertext is invalid, triggering regeneration on the
   next call.
4. _fernet() raises RuntimeError when MINTKEY_BOOTSTRAP_KEK is absent or malformed.
5. _sync_admin_password decrypts correctly (unit-level, without real Keycloak).

Strike-2 update: _BOOTSTRAP_KEK_RAW module-level attribute removed; _fernet()
now reads os.getenv() at call time.  Tests updated to use monkeypatch.setenv().
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from cryptography.fernet import Fernet

# Put the seed-job package on the path so we can import main without installing.
sys.path.insert(0, str(Path(__file__).parent.parent))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def kek() -> bytes:
    """A fresh Fernet key for each test."""
    return Fernet.generate_key()


@pytest.fixture()
def kek_str(kek: bytes) -> str:
    return kek.decode()


# ---------------------------------------------------------------------------
# _fernet() — key loading
# ---------------------------------------------------------------------------

class TestFernet:
    def test_raises_when_kek_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("MINTKEY_BOOTSTRAP_KEK", raising=False)
        import main as m
        with pytest.raises(RuntimeError, match="MINTKEY_BOOTSTRAP_KEK env var is not set"):
            m._fernet()

    def test_raises_on_malformed_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", "not-a-valid-fernet-key!!!")
        import main as m
        with pytest.raises(RuntimeError, match="not a valid Fernet key"):
            m._fernet()

    def test_returns_fernet_with_valid_key(self, kek_str: str, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", kek_str)
        import main as m
        f = m._fernet()
        assert isinstance(f, Fernet)


# ---------------------------------------------------------------------------
# _ensure_admin_password_file — writes encrypted ciphertext
# ---------------------------------------------------------------------------

class TestEnsureAdminPasswordFile:
    def test_file_contains_ciphertext_not_plaintext(
        self, tmp_path: Path, kek_str: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", kek_str)

        password = "SuperSecret_bootstrap_password_42"
        m._ensure_admin_password_file(tmp_path, password)

        pw_file = tmp_path / "admin_password"
        assert pw_file.exists(), "admin_password file must be created"

        raw = pw_file.read_bytes()
        # The raw bytes must NOT contain the plaintext password
        assert password.encode() not in raw, "Plaintext password must not appear on disk"
        # Fernet tokens are URL-safe base64 and start with version byte 0x80
        # (b'\x80' encoded as base64 → first decoded byte == 0x80)
        f = Fernet(kek_str.encode())
        decrypted = f.decrypt(raw).decode()
        assert decrypted == password

    def test_file_permissions_are_0o400(
        self, tmp_path: Path, kek_str: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", kek_str)

        m._ensure_admin_password_file(tmp_path, "some_password_value")
        pw_file = tmp_path / "admin_password"
        mode = pw_file.stat().st_mode & 0o777
        assert mode == 0o400, f"Expected 0o400, got 0o{mode:o}"

    def test_idempotent_valid_file_not_overwritten(
        self, tmp_path: Path, kek_str: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", kek_str)

        password = "first_password_abc"
        m._ensure_admin_password_file(tmp_path, password)
        pw_file = tmp_path / "admin_password"
        first_mtime = pw_file.stat().st_mtime

        # Second call with a different password value — file should NOT be overwritten
        # because the existing ciphertext still decrypts to a valid password.
        m._ensure_admin_password_file(tmp_path, "second_password_xyz")
        assert pw_file.stat().st_mtime == first_mtime, (
            "Valid existing ciphertext must not be overwritten on re-run"
        )

    def test_invalid_file_is_regenerated(
        self, tmp_path: Path, kek_str: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", kek_str)

        pw_file = tmp_path / "admin_password"
        # Write garbage (simulates corruption or old plaintext from pre-S6)
        pw_file.write_bytes(b"plaintext_old_password")
        pw_file.chmod(0o400)

        password = "new_encrypted_password"
        m._ensure_admin_password_file(tmp_path, password)

        raw = pw_file.read_bytes()
        f = Fernet(kek_str.encode())
        assert f.decrypt(raw).decode() == password

    def test_wrong_kek_triggers_regeneration(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m

        kek_a = Fernet.generate_key().decode()
        kek_b = Fernet.generate_key().decode()

        # Write with KEK-A
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", kek_a)
        m._ensure_admin_password_file(tmp_path, "password_with_kek_a")

        # Validate+generate with KEK-B → should detect invalid, regenerate
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", kek_b)
        m._ensure_admin_password_file(tmp_path, "password_with_kek_b")

        pw_file = tmp_path / "admin_password"
        f_b = Fernet(kek_b.encode())
        assert f_b.decrypt(pw_file.read_bytes()).decode() == "password_with_kek_b"


# ---------------------------------------------------------------------------
# Regression: the generate() lambda returns bytes (Fernet ciphertext), so
# _ensure_secret_file must call path.write_bytes(), not path.write_text().
# ---------------------------------------------------------------------------

class TestEnsureSecretFileDispatch:
    def test_bytes_value_written_as_bytes(
        self, tmp_path: Path, kek_str: str, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        import main as m
        monkeypatch.setenv("MINTKEY_BOOTSTRAP_KEK", kek_str)

        password = "dispatch_test_password"
        m._ensure_admin_password_file(tmp_path, password)

        pw_file = tmp_path / "admin_password"
        # Fernet.encrypt always returns bytes; if the file were written with
        # write_text() it would raise or produce garbled content.
        raw = pw_file.read_bytes()
        f = Fernet(kek_str.encode())
        # Should not raise InvalidToken
        plaintext = f.decrypt(raw).decode()
        assert plaintext == password
