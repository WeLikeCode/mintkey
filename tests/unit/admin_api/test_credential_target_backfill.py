"""
Unit tests: the credential-target backfill changelog.

Requirement: proxy-stored-target › Stored targets of existing credentials are
filled from the service's base URL.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

CHANGELOG_DIR = Path(REPO_ROOT) / "apps" / "admin-api" / "db" / "changelog"
BACKFILL_FILE = CHANGELOG_DIR / "033-credential-target-backfill.yaml"
MASTER_FILE = CHANGELOG_DIR / "db.changelog-master.yaml"


def _normalise(text: str) -> str:
    """Lower-case and collapse runs of whitespace so fragments match across line wraps."""
    return " ".join(text.lower().split())


def _change_sets(changelog: Any) -> list[dict[str, Any]]:
    return [entry["changeSet"] for entry in changelog["databaseChangeLog"] if "changeSet" in entry]


def _sql_changes(changelog: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for change_set in _change_sets(changelog):
        for change in change_set.get("changes") or []:
            if isinstance(change, dict) and "sql" in change:
                found.append(change)
    return found


def _find_table_exists(node: Any) -> dict[str, Any] | None:
    if isinstance(node, dict):
        if "tableExists" in node:
            return node["tableExists"]
        for value in node.values():
            found = _find_table_exists(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_table_exists(item)
            if found is not None:
                return found
    return None


@pytest.mark.l4("C-7ac56330")
def test_C_7ac56330_backfill_changelog_fills_empty_targets_only() -> None:
    assert BACKFILL_FILE.is_file(), (
        f"missing changelog {BACKFILL_FILE.name}: stored targets of existing "
        "credentials are never filled from the service's base URL"
    )
    changelog = yaml.safe_load(BACKFILL_FILE.read_text())

    sql_changes = _sql_changes(changelog)
    assert len(sql_changes) == 1, "the backfill changelog must hold exactly one SQL change"
    sql_text = _normalise(sql_changes[0]["sql"]["sql"])

    for fragment in (
        "update vault.credentials",
        "set target_url",
        "public.services",
        "s.id = vc.service_id",
        "s.tenant_id = vc.tenant_id",
        "target_url = ''",
        "~* '^https?://'",
        "set_config('app.platform_admin_view', 'on', true)",
    ):
        assert fragment in sql_text, f"backfill SQL is missing {fragment!r}"

    change_set = next(cs for cs in _change_sets(changelog) if cs.get("changes"))
    preconditions = change_set.get("preConditions") or []
    assert any(
        isinstance(p, dict) and str(p.get("onFail", "")).upper() == "MARK_RAN"
        for p in preconditions
    ), "the change set must MARK_RAN when its precondition fails"
    table_exists = _find_table_exists(preconditions)
    assert table_exists is not None, "the change set must guard on tableExists"
    assert str(table_exists.get("schemaName", "")).lower() == "vault"
    assert str(table_exists.get("tableName", "")).lower() == "credentials"
    assert change_set.get("rollback"), "the change set must define a rollback"

    master = yaml.safe_load(MASTER_FILE.read_text())
    includes = [
        entry["include"]
        for entry in master["databaseChangeLog"]
        if isinstance(entry, dict) and "include" in entry
    ]
    matching = [
        inc
        for inc in includes
        if str(inc.get("file", "")).endswith("033-credential-target-backfill.yaml")
    ]
    assert len(matching) == 1, (
        "db.changelog-master.yaml must include 033-credential-target-backfill.yaml exactly once"
    )
