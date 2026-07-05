"""
CI gate: SQLAlchemy mirror diff — structural validation (T-1.11.6).

Asserts that `mintkey-models/mintkey_models/db.py` stays in sync with
the Liquibase changelogs in `admin-api/db/changelog/`.

No live database required.  All checks are static / structural.

Sources:
  - ADR-0015 (Liquibase is source of truth; SQLAlchemy mirrors)
  - ADR-0008  (every domain table has tenant_id + RLS)
  - ADR-0014.8 (platform-scoped allowlist)
  - T-1.11.6
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

import pytest
import yaml
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_SRC = REPO_ROOT / "packages/python/mintkey-models"
CHANGELOG_DIR = REPO_ROOT / "apps/admin-api" / "db" / "changelog"

# ---------------------------------------------------------------------------
# Dynamic import of mintkey_models.db so the test is runnable without
# having the package installed, as long as REPO_ROOT/mintkey-models is
# on sys.path (handled below).
# ---------------------------------------------------------------------------

if str(MODELS_SRC) not in sys.path:
    sys.path.insert(0, str(MODELS_SRC))

from mintkey_models import db as _db  # noqa: E402  (after sys.path manipulation)

# ---------------------------------------------------------------------------
# Discover all mapped model classes
# ---------------------------------------------------------------------------


def _all_model_classes() -> list[type]:
    """Return every SQLAlchemy mapped class declared in mintkey_models.db."""
    models = []
    for attr_name in dir(_db):
        obj = getattr(_db, attr_name)
        if (
            isinstance(obj, type)
            and issubclass(obj, DeclarativeBase)
            and obj is not _db.Base
            and hasattr(obj, "__table__")
        ):
            models.append(obj)
    return models


# ---------------------------------------------------------------------------
# Parse Liquibase changelogs
# ---------------------------------------------------------------------------


def _parse_changelogs() -> tuple[dict[str, set[str]], set[str]]:
    """
    Walk all YAML changelogs and return:
      - table_columns: {table_name -> {column_name, ...}}
      - all_column_names: flat set of every column name that appears
        in any createTable changeset.
    """
    table_columns: dict[str, set[str]] = {}
    all_column_names: set[str] = set()

    for yaml_file in sorted(CHANGELOG_DIR.glob("*.yaml")):
        raw: Any = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        changelog = raw.get("databaseChangeLog", [])
        for entry in changelog:
            change_set = entry.get("changeSet", {})
            for change in change_set.get("changes", []):
                create = change.get("createTable")
                if not create:
                    continue
                table = create["tableName"]
                cols = {
                    col["column"]["name"]
                    for col in create.get("columns", [])
                }
                table_columns.setdefault(table, set()).update(cols)
                all_column_names.update(cols)

    return table_columns, all_column_names


_TABLE_COLUMNS, _ALL_CHANGELOG_COLUMN_NAMES = _parse_changelogs()
_ALL_MODEL_CLASSES = _all_model_classes()

# ---------------------------------------------------------------------------
# Platform-scoped tables: exempt from tenant_id requirement.
# Mirrors the RLS_EXCLUDE list in tests/architecture/test_rls_coverage.py.
# Source: ADR-0014.8 allowlist.
# ---------------------------------------------------------------------------

PLATFORM_SCOPED_TABLES: frozenset[str] = frozenset(
    [
        # The tenants table IS the tenant root — its RLS uses `id` not
        # `tenant_id`, so it has no tenant_id foreign-key column.
        "tenants",
        "admin_request_jti",   # replay-protection JTIs (ADR-0016.1)
        "service_identities",  # per-service boot secrets (ADR-0014.2)
        "audit_chain_state",   # per-tenant chain head pointer (ADR-0014.7)
        "oidc_login_state",    # PKCE login state — not tenant-scoped (login happens before tenant is known)
    ]
)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_all_models_have_tenant_id_or_are_on_platform_allowlist() -> None:
    """
    Every SQLAlchemy model that maps a domain table must declare a `tenant_id`
    column, unless the table is explicitly in PLATFORM_SCOPED_TABLES.

    Source: ADR-0008 (multi-tenancy row-level isolation), ADR-0014.8.
    """
    violations: list[str] = []
    for cls in _ALL_MODEL_CLASSES:
        table_name: str = cls.__tablename__  # type: ignore[attr-defined]
        if table_name in PLATFORM_SCOPED_TABLES:
            continue
        mapper = sa_inspect(cls)
        col_names = {col.key for col in mapper.mapper.columns}
        if "tenant_id" not in col_names:
            violations.append(
                f"{cls.__name__} (table={table_name!r}) has no tenant_id column"
            )

    assert not violations, (
        "Models missing tenant_id (ADR-0008) — add to PLATFORM_SCOPED_TABLES "
        "if intentionally platform-scoped:\n" + "\n".join(violations)
    )


def test_no_model_defines_column_not_in_changelogs() -> None:
    """
    No SQLAlchemy model may declare a column that does not appear in any
    createTable changeset across all Liquibase YAML files.

    This is the primary anti-pattern guard from ADR-0015: the SQLAlchemy
    mirror must never get ahead of the Liquibase source of truth.

    Source: ADR-0015 (Liquibase is source of truth).
    """
    violations: list[str] = []
    for cls in _ALL_MODEL_CLASSES:
        table_name: str = cls.__tablename__  # type: ignore[attr-defined]
        mapper = sa_inspect(cls)
        for col in mapper.mapper.columns:
            if col.key not in _ALL_CHANGELOG_COLUMN_NAMES:
                violations.append(
                    f"{cls.__name__}.{col.key} (table={table_name!r}) "
                    f"is not present in any Liquibase changelog createTable"
                )

    assert not violations, (
        "SQLAlchemy model columns with no matching Liquibase changeset "
        "(ADR-0015 violation — add a Liquibase changeset first):\n"
        + "\n".join(violations)
    )


def test_liquibase_tables_have_sqlalchemy_models() -> None:
    """
    Every table created in a Liquibase `createTable` changeset must have a
    corresponding SQLAlchemy model class in mintkey_models.db.

    Source: ADR-0015 (SQLAlchemy mirrors Liquibase — no silent orphan tables).
    """
    model_table_names: set[str] = {
        cls.__tablename__  # type: ignore[attr-defined]
        for cls in _ALL_MODEL_CLASSES
    }

    missing: list[str] = sorted(_TABLE_COLUMNS.keys() - model_table_names)
    assert not missing, (
        "Liquibase tables with no SQLAlchemy model (ADR-0015):\n"
        + "\n".join(missing)
    )


def test_tenant_scoped_models_match_rls_test_table_list() -> None:
    """
    Import the TENANT_SCOPED constant from tests/architecture/test_rls_coverage.py
    and assert that every table in that set has a SQLAlchemy model.

    Keeps the model layer in sync with the RLS architecture test.
    Source: ADR-0008, ADR-0014.8.
    """
    rls_test_path = (
        REPO_ROOT / "tests" / "architecture" / "test_rls_coverage.py"
    )
    spec = importlib.util.spec_from_file_location("test_rls_coverage", rls_test_path)
    assert spec is not None and spec.loader is not None, (
        f"Cannot locate test_rls_coverage.py at {rls_test_path}"
    )
    rls_mod = importlib.util.module_from_spec(spec)
    # test_rls_coverage imports testcontainers; inject a stub if not installed.
    # We only need the TENANT_SCOPED constant, not the fixture/test code.
    _stub_missing_imports(rls_mod)
    try:
        spec.loader.exec_module(rls_mod)  # type: ignore[union-attr]
    except ImportError:
        pytest.skip(
            "test_rls_coverage.py has unavailable imports (e.g. testcontainers); "
            "skipping cross-reference check"
        )

    tenant_scoped: frozenset[str] = rls_mod.TENANT_SCOPED  # type: ignore[attr-defined]
    model_table_names: set[str] = {
        cls.__tablename__  # type: ignore[attr-defined]
        for cls in _ALL_MODEL_CLASSES
    }

    missing = sorted(tenant_scoped - model_table_names)
    assert not missing, (
        "Tables in TENANT_SCOPED (test_rls_coverage.py) have no SQLAlchemy "
        "model (ADR-0008):\n" + "\n".join(missing)
    )


def _stub_missing_imports(mod: Any) -> None:
    """
    Pre-populate sys.modules with lightweight stubs for optional heavy
    imports (testcontainers, psycopg2) so exec_module doesn't raise
    ImportError when those packages aren't installed.
    """
    stubs = {
        "testcontainers": None,
        "testcontainers.postgres": None,
        "psycopg2": None,
        "psycopg2.extras": None,
    }
    for name, value in stubs.items():
        if name not in sys.modules:
            from unittest.mock import MagicMock
            sys.modules[name] = MagicMock()


def test_sqlalchemy_models_use_declarative_base() -> None:
    """
    All model classes in mintkey_models.db must inherit from the shared
    `Base` (DeclarativeBase subclass defined in the same module).

    This guards against models accidentally being added outside the registry,
    which would make them invisible to `inspect(Base).mapper.registry`.

    Source: ADR-0012 (SQLAlchemy 2.x Mapped types).
    """
    Base = _db.Base  # noqa: N806

    violations: list[str] = []
    for cls in _ALL_MODEL_CLASSES:
        if not issubclass(cls, Base):
            violations.append(cls.__name__)

    assert not violations, (
        "Model class(es) do not inherit from mintkey_models.db.Base (ADR-0012):\n"
        + "\n".join(violations)
    )
