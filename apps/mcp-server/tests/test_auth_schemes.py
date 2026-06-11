"""
Enum-parity test: every AuthScheme value in vault.proto must have an entry in
INJECTION_HINTS, and every key in INJECTION_HINTS must map to a known proto
enum value (no orphans).

Also smoke-tests the structure of each hint entry.

Source: design.md D1; spec service-usage-guidance "Scenario: Enum coverage is enforced".
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Parse vault.proto AuthScheme enum → set of lowercase scheme strings
# ---------------------------------------------------------------------------
_PROTO_PATH = (
    Path(__file__).resolve().parents[3]
    / "docs" / "architecture" / "contracts" / "vault-adapter" / "vault.proto"
)

# Map AUTH_SCHEME_FOO_BAR → foo_bar (skip UNSPECIFIED = 0).
# tools.yaml uses the lowercase_underscore form; we derive the same mapping.
_PROTO_ENUM_RE = re.compile(r"AUTH_SCHEME_([A-Z0-9_]+)\s*=\s*(\d+)")


def _parse_proto_schemes() -> set[str]:
    text = _PROTO_PATH.read_text()
    schemes: set[str] = set()
    for m in _PROTO_ENUM_RE.finditer(text):
        name, value = m.group(1), int(m.group(2))
        if value == 0:
            # AUTH_SCHEME_UNSPECIFIED is not a real scheme; skip.
            continue
        schemes.add(name.lower())
    return schemes


_PROTO_SCHEMES = _parse_proto_schemes()


# ---------------------------------------------------------------------------
# Import the table under test (will fail until 2.1 is implemented)
# ---------------------------------------------------------------------------
from mcp_server.auth_schemes import INJECTION_HINTS  # noqa: E402  (after sys.path setup in conftest)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestInjectionHintsParity:
    """INJECTION_HINTS must be in 1:1 correspondence with vault.proto AuthScheme (ex. UNSPECIFIED)."""

    def test_no_missing_schemes(self):
        """Every proto enum value has a hint entry."""
        missing = _PROTO_SCHEMES - set(INJECTION_HINTS.keys())
        assert not missing, (
            f"INJECTION_HINTS is missing entries for proto scheme(s): {sorted(missing)}. "
            "Add a hint to auth_schemes.py for each missing scheme."
        )

    def test_no_orphan_schemes(self):
        """No hint entry lacks a corresponding proto enum value."""
        orphans = set(INJECTION_HINTS.keys()) - _PROTO_SCHEMES
        assert not orphans, (
            f"INJECTION_HINTS has orphan entries not in vault.proto: {sorted(orphans)}. "
            "Either the proto was updated or the key is misspelled."
        )


class TestInjectionHintStructure:
    """Each hint entry must have the required keys with correct types."""

    _REQUIRED_KEYS = {"injects", "location", "never_send", "handled_by", "status"}
    _VALID_STATUSES = {"injected_by_proxy", "not_implemented", "handled_by_other_proxy"}
    _VALID_LOCATIONS = {"header", "query", "connection", "out_of_band"}

    @pytest.mark.parametrize("scheme", sorted(_PROTO_SCHEMES))
    def test_hint_has_required_keys(self, scheme: str):
        hint = INJECTION_HINTS[scheme]
        missing = self._REQUIRED_KEYS - set(hint.keys())
        assert not missing, f"Hint for '{scheme}' missing keys: {missing}"

    @pytest.mark.parametrize("scheme", sorted(_PROTO_SCHEMES))
    def test_hint_status_is_valid(self, scheme: str):
        hint = INJECTION_HINTS[scheme]
        assert hint["status"] in self._VALID_STATUSES, (
            f"Hint for '{scheme}' has invalid status '{hint['status']}'. "
            f"Must be one of: {self._VALID_STATUSES}"
        )

    @pytest.mark.parametrize("scheme", sorted(_PROTO_SCHEMES))
    def test_hint_location_is_valid(self, scheme: str):
        hint = INJECTION_HINTS[scheme]
        assert hint["location"] in self._VALID_LOCATIONS, (
            f"Hint for '{scheme}' has invalid location '{hint['location']}'. "
            f"Must be one of: {self._VALID_LOCATIONS}"
        )

    @pytest.mark.parametrize("scheme", sorted(_PROTO_SCHEMES))
    def test_never_send_is_string(self, scheme: str):
        hint = INJECTION_HINTS[scheme]
        assert isinstance(hint["never_send"], str), (
            f"Hint for '{scheme}'.never_send must be a string."
        )

    @pytest.mark.parametrize("scheme", sorted(_PROTO_SCHEMES))
    def test_injects_is_string(self, scheme: str):
        hint = INJECTION_HINTS[scheme]
        assert isinstance(hint["injects"], str), (
            f"Hint for '{scheme}'.injects must be a string."
        )


class TestSpecificHintBehavior:
    """Spot-check concrete scenarios from the spec."""

    def test_bearer_token_sets_authorization_header(self):
        """Spec scenario: Bearer-token service carries a concrete hint."""
        hint = INJECTION_HINTS["bearer_token"]
        assert "Authorization" in hint["injects"]
        assert "Bearer" in hint["injects"]
        assert "Authorization" in hint["never_send"]

    def test_mtls_is_not_implemented(self):
        """Spec scenario: Unimplemented scheme is honest."""
        hint = INJECTION_HINTS["mtls"]
        assert hint["status"] == "not_implemented"
        # The hint text must say it will fail, not imply it works.
        combined = (hint["injects"] + hint["never_send"]).lower()
        assert "not implemented" in combined or "will fail" in combined or "error" in combined

    def test_ssh_schemes_handled_by_ssh_proxy(self):
        """SSH schemes must state handled_by=ssh-proxy."""
        for scheme in ("ssh_private_key", "ssh_ca", "ssh_password"):
            hint = INJECTION_HINTS[scheme]
            assert hint["status"] == "handled_by_other_proxy", (
                f"'{scheme}' should have status=handled_by_other_proxy"
            )
            assert "ssh" in hint["handled_by"].lower(), (
                f"'{scheme}' should reference ssh-proxy in handled_by"
            )

    def test_email_schemes_handled_by_email_proxy(self):
        """Email schemes must state handled_by=email-proxy."""
        for scheme in ("email_password", "email_oauth2", "email_app_password"):
            hint = INJECTION_HINTS[scheme]
            assert hint["status"] == "handled_by_other_proxy", (
                f"'{scheme}' should have status=handled_by_other_proxy"
            )
            assert "email" in hint["handled_by"].lower(), (
                f"'{scheme}' should reference email-proxy in handled_by"
            )

    def test_api_key_header_default_name(self):
        """api_key_header default header name is X-API-Key (mirrors injector.go:51-53)."""
        hint = INJECTION_HINTS["api_key_header"]
        assert "X-API-Key" in hint["injects"]

    def test_api_key_query_default_param(self):
        """api_key_query default query param is api_key (mirrors injector.go:58-60)."""
        hint = INJECTION_HINTS["api_key_query"]
        assert "api_key" in hint["injects"]

    def test_basic_auth_user_pass_note(self):
        """basic_auth hint must mention user:pass base64 encoding."""
        hint = INJECTION_HINTS["basic_auth"]
        assert "Basic" in hint["injects"]
        assert "base64" in hint["injects"].lower() or "base64" in hint["never_send"].lower()
