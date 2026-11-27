"""
Unit tests: the agent-role / service-owner schema change.

Requirement: agent-roles-and-ownership › The schema stores an agent's role and
a service's owner

  - the changelog adds `agents.role` (consumer | publisher, default consumer)
    and the two nullable service owner columns, the CHECK, the foreign keys and
    the owner index (`031-agent-roles-and-ownership.yaml`).
  - the master changelog includes it exactly once, and the ORM mirror
    `mintkey_models/db.py` does not gain the columns.

Sources:
  - `openspec/changes/agent-roles-and-ownership/spec.md` — The schema stores an
    agent's role and a service's owner
  - `openspec/changes/agent-roles-and-ownership/design.md` — D1, D2 and Context
    (the ORM mirror ignores `addColumn` columns)
"""
from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
CHANGELOG_DIR = REPO_ROOT / "apps" / "admin-api" / "db" / "changelog"
MIGRATION_FILE = CHANGELOG_DIR / "031-agent-roles-and-ownership.yaml"
MASTER_FILE = CHANGELOG_DIR / "db.changelog-master.yaml"
MODELS_DB = (
    REPO_ROOT
    / "packages"
    / "python"
    / "mintkey-models"
    / "mintkey_models"
    / "db.py"
)


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


def _added_columns(changelog: Any) -> dict[tuple[str, str], dict[str, Any]]:
    """Map (table name, column name) -> column definition for every addColumn."""
    columns: dict[tuple[str, str], dict[str, Any]] = {}
    for change in _all_changes(changelog):
        add_column = change.get("addColumn")
        if not isinstance(add_column, dict):
            continue
        table = str(add_column.get("tableName", ""))
        for entry in add_column.get("columns") or []:
            if not isinstance(entry, dict):
                continue
            column = entry.get("column")
            if isinstance(column, dict) and "name" in column:
                columns[(table, str(column["name"]))] = column
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


def _column_names(value: Any) -> set[str]:
    if isinstance(value, str):
        return {part.strip() for part in value.split(",") if part.strip()}
    if isinstance(value, list):
        return {str(part).strip() for part in value if str(part).strip()}
    return set()


def _foreign_keys(
    changelog: Any,
) -> dict[tuple[str, str], dict[str, Any]]:
    """Map (base table, base column) -> addForeignKeyConstraint change."""
    foreign_keys: dict[tuple[str, str], dict[str, Any]] = {}
    for change in _all_changes(changelog):
        constraint = change.get("addForeignKeyConstraint")
        if not isinstance(constraint, dict):
            continue
        table = str(constraint.get("baseTableName", ""))
        for column in _column_names(constraint.get("baseColumnNames")):
            foreign_keys[(table, column)] = constraint
    return foreign_keys


def _indexes(changelog: Any) -> list[dict[str, Any]]:
    return [
        change["createIndex"]
        for change in _all_changes(changelog)
        if isinstance(change.get("createIndex"), dict)
    ]


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


@pytest.mark.l4("C-73e5aa3d")
def test_C_73e5aa3d_changelog_adds_role_and_owner_columns() -> None:
    assert MIGRATION_FILE.is_file(), (
        f"missing changelog {MIGRATION_FILE.name}: agents never gains role and "
        "services never gains owner_agent_id / created_by_agent_id"
    )

    changelog = yaml.safe_load(MIGRATION_FILE.read_text(encoding="utf-8"))
    assert isinstance(changelog, dict), "the changelog must parse as a YAML mapping"
    assert "databaseChangeLog" in changelog

    columns = _added_columns(changelog)

    role = columns.get(("agents", "role"))
    assert role is not None, "the changelog has no addColumn for agents.role"
    assert str(role.get("type", "")).upper() == "TEXT", (
        "agents.role must be a TEXT column"
    )
    assert _default_value(role) == "consumer", (
        "agents.role must default to `consumer`"
    )
    assert _constraint(role, "nullable") is False, (
        "agents.role must be NOT NULL (`nullable: false`)"
    )

    for name in ("owner_agent_id", "created_by_agent_id"):
        column = columns.get(("services", name))
        assert column is not None, (
            f"the changelog has no addColumn for services.{name}"
        )
        assert str(column.get("type", "")).upper() == "UUID", (
            f"services.{name} must be a UUID column"
        )
        assert _constraint(column, "nullable") is not False, (
            f"services.{name} must be nullable (no `nullable: false`)"
        )

    assert "check (role in ('consumer', 'publisher'))" in _sql_texts(changelog), (
        "the changelog needs an SQL change constraining role to "
        "('consumer', 'publisher')"
    )

    foreign_keys = _foreign_keys(changelog)
    for name in ("owner_agent_id", "created_by_agent_id"):
        foreign_key = foreign_keys.get(("services", name))
        assert foreign_key is not None, (
            f"the changelog has no addForeignKeyConstraint for services.{name}"
        )
        assert str(foreign_key.get("referencedTableName", "")) == "agents", (
            f"services.{name} must reference agents"
        )
        assert _column_names(foreign_key.get("referencedColumnNames")) == {"id"}, (
            f"services.{name} must reference agents(id)"
        )
        assert str(foreign_key.get("onDelete", "")).upper() == "SET NULL", (
            f"services.{name} must be ON DELETE SET NULL"
        )

    assert any(
        str(index.get("tableName", "")) == "services"
        and _index_column_names(index) >= {"tenant_id", "owner_agent_id"}
        for index in _indexes(changelog)
    ), "the changelog needs a createIndex on services (tenant_id, owner_agent_id)"


@pytest.mark.l4("C-1830b71d")
def test_C_1830b71d_master_includes_once_and_mirror_stays_unchanged() -> None:
    assert MIGRATION_FILE.is_file(), (
        f"missing changelog {MIGRATION_FILE.name}: there is no migration to "
        "include in the master changelog"
    )

    master = yaml.safe_load(MASTER_FILE.read_text(encoding="utf-8"))
    includes = [
        entry["include"]
        for entry in master["databaseChangeLog"]
        if isinstance(entry, dict) and "include" in entry
    ]
    matching = [
        include
        for include in includes
        if Path(str(include.get("file", ""))).name == MIGRATION_FILE.name
    ]
    assert len(matching) == 1, (
        "db.changelog-master.yaml must include "
        f"{MIGRATION_FILE.name} exactly once"
    )

    db_text = MODELS_DB.read_text(encoding="utf-8")
    assert "owner_agent_id" not in db_text, (
        "mintkey_models/db.py must not mirror services.owner_agent_id"
    )
    assert "created_by_agent_id" not in db_text, (
        "mintkey_models/db.py must not mirror services.created_by_agent_id"
    )

    agent_source = _class_source(db_text, "Agent")
    assert agent_source is not None, "the Agent class is missing from mintkey_models/db.py"
    assert "role: Mapped" not in agent_source, (
        "mintkey_models/db.py Agent must not mirror agents.role"
    )
