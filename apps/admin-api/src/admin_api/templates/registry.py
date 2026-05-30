"""In-memory template registry loaded from YAML at import time.

Source: design §1 TemplateRegistry; Requirements 1.1, 1.3, 1.4, 2.3, 2.4.
"""

from __future__ import annotations

import importlib.resources
import logging

import yaml
from pydantic import ValidationError

from admin_api.templates.models import ServiceTemplate

logger = logging.getLogger(__name__)


class TemplateRegistry:
    """In-memory catalog of service templates loaded from YAML."""

    def __init__(self, templates: list[ServiceTemplate]) -> None:
        self._templates = templates
        self._by_id: dict[str, ServiceTemplate] = {
            t.template_id: t for t in templates
        }

    def list_all(
        self,
        category: str | None = None,
        search: str | None = None,
    ) -> list[ServiceTemplate]:
        """Return templates filtered by optional category and search term.

        The search filter is case-insensitive and matches against
        name, display_name, and description fields.
        """
        results = self._templates

        if category is not None:
            results = [t for t in results if t.category == category]

        if search is not None:
            term = search.lower()
            results = [
                t
                for t in results
                if term in t.name.lower()
                or term in t.display_name.lower()
                or term in t.description.lower()
            ]

        return results

    def get(self, template_id: str) -> ServiceTemplate | None:
        """Return a single template by ID, or None if not found."""
        return self._by_id.get(template_id)


def _load_templates() -> list[ServiceTemplate]:
    """Load and validate templates from the bundled YAML file.

    Malformed entries are skipped with a warning log (Req 1.4).
    If the file is missing or unreadable, returns an empty list.
    """
    templates: list[ServiceTemplate] = []

    try:
        yaml_path = importlib.resources.files("admin_api.templates").joinpath(
            "service_templates.yaml"
        )
        raw = yaml_path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError) as exc:
        logger.warning(
            "template_registry.load_failed: could not read service_templates.yaml — %s",
            exc,
        )
        return templates

    try:
        data = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        logger.warning(
            "template_registry.yaml_parse_failed: %s",
            exc,
        )
        return templates

    if not isinstance(data, dict) or "templates" not in data:
        logger.warning(
            "template_registry.invalid_structure: expected top-level 'templates' key"
        )
        return templates

    entries = data["templates"]
    if not isinstance(entries, list):
        logger.warning(
            "template_registry.invalid_structure: 'templates' must be a list"
        )
        return templates

    for idx, entry in enumerate(entries):
        try:
            template = ServiceTemplate.model_validate(entry)
            templates.append(template)
        except (ValidationError, TypeError) as exc:
            template_id = entry.get("template_id", f"<index {idx}>") if isinstance(entry, dict) else f"<index {idx}>"
            logger.warning(
                "template_registry.malformed_entry: skipping template_id=%s — %s",
                template_id,
                exc,
            )

    return templates


# Module-level singleton — loaded at import time (Req 1.1).
registry = TemplateRegistry(_load_templates())
