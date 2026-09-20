"""
Integration test — single trace ID + per-transition metric increments.

Feature: agent-access-requests — Task 9.3.

Asserts the two observability guarantees of Requirement 11 against a REAL
Postgres 16 testcontainer with the real Liquibase changelogs applied
(changeset 030 present):

  1. Single trace ID (Req 11.1) — "WHEN an agent request flows from MCP_Server
     through Admin_API to the Admin_Console approval, THE system SHALL produce
     OTel spans ... that share a single trace ID, such that the spans are
     retrievable as one trace." Task 9.1 added
     ``mintkey_models.audit.current_trace_id()`` + the ``:trace_id`` INSERT bind
     on the audit envelope + admin-ui BFF ``traceparent`` forwarding. Because
     every service continues the inbound ``traceparent`` (W3C Trace Context),
     all spans on the path — and every audit row they emit — carry ONE trace
     id. The realistic, harness-testable cross-op assertion is:

       (b) a ``create`` and its later ``approve``, executed within ONE active
           trace context, produce ``access_request.*`` audit rows whose
           ``trace_id`` column is identical; AND
       (c) that shared ``trace_id`` equals the active span's W3C trace-id
           (proving it is stamped from the active OTel span, not invented) —
           which is exactly what an inbound ``traceparent`` forwarded through
           the admin-ui BFF preserves into the admin-api span.

     The unit-level "audit_emit stamps the active trace_id" assertion is already
     covered by ``packages/python/mintkey-models/tests/test_audit.py``
     (``TestCurrentTraceId`` / ``test_emit_stamps_current_trace_id``); this file
     does NOT duplicate it — it focuses on the CROSS-OP (create+approve) trace
     equality that only an integration harness can show. If OpenTelemetry is not
     importable, the trace portion skips gracefully; the metric assertions still
     run.

  2. Metric increments (Req 11.2) — "WHEN a request transitions to the created,
     approved, rejected, or expired state, THE system SHALL increment the
     corresponding OTel counter metric labelled with ``kind`` and
     ``tenant_id``." We sample the four
     ``access_request_{created,approved,rejected,expired}_total{kind,tenant_id}``
     counters from the shared prometheus ``REGISTRY`` immediately before and
     after each corresponding transition (create / approve / reject /
     sweep→expired) and assert the delta is EXACTLY 1 for the right
     ``kind`` + ``tenant_id`` label pair (and that unrelated label pairs are
     untouched).

Testing approach (mirrors ``test_access_requests_approve_properties.py``):
  - ADD-ONLY file. Modifies neither service code nor any existing test
    (Req 14.2).
  - Reuses this directory's ``conftest.py`` session fixtures
    (``postgres_container`` / ``apply_migrations`` / ``admin_app``) — real
    Postgres 16 + real changelogs (AGENTS.md Principle 1: never assert a column
    exists without introspecting it against the real schema; here we read the
    real ``audit_events.trace_id`` column back).
  - SAME module-loop + NullPool ``_ARP_SESSIONMAKER`` + ``_seed`` pattern so
    pooled asyncpg connections never outlive their loop.
  - If Docker / testcontainers / psycopg2 is unavailable, the DB-backed tests
    skip gracefully. If ``prometheus_client`` is unavailable, the metric tests
    skip. If ``opentelemetry`` is unavailable, only the trace-id test skips.

Source: .kiro/specs/agent-access-requests/requirements.md Req 11.1, 11.2;
        design.md §Metrics; Task 9.1 (current_trace_id + :trace_id bind),
        Task 9.2 (record_transition counters); ADR-0008, ADR-0017.11, ADR-0019.
"""
from __future__ import annotations

import asyncio
import secrets
import uuid
from typing import Any

import pytest

from admin_api.services.access_requests import (
    _new_request_id,
    _request_wire_to_uuid,
    approve,
    create_access_request,
    reject,
    sweep_tenant_expired,
)

# ---------------------------------------------------------------------------
# Optional-dependency guards (mirror the repo's skip conventions).
# ---------------------------------------------------------------------------
try:  # pragma: no cover - import guard
    import psycopg2  # noqa: F401

    _PSYCOPG2 = True
except Exception:  # pragma: no cover
    _PSYCOPG2 = False

try:  # pragma: no cover - import guard
    from prometheus_client import REGISTRY

    _PROMETHEUS = True
except Exception:  # pragma: no cover
    _PROMETHEUS = False

try:  # pragma: no cover - import guard
    from opentelemetry import trace as _otel_trace
    from opentelemetry.sdk.trace import TracerProvider as _TracerProvider

    _OTEL = True
except Exception:  # pragma: no cover
    _OTEL = False


# One persistent event loop for the whole module. A fresh loop per call would
# orphan pooled asyncpg connections created on an earlier loop; every coroutine
# here runs on the SAME loop and the dedicated NullPool engine keeps no
# connection alive between calls.
_LOOP = asyncio.new_event_loop()


def _run(coro: Any) -> Any:
    """Drive an async coroutine to completion on the shared module loop."""
    return _LOOP.run_until_complete(coro)


# ===========================================================================
# Fake Vault Adapter client — for the integration/approve path.
# ``approve`` (integration branch) calls ``put_credential``; the access-request
# grant branch used here does not, but a fake is harmless and matches the
# approve-properties test.
# ===========================================================================


class _FakeVault:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def put_credential(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"key_version": 1}


# ===========================================================================
# testcontainer plumbing (mirrors test_access_requests_approve_properties.py)
# ===========================================================================


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


# Dedicated NullPool sessionmaker for these tests, set by ``_seed``.
_ARP_SESSIONMAKER: Any = None


async def _new_session():  # type: ignore[no-untyped-def]
    assert _ARP_SESSIONMAKER is not None, "_seed fixture must run first"
    return _ARP_SESSIONMAKER()


@pytest.fixture(scope="module")
def _seed(admin_app, apply_migrations, postgres_container):  # type: ignore[no-untyped-def]
    """Seed one tenant + a requesting agent + a service; return their IDs.

    Builds a dedicated NullPool async engine (bound to the testcontainer DB) and
    publishes its sessionmaker to ``_ARP_SESSIONMAKER`` so the test bodies open
    sessions on the single shared loop without a connection pool.

    Depends on ``apply_migrations`` so changeset 030 (access_requests) and the
    ``audit_events.trace_id`` column (changeset 007) are present.
    """
    import hashlib

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

    tenant_id = str(uuid.uuid4())
    _exec(
        postgres_container,
        "INSERT INTO tenants (id, slug, display_name, isolation_mode, status)"
        " VALUES (%s, %s, %s, 'row', 'active')",
        (tenant_id, f"arp-obs-{tenant_id[:8]}", "arp-obs"),
    )

    agent_id = str(uuid.uuid4())
    raw = "mk_agent_" + secrets.token_hex(20)
    _exec(
        postgres_container,
        "INSERT INTO agents"
        " (id, tenant_id, name, description, api_key_hash, api_key_fingerprint,"
        "  mcp_endpoint, status, rate_limit_rps)"
        " VALUES (%s, %s, %s, NULL, %s, %s, %s, 'active', NULL)",
        (
            agent_id,
            tenant_id,
            "arp-obs-requesting-agent",
            PasswordHasher().hash(raw),
            hashlib.sha256(raw.encode()).digest()[:8].hex(),
            f"http://localhost:8100/v1/agents/{agent_id}",
        ),
    )

    service_id = str(uuid.uuid4())
    _exec(
        postgres_container,
        "INSERT INTO services"
        " (id, tenant_id, name, slug, display_name, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'bearer_token', 'active')",
        (
            service_id,
            tenant_id,
            "arp-obs-service",
            "arp-obs-service",
            "arp-obs-service",
            "https://api.example.com",
        ),
    )

    yield {
        "tenant_id": tenant_id,
        "requesting_agent_id": agent_id,
        "service_id": service_id,
    }

    _LOOP.run_until_complete(arp_engine.dispose())
    _ARP_SESSIONMAKER = None


# ===========================================================================
# Direct-INSERT helper for seeding a PENDING row that approve/reject/sweep act on
# (the same wire-id minting used by the approve-properties test).
# ===========================================================================


def _seed_pending_access(  # type: ignore[no-untyped-def]
    postgres_container,
    *,
    tenant_id: str,
    requesting_agent_id: str,
    service_id: str,
    action: str,
    expires_at,
    created_at,
) -> str:
    """INSERT one pending ``access`` row with a fresh, decodable ``request_`` id."""
    wire_id = _new_request_id()
    row_uuid = _request_wire_to_uuid(wire_id)
    _exec(
        postgres_container,
        "INSERT INTO access_requests"
        " (id, tenant_id, kind, status, requesting_agent_id, service_id, action,"
        "  expires_at, created_at, created_by)"
        " VALUES (%s, %s, 'access', 'pending', %s, %s, %s, %s, %s, %s)",
        (
            str(row_uuid),
            tenant_id,
            requesting_agent_id,
            service_id,
            action,
            expires_at,
            created_at,
            requesting_agent_id,
        ),
    )
    return wire_id


# ===========================================================================
# prometheus_client sampling helper.
# ===========================================================================


def _counter_value(name: str, *, kind: str, tenant_id: str) -> float:
    """Return the current value of ``<name>{kind,tenant_id}`` (0.0 if never set).

    prometheus ``Counter`` samples end with ``_total``; the metric NAMEs already
    carry ``_total`` (e.g. ``access_request_created_total``), so the sample name
    is ``<name>`` itself. A label pair that has never been ``.inc()``-ed has no
    sample yet, which ``get_sample_value`` reports as ``None`` → treated as 0.0.
    """
    value = REGISTRY.get_sample_value(
        name, {"kind": kind, "tenant_id": tenant_id}
    )
    return float(value) if value is not None else 0.0


# ===========================================================================
# Req 11.2 — per-transition counter increments
# ===========================================================================


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
@pytest.mark.skipif(not _PROMETHEUS, reason="prometheus_client unavailable")
class TestMetricIncrements:
    """Req 11.2 — each of created / approved / rejected / expired increments its
    ``access_request_<transition>_total{kind,tenant_id}`` counter by exactly 1."""

    def test_created_counter_increments_by_one(self, _seed, postgres_container) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        action = "read-" + uuid.uuid4().hex[:8]

        before = _counter_value(
            "access_request_created_total", kind="access", tenant_id=tenant_id
        )
        # An unrelated label pair must stay untouched.
        other_before = _counter_value(
            "access_request_created_total", kind="integration", tenant_id=tenant_id
        )

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await create_access_request(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        requesting_agent_id=uuid.UUID(req_agent),
                        service_id=uuid.UUID(service),
                        action=action,
                    )
            finally:
                await session.close()

        _run(_do())

        after = _counter_value(
            "access_request_created_total", kind="access", tenant_id=tenant_id
        )
        other_after = _counter_value(
            "access_request_created_total", kind="integration", tenant_id=tenant_id
        )
        assert after - before == 1.0
        assert other_after == other_before

    def test_approved_counter_increments_by_one(self, _seed, postgres_container) -> None:
        from datetime import datetime, timedelta, timezone

        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        action = "approve-" + uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        wire_id = _seed_pending_access(
            postgres_container,
            tenant_id=tenant_id,
            requesting_agent_id=req_agent,
            service_id=service,
            action=action,
            expires_at=now + timedelta(days=30),
            created_at=now,
        )

        before = _counter_value(
            "access_request_approved_total", kind="access", tenant_id=tenant_id
        )

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    result = await approve(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id,
                        vault=_FakeVault(),  # type: ignore[arg-type]
                    )
                return result.status
            finally:
                await session.close()

        assert _run(_do()) == "approved"

        after = _counter_value(
            "access_request_approved_total", kind="access", tenant_id=tenant_id
        )
        assert after - before == 1.0

    def test_rejected_counter_increments_by_one(self, _seed, postgres_container) -> None:
        from datetime import datetime, timedelta, timezone

        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        action = "reject-" + uuid.uuid4().hex[:8]
        now = datetime.now(timezone.utc)
        wire_id = _seed_pending_access(
            postgres_container,
            tenant_id=tenant_id,
            requesting_agent_id=req_agent,
            service_id=service,
            action=action,
            expires_at=now + timedelta(days=30),
            created_at=now,
        )

        before = _counter_value(
            "access_request_rejected_total", kind="access", tenant_id=tenant_id
        )

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    result = await reject(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id,
                        reason="not needed right now",
                    )
                return result.status
            finally:
                await session.close()

        assert _run(_do()) == "rejected"

        after = _counter_value(
            "access_request_rejected_total", kind="access", tenant_id=tenant_id
        )
        assert after - before == 1.0

    def test_expired_counter_increments_by_one(self, _seed, postgres_container) -> None:
        from datetime import datetime, timedelta, timezone

        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        action = "expire-" + uuid.uuid4().hex[:8]
        # Seed a single ALREADY-ELAPSED pending row so the tenant sweep flips
        # exactly one row → expired.
        now = datetime.now(timezone.utc)
        _seed_pending_access(
            postgres_container,
            tenant_id=tenant_id,
            requesting_agent_id=req_agent,
            service_id=service,
            action=action,
            expires_at=now - timedelta(seconds=1),
            created_at=now - timedelta(days=31),
        )

        before = _counter_value(
            "access_request_expired_total", kind="access", tenant_id=tenant_id
        )

        async def _do() -> int:
            session = await _new_session()
            try:
                async with session.begin():
                    return await sweep_tenant_expired(
                        session, tenant_id=uuid.UUID(tenant_id)
                    )
            finally:
                await session.close()

        expired_count = _run(_do())
        assert expired_count == 1

        after = _counter_value(
            "access_request_expired_total", kind="access", tenant_id=tenant_id
        )
        assert after - before == 1.0


# ===========================================================================
# Req 11.1 — single trace ID across create + approve
# ===========================================================================


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
@pytest.mark.skipif(not _OTEL, reason="opentelemetry (SDK) unavailable")
class TestSingleTraceId:
    """Req 11.1 — a create and its later approve, run within ONE active trace
    context, produce audit rows sharing that trace's id (stamped from the active
    OTel span by ``current_trace_id()``), which is exactly what an inbound
    ``traceparent`` forwarded through the admin-ui BFF preserves into admin-api.
    """

    def test_create_then_approve_share_one_trace_id(
        self, _seed, postgres_container
    ) -> None:
        # A real SDK TracerProvider so spans have a valid, sampled context and
        # ``current_trace_id()`` returns a genuine 32-hex trace id. Installed via
        # the API only if none is set, so we never clobber an app-configured
        # provider (idempotent, additive).
        provider = _otel_trace.get_tracer_provider()
        if not isinstance(provider, _TracerProvider):
            _otel_trace.set_tracer_provider(_TracerProvider())
        tracer = _otel_trace.get_tracer("test.access_requests.observability")

        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        action = "trace-" + uuid.uuid4().hex[:8]

        # Run create + approve inside ONE active span so both audit rows are
        # stamped with the same active trace id (as they would be when the whole
        # flow shares one inbound traceparent MCP → admin-api → admin-ui).
        with tracer.start_as_current_span("access_request.flow") as span:
            expected_trace_id = _otel_trace.format_trace_id(
                span.get_span_context().trace_id
            )

            async def _create() -> str:
                session = await _new_session()
                try:
                    async with session.begin():
                        created = await create_access_request(
                            session,
                            tenant_id=uuid.UUID(tenant_id),
                            requesting_agent_id=uuid.UUID(req_agent),
                            service_id=uuid.UUID(service),
                            action=action,
                        )
                    return created.request_id
                finally:
                    await session.close()

            wire_id = _run(_create())

            async def _approve() -> None:
                session = await _new_session()
                try:
                    async with session.begin():
                        await approve(
                            session,
                            tenant_id=uuid.UUID(tenant_id),
                            request_id=wire_id,
                            vault=_FakeVault(),  # type: ignore[arg-type]
                        )
                finally:
                    await session.close()

            _run(_approve())

        row_uuid = _request_wire_to_uuid(wire_id)

        # Read the trace_id column of the created + approved audit rows for this
        # request straight from the real audit_events table (introspect the real
        # column, not an assumption — AGENTS.md Principle 1).
        created_trace = _scalar(
            postgres_container,
            "SELECT trace_id FROM audit_events"
            " WHERE tenant_id = %s AND target_id = %s"
            "   AND event_type = 'access_request.created'",
            (tenant_id, str(row_uuid)),
        )
        approved_trace = _scalar(
            postgres_container,
            "SELECT trace_id FROM audit_events"
            " WHERE tenant_id = %s AND target_id = %s"
            "   AND event_type = 'access_request.approved'",
            (tenant_id, str(row_uuid)),
        )

        # Both rows carry a trace id, they are identical, and they equal the
        # active span's W3C trace-id (Req 11.1).
        assert created_trace is not None, "created audit row has no trace_id"
        assert approved_trace is not None, "approved audit row has no trace_id"
        assert created_trace == approved_trace
        assert created_trace == expected_trace_id
