"""
Unit tests for the email service template feature.

Covers:
  1. YAML template parsing: 4 email templates load with correct kind=email_service.
  2. Existing HTTP templates still default to kind=http_service.
  3. template-list endpoint includes email templates with kind field.
  4. from-template logic: correct fields pre-filled, audit payload correct.
  5. from-template with name override uses the override.
  6. from-template rejects http_service template_id.
  7. from-template returns 404 for unknown template_id.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from admin_api.templates.models import ServiceTemplate
from admin_api.templates.registry import TemplateRegistry, _load_templates


# ---------------------------------------------------------------------------
# 1 + 2: YAML loads correctly
# ---------------------------------------------------------------------------


class TestEmailTemplateYamlLoading:
    """Verify the four email templates load from service_templates.yaml."""

    def setup_method(self) -> None:
        self.templates = _load_templates()
        self.by_id = {t.template_id: t for t in self.templates}

    def test_four_email_templates_loaded(self) -> None:
        """Exactly 4 email templates must load."""
        email_tpls = [t for t in self.templates if t.kind == "email_service"]
        assert len(email_tpls) == 4

    def test_gmail_template_fields(self) -> None:
        t = self.by_id["email_gmail_oauth2"]
        assert t.kind == "email_service"
        assert t.imap_host == "imap.gmail.com"
        assert t.imap_port == 993
        assert t.smtp_host == "smtp.gmail.com"
        assert t.smtp_port == 465
        assert t.auth_scheme == "email_oauth2"
        assert t.provider == "gmail"
        assert t.category == "email"

    def test_outlook_template_fields(self) -> None:
        t = self.by_id["email_outlook_oauth2"]
        assert t.kind == "email_service"
        assert t.imap_host == "outlook.office365.com"
        assert t.imap_port == 993
        assert t.smtp_host == "smtp.office365.com"
        assert t.smtp_port == 587
        assert t.auth_scheme == "email_oauth2"
        assert t.provider == "outlook"

    def test_icloud_template_fields(self) -> None:
        t = self.by_id["email_icloud_app_password"]
        assert t.kind == "email_service"
        assert t.imap_host == "imap.mail.me.com"
        assert t.smtp_host == "smtp.mail.me.com"
        assert t.auth_scheme == "email_app_password"
        assert t.provider == "generic"

    def test_generic_imap_smtp_template_fields(self) -> None:
        t = self.by_id["email_generic_imap_smtp"]
        assert t.kind == "email_service"
        assert t.imap_host == ""  # operator fills this
        assert t.smtp_host == ""  # operator fills this
        assert t.imap_port == 993
        assert t.smtp_port == 587
        assert t.auth_scheme == "email_password"
        assert t.provider == "generic"

    def test_tailscale_template_fields(self) -> None:
        t = self.by_id.get("tailscale")
        assert t is not None, "tailscale template must be present"
        assert t.kind == "http_service"
        assert t.auth_type == "bearer_token"
        assert t.base_url == "https://api.tailscale.com"
        assert t.test_path == "/api/v2/tailnet/-/devices"
        assert t.category == "networking"

    def test_existing_http_templates_default_to_http_service_kind(self) -> None:
        """Legacy HTTP templates must have kind=http_service (backward compat)."""
        http_tpls = [t for t in self.templates if t.kind == "http_service"]
        # At least the well-known ones must be present
        http_ids = {t.template_id for t in http_tpls}
        assert "github" in http_ids
        assert "stripe" in http_ids
        assert "gitlab" in http_ids
        assert "slack" in http_ids
        assert "tailscale" in http_ids

    def test_no_http_template_has_email_kind(self) -> None:
        """None of the HTTP templates should accidentally get kind=email_service."""
        http_tpls = [t for t in self.templates if t.template_id not in {
            "email_gmail_oauth2", "email_outlook_oauth2",
            "email_icloud_app_password", "email_generic_imap_smtp",
        }]
        for t in http_tpls:
            assert t.kind == "http_service", (
                f"Template {t.template_id!r} has unexpected kind={t.kind!r}"
            )


# ---------------------------------------------------------------------------
# 3: Registry.list_all() filters correctly
# ---------------------------------------------------------------------------


class TestEmailTemplateRegistry:
    """Registry filter and lookup behave correctly for email templates."""

    def setup_method(self) -> None:
        templates = _load_templates()
        self.registry = TemplateRegistry(templates)

    def test_list_all_category_email_returns_four(self) -> None:
        results = self.registry.list_all(category="email")
        assert len(results) == 4
        ids = {t.template_id for t in results}
        assert "email_gmail_oauth2" in ids
        assert "email_outlook_oauth2" in ids
        assert "email_icloud_app_password" in ids
        assert "email_generic_imap_smtp" in ids

    def test_get_gmail_template_by_id(self) -> None:
        t = self.registry.get("email_gmail_oauth2")
        assert t is not None
        assert t.kind == "email_service"

    def test_email_templates_do_not_appear_in_http_category(self) -> None:
        ci_results = self.registry.list_all(category="ci_cd")
        email_ids = {"email_gmail_oauth2", "email_outlook_oauth2",
                     "email_icloud_app_password", "email_generic_imap_smtp"}
        for t in ci_results:
            assert t.template_id not in email_ids


# ---------------------------------------------------------------------------
# 4–7: from-template endpoint logic (mocked DB)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmailServiceFromTemplate:
    """Unit tests for create_email_service_from_template() with mocked DB."""

    def _mock_session(self) -> AsyncMock:
        session = AsyncMock()
        session.execute = AsyncMock(return_value=MagicMock())
        return session

    async def test_gmail_template_pre_fills_hosts_and_auth(self) -> None:
        """from-template with gmail template pre-fills correct imap/smtp/auth."""
        from admin_api.api.email_services import create_email_service_from_template
        from admin_api.api.email_services import EmailServiceFromTemplate

        session = self._mock_session()
        tenant_id = uuid.uuid4()

        captured: dict[str, Any] = {}

        async def _fake_execute(query: Any, params: dict[str, Any] | None = None) -> MagicMock:
            if params and "imap_host" in params:
                captured.update(params)
            return MagicMock()

        session.execute = _fake_execute

        with patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock) as mock_audit, \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            resp = await create_email_service_from_template(
                tenant_id=tenant_id,
                body=EmailServiceFromTemplate(template_id="email_gmail_oauth2"),
                session=session,
            )

        assert resp.status_code == 201
        import json
        body = json.loads(resp.body)
        assert body["imap_host"] == "imap.gmail.com"
        assert body["imap_port"] == 993
        assert body["smtp_host"] == "smtp.gmail.com"
        assert body["smtp_port"] == 465
        assert body["auth_scheme"] == "email_oauth2"
        assert body["provider"] == "gmail"

        # Audit event must be emitted
        assert mock_audit.called
        call_kwargs = mock_audit.call_args[1]
        assert call_kwargs["event_type"] == "email.service.registered"
        assert call_kwargs["payload"]["template_id"] == "email_gmail_oauth2"

    async def test_name_override_is_used_when_provided(self) -> None:
        """Optional name override replaces the template default name."""
        from admin_api.api.email_services import create_email_service_from_template
        from admin_api.api.email_services import EmailServiceFromTemplate

        session = self._mock_session()
        tenant_id = uuid.uuid4()

        with patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            resp = await create_email_service_from_template(
                tenant_id=tenant_id,
                body=EmailServiceFromTemplate(
                    template_id="email_gmail_oauth2",
                    name="My Company Gmail",
                ),
                session=session,
            )

        import json
        body = json.loads(resp.body)
        assert body["name"] == "My Company Gmail"

    async def test_unknown_template_id_returns_404(self) -> None:
        """Non-existent template_id must return 404."""
        from admin_api.api.email_services import create_email_service_from_template
        from admin_api.api.email_services import EmailServiceFromTemplate

        session = self._mock_session()
        tenant_id = uuid.uuid4()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            resp = await create_email_service_from_template(
                tenant_id=tenant_id,
                body=EmailServiceFromTemplate(template_id="does_not_exist"),
                session=session,
            )

        assert resp.status_code == 404
        import json
        body = json.loads(resp.body)
        assert body["mintkey:code"] == "template_not_found"

    async def test_http_template_id_returns_422_wrong_kind(self) -> None:
        """Using an http_service template_id must return 422 wrong_template_kind."""
        from admin_api.api.email_services import create_email_service_from_template
        from admin_api.api.email_services import EmailServiceFromTemplate

        session = self._mock_session()
        tenant_id = uuid.uuid4()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            resp = await create_email_service_from_template(
                tenant_id=tenant_id,
                body=EmailServiceFromTemplate(template_id="github"),
                session=session,
            )

        assert resp.status_code == 422
        import json
        body = json.loads(resp.body)
        assert body["mintkey:code"] == "wrong_template_kind"
        assert "email_service" in body["title"]

    async def test_outlook_template_pre_fills_correct_smtp_port(self) -> None:
        """Outlook template uses smtp.office365.com:587."""
        from admin_api.api.email_services import create_email_service_from_template
        from admin_api.api.email_services import EmailServiceFromTemplate

        session = self._mock_session()
        tenant_id = uuid.uuid4()

        with patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            resp = await create_email_service_from_template(
                tenant_id=tenant_id,
                body=EmailServiceFromTemplate(template_id="email_outlook_oauth2"),
                session=session,
            )

        import json
        body = json.loads(resp.body)
        assert body["smtp_host"] == "smtp.office365.com"
        assert body["smtp_port"] == 587
        assert body["imap_host"] == "outlook.office365.com"
