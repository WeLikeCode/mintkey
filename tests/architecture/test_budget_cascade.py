"""
Architecture test: budget_counters cascade deletion (T-BUD-5.5).

Asserts that deleting a permission_grant removes its associated
budget_counters rows via ON DELETE CASCADE.

Sources:
  - T-BUD-5.5; NFR-4; design §1.
  - ADR-0008 (multi-tenancy)

Runs Liquibase migrations against a fresh Postgres (via testcontainers),
inserts test data, deletes the grant, and confirms counter rows are gone.
"""
from __future__ import annotations

import os
import subprocess
import uuid
from typing import Generator

import psycopg2
import pytest
from testcontainers.postgres import PostgresContainer

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
CHANGELOG_DIR = os.path.join(REPO_ROOT, "apps/admin-api", "db", "changelog")
MASTER_CHANGELOG = "db.changelog-master.yaml"
LIQUIBASE_IMAGE = "liquibase/liquibase:4.27.0"


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
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )


@pytest.fixture(scope="module")
def pg_conn() -> Generator[psycopg2.extensions.connection, None, None]:
    """Start Postgres 16, apply Liquibase changelogs, yield connection."""
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

        conn = psycopg2.connect(
            host=host, port=port, dbname=db, user=user, password=password
        )
        conn.autocommit = True
        try:
            yield conn
        finally:
            conn.close()


def test_cascade_delete_grant_removes_budget_counters(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    Deleting a permission_grant must cascade-delete its budget_counters rows.
    Source: T-BUD-5.5; NFR-4; design §1.
    """
    with pg_conn.cursor() as cur:
        # Create a tenant
        tenant_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO tenants (id, slug, display_name, isolation_mode, status)"
            " VALUES (%s, 'cascade-test', 'Cascade Test', 'row', 'active')",
            (tenant_id,),
        )

        # Create an agent
        agent_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO agents"
            " (id, tenant_id, name, api_key_hash, api_key_fingerprint,"
            "  mcp_endpoint, status)"
            " VALUES (%s, %s, 'cascade-agent', 'hash', 'fp01',"
            "  'http://localhost', 'active')",
            (agent_id, tenant_id),
        )

        # Create a service
        service_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO services"
            " (id, tenant_id, name, slug, display_name, base_url,"
            "  auth_scheme, status)"
            " VALUES (%s, %s, 'cascade-svc', 'cascade-svc', 'Cascade Svc',"
            "  'https://example.com', 'bearer_token', 'active')",
            (service_id, tenant_id),
        )

        # Create a permission grant
        perm_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO permission_grants"
            " (id, tenant_id, agent_id, service_id, action, constraints, status)"
            " VALUES (%s, %s, %s, %s, 'invoke', '{}'::jsonb, 'active')",
            (perm_id, tenant_id, agent_id, service_id),
        )

        # Create budget counter rows
        cur.execute(
            "INSERT INTO budget_counters"
            " (permission_id, period_start, period_end, ceiling, used, tenant_id)"
            " VALUES (%s, '2026-06-01T00:00:00Z', '2026-06-02T00:00:00Z',"
            "  100, 42, %s)",
            (perm_id, tenant_id),
        )
        cur.execute(
            "INSERT INTO budget_counters"
            " (permission_id, period_start, period_end, ceiling, used, tenant_id)"
            " VALUES (%s, '2026-06-02T00:00:00Z', '2026-06-03T00:00:00Z',"
            "  100, 10, %s)",
            (perm_id, tenant_id),
        )

        # Verify counters exist
        cur.execute(
            "SELECT COUNT(*) FROM budget_counters WHERE permission_id = %s",
            (perm_id,),
        )
        assert cur.fetchone()[0] == 2, "Expected 2 budget_counters rows"

        # Delete the grant
        cur.execute(
            "DELETE FROM permission_grants WHERE id = %s", (perm_id,)
        )

        # Verify counters are cascade-deleted
        cur.execute(
            "SELECT COUNT(*) FROM budget_counters WHERE permission_id = %s",
            (perm_id,),
        )
        count = cur.fetchone()[0]
        assert count == 0, (
            f"Expected 0 budget_counters rows after grant deletion, "
            f"got {count} — CASCADE not working (NFR-4, design §1)"
        )
