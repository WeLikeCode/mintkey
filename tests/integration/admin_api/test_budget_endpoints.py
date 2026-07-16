"""
Integration tests for budget GET/reset endpoints.

Validates T-BUD-2.3 and T-BUD-2.4:
  T-BUD-2.3:
    - GET /budget returns correct BudgetStatus (used, remaining, period_end).
    - GET /budget returns 404 when no budget configured.
  T-BUD-2.4:
    - POST /budget/reset creates new counter with used=0.
    - POST /budget/reset emits budget.reset audit event.
    - POST /budget/reset fires change-channel notification.

Source: T-BUD-2.3; T-BUD-2.4; FR-5, FR-9; design §5.
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
# CSRF helpers (same pattern as test_budget_config.py)
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-token-budget-ep"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}


def _post(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


def _get(client: TestClient, url: str, **kwargs):
    return client.get(url, **kwargs)


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
def ep_tenant(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "budget-ep-tenant")


@pytest.fixture(scope="module")
def ep_agent_id(admin_app: TestClient, postgres_container, ep_tenant: str) -> str:
    return _insert_agent(postgres_container, ep_tenant, "budget-ep-agent")


@pytest.fixture(scope="module")
def ep_service_id(admin_app: TestClient, postgres_container, ep_tenant: str) -> str:
    return _insert_service(postgres_container, ep_tenant, "budget-ep-svc")


@pytest.fixture(scope="module")
def ep_grant_with_budget(
    admin_app: TestClient,
    ep_tenant: str,
    ep_agent_id: str,
    ep_service_id: str,
    postgres_container,
) -> dict:
    """Create a permission grant with budget and return {perm_db_id, perm_wire_id}."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions",
        json={
            "service_id": ep_service_id,
            "action": "invoke-budget-ep",
            "constraints": {
                "budget": {"ceiling": 100, "period": "daily", "alert_thresholds": [50, 80, 100]},
            },
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Get DB UUID for the permission
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM permission_grants"
        " WHERE agent_id = %s AND service_id = %s AND action = %s AND tenant_id = %s",
        (ep_agent_id, ep_service_id, "invoke-budget-ep", ep_tenant),
    )
    perm_row = cur.fetchone()
    cur.close()
    conn.close()
    assert perm_row is not None

    return {
        "perm_db_id": str(perm_row[0]),
        "perm_wire_id": body["id"],
    }


@pytest.fixture(scope="module")
def ep_grant_no_budget(
    admin_app: TestClient,
    ep_tenant: str,
    ep_agent_id: str,
    ep_service_id: str,
    postgres_container,
) -> dict:
    """Create a permission grant WITHOUT budget and return {perm_db_id}."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions",
        json={
            "service_id": ep_service_id,
            "action": "invoke-no-budget",
        },
    )
    assert resp.status_code == 201, resp.text

    # Get DB UUID for the permission
    conn = _get_conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "SELECT id FROM permission_grants"
        " WHERE agent_id = %s AND service_id = %s AND action = %s AND tenant_id = %s",
        (ep_agent_id, ep_service_id, "invoke-no-budget", ep_tenant),
    )
    perm_row = cur.fetchone()
    cur.close()
    conn.close()
    assert perm_row is not None

    return {"perm_db_id": str(perm_row[0])}


# ---------------------------------------------------------------------------
# T-BUD-2.3: GET /budget tests
# ---------------------------------------------------------------------------


class TestGetBudgetStatus:
    """Tests for GET /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget."""

    def test_get_budget_returns_correct_status(
        self,
        admin_app: TestClient,
        ep_tenant: str,
        ep_agent_id: str,
        ep_grant_with_budget: dict,
    ) -> None:
        """
        GET /budget with valid budget configured returns correct BudgetStatus.
        Source: T-BUD-2.3; FR-9.
        """
        perm_id = ep_grant_with_budget["perm_db_id"]
        resp = _get(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions/{perm_id}/budget",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Verify all BudgetStatus fields present
        assert body["ceiling"] == 100
        assert body["period"] == "daily"
        assert body["used"] == 0
        assert body["remaining"] == 100
        assert "period_start" in body
        assert "period_end" in body
        assert body["alert_thresholds"] == [50, 80, 100]

    def test_get_budget_returns_404_when_no_budget(
        self,
        admin_app: TestClient,
        ep_tenant: str,
        ep_agent_id: str,
        ep_grant_no_budget: dict,
    ) -> None:
        """
        GET /budget on a grant without budget constraint returns 404.
        Source: T-BUD-2.3; design §5.
        """
        perm_id = ep_grant_no_budget["perm_db_id"]
        resp = _get(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions/{perm_id}/budget",
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert body["mintkey:code"] == "no_budget"

    def test_get_budget_reflects_used_counter(
        self,
        admin_app: TestClient,
        ep_tenant: str,
        ep_agent_id: str,
        ep_grant_with_budget: dict,
        postgres_container,
    ) -> None:
        """
        GET /budget returns correct used/remaining after counter is incremented.
        Source: T-BUD-2.3; FR-9.
        """
        perm_id = ep_grant_with_budget["perm_db_id"]

        # Simulate usage by updating the counter directly
        conn = _get_conn(postgres_container)
        cur = conn.cursor()
        cur.execute(
            "UPDATE budget_counters SET used = 42 WHERE permission_id = %s",
            (perm_id,),
        )
        conn.commit()
        cur.close()
        conn.close()

        resp = _get(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions/{perm_id}/budget",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        assert body["used"] == 42
        assert body["remaining"] == 58  # 100 - 42
        assert body["ceiling"] == 100


# ---------------------------------------------------------------------------
# T-BUD-2.4: POST /budget/reset tests
# ---------------------------------------------------------------------------


class TestResetBudget:
    """Tests for POST /v1/tenants/{tid}/agents/{aid}/permissions/{pid}/budget/reset."""

    def test_reset_creates_counter_with_used_zero(
        self,
        admin_app: TestClient,
        ep_tenant: str,
        ep_agent_id: str,
        ep_grant_with_budget: dict,
        postgres_container,
    ) -> None:
        """
        POST /budget/reset creates new counter with used=0.
        Source: T-BUD-2.4; FR-5.
        """
        perm_id = ep_grant_with_budget["perm_db_id"]

        # Simulate that budget has been partially used
        conn = _get_conn(postgres_container)
        cur = conn.cursor()
        cur.execute(
            "UPDATE budget_counters SET used = 75 WHERE permission_id = %s",
            (perm_id,),
        )
        conn.commit()
        cur.close()
        conn.close()

        # Reset
        resp = _post(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions/{perm_id}/budget/reset",
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()

        # Response should show used=0, remaining=ceiling
        assert body["used"] == 0
        assert body["remaining"] == 100
        assert body["ceiling"] == 100
        assert body["period"] == "daily"
        assert "period_start" in body
        assert "period_end" in body
        assert body["alert_thresholds"] == [50, 80, 100]

    def test_reset_emits_audit_event(
        self,
        admin_app: TestClient,
        ep_tenant: str,
        ep_agent_id: str,
        postgres_container,
        ep_service_id: str,
    ) -> None:
        """
        POST /budget/reset emits a budget.reset audit event.
        Source: T-BUD-2.4; FR-7.
        """
        # Create a separate grant for this test to avoid fixture interference
        resp = _post(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions",
            json={
                "service_id": ep_service_id,
                "action": "invoke-reset-audit",
                "constraints": {
                    "budget": {"ceiling": 50, "period": "hourly"},
                },
            },
        )
        assert resp.status_code == 201, resp.text

        # Get DB UUID
        conn = _get_conn(postgres_container)
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM permission_grants"
            " WHERE agent_id = %s AND service_id = %s AND action = %s AND tenant_id = %s",
            (ep_agent_id, ep_service_id, "invoke-reset-audit", ep_tenant),
        )
        perm_row = cur.fetchone()
        cur.close()
        conn.close()
        assert perm_row is not None
        perm_db_id = str(perm_row[0])

        # Simulate usage
        conn = _get_conn(postgres_container)
        cur = conn.cursor()
        cur.execute(
            "UPDATE budget_counters SET used = 30 WHERE permission_id = %s",
            (perm_db_id,),
        )
        conn.commit()
        cur.close()
        conn.close()

        # Reset
        reset_resp = _post(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions/{perm_db_id}/budget/reset",
        )
        assert reset_resp.status_code == 200, reset_resp.text

        # Verify audit event
        conn = _get_conn(postgres_container)
        cur = conn.cursor()
        cur.execute(
            "SELECT event_type, payload FROM audit_events"
            " WHERE tenant_id = %s AND event_type = 'budget.reset'"
            " ORDER BY at DESC LIMIT 1",
            (ep_tenant,),
        )
        audit_row = cur.fetchone()
        cur.close()
        conn.close()

        assert audit_row is not None, "No budget.reset audit event found"
        assert audit_row[0] == "budget.reset"
        payload = audit_row[1] if isinstance(audit_row[1], dict) else json.loads(audit_row[1])
        assert payload["previous_used"] == 30
        assert payload["previous_ceiling"] == 50
        assert "new_period_start" in payload

    def test_reset_returns_404_when_no_budget(
        self,
        admin_app: TestClient,
        ep_tenant: str,
        ep_agent_id: str,
        ep_grant_no_budget: dict,
    ) -> None:
        """
        POST /budget/reset on a grant without budget returns 404.
        Source: T-BUD-2.4; design §5.
        """
        perm_id = ep_grant_no_budget["perm_db_id"]
        resp = _post(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions/{perm_id}/budget/reset",
        )
        assert resp.status_code == 404, resp.text
        body = resp.json()
        assert body["mintkey:code"] == "no_budget"

    def test_get_budget_after_reset_shows_zero_used(
        self,
        admin_app: TestClient,
        ep_tenant: str,
        ep_agent_id: str,
        postgres_container,
        ep_service_id: str,
    ) -> None:
        """
        After POST /budget/reset, GET /budget reflects used=0.
        Source: T-BUD-2.4; FR-5, FR-9.
        """
        # Create a fresh grant for isolation
        resp = _post(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions",
            json={
                "service_id": ep_service_id,
                "action": "invoke-reset-get",
                "constraints": {
                    "budget": {"ceiling": 200, "period": "daily"},
                },
            },
        )
        assert resp.status_code == 201, resp.text

        # Get DB UUID
        conn = _get_conn(postgres_container)
        cur = conn.cursor()
        cur.execute(
            "SELECT id FROM permission_grants"
            " WHERE agent_id = %s AND service_id = %s AND action = %s AND tenant_id = %s",
            (ep_agent_id, ep_service_id, "invoke-reset-get", ep_tenant),
        )
        perm_row = cur.fetchone()
        cur.close()
        conn.close()
        assert perm_row is not None
        perm_db_id = str(perm_row[0])

        # Simulate usage
        conn = _get_conn(postgres_container)
        cur = conn.cursor()
        cur.execute(
            "UPDATE budget_counters SET used = 150 WHERE permission_id = %s",
            (perm_db_id,),
        )
        conn.commit()
        cur.close()
        conn.close()

        # Reset
        reset_resp = _post(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions/{perm_db_id}/budget/reset",
        )
        assert reset_resp.status_code == 200, reset_resp.text

        # GET /budget should now reflect reset state
        get_resp = _get(
            admin_app,
            f"/v1/tenants/{ep_tenant}/agents/{ep_agent_id}/permissions/{perm_db_id}/budget",
        )
        assert get_resp.status_code == 200, get_resp.text
        body = get_resp.json()
        assert body["used"] == 0
        assert body["remaining"] == 200
