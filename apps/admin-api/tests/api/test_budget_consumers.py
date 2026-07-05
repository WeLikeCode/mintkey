"""
TDD tests for the budget-consumers aggregation endpoint.

Endpoint: GET /v1/tenants/{tenant_id}/budget-consumers

Validates:
  - Returns only budget-configured grants (Req 2.5)
  - Response contains all required BudgetConsumerRecord fields (Req 2.1, 2.2, 2.3)
  - consumption_percentage = round((used/ceiling)*100) (Req 2.3)
  - Results sorted by consumption% descending, exhausted first (Req 2.3)
  - requests_last_30_min counts audit events correctly (Req 2.4)
  - Tenant isolation — no cross-tenant leakage (Req 2.6)
  - Empty result for tenant with no budget-configured grants (Req 2.5)
  - 401 without valid session (Req 2.6)

These tests are written BEFORE the endpoint implementation (TDD, Task 1.1).
They use httpx AsyncClient + pytest-asyncio with mocked DB sessions.

Source: design §Components → Admin-API: Aggregation Endpoint;
        requirements 2.1, 2.2, 2.3, 2.4, 2.5, 2.6.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from admin_api.db.deps import get_db_session
from admin_api.main import app


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_TENANT_A = uuid.UUID("aaaaaaaa-0000-0000-0000-000000000001")
_TENANT_B = uuid.UUID("bbbbbbbb-0000-0000-0000-000000000002")

_AGENT_1_ID = str(uuid.uuid4())
_AGENT_2_ID = str(uuid.uuid4())
_SERVICE_1_ID = str(uuid.uuid4())
_SERVICE_2_ID = str(uuid.uuid4())

_PERM_WITH_BUDGET_1 = str(uuid.uuid4())
_PERM_WITH_BUDGET_2 = str(uuid.uuid4())
_PERM_TENANT_B = str(uuid.uuid4())

_PERIOD_START = datetime(2026, 6, 15, 0, 0, 0, tzinfo=timezone.utc)
_PERIOD_END = datetime(2026, 6, 16, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _budget_row(
    *,
    permission_id: str,
    agent_id: str,
    agent_name: str,
    service_id: str,
    service_name: str,
    ceiling: int,
    period: str,
    used: int,
    requests_last_30_min: int = 0,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
) -> MagicMock:
    """Create a mock DB row matching the expected aggregation query output."""
    row = MagicMock()
    row.permission_id = permission_id
    row.agent_id = agent_id
    row.agent_name = agent_name
    row.service_id = service_id
    row.service_name = service_name
    row.ceiling = ceiling
    row.period = period
    row.used = used
    row.requests_last_30_min = requests_last_30_min
    row.period_start = period_start or _PERIOD_START
    row.period_end = period_end or _PERIOD_END
    return row


def _mock_session_returning(rows: list[MagicMock]) -> AsyncMock:
    """Create a mock AsyncSession that returns given rows from execute().fetchall()."""
    session = AsyncMock()

    result_mock = MagicMock()
    result_mock.fetchall.return_value = rows

    session.execute = AsyncMock(return_value=result_mock)

    return session


def _override_db_session(session: AsyncMock):
    """Create a FastAPI dependency override that yields the mock session."""

    async def _override() -> AsyncGenerator[AsyncMock, None]:
        yield session

    return _override


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def seed_rows_tenant_a() -> list[MagicMock]:
    """Budget-configured grants for tenant A: 2 records.

    - Exhausted grant: 100/100 = 100%
    - Non-exhausted grant: 45/200 = 23%
    """
    return [
        _budget_row(
            permission_id=_PERM_WITH_BUDGET_1,
            agent_id=_AGENT_1_ID,
            agent_name="DataBot",
            service_id=_SERVICE_1_ID,
            service_name="GitHub API",
            ceiling=100,
            period="daily",
            used=100,
            requests_last_30_min=15,
        ),
        _budget_row(
            permission_id=_PERM_WITH_BUDGET_2,
            agent_id=_AGENT_2_ID,
            agent_name="BuildAgent",
            service_id=_SERVICE_2_ID,
            service_name="Slack API",
            ceiling=200,
            period="hourly",
            used=45,
            requests_last_30_min=3,
        ),
    ]


@pytest.fixture
def seed_rows_tenant_b() -> list[MagicMock]:
    """Budget-configured grant for tenant B."""
    return [
        _budget_row(
            permission_id=_PERM_TENANT_B,
            agent_id=str(uuid.uuid4()),
            agent_name="TenantBBot",
            service_id=str(uuid.uuid4()),
            service_name="Private API",
            ceiling=50,
            period="monthly",
            used=10,
            requests_last_30_min=1,
        ),
    ]


@pytest.fixture(autouse=True)
def _cleanup_overrides():
    """Reset app dependency overrides after each test."""
    yield
    app.dependency_overrides.clear()


# ---------------------------------------------------------------------------
# Test: returns only budget-configured grants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBudgetConsumersFiltering:
    """Aggregation endpoint returns only grants with budget constraints configured."""

    async def test_returns_only_budget_configured_grants(
        self, seed_rows_tenant_a: list[MagicMock]
    ) -> None:
        """Only grants with budget constraints appear in response.

        The SQL query uses WHERE pg.constraints->'budget' IS NOT NULL.
        The mock session returns only budget-configured rows (simulating
        the SQL filter). Result should match exactly.

        Validates: Requirement 2.5.
        """
        session = _mock_session_returning(seed_rows_tenant_a)
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_A}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2


# ---------------------------------------------------------------------------
# Test: response contains all required fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestBudgetConsumersResponseSchema:
    """Each record must contain all required BudgetConsumerRecord fields."""

    async def test_response_contains_all_required_fields(
        self, seed_rows_tenant_a: list[MagicMock]
    ) -> None:
        """Every returned record has the full set of fields per the design schema.

        Required: permission_id, agent_id, agent_name, service_id, service_name,
        consumption_percentage, used, ceiling, period, period_start, period_end,
        requests_last_30_min.

        Validates: Requirements 2.1, 2.2, 2.3.
        """
        required_fields = {
            "permission_id",
            "agent_id",
            "agent_name",
            "service_id",
            "service_name",
            "consumption_percentage",
            "used",
            "ceiling",
            "period",
            "period_start",
            "period_end",
            "requests_last_30_min",
        }

        session = _mock_session_returning(seed_rows_tenant_a)
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_A}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) > 0

        for record in data:
            missing = required_fields - set(record.keys())
            assert not missing, (
                f"Record missing fields: {missing}. Got keys: {sorted(record.keys())}"
            )


# ---------------------------------------------------------------------------
# Test: consumption_percentage computed correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestConsumptionPercentage:
    """consumption_percentage = round((used / ceiling) * 100)."""

    @pytest.mark.parametrize(
        "used,ceiling,expected_pct",
        [
            (100, 100, 100),
            (45, 200, 22),   # round(22.5) = 22 (Python banker's rounding)
            (0, 50, 0),
            (1, 3, 33),      # round(33.33) = 33
            (2, 3, 67),      # round(66.67) = 67
            (99, 100, 99),
            (150, 100, 150), # over-budget
            (1, 1000, 0),    # round(0.1) = 0
            (999, 1000, 100),  # round(99.9) = 100
        ],
    )
    async def test_consumption_percentage_computation(
        self, used: int, ceiling: int, expected_pct: int
    ) -> None:
        """Verify percentage = round((used/ceiling)*100).

        Validates: Requirement 2.3; Design Property 5.
        """
        rows = [
            _budget_row(
                permission_id=str(uuid.uuid4()),
                agent_id=_AGENT_1_ID,
                agent_name="TestAgent",
                service_id=_SERVICE_1_ID,
                service_name="TestService",
                ceiling=ceiling,
                period="daily",
                used=used,
                requests_last_30_min=0,
            ),
        ]

        session = _mock_session_returning(rows)
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_A}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        actual_pct = data[0]["consumption_percentage"]
        assert actual_pct == expected_pct, (
            f"For used={used}, ceiling={ceiling}: "
            f"expected {expected_pct}%, got {actual_pct}%"
        )


# ---------------------------------------------------------------------------
# Test: results sorted by consumption% descending, exhausted first
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestSortOrder:
    """Results sorted: exhausted first, then by consumption% descending."""

    async def test_sorted_exhausted_first_then_descending(self) -> None:
        """Exhausted grants (used >= ceiling) appear first, then sorted by consumption%.

        Seed rows already ordered by SQL: 100%, 80%, 50%.
        The endpoint preserves the SQL sort order.

        Validates: Requirement 2.3; Design Property 6.
        """
        # SQL returns rows pre-sorted — exhausted first, then by pct desc.
        rows = [
            _budget_row(
                permission_id=str(uuid.uuid4()),
                agent_id=_AGENT_2_ID,
                agent_name="Agent100",
                service_id=_SERVICE_2_ID,
                service_name="Svc2",
                ceiling=100,
                period="daily",
                used=100,
            ),
            _budget_row(
                permission_id=str(uuid.uuid4()),
                agent_id=str(uuid.uuid4()),
                agent_name="Agent80",
                service_id=str(uuid.uuid4()),
                service_name="Svc3",
                ceiling=100,
                period="daily",
                used=80,
            ),
            _budget_row(
                permission_id=str(uuid.uuid4()),
                agent_id=_AGENT_1_ID,
                agent_name="Agent50",
                service_id=_SERVICE_1_ID,
                service_name="Svc1",
                ceiling=100,
                period="daily",
                used=50,
            ),
        ]

        session = _mock_session_returning(rows)
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_A}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

        percentages = [r["consumption_percentage"] for r in data]
        assert percentages == [100, 80, 50], (
            f"Expected [100, 80, 50] (exhausted first, then desc), got {percentages}"
        )

    async def test_multiple_exhausted_sorted_among_themselves(self) -> None:
        """Multiple exhausted grants sorted by consumption% among themselves.

        Seed: 150%, 100%, 90%. Expected same order.

        Validates: Requirement 2.3.
        """
        rows = [
            _budget_row(
                permission_id=str(uuid.uuid4()),
                agent_id=_AGENT_1_ID,
                agent_name="AgentOver",
                service_id=_SERVICE_1_ID,
                service_name="Svc1",
                ceiling=100,
                period="daily",
                used=150,
            ),
            _budget_row(
                permission_id=str(uuid.uuid4()),
                agent_id=_AGENT_2_ID,
                agent_name="AgentExact",
                service_id=_SERVICE_2_ID,
                service_name="Svc2",
                ceiling=100,
                period="daily",
                used=100,
            ),
            _budget_row(
                permission_id=str(uuid.uuid4()),
                agent_id=str(uuid.uuid4()),
                agent_name="Agent90",
                service_id=str(uuid.uuid4()),
                service_name="Svc3",
                ceiling=100,
                period="daily",
                used=90,
            ),
        ]

        session = _mock_session_returning(rows)
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_A}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 3

        percentages = [r["consumption_percentage"] for r in data]
        assert percentages == [150, 100, 90], (
            f"Expected [150, 100, 90], got {percentages}"
        )


# ---------------------------------------------------------------------------
# Test: requests_last_30_min counts audit events correctly
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestRequestsLast30Min:
    """requests_last_30_min counts token.issued audit events in the last 30 minutes."""

    async def test_requests_last_30_min_counted_correctly(self) -> None:
        """The count reflects audit_events with event_type='token.issued' within 30 min.

        Validates: Requirement 2.4.
        """
        rows = [
            _budget_row(
                permission_id=_PERM_WITH_BUDGET_1,
                agent_id=_AGENT_1_ID,
                agent_name="DataBot",
                service_id=_SERVICE_1_ID,
                service_name="GitHub API",
                ceiling=100,
                period="daily",
                used=75,
                requests_last_30_min=15,
            ),
        ]

        session = _mock_session_returning(rows)
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_A}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["requests_last_30_min"] == 15

    async def test_zero_requests_when_no_recent_events(self) -> None:
        """Grant with no recent token.issued events shows 0 requests.

        Validates: Requirement 2.4.
        """
        rows = [
            _budget_row(
                permission_id=_PERM_WITH_BUDGET_1,
                agent_id=_AGENT_1_ID,
                agent_name="IdleBot",
                service_id=_SERVICE_1_ID,
                service_name="Dormant API",
                ceiling=50,
                period="hourly",
                used=10,
                requests_last_30_min=0,
            ),
        ]

        session = _mock_session_returning(rows)
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_A}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["requests_last_30_min"] == 0


# ---------------------------------------------------------------------------
# Test: tenant isolation — no cross-tenant leakage
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestTenantIsolation:
    """Multi-tenant seed: query as tenant A sees only tenant A data."""

    async def test_no_cross_tenant_leakage(
        self,
        seed_rows_tenant_a: list[MagicMock],
    ) -> None:
        """Querying as tenant A returns only tenant A records.

        The endpoint scopes results via set_tenant_context (RLS) + explicit
        tenant_id in the SQL WHERE clause. Tenant B data never appears.

        Validates: Requirement 2.6; Design Property 2.
        """
        session = _mock_session_returning(seed_rows_tenant_a)
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ) as mock_set_ctx:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_A}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 2

        # Verify set_tenant_context was called with tenant A's ID
        mock_set_ctx.assert_awaited_once()
        call_args = mock_set_ctx.call_args
        # Positional: (session, tenant_id) or keyword
        tenant_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["tenant_id"]
        assert tenant_arg == _TENANT_A

    async def test_tenant_b_query_returns_only_tenant_b_data(
        self,
        seed_rows_tenant_b: list[MagicMock],
    ) -> None:
        """Querying as tenant B returns only tenant B records.

        Validates: Requirement 2.6.
        """
        session = _mock_session_returning(seed_rows_tenant_b)
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ) as mock_set_ctx:
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_B}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["agent_name"] == "TenantBBot"

        # Verify tenant context was set to tenant B
        mock_set_ctx.assert_awaited_once()
        call_args = mock_set_ctx.call_args
        tenant_arg = call_args[0][1] if len(call_args[0]) > 1 else call_args[1]["tenant_id"]
        assert tenant_arg == _TENANT_B


# ---------------------------------------------------------------------------
# Test: empty result for tenant with no budget-configured grants
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestEmptyResult:
    """Tenant with no budget-configured grants returns empty JSON array."""

    async def test_empty_array_when_no_budget_grants(self) -> None:
        """Tenant with zero budget-configured grants receives [].

        Validates: Requirement 2.5.
        """
        session = _mock_session_returning([])
        app.dependency_overrides[get_db_session] = _override_db_session(session)

        with patch(
            "admin_api.api.budget_consumers.set_tenant_context",
            new_callable=AsyncMock,
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
            ) as client:
                response = await client.get(
                    f"/v1/tenants/{_TENANT_A}/budget-consumers"
                )

        assert response.status_code == 200
        data = response.json()
        assert data == []


# ---------------------------------------------------------------------------
# Test: 401 without valid session
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestAuthentication:
    """Endpoint requires authentication — returns 401 without valid session."""

    async def test_401_without_valid_session(self) -> None:
        """Request without a valid authenticated session returns 401.

        The budget-consumers endpoint should validate that the request
        originates from an authenticated operator session (forwarded by the
        BFF). Without proper auth, the endpoint rejects with 401.

        Note: This test verifies the auth guard the implementation must include.
        The exact mechanism (middleware or dependency) is an implementation detail,
        but the behavior must be: no auth → 401/403.

        Validates: Requirement 2.6.
        """
        # Do NOT override the DB session — an unauthenticated request should
        # never reach the database query. The auth guard should reject first.
        # However, since this is TDD and the auth mechanism may vary, we
        # provide a failing DB override to confirm auth is checked before DB.
        async def _fail_session() -> AsyncGenerator[Any, None]:
            raise RuntimeError("DB should not be reached without auth")
            yield  # type: ignore[misc]  # noqa: E501 — unreachable, satisfies generator

        app.dependency_overrides[get_db_session] = _fail_session

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
        ) as client:
            # No auth headers, no cookies
            response = await client.get(
                f"/v1/tenants/{_TENANT_A}/budget-consumers"
            )

        # Expect 401 (Unauthorized) or 403 (Forbidden)
        assert response.status_code in (401, 403), (
            f"Expected 401/403 without auth, got {response.status_code}. "
            f"Body: {response.text}"
        )
