"""
Tests for mintkey_models.log_redact — log-safe secret redaction helper.

Verifies:
- Raw secret values are NOT emitted in log output (caplog).
- redact_secret() returns the correct display token.
- Edge cases: None, short values, values exactly at the visible boundary.
"""
from __future__ import annotations

import logging

import pytest

from mintkey_models.log_redact import redact_secret


# ---------------------------------------------------------------------------
# Unit tests for redact_secret()
# ---------------------------------------------------------------------------

class TestRedactSecretDisplayToken:
    def test_long_value_returns_prefix_plus_ellipsis(self) -> None:
        result = redact_secret("canary-demo-api-key")
        assert result == "cana…"

    def test_bearer_token_returns_first_four_chars(self) -> None:
        result = redact_secret("Bearer mk_svckey_ABCDE12345")
        assert result == "Bear…"

    def test_mk_svckey_prefix(self) -> None:
        result = redact_secret("mk_svckey_ABCDE12345")
        assert result == "mk_s…"

    def test_none_value_returns_none_sentinel(self) -> None:
        result = redact_secret(None)
        assert result == "<None>"

    def test_short_value_returns_redacted_sentinel(self) -> None:
        # Value shorter than or equal to visible threshold
        result = redact_secret("abc")
        assert result == "<redacted>"

    def test_value_exactly_at_boundary_returns_redacted(self) -> None:
        result = redact_secret("abcd")  # exactly 4 chars
        assert result == "<redacted>"

    def test_value_one_above_boundary_redacts(self) -> None:
        result = redact_secret("abcde")  # 5 chars
        assert result == "abcd…"

    def test_custom_visible_parameter(self) -> None:
        result = redact_secret("supersecretpassword", visible=6)
        assert result == "supers…"

    def test_raw_secret_not_in_output(self) -> None:
        secret = "canary-demo-api-key-supersensitive"
        display = redact_secret(secret)
        assert secret not in display
        assert len(display) < 10  # just the prefix + ellipsis


# ---------------------------------------------------------------------------
# Integration: raw secret must NOT appear in caplog output
# ---------------------------------------------------------------------------

def test_log_call_does_not_emit_raw_secret(caplog: pytest.LogCaptureFixture) -> None:
    """Verify that passing redact_secret() output to logger does not leak the value."""
    raw_secret = "Bearer mk_svckey_SUPERSENSITIVE12345"
    test_logger = logging.getLogger("test_log_redact")

    with caplog.at_level(logging.INFO, logger="test_log_redact"):
        test_logger.info("bearer: authorization=%s", redact_secret(raw_secret))

    assert caplog.records, "Expected at least one log record"
    log_output = " ".join(r.getMessage() for r in caplog.records)
    assert raw_secret not in log_output, (
        f"Raw secret leaked into log output: {log_output!r}"
    )
    assert "mk_svckey_" not in log_output, (
        "Partial secret (mk_svckey_ prefix) still present in log output"
    )
    # Confirm the redacted form IS present
    assert "Bear…" in log_output


def test_log_call_with_api_key_does_not_emit_raw_value(caplog: pytest.LogCaptureFixture) -> None:
    """Verify x_api_key logging path does not leak the raw key."""
    raw_key = "canary-demo-api-key"
    test_logger = logging.getLogger("test_log_redact")

    with caplog.at_level(logging.INFO, logger="test_log_redact"):
        test_logger.info("api-key-header: x_api_key=%s", redact_secret(raw_key))

    log_output = " ".join(r.getMessage() for r in caplog.records)
    assert raw_key not in log_output, (
        f"Raw API key leaked into log output: {log_output!r}"
    )
    assert "cana…" in log_output


def test_log_call_with_none_authorization(caplog: pytest.LogCaptureFixture) -> None:
    """Verify None authorization header is handled gracefully."""
    test_logger = logging.getLogger("test_log_redact")

    with caplog.at_level(logging.INFO, logger="test_log_redact"):
        test_logger.info("health: authorization=%s", redact_secret(None))

    log_output = " ".join(r.getMessage() for r in caplog.records)
    assert "<None>" in log_output
