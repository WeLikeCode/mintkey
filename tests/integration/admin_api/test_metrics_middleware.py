"""
Integration tests for the metrics middleware — OPS-N.

Verifies that MetricsMiddleware correctly populates:
  - mintkey_requests_total{method,path,status}  after real HTTP traffic
  - mintkey_audit_events_total                  after an audit-emitting endpoint

Strategy:
  - Use the shared `admin_app` TestClient (real Postgres + Liquibase).
  - Hit GET /v1/health 5 times, then inspect GET /metrics output.
  - Create a service (triggers audit_emit), then verify mintkey_audit_events_total.

Notes on prometheus_client in-process test isolation:
  - The REGISTRY is a module-level singleton shared across all test modules in
    the same pytest process. Counters are monotonically increasing and their
    values persist between test functions.
  - We therefore assert count >= N (not == N) to be robust against test order
    and against counters incremented by other test modules in the same run.

Source: OPS-N; T-1.10.2; design §4.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# CSRF helpers — double-submit cookie pattern (mirrors test_services.py)
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-token-metrics"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}


def _post(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _insert_tenant(postgres_container, slug: str) -> str:
    import psycopg2

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
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def metrics_tenant_uuid(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "test-metrics-tenant")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_health_hits_increment_requests_total(admin_app: TestClient) -> None:
    """
    Hit GET /v1/health 5 times, then assert mintkey_requests_total contains
    a line for method=GET, path=/v1/health, status=200 with count >= 5.
    """
    for _ in range(5):
        r = admin_app.get("/v1/health")
        assert r.status_code == 200

    metrics_resp = admin_app.get("/metrics")
    assert metrics_resp.status_code == 200

    body = metrics_resp.text

    # Prometheus text exposition format:
    # mintkey_requests_total{method="GET",path="/v1/health",status="200"} <N>
    # Labels can appear in any order, so we check for the metric name + key labels.
    assert "mintkey_requests_total" in body, (
        "mintkey_requests_total not found in /metrics output — middleware may not be wired"
    )

    # Find the specific label combination.  Prometheus sorts labels alphabetically,
    # so the order is: method, path, status.
    target_line = None
    for line in body.splitlines():
        if (
            line.startswith("mintkey_requests_total{")
            and 'method="GET"' in line
            and 'path="/v1/health"' in line
            and 'status="200"' in line
        ):
            target_line = line
            break

    assert target_line is not None, (
        f'Expected mintkey_requests_total{{method="GET",path="/v1/health",status="200"}} '
        f"in /metrics; full output:\n{body}"
    )

    # Extract the float value from the end of the line.
    count = float(target_line.split()[-1])
    assert count >= 5, (
        f"Expected count >= 5 for /v1/health GET 200 requests, got {count}"
    )


def test_audit_emit_increments_audit_events_total(
    admin_app: TestClient,
    metrics_tenant_uuid: str,
) -> None:
    """
    Creating a service triggers audit_emit() → mintkey_audit_events_total must
    be present in /metrics output and its value must be >= 1.
    """
    # Snapshot current value (may be > 0 if other test modules ran first)
    metrics_before = admin_app.get("/metrics").text
    before_count = _extract_audit_events_total(metrics_before)

    # Create a service → triggers audit_emit() → counter incremented
    resp = _post(
        admin_app,
        f"/v1/tenants/{metrics_tenant_uuid}/services",
        json={
            "name": "metrics-audit-svc",
            "base_url": "https://metrics-example.com/api",
            "auth_scheme": "bearer_token",
        },
    )
    assert resp.status_code == 201, f"Service creation failed: {resp.text}"

    metrics_after = admin_app.get("/metrics").text
    after_count = _extract_audit_events_total(metrics_after)

    assert "mintkey_audit_events_total" in metrics_after, (
        "mintkey_audit_events_total not found in /metrics — audit.py counter may not be wired"
    )
    assert after_count > before_count, (
        f"mintkey_audit_events_total did not increment after service creation "
        f"(before={before_count}, after={after_count})"
    )


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _extract_audit_events_total(metrics_text: str) -> float:
    """
    Sum all mintkey_audit_events_total{...} sample values in the metrics output.
    Returns 0.0 if the metric is absent (counter hasn't been incremented yet).
    """
    total = 0.0
    for line in metrics_text.splitlines():
        if line.startswith("mintkey_audit_events_total{"):
            try:
                total += float(line.split()[-1])
            except (ValueError, IndexError):
                pass
    return total
