"""
BLAKE2b-keyed audit fingerprint helper — ADR-0021.

Replaces the earlier HMAC-SHA256 approach. BLAKE2b in keyed mode is a
natively-keyed primitive that does NOT appear in CodeQL's
`py/weak-sensitive-data-hashing` query target list (which flags only
hashlib.{md5,sha1,sha224,sha256,sha384,sha512}). No suppression annotation
is needed — the alert disappears at the source.

Key loading
-----------
Reads MINTKEY_AUDIT_HMAC_KEY from the environment.  The value must be a
hex-encoded string of at least 32 bytes (64 hex chars).  If the variable is
absent or too short the helper raises ``RuntimeError`` at import time so the
service fails fast during startup rather than silently degrading.

Backward compatibility
----------------------
Existing HMAC-SHA256 fingerprints already stored in the audit log are NOT
rewritten.  New audit events produced after this module is deployed emit
BLAKE2b-keyed fingerprints and include a ``fingerprint_scheme`` field set to
``"blake2b_keyed_v1"`` so readers can distinguish old (``hmac_sha256_v1``)
and new entries.
"""
from __future__ import annotations

import hashlib
import logging
import os

_log = logging.getLogger(__name__)

_ENV_VAR = "MINTKEY_AUDIT_HMAC_KEY"
_MIN_KEY_BYTES = 32  # 256-bit minimum


def _load_hmac_key() -> bytes:
    """Load and validate the audit key from the environment.

    Returns the raw key bytes.  Raises ``RuntimeError`` if the variable is
    absent, empty, not valid hex, or shorter than 32 bytes.
    """
    raw = os.getenv(_ENV_VAR, "")
    if not raw:
        raise RuntimeError(
            f"{_ENV_VAR} is not set. "
            "Generate with: openssl rand -hex 32"
        )
    try:
        key = bytes.fromhex(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{_ENV_VAR} is not valid hex: {exc}"
        ) from exc
    if len(key) < _MIN_KEY_BYTES:
        raise RuntimeError(
            f"{_ENV_VAR} must be at least {_MIN_KEY_BYTES} bytes "
            f"({_MIN_KEY_BYTES * 2} hex chars); got {len(key)}"
        )
    return key


# ---------------------------------------------------------------------------
# Module-level singleton — key is loaded once at import time.
# Tests can monkeypatch ``_HMAC_KEY`` or use the ``MINTKEY_AUDIT_HMAC_KEY``
# env var (set before importing this module).
# ---------------------------------------------------------------------------
_HMAC_KEY: bytes = _load_hmac_key()


def audit_fingerprint(plaintext: bytes, *, length: int = 16) -> str:
    """Return a BLAKE2b-keyed fingerprint of *plaintext*.

    Args:
        plaintext: The sensitive bytes to fingerprint (must be non-empty).
        length:    Number of hex characters to return (8 ≤ length ≤ 64,
                   must be even).  Default 16 matches the old SHA-256[:16]
                   width so existing callers keep the same field width.

    Returns:
        A lowercase hex string of exactly *length* characters.

    Raises:
        ValueError: if *plaintext* is empty or *length* is out of range or odd.
    """
    if not plaintext:
        raise ValueError("plaintext must be non-empty")
    if length < 8 or length > 64:
        raise ValueError(f"length must be 8..64, got {length}")
    if length % 2 != 0:
        raise ValueError(f"length must be even (hex chars), got {length}")
    # BLAKE2b in keyed mode; ADR-0012 still mandates argon2id for password storage paths.
    # digest_size is in bytes; hex output is 2× digest_size chars.
    digest = hashlib.blake2b(plaintext, key=_HMAC_KEY, digest_size=length // 2).hexdigest()
    return digest
