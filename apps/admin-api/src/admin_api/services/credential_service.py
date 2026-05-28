"""
OAuth2 Password Grant credential payload validation.

Defines the Pydantic model for validating structured credential payloads
when auth_type=oauth2_password_grant. Integrates with the existing SSRF
allowlist check (S-SEC-1) to reject token_url values pointing at private
or loopback addresses.

Source: design §7 (Admin API — Credential Validation for oauth2_password_grant);
        Requirements 19.2, 19.4, 19.5, 19.6.
"""
from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlsplit

from pydantic import BaseModel, field_validator


# ---------------------------------------------------------------------------
# SSRF forbidden networks — mirrors S-SEC-1 / ADR-0014.4
# (same list as apps/admin-api/src/admin_api/api/services.py)
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


def validate_token_url_ssrf(url: str) -> tuple[bool, str]:
    """Validate that a token_url is safe for outbound calls (S-SEC-1).

    Returns (is_safe, reason_if_unsafe).

    Checks:
      1. Scheme must be HTTPS.
      2. Hostname must be present.
      3. If hostname is an IP literal, it must not be in a forbidden network.
      4. If hostname is a DNS name, resolve it and reject if any address is
         in a forbidden network.

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

    # Check IP literal directly
    try:
        ip = ipaddress.ip_address(hostname)
        for net in _FORBIDDEN_NETWORKS:
            if ip in net:
                return (False, "private_or_loopback_ip_blocked")
        return (True, "")
    except ValueError:
        pass  # Not an IP literal — resolve DNS

    # DNS resolution check
    try:
        resolved = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return (False, "dns_resolution_failed")

    for _family, _type, _proto, _canonname, sockaddr in resolved:
        addr = sockaddr[0]
        ip = ipaddress.ip_address(addr)
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_multicast
            or ip.is_reserved
            or ip.is_unspecified
        ):
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

    Source: Requirements 19.2, 19.4, 19.5, 19.6.
    """

    token_url: str
    credential_fields: dict[str, str]
    token_response_path: str = "$.access_token"
    token_request_headers: dict[str, str] | None = None

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
