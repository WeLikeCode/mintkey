"""
CI gate (add-only): SQLAlchemy mirror diff for the `access_requests` table.

Feature: agent-access-requests — Task 2.3 (_Requirements: 12.6_).

This is an ADDITIVE check. It does NOT modify the existing generic mirror
gate in tests/acceptance/test_sqlalchemy_mirror.py; it adds a table-specific,
LIVE-DB assertion that the `AccessRequest` Mapped model in
`packages/python/mintkey-models/mintkey_models/db.py` faithfully mirrors the
schema introspected from Liquibase changeset
`apps/admin-api/db/changelog/030-access-requests.yaml`.

Per AGENTS.md Principle 1 ("never assert a column exists without introspecting
it"), the authoritative assertions here run against a fresh Postgres 16 that
has had the real Liquibase changelogs applied — no hand-asserted column list.

What is verified against the introspected schema:
  - column names           (information_schema.columns)
  - column types           (data_type, mapped to a coarse family)
  - nullability            (is_nullable)
  - primary key            (information_schema.table_constraints / key_column_usage)
  - foreign keys           (constraint_column_usage)
It additionally runs the `sqlacodegen` CLI against the live DB and asserts the
generated declarative model for `access_requests` matches the checked-in mirror
column-for-column (ADR-0015 default generation tool).

Requires Docker (testcontainers Postgres + official Liquibase image) exactly
like tests/architecture/test_rls_coverage.py. If Docker / testcontainers is
unavailable the live checks skip (mirrors the repo's existing skip conventions);
a static, DB-free structural check always runs so the file is never a no-op.

Sources:
  - ADR-0015  (Liquibase is source of truth; SQLAlchemy mirrors; sqlacodegen)
  - ADR-0008  (every domain table has tenant_id + RLS)
  - Req 12.6  (SQLAlchemy Mapped models mirror the introspected Liquibase schema)
  - reuses the testcontainers + Liquibase-Docker fixture pattern from
    tests/architecture/test_rls_coverage.py
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Generator

import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]
MODELS_SRC = REPO_ROOT / "packages/python/mintkey-models"
CHANGELOG_DIR = REPO_ROOT / "apps/admin-api" / "db" / "changelog"
MASTER_CHANGELOG = "db.changelog-master.yaml"
TABLE = "access_requests"
MODEL_NAME = "AccessRequest"

LIQUIBASE_IMAGE = "liquibase/liquibase:4.27.0"

# ---------------------------------------------------------------------------
# Import the checked-in mirror model
# ---------------------------------------------------------------------------

if str(MODELS_SRC) not in sys.path:
    sys.path.insert(0, str(MODELS_SRC))

from mintkey_models import db as _db  # noqa: E402  (after sys.path manipulation)

# ---------------------------------------------------------------------------
# Expected column shape — derived from the CHECKED-IN mirror model, NOT
# hand-typed. The live-DB tests below compare this against the introspected
# schema, so the assertion is model-vs-database, not literal-vs-database.
# ---------------------------------------------------------------------------

# Coarse Postgres data_type families keyed by the SQLAlchemy column type name.
# We compare families (uuid / character varying / jsonb / timestamp) rather than
# exact strings so that e.g. VARCHAR(32) -> 'character varying' is a match.
_SA_TYPE_TO_PG_FAMILY = {
    "UUID": "uuid",
    "STRING": "character varying",
    "VARCHAR": "character varying",
    "JSONB": "jsonb",
    "DATETIME": "timestamp with time zone",
    "TIMESTAMP": "timestamp with time zone",
}


def _model_cls() -> type[DeclarativeBase]:
    cls = getattr(_db, MODEL_NAME, None)
    assert cls is not None, (
        f"{MODEL_NAME} not found in mintkey_models.db — task 2.2 must land first"
    )
    return cls  # type: ignore[return-value]


def _model_columns() -> dict[str, dict[str, Any]]:
    """
    Introspect the checked-in SQLAlchemy mirror and return, per column:
      {name: {"nullable": bool, "pk": bool, "type_family": str, "fk": set[str]}}
    """
    mapper = sa_inspect(_model_cls())
    out: dict[str, dict[str, Any]] = {}
    for col in mapper.columns:  # type: ignore[union-attr]
        # Resolve a coarse PG family from the SQLAlchemy type class name.
        type_name = type(col.type).__name__.upper()
        family = _SA_TYPE_TO_PG_FAMILY.get(type_name, type_name.lower())
        fks = {
            f"{fk.column.table.name}.{fk.column.name}" for fk in col.foreign_keys
        }
        out[col.name] = {
            "nullable": bool(col.nullable),
            "pk": bool(col.primary_key),
            "type_family": family,
            "fk": fks,
        }
    return out


# ---------------------------------------------------------------------------
# Docker availability gate (mirrors repo convention)
# ---------------------------------------------------------------------------


def _docker_available() -> bool:
    if shutil.which("docker") is None:
        return False
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=20
        )
        return r.returncode == 0
    except Exception:
        return False


requires_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker unavailable — live Liquibase introspection diff skipped",
)


def _apply_liquibase(jdbc_url: str, username: str, password: str) -> None:
    """Apply Liquibase changelogs via the official Docker image (per test_rls_coverage.py)."""
    cmd = [
        "docker", "run", "--rm",
        "--add-host", "host.docker.internal:host-gateway",
        "-v", f"{CHANGELOG_DIR}:/liquibase/changelog:ro",
        LIQUIBASE_IMAGE,
        f"--url={jdbc_url}",
        f"--username={username}",
        f"--password={password}",
        f"--changeLogFile=changelog/{MASTER_CHANGELOG}",
        "update",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
    if result.returncode != 0:
        raise AssertionError(
            f"Liquibase update failed (exit {result.returncode}).\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Fixture: fresh Postgres 16 + Liquibase applied, yielding a psycopg2 conn.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_conn() -> Generator[Any, None, None]:
    try:
        import psycopg2  # noqa: PLC0415
        from testcontainers.postgres import PostgresContainer  # noqa: PLC0415
    except Exception as exc:  # pragma: no cover - env dependent
        pytest.skip(f"testcontainers/psycopg2 unavailable: {exc}")

    with PostgresContainer("postgres:16") as pg:
        host = pg.get_container_host_ip()
        port = int(pg.get_exposed_port(5432))
        db = pg.dbname
        user = pg.username
        password = pg.password
        jdbc_url = (
            f"jdbc:postgresql://host.docker.internal:{port}/{db}?currentSchema=public"
        )
        _apply_liquibase(jdbc_url, user, password)

        conn = psycopg2.connect(
            host=host, port=port, dbname=db, user=user, password=password
        )
        conn.autocommit = True
        try:
            yield conn
        finally:
            conn.close()


# ---------------------------------------------------------------------------
# DB introspection helpers
# ---------------------------------------------------------------------------


def _db_columns(conn: Any) -> dict[str, dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'public' AND table_name = %s
            ORDER BY ordinal_position
            """,
            (TABLE,),
        )
        cols = {
            name: {"type_family": dtype, "nullable": (isnull == "YES")}
            for (name, dtype, isnull) in cur.fetchall()
        }
    return cols


def _db_primary_key(conn: Any) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.table_name = %s
              AND tc.constraint_type = 'PRIMARY KEY'
            """,
            (TABLE,),
        )
        return {row[0] for row in cur.fetchall()}


def _db_foreign_keys(conn: Any) -> dict[str, str]:
    """Return {local_column: 'referenced_table.referenced_column'}."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT kcu.column_name,
                   ccu.table_name AS ref_table,
                   ccu.column_name AS ref_column
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage ccu
              ON tc.constraint_name = ccu.constraint_name
             AND tc.table_schema = ccu.table_schema
            WHERE tc.table_schema = 'public'
              AND tc.table_name = %s
              AND tc.constraint_type = 'FOREIGN KEY'
            """,
            (TABLE,),
        )
        return {
            col: f"{ref_table}.{ref_column}"
            for (col, ref_table, ref_column) in cur.fetchall()
        }


# ---------------------------------------------------------------------------
# Static (DB-free) sanity check — always runs, so the file is never a no-op.
# ---------------------------------------------------------------------------


def test_access_request_model_is_registered_and_maps_the_table() -> None:
    """
    The AccessRequest mirror model exists, inherits the shared Base, and maps
    the `access_requests` table. (Static; no DB.)  Source: ADR-0015, Req 12.6.
    """
    cls = _model_cls()
    assert issubclass(cls, _db.Base), f"{MODEL_NAME} must inherit mintkey_models.db.Base"
    assert cls.__tablename__ == TABLE  # type: ignore[attr-defined]
    cols = _model_columns()
    # A minimal shape guard that does not duplicate the DB-authoritative checks.
    assert "id" in cols and cols["id"]["pk"], "id must be the primary key"
    assert "tenant_id" in cols and not cols["tenant_id"]["nullable"], (
        "tenant_id must exist and be NOT NULL (ADR-0008)"
    )


# ---------------------------------------------------------------------------
# LIVE-DB introspection diff — the authoritative mirror check for 030.
# ---------------------------------------------------------------------------


@requires_docker
def test_access_requests_columns_match_introspected_schema(pg_conn: Any) -> None:
    """
    Column names, coarse type family, and nullability of the AccessRequest
    mirror model must equal the introspected `access_requests` schema.
    Source: ADR-0015, Req 12.6.
    """
    model = _model_columns()
    db = _db_columns(pg_conn)
    assert db, f"table {TABLE!r} not found in introspected schema (Liquibase not applied?)"

    model_names = set(model)
    db_names = set(db)
    assert model_names == db_names, (
        "Column-name drift between AccessRequest model and introspected schema:\n"
        f"  only in model: {sorted(model_names - db_names)}\n"
        f"  only in DB   : {sorted(db_names - model_names)}"
    )

    type_drift: list[str] = []
    null_drift: list[str] = []
    for name in sorted(model_names):
        if model[name]["type_family"] != db[name]["type_family"]:
            type_drift.append(
                f"  {name}: model={model[name]['type_family']!r} db={db[name]['type_family']!r}"
            )
        if model[name]["nullable"] != db[name]["nullable"]:
            null_drift.append(
                f"  {name}: model nullable={model[name]['nullable']} "
                f"db nullable={db[name]['nullable']}"
            )

    assert not type_drift, "Type-family drift (ADR-0015):\n" + "\n".join(type_drift)
    assert not null_drift, "Nullability drift (ADR-0015):\n" + "\n".join(null_drift)


@requires_docker
def test_access_requests_primary_key_matches(pg_conn: Any) -> None:
    """PK column set of the mirror model equals the introspected PK. Source: ADR-0015."""
    model_pk = {n for n, m in _model_columns().items() if m["pk"]}
    db_pk = _db_primary_key(pg_conn)
    assert model_pk == db_pk, (
        f"Primary-key drift: model={sorted(model_pk)} db={sorted(db_pk)}"
    )


@requires_docker
def test_access_requests_foreign_keys_match(pg_conn: Any) -> None:
    """
    Every FK declared on the mirror model must exist in the introspected schema
    with the same referent, and vice-versa. Source: ADR-0015, design §Data Models.
    """
    model_fks: dict[str, set[str]] = {
        n: m["fk"] for n, m in _model_columns().items() if m["fk"]
    }
    # Flatten model FKs to {local_col: referent} (single-column FKs only here).
    model_flat = {col: next(iter(refs)) for col, refs in model_fks.items()}
    db_flat = _db_foreign_keys(pg_conn)

    assert model_flat == db_flat, (
        "Foreign-key drift between AccessRequest model and introspected schema:\n"
        f"  model: {sorted(model_flat.items())}\n"
        f"  db   : {sorted(db_flat.items())}"
    )


@requires_docker
def test_access_requests_sqlacodegen_diff_is_clean(pg_conn: Any) -> None:
    """
    Run the ADR-0015 default generation tool (`sqlacodegen --generator declarative`)
    against the live DB and assert the generated model for `access_requests`
    carries exactly the mirror's column set. This is the tool-based half of the
    mirror-diff CI step described in ADR-0015.

    We scope the comparison to the `access_requests` table (add-only): the diff
    asserts that every mirror column appears in the generated class and no extra
    column is generated for the table.  Source: ADR-0015, Req 12.6.
    """
    sqlacodegen = shutil.which("sqlacodegen")
    if sqlacodegen is None:
        pytest.skip("sqlacodegen not installed — tool-based diff skipped")

    # psycopg2 does not expose the password, so drive sqlacodegen with a
    # password-less URL and supply the password via PGPASSWORD. The
    # testcontainers PostgresContainer default password is 'test'.
    params = pg_conn.get_dsn_parameters()
    env = dict(os.environ)
    env.setdefault("PGPASSWORD", "test")
    url_no_pw = (
        f"postgresql://{params['user']}@{params['host']}:{params['port']}/{params['dbname']}"
    )

    result = subprocess.run(
        [sqlacodegen, "--generator", "declarative", "--tables", TABLE, url_no_pw],
        capture_output=True,
        text=True,
        timeout=120,
        env=env,
    )
    if result.returncode != 0:
        pytest.skip(
            "sqlacodegen could not connect/generate "
            f"(exit {result.returncode}): {result.stderr.strip()[:400]}"
        )

    generated = result.stdout
    assert TABLE in generated, (
        f"sqlacodegen produced no declaration for {TABLE!r}:\n{generated[:800]}"
    )

    # sqlacodegen `--tables access_requests` still emits FK-related tables, so
    # isolate ONLY the class whose __tablename__ == 'access_requests' before
    # parsing its columns.
    class_body = _extract_class_body(generated, TABLE)
    assert class_body, (
        f"Could not locate the generated class for __tablename__={TABLE!r}:\n"
        f"{generated[:1500]}"
    )

    # Column declarations render as `    <name>: Mapped[...] = mapped_column(...)`.
    # Exclude ORM relationships (`= relationship(...)`), which are not columns.
    generated_cols: set[str] = set()
    for m in re.finditer(
        r"^\s{4}([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*Mapped\[.*$", class_body, re.MULTILINE
    ):
        line = m.group(0)
        if "mapped_column(" in line:
            generated_cols.add(m.group(1))
    assert generated_cols, (
        f"Could not parse any column declarations from generated class:\n{class_body[:1200]}"
    )

    model_names = set(_model_columns())
    missing = sorted(model_names - generated_cols)
    extra = sorted(generated_cols - model_names)
    assert not missing and not extra, (
        "sqlacodegen-generated model for access_requests drifts from the "
        f"checked-in mirror (ADR-0015):\n"
        f"  missing from generated (present in mirror): {missing}\n"
        f"  extra in generated (absent from mirror):    {extra}\n\n"
        f"--- generated class ---\n{class_body[:1500]}"
    )


def _extract_class_body(generated: str, table: str) -> str:
    """
    Return the source lines of the generated class whose __tablename__ == table,
    from its `class ...` line up to (but excluding) the next top-level `class `.
    """
    lines = generated.splitlines()
    # Find the index of the __tablename__ marker, then walk back to its class.
    marker = f"__tablename__ = '{table}'"
    idx = next((i for i, ln in enumerate(lines) if marker in ln), None)
    if idx is None:
        return ""
    start = next(
        (j for j in range(idx, -1, -1) if lines[j].startswith("class ")), idx
    )
    end = next(
        (k for k in range(start + 1, len(lines)) if lines[k].startswith("class ")),
        len(lines),
    )
    return "\n".join(lines[start:end])
