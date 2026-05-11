"""
PlatformAdmin cross-tenant access audit helper.

Emits a "platform_admin.access" audit event whenever a PlatformAdmin performs
a cross-tenant read. Call emit_platform_admin_access() from each endpoint handler
that is accessible to PlatformAdmin.

Architecture constraints:
  - Checks X-Platform-Admin: true header (MVP stub).
  - Only emits when the header is present; no-ops for regular operators.
  - Uses the UUID(0) system tenant as the audit's owning tenant_id so the event
    appears in the platform-level audit chain, not a tenant's chain.
  - All audit fields conform to ADR-0014.7 (hash chain).

Source: T-1.13.4; ADR-0014.7; Req AUD-3.
"""
from __future__ import annotations

from uuid import UUID

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.audit import audit_emit

# Platform-level owning tenant for admin audit events (matches settings.py)
_SYSTEM_TENANT_ID = UUID("00000000-0000-0000-0000-000000000000")


async def emit_platform_admin_access(
    request: Request,
    session: AsyncSession,
    tenant_id: str,
    resource_type: str,
) -> None:
    """
    Emit a "platform_admin.access" audit event if the request carries the
    X-Platform-Admin: true header.  No-op otherwise.

    Args:
        request:       The incoming FastAPI request.
        session:       Active DB session (must be inside a transaction).
        tenant_id:     The tenant being viewed (from path param).
        resource_type: Human-readable label for the resource being read
                       (e.g. "audit_events", "audit_verify_chain").

    Source: T-1.13.4; ADR-0014.7.
    """
    if request.headers.get("X-Platform-Admin") != "true":
        return

    await audit_emit(
        session=session,
        tenant_id=_SYSTEM_TENANT_ID,
        event_type="platform_admin.access",
        actor_id=None,
        actor_type="platform_admin",
        target_id=None,
        target_type=resource_type,
        payload={
            "resource_type": resource_type,
            "viewed_tenant_id": tenant_id,
            "method": request.method,
            "path": request.url.path,
        },
    )
