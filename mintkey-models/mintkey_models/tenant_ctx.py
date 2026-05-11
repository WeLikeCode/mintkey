"""
Tenant context helper — shared between admin-api and mcp-server.

Sets app.current_tenant (and optionally app.platform_admin_view) via
bound parameters. Never uses f-string interpolation into SQL — that would
be a SQL injection vector and is explicitly forbidden by ADR-0008 and the
T-1.0.15 architecture test.

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
    """Set app.current_tenant via bound parameters (never f-strings).

    Source: design §4, ADR-0008.
    """
    await session.execute(
        text("SELECT set_config('app.current_tenant', :tid, true)"),
        {"tid": str(tenant_id)},
    )
    if is_platform_admin_view:
        # PlatformAdmin escape hatch — ADR-0016.3
        await session.execute(
            text("SELECT set_config('app.platform_admin_view', 'on', true)"),
        )
