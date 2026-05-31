"""
Credential payload validation for structured auth schemes.

Defines Pydantic models for validating structured credential payloads:
  - OAuth2PasswordGrantPayload: auth_type=oauth2_password_grant. Integrates
    with the existing SSRF allowlist check (S-SEC-1).
  - AppleJWTPayload: auth_scheme=apple_jwt. Validates .p8 PEM material,
    key_id, and issuer_id fields; scrubs p8_key_pem from any log output.

Source: design §7 (Admin API — Credential Validation for oauth2_password_grant);
        Requirements 19.2, 19.4, 19.5, 19.6; spec §4.2 (apple_jwt).
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


# ---------------------------------------------------------------------------
# SSRF forbidden networks — S-SEC-1 / ADR-0014.4
# Shared by both services.py (base_url / test-url checks) and this module
# (token_url check). ONE authoritative list.
# ---------------------------------------------------------------------------

_FORBIDDEN_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("::1/128"),
]


def resolve_hostname_is_private(hostname: str) -> bool:
    """Return True if *hostname* DNS-resolves to any forbidden (private/loopback/
    link-local/multicast/reserved/unspecified) IP address — S-SEC-1.

    This is the single shared DNS-SSRF resolver used by both
    ``validate_token_url_ssrf`` (token_url check) and
    ``admin_api.api.services._is_forbidden_destination`` (base_url check).

    - IP literals are checked directly against ``_FORBIDDEN_NETWORKS``.
    - DNS names are resolved via ``socket.getaddrinfo``; if *any* returned
      address is in a forbidden range the function returns ``True``.
    - On ``gaierror`` (DNS failure) returns ``False`` — fails open so that
      a non-resolvable hostname is not mistakenly blocked (connection will
      fail at request time anyway).

    Callers are responsible for checking ``MINTKEY_SSRF_ALLOW_PRIVATE``
    before calling this function.
    """
    # IP literal — fast path
    try:
        ip = ipaddress.ip_address(hostname)
        return any(ip in net for net in _FORBIDDEN_NETWORKS)
    except ValueError:
        pass  # Not an IP literal — resolve DNS

    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return False  # DNS failure → fail open

    for _family, _type, _proto, _canonname, sockaddr in resolved:
        addr = sockaddr[0]
        try:
            ip = ipaddress.ip_address(addr)
            if (
                ip.is_private
                or ip.is_loopback
                or ip.is_link_local
                or ip.is_multicast
                or ip.is_reserved
                or ip.is_unspecified
            ):
                return True
        except ValueError:
            continue
    return False


def validate_token_url_ssrf(url: str) -> tuple[bool, str]:
    """Validate that a token_url is safe for outbound calls (S-SEC-1).

    Returns (is_safe, reason_if_unsafe).

    Checks:
      1. Scheme must be HTTPS.
      2. Hostname must be present.
      3. Hostname (IP literal or DNS name) must not resolve to a forbidden
         network — delegated to ``resolve_hostname_is_private``.

    Operators may set MINTKEY_SSRF_ALLOW_PRIVATE=1 to opt OUT of the
    private-IP block (e.g. dev workflows hitting a private mock backend).
    """
    parts = urlsplit(url)

    if parts.scheme != "https":
        return (False, "scheme_must_be_https")

    hostname = parts.hostname
    if not hostname:
        return (False, "missing_host")

    # Opt-out for dev environments
    if os.environ.get("MINTKEY_SSRF_ALLOW_PRIVATE") == "1":
        return (True, "")

    if resolve_hostname_is_private(hostname):
        return (False, "private_or_loopback_ip_blocked")

    return (True, "")


# ---------------------------------------------------------------------------
# OAuth2 Password Grant credential payload model
# ---------------------------------------------------------------------------


class OAuth2PasswordGrantPayload(BaseModel):
    """Structured credential payload for auth_type=oauth2_password_grant.

    Validated at registration time. The Vault Adapter stores this as JSON.

    Fields:
      - token_url: HTTPS endpoint that accepts credential_fields and returns
        a token. Must pass SSRF allowlist (S-SEC-1).
      - credential_fields: Operator-defined key-value pairs sent as the JSON
        body to token_url. At least one entry required. Field names are NOT
        hardcoded to username/password — arbitrary names are allowed.
      - token_response_path: JSONPath expression for extracting the access
        token from the token endpoint response. Defaults to $.access_token.
      - token_request_headers: Optional extra headers to include on the token
        exchange request.
      - exchange_timeout_seconds: HTTP timeout (in seconds) for the token
        exchange request. Default 10; bounds [1, 120]. Some upstreams (e.g.
        sleeping Azure apps) need >3 s to wake — operators set this explicitly.

    Source: Requirements 19.2, 19.4, 19.5, 19.6.
    """

    token_url: str
    credential_fields: dict[str, str]
    token_response_path: str = "$.access_token"
    token_request_headers: dict[str, str] | None = None
    exchange_timeout_seconds: int = Field(
        default=10,
        ge=1,
        le=120,
        description=(
            "Timeout in seconds for the token-exchange HTTP request. "
            "Bounds [1, 120]; default 10."
        ),
    )

    @field_validator("token_url")
    @classmethod
    def validate_https(cls, v: str) -> str:
        """Require HTTPS scheme — Requirement 19.4."""
        parts = urlsplit(v)
        if parts.scheme != "https":
            raise ValueError("token_url must use HTTPS")
        if not parts.hostname:
            raise ValueError("token_url must have a valid hostname")
        return v

    @field_validator("token_url")
    @classmethod
    def validate_ssrf(cls, v: str) -> str:
        """Reject private/loopback destinations — S-SEC-1, Requirement 19.4."""
        is_safe, reason = validate_token_url_ssrf(v)
        if not is_safe:
            raise ValueError(
                f"token_url blocked by SSRF policy: {reason}"
            )
        return v

    @field_validator("credential_fields")
    @classmethod
    def validate_non_empty(cls, v: dict[str, str]) -> dict[str, str]:
        """Require at least one credential field — Requirement 19.2, 19.5."""
        if not v:
            raise ValueError("credential_fields must contain at least one entry")
        return v


# ---------------------------------------------------------------------------
# Apple JWT credential payload model — spec §4.2
# ---------------------------------------------------------------------------

_APPLE_PEM_PREFIX = "-----BEGIN PRIVATE KEY-----"


class AppleJWTPayload(BaseModel):
    """Structured credential payload for auth_scheme=apple_jwt.

    Validated at registration time. The Vault Adapter stores this as a JSON
    envelope: { "scheme": "apple_jwt", "p8_key_pem": ..., "key_id": ...,
    "issuer_id": ... }.

    Fields:
      - p8_key_pem: PEM-encoded PKCS#8 private key (.p8 file contents).
        Must begin with "-----BEGIN PRIVATE KEY-----". NEVER included in
        audit events or log output — scrubbed at all call sites.
      - key_id: 10-char Apple developer key ID (non-empty string).
      - issuer_id: Apple Team ID / Issuer ID (non-empty string; spec hints
        UUID format but basic non-empty is enforced in this chunk).

    Source: spec §4.2; ADR-0014.4; ADR-0014.7.
    """

    # NOTE: p8_key_pem is intentionally NOT repr'd or logged anywhere.
    # The field is validated then serialised into the vault envelope; it
    # MUST NOT appear in any audit payload or structlog event.
    p8_key_pem: str
    key_id: str
    issuer_id: str

    @field_validator("p8_key_pem")
    @classmethod
    def validate_pem_header(cls, v: str) -> str:
        """Require PKCS#8 PEM header — spec §4.2."""
        stripped = v.strip()
        if not stripped.startswith(_APPLE_PEM_PREFIX):
            raise ValueError(
                f"p8_key_pem must start with '{_APPLE_PEM_PREFIX}'"
            )
        return v

    @field_validator("key_id")
    @classmethod
    def validate_key_id_non_empty(cls, v: str) -> str:
        """key_id must be non-empty — spec §4.2."""
        if not v.strip():
            raise ValueError("key_id must be a non-empty string")
        return v

    @field_validator("issuer_id")
    @classmethod
    def validate_issuer_id_non_empty(cls, v: str) -> str:
        """issuer_id must be non-empty — spec §4.2."""
        if not v.strip():
            raise ValueError("issuer_id must be a non-empty string")
        return v

    def to_vault_envelope(self) -> str:
        """Serialise to the JSON envelope shape the Vault Adapter expects.

        Returns the canonical envelope string:
          { "scheme": "apple_jwt", "p8_key_pem": ..., "key_id": ..., "issuer_id": ... }

        This is the ONLY place p8_key_pem is written into a string after
        validation; the resulting string is passed directly to StoreCredential
        and NEVER logged or returned in a response.
        """
        import json as _json

        return _json.dumps(
            {
                "scheme": "apple_jwt",
                "p8_key_pem": self.p8_key_pem,
                "key_id": self.key_id,
                "issuer_id": self.issuer_id,
            },
            separators=(",", ":"),
        )
