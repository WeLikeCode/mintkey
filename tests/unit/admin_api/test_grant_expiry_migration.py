"""
Unit tests: the grant-expiry changelog and the Core table.

Requirement: grant-expiry › The schema stores a grant's expiry and grantor

  - the changelog adds the columns (`030-grant-expiry.yaml` and the master)
  - the Core table knows the columns (`admin_api.db.tables.permission_grants`)
    while `mintkey_models/db.py` stays untouched.

Sources:
  - `openspec/changes/grant-expiry/spec.md` — The schema stores a grant's
    expiry and grantor
  - `openspec/changes/grant-expiry/design.md` — D1 (columns) and Context
    (the ORM mirror ignores `addColumn` columns)
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CHANGELOG_DIR = REPO_ROOT / "apps" / "admin-api" / "db" / "changelog"
GRANT_EXPIRY_FILE = CHANGELOG_DIR / "030-grant-expiry.yaml"
MASTER_FILE = CHANGELOG_DIR / "db.changelog-master.yaml"
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
MODELS_DB = REPO_ROOT / "packages" / "python" / "mintkey-models" / "mintkey_models" / "db.py"

COLUMN_NAMES = ("expires_at", "grantor_type", "grantor_id")


def _normalise(text: str) -> str:
    """Lower-case and collapse runs of whitespace so fragments match across line wraps."""
    return " ".join(text.lower().split())


def _change_sets(changelog: Any) -> list[dict[str, Any]]:
    return [
        entry["changeSet"]
        for entry in changelog["databaseChangeLog"]
        if isinstance(entry, dict) and "changeSet" in entry
    ]


def _all_changes(changelog: Any) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for change_set in _change_sets(changelog):
        for change in change_set.get("changes") or []:
            if isinstance(change, dict):
                changes.append(change)
    return changes


def _added_columns(changelog: Any) -> dict[str, dict[str, Any]]:
    """Map column name -> column definition for every addColumn in the file."""
    columns: dict[str, dict[str, Any]] = {}
    for change in _all_changes(changelog):
        add_column = change.get("addColumn")
        if not isinstance(add_column, dict):
            continue
        for entry in add_column.get("columns") or []:
            if not isinstance(entry, dict):
                continue
            column = entry.get("column")
            if isinstance(column, dict) and "name" in column:
                columns[str(column["name"])] = column
    return columns


def _default_value(column: dict[str, Any]) -> str:
    for key in ("defaultValue", "defaultValueComputed", "defaultValueNumeric"):
        if key in column:
            return str(column[key]).strip().strip("'\"").lower()
    return ""


def _constraint(column: dict[str, Any], name: str) -> Any:
    constraints = column.get("constraints") or {}
    if not isinstance(constraints, dict):
        return None
    return constraints.get(name)


def _sql_texts(changelog: Any) -> str:
    texts: list[str] = []
    for change in _all_changes(changelog):
        sql = change.get("sql")
        if isinstance(sql, dict) and isinstance(sql.get("sql"), str):
            texts.append(sql["sql"])
    return _normalise(" ".join(texts))


def _index_column_names(index: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    for entry in index.get("columns") or []:
        if not isinstance(entry, dict):
            continue
        column = entry.get("column")
        if isinstance(column, dict) and "name" in column:
            names.add(str(column["name"]))
        elif "name" in entry:
            names.add(str(entry["name"]))
    return names


def _class_source(source: str, class_name: str) -> str | None:
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                return segment
    return None


@pytest.mark.l4("C-48b97ae8")
def test_C_48b97ae8_changelog_adds_expiry_and_grantor_columns() -> None:
    assert GRANT_EXPIRY_FILE.is_file(), (
        f"missing changelog {GRANT_EXPIRY_FILE.name}: permission_grants never "
        "gains expires_at, grantor_type and grantor_id"
    )

    changelog = yaml.safe_load(GRANT_EXPIRY_FILE.read_text(encoding="utf-8"))
    columns = _added_columns(changelog)

    for name in COLUMN_NAMES:
        assert name in columns, f"the changelog has no addColumn for {name!r}"

    expires_at = columns["expires_at"]
    assert str(expires_at.get("type", "")).upper() == "TIMESTAMPTZ", (
        "expires_at must be a TIMESTAMPTZ column"
    )
    assert _constraint(expires_at, "nullable") is not False, (
        "expires_at must be nullable (no `nullable: false`)"
    )

    grantor_id = columns["grantor_id"]
    assert str(grantor_id.get("type", "")).upper() == "UUID", (
        "grantor_id must be a UUID column"
    )
    assert _constraint(grantor_id, "nullable") is not False, (
        "grantor_id must be nullable (no `nullable: false`)"
    )

    grantor_type = columns["grantor_type"]
    assert str(grantor_type.get("type", "")).upper() == "TEXT", (
        "grantor_type must be a TEXT column"
    )
    assert _constraint(grantor_type, "nullable") is False, (
        "grantor_type must be NOT NULL (`nullable: false`)"
    )
    assert _default_value(grantor_type) == "operator", (
        "grantor_type must default to `operator`"
    )

    assert "check (grantor_type in ('operator', 'agent'))" in _sql_texts(changelog), (
        "the changelog needs an SQL change constraining grantor_type to "
        "('operator', 'agent')"
    )

    indexes = [
        change["createIndex"]
        for change in _all_changes(changelog)
        if isinstance(change.get("createIndex"), dict)
    ]
    assert any(
        str(index.get("tableName", "")) == "permission_grants"
        and _index_column_names(index) >= {"tenant_id", "grantor_id"}
        for index in indexes
    ), "the changelog needs a createIndex on permission_grants (tenant_id, grantor_id)"

    master = yaml.safe_load(MASTER_FILE.read_text(encoding="utf-8"))
    includes = [
        entry["include"]
        for entry in master["databaseChangeLog"]
        if isinstance(entry, dict) and "include" in entry
    ]
    matching = [
        include
        for include in includes
        if Path(str(include.get("file", ""))).name == GRANT_EXPIRY_FILE.name
    ]
    assert len(matching) == 1, (
        "db.changelog-master.yaml must include 030-grant-expiry.yaml exactly once"
    )


@pytest.mark.l4("C-efc458dc")
def test_C_efc458dc_core_table_has_columns_and_model_does_not() -> None:
    if str(ADMIN_API_SRC) not in sys.path:
        sys.path.insert(0, str(ADMIN_API_SRC))

    from admin_api.db.tables import permission_grants

    keys = set(permission_grants.c.keys())
    for name in COLUMN_NAMES:
        assert name in keys, (
            f"admin_api.db.tables.permission_grants has no {name!r} column"
        )

    class_source = _class_source(MODELS_DB.read_text(encoding="utf-8"), "PermissionGrant")
    assert class_source is not None, "PermissionGrant is missing from mintkey_models/db.py"
    for name in COLUMN_NAMES:
        assert name not in class_source, (
            f"mintkey_models/db.py PermissionGrant must not mirror {name!r}: the "
            "ORM mirror ignores the addColumn columns"
        )
