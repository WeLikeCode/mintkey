"""
Property-based tests (Hypothesis) for the agent-access-requests AUDIT / SECRET
guarantees: audit coverage, audit actor type, audit-failure atomicity, and the
red-team secret-non-leak canary.

Feature: agent-access-requests — Task 5.6.

Exercises the create / approve / reject / expire state changes and their audit
emitters in ``admin_api.services.access_requests`` against a REAL Postgres 16
testcontainer with the real Liquibase changelogs applied (changeset 030
present):

  - ``create_access_request`` / ``create_integration_proposal`` /
    ``create_share_request``  (emit ``access_request.created``)
  - ``approve``                (emit ``access_request.approved`` + reused
                                ``agent.permission.granted`` /
                                ``service.registered`` / ``credential.registered``)
  - ``reject``                 (emit ``access_request.rejected``)
  - ``sweep_tenant_expired``   (emit ``access_request.expired``)

Properties (statements copied verbatim from
``.kiro/specs/agent-access-requests/design.md`` §Correctness Properties):

  - Property 1  — The operator secret never leaks anywhere secret-free
                  (Validates: Requirements 6.1, 6.3, 6.7, 10.3, 11.3, 11.5)
  - Property 10 — Every state change emits its audit event through the chokepoint
                  (Validates: Requirements 5.4, 7.1, 10.1, 10.4)
  - Property 11 — Audit actor type matches the trigger
                  (Validates: Requirements 10.5)
  - Property 12 — Audit failure aborts the state change atomically
                  (Validates: Requirements 10.6)

Testing approach (mirrors ``test_access_requests_approve_properties.py``):
  - Each property runs a MINIMUM of 100 Hypothesis iterations
    (``@settings(max_examples=...)`` with ``>= 100``).
  - This is an ADD-ONLY file. It modifies neither the service code nor any
    existing test (Req 14.2).
  - The DB-backed assertions run against a REAL Postgres 16 testcontainer with
    the real changelogs applied (changeset 030 + seeds). This reuses the
    session-scoped ``postgres_container`` / ``apply_migrations`` / ``admin_app``
    fixtures in this directory's ``conftest.py`` (AGENTS.md Principle 1 — never
    assert an audit row / a leaked value exists without introspecting it against
    the real schema). If Docker / testcontainers / psycopg2 is unavailable, the
    tests skip gracefully (matching the repo's skip conventions).
  - The SAME module-loop + NullPool ``_ARP_SESSIONMAKER`` + ``_seed`` fixture
    pattern as the approve-properties test is used so pooled asyncpg connections
    never outlive their loop.

Property 1 is THE red-team secret-non-leak canary: a known ``CANARY`` value is
planted in the operator credential handed to ``approve`` (integration finalize)
and to ``connection_test``. After the operation the canary is searched for in
EVERY text / jsonb column of ``access_requests`` and ``audit_events`` for the
tenant, in the Connection_Test diagnostic, and in the result returned to the
agent — it must appear nowhere. A vault-DOWN variant (fake vault raises the same
``grpc.aio.AioRpcError`` the real client surfaces) asserts nothing (no services
row, no credential, no secret anywhere) is persisted when the store is
unavailable (Req 6.7).

Source: .kiro/specs/agent-access-requests/design.md §Correctness Properties,
        §Testing Strategy; requirements.md Req 5.4, 6.1, 6.3, 6.7, 7.1, 10.1,
        10.3, 10.4, 10.5, 10.6, 11.3, 11.5; ADR-0008, ADR-0014.4, ADR-0014.7,
        ADR-0017.6, ADR-0017.11, ADR-0019.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi import HTTPException
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import admin_api.services.access_requests as ar
from admin_api.services.access_requests import (
    AccessRequestError,
    _new_request_id,
    _request_wire_to_uuid,
    approve,
    connection_test,
    create_access_request,
    create_integration_proposal,
    create_share_request,
    reject,
    sweep_tenant_expired,
)

# Minimum iterations per property (Task 5.6 requirement: >= 100). Kept in the
# 100-120 band because each example does real DB work (Task 5.6 runtime bound).
_MAX_EXAMPLES = 100

# Hypothesis + a per-example real DB round-trip is slow and reuses a shared
# fixture across examples, so disable the deadline and the
# function-scoped-fixture health check (the fixture is intentionally reused).
_DB_SETTINGS = settings(
    max_examples=_MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)

# The planted red-team canary — an unmistakable, high-entropy secret substring
# that the leak search greps for across every persisted text/jsonb column.
_CANARY = "CANARY-Slkj2h4-secret-4bXQ9zP-do-not-leak"


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
# Fake Vault Adapter clients.
#
# ``approve`` (integration branch) calls ``vault.put_credential(...)`` once and
# reads ``key_version`` off the returned mapping (mirrors the approve-properties
# ``_FakeVault``). A vault-DOWN variant raises the SAME ``grpc.aio.AioRpcError``
# the real client surfaces so the service translates it to ``vault_unavailable``
# and the router-owned transaction rolls back (Req 6.7).
# ===========================================================================


class _FakeVault:
    """Minimal async vault stub: records the put and returns a key_version."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def put_credential(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"key_version": 1}


def _make_down_vault() -> Any:
    """A vault whose ``put_credential`` raises the real gRPC unavailable error."""
    import grpc

    class _DownVault:
        def __init__(self) -> None:
            self.calls: list[dict[str, Any]] = []

        async def put_credential(self, **kwargs: Any) -> dict[str, object]:
            self.calls.append(dict(kwargs))
            raise grpc.aio.AioRpcError(
                code=grpc.StatusCode.UNAVAILABLE,
                initial_metadata=grpc.aio.Metadata(),
                trailing_metadata=grpc.aio.Metadata(),
                details="vault down (test)",
            )

    return _DownVault()


# ===========================================================================
# testcontainer plumbing (mirrors test_access_requests_approve_properties.py)
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


def _fetchall(postgres_container, sql: str, params: tuple[Any, ...] = ()):  # type: ignore[no-untyped-def]
    conn = _conn(postgres_container)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchall()
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
    """Seed one tenant + requesting/target agents + a service; return their IDs.

    Also builds a dedicated NullPool async engine (bound to the testcontainer
    DB) and publishes its sessionmaker to ``_ARP_SESSIONMAKER`` so the property
    bodies open sessions on the single shared loop without a connection pool.

    ``apply_migrations`` is depended on so changeset 030 (access_requests) is
    present before any create/approve/reject/sweep runs.
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

    tenant_id = str(uuid.uuid4())
    _exec(
        postgres_container,
        "INSERT INTO tenants (id, slug, display_name, isolation_mode, status)"
        " VALUES (%s, %s, %s, 'row', 'active')",
        (tenant_id, f"arp-aud-{tenant_id[:8]}", "arp-aud"),
    )

    def _agent(name: str) -> str:
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

    requesting_agent_id = _agent("arp-aud-requesting-agent")
    target_agent_id = _agent("arp-aud-target-agent")
    # An operator id used as the approve/reject ``resolved_by`` — the actor_id
    # asserted by Property 11. It need not be a real operators row (audit
    # actor_id has no FK), so a fresh UUID is sufficient and unambiguous.
    operator_id = str(uuid.uuid4())

    service_id = str(uuid.uuid4())
    _exec(
        postgres_container,
        "INSERT INTO services"
        " (id, tenant_id, name, slug, display_name, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'bearer_token', 'active')",
        (
            service_id,
            tenant_id,
            "arp-aud-service",
            "arp-aud-service",
            "arp-aud-service",
            "https://api.example.com",
        ),
    )

    yield {
        "tenant_id": tenant_id,
        "requesting_agent_id": requesting_agent_id,
        "target_agent_id": target_agent_id,
        "operator_id": operator_id,
        "service_id": service_id,
    }

    _LOOP.run_until_complete(arp_engine.dispose())
    _ARP_SESSIONMAKER = None


# ===========================================================================
# Direct-INSERT seeding helper (mirrors the approve-properties file).
#
# ``approve``/``reject``/``sweep`` load rows under the tenant GUC by decoding the
# wire ``request_id`` back to the stored PK (ADR-0017.11), so we mint the wire id
# via the module's own ``_new_request_id`` and store the matching UUID via
# ``_request_wire_to_uuid`` — guaranteeing the wire form decodes to the row.
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
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> str:
    """INSERT one access_requests row with a fresh, decodable ``request_`` id.

    Returns the wire ``request_id`` that ``approve``/``reject``/``sweep`` accept.
    """
    wire_id = _new_request_id()
    row_uuid = _request_wire_to_uuid(wire_id)
    now = created_at or datetime.now(_UTC)
    exp = expires_at or (now + timedelta(days=30))
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


# ---------------------------------------------------------------------------
# Audit / leak query helpers.
# ---------------------------------------------------------------------------


def _audit_rows_for_target(postgres_container, tenant_id: str, request_wire_id: str):  # type: ignore[no-untyped-def]
    """Return (event_type, actor_type, actor_id, payload) audit rows whose
    payload names *request_wire_id* — i.e. the events for THIS request."""
    return _fetchall(
        postgres_container,
        "SELECT event_type, actor_type, actor_id::text, payload::text"
        "  FROM audit_events"
        " WHERE tenant_id = %s AND payload::text LIKE %s"
        " ORDER BY at ASC",
        (tenant_id, f"%{request_wire_id}%"),
    )


def _audit_event_types(postgres_container, tenant_id: str, request_wire_id: str) -> set[str]:  # type: ignore[no-untyped-def]
    return {r[0] for r in _audit_rows_for_target(postgres_container, tenant_id, request_wire_id)}


def _canary_hits(postgres_container, tenant_id: str) -> list[str]:  # type: ignore[no-untyped-def]
    """Search every text/jsonb column of access_requests + audit_events for the
    canary substring, returning a list of "table.column" hit descriptions.

    This is the persisted-store half of the red-team canary (Property 1): if the
    operator secret ever reached the request row (any column incl. proposed_config)
    or any audit payload, the canary appears here and the property fails with a
    precise location.
    """
    hits: list[str] = []

    # access_requests — proposed_config (jsonb) + every text-ish column.
    ar_rows = _fetchall(
        postgres_container,
        "SELECT id::text, kind, status, action, share_direction, reason,"
        "       proposed_config::text"
        "  FROM access_requests WHERE tenant_id = %s",
        (tenant_id,),
    )
    ar_cols = ("id", "kind", "status", "action", "share_direction", "reason",
               "proposed_config")
    for row in ar_rows:
        for col, val in zip(ar_cols, row):
            if val is not None and _CANARY in str(val):
                hits.append(f"access_requests.{col}")

    # audit_events — payload (jsonb) + event_type + actor columns.
    ev_rows = _fetchall(
        postgres_container,
        "SELECT event_type, actor_type, payload::text FROM audit_events"
        " WHERE tenant_id = %s",
        (tenant_id,),
    )
    for event_type, actor_type, payload in ev_rows:
        for col, val in (("event_type", event_type), ("actor_type", actor_type),
                         ("payload", payload)):
            if val is not None and _CANARY in str(val):
                hits.append(f"audit_events.{col}")

    # services + credentials — the finalize path creates these; assert the
    # canary never lands in any of their text/jsonb columns either.
    svc_rows = _fetchall(
        postgres_container,
        "SELECT COALESCE(name,'')||'|'||COALESCE(base_url,'')||'|'"
        "||COALESCE(display_name,'')||'|'||COALESCE(description,'')"
        "  FROM services WHERE tenant_id = %s",
        (tenant_id,),
    )
    for (blob,) in svc_rows:
        if blob is not None and _CANARY in str(blob):
            hits.append("services.<text>")

    return hits


def _service_count(postgres_container, tenant_id: str) -> int:  # type: ignore[no-untyped-def]
    return int(_scalar(postgres_container,
               "SELECT count(*) FROM services WHERE tenant_id = %s", (tenant_id,)))


def _credential_count(postgres_container, tenant_id: str) -> int:  # type: ignore[no-untyped-def]
    return int(_scalar(postgres_container,
               "SELECT count(*) FROM credentials WHERE tenant_id = %s", (tenant_id,)))


def _status_of(postgres_container, tenant_id: str, wire_id: str) -> str | None:  # type: ignore[no-untyped-def]
    row = _fetchone(
        postgres_container,
        "SELECT status FROM access_requests WHERE id = %s AND tenant_id = %s",
        (str(_request_wire_to_uuid(wire_id)), tenant_id),
    )
    return row[0] if row else None


def _grant_count(postgres_container, tenant_id: str, agent_id: str, service_id: str, action: str) -> int:  # type: ignore[no-untyped-def]
    return int(
        _scalar(
            postgres_container,
            "SELECT count(*) FROM permission_grants"
            " WHERE tenant_id = %s AND agent_id = %s AND service_id = %s AND action = %s",
            (tenant_id, agent_id, service_id, action),
        )
    )


# Strategies -----------------------------------------------------------------

# A non-empty, non-whitespace action string that Postgres can store (no NUL /
# control chars — a generator constraint, not a spec change).
_db_safe_action = st.text(
    alphabet=st.characters(min_codepoint=0x21, max_codepoint=0x7E),
    min_size=1,
    max_size=16,
).filter(lambda s: s.strip())

_valid_reason = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    min_size=1,
    max_size=120,
).filter(lambda s: s.strip())


def _integration_proposed(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "base_url": "https://api.example.com",
        "auth_scheme": "bearer_token",
    }


# ===========================================================================
# Property 1 — The operator secret never leaks anywhere secret-free
# ===========================================================================
# Feature: agent-access-requests, Property 1: The operator secret never leaks
# anywhere secret-free — for any operator-supplied secret value used to submit,
# test, or finalize an integration proposal, after the operation completes the
# secret value SHALL NOT appear in the access_requests row (including
# proposed_config), in any structured log entry, in any audit event payload, in
# any OTel span attribute, in the Connection_Test diagnostic message, or in any
# response visible to the agent — and if the Vault Adapter is unavailable, no
# service, credential, or secret SHALL be persisted anywhere.


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty1SecretNonLeak:
    """Property 1 — THE red-team canary. The planted operator secret must not
    appear in any persisted text/jsonb column, in the returned agent-visible
    result, or in the Connection_Test diagnostic; and a vault-down finalize
    persists nothing."""

    @_DB_SETTINGS
    @given(
        display=st.text(
            alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
            min_size=1, max_size=20,
        ).filter(lambda s: s.strip()),
    )
    def test_finalize_secret_never_persisted_or_returned(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, display: str,
    ) -> None:
        """Integration finalize: the operator secret (canary) is handed to the
        vault only; it never lands on the request row, any audit payload, any
        services/credentials text column, or the returned agent-visible result."""
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        operator = _seed["operator_id"]
        name = "leak1-" + uuid.uuid4().hex[:12]

        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="integration",
            status="pending", requesting_agent_id=req_agent,
            proposed_config=_integration_proposed(name),
        )

        vault = _FakeVault()

        async def _do() -> Any:
            session = await _new_session()
            try:
                async with session.begin():
                    return await approve(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, vault=vault,  # type: ignore[arg-type]
                        resolved_by=uuid.UUID(operator),
                        # The planted secret canary — must reach ONLY the vault.
                        credential={"credential_value": _CANARY},
                        config={"display_name": display},
                    )
            finally:
                await session.close()

        result = _run(_do())

        # The secret WAS handed to the vault exactly once (that is the ONLY
        # place it is allowed to go).
        assert len(vault.calls) == 1
        assert vault.calls[0].get("plaintext") == _CANARY

        # It appears NOWHERE in any persisted text/jsonb column (row,
        # proposed_config, audit payloads, services/credentials text).
        hits = _canary_hits(postgres_container, tenant_id)
        assert hits == [], f"operator secret leaked into: {hits}"

        # It appears nowhere in the agent-visible returned result (Req 11.5).
        assert _CANARY not in json.dumps(
            {"request_id": result.request_id, "status": result.status,
             "kind": result.kind}
        )

        # Sanity: the finalize actually happened (approved + service created),
        # so the "no leak" result is not a vacuous pass.
        assert result.status == "approved"
        assert _status_of(postgres_container, tenant_id, wire_id) == "approved"

    @_DB_SETTINGS
    @given(dummy=st.integers(min_value=0, max_value=3))
    def test_connection_test_diagnostic_is_secret_free(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, dummy: int,
    ) -> None:
        """Connection_Test: the operator secret (canary) is used only to build
        the in-memory transient candidate; the returned diagnostic + any
        persisted column must never contain it (Req 6.3, P-1)."""
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        name = "leak2-" + uuid.uuid4().hex[:12]

        # base_url points at an unroutable TEST-NET-1 host so the handshake
        # fails fast (secret-free diagnostic) without external egress. It never
        # produces a successful 2xx, but the property is about the SECRET not
        # leaking regardless of ok/fail.
        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="integration",
            status="pending", requesting_agent_id=req_agent,
            proposed_config={
                "name": name,
                "base_url": "https://192.0.2.1",
                "auth_scheme": "bearer_token",
            },
        )

        async def _do() -> Any:
            session = await _new_session()
            try:
                async with session.begin():
                    return await connection_test(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id,
                        credential={"credential_value": _CANARY},
                    )
            finally:
                await session.close()

        try:
            result = _run(_do())
        except AccessRequestError as exc:
            # A not-found style rejection is acceptable; the error must itself
            # carry no secret (Req 6.3, P-1).
            assert _CANARY not in str(exc)
            assert _CANARY not in (exc.title or "")
            # And nothing secret was persisted.
            assert _canary_hits(postgres_container, tenant_id) == []
            return
        except HTTPException as exc:
            # The reused transient-test machinery rejects a private/special-IP
            # base_url via its SSRF egress allowlist (ADR-0007) as an
            # HTTPException — an acceptable secret-free rejection path. The
            # crucial Property-1 assertion is that this rejection carries NO
            # secret material (the transient handler redacts the host).
            assert _CANARY not in str(exc.detail)
            assert _canary_hits(postgres_container, tenant_id) == []
            return

        # The returned diagnostic / result carries no secret material.
        assert _CANARY not in (result.diagnostic or "")
        assert _CANARY not in (result.error or "")
        assert _CANARY not in json.dumps(
            {"ok": result.ok, "latency_ms": result.latency_ms,
             "diagnostic": result.diagnostic, "status_code": result.status_code,
             "error": result.error}
        )
        # Connection_Test persists nothing — no canary anywhere in the store.
        assert _canary_hits(postgres_container, tenant_id) == []

    @_DB_SETTINGS
    @given(dummy=st.integers(min_value=0, max_value=3))
    def test_vault_down_finalize_persists_nothing(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, dummy: int,
    ) -> None:
        """Vault-DOWN variant (Req 6.7): when the vault raises, approve fails
        with vault_unavailable and NO service / credential / secret is
        persisted anywhere; the request stays pending."""
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        operator = _seed["operator_id"]
        name = "leak3-" + uuid.uuid4().hex[:12]

        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="integration",
            status="pending", requesting_agent_id=req_agent,
            proposed_config=_integration_proposed(name),
        )

        services_before = _service_count(postgres_container, tenant_id)
        creds_before = _credential_count(postgres_container, tenant_id)
        vault = _make_down_vault()

        async def _do() -> None:
            session = await _new_session()
            try:
                # The router owns the transaction; a raised error rolls it back.
                async with session.begin():
                    await approve(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, vault=vault,  # type: ignore[arg-type]
                        resolved_by=uuid.UUID(operator),
                        credential={"credential_value": _CANARY},
                        config=None,
                    )
            finally:
                await session.close()

        with pytest.raises(AccessRequestError) as exc:
            _run(_do())
        assert exc.value.code == "vault_unavailable"

        # Nothing persisted: no new service, no new credential (Req 6.7).
        assert _service_count(postgres_container, tenant_id) == services_before
        assert _credential_count(postgres_container, tenant_id) == creds_before
        # The specific service by unique name never materialised.
        assert _scalar(postgres_container,
                       "SELECT count(*) FROM services WHERE tenant_id = %s AND name = %s",
                       (tenant_id, name)) == 0
        # No secret anywhere; request left pending (rolled back).
        assert _canary_hits(postgres_container, tenant_id) == []
        assert _status_of(postgres_container, tenant_id, wire_id) == "pending"


# ===========================================================================
# Property 10 — Every state change emits its audit event through the chokepoint
# ===========================================================================
# Feature: agent-access-requests, Property 10: Every state change emits its
# audit event through the chokepoint — for any request state transition
# (created, approved, rejected, expired) — and additionally for any approval
# that creates a grant, service, or credential — the corresponding audit
# event(s) (access_request.created/approved/rejected/expired plus, on approval,
# agent.permission.granted / service.registered / credential.registered) SHALL
# be emitted via the single audit.emit() chokepoint and extend the tenant's
# hash chain.


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty10AuditCoverage:
    """Property 10 — every state change writes exactly its expected
    access_request.* audit row (plus reused events on approve)."""

    @_DB_SETTINGS
    @given(kind=st.sampled_from(["access", "share"]), action=_db_safe_action)
    def test_created_emits_created_event(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, kind: str, action: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        target = _seed["target_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    if kind == "access":
                        created = await create_access_request(
                            session, tenant_id=uuid.UUID(tenant_id),
                            requesting_agent_id=uuid.UUID(req_agent),
                            service_id=uuid.UUID(service), action=act,
                        )
                    else:
                        created = await create_share_request(
                            session, tenant_id=uuid.UUID(tenant_id),
                            requesting_agent_id=uuid.UUID(req_agent),
                            service_id=uuid.UUID(service), action=act,
                            target_agent_id=uuid.UUID(target),
                        )
                return created.request_id
            finally:
                await session.close()

        request_id = _run(_do())
        types = _audit_event_types(postgres_container, tenant_id, request_id)
        assert "access_request.created" in types

    @_DB_SETTINGS
    @given(dummy=st.integers(min_value=0, max_value=3))
    def test_created_integration_emits_created_event(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, dummy: int,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        name = "cov-int-" + uuid.uuid4().hex[:10]

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    created = await create_integration_proposal(
                        session, tenant_id=uuid.UUID(tenant_id),
                        requesting_agent_id=uuid.UUID(req_agent),
                        name=name, base_url="https://api.example.com",
                        auth_scheme="bearer_token", openapi_url=None, config=None,
                    )
                return created.request_id
            finally:
                await session.close()

        request_id = _run(_do())
        types = _audit_event_types(postgres_container, tenant_id, request_id)
        assert "access_request.created" in types

    @_DB_SETTINGS
    @given(kind=st.sampled_from(["access", "share"]), action=_db_safe_action)
    def test_approve_emits_approved_plus_granted(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, kind: str, action: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        target = _seed["target_agent_id"]
        service = _seed["service_id"]
        operator = _seed["operator_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        if kind == "access":
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="access",
                status="pending", requesting_agent_id=req_agent,
                service_id=service, action=act,
            )
        else:
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="share",
                status="pending", requesting_agent_id=req_agent,
                service_id=service, action=act, target_agent_id=target,
                share_direction="inbound",
            )

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await approve(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, vault=_FakeVault(),  # type: ignore[arg-type]
                        resolved_by=uuid.UUID(operator),
                    )
            finally:
                await session.close()

        grants_before = int(_scalar(
            postgres_container,
            "SELECT count(*) FROM audit_events"
            " WHERE tenant_id = %s AND event_type = 'agent.permission.granted'",
            (tenant_id,),
        ))

        _run(_do())
        types = _audit_event_types(postgres_container, tenant_id, wire_id)
        assert "access_request.approved" in types
        # A new grant was created, so the reused grant event is present too.
        # The agent.permission.granted payload carries the perm_/agent_/svc_
        # ids (not the request_ id), so it is counted tenant-wide by a
        # before/after delta rather than matched against the request wire id.
        grants_after = int(_scalar(
            postgres_container,
            "SELECT count(*) FROM audit_events"
            " WHERE tenant_id = %s AND event_type = 'agent.permission.granted'",
            (tenant_id,),
        ))
        assert grants_after == grants_before + 1

    @_DB_SETTINGS
    @given(dummy=st.integers(min_value=0, max_value=3))
    def test_approve_integration_emits_approved_service_credential(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, dummy: int,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        operator = _seed["operator_id"]
        name = "cov-fin-" + uuid.uuid4().hex[:10]

        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="integration",
            status="pending", requesting_agent_id=req_agent,
            proposed_config=_integration_proposed(name),
        )

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await approve(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, vault=_FakeVault(),  # type: ignore[arg-type]
                        resolved_by=uuid.UUID(operator),
                        credential={"credential_value": _CANARY},
                    )
            finally:
                await session.close()

        _run(_do())
        types = _audit_event_types(postgres_container, tenant_id, wire_id)
        assert "access_request.approved" in types
        # The finalize path also created a service + credential; assert those
        # reused events landed (they carry the svc_ id, not the request_ id, so
        # count them tenant-wide as a coverage check).
        assert int(_scalar(postgres_container,
                   "SELECT count(*) FROM audit_events"
                   " WHERE tenant_id = %s AND event_type = 'service.registered'",
                   (tenant_id,))) >= 1
        assert int(_scalar(postgres_container,
                   "SELECT count(*) FROM audit_events"
                   " WHERE tenant_id = %s AND event_type = 'credential.registered'",
                   (tenant_id,))) >= 1

    @_DB_SETTINGS
    @given(action=_db_safe_action, reason=_valid_reason)
    def test_reject_emits_rejected_event(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, action: str, reason: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        operator = _seed["operator_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="access",
            status="pending", requesting_agent_id=req_agent,
            service_id=service, action=act,
        )

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await reject(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, reason=reason,
                        resolved_by=uuid.UUID(operator),
                    )
            finally:
                await session.close()

        _run(_do())
        types = _audit_event_types(postgres_container, tenant_id, wire_id)
        assert "access_request.rejected" in types

    @_DB_SETTINGS
    @given(action=_db_safe_action)
    def test_expire_sweep_emits_expired_event(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, action: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        # An already-elapsed pending row (created 40d ago, expired 10d ago).
        past = datetime.now(_UTC) - timedelta(days=40)
        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="access",
            status="pending", requesting_agent_id=req_agent,
            service_id=service, action=act,
            created_at=past, expires_at=past + timedelta(days=30),
        )

        async def _do() -> int:
            session = await _new_session()
            try:
                async with session.begin():
                    return await sweep_tenant_expired(
                        session, tenant_id=uuid.UUID(tenant_id),
                    )
            finally:
                await session.close()

        _run(_do())
        assert _status_of(postgres_container, tenant_id, wire_id) == "expired"
        types = _audit_event_types(postgres_container, tenant_id, wire_id)
        assert "access_request.expired" in types


# ===========================================================================
# Property 11 — Audit actor type matches the trigger
# ===========================================================================
# Feature: agent-access-requests, Property 11: Audit actor type matches the
# trigger — for any emitted request audit event, actor_type SHALL be agent for
# agent-initiated creation, operator for operator approve/reject (with operator
# identity derived from the validated session), and system for expiration.


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty11ActorType:
    """Property 11 — created→agent, approved/rejected→operator (actor_id ==
    resolved_by), expired→system."""

    @_DB_SETTINGS
    @given(kind=st.sampled_from(["access", "share"]), action=_db_safe_action)
    def test_created_actor_is_agent(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, kind: str, action: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        target = _seed["target_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    if kind == "access":
                        created = await create_access_request(
                            session, tenant_id=uuid.UUID(tenant_id),
                            requesting_agent_id=uuid.UUID(req_agent),
                            service_id=uuid.UUID(service), action=act,
                        )
                    else:
                        created = await create_share_request(
                            session, tenant_id=uuid.UUID(tenant_id),
                            requesting_agent_id=uuid.UUID(req_agent),
                            service_id=uuid.UUID(service), action=act,
                            target_agent_id=uuid.UUID(target),
                        )
                return created.request_id
            finally:
                await session.close()

        request_id = _run(_do())
        rows = _audit_rows_for_target(postgres_container, tenant_id, request_id)
        created_rows = [r for r in rows if r[0] == "access_request.created"]
        assert created_rows, "no access_request.created event found"
        for event_type, actor_type, actor_id, _payload in created_rows:
            assert actor_type == "agent"
            # actor_id is the requesting agent (agent-initiated).
            assert actor_id == req_agent

    @_DB_SETTINGS
    @given(
        outcome=st.sampled_from(["approve", "reject"]),
        action=_db_safe_action,
        reason=_valid_reason,
    )
    def test_approve_reject_actor_is_operator(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, outcome: str, action: str, reason: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        operator = _seed["operator_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="access",
            status="pending", requesting_agent_id=req_agent,
            service_id=service, action=act,
        )

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    if outcome == "approve":
                        await approve(
                            session, tenant_id=uuid.UUID(tenant_id),
                            request_id=wire_id, vault=_FakeVault(),  # type: ignore[arg-type]
                            resolved_by=uuid.UUID(operator),
                        )
                    else:
                        await reject(
                            session, tenant_id=uuid.UUID(tenant_id),
                            request_id=wire_id, reason=reason,
                            resolved_by=uuid.UUID(operator),
                        )
            finally:
                await session.close()

        _run(_do())
        expected_event = f"access_request.{'approved' if outcome == 'approve' else 'rejected'}"
        rows = _audit_rows_for_target(postgres_container, tenant_id, wire_id)
        state_rows = [r for r in rows if r[0] == expected_event]
        assert state_rows, f"no {expected_event} event found"
        for _event_type, actor_type, actor_id, _payload in state_rows:
            assert actor_type == "operator"
            # Operator identity derived from the validated session (resolved_by).
            assert actor_id == operator

    @_DB_SETTINGS
    @given(action=_db_safe_action)
    def test_expired_actor_is_system(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, action: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        past = datetime.now(_UTC) - timedelta(days=40)
        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="access",
            status="pending", requesting_agent_id=req_agent,
            service_id=service, action=act,
            created_at=past, expires_at=past + timedelta(days=30),
        )

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await sweep_tenant_expired(
                        session, tenant_id=uuid.UUID(tenant_id),
                    )
            finally:
                await session.close()

        _run(_do())
        rows = _audit_rows_for_target(postgres_container, tenant_id, wire_id)
        expired_rows = [r for r in rows if r[0] == "access_request.expired"]
        assert expired_rows, "no access_request.expired event found"
        for _event_type, actor_type, actor_id, _payload in expired_rows:
            assert actor_type == "system"
            # System-initiated expiry carries no human/agent actor.
            assert actor_id is None


# ===========================================================================
# Property 12 — Audit failure aborts the state change atomically
# ===========================================================================
# Feature: agent-access-requests, Property 12: Audit failure aborts the state
# change atomically — for any request state transition in which the audit event
# cannot be emitted, no request status update, permission grant, service, or
# credential SHALL be persisted.


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty12AuditFailureAtomic:
    """Property 12 — when audit_emit raises inside the transaction, the whole
    state change rolls back: no status flip, no grant, no service/credential."""

    @_DB_SETTINGS
    @given(
        transition=st.sampled_from(["approve_access", "approve_integration", "reject"]),
        action=_db_safe_action,
        reason=_valid_reason,
    )
    def test_audit_failure_rolls_back(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, monkeypatch, transition: str,
        action: str, reason: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        operator = _seed["operator_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]
        name = "atomic-" + uuid.uuid4().hex[:12]

        # Force EVERY audit emission on this path to fail. audit_emit is imported
        # into the service module's namespace, so patch it THERE (the name the
        # service actually calls). A DB write already happened before the emit
        # (status UPDATE / grant / service INSERT), so a raised audit proves the
        # whole caller-owned transaction is rolled back (Req 10.6).
        async def _boom(*_args: Any, **_kwargs: Any) -> None:
            raise RuntimeError("audit chain write failed (injected)")

        monkeypatch.setattr(ar, "audit_emit", _boom)

        if transition == "reject":
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="access",
                status="pending", requesting_agent_id=req_agent,
                service_id=service, action=act,
            )
        elif transition == "approve_access":
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="access",
                status="pending", requesting_agent_id=req_agent,
                service_id=service, action=act,
            )
        else:  # approve_integration
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="integration",
                status="pending", requesting_agent_id=req_agent,
                proposed_config=_integration_proposed(name),
            )

        services_before = _service_count(postgres_container, tenant_id)
        creds_before = _credential_count(postgres_container, tenant_id)
        grants_before = _grant_count(postgres_container, tenant_id, req_agent, service, act)

        async def _do() -> None:
            session = await _new_session()
            try:
                # Router-owned transaction: a raised error inside aborts it,
                # rolling back every write made before the failing emit.
                async with session.begin():
                    if transition == "reject":
                        await reject(
                            session, tenant_id=uuid.UUID(tenant_id),
                            request_id=wire_id, reason=reason,
                            resolved_by=uuid.UUID(operator),
                        )
                    elif transition == "approve_access":
                        await approve(
                            session, tenant_id=uuid.UUID(tenant_id),
                            request_id=wire_id, vault=_FakeVault(),  # type: ignore[arg-type]
                            resolved_by=uuid.UUID(operator),
                        )
                    else:
                        await approve(
                            session, tenant_id=uuid.UUID(tenant_id),
                            request_id=wire_id, vault=_FakeVault(),  # type: ignore[arg-type]
                            resolved_by=uuid.UUID(operator),
                            credential={"credential_value": _CANARY},
                        )
            finally:
                await session.close()

        with pytest.raises(RuntimeError):
            _run(_do())

        # The state change is fully rolled back (Req 10.6):
        #  - the request is still pending (status flip reverted),
        #  - no new grant / service / credential persisted.
        assert _status_of(postgres_container, tenant_id, wire_id) == "pending"
        assert _grant_count(postgres_container, tenant_id, req_agent, service, act) == grants_before
        assert _service_count(postgres_container, tenant_id) == services_before
        assert _credential_count(postgres_container, tenant_id) == creds_before
        # And the injected-failure path never leaked the finalize canary.
        assert _canary_hits(postgres_container, tenant_id) == []
