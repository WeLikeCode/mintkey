"""
Architecture test: RLS coverage on all tenant-scoped tables.

Sources:
  - ADR-0008  (multi-tenancy row-level isolation)
  - ADR-0014.8 (RLS architecture test — no qual='true', 100% coverage)
  - ADR-0016.3 (PlatformAdmin escape OR clause in every policy)
  - Req 1 AC3, AC4, AC11

Runs Liquibase migrations against a fresh Postgres (via testcontainers + official
Liquibase Docker image), then queries pg_policies and asserts:
  (a) every tenant-scoped table has a `tenant_isolation` policy,
  (b) no policy has qual='true' (no-op),
  (c) every policy's qual references BOTH `app.current_tenant` AND
      `app.platform_admin_view` (the PlatformAdmin escape — ADR-0016.3).

Platform-scoped tables are excluded by name via RLS_EXCLUDE (documented below).
"""
from __future__ import annotations

import os
import subprocess
from typing import Generator

import psycopg2
import psycopg2.extras
import pytest
from testcontainers.postgres import PostgresContainer

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
CHANGELOG_DIR = os.path.join(REPO_ROOT, "admin-api", "db", "changelog")
MASTER_CHANGELOG = "db.changelog-master.yaml"

# Every tenant-scoped table that must carry a tenant_isolation RLS policy.
# Source: design §2 / Req 1 AC3 + AC4.
TENANT_SCOPED: frozenset[str] = frozenset(
    [
        "tenants",
        "operators",
        "operator_tenant_memberships",
        "sessions",
        "agents",
        "services",
        "credentials",
        "permission_grants",
        "audit_events",
        "tenant_settings",
    ]
)

# Platform-scoped tables: explicitly exempt from RLS by design.
# Source: design §2 / Req 1 AC3 / ADR-0014.8 (allowlist).
RLS_EXCLUDE: frozenset[str] = frozenset(
    [
        "admin_request_jti",      # replay-protection JTIs (ADR-0016.1)
        "service_identities",     # per-service boot secrets (ADR-0014.2)
        "audit_chain_state",      # per-tenant chain head pointer (ADR-0014.7)
    ]
)

# Liquibase Docker image — pin to a stable tag in production; use 'latest' for dev.
LIQUIBASE_IMAGE = "liquibase/liquibase:4.27.0"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _apply_liquibase(jdbc_url: str, username: str, password: str) -> None:
    """
    Apply Liquibase changelogs via the official Docker image.

    Uses host.docker.internal so the Liquibase container (running inside Docker)
    can reach the testcontainers Postgres instance that is exposed on the host.
    Linux: --add-host host.docker.internal:host-gateway maps the alias.
    macOS/Docker Desktop: host.docker.internal is available by default.
    """
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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    """
    Start a fresh Postgres 16 container, apply all Liquibase changelogs,
    and yield an open psycopg2 connection for the assertions.
    """
    with PostgresContainer("postgres:16") as pg:
        host = pg.get_container_host_ip()
        port = int(pg.get_exposed_port(5432))
        db = pg.dbname
        user = pg.username
        password = pg.password

        # JDBC URL uses host.docker.internal so the Liquibase Docker container
        # can reach the Postgres container's exposed port on the Docker host.
        jdbc_url = (
            f"jdbc:postgresql://host.docker.internal:{port}/{db}"
            "?currentSchema=public"
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
# Tests
# ---------------------------------------------------------------------------


def test_all_tenant_scoped_tables_have_rls_policy(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    Every tenant-scoped table has at least one row in pg_policies.
    Source: ADR-0008, ADR-0014.8, Req 1 AC4.
    """
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename FROM pg_policies
            WHERE schemaname = 'public'
            """,
        )
        tables_with_policy = {row[0] for row in cur.fetchall()}

    missing = TENANT_SCOPED - tables_with_policy
    assert not missing, (
        f"Tenant-scoped tables with no RLS policy (ADR-0014.8): {sorted(missing)}"
    )


def test_no_noop_rls_policies(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    No policy in the public schema has qual='true' (a no-op that grants all rows).
    Source: ADR-0014.8.
    """
    with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT tablename, policyname, qual
            FROM pg_policies
            WHERE schemaname = 'public'
            """
        )
        policies = cur.fetchall()

    noop = [p for p in policies if p["qual"] == "true"]
    assert not noop, (
        f"No-op RLS policies (qual='true') found — violates ADR-0014.8: {noop}"
    )


def test_every_policy_references_current_tenant(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    Every tenant_isolation policy's qual must reference current_setting('app.current_tenant').
    Source: ADR-0008 §Decision, Req 1 AC4.
    """
    with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT tablename, policyname, qual
            FROM pg_policies
            WHERE schemaname = 'public'
              AND policyname = 'tenant_isolation'
            """
        )
        policies = cur.fetchall()

    bad = [
        p for p in policies
        if "app.current_tenant" not in (p["qual"] or "")
    ]
    assert not bad, (
        f"tenant_isolation policies missing app.current_tenant reference "
        f"(ADR-0008): {[p['tablename'] for p in bad]}"
    )


def test_every_policy_has_platform_admin_escape(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    Every tenant_isolation policy's qual must also include the PlatformAdmin OR
    clause: current_setting('app.platform_admin_view', true) = 'on'.
    Source: ADR-0016.3, Req 1 AC4.
    """
    with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT tablename, policyname, qual
            FROM pg_policies
            WHERE schemaname = 'public'
              AND policyname = 'tenant_isolation'
            """
        )
        policies = cur.fetchall()

    bad = [
        p for p in policies
        if "app.platform_admin_view" not in (p["qual"] or "")
    ]
    assert not bad, (
        f"tenant_isolation policies missing PlatformAdmin escape "
        f"(app.platform_admin_view — ADR-0016.3): {[p['tablename'] for p in bad]}"
    )


def test_platform_scoped_tables_have_no_rls(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    Platform-scoped tables (RLS_EXCLUDE) must NOT have RLS policies.
    Source: design §2 allowlist, Req 1 AC3.
    """
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT tablename FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = ANY(%s)
            """,
            (list(RLS_EXCLUDE),),
        )
        unexpected = {row[0] for row in cur.fetchall()}

    assert not unexpected, (
        f"Platform-scoped tables should have no RLS policies but do: {unexpected} "
        f"(violates design §2 allowlist)"
    )


def test_mintkey_app_role_has_no_bypassrls(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    mintkey_app must NOT have BYPASSRLS — it must be subject to RLS policies.
    Only mintkey_migrate (the Liquibase migration role) bypasses RLS.
    Source: ADR-0014.8 / T-1.0.11 assertion 6, design §2 DB roles table.
    """
    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT rolbypassrls FROM pg_roles WHERE rolname = 'mintkey_app'"
        )
        row = cur.fetchone()

    assert row is not None, "Role mintkey_app does not exist"
    assert row[0] is False, (
        "mintkey_app has BYPASSRLS=true — it must be subject to RLS (ADR-0014.8)"
    )


def test_mintkey_app_cannot_mutate_audit_events(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    mintkey_app must have no UPDATE or DELETE on audit_events (append-only enforced
    at the DB grant level per design §2 / ADR-0014.7 audit immutability).
    Source: ADR-0014.8 / T-1.0.11 assertion 7, design §2 DB roles table.
    """
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT privilege_type FROM information_schema.role_table_grants
            WHERE grantee = 'mintkey_app'
              AND table_name = 'audit_events'
              AND privilege_type IN ('UPDATE', 'DELETE')
            """
        )
        forbidden = {row[0] for row in cur.fetchall()}

    assert not forbidden, (
        f"mintkey_app has forbidden privileges on audit_events: {forbidden} "
        f"(must be append-only per ADR-0014.7 / design §2)"
    )


def test_rls_enabled_on_all_tenant_scoped_tables(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    pg_class.relrowsecurity must be true for every tenant-scoped table.
    Source: ADR-0008 §Decision.
    """
    with pg_conn.cursor() as cur:
        cur.execute(
            """
            SELECT relname FROM pg_class
            WHERE relkind = 'r'
              AND relnamespace = (SELECT oid FROM pg_namespace WHERE nspname = 'public')
              AND relname = ANY(%s)
              AND relrowsecurity = false
            """,
            (list(TENANT_SCOPED),),
        )
        rls_disabled = {row[0] for row in cur.fetchall()}

    assert not rls_disabled, (
        f"RLS not enabled (ALTER TABLE ... ENABLE ROW LEVEL SECURITY missing) "
        f"on tenant-scoped tables (ADR-0008): {sorted(rls_disabled)}"
    )
