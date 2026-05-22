"""
Acceptance test: audit hash chain integrity (T-1.7.5).

Uses a live Postgres 16 testcontainer with all Liquibase migrations applied,
then calls the REAL audit_emit() helper from mintkey_models.audit and verifies
the full hash-chain end-to-end.

Tests:
  - test_genesis_hash_is_correct   : first event's prev_hash == genesis sentinel
  - test_hash_chain_links_correctly: each event's prev_hash == previous event's hash
  - test_hash_computation_matches_spec: manual recompute matches stored hash
  - test_property_100_events_all_hashes_valid: PBT — 100 events, all hashes verified

Sources:
  - ADR-0014.7 (hash chain mandatory; prev_hash + hash per row, per-tenant)
  - Req AUD-4  (audit hash chain)
  - T-1.7.5    (integration test spec)
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import struct
import subprocess
import sys
import uuid
from typing import Generator

import pytest
import pytest_asyncio
from testcontainers.postgres import PostgresContainer

# ---------------------------------------------------------------------------
# Make mintkey_models importable when running from the repo root.
# ---------------------------------------------------------------------------
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
_MODELS_DIR = os.path.join(_REPO_ROOT, "packages/python/mintkey-models")
if _MODELS_DIR not in sys.path:
    sys.path.insert(0, _MODELS_DIR)

from mintkey_models.audit import audit_emit, compute_hash  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CHANGELOG_DIR = os.path.join(_REPO_ROOT, "apps/admin-api", "db", "changelog")
MASTER_CHANGELOG = "db.changelog-master.yaml"
LIQUIBASE_IMAGE = "liquibase/liquibase:4.27.0"

# The genesis sentinel: sha256("mintkey-audit-genesis-v1:" + tenant_id_str)
# where tenant_id_str is str(uuid) — matches how audit_chain_state is seeded.
def _genesis_hash(tenant_id: uuid.UUID) -> bytes:
    return hashlib.sha256(
        f"mintkey-audit-genesis-v1:{tenant_id}".encode()
    ).digest()


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
# Module-level fixture: one container + one Liquibase run for all tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def pg_dsn() -> Generator[str, None, None]:
    """
    Start Postgres 16, apply all Liquibase migrations, and yield an
    asyncpg-compatible DSN for use in async tests.
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

        # asyncpg DSN for SQLAlchemy async engine
        dsn = f"postgresql+asyncpg://{user}:{password}@{host}:{port}/{db}"
        yield dsn


# ---------------------------------------------------------------------------
# Per-test fixture: fresh tenant + seeded audit_chain_state
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def seeded_tenant(pg_dsn: str):
    """
    Create a fresh tenant and seed audit_chain_state with the genesis hash.
    Returns (async_session_maker, tenant_id).

    The superuser role is used so RLS does not interfere with test setup.
    We set app.platform_admin_view='on' in each session for RLS bypass on
    audit_events reads; audit_emit itself sets app.current_tenant.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )

    engine = create_async_engine(pg_dsn, echo=False)
    session_factory = async_sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    tenant_id = uuid.uuid4()
    genesis = _genesis_hash(tenant_id)

    async with session_factory() as setup_session:
        async with setup_session.begin():
            # Bypass RLS for setup (superuser already bypasses, but be explicit)
            await setup_session.execute(
                text("SET app.platform_admin_view TO 'on'")
            )
            await setup_session.execute(
                text(
                    "INSERT INTO tenants (id, slug, display_name, isolation_mode, status, settings)"
                    " VALUES (:id, :slug, :dn, 'row', 'active', '{}')"
                ),
                {"id": str(tenant_id), "slug": f"t_{tenant_id.hex[:8]}", "dn": "Test Tenant"},
            )
            await setup_session.execute(
                text(
                    "INSERT INTO audit_chain_state (tenant_id, head_event_id, head_hash)"
                    " VALUES (:tid, NULL, :hash)"
                ),
                {"tid": str(tenant_id), "hash": genesis},
            )

    yield session_factory, tenant_id

    await engine.dispose()


# ---------------------------------------------------------------------------
# Helper: emit one event inside a transaction with tenant context set
# ---------------------------------------------------------------------------


async def _emit(session_factory, tenant_id: uuid.UUID, event_type: str = "test.event") -> None:
    """Emit a single audit event for tenant_id."""
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    tid_str = str(tenant_id)
    async with session_factory() as session:
        async with session.begin():
            # SET does not support bound parameters; use literal interpolation.
            # tid_str is a UUID string — safe to embed directly.
            await session.execute(
                text(f"SET app.current_tenant TO '{tid_str}'")
            )
            await audit_emit(
                session,
                tenant_id,
                event_type,
                None,          # actor_id
                "system",      # actor_type
                None,          # target_id
                None,          # target_type
                {"seq": 0},    # payload
            )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_genesis_hash_is_correct(seeded_tenant):
    """
    First event's prev_hash must equal sha256("mintkey-audit-genesis-v1:" + tenant_id).

    Source: T-1.7.5; ADR-0014.7 genesis sentinel.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    session_factory, tenant_id = seeded_tenant
    genesis = _genesis_hash(tenant_id)

    await _emit(session_factory, tenant_id)

    async with session_factory() as session:
        await session.execute(text("SET app.platform_admin_view TO 'on'"))
        result = await session.execute(
            text(
                "SELECT prev_hash FROM audit_events"
                " WHERE tenant_id = :tid ORDER BY at ASC LIMIT 1"
            ),
            {"tid": str(tenant_id)},
        )
        row = result.fetchone()

    assert row is not None, "No audit event was inserted"
    assert row[0] == genesis, (
        f"First event prev_hash {row[0].hex()} != genesis {genesis.hex()}"
    )


@pytest.mark.asyncio
async def test_hash_chain_links_correctly(seeded_tenant):
    """
    Insert 5 events; each event's prev_hash must equal the previous event's hash.

    Source: T-1.7.5; ADR-0014.7 §chain linkage.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    session_factory, tenant_id = seeded_tenant

    for _ in range(5):
        await _emit(session_factory, tenant_id)

    async with session_factory() as session:
        await session.execute(text("SET app.platform_admin_view TO 'on'"))
        result = await session.execute(
            text(
                "SELECT prev_hash, hash FROM audit_events"
                " WHERE tenant_id = :tid ORDER BY at ASC"
            ),
            {"tid": str(tenant_id)},
        )
        rows = result.fetchall()

    assert len(rows) == 5, f"Expected 5 events, got {len(rows)}"

    for i in range(1, len(rows)):
        prev_row_hash = rows[i - 1][1]  # hash of event i-1
        this_row_prev = rows[i][0]       # prev_hash of event i
        assert prev_row_hash == this_row_prev, (
            f"Chain broken at event {i}: "
            f"prev event hash={prev_row_hash.hex()}, "
            f"this event prev_hash={this_row_prev.hex()}"
        )


@pytest.mark.asyncio
async def test_hash_computation_matches_spec(seeded_tenant):
    """
    Manually recompute hash = sha256(canonical_json(event_minus_hash) + prev_hash)
    and verify it matches the stored hash.

    Source: T-1.7.5; ADR-0014.7 hash formula.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    session_factory, tenant_id = seeded_tenant

    await _emit(session_factory, tenant_id, event_type="spec.verify")

    async with session_factory() as session:
        await session.execute(text("SET app.platform_admin_view TO 'on'"))
        result = await session.execute(
            text(
                "SELECT id, event_type, actor_id, actor_type,"
                "       target_id, target_type, payload, prev_hash, hash, at"
                " FROM audit_events"
                " WHERE tenant_id = :tid ORDER BY at ASC LIMIT 1"
            ),
            {"tid": str(tenant_id)},
        )
        row = result.fetchone()

    assert row is not None

    # Reconstruct the event_fields dict exactly as audit_emit builds it.
    event_fields = {
        "id": str(row[0]),
        "tenant_id": str(tenant_id),
        "event_type": row[1],
        "actor_id": str(row[2]) if row[2] is not None else None,
        "actor_type": row[3],
        "target_id": str(row[4]) if row[4] is not None else None,
        "target_type": row[5],
        "payload": row[6],  # already a dict from JSONB
        "at": row[9].isoformat(),
    }
    prev_hash: bytes = row[7]
    stored_hash: bytes = row[8]

    recomputed = compute_hash(event_fields, prev_hash)

    assert recomputed == stored_hash, (
        f"Recomputed hash {recomputed.hex()} != stored hash {stored_hash.hex()}"
    )


@pytest.mark.asyncio
async def test_property_100_events_all_hashes_valid(seeded_tenant):
    """
    PBT: insert 100 events, recompute every hash from scratch, assert all match.

    Source: T-1.7.5; ADR-0014.7 §chain integrity.
    """
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    session_factory, tenant_id = seeded_tenant

    for i in range(100):
        await _emit(session_factory, tenant_id, event_type=f"pbt.event.{i}")

    async with session_factory() as session:
        await session.execute(text("SET app.platform_admin_view TO 'on'"))
        result = await session.execute(
            text(
                "SELECT id, event_type, actor_id, actor_type,"
                "       target_id, target_type, payload, prev_hash, hash, at"
                " FROM audit_events"
                " WHERE tenant_id = :tid ORDER BY at ASC"
            ),
            {"tid": str(tenant_id)},
        )
        rows = result.fetchall()

    assert len(rows) == 100, f"Expected 100 events, got {len(rows)}"

    for i, row in enumerate(rows):
        event_fields = {
            "id": str(row[0]),
            "tenant_id": str(tenant_id),
            "event_type": row[1],
            "actor_id": str(row[2]) if row[2] is not None else None,
            "actor_type": row[3],
            "target_id": str(row[4]) if row[4] is not None else None,
            "target_type": row[5],
            "payload": row[6],
            "at": row[9].isoformat(),
        }
        prev_hash: bytes = row[7]
        stored_hash: bytes = row[8]

        recomputed = compute_hash(event_fields, prev_hash)
        assert recomputed == stored_hash, (
            f"PBT: hash mismatch at event index {i} (type={row[1]}): "
            f"recomputed={recomputed.hex()}, stored={stored_hash.hex()}"
        )
