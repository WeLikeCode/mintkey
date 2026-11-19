"""
Audit admin endpoints (PlatformAdmin only).

POST /v1/admin/audit/verify-chain          — on-demand audit chain verification.
POST /v1/admin/audit/acknowledge-tamper    — acknowledge a tampered chain event.

Architecture constraints:
  - PlatformAdmin check via session (ADR-0027 §D2) — X-Platform-Admin header no longer trusted.
  - All SQL uses bound parameters — no f-string interpolation — ADR-0008.
  - Hash chain logic re-implemented inline (pure hashlib) to avoid a cross-package
    import from audit-verify-job, which is a separate deployment unit.
  - Emits platform_admin.access via emit_platform_admin_access — ADR-0014.7.

Source: T-1.13.3; T-1.13.5; ADR-0008; ADR-0014.7; Req AUD-4; Req 15; ADR-0027 §D2.
"""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.sessions import require_platform_admin_session
from admin_api.db.deps import get_db_session
from admin_api.middleware.platform_admin_audit import emit_platform_admin_access
from mintkey_models.audit import audit_emit
from mintkey_models.audit_hash import chain_event_from_row, verify_events

router = APIRouter(prefix="/v1/admin/audit")

# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/verify-chain")
async def verify_chain_endpoint(
    tenant_id: str,
    request: Request,
    _authz: None = Depends(require_platform_admin_session),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    """
    On-demand audit chain verification for a given tenant.

    Requires PlatformAdmin role (session-based — ADR-0027 §D2).

    Returns:
      ok=true  → {"ok": true, "chain_length": N, "last_event_id": "...", "verified_at": "..."}
      ok=false → {"ok": false, "first_bad_event_id": "...", "expected_hash": "...", "actual_hash": "..."}

    Source: T-1.13.3; ADR-0014.7; Req AUD-4.
    """
    # Emit platform_admin.access before reading — ADR-0014.7 / T-1.13.4
    await emit_platform_admin_access(
        request=request,
        session=session,
        tenant_id=tenant_id,
        resource_type="audit_verify_chain",
    )

    # Fetch all 13 stored columns for the tenant in chain order — bound params only (ADR-0008)
    result = await session.execute(
        text(
            "SELECT id, tenant_id, event_type, actor_id, actor_type,"
            " target_id, target_type, payload, at, prev_hash, hash,"
            " request_id, trace_id"
            " FROM audit_events"
            " WHERE tenant_id = :tenant_id"
            " ORDER BY at ASC, id ASC"
        ),
        {"tenant_id": tenant_id},
    )
    rows = result.fetchall()

    chain = verify_events([chain_event_from_row(row) for row in rows])

    if chain.ok:
        return JSONResponse(
            {
                "ok": True,
                "chain_length": chain.chain_length,
                "last_event_id": chain.last_event_id,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    return JSONResponse(
        {
            "ok": False,
            "first_bad_event_id": chain.first_bad_event_id,
            "expected_hash": (
                chain.expected_hash.hex()
                if chain.expected_hash is not None
                else None
            ),
            "actual_hash": (
                chain.actual_hash.hex()
                if chain.actual_hash is not None
                else None
            ),
        }
    )


@router.post("/acknowledge-tamper", status_code=201)
async def acknowledge_tamper(
    tenant_id: str,
    event_id: str,
    _authz: None = Depends(require_platform_admin_session),
    session: AsyncSession = Depends(get_db_session, scope="function"),
) -> JSONResponse:
    """
    Record acknowledgment of a tampered audit chain event.

    Requires PlatformAdmin role (session-based — ADR-0027 §D2).

    Emits: audit.chain.tamper_acknowledged
    Source: T-1.13.5; Req 15; ADR-0014.7.
    """
    # Verify the tenant exists — bound parameters only (ADR-0008)
    result = await session.execute(
        text("SELECT id FROM tenants WHERE id = :tenant_id"),
        {"tenant_id": tenant_id},
    )
    if result.fetchone() is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "tenant_not_found"},
        )

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="audit.chain.tamper_acknowledged",
        actor_id=None,
        actor_type="platform_admin",
        target_id=event_id,
        target_type="audit_event",
        payload={
            "event_id": event_id,
            "tenant_id": tenant_id,
            "acknowledged_by": "platform_admin",
        },
    )

    return JSONResponse(
        status_code=201,
        content={"acknowledged": True, "event_id": event_id, "tenant_id": tenant_id},
    )
