"""
Unit tests for the pure validation helpers in
``admin_api.services.access_requests`` (T-3.1) plus the ``request_`` wire-ID
formatter in ``admin_api.utils.wire_ids`` (T-3.2).

These are example-based unit tests only — the Hypothesis property tests for the
same helpers land in T-3.4. This file is ADD-ONLY: it neither modifies the
helpers nor any existing test.

Coverage:
  - find_secret_denylist_field / config_has_secret_field — denylist match
    (client_secret, api_password, x_passphrase, private_key, token, api_key)
    AND miss (client_id, token_url, ssh_user, header_name)  — Req 2.4
  - is_ssh_auth_scheme                                       — Req 2.5
  - validate_ssh_base_url — valid ssh://host:port + invalid variants
    (no port, non-numeric port, wrong scheme, trailing path) — Req 2.5, 2.6
  - validate_openapi_url — non-HTTPS rejected, SSRF-blocked rejected,
    valid HTTPS pass                                          — Req 2.8, 2.9
  - compute_expires_at — exact 30-day delta + UTC normalisation — Req 9.1
  - db_uuid_to_wire_request — ^request_[0-9A-HJKMNP-TV-Z]{26}$ + round-trip

Source: T-3.2; Req 2.4, 2.5, 2.6, 2.8, 2.9, 9.1; ADR-0017.11; ADR-0023;
        S-SEC-1 (shared SSRF check).
"""
from __future__ import annotations

import re
import uuid as _uuid
from datetime import datetime, timedelta, timezone

import pytest

from admin_api.services.access_requests import (
    compute_expires_at,
    config_has_secret_field,
    find_secret_denylist_field,
    is_ssh_auth_scheme,
    validate_openapi_url,
    validate_ssh_base_url,
)
from admin_api.utils.wire_ids import db_uuid_to_wire_request, wire_to_db_uuid

# ---------------------------------------------------------------------------
# Secret-field denylist — Req 2.4 / P-1
# ---------------------------------------------------------------------------

_DENYLISTED_NAMES = [
    "client_secret",
    "api_password",
    "x_passphrase",
    "private_key",
    "token",
    "api_key",
]

_ALLOWED_NAMES = [
    "client_id",
    "token_url",
    "ssh_user",
    "header_name",
]


@pytest.mark.parametrize("name", _DENYLISTED_NAMES)
def test_find_secret_denylist_field_matches_secret_name(name: str) -> None:
    """A config containing a denylisted field returns that field name."""
    assert find_secret_denylist_field({name: "value"}) == name


@pytest.mark.parametrize("name", _DENYLISTED_NAMES)
def test_config_has_secret_field_true_for_secret_name(name: str) -> None:
    assert config_has_secret_field({name: "value"}) is True


@pytest.mark.parametrize("name", _ALLOWED_NAMES)
def test_find_secret_denylist_field_misses_non_secret_name(name: str) -> None:
    """Non-secret config field names are accepted (return None)."""
    assert find_secret_denylist_field({name: "value"}) is None


@pytest.mark.parametrize("name", _ALLOWED_NAMES)
def test_config_has_secret_field_false_for_non_secret_name(name: str) -> None:
    assert config_has_secret_field({name: "value"}) is False


def test_find_secret_denylist_field_empty_config_returns_none() -> None:
    assert find_secret_denylist_field({}) is None
    assert config_has_secret_field({}) is False


def test_find_secret_denylist_field_all_allowed_returns_none() -> None:
    """A config with only allowed names has no denylisted field."""
    config = {name: "v" for name in _ALLOWED_NAMES}
    assert find_secret_denylist_field(config) is None


def test_find_secret_denylist_field_detects_secret_among_allowed() -> None:
    """A single secret field among allowed fields is still detected."""
    config = {"client_id": "abc", "ssh_user": "root", "api_secret": "shh"}
    assert find_secret_denylist_field(config) == "api_secret"


def test_denylist_is_case_insensitive() -> None:
    """Matching is case-insensitive (Client_Secret == client_secret)."""
    assert find_secret_denylist_field({"Client_Secret": "v"}) == "Client_Secret"
    assert find_secret_denylist_field({"API_KEY": "v"}) == "API_KEY"


# ---------------------------------------------------------------------------
# SSH auth-scheme detection — Req 2.5 / ADR-0023
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "scheme", ["ssh_private_key", "ssh_ca", "ssh_password"]
)
def test_is_ssh_auth_scheme_true(scheme: str) -> None:
    assert is_ssh_auth_scheme(scheme) is True


@pytest.mark.parametrize(
    "scheme", ["bearer_token", "api_key", "oauth2_client_credentials", "ssh", ""]
)
def test_is_ssh_auth_scheme_false(scheme: str) -> None:
    assert is_ssh_auth_scheme(scheme) is False


# ---------------------------------------------------------------------------
# SSH base_url validation — Req 2.5, 2.6 / ADR-0023
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "ssh://host.example.com:22",
        "ssh://10.0.0.1:2222",
        "ssh://bastion:65535",
        "ssh://host:1",
    ],
)
def test_validate_ssh_base_url_valid(url: str) -> None:
    assert validate_ssh_base_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "ssh://host.example.com",        # no port
        "ssh://host:ssh",                # non-numeric port
        "https://host.example.com:22",   # wrong scheme
        "ssh://host:22/path",            # trailing path
        "ssh://host:22?q=1",             # query string
        "ssh://host:22#frag",            # fragment
        "ssh://:22",                     # empty host
        "ssh://host:70000",              # port out of range (>65535)
        "host:22",                       # missing scheme
        "",                              # empty string
    ],
)
def test_validate_ssh_base_url_invalid(url: str) -> None:
    assert validate_ssh_base_url(url) is False


def test_validate_ssh_base_url_port_zero_current_behaviour() -> None:
    """Port 0 is currently ACCEPTED by the helper.

    ``urlsplit("ssh://host:0").port`` returns ``0`` (not ``None`` and does not
    raise), so the current implementation — which rejects only ``None`` / raised
    ports — treats ``ssh://host:0`` as valid. The docstring's stated 1-65535
    range is not enforced for the lower bound. This test pins the ACTUAL
    behaviour (not the docstring); it must not be changed to green by editing
    the helper here (T-3.2 is add-only). Discrepancy noted for the T-3.1 owner.
    """
    assert validate_ssh_base_url("ssh://host:0") is True


# ---------------------------------------------------------------------------
# openapi_url validation — Req 2.8, 2.9 (shared SSRF check, S-SEC-1)
# ---------------------------------------------------------------------------


def test_validate_openapi_url_non_https_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-HTTPS openapi_url is rejected (Req 2.9)."""
    monkeypatch.delenv("MINTKEY_SSRF_ALLOW_PRIVATE", raising=False)
    ok, reason = validate_openapi_url("http://api.example.com/openapi.json")
    assert ok is False
    assert reason == "scheme_must_be_https"


def test_validate_openapi_url_ssrf_blocked_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An HTTPS URL resolving to a loopback address is SSRF-blocked (Req 2.9)."""
    monkeypatch.delenv("MINTKEY_SSRF_ALLOW_PRIVATE", raising=False)
    ok, reason = validate_openapi_url("https://127.0.0.1/openapi.json")
    assert ok is False
    assert reason == "private_or_loopback_ip_blocked"


def test_validate_openapi_url_missing_host_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MINTKEY_SSRF_ALLOW_PRIVATE", raising=False)
    ok, reason = validate_openapi_url("https:///openapi.json")
    assert ok is False
    assert reason == "missing_host"


def test_validate_openapi_url_valid_https_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A well-formed HTTPS URL passes when the private-IP block is opted out.

    Setting MINTKEY_SSRF_ALLOW_PRIVATE=1 avoids any real DNS resolution while
    still exercising the HTTPS + host checks, mirroring the dev opt-out the
    shared SSRF helper documents (S-SEC-1).
    """
    monkeypatch.setenv("MINTKEY_SSRF_ALLOW_PRIVATE", "1")
    ok, reason = validate_openapi_url("https://api.internal.example.com/openapi.json")
    assert ok is True
    assert reason == ""


# ---------------------------------------------------------------------------
# compute_expires_at — Req 9.1 (30-day delta + UTC normalisation)
# ---------------------------------------------------------------------------


def test_compute_expires_at_exact_30_day_delta_aware() -> None:
    created = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    expires = compute_expires_at(created)
    assert expires - created == timedelta(days=30)
    assert expires == datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)


def test_compute_expires_at_naive_treated_as_utc() -> None:
    """A naive created_at is treated as UTC and returned UTC-aware."""
    created_naive = datetime(2026, 1, 1, 12, 0, 0)
    expires = compute_expires_at(created_naive)
    assert expires.tzinfo is not None
    assert expires.utcoffset() == timedelta(0)
    assert expires == datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)


def test_compute_expires_at_normalises_offset_to_utc() -> None:
    """An aware non-UTC created_at is normalised to UTC before adding 30d."""
    plus_two = timezone(timedelta(hours=2))
    created = datetime(2026, 1, 1, 14, 0, 0, tzinfo=plus_two)
    expires = compute_expires_at(created)
    # 14:00 +02:00 == 12:00 UTC; +30 days -> 2026-01-31 12:00 UTC.
    assert expires.utcoffset() == timedelta(0)
    assert expires == datetime(2026, 1, 31, 12, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# request_ wire-ID formatter — ADR-0017.11
# ---------------------------------------------------------------------------

_REQUEST_WIRE_RE = re.compile(r"^request_[0-9A-HJKMNP-TV-Z]{26}$")


def test_db_uuid_to_wire_request_format() -> None:
    """The formatter emits the canonical ^request_<26 Crockford>$ form."""
    wire = db_uuid_to_wire_request("6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd")
    assert _REQUEST_WIRE_RE.match(wire), wire


def test_db_uuid_to_wire_request_accepts_uuid_object() -> None:
    u = _uuid.UUID("6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd")
    wire = db_uuid_to_wire_request(u)
    assert _REQUEST_WIRE_RE.match(wire), wire


def test_db_uuid_to_wire_request_round_trips() -> None:
    """Encoding then decoding recovers the original dashed UUID."""
    original = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
    wire = db_uuid_to_wire_request(original)
    decoded = wire_to_db_uuid(wire, "request")
    assert decoded == original


def test_db_uuid_to_wire_request_deterministic() -> None:
    """Same UUID always encodes to the same wire ID."""
    u = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
    assert db_uuid_to_wire_request(u) == db_uuid_to_wire_request(u)
