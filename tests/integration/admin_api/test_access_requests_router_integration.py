"""
Integration tests (HTTP-through-the-router) for the agent-access-requests
router — Task 6.3.

This is an ADD-ONLY test file. It modifies neither the app code nor any
existing test (Req 14.2). It exercises the FIVE operator-facing REST endpoints
of ``apps/admin-api/src/admin_api/api/access_requests.py`` through the real
FastAPI ``TestClient`` (``admin_app`` fixture) against a real PostgreSQL 16
testcontainer with the real Liquibase changelogs applied (changeset 030
present) — never a stub or mock DB, per AGENTS.md Principle 1 (validate against
the real schema).

Three concerns are covered (T-6.3):

  1. AUTH (Req 5.2, 5.3, 12.3) — operator-session enforcement per ADR-0019.
     The admin-api enforces the operator identity via the ``mintkey_session``
     cookie (``require_tenant_session`` / ``get_session_context``); the effective
     tenant scope and audit ``actor_id`` are derived from the SESSION, never from
     a request body (ADR-0019). The signed-request JWT (``AdminUiSignedRequest``)
     is verified in the AdminJS BFF layer (admin-ui), not admin-api, so the
     enforceable auth surface at this layer is the session cookie:
       (a) valid session (tenant matches path) → authorized;
       (b) MISSING session cookie on a POST → 401, no state change;
       (c) session scoped to a DIFFERENT tenant than the path (the concrete
           "claims disagree — tnt mismatch" case at this layer) → 403, no state
           change, and a cross-tenant ``request_id`` is invisible → 404.
     Every unauthorized case asserts the request row is UNCHANGED and no grant
     was created.

  2. CHANGE-CHANNEL (Req 5.7, 7.2, 7.6) — approving an access request publishes
     a grant change on the GLOBAL ``mintkey:agent`` channel (ADR-0010,
     ADR-0014.1 — global channel, tenant filter in the wrapper) observable within
     5s by a psycopg2 LISTEN subscriber; a subsequent revoke of that grant (via
     the existing permissions DELETE endpoint) publishes ``agent.permission.
     revoked`` on the same channel within 5s.

  3. CONNECTION_TEST (Req 6.3, 6.4) — ``POST .../{request_id}/test`` against a
     local stub upstream returns: ``ok`` for a healthy 2xx; a 401 surfaced as a
     fail/diagnostic (never a raised error); and a handshake timeout surfaced as
     ``ok:false`` with a timeout diagnostic. NO secret material appears in any
     diagnostic. The 10s ceiling is asserted WITHOUT literally waiting >10s by
     shrinking the module timeout constant for the timeout case only.

If Docker / testcontainers is unavailable the DB-backed tests skip gracefully,
matching the repo's skip conventions. The stub-upstream cases additionally skip
if the local HTTP stub cannot bind.

Source: T-6.3; design §Components (Admin API router) / §Sequence; requirements
        Req 5.2, 5.3, 5.7, 6.3, 6.4, 7.2, 7.6; ADR-0008 (tenant GUC),
        ADR-0010 / ADR-0014.1 (global change channel), ADR-0017.11 (prefixed
        ULID), ADR-0019 (session identity), ADR-0007 (egress allowlist).
"""
from __future__ import annotations

import json
import socket
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from starlette.testclient import TestClient

try:  # pragma: no cover - import guard mirrors repo skip conventions
    import psycopg2  # noqa: F401
    import psycopg2.extensions  # noqa: F401

    _PSYCOPG2 = True
except Exception:  # pragma: no cover
    _PSYCOPG2 = False

from admin_api.services.access_requests import (
    _new_request_id,
    _request_wire_to_uuid,
)

pytestmark = pytest.mark.skipif(not _PSYCOPG2, reason="psycopg2 unavailable")

# ---------------------------------------------------------------------------
# CSRF helpers (same pattern as test_permissions.py / test_services.py). The
# CsrfMiddleware requires the header+cookie double-submit; the session cookie is
# layered on top per-request.
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-token-arp-router"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}

_UTC = timezone.utc


def _post(client: TestClient, url: str, *, session_id: str | None = None, **kwargs):
    """POST with CSRF double-submit and (optionally) a mintkey_session cookie."""
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    if session_id is not None:
        cookies["mintkey_session"] = session_id
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


def _delete(client: TestClient, url: str, *, session_id: str | None = None, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    if session_id is not None:
        cookies["mintkey_session"] = session_id
    return client.delete(url, headers=headers, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# psycopg2 seeding helpers (same shape as test_permissions.py / test_services.py)
# ---------------------------------------------------------------------------


def _conn(postgres_container):  # type: ignore[no-untyped-def]
    import psycopg2

    return psycopg2.connect(
        host=postgres_container.get_container_host_ip(),
        port=postgres_container.get_exposed_port(5432),
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )


def _exec(postgres_container, sql: str, params: tuple = ()) -> None:  # type: ignore[no-untyped-def]
    conn = _conn(postgres_container)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        conn.commit()
    finally:
        conn.close()


def _scalar(postgres_container, sql: str, params: tuple = ()):  # type: ignore[no-untyped-def]
    conn = _conn(postgres_container)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        row = cur.fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _fetchone(postgres_container, sql: str, params: tuple = ()):  # type: ignore[no-untyped-def]
    conn = _conn(postgres_container)
    try:
        cur = conn.cursor()
        cur.execute(sql, params)
        return cur.fetchone()
    finally:
        conn.close()


def _insert_tenant(postgres_container, slug: str) -> str:  # type: ignore[no-untyped-def]
    tid = str(uuid.uuid4())
    _exec(
        postgres_container,
        "INSERT INTO tenants (id, slug, display_name, isolation_mode, status)"
        " VALUES (%s, %s, %s, 'row', 'active')",
        (tid, slug, slug),
    )
    return tid


def _insert_operator_and_session(  # type: ignore[no-untyped-def]
    postgres_container, tenant_id: str, *, is_platform_admin: bool = False
) -> tuple[str, str]:
    """Insert an operator + a live session row; return (operator_id, session_id).

    Mirrors ``_seed_authz_operator_and_session`` in test_services.py — the
    session_id is the ``mintkey_session`` cookie value ``validate_session`` will
    accept, and its ``tenant_id`` is what ``require_tenant_session`` compares to
    the path tenant.
    """
    operator_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    expires_at = datetime.now(_UTC) + timedelta(hours=8)
    conn = _conn(postgres_container)
    conn.autocommit = False
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT set_config('app.current_tenant', %s, false)", (tenant_id,))
            cur.execute("SELECT set_config('app.platform_admin_view', 'on', false)")
            cur.execute(
                "INSERT INTO operators"
                " (id, tenant_id, email, display_name, internal_password_hash,"
                "  is_platform_admin, status, created_at)"
                " VALUES (%s, %s, %s, %s, NULL, %s, 'active', now())",
                (
                    operator_id,
                    tenant_id,
                    f"arp-router-{operator_id[:8]}@mintkey.internal",
                    f"arp-router-{operator_id[:8]}",
                    is_platform_admin,
                ),
            )
            cur.execute(
                "INSERT INTO sessions"
                " (id, tenant_id, operator_id, expires_at, last_used_at, created_at, auth_method)"
                " VALUES (%s, %s, %s, %s, now(), now(), 'internal')",
                (session_id, tenant_id, operator_id, expires_at),
            )
        conn.commit()
    finally:
        conn.close()
    return operator_id, session_id


def _insert_agent(postgres_container, tenant_id: str, name: str) -> str:  # type: ignore[no-untyped-def]
    import hashlib
    import secrets

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


def _insert_service(postgres_container, tenant_id: str, slug: str, base_url: str) -> str:  # type: ignore[no-untyped-def]
    sid = str(uuid.uuid4())
    _exec(
        postgres_container,
        "INSERT INTO services"
        " (id, tenant_id, name, slug, display_name, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, 'bearer_token', 'active')",
        (sid, tenant_id, slug, slug, slug, base_url),
    )
    return sid


def _seed_access_request(  # type: ignore[no-untyped-def]
    postgres_container,
    *,
    tenant_id: str,
    kind: str,
    status: str,
    requesting_agent_id: str,
    service_id: str | None = None,
    action: str | None = None,
    target_agent_id: str | None = None,
    share_direction: str | None = None,
    proposed_config: dict | None = None,
    expires_at: datetime | None = None,
) -> str:
    """INSERT one access_requests row with a fresh decodable ``request_`` id.

    Uses the module's own ``_new_request_id`` + ``_request_wire_to_uuid`` so the
    returned wire id decodes to the stored PK (ADR-0017.11), exactly like the
    property-test seeding helpers.
    """
    wire_id = _new_request_id()
    row_uuid = _request_wire_to_uuid(wire_id)
    now = datetime.now(_UTC)
    exp = expires_at or (now + timedelta(days=30))
    _exec(
        postgres_container,
        "INSERT INTO access_requests"
        " (id, tenant_id, kind, status, requesting_agent_id, service_id, action,"
        "  target_agent_id, share_direction, proposed_config, reason,"
        "  expires_at, created_at, created_by)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, CAST(%s AS jsonb), NULL,"
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
            exp,
            now,
            requesting_agent_id,
        ),
    )
    return wire_id


def _request_status(postgres_container, tenant_id: str, wire_id: str):  # type: ignore[no-untyped-def]
    row_uuid = _request_wire_to_uuid(wire_id)
    row = _fetchone(
        postgres_container,
        "SELECT status FROM access_requests WHERE id = %s AND tenant_id = %s",
        (str(row_uuid), tenant_id),
    )
    return row[0] if row else None


def _grant_count(postgres_container, tenant_id, agent_id, service_id, action) -> int:  # type: ignore[no-untyped-def]
    return int(
        _scalar(
            postgres_container,
            "SELECT count(*) FROM permission_grants"
            " WHERE tenant_id = %s AND agent_id = %s AND service_id = %s AND action = %s",
            (tenant_id, agent_id, service_id, action),
        )
    )


# ===========================================================================
# 1. AUTH — operator-session enforcement (Req 5.2, 5.3, 12.3; ADR-0019)
# ===========================================================================


@pytest.fixture(scope="module")
def auth_ctx(admin_app: TestClient, apply_migrations, postgres_container):  # type: ignore[no-untyped-def]
    """Seed tenant A + tenant B, an operator/session in each, an agent + service
    in A, and a pending ACCESS request in A. Returns the wired ids/cookies."""
    tenant_a = _insert_tenant(postgres_container, f"arp-auth-a-{uuid.uuid4().hex[:8]}")
    tenant_b = _insert_tenant(postgres_container, f"arp-auth-b-{uuid.uuid4().hex[:8]}")
    _, session_a = _insert_operator_and_session(postgres_container, tenant_a)
    _, session_b = _insert_operator_and_session(postgres_container, tenant_b)

    agent_a = _insert_agent(postgres_container, tenant_a, "arp-auth-agent")
    service_a = _insert_service(
        postgres_container, tenant_a, "arp-auth-svc", "https://api.example.com"
    )
    action = "invoke-auth-" + uuid.uuid4().hex[:6]
    req_id = _seed_access_request(
        postgres_container,
        tenant_id=tenant_a,
        kind="access",
        status="pending",
        requesting_agent_id=agent_a,
        service_id=service_a,
        action=action,
    )
    return {
        "tenant_a": tenant_a,
        "tenant_b": tenant_b,
        "session_a": session_a,
        "session_b": session_b,
        "agent_a": agent_a,
        "service_a": service_a,
        "action": action,
        "request_id": req_id,
    }


def test_approve_with_valid_session_is_authorized(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, auth_ctx
) -> None:
    """(a) valid session whose tenant matches the path → authorized: the request
    is approved and exactly one grant is created (Req 5.1, 5.2)."""
    tenant_a = auth_ctx["tenant_a"]
    req_id = auth_ctx["request_id"]
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_a}/access-requests/{req_id}/approve",
        session_id=auth_ctx["session_a"],
        json={},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["request_id"] == req_id
    assert body["status"] == "approved"
    # Exactly one grant for the requesting agent on (service, action).
    assert (
        _grant_count(
            postgres_container,
            tenant_a,
            auth_ctx["agent_a"],
            auth_ctx["service_a"],
            auth_ctx["action"],
        )
        == 1
    )


def test_approve_missing_session_is_unauthorized_no_change(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, auth_ctx
) -> None:
    """(b) MISSING session cookie on a POST → 401; the request row is unchanged
    and no grant is created (Req 5.2)."""
    tenant_a = auth_ctx["tenant_a"]
    agent_a = auth_ctx["agent_a"]
    service_a = auth_ctx["service_a"]
    action = "invoke-noauth-" + uuid.uuid4().hex[:6]
    req_id = _seed_access_request(
        postgres_container,
        tenant_id=tenant_a,
        kind="access",
        status="pending",
        requesting_agent_id=agent_a,
        service_id=service_a,
        action=action,
    )
    before_grants = _grant_count(postgres_container, tenant_a, agent_a, service_a, action)

    # No session_id passed → no mintkey_session cookie.
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_a}/access-requests/{req_id}/approve",
        json={},
    )
    assert resp.status_code == 401, resp.text

    # Row unchanged; no grant created.
    assert _request_status(postgres_container, tenant_a, req_id) == "pending"
    assert _grant_count(postgres_container, tenant_a, agent_a, service_a, action) == before_grants


def test_approve_cross_tenant_session_is_unauthorized_no_change(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, auth_ctx
) -> None:
    """(d) a session scoped to a DIFFERENT tenant than the path (the tnt-mismatch
    case at this layer) → 403; the request row is unchanged and no grant is
    created (Req 5.2, 12.3)."""
    tenant_a = auth_ctx["tenant_a"]
    agent_a = auth_ctx["agent_a"]
    service_a = auth_ctx["service_a"]
    action = "invoke-xtenant-" + uuid.uuid4().hex[:6]
    req_id = _seed_access_request(
        postgres_container,
        tenant_id=tenant_a,
        kind="access",
        status="pending",
        requesting_agent_id=agent_a,
        service_id=service_a,
        action=action,
    )
    before_grants = _grant_count(postgres_container, tenant_a, agent_a, service_a, action)

    # Tenant-B session against a Tenant-A path → session tenant != path tenant.
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_a}/access-requests/{req_id}/approve",
        session_id=auth_ctx["session_b"],
        json={},
    )
    assert resp.status_code == 403, resp.text

    # Row unchanged; no grant created.
    assert _request_status(postgres_container, tenant_a, req_id) == "pending"
    assert _grant_count(postgres_container, tenant_a, agent_a, service_a, action) == before_grants


def test_reject_missing_session_is_unauthorized_no_change(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, auth_ctx
) -> None:
    """A reject POST without a session cookie → 401; the row stays pending with
    no reason recorded (Req 5.2, 8.x)."""
    tenant_a = auth_ctx["tenant_a"]
    agent_a = auth_ctx["agent_a"]
    service_a = auth_ctx["service_a"]
    action = "invoke-rej-noauth-" + uuid.uuid4().hex[:6]
    req_id = _seed_access_request(
        postgres_container,
        tenant_id=tenant_a,
        kind="access",
        status="pending",
        requesting_agent_id=agent_a,
        service_id=service_a,
        action=action,
    )
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant_a}/access-requests/{req_id}/reject",
        json={"reason": "should not apply"},
    )
    assert resp.status_code == 401, resp.text
    assert _request_status(postgres_container, tenant_a, req_id) == "pending"


def test_cross_tenant_request_id_is_invisible_404(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, auth_ctx
) -> None:
    """A ``request_id`` that exists only in tenant A is invisible when addressed
    under tenant B's own session+path → 404 request_not_found, without revealing
    cross-tenant existence (Req 4.4, 12.3)."""
    tenant_b = auth_ctx["tenant_b"]
    # A request that lives in tenant A.
    a_only = auth_ctx["request_id"]

    # Tenant B operator, tenant B path, but a tenant-A request id → not found.
    resp = admin_app.get(
        f"/v1/tenants/{tenant_b}/access-requests/{a_only}",
        cookies={"mintkey_session": auth_ctx["session_b"]},
    )
    assert resp.status_code == 404, resp.text
    assert resp.json().get("mintkey:code") == "request_not_found"


# ===========================================================================
# 2. CHANGE-CHANNEL — approve publishes grant change; revoke publishes revoked
#    (Req 5.7, 7.2, 7.6; ADR-0010 / ADR-0014.1 — GLOBAL mintkey:agent channel)
# ===========================================================================


def _listen_for_notify(postgres_container):  # type: ignore[no-untyped-def]
    """Open a dedicated psycopg2 connection LISTENing on ``mintkey:agent``.

    Autocommit mode is required for LISTEN/NOTIFY to deliver asynchronously. The
    channel is a fixed literal (``mintkey:agent``), not user input; it is quoted
    because of the ':' character. Returns the live connection so the caller can
    trigger the action and then poll for notifications up to a deadline.
    """
    import psycopg2
    import psycopg2.extensions

    conn = psycopg2.connect(
        host=postgres_container.get_container_host_ip(),
        port=postgres_container.get_exposed_port(5432),
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
    cur = conn.cursor()
    cur.execute('LISTEN "mintkey:agent"')
    return conn


def _collect_notifies(conn, *, timeout_s: float) -> list[dict]:  # type: ignore[no-untyped-def]
    """Poll a LISTENing connection for payloads until timeout_s elapses."""
    import select

    payloads: list[dict] = []
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        if select.select([conn], [], [], max(0.0, min(0.5, remaining))) == ([], [], []):
            conn.poll()
        conn.poll()
        while conn.notifies:
            note = conn.notifies.pop(0)
            try:
                payloads.append(json.loads(note.payload))
            except (ValueError, TypeError):
                payloads.append({"_raw": note.payload})
        if payloads:
            # Give a brief grace window for a second (revoke) notify if the
            # caller wants more than one; callers filter by event.
            break
    return payloads


@pytest.fixture(scope="module")
def chan_ctx(admin_app: TestClient, apply_migrations, postgres_container):  # type: ignore[no-untyped-def]
    """Seed a tenant + operator/session + agent + service + pending access
    request for the change-channel tests."""
    tenant = _insert_tenant(postgres_container, f"arp-chan-{uuid.uuid4().hex[:8]}")
    _, session_id = _insert_operator_and_session(postgres_container, tenant)
    agent = _insert_agent(postgres_container, tenant, "arp-chan-agent")
    service = _insert_service(
        postgres_container, tenant, "arp-chan-svc", "https://api.example.com"
    )
    return {
        "tenant": tenant,
        "session": session_id,
        "agent": agent,
        "service": service,
    }


def test_approve_publishes_grant_change_on_mintkey_agent(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, chan_ctx
) -> None:
    """Approving an access request publishes a grant change on the GLOBAL
    ``mintkey:agent`` channel, observable within 5s (Req 5.7, 7.2; P-9)."""
    tenant = chan_ctx["tenant"]
    agent = chan_ctx["agent"]
    service = chan_ctx["service"]
    action = "invoke-chan-appr-" + uuid.uuid4().hex[:6]
    req_id = _seed_access_request(
        postgres_container,
        tenant_id=tenant,
        kind="access",
        status="pending",
        requesting_agent_id=agent,
        service_id=service,
        action=action,
    )

    conn = _listen_for_notify(postgres_container)
    try:
        resp = _post(
            admin_app,
            f"/v1/tenants/{tenant}/access-requests/{req_id}/approve",
            session_id=chan_ctx["session"],
            json={},
        )
        assert resp.status_code == 200, resp.text
        payloads = _collect_notifies(conn, timeout_s=5.0)
    finally:
        conn.close()

    grant_events = [
        p
        for p in payloads
        if p.get("event") == "agent.permission.granted"
        and p.get("tenant_id") == tenant
        and p.get("action") == action
    ]
    assert grant_events, (
        f"expected an agent.permission.granted notify on mintkey:agent within 5s; "
        f"got {payloads}"
    )


def test_revoke_publishes_permission_revoked_on_mintkey_agent(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, chan_ctx
) -> None:
    """After approval creates a grant, revoking that grant via the permissions
    DELETE endpoint publishes ``agent.permission.revoked`` on ``mintkey:agent``
    within 5s (Req 7.6; P-9)."""
    tenant = chan_ctx["tenant"]
    agent = chan_ctx["agent"]
    service = chan_ctx["service"]
    action = "invoke-chan-rev-" + uuid.uuid4().hex[:6]
    req_id = _seed_access_request(
        postgres_container,
        tenant_id=tenant,
        kind="access",
        status="pending",
        requesting_agent_id=agent,
        service_id=service,
        action=action,
    )
    # Approve → creates the grant.
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant}/access-requests/{req_id}/approve",
        session_id=chan_ctx["session"],
        json={},
    )
    assert resp.status_code == 200, resp.text

    # Look up the created grant's internal DB id.
    perm_db_id = _scalar(
        postgres_container,
        "SELECT id FROM permission_grants"
        " WHERE tenant_id = %s AND agent_id = %s AND service_id = %s AND action = %s",
        (tenant, agent, service, action),
    )
    assert perm_db_id is not None, "approval must have created a grant row"

    conn = _listen_for_notify(postgres_container)
    try:
        del_resp = _delete(
            admin_app,
            f"/v1/tenants/{tenant}/agents/{agent}/permissions/{perm_db_id}",
            session_id=chan_ctx["session"],
        )
        assert del_resp.status_code == 204, del_resp.text
        payloads = _collect_notifies(conn, timeout_s=5.0)
    finally:
        conn.close()

    revoked_events = [
        p
        for p in payloads
        if p.get("event") == "agent.permission.revoked"
        and p.get("tenant_id") == tenant
    ]
    assert revoked_events, (
        f"expected an agent.permission.revoked notify on mintkey:agent within 5s; "
        f"got {payloads}"
    )


# ===========================================================================
# 3. CONNECTION_TEST — pass / 401 / timeout against a stub upstream
#    (Req 6.3, 6.4; no secret in any diagnostic; P-1)
# ===========================================================================

# The operator-supplied secret used across the Connection_Test cases. It must
# NOT appear in any returned diagnostic (Req 6.3, P-1).
_CANARY_SECRET = "canary-bearer-secret-DO-NOT-LEAK-1234567890"


class _StubHandler(BaseHTTPRequestHandler):
    """A tiny stub upstream. Path controls behavior:

      /ok      → 200 (healthy handshake)
      /unauth  → 401 (surfaced as a fail/diagnostic, not an exception)
      anything else → 200 (default health path also 200)
    """

    def log_message(self, *_args) -> None:  # noqa: D401 - silence stub logging
        return

    def _respond(self) -> None:
        if self.path.startswith("/unauth"):
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'{"error":"unauthorized"}')
            return
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'{"status":"ok"}')

    def do_GET(self) -> None:  # noqa: N802 - http.server API
        self._respond()

    def do_POST(self) -> None:  # noqa: N802
        self._respond()


@pytest.fixture(scope="module")
def stub_upstream():  # type: ignore[no-untyped-def]
    """Start a local HTTP stub upstream on an ephemeral port; yield its base URL."""
    try:
        server = ThreadingHTTPServer(("127.0.0.1", 0), _StubHandler)
    except OSError as exc:  # pragma: no cover - environment can't bind
        pytest.skip(f"cannot bind local stub upstream: {exc}")
    host, port = server.server_address[0], server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://{host}:{port}"
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture()
def _allow_private_ssrf(monkeypatch):  # type: ignore[no-untyped-def]
    """Opt out of the private-IP SSRF block so the localhost stub is reachable.

    ``_is_forbidden_destination`` reads ``MINTKEY_SSRF_ALLOW_PRIVATE`` from the
    environment at call time (ADR-0007 dev opt-out), so setting it here makes the
    127.0.0.1 stub a permitted destination for the duration of the test only.
    """
    monkeypatch.setenv("MINTKEY_SSRF_ALLOW_PRIVATE", "1")
    yield


@pytest.fixture(scope="module")
def test_ctx(admin_app: TestClient, apply_migrations, postgres_container):  # type: ignore[no-untyped-def]
    """Seed a tenant + operator/session + agent for the Connection_Test cases."""
    tenant = _insert_tenant(postgres_container, f"arp-test-{uuid.uuid4().hex[:8]}")
    _, session_id = _insert_operator_and_session(postgres_container, tenant)
    agent = _insert_agent(postgres_container, tenant, "arp-test-agent")
    return {"tenant": tenant, "session": session_id, "agent": agent}


def _seed_integration_proposal(  # type: ignore[no-untyped-def]
    postgres_container, tenant: str, agent: str, base_url: str
) -> str:
    return _seed_access_request(
        postgres_container,
        tenant_id=tenant,
        kind="integration",
        status="pending",
        requesting_agent_id=agent,
        proposed_config={
            "name": "arp-conn-test-" + uuid.uuid4().hex[:6],
            "base_url": base_url,
            "auth_scheme": "bearer_token",
        },
    )


def _diagnostic_has_no_secret(body: dict) -> None:
    """Assert the canary secret appears in no field of the test response."""
    blob = json.dumps(body)
    assert _CANARY_SECRET not in blob, f"secret leaked into diagnostic: {body}"


def test_connection_test_pass_for_2xx(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, test_ctx, stub_upstream, _allow_private_ssrf
) -> None:
    """A healthy 2xx upstream → ok:true; no secret in the diagnostic (Req 6.3)."""
    tenant = test_ctx["tenant"]
    req_id = _seed_integration_proposal(
        postgres_container, tenant, test_ctx["agent"], stub_upstream
    )
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant}/access-requests/{req_id}/test",
        session_id=test_ctx["session"],
        json={
            "credential": {"credential_value": _CANARY_SECRET},
            "config": {"base_url": stub_upstream + "/ok"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True, f"expected ok=true for a 2xx upstream; got {body}"
    _diagnostic_has_no_secret(body)


def test_connection_test_401_surfaced_as_fail(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, test_ctx, stub_upstream, _allow_private_ssrf
) -> None:
    """A 401 upstream is surfaced as a fail/diagnostic (ok:false), never a raised
    error; no secret in the diagnostic (Req 6.3)."""
    tenant = test_ctx["tenant"]
    req_id = _seed_integration_proposal(
        postgres_container, tenant, test_ctx["agent"], stub_upstream
    )
    resp = _post(
        admin_app,
        f"/v1/tenants/{tenant}/access-requests/{req_id}/test",
        session_id=test_ctx["session"],
        json={
            "credential": {"credential_value": _CANARY_SECRET},
            "config": {"base_url": stub_upstream + "/unauth"},
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False, f"expected ok=false for a 401 upstream; got {body}"
    # The 401 is surfaced as a diagnostic/status, not an exception.
    assert body.get("status_code") == 401 or body.get("response_body_truncated"), body
    _diagnostic_has_no_secret(body)


def test_connection_test_timeout_surfaced_as_ok_false(  # type: ignore[no-untyped-def]
    admin_app: TestClient, postgres_container, test_ctx, monkeypatch, _allow_private_ssrf
) -> None:
    """A handshake that exceeds the (bounded) timeout is surfaced as ok:false with
    a timeout diagnostic — never a raised error; no secret in the diagnostic
    (Req 6.4). The 10s ceiling is asserted WITHOUT waiting 10s by shrinking the
    module timeout constant and dialling a blackhole address that never responds.
    """
    from admin_api.services import access_requests as svc

    # Shrink the Connection_Test ceiling for this case only so we assert the
    # timeout path bounded (~1s) rather than literally waiting >10s. The service
    # wraps the handshake in asyncio.wait_for(..., CONNECTION_TEST_TIMEOUT_S).
    monkeypatch.setattr(svc, "CONNECTION_TEST_TIMEOUT_S", 1.0)

    # A blackhole endpoint: bind a socket and never accept, so the TCP connect
    # hangs past the shrunk ceiling. 127.0.0.1:1 is reserved and refuses fast on
    # some OSes, so use a bound-but-non-accepting socket for a true hang.
    blackhole = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    blackhole.bind(("127.0.0.1", 0))
    # Deliberately do NOT call listen()/accept() beyond the backlog so connects
    # stall; a tiny backlog + no accept produces a hang for the test's connect.
    blackhole.listen(0)
    bh_host, bh_port = blackhole.getsockname()
    blackhole_url = f"http://{bh_host}:{bh_port}"

    tenant = test_ctx["tenant"]
    req_id = _seed_integration_proposal(
        postgres_container, tenant, test_ctx["agent"], blackhole_url
    )
    try:
        resp = _post(
            admin_app,
            f"/v1/tenants/{tenant}/access-requests/{req_id}/test",
            session_id=test_ctx["session"],
            json={
                "credential": {"credential_value": _CANARY_SECRET},
                "config": {"base_url": blackhole_url},
            },
        )
    finally:
        blackhole.close()

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False, f"expected ok=false on timeout; got {body}"
    # The diagnostic must indicate a timeout and carry no secret.
    diag = (body.get("response_body_truncated") or "") + " " + str(body.get("error") or "")
    assert "timeout" in diag.lower() or body.get("error") == "timeout", (
        f"expected a timeout diagnostic; got {body}"
    )
    _diagnostic_has_no_secret(body)
