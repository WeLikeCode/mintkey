"""
Tests for set_tenant_context() helper.

Verifies: bound parameters (not f-strings); platform_admin_view support.
Source: T-1.0.9 test-first; design §4; ADR-0008 (bound parameter tenant context).
"""
from __future__ import annotations

import asyncio
import inspect
import uuid
from unittest.mock import AsyncMock


def _run(coro):
    """Synchronous runner for async coroutines (no pytest-asyncio required)."""
    return asyncio.get_event_loop().run_until_complete(coro)


class TestSetTenantContextBoundParams:
    """set_tenant_context uses bound params, not f-strings — ADR-0008."""

    def test_set_tenant_context_calls_correct_sql(self) -> None:
        """
        The SQL must contain ':tid' (bound param placeholder), not the raw UUID.
        Bound parameters prevent SQL injection per ADR-0008 / T-1.0.15.
        """
        from mintkey_models.tenant_ctx import set_tenant_context

        session = AsyncMock()
        tid = uuid.uuid4()

        _run(set_tenant_context(session, tid))

        assert session.execute.call_count == 1
        args, kwargs = session.execute.call_args_list[0]
        sql_str = str(args[0])
        assert "set_config" in sql_str
        assert "app.current_tenant" in sql_str
        assert ":tid" in sql_str, f"Bound param :tid not found in SQL: {sql_str}"
        # The bound param dict carries the tenant id as string
        assert args[1] == {"tid": str(tid)}, (
            f"Expected {{'tid': '{tid}'}}, got {args[1]}"
        )

    def test_set_tenant_context_platform_admin(self) -> None:
        """
        With is_platform_admin_view=True, a second execute sets app.platform_admin_view.
        Source: ADR-0016.3.
        """
        from mintkey_models.tenant_ctx import set_tenant_context

        session = AsyncMock()
        tid = uuid.uuid4()

        _run(set_tenant_context(session, tid, is_platform_admin_view=True))

        assert session.execute.call_count == 2
        # Second call sets app.platform_admin_view
        second_args, _ = session.execute.call_args_list[1]
        sql_str = str(second_args[0])
        assert "app.platform_admin_view" in sql_str

    def test_set_tenant_context_no_platform_admin_by_default(self) -> None:
        """Default (is_platform_admin_view=False) only issues one execute."""
        from mintkey_models.tenant_ctx import set_tenant_context

        session = AsyncMock()
        tid = uuid.uuid4()

        _run(set_tenant_context(session, tid))

        assert session.execute.call_count == 1, (
            "Expected exactly 1 execute (no platform_admin_view by default)"
        )

    def test_set_tenant_context_no_fstring(self) -> None:
        """
        Inspect source: the SQL must use bound params, not f-string interpolation.
        Per ADR-0008 and T-1.0.15 (SQL injection architecture test).
        """
        from mintkey_models import tenant_ctx

        source = inspect.getsource(tenant_ctx)
        # Must have a bound parameter placeholder
        assert ":tid" in source, "Source must contain :tid bound parameter"
        # No f-string may appear on any line that also references set_config + current_tenant
        for line in source.splitlines():
            if "set_config" in line and "current_tenant" in line:
                assert 'f"' not in line and "f'" not in line, (
                    f"set_config line must not use f-string: {line}"
                )
