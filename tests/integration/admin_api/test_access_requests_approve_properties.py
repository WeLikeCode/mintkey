"""
Property-based tests (Hypothesis) for the agent-access-requests APPROVE / REJECT
state machine, grant outcomes, terminal artifacts, and config-edit override.

Feature: agent-access-requests — Task 5.2.

Exercises ``approve`` and ``reject`` in
``admin_api.services.access_requests`` against a REAL Postgres 16 testcontainer
with the real Liquibase changelogs applied (changeset 030 present):

  - ``approve``  (branches by kind: access / share / integration finalize)
  - ``reject``

Properties (statements copied verbatim from
``.kiro/specs/agent-access-requests/design.md`` §Correctness Properties):

  - Property 3 — Approve and reject are legal only from ``pending``
                 (Validates: Requirements 5.6, 7.4, 9.5)
  - Property 4 — Terminal requests produce no side artifacts
                 (Validates: Requirements 8.3, 9.4)
  - Property 5 — Approving a pending grant-request yields exactly the requested
                 grant (Validates: Requirements 5.1, 7.1)
  - Property 6 — Approval is idempotent when the grant already exists
                 (Validates: Requirements 7.5)
  - Property 8 — Operator config edits override agent-proposed values
                 (Validates: Requirements 6.2)

Testing approach (mirrors ``test_access_requests_create_properties.py``):
  - Each property runs a MINIMUM of 100 Hypothesis iterations
    (``@settings(max_examples=...)`` with ``>= 100``).
  - This is an ADD-ONLY file. It modifies neither the service code nor any
    existing test (Req 14.2).
  - The DB-backed assertions run against a REAL Postgres 16 testcontainer with
    the real changelogs applied (changeset 030 + seeds). This reuses the
    session-scoped ``postgres_container`` / ``apply_migrations`` / ``admin_app``
    fixtures in this directory's ``conftest.py`` (AGENTS.md Principle 1 — never
    assert a column exists without introspecting it against the real schema).
    If Docker / testcontainers / psycopg2 is unavailable, the tests skip
    gracefully (matching the repo's skip conventions).
  - The SAME module-loop + NullPool ``_ARP_SESSIONMAKER`` + ``_seed`` fixture
    pattern as the create-properties test is used so pooled asyncpg connections
    never outlive their loop.
  - ``approve``/``reject`` require only a wire ``request_id`` and (for an
    integration finalize) a fake ``vault`` exposing an async ``put_credential``.
    The grant/share approve paths (Property 5/6) and the state-machine /
    terminal-artifact paths (Property 3/4) need no real vault; only the
    Property 8 integration-finalize path drives a fake vault.

Source: .kiro/specs/agent-access-requests/design.md §Correctness Properties,
        §Testing Strategy; requirements.md Req 5.1, 5.6, 6.2, 7.1, 7.4, 7.5,
        8.3, 9.4, 9.5; ADR-0008, ADR-0017.11, ADR-0019.
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
    reject,
)

# Minimum iterations per property (Task 5.2 requirement: >= 100). Kept in the
# 100-120 band because each example does real DB work (Task 5.2 runtime bound).
_MAX_EXAMPLES = 110

# Hypothesis + a per-example real DB round-trip is slow and reuses a shared
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
# connection alive between calls.
_LOOP = asyncio.new_event_loop()


def _run(coro: Any) -> Any:
    """Drive an async coroutine to completion on the shared module loop."""
    return _LOOP.run_until_complete(coro)


# ===========================================================================
# Fake Vault Adapter client — for the integration-finalize path (Property 8).
#
# ``approve`` (integration branch) calls ``vault.put_credential(...)`` exactly
# once and reads ``key_version`` off the returned mapping. A real vault is NOT
# needed to verify the config-edit override (Property 8) or any grant/share
# path (Property 5/6) — a fake that succeeds and returns a key_version is
# sufficient and keeps the secret out of the DB exactly like the real path.
# ===========================================================================


class _FakeVault:
    """Minimal async vault stub: records the put and returns a key_version."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    async def put_credential(self, **kwargs: Any) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {"key_version": 1}


# ===========================================================================
# testcontainer plumbing (mirrors test_access_requests_create_properties.py)
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
    """Seed one tenant + requesting/target agents + a service; return their IDs.

    Also builds a dedicated NullPool async engine (bound to the testcontainer
    DB) and publishes its sessionmaker to ``_ARP_SESSIONMAKER`` so the property
    bodies open sessions on the single shared loop without a connection pool.

    ``apply_migrations`` is depended on so changeset 030 (access_requests) is
    present before any approve/reject runs.
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
        (tenant_id, f"arp-appr-{tenant_id[:8]}", "arp-appr"),
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

    requesting_agent_id = _agent("arp-appr-requesting-agent")
    target_agent_id = _agent("arp-appr-target-agent")

    service_id = str(uuid.uuid4())
    _exec(
        postgres_container,
        "INSERT INTO services"
        " (id, tenant_id, name, slug, display_name, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'bearer_token', 'active')",
        (
            service_id,
            tenant_id,
            "arp-appr-service",
            "arp-appr-service",
            "arp-appr-service",
            "https://api.example.com",
        ),
    )

    yield {
        "tenant_id": tenant_id,
        "requesting_agent_id": requesting_agent_id,
        "target_agent_id": target_agent_id,
        "service_id": service_id,
    }

    _LOOP.run_until_complete(arp_engine.dispose())
    _ARP_SESSIONMAKER = None


# ===========================================================================
# Direct-INSERT seeding helpers.
#
# ``approve``/``reject`` load the row under the tenant GUC by decoding the wire
# ``request_id`` back to the stored PK (ADR-0017.11), so we mint the wire id via
# the module's own ``_new_request_id`` and store the matching UUID via
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

    Returns the wire ``request_id`` that ``approve``/``reject`` will accept.
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


def _grant_count(postgres_container, tenant_id: str, agent_id: str, service_id: str, action: str) -> int:  # type: ignore[no-untyped-def]
    return int(
        _scalar(
            postgres_container,
            "SELECT count(*) FROM permission_grants"
            " WHERE tenant_id = %s AND agent_id = %s AND service_id = %s AND action = %s",
            (tenant_id, agent_id, service_id, action),
        )
    )


def _row_status_reason(postgres_container, tenant_id: str, wire_id: str):  # type: ignore[no-untyped-def]
    row_uuid = _request_wire_to_uuid(wire_id)
    return _fetchone(
        postgres_container,
        "SELECT status, reason FROM access_requests WHERE id = %s AND tenant_id = %s",
        (str(row_uuid), tenant_id),
    )


# Strategies -----------------------------------------------------------------

# A non-empty, non-whitespace action string that Postgres can store (no NUL /
# control chars — a generator constraint, not a spec change; Postgres rejects
# 0x00 in any text column).
_db_safe_action = st.text(
    alphabet=st.characters(min_codepoint=0x21, max_codepoint=0x7E),
    min_size=1,
    max_size=16,
).filter(lambda s: s.strip())

# The non-pending terminal/other statuses guarded against by Property 3.
_non_pending_status = st.sampled_from(["approved", "rejected", "expired", "cancelled"])

# The two terminal statuses relevant to Property 4.
_terminal_status = st.sampled_from(["rejected", "expired"])

# A valid, non-empty, <=1000-char reject reason.
_valid_reason = st.text(
    alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
    min_size=1,
    max_size=200,
).filter(lambda s: s.strip())


# ===========================================================================
# Property 3 — Approve and reject are legal only from ``pending``
# ===========================================================================
# Feature: agent-access-requests, Property 3: Approve and reject are legal only
# from pending — for any request whose status is not pending (approved,
# rejected, expired, cancelled), an approve or reject action SHALL be rejected
# with request_not_pending, SHALL create no grant/service/credential, and SHALL
# leave the existing status and reason unchanged.


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty3StateMachineLegality:
    """Property 3 — approve/reject on a non-pending request → request_not_pending,
    nothing created, status + reason unchanged."""

    @_DB_SETTINGS
    @given(
        status=_non_pending_status,
        kind=st.sampled_from(["access", "share", "integration"]),
        action=_db_safe_action,
        preset_reason=st.one_of(st.none(), _valid_reason),
    )
    def test_approve_rejected_from_non_pending(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, status: str, kind: str, action: str,
        preset_reason: str | None,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        target = _seed["target_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]
        # reason is only meaningful on a 'rejected' row; keep it for the
        # unchanged-check regardless of status.
        reason = preset_reason if status == "rejected" else None

        if kind == "access":
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="access",
                status=status, requesting_agent_id=req_agent, service_id=service,
                action=act, reason=reason,
            )
            grant_agent = req_agent
        elif kind == "share":
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="share",
                status=status, requesting_agent_id=req_agent, service_id=service,
                action=act, target_agent_id=target, share_direction="inbound",
                reason=reason,
            )
            grant_agent = target
        else:  # integration
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="integration",
                status=status, requesting_agent_id=req_agent,
                proposed_config={"name": "n-" + uuid.uuid4().hex[:8],
                                 "base_url": "https://api.example.com",
                                 "auth_scheme": "bearer_token"},
                reason=reason,
            )
            grant_agent = None

        services_before = int(
            _scalar(postgres_container,
                    "SELECT count(*) FROM services WHERE tenant_id = %s", (tenant_id,))
        )
        creds_before = int(
            _scalar(postgres_container,
                    "SELECT count(*) FROM credentials WHERE tenant_id = %s", (tenant_id,))
        )
        grants_before = (
            _grant_count(postgres_container, tenant_id, grant_agent, service, act)
            if grant_agent is not None else 0
        )
        vault = _FakeVault()

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await approve(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, vault=vault,  # type: ignore[arg-type]
                        credential={"credential_value": "s3cr3t-canary"},
                        config=None,
                    )
            finally:
                await session.close()

        with pytest.raises(AccessRequestError) as exc:
            _run(_do())
        assert exc.value.code == "request_not_pending"

        # No vault write, no service/credential/grant created.
        assert vault.calls == []
        assert int(_scalar(postgres_container,
                   "SELECT count(*) FROM services WHERE tenant_id = %s",
                   (tenant_id,))) == services_before
        assert int(_scalar(postgres_container,
                   "SELECT count(*) FROM credentials WHERE tenant_id = %s",
                   (tenant_id,))) == creds_before
        if grant_agent is not None:
            assert _grant_count(postgres_container, tenant_id, grant_agent,
                                service, act) == grants_before

        # status + reason unchanged (Req 5.6/7.4/9.5).
        st_row = _row_status_reason(postgres_container, tenant_id, wire_id)
        assert st_row is not None
        assert st_row[0] == status
        assert st_row[1] == reason

    @_DB_SETTINGS
    @given(
        status=_non_pending_status,
        action=_db_safe_action,
        preset_reason=st.one_of(st.none(), _valid_reason),
        new_reason=_valid_reason,
    )
    def test_reject_rejected_from_non_pending(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, status: str, action: str,
        preset_reason: str | None, new_reason: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]
        reason = preset_reason if status == "rejected" else None

        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="access",
            status=status, requesting_agent_id=req_agent, service_id=service,
            action=act, reason=reason,
        )
        grants_before = _grant_count(postgres_container, tenant_id, req_agent, service, act)

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await reject(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, reason=new_reason,
                    )
            finally:
                await session.close()

        with pytest.raises(AccessRequestError) as exc:
            _run(_do())
        assert exc.value.code == "request_not_pending"

        # No grant created; status + reason unchanged (not overwritten by new_reason).
        assert _grant_count(postgres_container, tenant_id, req_agent, service, act) == grants_before
        st_row = _row_status_reason(postgres_container, tenant_id, wire_id)
        assert st_row is not None
        assert st_row[0] == status
        assert st_row[1] == reason


# ===========================================================================
# Property 4 — Terminal requests produce no side artifacts
# ===========================================================================
# Feature: agent-access-requests, Property 4: Terminal requests produce no side
# artifacts — for any request that reaches rejected or expired, no permission
# grant, service, or credential SHALL exist as a result of that request.


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty4NoTerminalArtifacts:
    """Property 4 — a rejected/expired request yields no grant, service, or
    credential from that request (reject drives it; approve is then refused)."""

    @_DB_SETTINGS
    @given(
        kind=st.sampled_from(["access", "share"]),
        action=_db_safe_action,
        reason=_valid_reason,
    )
    def test_reject_creates_no_artifacts(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, kind: str, action: str, reason: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        target = _seed["target_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        if kind == "access":
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="access",
                status="pending", requesting_agent_id=req_agent,
                service_id=service, action=act,
            )
            grant_agent = req_agent
        else:
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="share",
                status="pending", requesting_agent_id=req_agent,
                service_id=service, action=act, target_agent_id=target,
                share_direction="inbound",
            )
            grant_agent = target

        services_before = int(
            _scalar(postgres_container,
                    "SELECT count(*) FROM services WHERE tenant_id = %s", (tenant_id,))
        )
        creds_before = int(
            _scalar(postgres_container,
                    "SELECT count(*) FROM credentials WHERE tenant_id = %s", (tenant_id,))
        )

        async def _do_reject() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await reject(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, reason=reason,
                    )
            finally:
                await session.close()

        _run(_do_reject())

        # Row is terminal (rejected); no grant/service/credential exists as a
        # result of this request (Req 8.3).
        st_row = _row_status_reason(postgres_container, tenant_id, wire_id)
        assert st_row is not None and st_row[0] == "rejected"
        assert _grant_count(postgres_container, tenant_id, grant_agent, service, act) == 0
        assert int(_scalar(postgres_container,
                   "SELECT count(*) FROM services WHERE tenant_id = %s",
                   (tenant_id,))) == services_before
        assert int(_scalar(postgres_container,
                   "SELECT count(*) FROM credentials WHERE tenant_id = %s",
                   (tenant_id,))) == creds_before

    @_DB_SETTINGS
    @given(
        status=_terminal_status,
        kind=st.sampled_from(["access", "share"]),
        action=_db_safe_action,
    )
    def test_terminal_row_stays_artifact_free_when_approve_attempted(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, status: str, kind: str, action: str,
    ) -> None:
        """A row already terminal (rejected/expired) cannot be approved into a
        grant — approve is refused, so still no side artifacts (Req 8.3, 9.4)."""
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        target = _seed["target_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        if kind == "access":
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="access",
                status=status, requesting_agent_id=req_agent,
                service_id=service, action=act,
                reason="r" if status == "rejected" else None,
            )
            grant_agent = req_agent
        else:
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="share",
                status=status, requesting_agent_id=req_agent,
                service_id=service, action=act, target_agent_id=target,
                share_direction="inbound",
                reason="r" if status == "rejected" else None,
            )
            grant_agent = target

        vault = _FakeVault()

        async def _do() -> None:
            session = await _new_session()
            try:
                async with session.begin():
                    await approve(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, vault=vault,  # type: ignore[arg-type]
                    )
            finally:
                await session.close()

        with pytest.raises(AccessRequestError) as exc:
            _run(_do())
        assert exc.value.code == "request_not_pending"
        assert _grant_count(postgres_container, tenant_id, grant_agent, service, act) == 0


# ===========================================================================
# Property 5 — Approving a pending grant-request yields exactly the requested grant
# ===========================================================================
# Feature: agent-access-requests, Property 5: Approving a pending grant-request
# yields exactly the requested grant — for any pending access request
# (requesting_agent, service, action), approval SHALL create exactly one
# permission grant for (requesting_agent, service, action) and set the request
# status to approved; and for any pending outbound/inbound share request
# (target_agent, service, action), approval SHALL create exactly one permission
# grant for (target_agent, service, action) and set status to approved.


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty5ApproveYieldsExactGrant:
    """Property 5 — approving a pending access/share request creates exactly one
    grant for the correct agent and marks the request approved."""

    @_DB_SETTINGS
    @given(
        kind=st.sampled_from(["access", "share"]),
        direction=st.sampled_from(["inbound", "outbound"]),
        action=_db_safe_action,
    )
    def test_approve_creates_exactly_one_grant(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, kind: str, direction: str, action: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        target = _seed["target_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        if kind == "access":
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="access",
                status="pending", requesting_agent_id=req_agent,
                service_id=service, action=act,
            )
            grant_agent = req_agent
        else:
            wire_id = _seed_request(
                postgres_container, tenant_id=tenant_id, kind="share",
                status="pending", requesting_agent_id=req_agent,
                service_id=service, action=act, target_agent_id=target,
                share_direction=direction,
            )
            grant_agent = target

        # No grant for the recipient before approval.
        assert _grant_count(postgres_container, tenant_id, grant_agent, service, act) == 0

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    result = await approve(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, vault=_FakeVault(),  # type: ignore[arg-type]
                    )
                return result.status
            finally:
                await session.close()

        status = _run(_do())
        assert status == "approved"

        # Exactly one grant for the RECIPIENT (requesting for access, target for
        # share) on (service, action); none for the other agent.
        assert _grant_count(postgres_container, tenant_id, grant_agent, service, act) == 1
        other = target if kind == "access" else req_agent
        assert _grant_count(postgres_container, tenant_id, other, service, act) == 0

        # Request is approved.
        st_row = _row_status_reason(postgres_container, tenant_id, wire_id)
        assert st_row is not None and st_row[0] == "approved"


# ===========================================================================
# Property 6 — Approval is idempotent when the grant already exists
# ===========================================================================
# Feature: agent-access-requests, Property 6: Approval is idempotent when the
# grant already exists — for any pending share request whose target grant
# (target_agent, service, action) already exists at approval time, approval
# SHALL set the request status to approved without creating a duplicate grant
# (exactly one grant remains).


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty6ApprovalIdempotent:
    """Property 6 — approving a share request whose target grant already exists
    marks it approved and leaves exactly one grant (no duplicate)."""

    @_DB_SETTINGS
    @given(direction=st.sampled_from(["inbound", "outbound"]), action=_db_safe_action)
    def test_approve_idempotent_existing_grant(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, direction: str, action: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        target = _seed["target_agent_id"]
        service = _seed["service_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        # Pre-existing grant for the TARGET on (service, act).
        _exec(
            postgres_container,
            "INSERT INTO permission_grants"
            " (id, tenant_id, agent_id, service_id, action, constraints, created_by)"
            " VALUES (%s, %s, %s, %s, %s, '{}', %s)",
            (str(uuid.uuid4()), tenant_id, target, service, act, req_agent),
        )
        assert _grant_count(postgres_container, tenant_id, target, service, act) == 1

        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="share",
            status="pending", requesting_agent_id=req_agent, service_id=service,
            action=act, target_agent_id=target, share_direction=direction,
        )

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    result = await approve(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, vault=_FakeVault(),  # type: ignore[arg-type]
                    )
                return result.status
            finally:
                await session.close()

        status = _run(_do())
        assert status == "approved"

        # Still exactly one grant — no duplicate (Req 7.5).
        assert _grant_count(postgres_container, tenant_id, target, service, act) == 1
        st_row = _row_status_reason(postgres_container, tenant_id, wire_id)
        assert st_row is not None and st_row[0] == "approved"


# ===========================================================================
# Property 8 — Operator config edits override agent-proposed values
# ===========================================================================
# Feature: agent-access-requests, Property 8: Operator config edits override
# agent-proposed values — for any integration proposal where the operator edits
# one or more non-secret config fields before finalizing, the created service
# SHALL reflect the operator's edited values in place of the agent-proposed
# values.


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty8ConfigEditOverride:
    """Property 8 — on integration finalize, operator-edited non-secret config
    values replace the agent-proposed values in the created service."""

    @_DB_SETTINGS
    @given(
        proposed_display=st.text(
            alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
            min_size=1, max_size=24,
        ).filter(lambda s: s.strip()),
        edited_display=st.text(
            alphabet=st.characters(min_codepoint=0x20, max_codepoint=0x7E),
            min_size=1, max_size=24,
        ).filter(lambda s: s.strip()),
        edited_base_url=st.sampled_from(
            [
                "https://edited-a.example.com",
                "https://edited-b.example.com",
                "https://edited-c.example.com/api",
            ]
        ),
    )
    def test_operator_edit_overrides_proposed(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, proposed_display: str,
        edited_display: str, edited_base_url: str,
    ) -> None:
        tenant_id = _seed["tenant_id"]
        req_agent = _seed["requesting_agent_id"]
        # Unique service name so the created row is unambiguously locatable.
        name = "prop8-" + uuid.uuid4().hex[:12]
        proposed_base_url = "https://agent-proposed.example.com"

        wire_id = _seed_request(
            postgres_container, tenant_id=tenant_id, kind="integration",
            status="pending", requesting_agent_id=req_agent,
            proposed_config={
                "name": name,
                "base_url": proposed_base_url,
                "auth_scheme": "bearer_token",
                "display_name": proposed_display,
            },
        )

        vault = _FakeVault()
        # Operator edits: change display_name and base_url (non-secret fields).
        operator_config = {
            "display_name": edited_display,
            "base_url": edited_base_url,
        }

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    result = await approve(
                        session, tenant_id=uuid.UUID(tenant_id),
                        request_id=wire_id, vault=vault,  # type: ignore[arg-type]
                        credential={"credential_value": "s3cr3t-canary"},
                        config=operator_config,
                    )
                return result.status
            finally:
                await session.close()

        status = _run(_do())
        assert status == "approved"

        # The created service reflects the OPERATOR-edited values, not the
        # agent-proposed ones (Req 6.2).
        row = _fetchone(
            postgres_container,
            "SELECT display_name, base_url FROM services"
            " WHERE tenant_id = %s AND name = %s",
            (tenant_id, name),
        )
        assert row is not None, "integration finalize did not create a services row"
        db_display, db_base_url = row
        assert db_base_url == edited_base_url          # edited value wins
        assert db_base_url != proposed_base_url
        assert db_display == edited_display            # edited value wins
        # If the operator edit differed from the proposal, the proposal value is
        # not what landed (unless the generators coincidentally matched).
        if edited_display != proposed_display:
            assert db_display != proposed_display

        # Vault was called exactly once with the edited base_url as target_url
        # (secret handed off, never persisted on the row).
        assert len(vault.calls) == 1
        assert vault.calls[0].get("target_url") == edited_base_url
        # The secret never lands on the request row's proposed_config.
        stored_cfg = _scalar(
            postgres_container,
            "SELECT proposed_config FROM access_requests WHERE id = %s",
            (str(_request_wire_to_uuid(wire_id)),),
        )
        cfg_text = json.dumps(stored_cfg) if stored_cfg is not None else ""
        assert "s3cr3t-canary" not in cfg_text
