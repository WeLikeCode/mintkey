"""
Pydantic models for the service template catalog.

Defines the schema for service templates loaded from service_templates.yaml.
Templates are read-only seed data — no database persistence.

Requirements: 1.3 (field validation), 18.1 (semver versioning).
Source: design §2 ServiceTemplate model.
"""
from __future__ import annotations

import re

from pydantic import BaseModel, field_validator


_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-((?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*)"
    r"(?:\.(?:0|[1-9]\d*|\d*[a-zA-Z-][0-9a-zA-Z-]*))*))?"
    r"(?:\+([0-9a-zA-Z-]+(?:\.[0-9a-zA-Z-]+)*))?$"
)


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
    """A single service template from the catalog."""

    template_id: str
    name: str
    display_name: str
    description: str
    base_url: str
    auth_type: str
    openapi_spec_url: str | None = None
    category: str
    version: str
    config_notes: str | None = None
    credential_hint: CredentialHint | None = None
    test_path: str | None = None

    @field_validator("version")
    @classmethod
    def validate_semver(cls, v: str) -> str:
        """Validate that version follows semantic versioning (e.g. 1.0.0)."""
        if not _SEMVER_RE.match(v):
            raise ValueError(
                f"version must follow semantic versioning (e.g. '1.0.0'), got '{v}'"
            )
        return v
