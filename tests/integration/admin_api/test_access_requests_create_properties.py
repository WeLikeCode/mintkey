"""
Property-based tests (Hypothesis) for the agent-access-requests CREATE logic.

Feature: agent-access-requests — Task 3.4.

Exercises the three create functions in
``admin_api.services.access_requests``:
  - ``create_access_request``
  - ``create_integration_proposal``
  - ``create_share_request``

Properties (statements copied verbatim from
``.kiro/specs/agent-access-requests/design.md`` §Correctness Properties):

  - Property 7  — The config secret-denylist gate rejects any secret field
                  (Validates: Requirements 2.4)
  - Property 13 — Created requests have the correct kind-specific shape
                  (Validates: Requirements 1.1, 2.7, 3.1, 3.2, 3.9)
  - Property 14 — Invalid create/reject inputs are rejected with no row change
                  (Validates: Requirements 1.3, 1.5, 2.2, 2.3, 2.5, 2.6, 3.3,
                   3.4, 3.7, 3.8, 8.2)
  - Property 16 — Duplicate pending requests are rejected
                  (Validates: Requirements 1.6)

Testing approach (mirrors the repo's established patterns):
  - Each property runs a MINIMUM of 100 Hypothesis iterations
    (``@settings(max_examples=...)`` with ``>= 100``).
  - This is an ADD-ONLY file. It modifies neither the service code nor any
    existing test (Req 14.2).
  - The DB-backed assertions (create shape, acceptance direction, duplicate
    pending, grant-dependent share rejections) run against a REAL Postgres 16
    testcontainer with the real Liquibase changelogs applied (changeset 030 +
    seeds). This reuses the session-scoped ``postgres_container`` /
    ``apply_migrations`` / ``admin_app`` fixtures in this directory's
    ``conftest.py`` (AGENTS.md Principle 1 — never assert a column exists
    without introspecting it against the real schema). If Docker /
    testcontainers is unavailable, those tests skip gracefully (matching the
    repo's skip conventions).
  - The pure-validation REJECTION directions — the secret-denylist gate
    (Property 7) and the argument-level rejections in Property 14 (missing /
    empty required fields, out-of-enum ``auth_scheme``, malformed SSH
    ``base_url``, SSH ``target_address``, share self-target) — reject BEFORE
    any DB read reachable from the create functions, so they run WITHOUT a DB
    against a no-op fake session and are always exercised (the ``@given``
    generators drive >= 100 examples regardless of Docker).

Source: .kiro/specs/agent-access-requests/design.md §Correctness Properties,
        §Testing Strategy; requirements.md Req 1.1/1.3/1.5/1.6, 2.2/2.3/2.4/
        2.5/2.6/2.7, 3.1/3.2/3.3/3.4/3.7/3.8/3.9; ADR-0008, ADR-0017.11,
        ADR-0023.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from admin_api.services.access_requests import (
    AccessRequestError,
    _AUTH_SCHEME_ENUM,
    create_access_request,
    create_integration_proposal,
    create_share_request,
)

# Minimum iterations per property (Task 3.4 requirement: >= 100).
_MAX_EXAMPLES = 150

# Hypothesis + a per-example real DB round-trip is slow and reuses a shared
# fixture across examples, so disable the deadline and the
# function-scoped-fixture health check (the fixture is intentionally reused).
_DB_SETTINGS = settings(
    max_examples=_MAX_EXAMPLES,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
_PURE_SETTINGS = settings(max_examples=_MAX_EXAMPLES, deadline=None)


# ===========================================================================
# No-op fake async session — for pure-validation REJECTION directions only.
#
# The create functions call ``set_tenant_context(session, ...)`` first (a
# harmless ``SELECT set_config(...)``) and only touch the DB via ``execute``
# afterwards. Every rejection asserted against this fake occurs BEFORE any
# reachable read/INSERT, so a session whose ``execute`` is a no-op that returns
# an empty result is sufficient and guarantees no row is ever written.
# ===========================================================================


class _EmptyResult:
    def fetchone(self) -> None:
        return None

    def fetchall(self) -> list[Any]:
        return []


class _NoOpSession:
    """Records nothing, inserts nothing; ``execute`` is a no-op await."""

    def __init__(self) -> None:
        self.execute_count = 0

    async def execute(self, *_args: Any, **_kwargs: Any) -> _EmptyResult:
        self.execute_count += 1
        return _EmptyResult()


# One persistent event loop for the whole module. A fresh loop per Hypothesis
# example would orphan pooled asyncpg connections created on an earlier loop
# ("Event loop is closed" at pool cleanup), so every coroutine here runs on the
# SAME loop and the dedicated NullPool engine (see ``_arp_engine``) keeps no
# connection alive between calls.
_LOOP = asyncio.new_event_loop()


def _run(coro: Any) -> Any:
    """Drive an async coroutine to completion on the shared module loop."""
    return _LOOP.run_until_complete(coro)


_TENANT = uuid.UUID("aaaaaaaa-0000-0000-0000-0000000000f4")
_AGENT = uuid.UUID("bbbbbbbb-0000-0000-0000-0000000000f4")
_TARGET = uuid.UUID("cccccccc-0000-0000-0000-0000000000f4")
_SERVICE = uuid.UUID("dddddddd-0000-0000-0000-0000000000f4")


# Non-secret config field names accepted by the denylist gate.
_NON_SECRET_KEYS = ["client_id", "token_url", "ssh_user", "header_name", "region"]

# Field-name shapes that MUST match the secret denylist
# (``*_secret`` / ``*_password`` / ``*_passphrase`` + exact
# ``private_key`` / ``token`` / ``api_key``) — Req 2.4.
_secret_key_strategy = st.one_of(
    st.from_regex(r"[a-z][a-z_]{0,10}_secret", fullmatch=True),
    st.from_regex(r"[a-z][a-z_]{0,10}_password", fullmatch=True),
    st.from_regex(r"[a-z][a-z_]{0,10}_passphrase", fullmatch=True),
    st.sampled_from(["private_key", "token", "api_key"]),
)

# Text that a real Postgres text column can store: no NUL (0x00) and no other
# C0/C1 control characters. Postgres rejects NUL bytes in ANY text column
# ("invalid byte sequence for encoding UTF8: 0x00"), so a NUL is outside the
# realistic valid input space for an action / config value — excluding it keeps
# the property's meaning intact (this is a generator constraint, not a code or
# spec change).
_db_safe_text = st.text(
    alphabet=st.characters(
        min_codepoint=0x20,
        max_codepoint=0x7E,  # printable ASCII
    ),
    min_size=0,
    max_size=12,
)

# A non-empty, non-whitespace action string that Postgres can store.
_db_safe_action = st.text(
    alphabet=st.characters(min_codepoint=0x21, max_codepoint=0x7E),
    min_size=1,
    max_size=16,
).filter(lambda s: s.strip())

_non_secret_config = st.dictionaries(
    keys=st.sampled_from(_NON_SECRET_KEYS),
    values=_db_safe_text,
    max_size=len(_NON_SECRET_KEYS),
)


# ===========================================================================
# Property 7 — secret-denylist gate (REJECTION direction; DB-free, always runs)
# ===========================================================================
# Feature: agent-access-requests, Property 7: The config secret-denylist gate
# rejects any secret field — for any integration proposal config object, the
# proposal SHALL be rejected with secret_field_not_allowed if and only if at
# least one key matches the secret denylist (*_secret, *_password, *_passphrase,
# private_key, token, api_key); when no key matches, the non-secret fields SHALL
# be accepted and stored on proposed_config.


class TestProperty7DenylistGate:
    """Property 7 — a config carrying any denylisted secret field is rejected."""

    @_PURE_SETTINGS
    @given(
        secret_key=_secret_key_strategy,
        extra=_non_secret_config,
        auth_scheme=st.sampled_from(
            ["bearer_token", "api_key_header", "oauth2_client_credentials"]
        ),
    )
    def test_config_with_secret_field_rejected(
        self, secret_key: str, extra: dict[str, str], auth_scheme: str
    ) -> None:
        """Any config containing a denylisted key → secret_field_not_allowed,
        raised before any DB row is written (Req 2.4, P-1)."""
        config = {**extra, secret_key: "shhh-canary"}
        session = _NoOpSession()

        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_integration_proposal(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    name="proposed-svc",
                    base_url="https://api.example.com",
                    auth_scheme=auth_scheme,
                    openapi_url=None,
                    config=config,
                )
            )

        assert exc.value.code == "secret_field_not_allowed"
        # The offending field name is surfaced (Req 2.4).
        assert exc.value.field == secret_key
        # No INSERT path was reached — the only execute is set_tenant_context,
        # and never an access_requests INSERT.
        assert session.execute_count <= 1


# ===========================================================================
# Property 14 — invalid create inputs rejected, no row (pure-validation subset;
# DB-free, always runs)
# ===========================================================================
# Feature: agent-access-requests, Property 14: Invalid create/reject inputs are
# rejected with no row change — for any create call missing or supplying an
# empty/whitespace required field (access: service_id/action; integration:
# name/base_url/auth_scheme, out-of-enum auth_scheme, SSH base_url not
# ssh://host:port, SSH with target_address; share: service_id/action/
# target_agent_id, self-target, outbound without the requester's grant, target
# already granted), the request SHALL be rejected with the specified error code
# and SHALL create no row; and for any reject call whose reason is missing,
# empty, whitespace-only, or longer than 1000 characters, the call SHALL be
# rejected with reason_required and SHALL leave the request unchanged.

# Whitespace / empty strings that must be treated as "missing" (Req 1.3, 2.2, 3.3).
_blank_strategy = st.sampled_from(["", "   ", "\t", "\n", "  \t \n "])


class TestProperty14PureRejections:
    """Property 14 — argument-level rejections that fire before any DB read."""

    # --- access: missing/empty action -------------------------------------
    @_PURE_SETTINGS
    @given(action=_blank_strategy)
    def test_access_blank_action_rejected(self, action: str) -> None:
        session = _NoOpSession()
        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_access_request(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    service_id=_SERVICE,
                    action=action,
                )
            )
        assert exc.value.code == "invalid_argument"
        assert exc.value.field == "action"
        assert session.execute_count <= 1

    @_PURE_SETTINGS
    @given(action=st.text(max_size=8))
    def test_access_missing_service_id_rejected(self, action: str) -> None:
        """service_id=None → invalid_argument naming service_id, no row."""
        session = _NoOpSession()
        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_access_request(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    service_id=None,
                    action=action,
                )
            )
        assert exc.value.code == "invalid_argument"
        assert exc.value.field == "service_id"
        assert session.execute_count <= 1

    # --- integration: missing required fields -----------------------------
    @_PURE_SETTINGS
    @given(
        which=st.sampled_from(["name", "base_url", "auth_scheme"]),
        blank=_blank_strategy,
    )
    def test_integration_blank_required_field_rejected(
        self, which: str, blank: str
    ) -> None:
        kwargs: dict[str, Any] = {
            "name": "svc",
            "base_url": "https://api.example.com",
            "auth_scheme": "bearer_token",
        }
        kwargs[which] = blank
        session = _NoOpSession()
        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_integration_proposal(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    openapi_url=None,
                    config={},
                    **kwargs,
                )
            )
        assert exc.value.code == "invalid_argument"
        assert exc.value.field == which
        assert session.execute_count <= 1

    # --- integration: auth_scheme not in the closed enum ------------------
    @_PURE_SETTINGS
    @given(
        auth_scheme=st.text(
            alphabet="abcdefghijklmnopqrstuvwxyz_", min_size=1, max_size=16
        ).filter(lambda s: s.strip() and s.strip() not in _AUTH_SCHEME_ENUM)
    )
    def test_integration_out_of_enum_auth_scheme_rejected(
        self, auth_scheme: str
    ) -> None:
        session = _NoOpSession()
        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_integration_proposal(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    name="svc",
                    base_url="https://api.example.com",
                    auth_scheme=auth_scheme,
                    openapi_url=None,
                    config={},
                )
            )
        assert exc.value.code == "invalid_argument"
        assert exc.value.field == "auth_scheme"
        assert session.execute_count <= 1

    # --- integration: SSH base_url not ssh://host:port (Req 2.5) ----------
    @_PURE_SETTINGS
    @given(
        ssh_scheme=st.sampled_from(["ssh_private_key", "ssh_ca", "ssh_password"]),
        bad_base_url=st.sampled_from(
            [
                "https://host.example.com:22",  # wrong scheme
                "ssh://host.example.com",        # no port
                "ssh://host:notaport",           # non-numeric port
                "ssh://host:22/path",            # trailing path
                "host:22",                        # missing scheme
                "ssh://:22",                      # empty host
            ]
        ),
    )
    def test_integration_ssh_bad_base_url_rejected(
        self, ssh_scheme: str, bad_base_url: str
    ) -> None:
        session = _NoOpSession()
        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_integration_proposal(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    name="ssh-box",
                    base_url=bad_base_url,
                    auth_scheme=ssh_scheme,
                    openapi_url=None,
                    config={"ssh_user": "root"},
                )
            )
        assert exc.value.code == "invalid_argument"
        assert exc.value.field == "base_url"
        assert session.execute_count <= 1

    # --- integration: SSH with target_address (Req 2.6) -------------------
    @_PURE_SETTINGS
    @given(
        ssh_scheme=st.sampled_from(["ssh_private_key", "ssh_ca", "ssh_password"]),
        target=st.text(min_size=1, max_size=20),
    )
    def test_integration_ssh_target_address_rejected(
        self, ssh_scheme: str, target: str
    ) -> None:
        session = _NoOpSession()
        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_integration_proposal(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    name="ssh-box",
                    base_url="ssh://host.example.com:22",
                    auth_scheme=ssh_scheme,
                    openapi_url=None,
                    config={"ssh_user": "root", "target_address": target},
                )
            )
        assert exc.value.code == "invalid_argument"
        assert exc.value.field == "target_address"
        assert session.execute_count <= 1

    # --- share: missing required fields -----------------------------------
    @_PURE_SETTINGS
    @given(blank=_blank_strategy)
    def test_share_blank_action_rejected(self, blank: str) -> None:
        session = _NoOpSession()
        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_share_request(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    service_id=_SERVICE,
                    action=blank,
                    target_agent_id=_TARGET,
                )
            )
        assert exc.value.code == "invalid_argument"
        assert exc.value.field == "action"
        assert session.execute_count <= 1

    @_PURE_SETTINGS
    @given(action=st.text(min_size=1, max_size=8).filter(lambda s: s.strip()))
    def test_share_missing_target_rejected(self, action: str) -> None:
        session = _NoOpSession()
        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_share_request(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    service_id=_SERVICE,
                    action=action,
                    target_agent_id=None,
                )
            )
        assert exc.value.code == "invalid_argument"
        assert exc.value.field == "target_agent_id"
        assert session.execute_count <= 1

    # --- share: self-target (Req 3.4) -------------------------------------
    @_PURE_SETTINGS
    @given(action=st.text(min_size=1, max_size=8).filter(lambda s: s.strip()))
    def test_share_self_target_rejected(self, action: str) -> None:
        session = _NoOpSession()
        with pytest.raises(AccessRequestError) as exc:
            _run(
                create_share_request(
                    session,  # type: ignore[arg-type]
                    tenant_id=_TENANT,
                    requesting_agent_id=_AGENT,
                    service_id=_SERVICE,
                    action=action,
                    target_agent_id=_AGENT,  # self-target
                )
            )
        assert exc.value.code == "invalid_argument"
        assert exc.value.field == "target_agent_id"
        assert session.execute_count <= 1


# ===========================================================================
# DB-backed properties (7 acceptance, 13, 14 grant-dependent, 16)
# ===========================================================================
# These use a REAL Postgres 16 testcontainer via the directory conftest.
# The ``_seed`` fixture inserts a tenant + a requesting agent + a target agent
# + a service once; each property creates rows under that tenant and counts
# ``access_requests`` before/after with psycopg2.

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


@pytest.fixture(scope="module")
def _seed(admin_app, apply_migrations, postgres_container):  # type: ignore[no-untyped-def]
    """Seed one tenant + requesting/target agents + a service; return their IDs.

    Also builds a dedicated NullPool async engine (bound to the testcontainer
    DB) and publishes its sessionmaker to ``_ARP_SESSIONMAKER`` so the property
    bodies open sessions on the single shared loop without a connection pool.

    ``apply_migrations`` is depended on so changeset 030 (access_requests) is
    present before any create runs.
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
        (tenant_id, f"arp-prop-{tenant_id[:8]}", "arp-prop"),
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

    requesting_agent_id = _agent("arp-requesting-agent")
    target_agent_id = _agent("arp-target-agent")

    service_id = str(uuid.uuid4())
    _exec(
        postgres_container,
        "INSERT INTO services"
        " (id, tenant_id, name, slug, display_name, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'bearer_token', 'active')",
        (
            service_id,
            tenant_id,
            "arp-service",
            "arp-service",
            "arp-service",
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


def _count_requests(postgres_container, tenant_id: str) -> int:  # type: ignore[no-untyped-def]
    return int(
        _scalar(
            postgres_container,
            "SELECT count(*) FROM access_requests WHERE tenant_id = %s",
            (tenant_id,),
        )
    )


# Dedicated NullPool sessionmaker for the property tests, set by the ``_seed``
# fixture. NullPool means each session's connection is opened and fully closed
# within the single shared loop, so no connection is ever cleaned up against a
# stale loop.
_ARP_SESSIONMAKER: Any = None


async def _new_session():  # type: ignore[no-untyped-def]
    """Open an AsyncSession bound to the dedicated NullPool test engine."""
    assert _ARP_SESSIONMAKER is not None, "_seed fixture must run first"
    return _ARP_SESSIONMAKER()


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty13CreateShapeDB:
    """Property 13 — created requests have the correct kind-specific shape."""

    # Feature: agent-access-requests, Property 13: Created requests have the
    # correct kind-specific shape — an access request SHALL have kind=access,
    # status=pending, a non-null (service_id, action), and null proposed_config;
    # an integration proposal SHALL have kind=integration, null service_id, and a
    # non-null proposed_config with no services row created; a share request
    # SHALL have kind=share, a non-null service_id, a share_direction of outbound
    # or inbound, and null proposed_config.

    @_DB_SETTINGS
    @given(action=_db_safe_action)
    def test_access_request_shape(self, _seed, postgres_container, action: str) -> None:  # type: ignore[no-untyped-def]
        tenant_id = _seed["tenant_id"]

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    created = await create_access_request(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        requesting_agent_id=uuid.UUID(_seed["requesting_agent_id"]),
                        service_id=uuid.UUID(_seed["service_id"]),
                        action=action,
                    )
                return created.request_id
            finally:
                await session.close()

        request_id = _run(_do())
        assert request_id.startswith("request_")

        row = _fetchone(
            postgres_container,
            "SELECT kind, status, service_id, action, proposed_config,"
            " target_agent_id, share_direction FROM access_requests"
            " WHERE tenant_id = %s AND requesting_agent_id = %s AND action = %s"
            " ORDER BY created_at DESC LIMIT 1",
            (tenant_id, _seed["requesting_agent_id"], action.strip()),
        )
        assert row is not None, "access request row not persisted"
        kind, status, service_id, act, proposed_config, target, direction = row
        assert kind == "access"
        assert status == "pending"
        assert service_id is not None
        assert act == action.strip()
        assert proposed_config is None
        assert target is None
        assert direction is None

    @_DB_SETTINGS
    @given(
        auth_scheme=st.sampled_from(
            ["bearer_token", "api_key_header", "oauth2_client_credentials"]
        ),
        config=_non_secret_config,
    )
    def test_integration_proposal_shape(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, auth_scheme: str, config: dict[str, str]
    ) -> None:
        tenant_id = _seed["tenant_id"]
        name = "prop-" + uuid.uuid4().hex[:12]

        async def _do() -> str:
            session = await _new_session()
            try:
                async with session.begin():
                    created = await create_integration_proposal(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        requesting_agent_id=uuid.UUID(_seed["requesting_agent_id"]),
                        name=name,
                        base_url="https://api.example.com",
                        auth_scheme=auth_scheme,
                        openapi_url=None,
                        config=config,
                    )
                return created.request_id
            finally:
                await session.close()

        services_before = int(
            _scalar(
                postgres_container,
                "SELECT count(*) FROM services WHERE tenant_id = %s",
                (tenant_id,),
            )
        )
        request_id = _run(_do())
        assert request_id.startswith("request_")

        row = _fetchone(
            postgres_container,
            "SELECT kind, status, service_id, proposed_config FROM access_requests"
            " WHERE tenant_id = %s AND proposed_config->>'name' = %s"
            " ORDER BY created_at DESC LIMIT 1",
            (tenant_id, name),
        )
        assert row is not None, "integration proposal row not persisted"
        kind, status, service_id, proposed_config = row
        assert kind == "integration"
        assert status == "pending"
        assert service_id is None            # Req 2.7 — no services FK on the row
        assert proposed_config is not None   # non-secret proposed config stored

        services_after = int(
            _scalar(
                postgres_container,
                "SELECT count(*) FROM services WHERE tenant_id = %s",
                (tenant_id,),
            )
        )
        assert services_after == services_before  # Req 2.7 — no services row created

    @_DB_SETTINGS
    @given(action=_db_safe_action)
    def test_share_request_shape_inbound(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, action: str
    ) -> None:
        """Requester holds no grant → inbound share; correct shape (Req 3.1/3.2/3.9)."""
        tenant_id = _seed["tenant_id"]
        act = action.strip() + "-" + uuid.uuid4().hex[:6]

        async def _do():  # type: ignore[no-untyped-def]
            session = await _new_session()
            try:
                async with session.begin():
                    return await create_share_request(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        requesting_agent_id=uuid.UUID(_seed["requesting_agent_id"]),
                        service_id=uuid.UUID(_seed["service_id"]),
                        action=act,
                        target_agent_id=uuid.UUID(_seed["target_agent_id"]),
                    )
            finally:
                await session.close()

        created = _run(_do())
        assert created.request_id.startswith("request_")
        assert created.share_direction == "inbound"

        row = _fetchone(
            postgres_container,
            "SELECT kind, status, service_id, share_direction, proposed_config"
            " FROM access_requests WHERE tenant_id = %s AND action = %s"
            " ORDER BY created_at DESC LIMIT 1",
            (tenant_id, act),
        )
        assert row is not None
        kind, status, service_id, direction, proposed_config = row
        assert kind == "share"
        assert status == "pending"
        assert service_id is not None
        assert direction in ("inbound", "outbound")
        assert proposed_config is None


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty7AcceptDB:
    """Property 7 (acceptance direction) — a config with only non-secret keys
    is accepted and stored on proposed_config."""

    # Feature: agent-access-requests, Property 7: The config secret-denylist gate
    # rejects any secret field — when no key matches, the non-secret fields SHALL
    # be accepted and stored on proposed_config.

    @_DB_SETTINGS
    @given(config=_non_secret_config)
    def test_non_secret_config_accepted_and_stored(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, config: dict[str, str]
    ) -> None:
        tenant_id = _seed["tenant_id"]
        name = "acc-" + uuid.uuid4().hex[:12]

        async def _do():  # type: ignore[no-untyped-def]
            session = await _new_session()
            try:
                async with session.begin():
                    return await create_integration_proposal(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        requesting_agent_id=uuid.UUID(_seed["requesting_agent_id"]),
                        name=name,
                        base_url="https://api.example.com",
                        auth_scheme="bearer_token",
                        openapi_url=None,
                        config=config,
                    )
            finally:
                await session.close()

        created = _run(_do())
        assert created.status == "pending"

        stored = _scalar(
            postgres_container,
            "SELECT proposed_config FROM access_requests"
            " WHERE tenant_id = %s AND proposed_config->>'name' = %s"
            " ORDER BY created_at DESC LIMIT 1",
            (tenant_id, name),
        )
        assert stored is not None
        # Every supplied non-secret key round-trips into proposed_config.
        for key in config:
            assert key in stored


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty14GrantDependentDB:
    """Property 14 (grant-dependent share rejections) — target already granted
    → already_granted, no row (Req 3.8)."""

    @_DB_SETTINGS
    @given(action=_db_safe_action)
    def test_share_target_already_granted_rejected_no_row(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, action: str
    ) -> None:
        tenant_id = _seed["tenant_id"]
        target_id = _seed["target_agent_id"]
        service_id = _seed["service_id"]
        act = "granted-" + uuid.uuid4().hex[:8]

        # Seed an existing grant for the TARGET on (service, act).
        _exec(
            postgres_container,
            "INSERT INTO permission_grants"
            " (id, tenant_id, agent_id, service_id, action, constraints, created_by)"
            " VALUES (%s, %s, %s, %s, %s, '{}', %s)",
            (
                str(uuid.uuid4()),
                tenant_id,
                target_id,
                service_id,
                act,
                _seed["requesting_agent_id"],
            ),
        )

        before = _count_requests(postgres_container, tenant_id)

        async def _do():  # type: ignore[no-untyped-def]
            session = await _new_session()
            try:
                async with session.begin():
                    return await create_share_request(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        requesting_agent_id=uuid.UUID(_seed["requesting_agent_id"]),
                        service_id=uuid.UUID(service_id),
                        action=act,
                        target_agent_id=uuid.UUID(target_id),
                    )
            finally:
                await session.close()

        with pytest.raises(AccessRequestError) as exc:
            _run(_do())
        assert exc.value.code == "already_granted"

        after = _count_requests(postgres_container, tenant_id)
        assert after == before  # no row created (Req 3.8, Property 14)


@pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")
class TestProperty16DuplicatePendingDB:
    """Property 16 — a second identical pending access request is rejected and
    exactly one such row remains."""

    # Feature: agent-access-requests, Property 16: Duplicate pending requests are
    # rejected — for any Requesting_Agent and (service_id, action), once a pending
    # access request exists, a second identical create SHALL be rejected with
    # request_already_pending and SHALL leave exactly one such row.

    @_DB_SETTINGS
    @given(action=_db_safe_action)
    def test_duplicate_pending_rejected_exactly_one_row(  # type: ignore[no-untyped-def]
        self, _seed, postgres_container, action: str
    ) -> None:
        tenant_id = _seed["tenant_id"]
        requesting_id = _seed["requesting_agent_id"]
        service_id = _seed["service_id"]
        act = "dup-" + uuid.uuid4().hex[:8]

        async def _create():  # type: ignore[no-untyped-def]
            session = await _new_session()
            try:
                async with session.begin():
                    return await create_access_request(
                        session,
                        tenant_id=uuid.UUID(tenant_id),
                        requesting_agent_id=uuid.UUID(requesting_id),
                        service_id=uuid.UUID(service_id),
                        action=act,
                    )
            finally:
                await session.close()

        # First create succeeds.
        first = _run(_create())
        assert first.status == "pending"

        # Second identical create must be rejected with request_already_pending.
        with pytest.raises(AccessRequestError) as exc:
            _run(_create())
        assert exc.value.code == "request_already_pending"

        # Exactly one pending access row for (agent, service, action).
        count = int(
            _scalar(
                postgres_container,
                "SELECT count(*) FROM access_requests"
                " WHERE tenant_id = %s AND kind = 'access' AND status = 'pending'"
                "   AND requesting_agent_id = %s AND service_id = %s AND action = %s",
                (tenant_id, requesting_id, service_id, act),
            )
        )
        assert count == 1
