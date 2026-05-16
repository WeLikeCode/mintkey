"""
Audit admin endpoints (PlatformAdmin only).

POST /v1/admin/audit/verify-chain          — on-demand audit chain verification.
POST /v1/admin/audit/acknowledge-tamper    — acknowledge a tampered chain event.

Architecture constraints:
  - PlatformAdmin check via X-Platform-Admin: true header (MVP stub).
  - All SQL uses bound parameters — no f-string interpolation — ADR-0008.
  - Hash chain logic re-implemented inline (pure hashlib) to avoid a cross-package
    import from audit-verify-job, which is a separate deployment unit.
  - Emits platform_admin.access via emit_platform_admin_access — ADR-0014.7.

Source: T-1.13.3; T-1.13.5; ADR-0008; ADR-0014.7; Req AUD-4; Req 15.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.deps import get_db_session
from admin_api.middleware.platform_admin_audit import emit_platform_admin_access
from mintkey_models.audit import audit_emit

router = APIRouter(prefix="/v1/admin/audit")

# ---------------------------------------------------------------------------
# PlatformAdmin guard (shared pattern from settings.py)
# ---------------------------------------------------------------------------

_PERMISSION_DENIED = JSONResponse(
    status_code=403,
    content={"mintkey:code": "permission_denied", "title": "Platform admin required"},
)


def _is_platform_admin(request: Request) -> bool:
    """
    MVP stub: returns True when X-Platform-Admin: true header is present.
    Source: T-1.13.1.
    """
    return request.headers.get("X-Platform-Admin") == "true"


# ---------------------------------------------------------------------------
# Pure hash-chain functions (re-implemented inline — no cross-package import)
# ADR-0014.7 / T-1.13.2 canonical algorithm.
# ---------------------------------------------------------------------------

_GENESIS_PREFIX = "mintkey-audit-genesis-v1:"


def _genesis_hash(tenant_id: str) -> bytes:
    return hashlib.sha256((_GENESIS_PREFIX + tenant_id).encode()).digest()


def _compute_event_hash(
    event_type: str, tenant_id: str, payload: dict, prev_hash: bytes
) -> bytes:
    canonical = json.dumps(
        {"event_type": event_type, "tenant_id": tenant_id, "payload": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical + prev_hash).digest()


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("/verify-chain")
async def verify_chain_endpoint(
    tenant_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    On-demand audit chain verification for a given tenant.

    Requires PlatformAdmin role (X-Platform-Admin: true in MVP).

    Returns:
      ok=true  → {"ok": true, "chain_length": N, "last_event_id": "...", "verified_at": "..."}
      ok=false → {"ok": false, "first_bad_event_id": "...", "expected_hash": "...", "actual_hash": "..."}

    Source: T-1.13.3; ADR-0014.7; Req AUD-4.
    """
    if not _is_platform_admin(request):
        return _PERMISSION_DENIED

    # Emit platform_admin.access before reading — ADR-0014.7 / T-1.13.4
    await emit_platform_admin_access(
        request=request,
        session=session,
        tenant_id=tenant_id,
        resource_type="audit_verify_chain",
    )

    # Fetch all audit events for the tenant in chain order — bound params only (ADR-0008)
    result = await session.execute(
        text(
            "SELECT id, event_type, tenant_id, payload, hash, prev_hash"
            " FROM audit_events"
            " WHERE tenant_id = :tenant_id"
            " ORDER BY id ASC"
        ),
        {"tenant_id": tenant_id},
    )
    rows = result.fetchall()

    if not rows:
        return JSONResponse(
            {
                "ok": True,
                "chain_length": 0,
                "last_event_id": None,
                "verified_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    # Verify chain
    expected_prev = _genesis_hash(tenant_id)

    for i, row in enumerate(rows):
        stored_prev: bytes = row.prev_hash
        stored_hash: bytes = row.hash
        payload: dict = row.payload if isinstance(row.payload, dict) else {}

        if stored_prev != expected_prev:
            computed = _compute_event_hash(row.event_type, str(row.tenant_id), payload, expected_prev)
            return JSONResponse(
                {
                    "ok": False,
                    "first_bad_event_id": row.id,
                    "expected_hash": expected_prev.hex(),
                    "actual_hash": stored_prev.hex(),
                }
            )

        computed = _compute_event_hash(row.event_type, str(row.tenant_id), payload, stored_prev)
        if stored_hash != computed:
            return JSONResponse(
                {
                    "ok": False,
                    "first_bad_event_id": row.id,
                    "expected_hash": computed.hex(),
                    "actual_hash": stored_hash.hex(),
                }
            )

        expected_prev = computed

    return JSONResponse(
        {
            "ok": True,
            "chain_length": len(rows),
            "last_event_id": rows[-1].id,
            "verified_at": datetime.now(timezone.utc).isoformat(),
        }
    )


@router.post("/acknowledge-tamper", status_code=201)
async def acknowledge_tamper(
    tenant_id: str,
    event_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Record acknowledgment of a tampered audit chain event.

    Requires PlatformAdmin role (X-Platform-Admin: true in MVP).

    Emits: audit.chain.tamper_acknowledged
    Source: T-1.13.5; Req 15; ADR-0014.7.
    """
    if not _is_platform_admin(request):
        return _PERMISSION_DENIED

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
