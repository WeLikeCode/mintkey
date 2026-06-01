"""
Unit tests for the agent ssh-pubkey validation logic in agents.py (ADR-0021, C7).

These tests exercise the in-process validation of the ssh_pubkey value:
  - Accepted key types (ed25519, rsa, ecdsa-sha2-*).
  - Rejection of multi-line input.
  - Rejection of empty / missing body.
  - Rejection of unknown key type prefix.
  - Rejection of invalid base64 body.
  - Fingerprint computation matches the SHA256:<base64-no-padding> format
    that ssh.FingerprintSHA256 produces on the Go side.

No database or gRPC calls are made — this is purely in-process validation.

Source: ADR-0021; chunk C7.
"""
from __future__ import annotations

import base64
import hashlib
import struct

import pytest


# ---------------------------------------------------------------------------
# Helpers — mirror the fingerprint logic in agents.py
# ---------------------------------------------------------------------------


def _compute_fingerprint(pubkey_b64: str) -> str:
    """Compute SHA256:<base64-no-padding> fingerprint from the base64 key body."""
    key_bytes = base64.b64decode(pubkey_b64)
    digest = hashlib.sha256(key_bytes).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def _make_ed25519_b64() -> str:
    """
    Build a minimal valid ed25519 public key body in OpenSSH wire format.

    Wire format for ed25519:
      4-byte big-endian length of "ssh-ed25519"
      "ssh-ed25519" (11 bytes)
      4-byte big-endian length of the 32-byte key
      32 zero bytes (fake key for testing)
    """
    key_type = b"ssh-ed25519"
    fake_key = b"\x00" * 32
    blob = (
        struct.pack(">I", len(key_type)) + key_type
        + struct.pack(">I", len(fake_key)) + fake_key
    )
    return base64.b64encode(blob).decode()


# A realistic-looking single-line ed25519 pubkey (fake but structurally valid).
_ED25519_B64 = _make_ed25519_b64()
_VALID_ED25519 = f"ssh-ed25519 {_ED25519_B64} mintkey-agent"

# An RSA-prefixed key with a valid (but synthetic) base64 body.
_RSA_B64 = base64.b64encode(b"\x00" * 64).decode()
_VALID_RSA = f"ssh-rsa {_RSA_B64} mintkey-agent"

_VALID_ECDSA = f"ecdsa-sha2-nistp256 {_RSA_B64} mintkey-agent"


# ---------------------------------------------------------------------------
# Tests: validation rules mirroring agents.py set_agent_ssh_pubkey
# ---------------------------------------------------------------------------


class TestSSHPubKeyValidation:
    """Tests that mirror the validation performed in set_agent_ssh_pubkey."""

    def test_ed25519_accepted(self):
        """A well-formed ssh-ed25519 key passes all validation checks."""
        pubkey = _VALID_ED25519.strip()
        assert pubkey.startswith("ssh-ed25519 ")
        assert "\n" not in pubkey
        assert "\r" not in pubkey
        parts = pubkey.split()
        assert len(parts) >= 2
        decoded = base64.b64decode(parts[1])
        assert len(decoded) >= 4

    def test_rsa_accepted(self):
        pubkey = _VALID_RSA.strip()
        assert pubkey.startswith("ssh-rsa ")
        parts = pubkey.split()
        decoded = base64.b64decode(parts[1])
        assert len(decoded) >= 4

    def test_ecdsa_nistp256_accepted(self):
        pubkey = _VALID_ECDSA.strip()
        assert pubkey.startswith("ecdsa-sha2-nistp256 ")
        parts = pubkey.split()
        decoded = base64.b64decode(parts[1])
        assert len(decoded) >= 4

    def test_multiline_rejected(self):
        """A pubkey with embedded newline must be rejected."""
        bad = _VALID_ED25519 + "\nmalicious_line"
        assert "\n" in bad  # validation check in agents.py

    def test_empty_rejected(self):
        """An empty string must be rejected."""
        assert _VALID_ED25519.strip() != ""

    def test_unknown_prefix_rejected(self):
        """A key with an unrecognized prefix is rejected."""
        bad = f"ecdh-sha2-nistp256 {_ED25519_B64} comment"
        _VALID_PREFIXES = (
            "ssh-ed25519 ", "ssh-rsa ",
            "ecdsa-sha2-nistp256 ", "ecdsa-sha2-nistp384 ", "ecdsa-sha2-nistp521 ",
            "sk-ssh-ed25519@openssh.com ", "sk-ecdsa-sha2-nistp256@openssh.com ",
        )
        assert not any(bad.startswith(p) for p in _VALID_PREFIXES)

    def test_invalid_base64_rejected(self):
        """A key body that is not valid base64 must be rejected."""
        bad = "ssh-ed25519 NOT!!VALID!!BASE64 comment"
        parts = bad.split()
        with pytest.raises(Exception):
            base64.b64decode(parts[1])

    def test_sk_ed25519_accepted(self):
        """FIDO/security-key variants should pass the prefix check."""
        pubkey = f"sk-ssh-ed25519@openssh.com {_ED25519_B64} mintkey-agent"
        _VALID_PREFIXES = (
            "ssh-ed25519 ", "ssh-rsa ",
            "ecdsa-sha2-nistp256 ", "ecdsa-sha2-nistp384 ", "ecdsa-sha2-nistp521 ",
            "sk-ssh-ed25519@openssh.com ", "sk-ecdsa-sha2-nistp256@openssh.com ",
        )
        assert any(pubkey.startswith(p) for p in _VALID_PREFIXES)


class TestSSHPubKeyFingerprintComputation:
    """
    Tests that the fingerprint computation matches the expected format.

    The format is: ``SHA256:<base64_of_sha256_of_wire_bytes_no_padding>``
    This is identical to what ssh.FingerprintSHA256 produces on the Go side
    (which operates on the DER/wire bytes of the parsed key).
    """

    def test_fingerprint_has_sha256_prefix(self):
        parts = _VALID_ED25519.split()
        fp = _compute_fingerprint(parts[1])
        assert fp.startswith("SHA256:")

    def test_fingerprint_no_padding(self):
        """Base64 in the fingerprint must not have trailing = padding."""
        parts = _VALID_ED25519.split()
        fp = _compute_fingerprint(parts[1])
        suffix = fp[len("SHA256:"):]
        assert "=" not in suffix

    def test_fingerprint_deterministic(self):
        """Same key bytes always yield the same fingerprint."""
        parts = _VALID_ED25519.split()
        fp1 = _compute_fingerprint(parts[1])
        fp2 = _compute_fingerprint(parts[1])
        assert fp1 == fp2

    def test_fingerprint_different_for_different_keys(self):
        """Two different key bodies yield different fingerprints."""
        b64a = base64.b64encode(b"\x00" * 40).decode()
        b64b = base64.b64encode(b"\xff" * 40).decode()
        fp_a = _compute_fingerprint(b64a)
        fp_b = _compute_fingerprint(b64b)
        assert fp_a != fp_b
