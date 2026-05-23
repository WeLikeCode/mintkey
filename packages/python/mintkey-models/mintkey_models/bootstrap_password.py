"""
mintkey_models.bootstrap_password — shared decrypt helper for bootstrap admin password.

The bootstrap admin password is written to disk as Fernet ciphertext by the seed-job
(S6 CodeQL fix).  Every Python service that reads admin_password must use this helper
instead of a plain Path.read_text() to avoid handling raw ciphertext as a password.

Usage:
    from mintkey_models.bootstrap_password import read_bootstrap_password

    pw = read_bootstrap_password("/run/secrets/mintkey/bootstrap-secrets/admin_password")

Environment:
    MINTKEY_BOOTSTRAP_KEK — URL-safe base64-encoded 32-byte Fernet key.
        Required at runtime for any caller that reads the encrypted file.
        Generate with:
            python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"

Source: S6 CodeQL cleartext-storage fix (strike-2 scope expansion).
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from cryptography.fernet import Fernet


class BootstrapPasswordError(Exception):
    """Raised when the bootstrap password file cannot be decrypted or is missing."""


def _get_fernet() -> "Fernet":
    """Return a Fernet instance using MINTKEY_BOOTSTRAP_KEK.

    Deferred import keeps the cryptography dependency optional for callers
    that only use other mintkey_models modules.

    Raises:
        BootstrapPasswordError: if the env var is missing or the key is malformed.
    """
    try:
        from cryptography.fernet import Fernet  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise BootstrapPasswordError(
            "cryptography package is not installed. "
            "Add cryptography>=42.0 to your service dependencies."
        ) from exc

    kek_raw = os.getenv("MINTKEY_BOOTSTRAP_KEK")
    if not kek_raw:
        raise BootstrapPasswordError(
            "MINTKEY_BOOTSTRAP_KEK env var is not set. "
            "Set it to the Fernet key used by the seed-job. "
            "Generate one with: "
            "python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    try:
        return Fernet(kek_raw.encode())
    except (ValueError, Exception) as exc:
        raise BootstrapPasswordError(
            f"MINTKEY_BOOTSTRAP_KEK is not a valid Fernet key: {exc}"
        ) from exc


def read_bootstrap_password_bytes(path: str | Path) -> bytes:
    """Read and decrypt the Fernet-encrypted bootstrap admin password file.

    Args:
        path: path to the admin_password file (ciphertext).

    Returns:
        The decrypted password as bytes.

    Raises:
        BootstrapPasswordError: if the file is missing, MINTKEY_BOOTSTRAP_KEK is not
            set, the key is malformed, or the ciphertext is invalid/tampered.
    """
    p = Path(path)
    if not p.exists():
        raise BootstrapPasswordError(
            f"Bootstrap password file not found: {p}. "
            "Ensure the seed-job has completed successfully and the "
            "bootstrap-secrets volume is mounted."
        )

    ciphertext = p.read_bytes()
    fernet = _get_fernet()

    try:
        from cryptography.fernet import InvalidToken  # noqa: PLC0415
    except ImportError as exc:  # pragma: no cover
        raise BootstrapPasswordError(
            "cryptography package is not installed."
        ) from exc

    try:
        return fernet.decrypt(ciphertext)
    except InvalidToken as exc:
        raise BootstrapPasswordError(
            f"Failed to decrypt bootstrap password from {p}: invalid ciphertext or wrong KEK. "
            "Verify MINTKEY_BOOTSTRAP_KEK matches the key used by the seed-job."
        ) from exc


def read_bootstrap_password(path: str | Path) -> str:
    """Read and decrypt the Fernet-encrypted bootstrap admin password file.

    Args:
        path: path to the admin_password file (ciphertext).

    Returns:
        The decrypted password as a str (UTF-8, stripped of trailing whitespace).

    Raises:
        BootstrapPasswordError: if the file is missing, MINTKEY_BOOTSTRAP_KEK is not
            set, the key is malformed, or the ciphertext is invalid/tampered.
    """
    return read_bootstrap_password_bytes(path).decode().strip()
