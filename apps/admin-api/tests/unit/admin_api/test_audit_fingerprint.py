"""
Unit tests for audit_fingerprint helper — ADR-0021.

Covers:
  - Same input + same key → same fingerprint (deterministic).
  - Different inputs → different fingerprints.
  - Different keys → different fingerprints for same input (key sensitivity).
  - Empty plaintext raises ValueError.
  - length < 8 raises ValueError.
  - length > 64 raises ValueError.
  - length at boundary values (8 and 64) accepted.
  - Default length produces 16-char hex string.
  - Returns lowercase hex only.
  - Missing env var at load time raises RuntimeError.
  - Env var with too-short key raises RuntimeError.
  - Env var with non-hex value raises RuntimeError.

Source: ADR-0021; py/weak-sensitive-data-hashing fix (chunk α).
"""
from __future__ import annotations

import importlib
import os
import sys

import pytest


# ---------------------------------------------------------------------------
# Helpers — inject a test key without clobbering the real env var permanently
# ---------------------------------------------------------------------------

_TEST_KEY_HEX = "a" * 64  # 32 bytes, all 0xaa — valid but not a real secret


def _import_fresh(key_hex: str | None = _TEST_KEY_HEX):
    """
    Import (or reimport) admin_api.services.audit_fingerprint with a
    controlled env var, bypassing the cached module.
    """
    mod_name = "admin_api.services.audit_fingerprint"
    # Remove cached module so _load_hmac_key() runs again.
    sys.modules.pop(mod_name, None)

    old = os.environ.get("MINTKEY_AUDIT_HMAC_KEY")
    try:
        if key_hex is None:
            os.environ.pop("MINTKEY_AUDIT_HMAC_KEY", None)
        else:
            os.environ["MINTKEY_AUDIT_HMAC_KEY"] = key_hex
        mod = importlib.import_module(mod_name)
        return mod
    finally:
        # Restore original value
        if old is None:
            os.environ.pop("MINTKEY_AUDIT_HMAC_KEY", None)
        else:
            os.environ["MINTKEY_AUDIT_HMAC_KEY"] = old
        # Evict the freshly imported module so subsequent tests start clean
        sys.modules.pop(mod_name, None)


# ---------------------------------------------------------------------------
# Key-loading error paths
# ---------------------------------------------------------------------------


def test_missing_env_var_raises() -> None:
    """RuntimeError when MINTKEY_AUDIT_HMAC_KEY is not set."""
    with pytest.raises(RuntimeError, match="MINTKEY_AUDIT_HMAC_KEY"):
        _import_fresh(key_hex=None)


def test_too_short_key_raises() -> None:
    """RuntimeError when key is valid hex but fewer than 32 bytes (< 64 hex chars)."""
    short_hex = "ab" * 16  # 16 bytes — below minimum
    with pytest.raises(RuntimeError, match="at least 32 bytes"):
        _import_fresh(key_hex=short_hex)


def test_non_hex_key_raises() -> None:
    """RuntimeError when MINTKEY_AUDIT_HMAC_KEY contains non-hex characters."""
    with pytest.raises(RuntimeError, match="not valid hex"):
        _import_fresh(key_hex="z" * 64)


def test_exactly_32_byte_key_accepted() -> None:
    """A 32-byte (64 hex char) key is the minimum and must be accepted."""
    mod = _import_fresh(key_hex=_TEST_KEY_HEX)
    # If we get here without RuntimeError the key was accepted.
    assert mod is not None


# ---------------------------------------------------------------------------
# Functional correctness — import with a known key
# ---------------------------------------------------------------------------

# Use a fixed 32-byte test key for all functional tests.
_FIXED_KEY_HEX = "0123456789abcdef" * 4  # 64 hex chars = 32 bytes


@pytest.fixture()
def af():
    """Return the audit_fingerprint function loaded with a fixed test key."""
    mod = _import_fresh(key_hex=_FIXED_KEY_HEX)
    return mod.audit_fingerprint


def test_deterministic(af) -> None:
    """Same plaintext → same fingerprint."""
    a = af(b"hello world")
    b = af(b"hello world")
    assert a == b


def test_different_inputs(af) -> None:
    """Different plaintexts → different fingerprints."""
    a = af(b"hello world")
    b = af(b"hello worldx")
    assert a != b


def test_default_length_16(af) -> None:
    """Default length is 16 hex characters."""
    fp = af(b"test-input")
    assert len(fp) == 16


def test_lowercase_hex_only(af) -> None:
    """Output is lowercase hex (no uppercase, no non-hex chars)."""
    fp = af(b"test-input")
    assert fp == fp.lower()
    assert all(c in "0123456789abcdef" for c in fp)


def test_length_boundary_8(af) -> None:
    """length=8 (minimum) returns 8 hex chars."""
    fp = af(b"data", length=8)
    assert len(fp) == 8


def test_length_boundary_64(af) -> None:
    """length=64 (maximum) returns 64 hex chars."""
    fp = af(b"data", length=64)
    assert len(fp) == 64


def test_custom_length(af) -> None:
    """Custom length is honoured."""
    for n in (8, 12, 16, 32, 64):
        fp = af(b"data", length=n)
        assert len(fp) == n


# ---------------------------------------------------------------------------
# Input validation errors
# ---------------------------------------------------------------------------


def test_empty_plaintext_raises(af) -> None:
    """ValueError when plaintext is empty bytes."""
    with pytest.raises(ValueError, match="non-empty"):
        af(b"")


def test_length_too_short_raises(af) -> None:
    """ValueError when length < 8."""
    with pytest.raises(ValueError, match="length must be 8..64"):
        af(b"data", length=7)


def test_length_too_long_raises(af) -> None:
    """ValueError when length > 64."""
    with pytest.raises(ValueError, match="length must be 8..64"):
        af(b"data", length=65)


# ---------------------------------------------------------------------------
# Key sensitivity — different HMAC keys produce different fingerprints
# ---------------------------------------------------------------------------


def test_different_keys_different_output() -> None:
    """Two different keys MUST produce different fingerprints for the same input."""
    key_a_hex = "a" * 64
    key_b_hex = "b" * 64

    mod_a = _import_fresh(key_hex=key_a_hex)
    fp_a = mod_a.audit_fingerprint(b"canary")

    mod_b = _import_fresh(key_hex=key_b_hex)
    fp_b = mod_b.audit_fingerprint(b"canary")

    assert fp_a != fp_b, "Different keys should produce different fingerprints"
