"""
Property-based test (Hypothesis) for the agent-access-requests LIST logic.

Feature: agent-access-requests — Task 3.6.

Exercises ``admin_api.services.access_requests.list_requests`` — the operator
review list (Req 4.1, 4.2, 4.3).

Property (statement copied verbatim from
``.kiro/specs/agent-access-requests/design.md`` §Correctness Properties):

  - Property 15 — Listing returns the correct tenant-scoped, filtered, ordered
                  subset (Validates: Requirements 1.7, 4.1, 4.2, 8.4)

Testing approach (mirrors the sibling
``test_access_requests_create_properties.py`` so the two files stay
consistent):
  - Runs a MINIMUM of 100 Hypothesis iterations
    (``@settings(max_examples=...)`` with ``>= 100``).
  - This is an ADD-ONLY file. It modifies neither the service code nor any
    existing test (Req 14.2).
  - The property is inherently DB-backed: ``list_requests`` reads real rows
    under the tenant GUC (RLS, P-3), so it runs against a REAL Postgres 16
    testcontainer with the real Liquibase changelogs applied (changeset 030 +
    seeds). It reuses this directory's session-scoped ``postgres_container`` /
    ``apply_migrations`` / ``admin_app`` conftest fixtures (AGENTS.md
    Principle 1 — never assert behaviour over a schema without introspecting
    it against the real schema). If Docker / testcontainers / psycopg2 is
    unavailable, the test skips gracefully (matching the repo's skip
    conventions).
  - Each example does minimal DB work: it INSERTs a small, generated set of
    ``access_requests`` rows (varied ``kind`` / ``status``, deterministic
    distinct ``created_at`` timestamps) for the primary tenant PLUS one row in
    a DIFFERENT tenant, calls ``list_requests`` once with a generated
    ``status`` / ``kind`` filter, asserts the returned subset is EXACTLY the
    primary-tenant rows matching the filter ordered by ``created_at`` desc
    (tie-broken by ``id`` desc, matching the service's ``ORDER BY``), asserts
    the Req 4.2 required fields are present, and asserts the cross-tenant row
    NEVER appears (Req 8.4 / P-3 tenant scope). It then TRUNCATEs the rows it
    inserted so examples do not accumulate.

Source: .kiro/specs/agent-access-requests/design.md §Correctness Properties
        (Property 15), §Wire Contracts; requirements.md Req 1.7, 4.1, 4.2, 4.3,
        8.4; ADR-0008 (RLS), ADR-0017.11 (prefixed ULIDs).
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from admin_api.services.access_requests import list_requests
from admin_api.utils.wire_ids import db_uuid_to_wire

# Minimum iterations (Task 3.6 requirement: >= 100). Kept in the 100-120 range
# because each example does real DB work (design §Testing Strategy note).
_MAX_EXAMPLES = 110

# Hypothesis + a per-example real DB round-trip reuses a shared session-scoped
# fixture across examples, so disable the deadline and the
# function-scoped-fixture health check (the fixture is intentionally reused).
_DB_SETTINGS = settings(
    max_examples=_MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)


# One persistent event loop for the whole module. A fresh loop per Hypothesis
# example would orphan pooled asyncpg connections created on an earlier loop
# ("Event loop is closed" at pool cleanup), so every coroutine here runs on the
# SAME loop and the dedicated NullPool engine (see ``_seed``) keeps no
# connection alive between calls. Mirrors the create-properties module.
_LOOP = asyncio.new_event_loop()


def _run(coro: Any) -> Any:
    """Drive an async coroutine to completion on the shared module loop."""
    return _LOOP.run_until_complete(coro)


# The closed enums the generators draw from (Req 4.3).
_KINDS = ["access", "integration", "share"]
_STATUSES = ["pending", "approved", "rejected", "expired", "cancelled"]


# ---------------------------------------------------------------------------
# psycopg2 helpers (mirror the sibling create-properties file).
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import guard mirrors repo skip conventions
    import psycopg2  # noqa: F401

    _PSYCOPG2 = True
except Exception:  # pragma: no cover
    _PSYCOPG2 = False


def _conn(postgres_container):  # type: ignore[no-untyped-def]
    import psycopg2

    return psycopg2.connect(
        host=postgres_container.get_container_host_ip(),
        port=postgres_container.get_exposed_port(5432),
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )


def _exec(postgres_container, sql: str, params: tuple[Any, ...] = ()) -> None:  # type: ignore[no-untyped-def]
    conn = _conn(postgres_container)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _exec_many(postgres_container, sql: str, seq: list[tuple[Any, ...]]) -> None:  # type: ignore[no-untyped-def]
    conn = _conn(postgres_container)
    try:
        cur = conn.cursor()
        cur.executemany(sql, seq)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Seed: two tenants (primary + "other"), each with a requesting agent + a
# service, plus a dedicated NullPool async engine so the property body opens
# sessions on the single shared loop without a connection pool.
# ---------------------------------------------------------------------------
_ARP_SESSIONMAKER: Any = None


@pytest.fixture(scope="module")
def _seed(admin_app, apply_migrations, postgres_container):  # type: ignore[no-untyped-def]
    """Seed a PRIMARY tenant and a DIFFERENT tenant, each with a requesting
    agent + a service; publish a NullPool sessionmaker to ``_ARP_SESSIONMAKER``.

    ``apply_migrations`` is depended on so changeset 030 (access_requests) is
    present before any list/insert runs.
    """
    import hashlib
    import secrets

    from argon2 import PasswordHasher
    from sqlalchemy.ext.asyncio import (
        AsyncSession,
        async_sessionmaker,
        create_async_engine,
    )
    from sqlalchemy.pool import NullPool

    global _ARP_SESSIONMAKER

    db_url = (
        f"postgresql+asyncpg://{postgres_container.username}:"
        f"{postgres_container.password}@"
        f"{postgres_container.get_container_host_ip()}:"
        f"{postgres_container.get_exposed_port(5432)}/"
        f"{postgres_container.dbname}"
    )
    arp_engine = create_async_engine(db_url, echo=False, poolclass=NullPool)
    _ARP_SESSIONMAKER = async_sessionmaker(
        bind=arp_engine, class_=AsyncSession, expire_on_commit=False
    )

    def _tenant(label: str) -> str:
        tid = str(uuid.uuid4())
        _exec(
            postgres_container,
            "INSERT INTO tenants (id, slug, display_name, isolation_mode, status)"
            " VALUES (%s, %s, %s, 'row', 'active')",
            (tid, f"arp-list-{label}-{tid[:8]}", f"arp-list-{label}"),
        )
        return tid

    def _agent(tenant_id: str, name: str) -> str:
        aid = str(uuid.uuid4())
        raw = "mk_agent_" + secrets.token_hex(20)
        _exec(
            postgres_container,
            "INSERT INTO agents"
            " (id, tenant_id, name, description, api_key_hash, api_key_fingerprint,"
            "  mcp_endpoint, status, rate_limit_rps)"
            " VALUES (%s, %s, %s, NULL, %s, %s, %s, 'active', NULL)",
            (
                aid,
                tenant_id,
                name,
                PasswordHasher().hash(raw),
                hashlib.sha256(raw.encode()).digest()[:8].hex(),
                f"http://localhost:8100/v1/agents/{aid}",
            ),
        )
        return aid

    def _service(tenant_id: str, name: str) -> str:
        sid = str(uuid.uuid4())
        _exec(
            postgres_container,
            "INSERT INTO services"
            " (id, tenant_id, name, slug, display_name, base_url, auth_scheme, status)"
            " VALUES (%s, %s, %s, %s, %s, %s, 'bearer_token', 'active')",
            (sid, tenant_id, name, name, name, "https://api.example.com"),
        )
        return sid

    primary_tenant = _tenant("primary")
    other_tenant = _tenant("other")

    seed = {
        "tenant_id": primary_tenant,
        "agent_id": _agent(primary_tenant, "arp-list-primary-agent"),
        "service_id": _service(primary_tenant, "arp-list-primary-svc"),
        "other_tenant_id": other_tenant,
        "other_agent_id": _agent(other_tenant, "arp-list-other-agent"),
        "other_service_id": _service(other_tenant, "arp-list-other-svc"),
    }

    yield seed

    _LOOP.run_until_complete(arp_engine.dispose())
    _ARP_SESSIONMAKER = None


async def _new_session():  # type: ignore[no-untyped-def]
    """Open an AsyncSession bound to the dedicated NullPool test engine."""
    assert _ARP_SESSIONMAKER is not None, "_seed fixture must run first"
    return _ARP_SESSIONMAKER()


# The subset of access_requests columns a listing row needs. Kind-specific
# NOT-NULL constraints are respected: access/share carry (service_id, action),
# integration carries proposed_config; share carries (target_agent_id,
# share_direction).
def _row_values(
    *,
    row_id: str,
    tenant_id: str,
    kind: str,
    status: str,
    agent_id: str,
    service_id: str,
    target_agent_id: str | None,
    created_at: datetime,
) -> tuple[Any, ...]:
    if kind == "access":
        svc: str | None = service_id
        action: str | None = "read-" + row_id[:6]
        target: str | None = None
        direction: str | None = None
        proposed: str | None = None
    elif kind == "share":
        svc = service_id
        action = "read-" + row_id[:6]
        target = target_agent_id
        direction = "inbound"
        proposed = None
    else:  # integration
        svc = None
        action = None
        target = None
        direction = None
        proposed = '{"name": "prop-' + row_id[:8] + '"}'
    expires_at = created_at + timedelta(days=30)
    return (
        row_id,
        tenant_id,
        kind,
        status,
        agent_id,
        svc,
        action,
        target,
        direction,
        proposed,
        created_at,
        expires_at,
        agent_id,  # created_by
    )


_INSERT_SQL = (
    "INSERT INTO access_requests"
    " (id, tenant_id, kind, status, requesting_agent_id, service_id, action,"
    "  target_agent_id, share_direction, proposed_config, created_at,"
    "  expires_at, created_by)"
    " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,"
    "         %s::jsonb, %s, %s, %s)"
)


# A generated request row: (kind, status). created_at is derived from the
# row's index so every row has a DISTINCT timestamp and the expected ordering
# is unambiguous.
_req_strategy = st.tuples(st.sampled_from(_KINDS), st.sampled_from(_STATUSES))

# Optional filters: None means "no filter". Drawn from the valid enums (Req 4.3)
# so the call never hits the invalid_argument branch (that branch is covered by
# Property 14 in the sibling file).
_status_filter = st.one_of(st.none(), st.sampled_from(_STATUSES))
_kind_filter = st.one_of(st.none(), st.sampled_from(_KINDS))


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty15ListSubsetOrderScope:
    """Property 15 — the list is the correct tenant-scoped, filtered, ordered
    subset, and cross-tenant rows never appear."""

    # Feature: agent-access-requests, Property 15: Listing returns the correct
    # tenant-scoped, filtered, ordered subset — For any set of requests and any
    # valid status/kind filters, the operator list SHALL return exactly the
    # tenant's requests matching the filters ordered by created_at descending
    # with the required fields; and for any agent, list_my_requests SHALL return
    # exactly that agent's requests scoped to its tenant.

    @_DB_SETTINGS
    @given(
        rows=st.lists(_req_strategy, min_size=0, max_size=8),
        status_filter=_status_filter,
        kind_filter=_kind_filter,
    )
    def test_list_is_tenant_scoped_filtered_ordered(  # type: ignore[no-untyped-def]
        self,
        _seed,
        postgres_container,
        rows: list[tuple[str, str]],
        status_filter: str | None,
        kind_filter: str | None,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        agent_id = _seed["agent_id"]
        service_id = _seed["service_id"]

        # Distinct, monotonically DECREASING created_at per row index so that a
        # smaller index == a LATER timestamp. That makes the expected order
        # simply the insertion order (index 0 first) — before the id tie-break
        # is ever needed, because every timestamp is unique.
        base = datetime(2026, 1, 1, tzinfo=timezone.utc)

        expected: list[tuple[str, str, str]] = []  # (created_at-key, id, wire_id)
        insert_seq: list[tuple[Any, ...]] = []
        for idx, (kind, status) in enumerate(rows):
            row_id = str(uuid.uuid4())
            # Later index -> earlier time, so index 0 is newest.
            created_at = base - timedelta(minutes=idx)
            insert_seq.append(
                _row_values(
                    row_id=row_id,
                    tenant_id=tenant_id,
                    kind=kind,
                    status=status,
                    agent_id=agent_id,
                    service_id=service_id,
                    target_agent_id=agent_id if kind == "share" else None,
                    created_at=created_at,
                )
            )
            matches = (status_filter is None or status == status_filter) and (
                kind_filter is None or kind == kind_filter
            )
            if matches:
                # Sort key: newest first == largest created_at first. We store
                # negative index so Python's ascending sort yields index order.
                expected.append((f"{idx:04d}", row_id, db_uuid_to_wire(row_id, "request")))

        # One cross-tenant row that MUST never appear (Req 8.4 / P-3). Give it a
        # created_at that would sort FIRST if it were (wrongly) included.
        cross_id = str(uuid.uuid4())
        cross_created = base + timedelta(minutes=1)
        cross_kind = "access"
        cross_status = status_filter or "pending"
        _exec(
            postgres_container,
            _INSERT_SQL,
            _row_values(
                row_id=cross_id,
                tenant_id=_seed["other_tenant_id"],
                kind=cross_kind,
                status=cross_status,
                agent_id=_seed["other_agent_id"],
                service_id=_seed["other_service_id"],
                target_agent_id=None,
                created_at=cross_created,
            ),
        )
        cross_wire = db_uuid_to_wire(cross_id, "request")

        if insert_seq:
            _exec_many(postgres_container, _INSERT_SQL, insert_seq)

        try:
            async def _do():  # type: ignore[no-untyped-def]
                session = await _new_session()
                try:
                    return await list_requests(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        status=status_filter,
                        kind=kind_filter,
                    )
                finally:
                    await session.close()

            result = _run(_do())

            returned_ids = [item.request_id for item in result]

            # (1) Cross-tenant row never appears (Req 8.4 / P-3 tenant scope).
            assert cross_wire not in returned_ids, "cross-tenant row leaked into list"

            # (2) The returned set is EXACTLY the primary-tenant rows matching
            #     the filters — no more, no fewer (Req 4.1, 4.2).
            #     (Other test modules TRUNCATE between modules; within this
            #     module we insert only under these two seeded tenants and clean
            #     up in the finally block, so the primary tenant holds exactly
            #     the rows inserted this example.)
            expected_wire_ordered = [wire for _key, _rid, wire in expected]
            assert set(returned_ids) == set(expected_wire_ordered)

            # (3) Ordered by created_at DESC (newest first == smallest index
            #     first, since later index == earlier time). Every timestamp is
            #     distinct, so the order is fully determined.
            assert returned_ids == expected_wire_ordered, (
                "list not ordered by created_at desc"
            )

            # (4) Req 4.2 required fields present on every returned item, and
            #     the filters actually held.
            for item in result:
                assert item.request_id.startswith("request_")
                assert item.kind in _KINDS
                assert item.status in _STATUSES
                assert item.requesting_agent_id.startswith("agent_")
                assert item.created_at is not None
                assert item.expires_at is not None
                if status_filter is not None:
                    assert item.status == status_filter
                if kind_filter is not None:
                    assert item.kind == kind_filter
        finally:
            # Remove every row this example inserted (both tenants) so examples
            # do not accumulate and the "exactly this set" assertion holds next
            # time. Add-only cleanup scoped to the two seeded tenants.
            _exec(
                postgres_container,
                "DELETE FROM access_requests WHERE tenant_id = %s OR tenant_id = %s",
                (tenant_id, _seed["other_tenant_id"]),
            )
