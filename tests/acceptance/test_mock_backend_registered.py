"""
Acceptance test: mock-backend is registered in the default tenant after
MINTKEY_SEED_DEMO=true seed run (T-1.11.4).

This test is structural (no live DB):
  - Validates the seed_mock_backend_demo function is importable and callable.
  - Validates the function inserts the correct service slug and agent name.
  - The integration form (requires docker compose) is skipped unless
    MINTKEY_INTEGRATION_TEST=true.

Source: T-1.11.4; Req 12 AC2; design §12.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import pytest

from mintkey_models.bootstrap_password import read_bootstrap_password

# Make seed-job importable from tests
SEED_DIR = Path(__file__).resolve().parents[2] / "seed-job"
if str(SEED_DIR) not in sys.path:
    sys.path.insert(0, str(SEED_DIR))


from main import (  # noqa: E402
    DEMO_AGENT_NAME,
    MOCK_BACKEND_SLUG,
    seed_mock_backend_demo,
)


def _make_mock_conn(service_id="svc-uuid-1", agent_id="agent-uuid-1"):
    """Return a psycopg2 connection mock with pre-configured cursor fetchone."""
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__ = lambda s: cur
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

    # First fetchone: service_id, second fetchone: agent_id
    cur.fetchone.side_effect = [(service_id,), (agent_id,)]
    return conn, cur


def test_seed_mock_backend_demo_inserts_service():
    """seed_mock_backend_demo inserts mock-backend service with correct slug."""
    conn, cur = _make_mock_conn()
    seed_mock_backend_demo(conn, "tenant-uuid-1")

    # Find INSERT INTO services call
    service_insert_found = False
    for c in cur.execute.call_args_list:
        sql = c.args[0] if c.args else ""
        if "INSERT INTO services" in sql:
            params = c.args[1]
            assert MOCK_BACKEND_SLUG in params, "mock-backend slug not in INSERT params"
            assert "api_key_header" in params
            service_insert_found = True
            break
    assert service_insert_found, "No INSERT INTO services found"


def test_seed_mock_backend_demo_inserts_agent():
    """seed_mock_backend_demo inserts demo agent with correct name."""
    conn, cur = _make_mock_conn()
    seed_mock_backend_demo(conn, "tenant-uuid-1")

    agent_insert_found = False
    for c in cur.execute.call_args_list:
        sql = c.args[0] if c.args else ""
        if "INSERT INTO agents" in sql:
            params = c.args[1]
            assert DEMO_AGENT_NAME in params
            agent_insert_found = True
            break
    assert agent_insert_found, "No INSERT INTO agents found"


def test_seed_mock_backend_demo_grants_permissions():
    """seed_mock_backend_demo inserts at least 4 permission grants."""
    conn, cur = _make_mock_conn()
    seed_mock_backend_demo(conn, "tenant-uuid-1")

    grant_count = sum(
        1 for c in cur.execute.call_args_list
        if "INSERT INTO permission_grants" in (c.args[0] if c.args else "")
    )
    assert grant_count >= 4, f"Expected ≥ 4 permission grants, got {grant_count}"


def test_seed_mock_backend_demo_idempotent():
    """seed_mock_backend_demo uses ON CONFLICT DO NOTHING (idempotent)."""
    conn, cur = _make_mock_conn()
    seed_mock_backend_demo(conn, "tenant-uuid-1")

    # Verify every INSERT uses ON CONFLICT DO NOTHING
    for c in cur.execute.call_args_list:
        sql = c.args[0] if c.args else ""
        if sql.strip().upper().startswith("INSERT INTO") and "databasechangelog" not in sql:
            assert "ON CONFLICT" in sql, f"INSERT missing ON CONFLICT guard:\n{sql}"


@pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true"
    or os.getenv("MINTKEY_SEED_DEMO", "").lower() not in ("1", "true", "yes"),
    reason="Integration test: requires running docker compose stack with MINTKEY_SEED_DEMO=true",
)
def test_mock_backend_registered_integration():
    """
    After docker compose up with MINTKEY_SEED_DEMO=true, the mock-backend
    service and mock-agent are queryable via admin-api.
    """
    import httpx

    admin_api = os.getenv("ADMIN_API_URL", "http://localhost:8080")
    # Authenticate as bootstrap admin
    resp = httpx.post(
        f"{admin_api}/v1/auth/internal-login",
        json={"email": "admin@mintkey.internal", "password": read_bootstrap_password("data/bootstrap-secrets/admin_password")},
    )
    assert resp.status_code == 200
    login_data = resp.json()

    # Build headers: include X-Platform-Admin when the session has that role.
    admin_headers = {}
    if login_data.get("is_platform_admin"):
        admin_headers["X-Platform-Admin"] = "true"

    # Get default tenant ID
    tenants_resp = httpx.get(
        f"{admin_api}/v1/tenants", cookies=resp.cookies, headers=admin_headers
    )
    assert tenants_resp.status_code == 200
    tenant_id = next(
        t["id"] for t in tenants_resp.json()["data"] if t["slug"] == "t_default"
    )

    # Verify mock-backend service is registered
    services_resp = httpx.get(
        f"{admin_api}/v1/tenants/{tenant_id}/services",
        cookies=resp.cookies,
    )
    assert services_resp.status_code == 200
    slugs = [s["slug"] for s in services_resp.json()["services"]]
    assert "mock-backend" in slugs, f"mock-backend not in services: {slugs}"

    # Verify mock-agent is registered
    agents_resp = httpx.get(
        f"{admin_api}/v1/tenants/{tenant_id}/agents",
        cookies=resp.cookies,
    )
    assert agents_resp.status_code == 200
    names = [a["name"] for a in agents_resp.json()["agents"]]
    assert "mock-agent" in names, f"mock-agent not in agents: {names}"
