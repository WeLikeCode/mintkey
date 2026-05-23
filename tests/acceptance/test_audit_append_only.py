"""
Acceptance test: audit_events is append-only for mintkey_app.

Sources:
  - ADR-0014.7 (audit hash chain, immutability)
  - ADR-0014.8 (mintkey_app grant: INSERT+SELECT only on audit_events)
  - design §2 DB roles table

Starts a Postgres 16 testcontainer, applies all Liquibase migrations, then
connects as mintkey_app and asserts:
  (a) UPDATE on audit_events → InsufficientPrivilege
  (b) DELETE on audit_events → InsufficientPrivilege
  (c) INSERT into audit_events → succeeds
  (d) SELECT from audit_events → succeeds
"""
from __future__ import annotations

import os
import subprocess
import uuid
from typing import Generator

import psycopg2
import psycopg2.extensions
from psycopg2 import errors as pg_errors
import pytest
from testcontainers.postgres import PostgresContainer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
CHANGELOG_DIR = os.path.join(REPO_ROOT, "apps/admin-api", "db", "changelog")
MASTER_CHANGELOG = "db.changelog-master.yaml"
LIQUIBASE_IMAGE = "liquibase/liquibase:4.27.0"

# Fixed tenant UUID used for all tests in this module.
TENANT_ID = "00000000-0000-0000-0000-000000000001"
APP_ROLE_PASSWORD = "mintkey_app_pass"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_liquibase(jdbc_url: str, username: str, password: str) -> None:
    """Apply Liquibase changelogs via the official Docker image."""
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
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )


# ---------------------------------------------------------------------------
# Module-level fixture: one container + one Liquibase run for all 4 tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def db_info() -> Generator[dict, None, None]:
    """
    Start Postgres 16, run Liquibase, set mintkey_app password, seed a tenant
    row, and yield connection params for both the superuser and mintkey_app.
    """
    with PostgresContainer("postgres:16") as pg:
        host = pg.get_container_host_ip()
        port = int(pg.get_exposed_port(5432))
        db = pg.dbname
        user = pg.username
        password = pg.password

        jdbc_url = (
            f"jdbc:postgresql://host.docker.internal:{port}/{db}"
            "?currentSchema=public"
        )
        _apply_liquibase(jdbc_url, user, password)

        # Superuser connection for seed setup.
        admin_conn = psycopg2.connect(
            host=host, port=port, dbname=db, user=user, password=password
        )
        admin_conn.autocommit = True

        with admin_conn.cursor() as cur:
            # Give mintkey_app a known password so we can connect as it.
            cur.execute(
                f"ALTER ROLE mintkey_app WITH PASSWORD %s",
                (APP_ROLE_PASSWORD,),
            )
            # Grant CONNECT to mintkey_app on the database.
            cur.execute(
                f"GRANT CONNECT ON DATABASE {db} TO mintkey_app"
            )
            # Seed a tenant row as superuser (bypasses RLS).
            cur.execute(
                """
                INSERT INTO tenants (id, slug, display_name, isolation_mode, status, settings)
                VALUES (%s, 'test-tenant', 'Test Tenant', 'row', 'active', '{}')
                ON CONFLICT DO NOTHING
                """,
                (TENANT_ID,),
            )

        admin_conn.close()

        yield {
            "host": host,
            "port": port,
            "db": db,
            "admin_user": user,
            "admin_password": password,
        }


@pytest.fixture(scope="module")
def app_conn(db_info: dict) -> Generator[psycopg2.extensions.connection, None, None]:
    """Open a psycopg2 connection as mintkey_app for the privilege tests."""
    conn = psycopg2.connect(
        host=db_info["host"],
        port=db_info["port"],
        dbname=db_info["db"],
        user="mintkey_app",
        password=APP_ROLE_PASSWORD,
    )
    conn.autocommit = True
    try:
        yield conn
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_mintkey_app_cannot_update_audit_events(
    app_conn: psycopg2.extensions.connection,
) -> None:
    """
    mintkey_app must not be able to UPDATE audit_events.
    Source: ADR-0014.7 audit immutability, ADR-0014.8 grant table.
    """
    with app_conn.cursor() as cur:
        cur.execute(
            f"SET app.current_tenant TO '{TENANT_ID}'"
        )
        try:
            cur.execute(
                "UPDATE audit_events SET event_type = 'tampered' WHERE 1=0"
            )
            pytest.fail("UPDATE on audit_events should have raised InsufficientPrivilege")
        except pg_errors.InsufficientPrivilege:
            pass  # Expected — append-only enforced at grant level.
        finally:
            app_conn.rollback()


def test_mintkey_app_cannot_delete_audit_events(
    app_conn: psycopg2.extensions.connection,
) -> None:
    """
    mintkey_app must not be able to DELETE from audit_events.
    Source: ADR-0014.7 audit immutability, ADR-0014.8 grant table.
    """
    with app_conn.cursor() as cur:
        cur.execute(
            f"SET app.current_tenant TO '{TENANT_ID}'"
        )
        try:
            cur.execute("DELETE FROM audit_events WHERE 1=0")
            pytest.fail("DELETE on audit_events should have raised InsufficientPrivilege")
        except pg_errors.InsufficientPrivilege:
            pass  # Expected.
        finally:
            app_conn.rollback()


def test_mintkey_app_can_insert_audit_events(
    app_conn: psycopg2.extensions.connection,
) -> None:
    """
    mintkey_app must be able to INSERT into audit_events.
    Source: ADR-0014.8 — mintkey_app holds INSERT on audit_events.
    """
    row_id = str(uuid.uuid4())
    with app_conn.cursor() as cur:
        cur.execute(
            f"SET app.current_tenant TO '{TENANT_ID}'"
        )
        cur.execute(
            """
            INSERT INTO audit_events
                (id, tenant_id, event_type, actor_type, payload, prev_hash, hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                row_id,
                TENANT_ID,
                "test.event",
                "system",
                "{}",
                b"\x00" * 32,   # prev_hash (BYTEA)
                b"\xff" * 32,   # hash (BYTEA)
            ),
        )
    # No exception → INSERT succeeded.


def test_mintkey_app_can_select_audit_events(
    app_conn: psycopg2.extensions.connection,
) -> None:
    """
    mintkey_app must be able to SELECT from audit_events.
    Source: ADR-0014.8 — mintkey_app holds SELECT on audit_events.
    """
    with app_conn.cursor() as cur:
        cur.execute(
            f"SET app.current_tenant TO '{TENANT_ID}'"
        )
        cur.execute("SELECT id, event_type FROM audit_events LIMIT 1")
        # fetchall() may return 0 or more rows — what matters is no exception.
        cur.fetchall()
