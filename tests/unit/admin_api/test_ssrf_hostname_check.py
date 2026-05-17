"""
Unit tests for the SSRF host-binding guardrail added in S1 — py/full-ssrf.

Rule: _check_ssrf_hostname(final_url, base_url) must raise HTTPException(400)
whenever the effective hostname of final_url differs from the hostname of
base_url (case-insensitive).

Source: S-SEC-1; ADR-0014.4; CodeQL alert py/full-ssrf @ services.py:537.
"""
from __future__ import annotations

import pytest


# ---------------------------------------------------------------------------
# Negative tests — SSRF attempts that MUST be rejected
# ---------------------------------------------------------------------------


class TestSSRFBlocked:
    """Requests whose final_url escapes the declared base_url host are rejected."""

    def test_link_local_metadata_endpoint_rejected(self) -> None:
        """169.254.169.254 (AWS/GCP metadata) is not the declared host."""
        from fastapi import HTTPException

        from admin_api.api.services import _check_ssrf_hostname

        with pytest.raises(HTTPException) as exc_info:
            _check_ssrf_hostname(
                final_url="http://169.254.169.254/latest/meta-data/",
                base_url="https://api.github.com",
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["mintkey:code"] == "ssrf_blocked"

    def test_localhost_rejected(self) -> None:
        """localhost as final_url host does not match an external service base_url."""
        from fastapi import HTTPException

        from admin_api.api.services import _check_ssrf_hostname

        with pytest.raises(HTTPException) as exc_info:
            _check_ssrf_hostname(
                final_url="http://localhost/admin",
                base_url="https://api.github.com",
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["mintkey:code"] == "ssrf_blocked"

    def test_internal_hostname_rejected(self) -> None:
        """internal.local diverges from the external service declared in base_url."""
        from fastapi import HTTPException

        from admin_api.api.services import _check_ssrf_hostname

        with pytest.raises(HTTPException) as exc_info:
            _check_ssrf_hostname(
                final_url="http://internal.local/secret",
                base_url="https://api.github.com",
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["mintkey:code"] == "ssrf_blocked"

    def test_path_injection_redirecting_to_different_host_rejected(self) -> None:
        """
        Attack vector: test.path = //evil.com/steal causes httpx to resolve
        the request against evil.com, not api.github.com.
        After base_url.rstrip('/') + path, final_url might parse as evil.com.
        """
        from fastapi import HTTPException

        from admin_api.api.services import _check_ssrf_hostname

        with pytest.raises(HTTPException) as exc_info:
            _check_ssrf_hostname(
                final_url="https://evil.com/steal",
                base_url="https://api.github.com",
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["mintkey:code"] == "ssrf_blocked"
        assert exc_info.value.detail["base_host"] == "api.github.com"
        assert exc_info.value.detail["final_host"] == "evil.com"


# ---------------------------------------------------------------------------
# Positive tests — legitimate outbound URLs that MUST be permitted
# ---------------------------------------------------------------------------


class TestSSRFPermitted:
    """Requests whose final_url stays on the declared base_url host are allowed."""

    def test_matching_hostname_passes(self) -> None:
        """Happy path: final_url host == base_url host."""
        from admin_api.api.services import _check_ssrf_hostname

        # Must not raise — returns None
        result = _check_ssrf_hostname(
            final_url="https://api.github.com/repos/octocat/hello-world",
            base_url="https://api.github.com",
        )
        assert result is None

    def test_matching_hostname_with_path_passes(self) -> None:
        """base_url with trailing path prefix; final_url extends it — still same host."""
        from admin_api.api.services import _check_ssrf_hostname

        result = _check_ssrf_hostname(
            final_url="https://api.stripe.com/v1/charges",
            base_url="https://api.stripe.com",
        )
        assert result is None

    def test_case_insensitive_hostname_match(self) -> None:
        """Hostname comparison is case-insensitive (RFC 4343)."""
        from admin_api.api.services import _check_ssrf_hostname

        result = _check_ssrf_hostname(
            final_url="https://API.GITHUB.COM/repos",
            base_url="https://api.github.com",
        )
        assert result is None

    def test_matching_hostname_with_query_param_appended(self) -> None:
        """api_key_query scheme appends ?api_key=... — host must still match."""
        from admin_api.api.services import _check_ssrf_hostname

        result = _check_ssrf_hostname(
            final_url="https://api.github.com/repos?api_key=secret",
            base_url="https://api.github.com",
        )
        assert result is None
