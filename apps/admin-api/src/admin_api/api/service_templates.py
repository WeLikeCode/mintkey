"""
Service template endpoints — OPS-R.

GET /v1/service-templates          — list templates (filterable by category, search)
GET /v1/service-templates/{template_id}   — get a single template by ID

Templates are loaded from the YAML-based TemplateRegistry at startup.
No auth beyond what the rest of /v1 enforces (OperatorSession or OperatorBearer).
Read-only, non-sensitive — no audit emission required.

Source: design §3 FastAPI Router — Service Templates.
Requirements: 2.1, 2.2, 2.3, 2.4, 18.3.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from admin_api.templates.models import ServiceTemplate
from admin_api.templates.registry import registry

router = APIRouter(prefix="/v1/service-templates")


def _template_to_list_item(t: ServiceTemplate) -> dict[str, Any]:
    """Map a ServiceTemplate to the list-item wire representation.

    Includes all fields required by Req 2.2 and 18.3, plus the kind
    discriminator so clients can distinguish http_service from email_service.
    Email templates also carry imap_host/port + smtp_host/port; base_url is
    None for them.
    """
    item: dict[str, Any] = {
        "template_id": t.template_id,
        "kind": t.kind,
        "name": t.name,
        "display_name": t.display_name,
        "description": t.description,
        "base_url": t.base_url,
        "auth_type": t.auth_type,
        "auth_scheme": t.auth_scheme,
        "openapi_spec_url": t.openapi_spec_url,
        "category": t.category,
        "version": t.version,
    }
    # Additive: include email fields when present (non-None)
    if t.kind == "email_service":
        item["provider"] = t.provider
        item["imap_host"] = t.imap_host
        item["imap_port"] = t.imap_port
        item["smtp_host"] = t.smtp_host
        item["smtp_port"] = t.smtp_port
    return item


@router.get("")
async def list_templates(
    category: Optional[str] = None,
    search: Optional[str] = None,
) -> JSONResponse:
    """
    List all service templates, optionally filtered by category and/or search term.

    Query parameters:
      category — filter to templates matching this category (exact match)
      search — case-insensitive substring match across name, display_name, description

    Source: Req 2.1, 2.2, 2.3, 2.4, 18.3.
    """
    templates = registry.list_all(category=category, search=search)
    items = [_template_to_list_item(t) for t in templates]
    return JSONResponse({"templates": items})


@router.get("/{template_id}")
async def get_template(template_id: str) -> JSONResponse:
    """
    Get a single template by ID.

    Returns 404 with mintkey:code=template_not_found for unknown IDs.

    Source: Req 3.1, 3.2.
    """
    template = registry.get(template_id)
    if template is None:
        return JSONResponse(
            status_code=404,
            content={
                "mintkey:code": "template_not_found",
                "title": f"Template '{template_id}' not found",
            },
        )
    # Full detail includes config_notes and credential_hint
    detail = _template_to_list_item(template)
    detail["config_notes"] = template.config_notes
    detail["test_path"] = template.test_path
    if template.credential_hint is not None:
        detail["credential_hint"] = template.credential_hint.model_dump(
            exclude_none=True
        )
    else:
        detail["credential_hint"] = None
    return JSONResponse(detail)
