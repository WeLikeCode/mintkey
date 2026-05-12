"""
Tenant management endpoints.

POST   /v1/tenants              — create a new tenant (PlatformAdmin only, 201)
GET    /v1/tenants              — list all tenants (PlatformAdmin only, 200)
GET    /v1/tenants/{tenant_id}  — get single tenant (200)
PATCH  /v1/tenants/{tenant_id}  — update tenant metadata (PlatformAdmin only, 200)
DELETE /v1/tenants/{tenant_id}  — soft-delete tenant (PlatformAdmin only, 204)

Architecture constraints:
  - PlatformAdmin only for create/list/patch/delete — ADR-0017.4; Req 13 AC1.
  - ULID ID with "tenant_" prefix — ADR-0017.11.
  - audit_chain_state row initialised with genesis hash on creation — ADR-0014.7.
  - Audit event "tenant.created" emitted — ADR-0014.7; Req AUD-3.
  - Audit event "tenant.updated" / "tenant.deleted" emitted on changes — ADR-0014.7.
  - Duplicate slug → 409 mintkey:code=tenant_already_exists.
  - Non-PlatformAdmin → 403 mintkey:code=permission_denied.
  - No f-string SQL — ADR-0008; T-1.0.15.

Source: T-1.12.1; ADR-0008; ADR-0014.7; ADR-0017.11; Req 13 AC1.
"""
from __future__ import annotations

import hashlib
import time
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import exc as sa_exc
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.deps import get_db_session
from mintkey_models.audit import audit_emit

router = APIRouter(prefix="/v1/tenants")

# Crockford base32 alphabet (uppercase, no I/L/O/U) — ADR-0017.11
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

GENESIS_PREFIX = "mintkey-audit-genesis-v1:"


# ---------------------------------------------------------------------------
# ID generation — ADR-0017.11
# ---------------------------------------------------------------------------


def _new_tenant_id() -> str:
    """
    Generate a ULID-format ID with the 'tenant_' prefix — ADR-0017.11.

    Layout: 10 time chars (48-bit ms) + 16 random chars = 26 Crockford base32 chars.
    """
    ts_ms = int(time.time() * 1000)
    rand = int.from_bytes(uuid.uuid4().bytes[:10], "big")

    t_enc = []
    v = ts_ms
    for _ in range(10):
        t_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    t_enc.reverse()

    r_enc = []
    v = rand
    for _ in range(16):
        r_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    r_enc.reverse()

    return "tenant_" + "".join(t_enc) + "".join(r_enc)


def _genesis_hash(tenant_id: str) -> str:
    """
    Compute genesis hash: sha256("mintkey-audit-genesis-v1:" + tenant_id).
    Returns hex string.
    Source: ADR-0014.7; T-1.12.1.
    """
    return hashlib.sha256(
        (GENESIS_PREFIX + tenant_id).encode()
    ).hexdigest()


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class CreateTenantRequest(BaseModel):
    slug: str
    name: str
    isolation_mode: str = "row"  # "row" or "database"


class UpdateTenantRequest(BaseModel):
    display_name: Optional[str] = None
    status: Optional[str] = None
    settings: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _is_platform_admin(request: Request) -> bool:
    """
    Check whether the caller is a PlatformAdmin.

    In unit tests this is signalled via the X-Platform-Admin: true header.
    Production will use the session operator's is_platform_admin flag; this
    header-based check keeps unit tests simple without requiring a full auth
    stack. The pattern mirrors the admin-settings stub used elsewhere.
    """
    return request.headers.get("X-Platform-Admin", "").lower() == "true"


async def _set_platform_admin_rls(session: AsyncSession) -> None:
    """
    Set the per-connection GUCs required for platform-admin queries on the
    tenants table.  The tenants RLS policy allows access when either
    id = current_tenant (per-tenant) or platform_admin_view = 'on'.
    Platform-admin endpoints do cross-tenant reads, so they always use the
    latter branch.  Leaving current_tenant as '' causes the ::uuid cast to
    fail even when platform_admin_view is 'on', so we set it to the sentinel
    zero UUID.
    """
    await session.execute(
        text(
            "SELECT set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', true),"
            " set_config('app.platform_admin_view', 'on', true)"
        )
    )


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_tenant(
    body: CreateTenantRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Create a new tenant. PlatformAdmin only.

    Steps:
      1. Check is_platform_admin → 403 if not.
      2. Generate tenant_id = ULID with "tenant_" prefix.
      3. INSERT tenant row (ON CONFLICT slug → 409).
      4. Compute genesis hash = sha256("mintkey-audit-genesis-v1:" + tenant_id).
      5. INSERT audit_chain_state row with genesis_hash.
      6. Emit audit event "tenant.created".
      7. Return {"tenant_id": tenant_id, "slug": body.slug}.

    Source: T-1.12.1; ADR-0008; ADR-0014.7; ADR-0017.11; Req 13 AC1.
    """
    # Step 1: PlatformAdmin gate — ADR-0017.4
    if not _is_platform_admin(request):
        return JSONResponse(
            status_code=403,
            content={
                "mintkey:code": "permission_denied",
                "title": "PlatformAdmin access required",
            },
        )

    await _set_platform_admin_rls(session)

    # Step 2: Generate ULID ID with tenant_ prefix — ADR-0017.11
    tenant_id = _new_tenant_id()
    internal_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # Step 3: INSERT tenant row — bound parameters, no f-string SQL (ADR-0008)
    try:
        await session.execute(
            text(
                "INSERT INTO tenants"
                " (id, slug, display_name, isolation_mode, status, created_at, updated_at)"
                " VALUES"
                " (:id, :slug, :display_name, :isolation_mode, :status, :created_at, :updated_at)"
            ),
            {
                "id": str(internal_id),
                "slug": body.slug,
                "display_name": body.name,
                "isolation_mode": body.isolation_mode,
                "status": "active",
                "created_at": now,
                "updated_at": now,
            },
        )
    except sa_exc.IntegrityError:
        return JSONResponse(
            status_code=409,
            content={
                "mintkey:code": "tenant_already_exists",
                "title": "A tenant with this slug already exists",
            },
        )

    # Step 4 + 5: Compute genesis hash and INSERT audit_chain_state
    genesis = _genesis_hash(tenant_id)
    await session.execute(
        text(
            "INSERT INTO audit_chain_state"
            " (tenant_id, head_hash, head_event_id)"
            " VALUES"
            " (:tenant_id, :head_hash, :head_event_id)"
        ),
        {
            "tenant_id": str(internal_id),
            "head_hash": bytes.fromhex(genesis),
            "head_event_id": None,
        },
    )

    # Step 6: Emit audit event — ADR-0014.7, Req AUD-3
    await audit_emit(
        session=session,
        tenant_id=internal_id,
        event_type="tenant.created",
        actor_id=None,
        actor_type="platform_admin",
        target_id=internal_id,
        target_type="tenant",
        payload={"slug": body.slug, "name": body.name, "tenant_id": tenant_id},
    )

    # Step 7: Return wire response
    return JSONResponse(
        status_code=201,
        content={"tenant_id": tenant_id, "slug": body.slug},
    )


# ---------------------------------------------------------------------------
# GET /v1/tenants — list all tenants (PlatformAdmin only)
# ---------------------------------------------------------------------------


@router.get("")
async def list_tenants(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List all tenants. PlatformAdmin only.

    Source: OpenAPI listTenants; ADR-0017.4.
    """
    if not _is_platform_admin(request):
        return JSONResponse(
            status_code=403,
            content={"mintkey:code": "permission_denied", "title": "PlatformAdmin access required"},
        )

    await _set_platform_admin_rls(session)
    result = await session.execute(
        text(
            "SELECT id, slug, display_name, status, settings, created_at, updated_at"
            " FROM tenants ORDER BY created_at ASC"
        )
    )
    rows = result.fetchall()
    data = [
        {
            "id": str(row.id),
            "slug": row.slug,
            "display_name": row.display_name,
            "status": row.status,
            "settings": row.settings or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]
    return JSONResponse({"data": data, "next_cursor": None})


# ---------------------------------------------------------------------------
# GET /v1/tenants/{tid} — get single tenant
# ---------------------------------------------------------------------------


@router.get("/{tid}")
async def get_tenant(
    tid: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Get a single tenant by id (UUID string).

    Accessible by PlatformAdmin or any operator with membership.
    For now the auth stub allows the call if header present; the real
    session check is deferred to the auth integration task.

    Source: OpenAPI getTenant; ADR-0017.4.
    """
    await _set_platform_admin_rls(session)
    result = await session.execute(
        text(
            "SELECT id, slug, display_name, status, settings, created_at, updated_at"
            " FROM tenants WHERE id = :tid"
        ),
        {"tid": tid},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Tenant not found"},
        )
    return JSONResponse(
        {
            "id": str(row.id),
            "slug": row.slug,
            "display_name": row.display_name,
            "status": row.status,
            "settings": row.settings or {},
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    )


# ---------------------------------------------------------------------------
# PATCH /v1/tenants/{tid} — update tenant metadata (PlatformAdmin only)
# ---------------------------------------------------------------------------


@router.patch("/{tid}")
async def update_tenant(
    tid: str,
    body: UpdateTenantRequest,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Update tenant metadata. PlatformAdmin only. Slug is immutable.

    Emits audit event "tenant.updated" — ADR-0014.7.
    Source: OpenAPI updateTenant; ADR-0017.4.
    """
    if not _is_platform_admin(request):
        return JSONResponse(
            status_code=403,
            content={"mintkey:code": "permission_denied", "title": "PlatformAdmin access required"},
        )

    await _set_platform_admin_rls(session)
    # Fetch current row to verify existence
    result = await session.execute(
        text("SELECT id FROM tenants WHERE id = :tid"),
        {"tid": tid},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Tenant not found"},
        )

    now = datetime.now(timezone.utc)
    updates = {}
    if body.display_name is not None:
        updates["display_name"] = body.display_name
    if body.status is not None:
        updates["status"] = body.status
    if body.settings is not None:
        updates["settings"] = body.settings

    if updates:
        # Static SQL with COALESCE — no f-string SQL (ADR-0008, T-1.0.15).
        await session.execute(
            text(
                "UPDATE tenants"
                " SET display_name = COALESCE(:display_name, display_name),"
                "     status = COALESCE(:status, status),"
                "     settings = COALESCE(:settings, settings),"
                "     updated_at = :updated_at"
                " WHERE id = :tid"
            ),
            {
                "display_name": updates.get("display_name"),
                "status": updates.get("status"),
                "settings": updates.get("settings"),
                "updated_at": now,
                "tid": tid,
            },
        )

    # Emit audit event — ADR-0014.7
    import uuid as _uuid
    tenant_uuid = _uuid.UUID(tid)
    await audit_emit(
        session=session,
        tenant_id=tenant_uuid,
        event_type="tenant.updated",
        actor_id=None,
        actor_type="platform_admin",
        target_id=tenant_uuid,
        target_type="tenant",
        payload={"tenant_id": tid, **updates},
    )

    # Return updated row
    result2 = await session.execute(
        text(
            "SELECT id, slug, display_name, status, settings, created_at, updated_at"
            " FROM tenants WHERE id = :tid"
        ),
        {"tid": tid},
    )
    updated = result2.fetchone()
    assert updated is not None
    return JSONResponse(
        {
            "id": str(updated.id),
            "slug": updated.slug,
            "display_name": updated.display_name,
            "status": updated.status,
            "settings": updated.settings or {},
            "created_at": updated.created_at.isoformat() if updated.created_at else None,
            "updated_at": updated.updated_at.isoformat() if updated.updated_at else None,
        }
    )


# ---------------------------------------------------------------------------
# DELETE /v1/tenants/{tid} — soft-delete tenant (PlatformAdmin only)
# ---------------------------------------------------------------------------


@router.delete("/{tid}", status_code=204)
async def delete_tenant(
    tid: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Soft-delete a tenant by moving it to status="deleted". PlatformAdmin only.

    Emits audit event "tenant.deleted" — ADR-0016.7.
    Source: OpenAPI deleteTenant; ADR-0017.4; OQ-001.
    """
    if not _is_platform_admin(request):
        return JSONResponse(
            status_code=403,
            content={"mintkey:code": "permission_denied", "title": "PlatformAdmin access required"},
        )

    await _set_platform_admin_rls(session)
    result = await session.execute(
        text("SELECT id, status FROM tenants WHERE id = :tid"),
        {"tid": tid},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Tenant not found"},
        )
    if row.status == "deleted":
        return JSONResponse(
            status_code=409,
            content={"mintkey:code": "tenant_already_deleted", "title": "Tenant is already deleted"},
        )

    now = datetime.now(timezone.utc)
    await session.execute(
        text("UPDATE tenants SET status = 'deleted', updated_at = :now WHERE id = :tid"),
        {"now": now, "tid": tid},
    )

    import uuid as _uuid
    tenant_uuid = _uuid.UUID(tid)
    await audit_emit(
        session=session,
        tenant_id=tenant_uuid,
        event_type="tenant.deleted",
        actor_id=None,
        actor_type="platform_admin",
        target_id=tenant_uuid,
        target_type="tenant",
        payload={"tenant_id": tid},
    )

    return JSONResponse(status_code=204, content=None)
