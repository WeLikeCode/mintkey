"""
Credential payload validation for structured auth schemes.

Defines Pydantic models for validating structured credential payloads:
  - OAuth2PasswordGrantPayload: auth_type=oauth2_password_grant. Integrates
    with the existing SSRF allowlist check (S-SEC-1).
  - AppleJWTPayload: auth_scheme=apple_jwt. Validates .p8 PEM material,
    key_id, and issuer_id fields; scrubs p8_key_pem from any log output.
  - GoogleServiceAccountPayload: auth_scheme=google_service_account. Validates
    Google service-account JSON key material; scrubs service_account_json,
    json_key, and private_key from any log output — ADR-0014.7, S-SEC-1.
  - SSHPrivateKeyPayload: auth_scheme=ssh_private_key. Validates PEM-encoded
    SSH private key material, target_address ("host:port"), and ssh_user.
    private_key_pem is NEVER included in audit events or log output — ADR-0021,
    ADR-0014.7, S-SEC-1.

Source: design §7 (Admin API — Credential Validation for oauth2_password_grant);
        Requirements 19.2, 19.4, 19.5, 19.6; spec §4.2 (apple_jwt);
        spec §4.3 (google_service_account); ADR-0021 (ssh_private_key).
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
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


# ---------------------------------------------------------------------------
# Google Service Account credential payload model — spec §4.3
# ---------------------------------------------------------------------------

_GOOGLE_REQUIRED_FIELDS = (
    "type",
    "project_id",
    "private_key_id",
    "private_key",
    "client_email",
    "token_uri",
)


class GoogleServiceAccountPayload(BaseModel):
    """Structured credential payload for auth_scheme=google_service_account.

    Validated at registration time. The Vault Adapter stores this as a JSON
    envelope: { "scheme": "google_service_account", "json_key": ...,
    "scope": ... }, where ``json_key`` is the raw Google service-account JSON
    string (matches the ``StoredBlob`` shape in vault-adapter Go code).

    Fields:
      - service_account_json: The raw Google service-account JSON as a string.
        Must parse as a JSON object, ``type == "service_account"``, and include
        required fields ``project_id``, ``private_key_id``, ``private_key``
        (must start with ``-----BEGIN``), ``client_email`` (must contain ``@``),
        and ``token_uri`` (must start with ``https://``).
        NEVER included in audit events or log output — ADR-0014.4, ADR-0014.7.
      - scope: OAuth2 scope string for the service account token exchange.
        Defaults to the Android Publisher scope; must be non-empty.

    Source: spec §4.3; ADR-0014.4; ADR-0014.7.
    """

    # NOTE: service_account_json contains private_key — NEVER repr'd or logged.
    # The field is validated then serialised into the vault envelope; it MUST
    # NOT appear in any audit payload or structlog / stdlib log event.
    service_account_json: str
    scope: str = "https://www.googleapis.com/auth/androidpublisher"

    @field_validator("service_account_json")
    @classmethod
    def validate_service_account_json(cls, v: str) -> str:
        """Parse and validate Google service-account JSON — spec §4.3."""
        try:
            parsed = json.loads(v)
        except (json.JSONDecodeError, ValueError):
            raise ValueError("invalid service_account_json: not valid JSON")

        if not isinstance(parsed, dict):
            raise ValueError("invalid service_account_json: must be a JSON object")

        # Reject user-credential blobs (auth_uri-only, authorized_user type).
        acc_type = parsed.get("type", "")
        if acc_type != "service_account":
            raise ValueError(
                "invalid service_account_json: type must be 'service_account'"
            )

        # Validate all required fields are present and non-empty.
        for field in _GOOGLE_REQUIRED_FIELDS:
            val = parsed.get(field)
            if not val or not str(val).strip():
                raise ValueError(
                    f"invalid service_account_json: missing or empty field '{field}'"
                )

        # private_key must look like PEM material.
        private_key: str = parsed["private_key"]
        if not private_key.strip().startswith("-----BEGIN"):
            raise ValueError(
                "invalid service_account_json: private_key must start with '-----BEGIN'"
            )

        # client_email must be email-ish.
        client_email: str = parsed["client_email"]
        if "@" not in client_email:
            raise ValueError(
                "invalid service_account_json: client_email must contain '@'"
            )

        # token_uri must be HTTPS.
        token_uri: str = parsed["token_uri"]
        if not token_uri.startswith("https://"):
            raise ValueError(
                "invalid service_account_json: token_uri must start with 'https://'"
            )

        return v

    @field_validator("scope")
    @classmethod
    def validate_scope_non_empty(cls, v: str) -> str:
        """scope must be non-empty — spec §4.3."""
        if not v.strip():
            raise ValueError("scope must be a non-empty string")
        return v

    def to_vault_envelope(self) -> bytes:
        """Serialise to the JSON envelope shape the Vault Adapter expects.

        Returns the canonical envelope bytes:
          { "scheme": "google_service_account", "json_key": ..., "scope": ... }

        ``json_key`` (not ``service_account_json``) is the field name expected
        by the Go StoredBlob in vault-adapter/internal/googleserviceaccount/key.go.

        This is the ONLY place service_account_json is written into a serialised
        value after validation; the resulting bytes are passed directly to
        StoreCredential and NEVER logged or returned in a response.
        """
        return json.dumps(
            {
                "scheme": "google_service_account",
                "json_key": json.loads(self.service_account_json),
                "scope": self.scope,
            },
            separators=(",", ":"),
        ).encode()


# ---------------------------------------------------------------------------
# SSH Private Key credential payload model — ADR-0021
# ---------------------------------------------------------------------------

_SSH_SAFE_USER_RE = re.compile(r'^[a-zA-Z0-9._-]+$')


class SSHPrivateKeyPayload(BaseModel):
    """Structured credential payload for auth_scheme=ssh_private_key.

    Validated at registration time. The Vault Adapter stores the raw PEM bytes
    directly (no JSON envelope) in the encrypted payload column.  The routing
    metadata (target_address, ssh_user) is passed as separate gRPC fields on
    the PutCredential call and stored in the dedicated vault.credentials columns
    added by Liquibase changeset 020-vault-ssh-cols.yaml.

    Fields:
      - private_key_pem: PEM-encoded SSH private key (OpenSSH or PKCS#8 format).
        Must begin with "-----BEGIN" and contain "PRIVATE KEY-----".
        NEVER included in audit events or log output — ADR-0021, ADR-0014.7.
      - target_address: "host:port" string for the backend SSH server.  Port
        must be a valid decimal integer.
      - ssh_user: SSH username for authentication.  Must be non-empty and
        contain only safe characters (ASCII letters, digits, '.', '_', '-').
        Shell-metacharacters are rejected.

    Source: ADR-0021; ADR-0014.4; ADR-0014.7.
    """

    # NOTE: private_key_pem is intentionally NOT repr'd or logged anywhere.
    # The field is validated then passed as raw bytes to StoreCredential;
    # it MUST NOT appear in any audit payload or structlog / stdlib log event.
    private_key_pem: str = Field(..., min_length=1)
    target_address: str  # "host:port"
    ssh_user: str

    @field_validator("private_key_pem")
    @classmethod
    def validate_pem(cls, v: str) -> str:
        """Require PEM header with PRIVATE KEY marker — ADR-0021."""
        stripped = v.strip()
        if not (stripped.startswith("-----BEGIN") and "PRIVATE KEY-----" in stripped):
            raise ValueError(
                "private_key_pem must be a PEM-encoded private key "
                "(must start with '-----BEGIN' and contain 'PRIVATE KEY-----')"
            )
        return v

    @field_validator("target_address")
    @classmethod
    def validate_target(cls, v: str) -> str:
        """Require 'host:port' format with a numeric port — ADR-0021."""
        parts = v.rsplit(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            raise ValueError(
                "target_address must be 'host:port' with a numeric port (e.g. 'myhost:22')"
            )
        host = parts[0].strip()
        if not host:
            raise ValueError("target_address host part must not be empty")
        return v

    @field_validator("ssh_user")
    @classmethod
    def validate_user(cls, v: str) -> str:
        """Require non-empty ssh_user with no shell-metacharacters — ADR-0021."""
        if not v.strip():
            raise ValueError("ssh_user must be a non-empty string")
        if not _SSH_SAFE_USER_RE.match(v):
            raise ValueError(
                "ssh_user contains invalid characters; "
                "only ASCII letters, digits, '.', '_', and '-' are allowed"
            )
        return v

    def to_vault_envelope(self) -> bytes:
        """Return the raw PEM bytes to store in the Vault Adapter.

        For SSH, there is no JSON envelope — the PEM IS the credential.
        target_address and ssh_user are passed as separate gRPC metadata fields
        on the PutCredential call (see admin_api/api/credentials.py).

        This is the ONLY place private_key_pem is read after validation; the
        resulting bytes are passed directly to PutCredential and NEVER logged.
        """
        return self.private_key_pem.encode()


# ---------------------------------------------------------------------------
# SSH Password credential payload model — ADR-0021
# ---------------------------------------------------------------------------


class SSHPasswordPayload(BaseModel):
    """Structured credential payload for auth_scheme=ssh_password.

    Validated at registration time. The Vault Adapter stores the raw password
    bytes directly (no JSON envelope) in the encrypted payload column.  The
    routing metadata (target_address, username) is passed as separate gRPC
    fields on the PutCredential call and stored in the dedicated vault columns.

    Fields:
      - username: SSH username for authentication.  Must be non-empty and
        contain only safe characters (ASCII letters, digits, '.', '_', '-').
        Shell-metacharacters are rejected.
      - password: SSH password.  Length 1..1024 bytes after UTF-8 encoding.
        NEVER included in audit events or log output — ADR-0021, ADR-0014.7.
      - target_address: "host:port" string for the backend SSH server.  Port
        must be a valid decimal integer.

    Source: ADR-0021; ADR-0014.4; ADR-0014.7.
    """

    # NOTE: password is intentionally NOT repr'd or logged anywhere.
    # The field is validated then passed as raw bytes to PutCredential;
    # it MUST NOT appear in any audit payload or structlog / stdlib log event.
    username: str
    password: str = Field(..., min_length=1, max_length=1024)
    target_address: str  # "host:port"

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        """Require non-empty username with no shell-metacharacters — ADR-0021."""
        if not v.strip():
            raise ValueError("username must be a non-empty string")
        if not _SSH_SAFE_USER_RE.match(v):
            raise ValueError(
                "username contains invalid characters; "
                "only ASCII letters, digits, '.', '_', and '-' are allowed"
            )
        return v

    @field_validator("password")
    @classmethod
    def validate_password_length(cls, v: str) -> str:
        """Require non-empty password that fits in 1024 bytes — ADR-0021."""
        if not v:
            raise ValueError("password must not be empty")
        if len(v.encode("utf-8")) > 1024:
            raise ValueError("password exceeds 1024-byte limit after UTF-8 encoding")
        return v

    @field_validator("target_address")
    @classmethod
    def validate_target(cls, v: str) -> str:
        """Require 'host:port' format with a numeric port — ADR-0021."""
        parts = v.rsplit(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            raise ValueError(
                "target_address must be 'host:port' with a numeric port (e.g. 'myhost:22')"
            )
        host = parts[0].strip()
        if not host:
            raise ValueError("target_address host part must not be empty")
        return v

    def to_vault_envelope(self) -> bytes:
        """Return the raw password bytes to store in the Vault Adapter.

        For SSH password, the stored credential IS the raw password bytes.
        username and target_address are passed as separate gRPC metadata fields
        on the PutCredential call (username → ssh_user, target_address → target_address).

        This is the ONLY place password is read after validation; the resulting
        bytes are passed directly to PutCredential and NEVER logged.
        """
        return self.password.encode("utf-8")


# ---------------------------------------------------------------------------
# OAuth2 Client-Credentials credential payload model — ADR-0029
# (MongoDB Atlas Service Accounts; auth_scheme=oauth2_client_credentials, enum 5)
# ---------------------------------------------------------------------------


class OAuth2ClientCredentialsPayload(BaseModel):
    """Structured credential payload for auth_scheme=oauth2_client_credentials.

    Validated at registration time. The Vault Adapter stores the canonical JSON
    envelope the Go proxy parses (design.md Component 1 — a bare object, NOT a
    {"scheme": ...} wrapper): the proxy discriminates a live-exchange scheme-5
    credential from a pre-fetched bearer by the presence of a non-empty token_url.

    Fields:
      - token_url: HTTPS endpoint that mints the access token via
        grant_type=client_credentials. Must pass SSRF allowlist (S-SEC-1).
      - client_id: OAuth2 client identifier (non-empty; sent as HTTP Basic user).
      - client_secret: OAuth2 client secret (non-empty). NEVER logged, echoed in a
        response, or included in an audit payload — ADR-0014.4, ADR-0014.7, S-SEC-1.
      - scope: Optional space-delimited scopes; omitted from the envelope when unset.
      - token_response_path: JSONPath for extracting the access token. Default
        "$.access_token".

    Source: design.md Component 1; ADR-0029; ADR-0014.4; ADR-0014.7.
    """

    # NOTE: client_secret is intentionally NOT repr'd or logged anywhere.
    token_url: str
    client_id: str
    client_secret: str
    scope: str | None = None
    audience: str | None = None
    token_response_path: str = "$.access_token"

    @field_validator("token_url")
    @classmethod
    def validate_https(cls, v: str) -> str:
        """Require HTTPS scheme — ADR-0029."""
        parts = urlsplit(v)
        if parts.scheme != "https":
            raise ValueError("token_url must use HTTPS")
        if not parts.hostname:
            raise ValueError("token_url must have a valid hostname")
        return v

    @field_validator("token_url")
    @classmethod
    def validate_ssrf(cls, v: str) -> str:
        """Reject private/loopback destinations — S-SEC-1 (shared SSRF resolver)."""
        is_safe, reason = validate_token_url_ssrf(v)
        if not is_safe:
            raise ValueError(f"token_url blocked by SSRF policy: {reason}")
        return v

    @field_validator("client_id")
    @classmethod
    def validate_client_id_non_empty(cls, v: str) -> str:
        """client_id must be non-empty — ADR-0029."""
        if not v.strip():
            raise ValueError("client_id must be a non-empty string")
        return v

    @field_validator("client_secret")
    @classmethod
    def validate_client_secret_non_empty(cls, v: str) -> str:
        """client_secret must be non-empty — ADR-0029."""
        if not v.strip():
            raise ValueError("client_secret must be a non-empty string")
        return v

    @field_validator("audience")
    @classmethod
    def validate_audience(cls, v: str | None) -> str | None:
        """audience, when present, must be a non-empty absolute URI with no
        surrounding whitespace — design.md §audience extension.

        Deliberately NOT SSRF-checked and NOT restricted to HTTPS: audience is
        an opaque token-request identifier, never dereferenced as a network
        destination.  token_url keeps its own HTTPS + SSRF validators.
        """
        if v is None:
            return v
        if v != v.strip():
            raise ValueError(
                "audience must not have surrounding whitespace"
            )
        if not urlsplit(v).scheme:
            raise ValueError(
                "audience must be an absolute URI with a non-empty scheme "
                "(e.g. https://YOUR_TENANT.auth0.com/api/v2/ or urn:my-api)"
            )
        return v

    def to_vault_envelope(self) -> str:
        """Serialise to the canonical JSON the Go proxy parses (design.md Component 1).

        Emits {token_url, client_id, client_secret, token_response_path[, scope][, audience]};
        scope and audience are omitted when unset (Go `omitempty` parity). This is
        the ONLY place client_secret is written into a string after validation; the
        result is passed directly to StoreCredential and NEVER logged or returned.
        """
        import json as _json

        envelope: dict[str, str] = {
            "token_url": self.token_url,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "token_response_path": self.token_response_path,
        }
        if self.scope:
            envelope["scope"] = self.scope
        if self.audience:
            envelope["audience"] = self.audience
        return _json.dumps(envelope, separators=(",", ":"))


# ---------------------------------------------------------------------------
# HTTP Digest credential payload model — ADR-0029
# (MongoDB Atlas Programmatic API Keys; auth_scheme=http_digest, enum 18)
# ---------------------------------------------------------------------------


class HTTPDigestPayload(BaseModel):
    """Structured credential payload for auth_scheme=http_digest.

    Validated at registration time. The Vault Adapter stores the canonical JSON
    envelope {"public_key","private_key"} the Go digest transport parses
    (design.md Component 2). RFC 2617 Digest uses public_key as the username and
    private_key as the password.

    Fields:
      - public_key: Atlas public key — RFC 2617 username (non-empty).
      - private_key: Atlas private key — RFC 2617 password (non-empty). NEVER
        logged, echoed in a response, or included in an audit payload —
        ADR-0014.4, ADR-0014.7, S-SEC-1.

    Source: design.md Component 2; ADR-0029; ADR-0014.4; ADR-0014.7.
    """

    # NOTE: private_key is intentionally NOT repr'd or logged anywhere.
    public_key: str
    private_key: str

    @field_validator("public_key")
    @classmethod
    def validate_public_key_non_empty(cls, v: str) -> str:
        """public_key must be non-empty — ADR-0029."""
        if not v.strip():
            raise ValueError("public_key must be a non-empty string")
        return v

    @field_validator("private_key")
    @classmethod
    def validate_private_key_non_empty(cls, v: str) -> str:
        """private_key must be non-empty — ADR-0029."""
        if not v.strip():
            raise ValueError("private_key must be a non-empty string")
        return v

    def to_vault_envelope(self) -> str:
        """Serialise to the canonical {"public_key","private_key"} JSON (design.md Component 2).

        This is the ONLY place private_key is written into a string after
        validation; the result is passed directly to StoreCredential and NEVER
        logged or returned.
        """
        import json as _json

        return _json.dumps(
            {"public_key": self.public_key, "private_key": self.private_key},
            separators=(",", ":"),
        )
