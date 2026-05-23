"""
Integration tests for /v1/internal/audit/emit rate limiting (#26).

Uses the real FastAPI TestClient with the testcontainer Postgres DB.
The rate limiter is injected fresh per test via dependency override so
state does not leak between test functions.

Time notes
----------
The _TokenBucket uses time.monotonic() for timestamp-based refill.  When
100 synchronous HTTP requests go through the TestClient they take real wall
time (~10-100 ms total), so at 100 rps ~1-10 tokens would refill during the
drain loop and the 101st request would slip through.

To make tests deterministic without sleeping we freeze time.monotonic inside
the rate-limiter module.  For tests that validate refill behaviour we advance
the frozen clock explicitly.

Test cases:
  1. test_100_requests_all_succeed       — burst of 100 allowed (time frozen)
  2. test_101st_returns_429              — 101st in same "instant" denied
  3. test_retry_after_header_present     — 429 includes Retry-After: 1
  4. test_refill_allows_after_idle       — advancing the clock allows 50 more
  5. test_independent_tokens             — exhausted token doesn't block another
  6. test_unauthenticated_still_401      — missing token → 401 not 429
  7. test_wrong_token_still_401          — bad token → 401 not 429

Source: #26 — rate-limit /v1/internal/audit/emit.
"""
from __future__ import annotations

import os
import sys
import time
import uuid
from contextlib import contextmanager
from unittest.mock import patch

import psycopg2
import pytest
from starlette.testclient import TestClient

# Ensure source trees on sys.path (mirrors conftest pattern).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
for _src in (
    os.path.join(_REPO_ROOT, "apps/admin-api", "src"),
    os.path.join(_REPO_ROOT, "packages/python/mintkey-models"),
):
    if _src not in sys.path:
        sys.path.insert(0, _src)

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_TOKEN_A = "mk_svctoken_test_rate_limit_aaa111"
_TOKEN_B = "mk_svctoken_test_rate_limit_bbb222"
_EMIT_URL = "/v1/internal/audit/emit"

# Minimal valid emit body — actor_id is null so cross-tenant check is skipped.
_SYSTEM_TENANT = "00000000-0000-0000-0000-000000000099"


def _emit_body(tenant_id: str = _SYSTEM_TENANT) -> dict:
    return {
        "event_type": "token.issued",
        "tenant_id": tenant_id,
        "actor_id": None,
        "actor_type": "system",
        "target_id": str(uuid.uuid4()),
        "target_type": "token",
        "payload": {},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_tenant(postgres_container, slug: str) -> str:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    cur = conn.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO tenants (slug, display_name, isolation_mode, status)"
            " VALUES (%s, %s, 'row', 'active') RETURNING id",
            (slug, slug),
        )
        conn.commit()
        row = cur.fetchone()
    else:
        conn.commit()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0])


# ---------------------------------------------------------------------------
# Frozen-clock context manager
# ---------------------------------------------------------------------------

class _FrozenClock:
    """
    A mutable clock whose value is controlled by the test.

    Pass to patch('admin_api.services.audit_emit_rate_limiter.time') so the
    token bucket sees a deterministic monotonic() value.  Advancing .now
    simulates idle time.
    """

    def __init__(self, start: float) -> None:
        self.now = start

    def monotonic(self) -> float:
        return self.now


@contextmanager
def frozen_time(start: float = 1_000_000.0):
    """
    Context manager: freeze time.monotonic inside the rate-limiter module.
    Yields the _FrozenClock so the test can advance it.
    """
    clock = _FrozenClock(start)
    with patch(
        "admin_api.services.audit_emit_rate_limiter.time",
        new=clock,
    ):
        yield clock


# ---------------------------------------------------------------------------
# Fresh-limiter fixture — guarantees test isolation
# ---------------------------------------------------------------------------


@pytest.fixture()
def rate_limited_app(admin_app: TestClient, monkeypatch) -> TestClient:
    """
    Override the rate-limiter dependency with a fresh AuditEmitRateLimiter
    (rps=100) and patch the service-token allowlist to accept _TOKEN_A and
    _TOKEN_B.  State does not persist between test functions.
    """
    from admin_api.services.audit_emit_rate_limiter import AuditEmitRateLimiter
    from admin_api.services.audit_emit_rate_limiter import get_rate_limiter

    # Inject env vars so the token allowlist accepts our test tokens.
    monkeypatch.setenv("MINTKEY_BROKER_SERVICE_TOKEN", _TOKEN_A)
    monkeypatch.setenv("MINTKEY_PROXY_SERVICE_TOKEN", _TOKEN_B)
    monkeypatch.setenv("MINTKEY_MCP_SERVICE_TOKEN", "")

    fresh_limiter = AuditEmitRateLimiter(rps=100)
    admin_app.app.dependency_overrides[get_rate_limiter] = lambda: fresh_limiter  # type: ignore[attr-defined]
    yield admin_app
    admin_app.app.dependency_overrides.pop(get_rate_limiter, None)  # type: ignore[attr-defined]


@pytest.fixture()
def emit_tenant(rate_limited_app: TestClient, postgres_container) -> str:
    """Insert a tenant used as the emit target."""
    return _insert_tenant(postgres_container, "rate-limit-test-tenant")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_100_requests_all_succeed(
    rate_limited_app: TestClient,
    emit_tenant: str,
) -> None:
    """
    The first 100 emits with a valid token must all return 200.

    Time is frozen so no tokens refill between requests — this confirms the
    burst capacity is exactly 100.
    """
    with frozen_time():
        for i in range(100):
            resp = rate_limited_app.post(
                _EMIT_URL,
                json=_emit_body(emit_tenant),
                headers={"X-Mintkey-Service-Token": _TOKEN_A},
            )
            assert resp.status_code == 200, (
                f"Request {i + 1}/100 should be 200 OK, got {resp.status_code}: {resp.text}"
            )


def test_101st_returns_429(
    rate_limited_app: TestClient,
    emit_tenant: str,
) -> None:
    """
    After 100 rapid emits (frozen time) the 101st must return HTTP 429.
    """
    with frozen_time():
        for _ in range(100):
            rate_limited_app.post(
                _EMIT_URL,
                json=_emit_body(emit_tenant),
                headers={"X-Mintkey-Service-Token": _TOKEN_A},
            )
        resp = rate_limited_app.post(
            _EMIT_URL,
            json=_emit_body(emit_tenant),
            headers={"X-Mintkey-Service-Token": _TOKEN_A},
        )
    assert resp.status_code == 429, (
        f"101st request should be rate-limited (429), got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert body.get("mintkey:code") == "rate_limited"
    assert "title" in body


def test_retry_after_header_present(
    rate_limited_app: TestClient,
    emit_tenant: str,
) -> None:
    """A 429 response must include Retry-After: 1."""
    with frozen_time():
        for _ in range(100):
            rate_limited_app.post(
                _EMIT_URL,
                json=_emit_body(emit_tenant),
                headers={"X-Mintkey-Service-Token": _TOKEN_A},
            )
        resp = rate_limited_app.post(
            _EMIT_URL,
            json=_emit_body(emit_tenant),
            headers={"X-Mintkey-Service-Token": _TOKEN_A},
        )
    assert resp.status_code == 429
    assert resp.headers.get("retry-after") == "1", (
        f"Expected Retry-After: 1, got {resp.headers.get('retry-after')!r}"
    )


def test_refill_allows_after_idle(
    rate_limited_app: TestClient,
    emit_tenant: str,
) -> None:
    """
    After exhausting the bucket, advancing the frozen clock by 0.5 s adds
    50 tokens (0.5 × 100 rps).  50 further requests must all succeed.
    """
    with frozen_time(start=1_000_000.0) as clock:
        # Drain.
        for _ in range(100):
            rate_limited_app.post(
                _EMIT_URL,
                json=_emit_body(emit_tenant),
                headers={"X-Mintkey-Service-Token": _TOKEN_A},
            )
        # Confirm exhausted.
        resp = rate_limited_app.post(
            _EMIT_URL,
            json=_emit_body(emit_tenant),
            headers={"X-Mintkey-Service-Token": _TOKEN_A},
        )
        assert resp.status_code == 429, "bucket should be empty after drain"

        # Advance the frozen clock by 0.5 s → 50 tokens refill.
        clock.now += 0.5

        # 50 more requests should succeed.
        for i in range(50):
            resp = rate_limited_app.post(
                _EMIT_URL,
                json=_emit_body(emit_tenant),
                headers={"X-Mintkey-Service-Token": _TOKEN_A},
            )
            assert resp.status_code == 200, (
                f"Post-refill request {i + 1}/50 should be 200, got {resp.status_code}"
            )

        # 51st post-refill request must be denied again (frozen time, no more refill).
        resp = rate_limited_app.post(
            _EMIT_URL,
            json=_emit_body(emit_tenant),
            headers={"X-Mintkey-Service-Token": _TOKEN_A},
        )
        assert resp.status_code == 429, (
            f"51st post-refill request should be 429, got {resp.status_code}"
        )


def test_independent_tokens(
    rate_limited_app: TestClient,
    emit_tenant: str,
) -> None:
    """
    Exhausting TOKEN_A's bucket must not affect TOKEN_B.
    """
    with frozen_time():
        # Drain TOKEN_A.
        for _ in range(100):
            rate_limited_app.post(
                _EMIT_URL,
                json=_emit_body(emit_tenant),
                headers={"X-Mintkey-Service-Token": _TOKEN_A},
            )
        # Verify TOKEN_A is exhausted.
        resp_a = rate_limited_app.post(
            _EMIT_URL,
            json=_emit_body(emit_tenant),
            headers={"X-Mintkey-Service-Token": _TOKEN_A},
        )
        assert resp_a.status_code == 429

        # TOKEN_B should still have a full bucket.
        for i in range(10):
            resp_b = rate_limited_app.post(
                _EMIT_URL,
                json=_emit_body(emit_tenant),
                headers={"X-Mintkey-Service-Token": _TOKEN_B},
            )
            assert resp_b.status_code == 200, (
                f"TOKEN_B request {i + 1}/10 should be 200, got {resp_b.status_code}"
            )


def test_unauthenticated_still_401(
    rate_limited_app: TestClient,
    emit_tenant: str,
) -> None:
    """
    A request with no service token must receive 401, not 429.
    Rate limiting must only apply AFTER authentication.
    """
    resp = rate_limited_app.post(
        _EMIT_URL,
        json=_emit_body(emit_tenant),
    )
    assert resp.status_code == 401, (
        f"Missing token should be 401, got {resp.status_code}: {resp.text}"
    )


def test_wrong_token_still_401(
    rate_limited_app: TestClient,
    emit_tenant: str,
) -> None:
    """
    A request with an unrecognised service token must receive 401, not 429.
    """
    resp = rate_limited_app.post(
        _EMIT_URL,
        json=_emit_body(emit_tenant),
        headers={"X-Mintkey-Service-Token": "mk_svctoken_not_registered"},
    )
    assert resp.status_code == 401, (
        f"Wrong token should be 401, got {resp.status_code}: {resp.text}"
    )
