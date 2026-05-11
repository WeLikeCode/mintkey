"""
Tests for otel_redaction.py — SDK-level OTel span attribute redaction filter.

TDD: written before implementation per T-1.0.14 test-first discipline.
Source: T-1.0.14; ADR-0017.6 (span attribute allowlist; credential patterns).

Requirements verified:
- OTEL-SEC-1: exact name matches are always redacted
- OTEL-SEC-2: suffix matches (_token, _secret, _password, _passphrase, _key, _hash) are redacted
- OTEL-SEC-3: values matching credential patterns (sk_/pk_/eyJ) are redacted
- OTEL-SEC-4: safe attributes pass through unmodified
"""
from __future__ import annotations

import pytest
from mintkey_models.otel_redaction import redact_attributes, RedactingSpanProcessor


# ---------------------------------------------------------------------------
# redact_attributes — exact name matches
# ---------------------------------------------------------------------------

def test_exact_name_authorization_redacted():
    result = redact_attributes({"http.request.header.authorization": "Bearer token123"})
    assert "http.request.header.authorization" not in result


def test_exact_name_db_statement_redacted():
    result = redact_attributes({"db.statement": "SELECT * FROM sessions"})
    assert "db.statement" not in result


def test_exact_name_messaging_payload_redacted():
    result = redact_attributes({"messaging.message.payload": '{"secret": "x"}'})
    assert "messaging.message.payload" not in result


def test_exact_name_mintkey_token_redacted():
    result = redact_attributes({"mintkey.token": "eyJhbGciOiJFZERTQSJ9.payload.sig"})
    assert "mintkey.token" not in result


# ---------------------------------------------------------------------------
# redact_attributes — suffix matches
# ---------------------------------------------------------------------------

def test_suffix_token_redacted():
    result = redact_attributes({"mintkey.access_token": "sk_live_abc123"})
    assert "mintkey.access_token" not in result


def test_suffix_secret_redacted():
    result = redact_attributes({"client_secret": "super-secret"})
    assert "client_secret" not in result


def test_suffix_password_redacted():
    result = redact_attributes({"user_password": "hunter2"})
    assert "user_password" not in result


def test_suffix_passphrase_redacted():
    result = redact_attributes({"pgp_passphrase": "correct horse battery staple"})
    assert "pgp_passphrase" not in result


def test_suffix_key_redacted():
    result = redact_attributes({"api_key": "sk_live_xyz"})
    assert "api_key" not in result


def test_suffix_hash_redacted():
    result = redact_attributes({"credential_hash": "deadbeef" * 8})
    assert "credential_hash" not in result


# ---------------------------------------------------------------------------
# redact_attributes — value pattern matches
# ---------------------------------------------------------------------------

def test_value_sk_prefix_redacted():
    result = redact_attributes({"mintkey.credential": "sk_live_abc123"})
    assert "mintkey.credential" not in result


def test_value_pk_prefix_redacted():
    # "mintkey.pubkey" does NOT end with _key (it ends with "pubkey"), so
    # the only trigger here is the pk_ value pattern.
    result = redact_attributes({"mintkey.pubkey": "pk_test_xyz"})
    assert "mintkey.pubkey" not in result


def test_value_jwt_shape_redacted():
    result = redact_attributes({"mintkey.some_attr": "eyJhbGciOiJFZERTQSJ9.payload.sig"})
    assert "mintkey.some_attr" not in result


# ---------------------------------------------------------------------------
# redact_attributes — safe attributes pass through
# ---------------------------------------------------------------------------

def test_allowlisted_tenant_id_passes_through():
    result = redact_attributes({"mintkey.tenant_id": "tenant_01HX..."})
    assert "mintkey.tenant_id" in result
    assert result["mintkey.tenant_id"] == "tenant_01HX..."


def test_normal_attribute_passes_through():
    result = redact_attributes({"http.status_code": 200, "db.system": "postgresql"})
    assert result["http.status_code"] == 200
    assert result["db.system"] == "postgresql"


def test_non_string_value_not_redacted_by_value_pattern():
    # Integer values should not be matched against credential patterns.
    result = redact_attributes({"mintkey.retry_count": 3})
    assert result["mintkey.retry_count"] == 3


# ---------------------------------------------------------------------------
# RedactingSpanProcessor — integration with a mock downstream processor
# ---------------------------------------------------------------------------

class _MockSpan:
    """Minimal mutable span stand-in."""

    def __init__(self, attributes: dict) -> None:
        self._attributes = dict(attributes)


class _CapturingProcessor:
    """Records on_end calls for inspection."""

    def __init__(self) -> None:
        self.ended: list[_MockSpan] = []

    def on_start(self, span, parent_context=None):
        pass

    def on_end(self, span):
        self.ended.append(span)

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30_000):
        return True


def test_redacting_processor_strips_sensitive_on_end():
    downstream = _CapturingProcessor()
    processor = RedactingSpanProcessor(downstream)

    span = _MockSpan({
        "http.request.header.authorization": "Bearer secret",
        "http.status_code": 200,
        "api_key": "sk_live_abc",
    })
    processor.on_end(span)

    assert len(downstream.ended) == 1
    remaining = downstream.ended[0]._attributes
    assert "http.request.header.authorization" not in remaining
    assert "api_key" not in remaining
    assert remaining["http.status_code"] == 200


def test_redacting_processor_passes_safe_span_unchanged():
    downstream = _CapturingProcessor()
    processor = RedactingSpanProcessor(downstream)

    span = _MockSpan({"http.status_code": 404, "db.system": "postgresql"})
    processor.on_end(span)

    remaining = downstream.ended[0]._attributes
    assert remaining == {"http.status_code": 404, "db.system": "postgresql"}


def test_redacting_processor_delegates_shutdown_and_force_flush():
    downstream = _CapturingProcessor()
    processor = RedactingSpanProcessor(downstream)

    processor.shutdown()
    result = processor.force_flush(5000)
    assert result is True
