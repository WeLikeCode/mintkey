"""
T-BUD-4.1: describe_service returns budget info in your_constraints.budget.

Unit tests (no docker required):
  1. Grant with budget constraint + active counter → budget populated.
  2. Grant with budget constraint but no counter row → budget with used=0.
  3. Grant without budget constraint → budget is null.

Source: FR-8; design §8; T-BUD-4.1.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest


# A fixed UUID used across unit tests.
_TEST_SERVICE_UUID = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
_TEST_PERMISSION_UUID = "aaaa0000-1111-2222-3333-444455556666"


def _make_fake_service_row(
    *,
    service_id: str = _TEST_SERVICE_UUID,
    name: str = "test-svc",
    slug: str = "test-svc",
    base_url: str = "https://example.com",
    auth_scheme: str = "api_key_header",
    description=None,
    openapi_url=None,
) -> MagicMock:
    row = MagicMock()
    row.id = service_id
    row.name = name
    row.slug = slug
    row.base_url = base_url
    row.auth_scheme = auth_scheme
    row.description = description
    row.openapi_url = openapi_url
    return row


def _make_constraints_row(*, permission_id: str, constraints: dict | None) -> MagicMock:
    row = MagicMock()
    row.id = permission_id
    row.constraints = constraints
    return row


def _make_budget_counter_row(*, used: int, ceiling: int, period_end: datetime) -> MagicMock:
    row = MagicMock()
    row.used = used
    row.ceiling = ceiling
    row.period_end = period_end
    return row


def _build_app_with_budget_mocks(
    *,
    service_row,
    constraints_row=None,
    budget_counter_row=None,
):
    """
    Build a test app where describe_service will encounter:
    - service_row for the service SELECT
    - constraints_row for the permission_grants SELECT
    - budget_counter_row for the budget_counters SELECT

    The session.execute mock dispatches based on the SQL query string.
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context
    from mcp_server.main import create_app

    tenant_id = uuid.uuid4()
    agent_id = str(uuid.uuid4())
    fake_ctx = {"tenant_id": tenant_id, "agent_id": agent_id}

    _orig_validate = _main_mod.validate_agent_key

    async def _fake_validate(key):
        return fake_ctx, None

    _main_mod.validate_agent_key = _fake_validate
    app = create_app()

    async def _fake_agent_ctx():
        return fake_ctx

    app.dependency_overrides[get_agent_context] = _fake_agent_ctx

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()

        async def _execute(stmt, params=None, **kw):
            # Determine which query is being made based on the SQL text.
            sql_str = str(stmt.text) if hasattr(stmt, "text") else str(stmt)

            result_mock = MagicMock()

            if "budget_counters" in sql_str:
                result_mock.fetchone.return_value = budget_counter_row
            elif "permission_grants" in sql_str:
                result_mock.fetchone.return_value = constraints_row
            elif "FROM services" in sql_str:
                result_mock.fetchone.return_value = service_row
            else:
                # set_tenant_context or other calls — return empty
                result_mock.fetchone.return_value = None
                result_mock.fetchall.return_value = []

            return result_mock

        session.execute = _execute
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session
    return app, _orig_validate, _main_mod


def _run_describe_budget(
    *,
    service_row,
    constraints_row=None,
    budget_counter_row=None,
    service_id: str = _TEST_SERVICE_UUID,
):
    """Run describe_service with budget-aware mocks."""
    from httpx import AsyncClient, ASGITransport

    app, _orig, _main_mod = _build_app_with_budget_mocks(
        service_row=service_row,
        constraints_row=constraints_row,
        budget_counter_row=budget_counter_row,
    )
    try:
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/v1/tools/describe_service/{service_id}",
                    headers={"X-API-Key": "mk_agent_testkey"},
                )

        resp = asyncio.run(_inner())
    finally:
        _main_mod.validate_agent_key = _orig
    return resp


# ===========================================================================
# T-BUD-4.1: Budget info tests
# ===========================================================================


def test_describe_service_budget_populated_when_counter_exists() -> None:
    """
    Grant with a budget constraint and an active counter row returns
    your_constraints.budget with ceiling, period, used, remaining, period_end,
    alert_thresholds.

    Source: FR-8; design §8; T-BUD-4.1.
    """
    period_end = datetime(2026, 6, 28, 0, 0, 0)
    service_row = _make_fake_service_row()
    constraints_row = _make_constraints_row(
        permission_id=_TEST_PERMISSION_UUID,
        constraints={
            "budget": {
                "ceiling": 1000,
                "period": "daily",
                "alert_thresholds": [50, 80, 100],
            }
        },
    )
    budget_counter_row = _make_budget_counter_row(
        used=847,
        ceiling=1000,
        period_end=period_end,
    )

    resp = _run_describe_budget(
        service_row=service_row,
        constraints_row=constraints_row,
        budget_counter_row=budget_counter_row,
    )

    assert resp.status_code == 200, resp.text
    svc = resp.json()["service"]
    budget = svc["your_constraints"]["budget"]

    assert budget is not None, "budget should not be null when counter exists"
    assert budget["ceiling"] == 1000
    assert budget["period"] == "daily"
    assert budget["used"] == 847
    assert budget["remaining"] == 153
    assert budget["alert_thresholds"] == [50, 80, 100]
    # period_end should be an ISO 8601 string
    assert "2026-06-28" in budget["period_end"]


def test_describe_service_budget_used_zero_when_no_counter_row() -> None:
    """
    Grant with a budget constraint but no counter row (no requests this period)
    returns budget with used=0 and remaining=ceiling.

    Source: FR-8; design §8; T-BUD-4.1.
    """
    service_row = _make_fake_service_row()
    constraints_row = _make_constraints_row(
        permission_id=_TEST_PERMISSION_UUID,
        constraints={
            "budget": {
                "ceiling": 500,
                "period": "hourly",
                "alert_thresholds": [80, 100],
            }
        },
    )

    resp = _run_describe_budget(
        service_row=service_row,
        constraints_row=constraints_row,
        budget_counter_row=None,  # No counter row exists yet.
    )

    assert resp.status_code == 200, resp.text
    svc = resp.json()["service"]
    budget = svc["your_constraints"]["budget"]

    assert budget is not None, "budget should not be null when budget config exists"
    assert budget["ceiling"] == 500
    assert budget["period"] == "hourly"
    assert budget["used"] == 0
    assert budget["remaining"] == 500
    assert budget["alert_thresholds"] == [80, 100]
    assert budget["period_end"] is not None


def test_describe_service_budget_null_when_no_budget_constraint() -> None:
    """
    Grant without a budget constraint returns your_constraints.budget as null.

    Source: FR-8; design §8; T-BUD-4.1.
    """
    service_row = _make_fake_service_row()
    constraints_row = _make_constraints_row(
        permission_id=_TEST_PERMISSION_UUID,
        constraints={"rate_limit": 100, "time_window": 60},
    )

    resp = _run_describe_budget(
        service_row=service_row,
        constraints_row=constraints_row,
        budget_counter_row=None,
    )

    assert resp.status_code == 200, resp.text
    svc = resp.json()["service"]
    budget = svc["your_constraints"]["budget"]

    assert budget is None, f"budget should be null when no budget constraint, got: {budget}"


def test_describe_service_budget_null_when_no_permission_grant() -> None:
    """
    When no permission grant is found (constraints_row is None),
    your_constraints.budget should be null.

    Source: FR-8; design §8; T-BUD-4.1.
    """
    service_row = _make_fake_service_row()

    resp = _run_describe_budget(
        service_row=service_row,
        constraints_row=None,
        budget_counter_row=None,
    )

    assert resp.status_code == 200, resp.text
    svc = resp.json()["service"]
    budget = svc["your_constraints"]["budget"]

    assert budget is None, f"budget should be null when no permission grant, got: {budget}"
