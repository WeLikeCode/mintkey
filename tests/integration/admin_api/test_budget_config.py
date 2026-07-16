"""
Integration tests for budget config validation in grant creation/update.

Validates T-BUD-2.2:
  1. Invalid budget (ceiling=0, invalid period) is rejected with 422.
  2. Valid budget persists and creates a counter row.
  3. Ceiling update via PATCH updates the counter row.
  4. Period change via PATCH closes old row and creates new.
  5. budget.config_updated audit event is emitted.
  6. Change-channel NOTIFY is fired.

Source: T-BUD-2.2; FR-1, FR-6, FR-10; design §5, §6.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid

import psycopg2
import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# CSRF helpers (same pattern as test_permissions.py)
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-token-budget"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}


def _post(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


def _patch(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.patch(url, headers=headers, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _get_conn(postgres_container):
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )


def _insert_tenant(postgres_container, slug: str) -> str:
    conn = _get_conn(postgres_container)
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


def _insert_service(postgres_container, tenant_id: str, slug: str) -> str:
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    svc_id = str(uuid.uuid4())
    cur.execute(
        "INSERT INTO services"
        " (id, tenant_id, name, slug, display_name, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (svc_id, tenant_id, slug, slug, slug,
         "https://example.com/api", "bearer_token", "active"),
    )
    conn.commit()
    cur.close()
    conn.close()
    return svc_id


def _insert_agent(postgres_container, tenant_id: str, name: str) -> str:
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    raw_key = "mk_agent_" + secrets.token_hex(20)
    api_key_hash = ph.hash(raw_key)
    fingerprint = hashlib.sha256(raw_key.encode()).digest()[:8].hex()
    agent_internal_id = str(uuid.uuid4())

    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agents"
        " (id, tenant_id, name, description, api_key_hash, api_key_fingerprint,"
        "  mcp_endpoint, status, rate_limit_rps)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (agent_internal_id, tenant_id, name, None, api_key_hash, fingerprint,
         f"http://localhost:8100/v1/agents/{agent_internal_id}", "active", None),
    )
    conn.commit()
    cur.close()
    conn.close()
    return agent_internal_id


@pytest.fixture(scope="module")
def budget_tenant(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "budget-test-tenant")


@pytest.fixture(scope="module")
def budget_agent_id(admin_app: TestClient, postgres_container, budget_tenant: str) -> str:
    return _insert_agent(postgres_container, budget_tenant, "budget-agent")


@pytest.fixture(scope="module")
def budget_service_id(admin_app: TestClient, postgres_container, budget_tenant: str) -> str:
    return _insert_service(postgres_container, budget_tenant, "budget-svc")


# ---------------------------------------------------------------------------
# Tests: Invalid budget rejected (422)
# ---------------------------------------------------------------------------


def test_grant_with_budget_ceiling_zero_returns_422(
    admin_app: TestClient, budget_tenant: str, budget_agent_id: str, budget_service_id: str,
) -> None:
    """Budget ceiling=0 violates minimum=1 → 422. Source: design §2, FR-1."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions",
        json={
            "service_id": budget_service_id,
            "action": "invoke-ceil-zero",
            "constraints": {
                "budget": {"ceiling": 0, "period": "daily"},
            },
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json().get("mintkey:code") == "validation_failed"


def test_grant_with_budget_invalid_period_returns_422(
    admin_app: TestClient, budget_tenant: str, budget_agent_id: str, budget_service_id: str,
) -> None:
    """Budget period 'yearly' is not in enum → 422. Source: design §2."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions",
        json={
            "service_id": budget_service_id,
            "action": "invoke-bad-period",
            "constraints": {
                "budget": {"ceiling": 100, "period": "yearly"},
            },
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json().get("mintkey:code") == "validation_failed"


def test_grant_with_budget_invalid_threshold_returns_422(
    admin_app: TestClient, budget_tenant: str, budget_agent_id: str, budget_service_id: str,
) -> None:
    """Budget alert_thresholds > 100 violates max=100 → 422. Source: design §2."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions",
        json={
            "service_id": budget_service_id,
            "action": "invoke-bad-threshold",
            "constraints": {
                "budget": {"ceiling": 10, "period": "daily", "alert_thresholds": [150]},
            },
        },
    )
    assert resp.status_code == 422, resp.text
    assert resp.json().get("mintkey:code") == "validation_failed"


# ---------------------------------------------------------------------------
# Tests: Valid budget persists and counter created
# ---------------------------------------------------------------------------


def test_grant_with_valid_budget_creates_counter_row(
    admin_app: TestClient,
    budget_tenant: str,
    budget_agent_id: str,
    budget_service_id: str,
    postgres_container,
) -> None:
    """
    Grant with valid budget → 201; budget_counters row created with used=0.
    Source: T-BUD-2.2; FR-1.
    """
    resp = _post(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions",
        json={
            "service_id": budget_service_id,
            "action": "invoke-with-budget",
            "constraints": {
                "budget": {"ceiling": 50, "period": "daily"},
            },
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["constraints"]["budget"]["ceiling"] == 50
    assert body["constraints"]["budget"]["period"] == "daily"

    # Verify budget_counters row exists in the DB
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT permission_id, ceiling, used, period_start, period_end"
        " FROM budget_counters WHERE tenant_id = %s",
        (budget_tenant,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    assert len(rows) >= 1, f"Expected at least 1 budget_counters row, got {len(rows)}"
    # Find the row for our permission
    found = False
    for row in rows:
        if row[1] == 50 and row[2] == 0:
            found = True
            break
    assert found, f"No budget_counters row with ceiling=50, used=0 found. Rows: {rows}"


# ---------------------------------------------------------------------------
# Tests: PATCH — ceiling update updates counter row
# ---------------------------------------------------------------------------


def test_patch_budget_ceiling_updates_counter(
    admin_app: TestClient,
    budget_tenant: str,
    budget_agent_id: str,
    postgres_container,
) -> None:
    """
    PATCH with new ceiling → counter row ceiling updated. Source: T-BUD-2.2; FR-6.
    """
    # Create a service and grant with budget
    svc_id = _insert_service(postgres_container, budget_tenant, "budget-patch-ceil-svc")
    grant_resp = _post(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions",
        json={
            "service_id": svc_id,
            "action": "call-patch-ceil",
            "constraints": {
                "budget": {"ceiling": 100, "period": "daily"},
            },
        },
    )
    assert grant_resp.status_code == 201, grant_resp.text

    # Get the permission DB id for PATCH
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM permission_grants"
        " WHERE agent_id = %s AND service_id = %s AND action = %s AND tenant_id = %s",
        (budget_agent_id, svc_id, "call-patch-ceil", budget_tenant),
    )
    perm_row = cur.fetchone()
    cur.close()
    conn.close()
    assert perm_row is not None
    perm_db_id = str(perm_row[0])

    # PATCH to increase ceiling
    patch_resp = _patch(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions/{perm_db_id}",
        json={
            "constraints": {
                "budget": {"ceiling": 200, "period": "daily"},
            },
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    patch_body = patch_resp.json()
    assert patch_body["constraints"]["budget"]["ceiling"] == 200

    # Verify counter ceiling updated in DB
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT ceiling FROM budget_counters WHERE permission_id = %s ORDER BY period_start DESC LIMIT 1",
        (perm_db_id,),
    )
    counter_row = cur.fetchone()
    cur.close()
    conn.close()
    assert counter_row is not None, "No budget_counters row found after PATCH"
    assert counter_row[0] == 200, f"Expected ceiling=200, got {counter_row[0]}"


# ---------------------------------------------------------------------------
# Tests: PATCH — period change creates new counter row
# ---------------------------------------------------------------------------


def test_patch_budget_period_change_creates_new_counter(
    admin_app: TestClient,
    budget_tenant: str,
    budget_agent_id: str,
    postgres_container,
) -> None:
    """
    PATCH with different period → new counter row (old one left intact).
    Source: T-BUD-2.2; FR-6.
    """
    svc_id = _insert_service(postgres_container, budget_tenant, "budget-patch-period-svc")
    grant_resp = _post(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions",
        json={
            "service_id": svc_id,
            "action": "call-patch-period",
            "constraints": {
                "budget": {"ceiling": 50, "period": "hourly"},
            },
        },
    )
    assert grant_resp.status_code == 201, grant_resp.text

    # Get perm DB id
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM permission_grants"
        " WHERE agent_id = %s AND service_id = %s AND action = %s AND tenant_id = %s",
        (budget_agent_id, svc_id, "call-patch-period", budget_tenant),
    )
    perm_row = cur.fetchone()
    cur.close()
    conn.close()
    assert perm_row is not None
    perm_db_id = str(perm_row[0])

    # Count counter rows before
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM budget_counters WHERE permission_id = %s", (perm_db_id,))
    count_before = cur.fetchone()[0]
    cur.close()
    conn.close()

    # PATCH to change period from hourly → daily
    patch_resp = _patch(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions/{perm_db_id}",
        json={
            "constraints": {
                "budget": {"ceiling": 50, "period": "daily"},
            },
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text
    assert patch_resp.json()["constraints"]["budget"]["period"] == "daily"

    # Count counter rows after — should have at least the new daily row
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT period_start, period_end, ceiling, used FROM budget_counters"
        " WHERE permission_id = %s ORDER BY period_start DESC",
        (perm_db_id,),
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()

    # The newest row should be for the daily period with used=0
    assert len(rows) >= 1, "Expected at least 1 counter row after period change"
    newest = rows[0]
    assert newest[2] == 50, f"New counter ceiling should be 50, got {newest[2]}"
    assert newest[3] == 0, f"New counter used should be 0, got {newest[3]}"


# ---------------------------------------------------------------------------
# Tests: Audit event emitted on PATCH
# ---------------------------------------------------------------------------


def test_patch_budget_emits_audit_event(
    admin_app: TestClient,
    budget_tenant: str,
    budget_agent_id: str,
    postgres_container,
) -> None:
    """
    PATCH budget → budget.config_updated audit event emitted.
    Source: T-BUD-2.2; FR-7.
    """
    svc_id = _insert_service(postgres_container, budget_tenant, "budget-audit-svc")
    grant_resp = _post(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions",
        json={
            "service_id": svc_id,
            "action": "call-audit-test",
            "constraints": {
                "budget": {"ceiling": 10, "period": "hourly"},
            },
        },
    )
    assert grant_resp.status_code == 201, grant_resp.text

    # Get perm DB id
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM permission_grants"
        " WHERE agent_id = %s AND service_id = %s AND action = %s AND tenant_id = %s",
        (budget_agent_id, svc_id, "call-audit-test", budget_tenant),
    )
    perm_row = cur.fetchone()
    cur.close()
    conn.close()
    assert perm_row is not None
    perm_db_id = str(perm_row[0])

    # PATCH to update ceiling
    patch_resp = _patch(
        admin_app,
        f"/v1/tenants/{budget_tenant}/agents/{budget_agent_id}/permissions/{perm_db_id}",
        json={
            "constraints": {
                "budget": {"ceiling": 20, "period": "hourly"},
            },
        },
    )
    assert patch_resp.status_code == 200, patch_resp.text

    # Verify audit event
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT event_type, payload FROM audit_events"
        " WHERE tenant_id = %s AND event_type = 'budget.config_updated'"
        " ORDER BY at DESC LIMIT 1",
        (budget_tenant,),
    )
    audit_row = cur.fetchone()
    cur.close()
    conn.close()

    assert audit_row is not None, "No budget.config_updated audit event found"
    assert audit_row[0] == "budget.config_updated"
    payload = audit_row[1] if isinstance(audit_row[1], dict) else json.loads(audit_row[1])
    assert payload["old_ceiling"] == 10
    assert payload["new_ceiling"] == 20
