"""
Unit tests: seed job steps 1-5 idempotency.

Sources:
  - Req 1 AC5, AC6 (seed job idempotency, secrets written once)
  - ADR-0014.7 (audit hash chain mandatory; genesis hash = sha256("mintkey-audit-genesis-v1:" || tenant_id))
  - design §3 Sequence steps 1-5

Tests steps 2-5 (step 1 is pg-wait; skipped here since testcontainers guarantees connectivity).
Steps 6-8 (Vault Adapter keypairs) are tested separately after T-1.0.4 ships.
Steps 9-11 (Keycloak + audit emission) are tested separately after T-1.0.8 and T-1.7.x ship.
"""
from __future__ import annotations

import hashlib
import os
import subprocess
import sys
from pathlib import Path
from typing import Generator

import psycopg2
import psycopg2.extras
import pytest
from testcontainers.postgres import PostgresContainer

# Add seed-job to path so we can import its functions
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
SEED_JOB_DIR = os.path.join(REPO_ROOT, "apps/seed-job")
sys.path.insert(0, SEED_JOB_DIR)

CHANGELOG_DIR = os.path.join(REPO_ROOT, "apps/admin-api", "db", "changelog")
MASTER_CHANGELOG = "db.changelog-master.yaml"
LIQUIBASE_IMAGE = "liquibase/liquibase:4.27.0"


def _apply_liquibase(jdbc_url: str, username: str, password: str) -> None:
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
    """Postgres 16 container with all Liquibase changelogs applied."""
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_verify_liquibase_applied(pg_conn: psycopg2.extensions.connection) -> None:
    """Step 2: verify_liquibase_applied must succeed after migrations ran."""
    from main import verify_liquibase_applied

    verify_liquibase_applied(pg_conn)  # must not raise


def test_seed_default_tenant_creates_t_default(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """Step 3: t_default tenant is created with isolation_mode='row'."""
    from main import seed_default_tenant

    tenant_id = seed_default_tenant(pg_conn)

    with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM tenants WHERE slug = 't_default'")
        row = cur.fetchone()

    assert row is not None, "t_default tenant not found after seed"
    assert str(row["id"]) == tenant_id
    assert row["isolation_mode"] == "row"
    assert row["status"] == "active"


def test_seed_default_tenant_is_idempotent(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """Step 3 idempotency: calling seed_default_tenant twice returns same UUID."""
    from main import seed_default_tenant

    id1 = seed_default_tenant(pg_conn)
    id2 = seed_default_tenant(pg_conn)
    assert id1 == id2


def test_seed_audit_chain_state_genesis_hash(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    Step 4: audit_chain_state genesis hash = sha256("mintkey-audit-genesis-v1:" + tenant_id).
    Source: Req 1 AC12, ADR-0014.7, design §3 step 4.
    """
    from main import seed_audit_chain_state, seed_default_tenant

    tenant_id = seed_default_tenant(pg_conn)
    seed_audit_chain_state(pg_conn, tenant_id)

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT head_hash FROM audit_chain_state WHERE tenant_id = %s",
            (tenant_id,),
        )
        row = cur.fetchone()

    assert row is not None, "audit_chain_state row not found for t_default"
    expected = hashlib.sha256(
        f"mintkey-audit-genesis-v1:{tenant_id}".encode()
    ).digest()
    assert bytes(row[0]) == expected, (
        "Genesis hash mismatch — must be sha256('mintkey-audit-genesis-v1:' + tenant_id)"
    )


def test_seed_audit_chain_state_is_idempotent(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """Step 4 idempotency: calling seed_audit_chain_state twice is a no-op."""
    from main import seed_audit_chain_state, seed_default_tenant

    tenant_id = seed_default_tenant(pg_conn)
    seed_audit_chain_state(pg_conn, tenant_id)
    seed_audit_chain_state(pg_conn, tenant_id)  # must not raise

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM audit_chain_state WHERE tenant_id = %s",
            (tenant_id,),
        )
        count = cur.fetchone()[0]
    assert count == 1


def test_seed_bootstrap_operator_creates_platform_admin(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    Step 5: bootstrap operator is created with is_platform_admin=true
    and membership role=Admin for t_default.
    Source: Req 1 AC5, design §3 step 5.
    """
    from main import seed_bootstrap_operator, seed_default_tenant

    tenant_id = seed_default_tenant(pg_conn)
    operator_id, _password = seed_bootstrap_operator(pg_conn, tenant_id)

    with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT * FROM operators WHERE id = %s", (operator_id,))
        op = cur.fetchone()

    assert op is not None
    assert op["is_platform_admin"] is True
    assert op["status"] == "active"
    assert op["tenant_id"] == tenant_id

    with pg_conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT role FROM operator_tenant_memberships WHERE operator_id = %s AND tenant_id = %s",
            (operator_id, tenant_id),
        )
        mem = cur.fetchone()

    assert mem is not None, "OperatorTenantMembership for bootstrap admin not found"
    assert mem["role"] == "Admin"


def test_seed_bootstrap_operator_is_idempotent(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    Step 5 idempotency: running seed_bootstrap_operator twice yields same operator.
    Second call returns empty password (operator already exists).
    Source: Req 1 AC6.
    """
    from main import seed_bootstrap_operator, seed_default_tenant

    tenant_id = seed_default_tenant(pg_conn)
    id1, pw1 = seed_bootstrap_operator(pg_conn, tenant_id)
    id2, pw2 = seed_bootstrap_operator(pg_conn, tenant_id)

    assert id1 == id2, "Operator ID changed on second seed call — not idempotent"
    assert pw2 == "", "Second call must return empty password (operator already exists)"

    with pg_conn.cursor() as cur:
        cur.execute(
            "SELECT COUNT(*) FROM operators WHERE email = 'admin@mintkey.internal'"
        )
        count = cur.fetchone()[0]
    assert count == 1, f"Expected 1 bootstrap operator, found {count}"


def test_full_steps_1_to_5_run_twice_identical_state(
    pg_conn: psycopg2.extensions.connection,
) -> None:
    """
    Full idempotency: running all steps 1-5 twice leaves DB state identical.
    Source: Req 1 AC6, design §3.
    """
    from main import run_steps_1_to_5

    result1 = run_steps_1_to_5(pg_conn)
    result2 = run_steps_1_to_5(pg_conn)

    assert result1["tenant_id"] == result2["tenant_id"]
    assert result1["operator_id"] == result2["operator_id"]

    with pg_conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) FROM tenants WHERE slug = 't_default'")
        assert cur.fetchone()[0] == 1
        cur.execute("SELECT COUNT(*) FROM audit_chain_state")
        assert cur.fetchone()[0] == 1
        cur.execute(
            "SELECT COUNT(*) FROM operators WHERE email = 'admin@mintkey.internal'"
        )
        assert cur.fetchone()[0] == 1
