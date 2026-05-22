"""
Tenant context middleware.

Sets app.current_tenant (and optionally app.platform_admin_view) via
SET LOCAL-equivalent bound parameters before any query in the transaction.

Source: design §4 "Tenant context middleware (CORRECTED — bound parameters)";
        ADR-0008; ADR-0016.3; Req MT-2.
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_context(
    session: AsyncSession,
    tenant_id: UUID,
    is_platform_admin_view: bool = False,
) -> None:
    """
    Bind app.current_tenant to tenant_id for the current transaction.
    Bound parameters prevent SQL injection — never use f-strings here.
    Source: design §4; ADR-0008.
    """
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": str(tenant_id)},
    )
    if is_platform_admin_view:
        # PlatformAdmin escape — ADR-0016.3
        await session.execute(
            text("SELECT set_config('app.platform_admin_view', 'on', true)"),
        )
