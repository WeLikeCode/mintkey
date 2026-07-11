"""
Unit tests for the two MongoDB Atlas Administration API service templates.

Covers (OpenSpec change mongodb-atlas-admin-api, capability
mongodb-atlas-service-templates):
  1. Both Atlas templates load from service_templates.yaml with the pinned
     auth_type / base_url / openapi_spec_url / test_path / category.
  2. Both templates carry the mandatory `Accept` version-header instruction,
     verbatim, in BOTH the agent-visible `description` AND operator
     `config_notes`.
  3. from-template creates a service with the right `auth_scheme` and base_url.
"""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from admin_api.templates.registry import TemplateRegistry, _load_templates

ATLAS_BASE_URL = "https://cloud.mongodb.com/api/atlas/v2"
ATLAS_OPENAPI_URL = "https://mongodb.com/docs/atlas/reference/api-resources-spec/v2"

# The version-header instruction that MUST appear verbatim in both the
# agent-visible description and the operator config_notes of both templates.
VERSION_HEADER_TEXT = (
    "REQUIRED: send `Accept: application/vnd.atlas.<yyyy-mm-dd>+json` "
    "(e.g. `2025-03-12`) on every request — the Atlas API returns 406 without "
    "it. Mintkey forwards request headers to MongoDB unchanged; it does not add "
    "this header for you."
)


# ---------------------------------------------------------------------------
# 1: YAML loads both Atlas templates with the pinned fields
# ---------------------------------------------------------------------------


class TestAtlasTemplateYamlLoading:
    def setup_method(self) -> None:
        self.by_id = {t.template_id: t for t in _load_templates()}

    def test_service_account_template_fields(self) -> None:
        t = self.by_id["mongodb-atlas-service-account"]
        assert t.kind == "http_service"
        assert t.auth_type == "oauth2_client_credentials"
        assert t.base_url == ATLAS_BASE_URL
        assert t.openapi_spec_url == ATLAS_OPENAPI_URL
        assert t.test_path == "/groups"
        assert t.category == "database"

    def test_api_key_template_fields(self) -> None:
        t = self.by_id["mongodb-atlas-api-key"]
        assert t.kind == "http_service"
        assert t.auth_type == "http_digest"
        assert t.base_url == ATLAS_BASE_URL
        assert t.openapi_spec_url == ATLAS_OPENAPI_URL
        assert t.test_path == "/groups"
        assert t.category == "database"


# ---------------------------------------------------------------------------
# 2: version-header instruction present verbatim in description + config_notes
# ---------------------------------------------------------------------------


class TestAtlasVersionHeaderGuidance:
    def setup_method(self) -> None:
        self.by_id = {t.template_id: t for t in _load_templates()}

    @pytest.mark.parametrize(
        "template_id",
        ["mongodb-atlas-service-account", "mongodb-atlas-api-key"],
    )
    def test_version_header_in_description_and_config_notes(
        self, template_id: str
    ) -> None:
        t = self.by_id[template_id]
        assert t.description is not None
        assert VERSION_HEADER_TEXT in t.description, (
            f"{template_id} description missing verbatim version-header text"
        )
        assert t.config_notes is not None
        assert VERSION_HEADER_TEXT in t.config_notes, (
            f"{template_id} config_notes missing verbatim version-header text"
        )


# ---------------------------------------------------------------------------
# 3: registry filter + lookup
# ---------------------------------------------------------------------------


class TestAtlasTemplateRegistry:
    def setup_method(self) -> None:
        self.registry = TemplateRegistry(_load_templates())

    def test_both_atlas_templates_in_database_category(self) -> None:
        ids = {t.template_id for t in self.registry.list_all(category="database")}
        assert "mongodb-atlas-service-account" in ids
        assert "mongodb-atlas-api-key" in ids


# ---------------------------------------------------------------------------
# 4: from-template creates a service with the right auth_scheme + base_url
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAtlasFromTemplate:
    @pytest.mark.parametrize(
        ("template_id", "expected_auth_scheme"),
        [
            ("mongodb-atlas-service-account", "oauth2_client_credentials"),
            ("mongodb-atlas-api-key", "http_digest"),
        ],
    )
    async def test_from_template_sets_auth_scheme_and_base_url(
        self, template_id: str, expected_auth_scheme: str
    ) -> None:
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
                body=FromTemplateRequest(template_id=template_id),
                session=session,
            )

        assert resp.status_code == 201
        body = json.loads(resp.body)
        assert body["auth_scheme"] == expected_auth_scheme
        assert body["base_url"] == ATLAS_BASE_URL
        assert body["template_id"] == template_id
