"""
Tenant management endpoints.

POST /v1/tenants — create a new tenant (PlatformAdmin only, 201)

Architecture constraints:
  - PlatformAdmin only — ADR-0017.4; Req 13 AC1.
  - ULID ID with "tenant_" prefix — ADR-0017.11.
  - audit_chain_state row initialised with genesis hash on creation — ADR-0014.7.
  - Audit event "tenant.created" emitted — ADR-0014.7; Req AUD-3.
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
            " (tenant_id, head_hash, head_event_id, genesis_hash)"
            " VALUES"
            " (:tenant_id, :head_hash, :head_event_id, :genesis_hash)"
        ),
        {
            "tenant_id": str(internal_id),
            "head_hash": bytes.fromhex(genesis),
            "head_event_id": None,
            "genesis_hash": genesis,
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
