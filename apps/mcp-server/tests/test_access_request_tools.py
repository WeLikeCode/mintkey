"""
Integration tests for the four agent-access-request MCP tools (T-7.2).

Covers ``request_access``, ``propose_integration``, ``request_share``, and
``list_my_requests`` (see ``apps/mcp-server/src/mcp_server/tools/{request_access,
propose_integration,request_share,list_my_requests}.py`` + ``_access_requests_common.py``
from T-7.1).

Test harness follows the established mcp-server integration-test pattern (see
``test_secret_tools.py`` / ``test_request_token.py``): build the app-under-test
with ``create_app()``, simulate the Bearer Agent API Key context by overriding
the ``get_agent_context`` dependency, and mock the async DB session via a
``get_db_session`` dependency override. The audit chokepoint
(``mintkey_models.audit.audit_emit``, imported lazily inside
``_access_requests_common.emit_created_audit``) is patched to a no-op so no
hash-chain DB work is required — matching how the secret-tool tests isolate the
handler surface from the audit machinery.

Unlike the fully static secret-tool mock, this mock keeps a small in-memory row
store so ``list_my_requests`` can be asserted end-to-end: the mock honours the
handler's ``tenant_id`` + ``requesting_agent_id`` WHERE parameters, so seeding
rows for a second agent (same tenant) and a second tenant lets us prove those
rows are NOT returned to the caller (Req 1.7, 8.4).

Cases:
  - request_access      → creates kind=access pending row; echoes
                          {request_id (request_ prefix), status: "pending"} (Req 1.1)
  - propose_integration → creates kind=integration pending row; echoes
                          {request_id, status} (Req 2.1)
  - request_share       → creates kind=share pending row; echoes
                          {request_id, status, share_direction} (Req 3.1)
  - list_my_requests    → returns ONLY the caller's own rows scoped to its
                          tenant; rows for a second agent (same tenant) and a
                          second tenant are NOT returned (Req 1.7, 8.4)
  - none of the create tools accept a tenant_id argument — a passed tenant_id is
    ignored by the closed Pydantic input schema and never scopes the row
    (Req 13.2)

STRICTLY ADDITIVE: this is a NEW test file. It modifies no existing test and no
handler. Python 3.12, pytest, httpx ASGI transport (matching the established
mcp-server harness, which mocks the DB rather than standing up testcontainers
for tool-surface tests).

Source: T-7.2; design §Components (MCP Server); Req 1.1, 1.7, 2.1, 3.1, 8.4,
        13.2; ADR-0009 (tenant from auth ctx), ADR-0017.11 (prefixed ULID).
"""
from __future__ import annotations

import asyncio
import datetime as _dt
import uuid
from typing import Any, AsyncGenerator, Optional
from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

from mcp_server.utils.wire_ids import db_uuid_to_wire

# ---------------------------------------------------------------------------
# Fixed test identities (raw UUIDs for the auth context; wire form for inputs).
# ---------------------------------------------------------------------------

_TENANT_A = str(uuid.uuid4())
_TENANT_B = str(uuid.uuid4())

_AGENT_A = str(uuid.uuid4())          # the calling agent (tenant A)
_AGENT_A2 = str(uuid.uuid4())         # a second agent in tenant A
_AGENT_B = str(uuid.uuid4())          # an agent in tenant B

_SERVICE_UUID = str(uuid.uuid4())
_SERVICE_WIRE = db_uuid_to_wire(_SERVICE_UUID, "svc")

_TARGET_AGENT_UUID = str(uuid.uuid4())
_TARGET_AGENT_WIRE = db_uuid_to_wire(_TARGET_AGENT_UUID, "agent")


def _run(coro):
    """Run an async coroutine in a fresh event loop (test helper)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# In-memory row + mock DB session builder.
# ---------------------------------------------------------------------------


def _seed_row(
    *,
    tenant_id: str,
    requesting_agent_id: str,
    kind: str = "access",
    status: str = "pending",
) -> dict[str, Any]:
    """Build a seed row for the list-store honouring the columns list SELECTs."""
    now = _dt.datetime(2026, 1, 1, tzinfo=_dt.timezone.utc)
    return {
        "id": uuid.UUID(str(uuid.uuid4())),
        "tenant_id": tenant_id,
        "requesting_agent_id": requesting_agent_id,
        "kind": kind,
        "status": status,
        "created_at": now,
        # 30 days out — never elapsed at read time, so effective_status == status.
        "expires_at": now + _dt.timedelta(days=30),
    }


def _build_app(
    *,
    agent_id: str = _AGENT_A,
    tenant_id: str = _TENANT_A,
    service_present: bool = True,
    target_agent_present: bool = True,
    caller_holds_grant: bool = False,
    target_holds_grant: bool = False,
    pending_duplicate: bool = False,
    list_store: Optional[list[dict[str, Any]]] = None,
):
    """
    Build the mcp-server app with a mocked agent context + DB session.

    The DB mock dispatches on the parameter keys/SQL text the T-7.1 handlers use:

      - ``set_tenant_context`` (SET LOCAL) → empty result.
      - ``service_exists``  (params: sid + tid)                → configurable.
      - ``agent_exists``    (params: aid + tid, agents table)  → configurable.
      - ``grant_exists``    (permission_grants; aid == caller / target)
                            → configurable per-agent.
      - ``_pending_duplicate_exists`` (access_requests + status='pending' in SQL)
                            → configurable.
      - INSERT into access_requests → captured into ``inserted``.
      - list_my_requests SELECT (params: tid + aid) → filters ``list_store`` by
        tenant_id AND requesting_agent_id (and optional status/kind), proving
        tenant + agent scoping (Req 1.7, 8.4).
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _fake_agent_context():
        return {"agent_id": agent_id, "tenant_id": tenant_id}

    app.dependency_overrides[get_agent_context] = _fake_agent_context

    captured: dict[str, Any] = {"inserted": []}

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()

        async def _execute(stmt, params=None, **kw):
            result = MagicMock()
            result.fetchone = MagicMock(return_value=None)
            result.fetchall = MagicMock(return_value=[])
            result.mappings = MagicMock(return_value=[])
            p = params or {}
            sql = str(stmt)

            # INSERT — capture the row the handler is persisting.
            if sql.strip().upper().startswith("INSERT INTO ACCESS_REQUESTS"):
                captured["inserted"].append(dict(p))
                return result

            # list_my_requests SELECT — filter the seed store by tenant + agent.
            if "FROM access_requests" in sql and "requesting_agent_id = :aid" in sql \
                    and "ORDER BY" in sql:
                rows = list_store or []
                want_status = p.get("status")
                want_kind = p.get("kind")
                selected = [
                    r for r in rows
                    if r["tenant_id"] == p.get("tid")
                    and r["requesting_agent_id"] == p.get("aid")
                    and (want_status is None or r["status"] == want_status)
                    and (want_kind is None or r["kind"] == want_kind)
                ]
                selected.sort(key=lambda r: (r["created_at"], r["id"]), reverse=True)
                result.mappings = MagicMock(return_value=selected)
                return result

            # _pending_duplicate_exists — access_requests + status='pending'.
            if "FROM access_requests" in sql and "status = 'pending'" in sql:
                result.fetchone.return_value = (1,) if pending_duplicate else None
                return result

            # service_exists — services table.
            if "FROM services" in sql:
                result.fetchone.return_value = (1,) if service_present else None
                return result

            # agent_exists — agents table.
            if "FROM agents" in sql:
                result.fetchone.return_value = (1,) if target_agent_present else None
                return result

            # grant_exists — permission_grants; distinguish caller vs target.
            if "FROM permission_grants" in sql:
                aid = p.get("aid")
                if aid == agent_id:
                    result.fetchone.return_value = (1,) if caller_holds_grant else None
                elif aid == _TARGET_AGENT_UUID:
                    result.fetchone.return_value = (1,) if target_holds_grant else None
                else:
                    result.fetchone.return_value = None
                return result

            # set_tenant_context (SET LOCAL) and anything else — empty.
            return result

        session.execute = _execute
        session.commit = AsyncMock()
        captured["session"] = session
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session
    return app, captured


def _noop_audit():
    """Patch the audit chokepoint (lazy-imported in emit_created_audit) to no-op."""
    return patch("mintkey_models.audit.audit_emit", new=AsyncMock(return_value=None))


# ---------------------------------------------------------------------------
# request_access — Req 1.1
# ---------------------------------------------------------------------------


def test_request_access_creates_access_pending_and_echoes_request_id():
    """request_access creates a kind=access pending row and echoes request_id/status."""
    app, captured = _build_app()
    with _noop_audit():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/request_access",
                    json={"service_id": _SERVICE_WIRE, "action": "call"},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["request_id"].startswith("request_")

    # Exactly one access_requests row inserted, kind=access, tenant scoped to ctx.
    assert len(captured["inserted"]) == 1
    row = captured["inserted"][0]
    assert row["kind"] == "access"
    assert row["tenant_id"] == _TENANT_A
    assert row["requesting_agent_id"] == _AGENT_A
    # request_id echoed matches the inserted row's derived wire id.
    assert db_uuid_to_wire(row["id"], "request") == body["request_id"]


def test_request_access_ignores_client_supplied_tenant_id():
    """A tenant_id argument is not part of the closed input schema (Req 13.2).

    The tenant that scopes the row comes from the auth context, never from the
    request body — so a client-passed tenant_id (here tenant B) is ignored and
    the row is still created under the caller's tenant (tenant A).
    """
    app, captured = _build_app()
    with _noop_audit():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/request_access",
                    json={
                        "service_id": _SERVICE_WIRE,
                        "action": "call",
                        "tenant_id": _TENANT_B,  # must be ignored
                    },
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    assert len(captured["inserted"]) == 1
    row = captured["inserted"][0]
    # Row scoped to the auth-context tenant (A), NOT the body-supplied tenant (B).
    assert row["tenant_id"] == _TENANT_A
    assert row["tenant_id"] != _TENANT_B


def test_request_access_unauthenticated_returns_401():
    """request_access returns 401 when no agent context is present."""
    import mcp_server.main as _main_mod
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _no_ctx():
        return None

    app.dependency_overrides[get_agent_context] = _no_ctx

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/v1/tools/request_access",
                json={"service_id": _SERVICE_WIRE, "action": "call"},
            )

    resp = _run(_inner())
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# propose_integration — Req 2.1
# ---------------------------------------------------------------------------


def test_propose_integration_creates_integration_pending_and_echoes_request_id():
    """propose_integration creates a kind=integration pending row; echoes id/status."""
    app, captured = _build_app()
    with _noop_audit():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/propose_integration",
                    json={
                        "name": "acme-api",
                        "base_url": "https://api.acme.example",
                        "auth_scheme": "bearer_token",
                        "config": {"client_id": "abc123"},
                    },
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["request_id"].startswith("request_")

    assert len(captured["inserted"]) == 1
    row = captured["inserted"][0]
    assert row["kind"] == "integration"
    assert row["tenant_id"] == _TENANT_A
    assert row["requesting_agent_id"] == _AGENT_A
    # No services row is created; a proposal carries proposed_config, no service_id.
    assert row["service_id"] is None


def test_propose_integration_ignores_client_supplied_tenant_id():
    """A tenant_id argument is not part of propose_integration's schema (Req 13.2)."""
    app, captured = _build_app()
    with _noop_audit():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/propose_integration",
                    json={
                        "name": "acme-api",
                        "base_url": "https://api.acme.example",
                        "auth_scheme": "bearer_token",
                        "config": {"client_id": "abc123"},
                        "tenant_id": _TENANT_B,  # must be ignored
                    },
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    row = captured["inserted"][0]
    assert row["tenant_id"] == _TENANT_A


# ---------------------------------------------------------------------------
# request_share — Req 3.1
# ---------------------------------------------------------------------------


def test_request_share_creates_share_pending_and_echoes_direction():
    """request_share creates a kind=share pending row; echoes id/status/direction.

    The caller holds the (service, action) grant → the share is ``outbound``.
    """
    app, captured = _build_app(
        service_present=True,
        target_agent_present=True,
        caller_holds_grant=True,   # → outbound
        target_holds_grant=False,
    )
    with _noop_audit():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/request_share",
                    json={
                        "service_id": _SERVICE_WIRE,
                        "action": "call",
                        "target_agent_id": _TARGET_AGENT_WIRE,
                    },
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "pending"
    assert body["request_id"].startswith("request_")
    assert body["share_direction"] == "outbound"

    assert len(captured["inserted"]) == 1
    row = captured["inserted"][0]
    assert row["kind"] == "share"
    assert row["tenant_id"] == _TENANT_A
    assert row["requesting_agent_id"] == _AGENT_A
    assert row["share_direction"] == "outbound"
    assert row["target_agent_id"] == _TARGET_AGENT_UUID


def test_request_share_inbound_direction_when_caller_lacks_grant():
    """When the caller lacks the grant, the share is recorded as ``inbound``."""
    app, captured = _build_app(
        service_present=True,
        target_agent_present=True,
        caller_holds_grant=False,  # → inbound
        target_holds_grant=False,
    )
    with _noop_audit():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/request_share",
                    json={
                        "service_id": _SERVICE_WIRE,
                        "action": "call",
                        "target_agent_id": _TARGET_AGENT_WIRE,
                    },
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["share_direction"] == "inbound"
    assert captured["inserted"][0]["share_direction"] == "inbound"


# ---------------------------------------------------------------------------
# list_my_requests — Req 1.7, 8.4 (tenant + agent scoping)
# ---------------------------------------------------------------------------


def test_list_my_requests_returns_only_callers_tenant_scoped_rows():
    """list_my_requests returns ONLY the caller's own rows scoped to its tenant.

    Seed: two rows for the caller (agent A, tenant A), one row for a second agent
    in the SAME tenant (agent A2, tenant A), and one row for an agent in a
    DIFFERENT tenant (agent B, tenant B). Only the caller's two rows come back —
    the same-tenant-other-agent row and the other-tenant row are excluded
    (Req 1.7, 8.4).
    """
    caller_rows = [
        _seed_row(tenant_id=_TENANT_A, requesting_agent_id=_AGENT_A, kind="access"),
        _seed_row(tenant_id=_TENANT_A, requesting_agent_id=_AGENT_A, kind="share"),
    ]
    other_agent_same_tenant = _seed_row(
        tenant_id=_TENANT_A, requesting_agent_id=_AGENT_A2, kind="access"
    )
    other_tenant = _seed_row(
        tenant_id=_TENANT_B, requesting_agent_id=_AGENT_B, kind="access"
    )
    store = [*caller_rows, other_agent_same_tenant, other_tenant]

    app, _captured = _build_app(list_store=store)

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(
                "/v1/tools/list_my_requests",
                headers={"Authorization": "Bearer mk_agent_test"},
            )

    resp = _run(_inner())
    assert resp.status_code == 200, resp.text
    body = resp.json()
    returned_ids = {r["request_id"] for r in body["requests"]}

    expected_ids = {db_uuid_to_wire(r["id"], "request") for r in caller_rows}
    assert returned_ids == expected_ids

    # Explicitly assert the excluded rows are NOT present.
    assert db_uuid_to_wire(other_agent_same_tenant["id"], "request") not in returned_ids
    assert db_uuid_to_wire(other_tenant["id"], "request") not in returned_ids
    # Every returned row carries the required list fields.
    for r in body["requests"]:
        assert set(r) >= {"request_id", "kind", "status", "created_at", "expires_at"}


def test_list_my_requests_empty_when_caller_has_no_rows():
    """A caller with only other-agent / other-tenant rows in the store sees none."""
    store = [
        _seed_row(tenant_id=_TENANT_A, requesting_agent_id=_AGENT_A2, kind="access"),
        _seed_row(tenant_id=_TENANT_B, requesting_agent_id=_AGENT_B, kind="share"),
    ]
    app, _captured = _build_app(list_store=store)

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(
                "/v1/tools/list_my_requests",
                headers={"Authorization": "Bearer mk_agent_test"},
            )

    resp = _run(_inner())
    assert resp.status_code == 200, resp.text
    assert resp.json()["requests"] == []


def test_list_my_requests_unauthenticated_returns_401():
    """list_my_requests returns 401 when no agent context is present."""
    import mcp_server.main as _main_mod
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _no_ctx():
        return None

    app.dependency_overrides[get_agent_context] = _no_ctx

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/v1/tools/list_my_requests")

    resp = _run(_inner())
    assert resp.status_code == 401
