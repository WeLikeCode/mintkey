"""
Unit tests: the credential egress-scope changelog.

Requirement: proxy-public-egress › The vault stores an egress scope with each
credential › the changelog adds the column.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

import pytest
import yaml

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))

CHANGELOG_DIR = Path(REPO_ROOT) / "apps" / "admin-api" / "db" / "changelog"
EGRESS_FILE = CHANGELOG_DIR / "034-credential-egress-scope.yaml"
MASTER_FILE = CHANGELOG_DIR / "db.changelog-master.yaml"


def _normalise(text: str) -> str:
    """Lower-case and collapse runs of whitespace so fragments match across line wraps."""
    return " ".join(text.lower().split())


def _change_sets(changelog: Any) -> list[dict[str, Any]]:
    return [
        entry["changeSet"]
        for entry in changelog["databaseChangeLog"]
        if isinstance(entry, dict) and "changeSet" in entry
    ]


def _sql_changes(changelog: Any) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for change_set in _change_sets(changelog):
        for change in change_set.get("changes") or []:
            if isinstance(change, dict) and "sql" in change:
                found.append(change)
    return found


def _find_not_column_exists(node: Any) -> dict[str, Any] | None:
    """Return the columnExists guard nested under a `not`, if any."""
    if isinstance(node, dict):
        negation = node.get("not")
        if isinstance(negation, dict) and "columnExists" in negation:
            found = negation["columnExists"]
            if isinstance(found, dict):
                return found
        for value in node.values():
            found = _find_not_column_exists(value)
            if found is not None:
                return found
    elif isinstance(node, list):
        for item in node:
            found = _find_not_column_exists(item)
            if found is not None:
                return found
    return None


def _strings(node: Any) -> Iterator[str]:
    if isinstance(node, str):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _strings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _strings(item)


@pytest.mark.l4("C-09049412")
def test_C_09049412_changelog_adds_the_egress_scope_column() -> None:
    assert EGRESS_FILE.is_file(), (
        f"missing changelog {EGRESS_FILE.name}: vault.credentials never gains "
        "an egress_scope column"
    )
    changelog = yaml.safe_load(EGRESS_FILE.read_text())

    sql_changes = _sql_changes(changelog)
    assert len(sql_changes) == 1, "the changelog must hold exactly one SQL change"
    sql_text = _normalise(sql_changes[0]["sql"]["sql"])
    for fragment in (
        "alter table vault.credentials",
        "add column egress_scope text not null default 'any'",
        "check (egress_scope in ('any', 'public'))",
    ):
        assert fragment in sql_text, f"egress-scope SQL is missing {fragment!r}"

    change_set = next(cs for cs in _change_sets(changelog) if cs.get("changes"))
    preconditions = change_set.get("preConditions") or []
    assert any(
        isinstance(p, dict) and str(p.get("onFail", "")).upper() == "MARK_RAN"
        for p in preconditions
    ), "the change set must MARK_RAN when its precondition fails"
    column_exists = _find_not_column_exists(preconditions)
    assert column_exists is not None, (
        "the change set must guard on `not: columnExists` for the egress_scope column"
    )
    assert str(column_exists.get("schemaName", "")).lower() == "vault"
    assert str(column_exists.get("tableName", "")).lower() == "credentials"
    assert str(column_exists.get("columnName", "")).lower() == "egress_scope"

    rollback = change_set.get("rollback")
    assert rollback, "the change set must define a rollback"
    rollback_text = _normalise(" ".join(_strings(rollback)))
    assert "drop column if exists egress_scope" in rollback_text, (
        "the rollback must drop the egress_scope column when it exists"
    )

    master = yaml.safe_load(MASTER_FILE.read_text())
    includes = [
        entry["include"]
        for entry in master["databaseChangeLog"]
        if isinstance(entry, dict) and "include" in entry
    ]
    matching = [
        inc
        for inc in includes
        if Path(str(inc.get("file", ""))).name == EGRESS_FILE.name
    ]
    assert len(matching) == 1, (
        "db.changelog-master.yaml must include "
        f"{EGRESS_FILE.name} exactly once"
    )
