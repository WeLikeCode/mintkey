"""
Unit tests for the Auth0 Management API service template.

Covers (OpenSpec change auth0-management-template):
  (a) YAML loads with pinned auth_type / base_url / openapi_spec_url /
      test_path / category.
  (b) credential_hint SURVIVES registry loading with token_url,
      token_response_path, and all three credential_fields keys
      (client_id, client_secret, audience) — guards the CredentialHint
      extra='ignore' behaviour; contrast with the Atlas flat-key wrinkle
      where top-level client_id/client_secret are silently dropped.
  (c) config_notes contains "YOUR_TENANT" and the trailing-slash audience
      instruction.
  (d) from-template returns 201 with auth_scheme oauth2_client_credentials
      and the placeholder base_url (mirrors the Atlas test's SSRF-gate
      patching style).

NOTE: The pre-existing Atlas flat-hint-key wrinkle (mongodb-atlas-service-account
template carries flat client_id/client_secret keys at the credential_hint level
that are silently dropped by CredentialHint extra='ignore') is NOT fixed here —
surgical changes only.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from admin_api.templates.registry import TemplateRegistry, _load_templates

AUTH0_TEMPLATE_ID = "auth0-management"
AUTH0_BASE_URL = "https://YOUR_TENANT.auth0.com/api/v2"
AUTH0_OPENAPI_URL = "https://auth0.com/docs/oas/management/v2/management-api-oas.json"
AUTH0_TOKEN_URL = "https://YOUR_TENANT.auth0.com/oauth/token"
AUTH0_TOKEN_RESPONSE_PATH = "$.access_token"


# ---------------------------------------------------------------------------
# (a) YAML loads with the pinned fields
# ---------------------------------------------------------------------------


class TestAuth0TemplateYamlLoading:
    def setup_method(self) -> None:
        self.by_id = {t.template_id: t for t in _load_templates()}

    def test_template_present(self) -> None:
        assert AUTH0_TEMPLATE_ID in self.by_id, (
            "auth0-management template not found in service_templates.yaml"
        )

    def test_auth_type(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.auth_type == "oauth2_client_credentials"

    def test_base_url(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.base_url == AUTH0_BASE_URL

    def test_openapi_spec_url(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.openapi_spec_url == AUTH0_OPENAPI_URL

    def test_test_path(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.test_path == "/clients"

    def test_category(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.category == "identity"


# ---------------------------------------------------------------------------
# (b) credential_hint survives registry loading with all three keys
# ---------------------------------------------------------------------------


class TestAuth0CredentialHintSurvival:
    def setup_method(self) -> None:
        self.by_id = {t.template_id: t for t in _load_templates()}

    def test_credential_hint_present(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.credential_hint is not None, "credential_hint must not be None"

    def test_token_url_survives(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.credential_hint is not None
        assert t.credential_hint.token_url == AUTH0_TOKEN_URL

    def test_token_response_path_survives(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.credential_hint is not None
        assert t.credential_hint.token_response_path == AUTH0_TOKEN_RESPONSE_PATH

    def test_credential_fields_present(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.credential_hint is not None
        assert t.credential_hint.credential_fields is not None, (
            "credential_fields must not be None after loading"
        )

    def test_client_id_in_credential_fields(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.credential_hint is not None
        assert t.credential_hint.credential_fields is not None
        assert "client_id" in t.credential_hint.credential_fields

    def test_client_secret_in_credential_fields(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.credential_hint is not None
        assert t.credential_hint.credential_fields is not None
        assert "client_secret" in t.credential_hint.credential_fields

    def test_audience_in_credential_fields(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.credential_hint is not None
        assert t.credential_hint.credential_fields is not None
        assert "audience" in t.credential_hint.credential_fields, (
            "audience key must survive registry loading in credential_fields"
        )


# ---------------------------------------------------------------------------
# (c) config_notes contains YOUR_TENANT and trailing-slash audience instruction
# ---------------------------------------------------------------------------


class TestAuth0ConfigNotes:
    def setup_method(self) -> None:
        self.by_id = {t.template_id: t for t in _load_templates()}

    def test_config_notes_present(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.config_notes is not None

    def test_config_notes_contains_your_tenant(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.config_notes is not None
        assert "YOUR_TENANT" in t.config_notes, (
            "config_notes must instruct operator to replace YOUR_TENANT"
        )

    def test_config_notes_contains_trailing_slash_instruction(self) -> None:
        t = self.by_id[AUTH0_TEMPLATE_ID]
        assert t.config_notes is not None
        assert "trailing slash" in t.config_notes.lower(), (
            "config_notes must state that audience must include the trailing slash"
        )


# ---------------------------------------------------------------------------
# (d) from-template returns 201 with oauth2_client_credentials + placeholder base_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAuth0FromTemplate:
    async def test_from_template_sets_auth_scheme_and_base_url(self) -> None:
        from admin_api.api.services import (
            FromTemplateRequest,
            create_service_from_template,
        )

        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock())
        tenant_id = uuid.uuid4()

        with patch(
            "admin_api.api.services.audit_emit", new_callable=AsyncMock
        ), patch(
            "admin_api.api.services.notify_change", new_callable=AsyncMock
        ), patch(
            "admin_api.api.services.set_tenant_context", new_callable=AsyncMock
        ), patch(
            "admin_api.api.services._is_forbidden_destination", return_value=False
        ):
            resp = await create_service_from_template(
                tenant_id=tenant_id,
                body=FromTemplateRequest(template_id=AUTH0_TEMPLATE_ID),
                session=session,
            )

        assert resp.status_code == 201
        body = json.loads(resp.body)
        assert body["auth_scheme"] == "oauth2_client_credentials"
        assert body["base_url"] == AUTH0_BASE_URL
        assert body["template_id"] == AUTH0_TEMPLATE_ID
