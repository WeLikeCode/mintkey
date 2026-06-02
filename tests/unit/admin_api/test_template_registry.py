"""
Unit tests for TemplateRegistry and ServiceTemplate model.

Tasks 2.4 + 3.4 from the service-templates Kiro spec.

Task 2.4: TemplateRegistry — load, skip-malformed, filter, search.
Task 3.4: OAuth2PasswordGrantPayload — HTTPS enforcement, empty fields,
          default token_response_path, arbitrary field names, SSRF rejection.

Task 3.2: Hypothesis PBT — Property 1: Credential payload validation.
          For ANY credential payload accepted iff token_url is HTTPS AND
          credential_fields non-empty.

Task 3.3: Hypothesis PBT — Property 3: token_url HTTPS + SSRF validation.
          For ANY URL string accepted iff HTTPS scheme AND passes the SSRF
          allowlist (no private/loopback IPs).
"""
from __future__ import annotations

import logging
import textwrap
from unittest.mock import patch

import pytest
from hypothesis import given, settings, assume
from hypothesis import strategies as st
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# sys.path handled by top-level conftest.py — admin_api already importable.
# ---------------------------------------------------------------------------

from admin_api.templates.models import ServiceTemplate, CredentialHint
from admin_api.templates.registry import TemplateRegistry
from admin_api.services.credential_service import (
    OAuth2PasswordGrantPayload,
    validate_token_url_ssrf,
)


# ===========================================================================
# Task 2.4 — TemplateRegistry + ServiceTemplate unit tests
# ===========================================================================


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_template_dict(**kwargs) -> dict:
    """Return a minimal valid ServiceTemplate dict, overridable via kwargs."""
    base = {
        "template_id": "test-svc",
        "name": "test-svc",
        "display_name": "Test Service",
        "description": "A test service for unit tests.",
        "base_url": "https://api.example.com",
        "auth_type": "bearer_token",
        "openapi_spec_url": None,
        "category": "testing",
        "version": "1.0.0",
        "config_notes": None,
        "credential_hint": None,
        "test_path": "/health",
    }
    base.update(kwargs)
    return base


def _make_registry(yaml_text: str) -> TemplateRegistry:
    """Parse a YAML snippet and return a TemplateRegistry (bypasses file I/O)."""
    import yaml
    data = yaml.safe_load(yaml_text)
    templates = []
    for entry in data.get("templates", []):
        try:
            templates.append(ServiceTemplate.model_validate(entry))
        except (ValidationError, TypeError):
            pass  # mirrors registry._load_templates behaviour for malformed entries
    return TemplateRegistry(templates)


_VALID_YAML = textwrap.dedent("""\
    templates:
      - template_id: gitlab
        name: gitlab
        display_name: GitLab
        description: CI/CD pipelines.
        base_url: https://gitlab.com/api/v4
        auth_type: bearer_token
        openapi_spec_url: null
        category: ci_cd
        version: "1.0.0"
        config_notes: null
        credential_hint: null
        test_path: /version
      - template_id: stripe
        name: stripe
        display_name: Stripe Payments
        description: Payments and invoicing via Stripe API.
        base_url: https://api.stripe.com/v1
        auth_type: bearer_token
        openapi_spec_url: null
        category: payments
        version: "2.0.1"
        config_notes: null
        credential_hint: null
        test_path: /charges?limit=1
      - template_id: sendgrid
        name: sendgrid
        display_name: SendGrid
        description: Transactional email via SendGrid.
        base_url: https://api.sendgrid.com
        auth_type: api_key_header
        openapi_spec_url: null
        category: communications
        version: "1.0.0"
        config_notes: null
        credential_hint: null
        test_path: /user/profile
""")

_MALFORMED_YAML = textwrap.dedent("""\
    templates:
      - template_id: good
        name: good
        display_name: Good Template
        description: A valid entry.
        base_url: https://api.good.example.com
        auth_type: bearer_token
        openapi_spec_url: null
        category: testing
        version: "1.0.0"
        config_notes: null
        credential_hint: null
        test_path: /health
      - template_id: bad-semver
        name: bad-semver
        display_name: Bad Semver
        description: This has an invalid version field.
        base_url: https://api.bad.example.com
        auth_type: bearer_token
        openapi_spec_url: null
        category: testing
        version: "not-a-semver"
        config_notes: null
        credential_hint: null
        test_path: /health
      - missing_required: true
""")


# ---------------------------------------------------------------------------
# TemplateRegistry tests
# ---------------------------------------------------------------------------


class TestTemplateRegistry:
    """Unit tests for TemplateRegistry.list_all and TemplateRegistry.get."""

    def setup_method(self):
        self.registry = _make_registry(_VALID_YAML)

    def test_list_all_returns_all_loaded_templates(self):
        """list_all() without filters returns every loaded template."""
        templates = self.registry.list_all()
        assert len(templates) == 3

    def test_get_returns_correct_template(self):
        """get(template_id) returns the matching ServiceTemplate."""
        tmpl = self.registry.get("gitlab")
        assert tmpl is not None
        assert tmpl.template_id == "gitlab"
        assert tmpl.display_name == "GitLab"

    def test_get_unknown_returns_none(self):
        """get() for a non-existent template_id returns None (not an exception)."""
        assert self.registry.get("does-not-exist") is None

    def test_list_all_category_filter(self):
        """list_all(category=...) returns only matching templates."""
        results = self.registry.list_all(category="ci_cd")
        assert len(results) == 1
        assert results[0].template_id == "gitlab"

    def test_list_all_category_filter_no_match(self):
        """list_all(category=...) returns empty list when no templates match."""
        results = self.registry.list_all(category="observability")
        assert results == []

    def test_list_all_search_by_name(self):
        """search matches against the name field."""
        results = self.registry.list_all(search="stripe")
        assert len(results) == 1
        assert results[0].template_id == "stripe"

    def test_list_all_search_by_display_name(self):
        """search matches against display_name."""
        results = self.registry.list_all(search="SendGrid")
        assert len(results) == 1
        assert results[0].template_id == "sendgrid"

    def test_list_all_search_by_description(self):
        """search matches against description."""
        results = self.registry.list_all(search="invoicing")
        assert len(results) == 1
        assert results[0].template_id == "stripe"

    def test_list_all_search_case_insensitive(self):
        """Case-insensitive search — 'GITLAB' finds the gitlab template."""
        results = self.registry.list_all(search="GITLAB")
        assert len(results) == 1
        assert results[0].template_id == "gitlab"

    def test_list_all_search_mixed_case(self):
        """search='StRiPe' finds stripe."""
        results = self.registry.list_all(search="StRiPe")
        assert len(results) == 1
        assert results[0].template_id == "stripe"

    def test_list_all_combined_category_and_search_narrows_results(self):
        """Combining category + search applies both filters."""
        results = self.registry.list_all(category="payments", search="stripe")
        assert len(results) == 1
        assert results[0].template_id == "stripe"

    def test_list_all_combined_category_and_search_no_cross_hit(self):
        """category=ci_cd + search=stripe yields empty (Stripe is in payments)."""
        results = self.registry.list_all(category="ci_cd", search="stripe")
        assert results == []

    def test_malformed_entry_skipped_valid_still_loaded(self):
        """Malformed entries are skipped; valid entries still load."""
        import yaml
        data = yaml.safe_load(_MALFORMED_YAML)
        templates_loaded = []
        for entry in data.get("templates", []):
            try:
                templates_loaded.append(ServiceTemplate.model_validate(entry))
            except (ValidationError, TypeError):
                pass  # skip

        reg = TemplateRegistry(templates_loaded)
        templates = reg.list_all()
        # Only "good" survives — bad-semver fails validator, missing_required fails model
        assert len(templates) == 1
        assert templates[0].template_id == "good"

    def test_malformed_entry_logs_warning(self, caplog):
        """_load_templates() logs a warning for each malformed entry.

        Calls the real _load_templates via an in-memory YAML patch.
        """
        import yaml
        from admin_api.templates import registry as reg_module

        _bad_yaml = textwrap.dedent("""\
            templates:
              - template_id: valid-one
                name: valid-one
                display_name: Valid One
                description: Valid entry.
                base_url: https://api.valid.example.com
                auth_type: bearer_token
                openapi_spec_url: null
                category: testing
                version: "1.0.0"
                config_notes: null
                credential_hint: null
                test_path: /health
              - template_id: bad-version
                name: bad-version
                display_name: Bad Version
                description: Bad semver.
                base_url: https://api.bad.example.com
                auth_type: bearer_token
                openapi_spec_url: null
                category: testing
                version: "not-semver"
                config_notes: null
                credential_hint: null
                test_path: /health
        """)

        # Patch importlib.resources so _load_templates reads our inline YAML
        class _FakeResource:
            def read_text(self, encoding="utf-8"):
                return _bad_yaml

        class _FakePackage:
            def joinpath(self, _name):
                return _FakeResource()

        import importlib.resources
        with patch.object(importlib.resources, "files", return_value=_FakePackage()):
            with caplog.at_level(logging.WARNING, logger="admin_api.templates.registry"):
                loaded = reg_module._load_templates()

        assert len(loaded) == 1
        assert loaded[0].template_id == "valid-one"
        assert any("bad-version" in rec.message for rec in caplog.records), (
            "Expected a warning mentioning the bad template_id"
        )


# ---------------------------------------------------------------------------
# ServiceTemplate Pydantic model tests
# ---------------------------------------------------------------------------


class TestServiceTemplateModel:
    """ServiceTemplate validates required fields and semver version."""

    def test_valid_template_constructs(self):
        """A fully specified valid dict round-trips through ServiceTemplate."""
        tmpl = ServiceTemplate.model_validate(_make_template_dict())
        assert tmpl.template_id == "test-svc"
        assert tmpl.version == "1.0.0"

    def test_semver_invalid_raises(self):
        """Non-semver version raises ValidationError."""
        with pytest.raises(ValidationError, match="semantic versioning"):
            ServiceTemplate.model_validate(_make_template_dict(version="1.0"))

    def test_semver_valid_prerelease(self):
        """Semver with pre-release label is accepted (e.g. 1.0.0-alpha)."""
        tmpl = ServiceTemplate.model_validate(_make_template_dict(version="1.0.0-alpha.1"))
        assert tmpl.version == "1.0.0-alpha.1"

    def test_semver_valid_with_build(self):
        """Semver with build metadata accepted (e.g. 1.0.0+build.1)."""
        tmpl = ServiceTemplate.model_validate(_make_template_dict(version="1.0.0+build.42"))
        assert tmpl.version == "1.0.0+build.42"

    def test_missing_required_field_raises(self):
        """Omitting a required field (e.g. template_id) raises ValidationError."""
        d = _make_template_dict()
        del d["template_id"]
        with pytest.raises(ValidationError):
            ServiceTemplate.model_validate(d)

    def test_credential_hint_none_allowed(self):
        """credential_hint=None is accepted."""
        tmpl = ServiceTemplate.model_validate(_make_template_dict(credential_hint=None))
        assert tmpl.credential_hint is None

    def test_credential_hint_with_token_url(self):
        """credential_hint with oauth2 fields round-trips correctly."""
        hint = {
            "token_url": "https://auth.example.com/token",
            "credential_fields": {"username": "u", "password": "p"},
            "token_response_path": "$.token",
        }
        tmpl = ServiceTemplate.model_validate(_make_template_dict(credential_hint=hint))
        assert tmpl.credential_hint is not None
        assert tmpl.credential_hint.token_url == "https://auth.example.com/token"


# ===========================================================================
# Task 3.4 — OAuth2PasswordGrantPayload unit tests
# ===========================================================================


class TestOAuth2PasswordGrantPayload:
    """Unit tests for OAuth2PasswordGrantPayload field validation."""

    _PUBLIC_DNS_PATCH = patch(
        "admin_api.services.credential_service.socket.getaddrinfo",
        return_value=[(2, 1, 6, "", ("8.8.8.8", 0))],
    )

    def _valid_payload(self) -> dict:
        return {
            "token_url": "https://auth.example.com/token",
            "credential_fields": {"client_id": "abc", "client_secret": "xyz"},
        }

    def test_valid_payload_accepted(self):
        """A minimal valid payload (HTTPS, non-empty fields) is accepted."""
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(self._valid_payload())
        assert p.token_url == "https://auth.example.com/token"
        assert p.credential_fields == {"client_id": "abc", "client_secret": "xyz"}

    def test_rejects_non_https_token_url(self):
        """http:// token_url is rejected (Req 19.4)."""
        d = self._valid_payload()
        d["token_url"] = "http://auth.example.com/token"
        with pytest.raises(ValidationError, match="HTTPS"):
            OAuth2PasswordGrantPayload.model_validate(d)

    def test_rejects_ftp_scheme(self):
        """ftp:// token_url is rejected."""
        d = self._valid_payload()
        d["token_url"] = "ftp://auth.example.com/token"
        with pytest.raises(ValidationError):
            OAuth2PasswordGrantPayload.model_validate(d)

    def test_rejects_empty_credential_fields(self):
        """Empty credential_fields dict is rejected (Req 19.5)."""
        d = self._valid_payload()
        d["credential_fields"] = {}
        with self._PUBLIC_DNS_PATCH:
            with pytest.raises(ValidationError, match="at least one"):
                OAuth2PasswordGrantPayload.model_validate(d)

    def test_default_token_response_path_is_access_token(self):
        """token_response_path defaults to $.access_token (Req 19.6)."""
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(self._valid_payload())
        assert p.token_response_path == "$.access_token"

    def test_explicit_token_response_path_stored(self):
        """Explicit token_response_path overrides the default."""
        d = self._valid_payload()
        d["token_response_path"] = "$.token"
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(d)
        assert p.token_response_path == "$.token"

    def test_accepts_arbitrary_field_names(self):
        """credential_fields accepts any field names — not locked to username/password."""
        d = self._valid_payload()
        d["credential_fields"] = {
            "api_key": "k",
            "org_id": "org-123",
            "region": "us-east-1",
        }
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(d)
        assert set(p.credential_fields.keys()) == {"api_key", "org_id", "region"}

    def test_ssrf_rejects_loopback(self):
        """token_url with 127.0.0.1 is rejected by SSRF check."""
        d = self._valid_payload()
        d["token_url"] = "https://127.0.0.1/token"
        with pytest.raises(ValidationError, match="SSRF"):
            OAuth2PasswordGrantPayload.model_validate(d)

    def test_ssrf_rejects_rfc1918_10(self):
        """token_url with 10.x.x.x is rejected by SSRF check."""
        d = self._valid_payload()
        d["token_url"] = "https://10.0.0.1/token"
        with pytest.raises(ValidationError, match="SSRF"):
            OAuth2PasswordGrantPayload.model_validate(d)

    def test_ssrf_rejects_rfc1918_172(self):
        """token_url with 172.16.x.x is rejected by SSRF check."""
        d = self._valid_payload()
        d["token_url"] = "https://172.16.0.1/token"
        with pytest.raises(ValidationError, match="SSRF"):
            OAuth2PasswordGrantPayload.model_validate(d)

    def test_ssrf_rejects_rfc1918_192(self):
        """token_url with 192.168.x.x is rejected by SSRF check."""
        d = self._valid_payload()
        d["token_url"] = "https://192.168.1.1/token"
        with pytest.raises(ValidationError, match="SSRF"):
            OAuth2PasswordGrantPayload.model_validate(d)

    def test_ssrf_rejects_link_local(self):
        """token_url with 169.254.x.x (link-local) is rejected."""
        d = self._valid_payload()
        d["token_url"] = "https://169.254.169.254/token"
        with pytest.raises(ValidationError, match="SSRF"):
            OAuth2PasswordGrantPayload.model_validate(d)

    def test_ssrf_rejects_hostname_resolving_to_private(self):
        """token_url with a hostname that DNS-resolves to a private IP is rejected."""
        d = self._valid_payload()
        d["token_url"] = "https://internal.corp.example.com/token"
        with patch(
            "admin_api.services.credential_service.socket.getaddrinfo",
            return_value=[(2, 1, 6, "", ("10.0.1.50", 0))],
        ):
            with pytest.raises(ValidationError, match="SSRF"):
                OAuth2PasswordGrantPayload.model_validate(d)

    def test_token_request_headers_optional(self):
        """token_request_headers is optional and defaults to None."""
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(self._valid_payload())
        assert p.token_request_headers is None

    # --- exchange_timeout_seconds tests (OAUTH-C1) ---

    def test_exchange_timeout_seconds_defaults_to_10(self):
        """exchange_timeout_seconds defaults to 10 when not supplied."""
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(self._valid_payload())
        assert p.exchange_timeout_seconds == 10

    def test_exchange_timeout_seconds_explicit_30_accepted(self):
        """exchange_timeout_seconds=30 is accepted and stored (real-world Azure value)."""
        d = self._valid_payload()
        d["exchange_timeout_seconds"] = 30
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(d)
        assert p.exchange_timeout_seconds == 30

    def test_exchange_timeout_seconds_lower_bound_1_accepted(self):
        """exchange_timeout_seconds=1 (lower bound) is accepted."""
        d = self._valid_payload()
        d["exchange_timeout_seconds"] = 1
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(d)
        assert p.exchange_timeout_seconds == 1

    def test_exchange_timeout_seconds_upper_bound_120_accepted(self):
        """exchange_timeout_seconds=120 (upper bound) is accepted."""
        d = self._valid_payload()
        d["exchange_timeout_seconds"] = 120
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(d)
        assert p.exchange_timeout_seconds == 120

    def test_exchange_timeout_seconds_zero_rejected(self):
        """exchange_timeout_seconds=0 is below the minimum (1) and must be rejected."""
        d = self._valid_payload()
        d["exchange_timeout_seconds"] = 0
        with self._PUBLIC_DNS_PATCH:
            with pytest.raises(ValidationError, match="exchange_timeout_seconds"):
                OAuth2PasswordGrantPayload.model_validate(d)

    def test_exchange_timeout_seconds_121_rejected(self):
        """exchange_timeout_seconds=121 exceeds the maximum (120) and must be rejected."""
        d = self._valid_payload()
        d["exchange_timeout_seconds"] = 121
        with self._PUBLIC_DNS_PATCH:
            with pytest.raises(ValidationError, match="exchange_timeout_seconds"):
                OAuth2PasswordGrantPayload.model_validate(d)

    def test_exchange_timeout_seconds_in_serialized_json(self):
        """exchange_timeout_seconds appears in model_dump() so it's included in stored JSON."""
        d = self._valid_payload()
        d["exchange_timeout_seconds"] = 30
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(d)
        dumped = p.model_dump()
        assert "exchange_timeout_seconds" in dumped
        assert dumped["exchange_timeout_seconds"] == 30

    def test_exchange_timeout_seconds_default_in_serialized_json(self):
        """Default value (10) is present in model_dump() even when not supplied."""
        with self._PUBLIC_DNS_PATCH:
            p = OAuth2PasswordGrantPayload.model_validate(self._valid_payload())
        dumped = p.model_dump()
        assert "exchange_timeout_seconds" in dumped
        assert dumped["exchange_timeout_seconds"] == 10


# ===========================================================================
# Task 3.2 — Hypothesis PBT: Property 1 (Credential payload validation)
#
# Property 1: For any credential payload, the Admin API SHALL accept it iff
#   token_url is HTTPS AND credential_fields is non-empty.
#
# Here we exercise the Pydantic model directly (the same path the API calls).
# We patch the narrow SSRF DNS resolver to return a public IP so the
# discriminating variable is purely the HTTPS + non-empty-fields condition.
# ===========================================================================


_PUBLIC_ADDRS = [(2, 1, 6, "", ("8.8.8.8", 0))]


def _try_validate(payload: dict) -> bool:
    """Return True iff OAuth2PasswordGrantPayload accepts the payload."""
    try:
        OAuth2PasswordGrantPayload.model_validate(payload)
        return True
    except (ValidationError, Exception):
        return False


@given(
    scheme=st.sampled_from(["https", "http", "ftp", "ws", ""]),
    host=st.from_regex(r"[a-z]{3,10}\.[a-z]{2,5}", fullmatch=True),
    path=st.from_regex(r"/[a-z]{0,10}", fullmatch=True),
    fields=st.one_of(
        st.just({}),
        st.dictionaries(
            st.text(min_size=1, max_size=10, alphabet=st.characters(whitelist_categories=("Ll",))),
            st.text(min_size=0, max_size=20),
            min_size=1,
            max_size=5,
        ),
    ),
)
@settings(max_examples=200)
def test_property1_credential_payload_validation(scheme, host, path, fields):
    """Property 1: payload accepted iff scheme=='https' AND fields non-empty.

    Discriminating power:
    - Any http:// URL → rejected (tests the HTTPS guard)
    - Any {} credential_fields → rejected (tests the non-empty guard)
    - Any https:// with non-empty fields → accepted (positive case)
    """
    url = f"{scheme}://{host}{path}" if scheme else f"//{host}{path}"
    payload = {"token_url": url, "credential_fields": fields}

    with patch(
        "admin_api.services.credential_service.socket.getaddrinfo",
        return_value=_PUBLIC_ADDRS,
    ):
        accepted = _try_validate(payload)

    is_https = scheme == "https"
    has_fields = len(fields) > 0

    if is_https and has_fields:
        assert accepted, (
            f"Expected acceptance for HTTPS + non-empty fields; url={url!r}, fields={fields!r}"
        )
    elif not is_https:
        assert not accepted, (
            f"Expected rejection for non-HTTPS scheme={scheme!r}; url={url!r}"
        )
    else:
        # is_https but fields empty
        assert not accepted, (
            f"Expected rejection for empty credential_fields; url={url!r}"
        )


# ===========================================================================
# Task 3.3 — Hypothesis PBT: Property 3 (token_url HTTPS + SSRF validation)
#
# Property 3: For any URL string the Admin API SHALL accept as token_url iff
#   it uses HTTPS scheme AND passes the SSRF allowlist check.
#
# We patch socket.getaddrinfo narrowly to control which IPs are returned,
# keeping asyncpg DB connections unaffected (they never call getaddrinfo on
# these synthetic hostnames).
# ===========================================================================

# IP addresses that are in each forbidden network:
_PRIVATE_IPS = [
    "10.0.0.1",       # RFC1918 10/8
    "172.16.0.1",     # RFC1918 172.16/12
    "192.168.1.1",    # RFC1918 192.168/16
    "127.0.0.1",      # loopback
    "169.254.1.1",    # link-local
    "::1",            # IPv6 loopback
    "fc00::1",        # IPv6 unique-local
]

_PUBLIC_IP = "8.8.8.8"  # a safe public IP


@given(
    scheme=st.sampled_from(["https", "http", "ftp"]),
    # Use a fixed synthetic hostname; we control DNS resolution via patch
    private_ip=st.sampled_from(_PRIVATE_IPS),
)
@settings(max_examples=150)
def test_property3_token_url_https_and_ssrf_validation_private(scheme, private_ip):
    """Property 3 (private-IP branch): HTTPS + private IP → rejected."""
    url = f"{scheme}://synthetic.test.invalid/token"
    # Patch the resolver to return the private IP so we exercise the SSRF path
    fake_addr = [(10 if ":" in private_ip else 2, 1, 6, "", (private_ip, 0))]
    with patch(
        "admin_api.services.credential_service.socket.getaddrinfo",
        return_value=fake_addr,
    ):
        is_safe, reason = validate_token_url_ssrf(url)

    if scheme != "https":
        assert not is_safe, f"Non-HTTPS {scheme!r} must be rejected; got safe=True"
        assert reason == "scheme_must_be_https"
    else:
        # HTTPS but private/loopback IP → SSRF rejection
        assert not is_safe, (
            f"HTTPS + private IP {private_ip!r} must be blocked; got safe=True"
        )
        assert reason == "private_or_loopback_ip_blocked"


@given(
    scheme=st.sampled_from(["https", "http", "ftp"]),
)
@settings(max_examples=100)
def test_property3_token_url_https_and_ssrf_validation_public(scheme):
    """Property 3 (public-IP branch): HTTPS + public IP → accepted."""
    url = f"{scheme}://synthetic.test.invalid/token"
    fake_addr = [(2, 1, 6, "", (_PUBLIC_IP, 0))]
    with patch(
        "admin_api.services.credential_service.socket.getaddrinfo",
        return_value=fake_addr,
    ):
        is_safe, reason = validate_token_url_ssrf(url)

    if scheme == "https":
        assert is_safe, f"HTTPS + public IP must be accepted; reason={reason!r}"
        assert reason == ""
    else:
        assert not is_safe, f"Non-HTTPS must be rejected; scheme={scheme!r}"


_PRIVATE_IPV4_IPS = [ip for ip in _PRIVATE_IPS if ":" not in ip]
_PRIVATE_IPV6_IPS = [ip for ip in _PRIVATE_IPS if ":" in ip]


@given(
    ip_str=st.sampled_from(_PRIVATE_IPV4_IPS),
)
@settings(max_examples=50)
def test_property3_ipv4_literal_private_rejected(ip_str):
    """Property 3 (IPv4 literal): HTTPS + private IPv4 literal → SSRF blocked (no DNS)."""
    url = f"https://{ip_str}/token"
    # No DNS patch needed — IP literals are checked directly without getaddrinfo
    is_safe, reason = validate_token_url_ssrf(url)
    assert not is_safe, f"Private IPv4 literal {ip_str!r} must be blocked"
    assert reason == "private_or_loopback_ip_blocked"


@given(
    ip_str=st.sampled_from(_PRIVATE_IPV6_IPS),
)
@settings(max_examples=20)
def test_property3_ipv6_literal_private_rejected(ip_str):
    """Property 3 (IPv6 literal): HTTPS + private IPv6 bracketed literal → SSRF blocked.

    IPv6 addresses must be bracketed in URLs per RFC 3986: https://[::1]/token.
    """
    url = f"https://[{ip_str}]/token"
    is_safe, reason = validate_token_url_ssrf(url)
    assert not is_safe, f"Private IPv6 literal [{ip_str}] must be blocked"
    assert reason == "private_or_loopback_ip_blocked"
