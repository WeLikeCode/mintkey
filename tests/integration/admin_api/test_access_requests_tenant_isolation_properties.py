"""
Property-based test (Hypothesis) for agent-access-requests TENANT ISOLATION.

Feature: agent-access-requests — Task 6.2 (architecture-flavored, add-only).

Exercises the tenant-isolation invariant of the service layer in
``admin_api.services.access_requests`` against a REAL Postgres 16 testcontainer
with the real Liquibase changelogs applied (changeset 030 present, RLS policy
``tenant_isolation`` active on ``access_requests``):

  - ``get_request``      (read)
  - ``list_requests``    (read)
  - ``approve``          (mutation)
  - ``reject``           (mutation)
  - ``connection_test``  (mutation-shaped diagnostic)

Property (statement copied verbatim from
``.kiro/specs/agent-access-requests/design.md`` §Correctness Properties):

  - Property 2 — Tenant isolation holds for every cross-tenant reference
                 (Validates: Requirements 4.4, 5.5, 8.6, 12.2, 12.3, 12.4)

Why this is an architecture / red-team property (design §Testing Strategy):
  Every service function resolves and SETS the tenant GUC itself from its
  ``tenant_id`` argument (``set_tenant_context``), so an operation is only ever
  evaluated *inside* a tenant context — never unscoped. RLS then makes any row
  owned by a different tenant invisible. This test seeds a request row in tenant
  A and asserts that:

    1. Under tenant B's context (get/approve/reject/test on A's ``request_id``)
       → ``AccessRequestError`` code ``request_not_found`` (RLS hides the row),
       and ``list_requests`` under B never contains A's row.
    2. Under a RANDOM, non-existent tenant context (fuzzed) — the "no resolvable
       tenant context" case (Req 12.4) — the same operations respond as though
       the row does not exist (``request_not_found`` / empty list); the row is
       NEVER operated on unscoped.

  In every case A's row must remain untouched (status/reason unchanged, no
  grant/service/credential created). If any cross-tenant reference ever becomes
  visible or actionable, that is a GENUINE tenant-isolation defect and the
  property fails with a counterexample — it is NOT worked around.

Testing approach (mirrors ``test_access_requests_approve_properties.py`` and
``test_access_requests_create_properties.py``):
  - The property runs a MINIMUM of 100 Hypothesis iterations
    (``@settings(max_examples=...)`` with ``>= 100``).
  - This is an ADD-ONLY file. It modifies neither the service code nor any
    existing test (Req 14.2).
  - Uses the SAME session-scoped ``postgres_container`` / ``apply_migrations`` /
    ``admin_app`` conftest fixtures, the SAME module-loop + NullPool
    ``_ARP_SESSIONMAKER`` + ``_seed`` pattern, but the ``_seed`` fixture here
    seeds TWO tenants (A and B) so cross-tenant references can be exercised.
    If Docker / testcontainers / psycopg2 is unavailable the tests skip
    gracefully (matching the repo's skip conventions).

Source: .kiro/specs/agent-access-requests/design.md §Correctness Properties
        (Property 2), §Testing Strategy; requirements.md Req 4.4, 5.5, 8.6,
        12.2, 12.3, 12.4; ADR-0008 (tenant GUC + RLS), ADR-0017.11 (prefixed
        ULID), architecture-principles.md P-3 (tenant isolation is structural).
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from admin_api.services.access_requests import (
    AccessRequestError,
    _new_request_id,
    _request_wire_to_uuid,
    approve,
    connection_test,
    get_request,
    list_requests,
    reject,
)

# Minimum iterations for the property (Task 6.2: >= 100). Kept in the 100-120
# band because each example does real DB work (Task 6.2 runtime bound).
_MAX_EXAMPLES = 110

# Hypothesis + a per-example real DB round-trip is slow and reuses a shared
# module-scoped fixture across examples, so disable the deadline and the
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
# connection alive between calls.
_LOOP = asyncio.new_event_loop()


def _run(coro: Any) -> Any:
    """Drive an async coroutine to completion on the shared module loop."""
    return _LOOP.run_until_complete(coro)


# ===========================================================================
# Fake Vault Adapter client — for the integration-finalize approve path.
#
# ``approve`` (integration branch) would call ``vault.put_credential(...)``. In
# this test the target row is ALWAYS invisible to the caller's tenant (RLS), so
# ``approve`` must fail with ``request_not_found`` BEFORE any vault interaction.
# The fake therefore records calls purely so the test can assert it was NEVER
# invoked (no cross-tenant write occurred).
# ===========================================================================


class _FakeVault:
    """Minimal async vault stub: records puts; must never be called here."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def put_credential(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"key_version": 1}


# ===========================================================================
# testcontainer plumbing (mirrors the sibling property tests)
# ===========================================================================

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


def _scalar(postgres_container, sql: str, params: tuple[Any, ...] = ()) -> Any:  # type: ignore[no-untyped-def]
    conn = _conn(postgres_container)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _fetchone(postgres_container, sql: str, params: tuple[Any, ...] = ()):  # type: ignore[no-untyped-def]
    conn = _conn(postgres_container)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


# Dedicated NullPool sessionmaker for the property tests, set by ``_seed``.
# NullPool means each session's connection is opened and fully closed within
# the single shared loop, so no connection is ever cleaned up against a stale
# loop.
_ARP_SESSIONMAKER: Any = None


async def _new_session():  # type: ignore[no-untyped-def]
    """Open an AsyncSession bound to the dedicated NullPool test engine."""
    assert _ARP_SESSIONMAKER is not None, "_seed fixture must run first"
    return _ARP_SESSIONMAKER()


@pytest.fixture(scope="module")
def _seed(admin_app, apply_migrations, postgres_container):  # type: ignore[no-untyped-def]
    """Seed TWO tenants (A + B), each with an agent + a service; return their IDs.

    Tenant A owns the request rows the property seeds; tenant B is the
    "attacker" context whose GUC is used to attempt cross-tenant reads/mutations.
    A random, never-seeded tenant id exercises the "no resolvable tenant
    context" case (Req 12.4).

    Also builds a dedicated NullPool async engine (bound to the testcontainer
    DB) and publishes its sessionmaker to ``_ARP_SESSIONMAKER`` so the property
    bodies open sessions on the single shared loop without a connection pool.

    ``apply_migrations`` is depended on so changeset 030 (access_requests + its
    RLS policy) is present before any read/mutation runs.
    """
    import hashlib
    import secrets

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
            (tid, f"arp-iso-{label}-{tid[:8]}", f"arp-iso-{label}"),
        )
        return tid

    def _agent(tenant_id: str, name: str) -> str:
        from argon2 import PasswordHasher

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

    tenant_a = _tenant("a")
    tenant_b = _tenant("b")

    yield {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "agent_a": _agent(tenant_a, "arp-iso-a-agent"),
        "target_a": _agent(tenant_a, "arp-iso-a-target"),
        "service_a": _service(tenant_a, "arp-iso-a-service"),
        # Tenant B has its own agent/service so B is a fully-formed, active
        # tenant (its GUC resolves) — the isolation must hold on data, not on B
        # being empty.
        "agent_b": _agent(tenant_b, "arp-iso-b-agent"),
        "service_b": _service(tenant_b, "arp-iso-b-service"),
    }

    _LOOP.run_until_complete(arp_engine.dispose())
    _ARP_SESSIONMAKER = None


# ===========================================================================
# Direct-INSERT seeding helper (mirrors the approve-properties test).
#
# ``get``/``approve``/``reject``/``test`` decode the wire ``request_id`` back to
# the stored PK (ADR-0017.11), so we mint the wire id via the module's own
# ``_new_request_id`` and store the matching UUID via ``_request_wire_to_uuid``.
# ===========================================================================

_UTC = timezone.utc


def _seed_request(
    postgres_container,  # type: ignore[no-untyped-def]
    *,
    tenant_id: str,
    kind: str,
    status: str,
    requesting_agent_id: str,
    service_id: str | None = None,
    action: str | None = None,
    target_agent_id: str | None = None,
    share_direction: str | None = None,
    proposed_config: dict[str, Any] | None = None,
    reason: str | None = None,
) -> str:
    """INSERT one access_requests row (in *tenant_id*) with a decodable id.

    Returns the wire ``request_id`` that the service functions decode.
    """
    wire_id = _new_request_id()
    row_uuid = _request_wire_to_uuid(wire_id)
    now = datetime.now(_UTC)
    exp = now + timedelta(days=30)
    _exec(
        postgres_container,
        "INSERT INTO access_requests"
        " (id, tenant_id, kind, status, requesting_agent_id, service_id, action,"
        "  target_agent_id, share_direction, proposed_config, reason,"
        "  expires_at, created_at, created_by)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS jsonb), %s,"
        "         %s, %s, %s)",
        (
            str(row_uuid),
            tenant_id,
            kind,
            status,
            requesting_agent_id,
            service_id,
            action,
            target_agent_id,
            share_direction,
            json.dumps(proposed_config) if proposed_config is not None else None,
            reason,
            exp,
            now,
            requesting_agent_id,
        ),
    )
    return wire_id


def _row_status_reason(postgres_container, tenant_id: str, wire_id: str):  # type: ignore[no-untyped-def]
    """Read (status, reason) of tenant A's row directly (no RLS — raw conn)."""
    row_uuid = _request_wire_to_uuid(wire_id)
    return _fetchone(
        postgres_container,
        "SELECT status, reason FROM access_requests WHERE id = %s AND tenant_id = %s",
        (str(row_uuid), tenant_id),
    )


def _artifact_counts(postgres_container, tenant_id: str) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    """(#grants, #services, #credentials) for a tenant — for no-side-effect checks."""
    grants = int(
        _scalar(postgres_container,
                "SELECT count(*) FROM permission_grants WHERE tenant_id = %s",
                (tenant_id,))
    )
    services = int(
        _scalar(postgres_container,
                "SELECT count(*) FROM services WHERE tenant_id = %s", (tenant_id,))
    )
    creds = int(
        _scalar(postgres_container,
                "SELECT count(*) FROM credentials WHERE tenant_id = %s", (tenant_id,))
    )
    return grants, services, creds


# Strategies -----------------------------------------------------------------

# A non-empty, non-whitespace action Postgres can store (no NUL / control chars
# — a generator constraint, not a spec change; Postgres rejects 0x00 in text).
_db_safe_action = st.text(
    alphabet=st.characters(min_codepoint=0x21, max_codepoint=0x7E),
    min_size=1,
    max_size=16,
).filter(lambda s: s.strip())

# The kinds a seeded tenant-A request may take.
_kind = st.sampled_from(["access", "share", "integration"])

# "foreign tenant context" selector — either the real, fully-formed tenant B or
# a RANDOM never-seeded tenant id (the Req 12.4 "no resolvable tenant context"
# case). Both must make tenant A's row look non-existent.
_foreign_ctx = st.sampled_from(["tenant_b", "random"])

# A valid non-empty reject reason.
_valid_reason = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    min_size=1,
    max_size=120,
).filter(lambda s: s.strip())


def _seed_tenant_a_request(_seed, postgres_container, kind: str, act: str) -> str:  # type: ignore[no-untyped-def]
    """Seed a pending tenant-A request of the given kind; return its wire id."""
    tenant_a = _seed["tenant_a"]
    agent_a = _seed["agent_a"]
    if kind == "access":
        return _seed_request(
            postgres_container, tenant_id=tenant_a, kind="access",
            status="pending", requesting_agent_id=agent_a,
            service_id=_seed["service_a"], action=act,
        )
    if kind == "share":
        return _seed_request(
            postgres_container, tenant_id=tenant_a, kind="share",
            status="pending", requesting_agent_id=agent_a,
            service_id=_seed["service_a"], action=act,
            target_agent_id=_seed["target_a"], share_direction="inbound",
        )
    return _seed_request(
        postgres_container, tenant_id=tenant_a, kind="integration",
        status="pending", requesting_agent_id=agent_a,
        proposed_config={
            "name": "iso-" + uuid.uuid4().hex[:8],
            "base_url": "https://api.example.com",
            "auth_scheme": "bearer_token",
        },
    )


def _foreign_tenant_uuid(_seed, which: str) -> uuid.UUID:  # type: ignore[no-untyped-def]
    """Resolve the foreign-context tenant id: real tenant B or a random one."""
    if which == "tenant_b":
        return uuid.UUID(_seed["tenant_b"])
    return uuid.uuid4()  # never-seeded → "no resolvable tenant context" (Req 12.4)


# ===========================================================================
# Property 2 — Tenant isolation holds for every cross-tenant reference
# ===========================================================================
# Feature: agent-access-requests, Property 2: Tenant isolation holds for every
# cross-tenant reference — For any request_id belonging to a different tenant,
# every read and every mutation (get, approve, reject, test) evaluated under the
# caller's tenant context SHALL respond as though the request does not exist
# (request_not_found) and SHALL perform no state change; and for any
# request-touching operation with no resolvable tenant context, the operation
# SHALL be rejected rather than executed.


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty2TenantIsolation:
    """Property 2 — tenant A's request is invisible + unactionable under any
    foreign tenant context (real tenant B or a random/none tenant), across every
    read and mutation, with A's row left untouched and no side artifacts."""

    @_DB_SETTINGS
    @given(kind=_kind, ctx=_foreign_ctx, action=_db_safe_action)
    def test_reads_under_foreign_ctx_hide_the_row(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, kind: str, ctx: str, action: str,
    ) -> None:
        """get_request → request_not_found; list_requests never includes A's row
        (Req 4.4, 12.2, 12.3, 12.4)."""
        tenant_a = _seed["tenant_a"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]
        wire_id = _seed_tenant_a_request(_seed, postgres_container, kind, act)
        foreign = _foreign_tenant_uuid(_seed, ctx)

        before = _row_status_reason(postgres_container, tenant_a, wire_id)
        assert before is not None and before[0] == "pending"

        async def _do() -> list[str]:
            session = await _new_session()
            try:
                # get_request under the foreign context must not reveal the row.
                with pytest.raises(AccessRequestError) as exc:
                    await get_request(
                        session, tenant_id=foreign, request_id=wire_id
                    )
                assert exc.value.code == "request_not_found"

                # list_requests under the foreign context must not include it.
                items = await list_requests(session, tenant_id=foreign)
                return [it.request_id for it in items]
            finally:
                await session.close()

        listed_ids = _run(_do())
        assert wire_id not in listed_ids

        # Tenant A's row is untouched.
        after = _row_status_reason(postgres_container, tenant_a, wire_id)
        assert after is not None
        assert after[0] == "pending"
        assert after[1] == before[1]

    @_DB_SETTINGS
    @given(kind=_kind, ctx=_foreign_ctx, action=_db_safe_action)
    def test_approve_under_foreign_ctx_is_not_found_no_effect(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, kind: str, ctx: str, action: str,
    ) -> None:
        """approve on A's request under a foreign context → request_not_found,
        no grant/service/credential, vault never called, A's row unchanged
        (Req 5.5, 12.2, 12.3, 12.4)."""
        tenant_a = _seed["tenant_a"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]
        wire_id = _seed_tenant_a_request(_seed, postgres_container, kind, act)
        foreign = _foreign_tenant_uuid(_seed, ctx)

        a_before = _artifact_counts(postgres_container, tenant_a)
        vault = _FakeVault()

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await approve(
                        session, tenant_id=foreign, request_id=wire_id,
                        vault=vault,  # type: ignore[arg-type]
                        credential={"credential_value": "s3cr3t-canary"},
                        config=None,
                    )
            finally:
                await session.close()

        with pytest.raises(AccessRequestError) as exc:
            _run(_do())
        assert exc.value.code == "request_not_found"

        # Vault was never touched; no cross-tenant write happened.
        assert vault.calls == []
        # No side artifacts in tenant A (nor could any appear in the foreign
        # tenant — approve failed before any write).
        assert _artifact_counts(postgres_container, tenant_a) == a_before
        # A's row is still pending.
        after = _row_status_reason(postgres_container, tenant_a, wire_id)
        assert after is not None and after[0] == "pending"

    @_DB_SETTINGS
    @given(kind=_kind, ctx=_foreign_ctx, action=_db_safe_action, reason=_valid_reason)
    def test_reject_under_foreign_ctx_is_not_found_no_effect(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, kind: str, ctx: str, action: str,
        reason: str,
    ) -> None:
        """reject on A's request under a foreign context → request_not_found;
        A's status/reason unchanged (Req 8.6, 12.2, 12.3, 12.4)."""
        tenant_a = _seed["tenant_a"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]
        wire_id = _seed_tenant_a_request(_seed, postgres_container, kind, act)
        foreign = _foreign_tenant_uuid(_seed, ctx)

        before = _row_status_reason(postgres_container, tenant_a, wire_id)
        assert before is not None and before[0] == "pending"

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await reject(
                        session, tenant_id=foreign, request_id=wire_id,
                        reason=reason,
                    )
            finally:
                await session.close()

        with pytest.raises(AccessRequestError) as exc:
            _run(_do())
        assert exc.value.code == "request_not_found"

        # A's row is unchanged — the foreign reject reason was NOT written.
        after = _row_status_reason(postgres_container, tenant_a, wire_id)
        assert after is not None
        assert after[0] == "pending"
        assert after[1] == before[1]
        assert after[1] != reason

    @_DB_SETTINGS
    @given(ctx=_foreign_ctx, action=_db_safe_action)
    def test_connection_test_under_foreign_ctx_is_not_found(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, ctx: str, action: str,
    ) -> None:
        """connection_test on A's integration request under a foreign context →
        request_not_found, A's row unchanged (Req 12.2, 12.3, 12.4).

        connection_test targets integration proposals, so the seeded row is
        kind=integration; the row is invisible under the foreign GUC, so the
        service returns request_not_found before any handshake."""
        tenant_a = _seed["tenant_a"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]
        wire_id = _seed_tenant_a_request(_seed, postgres_container, "integration", act)
        foreign = _foreign_tenant_uuid(_seed, ctx)

        before = _row_status_reason(postgres_container, tenant_a, wire_id)
        assert before is not None and before[0] == "pending"

        async def _do() -> None:
            session = await _new_session()
            try:
                await connection_test(
                    session, tenant_id=foreign, request_id=wire_id,
                    credential={"credential_value": "s3cr3t-canary"},
                    config=None,
                )
            finally:
                await session.close()

        with pytest.raises(AccessRequestError) as exc:
            _run(_do())
        assert exc.value.code == "request_not_found"

        after = _row_status_reason(postgres_container, tenant_a, wire_id)
        assert after is not None
        assert after[0] == "pending"
        assert after[1] == before[1]
