"""
Pydantic models for the service template catalog.

Defines the schema for service templates loaded from service_templates.yaml.
Templates are read-only seed data — no database persistence.

Requirements: 1.3 (field validation), 18.1 (semver versioning).
Source: design §2 ServiceTemplate model.

kind discriminator (ADR-0024 corrigendum):
  http_service  — existing HTTP/REST service templates (default)
  email_service — IMAP+SMTP email service templates; carry imap_host/port +
                  smtp_host/port instead of a single base_url
"""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, field_validator


_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)

# Integer version allowed by email templates (not semver).
_INT_VERSION_RE = re.compile(r"^\d+$")


class OAuth2CredentialHint(BaseModel):
    """Credential hint for oauth2_password_grant auth type."""

    token_url: str
    credential_fields: dict[str, str]  # field_name -> placeholder
    token_response_path: str


class CredentialHint(BaseModel):
    """Credential hint — supports both simple auth types and oauth2_password_grant."""

    # Fields for simple auth types (bearer_token, api_key_header, basic_auth)
    field: str | None = None
    help: str | None = None
    format: str | None = None

    # Fields for oauth2_password_grant
    token_url: str | None = None
    credential_fields: dict[str, str] | None = None
    token_response_path: str | None = None


class ServiceTemplate(BaseModel):
    """A single service template from the catalog.

    kind defaults to 'http_service' for all legacy entries — additive field.
    email_service entries carry imap_host/port + smtp_host/port; base_url is
    optional (None) for them.
    provider is optional metadata used by the email-service from-template
    endpoint to set the provider column.
    """

    template_id: str
    kind: Literal["http_service", "email_service"] = "http_service"
    name: str
    display_name: str
    description: str = ""
    # HTTP service fields (required for http_service, absent for email_service)
    base_url: str | None = None
    auth_type: str | None = None  # kept for http_service compat
    openapi_spec_url: str | None = None
    category: str
    version: str
    config_notes: str | None = None
    credential_hint: CredentialHint | None = None
    test_path: str | None = None

    # Email service fields (only set for kind=email_service)
    provider: str | None = None
    imap_host: str | None = None
    imap_port: int | None = None
    smtp_host: str | None = None
    smtp_port: int | None = None
    auth_scheme: str | None = None  # email_oauth2 | email_app_password | email_password

    @field_validator("version", mode="before")
    @classmethod
    def validate_version(cls, v: object) -> str:
        """Accept full semver (e.g. 1.0.0) OR bare integer (e.g. 1) for email templates."""
        s = str(v)
        if _SEMVER_RE.match(s):
            return s
        if _INT_VERSION_RE.match(s):
            return s
        raise ValueError(
            f"version must follow semantic versioning (e.g. '1.0.0') or be a bare "
            f"integer (e.g. '1'), got '{s}'"
        )
