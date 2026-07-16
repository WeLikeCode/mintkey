"""
Operator management endpoints — promote Keycloak realm-`mintkey` users to
Mintkey operators, list, update, and deactivate them.

GET    /v1/operators                — list operators (PlatformAdmin only, 200)
POST   /v1/operators                — create an operator (PlatformAdmin only, 201)
PATCH  /v1/operators/{operator_id}  — update operator role/status (PlatformAdmin only, 200)
DELETE /v1/operators/{operator_id}  — soft-deactivate operator (PlatformAdmin only, 204)

Architecture constraints (ADR-0031):
  - Flat, platform-level collection — PlatformAdmin only for every endpoint (D1).
    Session-based authz via require_platform_admin_session; cross-tenant reads/writes
    use the platform-admin RLS view (app.platform_admin_view='on'), like api/tenants.py.
  - Wire IDs: `op_`-prefixed ULID derived from operators.id via db_uuid_to_wire(id,"op") /
    wire_to_db_uuid(wire,"op") — no schema change (D2).
  - No Keycloak call at creation; oidc_sub is optional and binds lazily on first OIDC
    login (D3). admin-api holds no realm-admin credentials.
  - DELETE is a soft-deactivate (status='disabled'), idempotent 204 (D4).
  - operators has no updated_at column and this endpoint adds none (D5).
  - Every write emits a hash-chained audit event with actor_type="platform_admin",
    actor_id from the session, against the operator's home tenant_id (D6).
  - internal_password_hash is NEVER serialized in a response or audit payload (S-SEC-1).
  - No f-string SQL — bound parameters only (ADR-0008; T-1.0.15).

Source: ADR-0031; openspec/changes/operator-management; ADR-0008; ADR-0014.7; ADR-0017.10.
"""
from __future__ import annotations

import uuid
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import exc as sa_exc
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.sessions import get_session_context, require_platform_admin_session
from admin_api.db.deps import get_db_session
from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid
from mintkey_models.audit import audit_emit

router = APIRouter(prefix="/v1/operators")

# Column set selected/returned for every operator serialization is spelled out as
# a literal in each text() call below — internal_password_hash is deliberately
# excluded (S-SEC-1). The list is NOT interpolated via an f-string: the anti-SQL-
# injection gate (tests/acceptance/test_no_sql_injection.py) forbids any dynamic
# argument to text(), so every query uses adjacent string literals only (ADR-0008).


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateOperatorRequest(BaseModel):
    email: str
    tenant_id: str
    display_name: Optional[str] = None
    oidc_sub: Optional[str] = None
    is_platform_admin: bool = False


class UpdateOperatorRequest(BaseModel):
    display_name: Optional[str] = None
    is_platform_admin: Optional[bool] = None
    status: Optional[Literal["active", "disabled"]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _set_platform_admin_rls(session: AsyncSession) -> None:
    """
    Set the per-connection GUCs required for platform-admin queries on the
    operators table.  The operators RLS policy allows access when either
    tenant_id = current_tenant (per-tenant) or platform_admin_view = 'on'.
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


def _operator_row_to_dict(row: Any) -> dict[str, Any]:
    """Map a DB row to the wire representation — never includes internal_password_hash.

    Emits `op_`/`tenant_` Crockford ULID wire-form IDs (ADR-0017.10 / D2).
    """
    return {
        "id": db_uuid_to_wire(row.id, "op"),
        "tenant_id": db_uuid_to_wire(row.tenant_id, "tenant"),
        "email": row.email,
        "display_name": row.display_name,
        "oidc_sub": row.oidc_sub,
        "oidc_provider": row.oidc_provider,
        "is_platform_admin": bool(row.is_platform_admin),
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def _actor_id(ctx: Any) -> Optional[uuid.UUID]:
    """Extract the session operator_id (audit actor) — None when unavailable (D6)."""
    if ctx is None or ctx.operator_id is None:
        return None
    return uuid.UUID(str(ctx.operator_id))


# ---------------------------------------------------------------------------
# GET /v1/operators — list operators (PlatformAdmin only)
# ---------------------------------------------------------------------------


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input cannot glob-match unexpectedly."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
async def list_operators(
    q: Optional[str] = None,
    tenant_id: Optional[str] = None,
    _authz: None = Depends(require_platform_admin_session),
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List operators across all tenants. PlatformAdmin only.

    Optional query parameters:
      q         — case-insensitive substring search on email or display_name.
      tenant_id — restrict to operators whose home tenant matches (tenant_ wire ID
                  or bare UUID).

    Source: ADR-0031 D1; openapi.yaml listOperators.
    """
    await _set_platform_admin_rls(session)

    # Decode an optional tenant_id filter (accepts tenant_ wire form or bare UUID).
    tenant_uuid: Optional[str] = None
    if tenant_id is not None:
        try:
            tenant_uuid = wire_to_db_uuid(tenant_id, "tenant")
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={"mintkey:code": "invalid_id", "title": "Invalid tenant_id"},
            )

    q_pattern: Optional[str] = None
    if q is not None:
        q_pattern = f"%{_escape_like(q)}%"

    # Explicit branches so each text() call has a constant (literal) argument (ADR-0008).
    if q_pattern is not None and tenant_uuid is not None:
        result = await session.execute(
            text(
                "SELECT id, tenant_id, email, display_name, oidc_sub, oidc_provider,"
                " is_platform_admin, status, created_at FROM operators"
                " WHERE tenant_id = :tenant_id"
                " AND (email ILIKE :pat ESCAPE '\\' OR display_name ILIKE :pat ESCAPE '\\')"
                " ORDER BY created_at ASC"
            ),
            {"tenant_id": tenant_uuid, "pat": q_pattern},
        )
    elif q_pattern is not None:
        result = await session.execute(
            text(
                "SELECT id, tenant_id, email, display_name, oidc_sub, oidc_provider,"
                " is_platform_admin, status, created_at FROM operators"
                " WHERE (email ILIKE :pat ESCAPE '\\' OR display_name ILIKE :pat ESCAPE '\\')"
                " ORDER BY created_at ASC"
            ),
            {"pat": q_pattern},
        )
    elif tenant_uuid is not None:
        result = await session.execute(
            text(
                "SELECT id, tenant_id, email, display_name, oidc_sub, oidc_provider,"
                " is_platform_admin, status, created_at FROM operators"
                " WHERE tenant_id = :tenant_id"
                " ORDER BY created_at ASC"
            ),
            {"tenant_id": tenant_uuid},
        )
    else:
        result = await session.execute(
            text(
                "SELECT id, tenant_id, email, display_name, oidc_sub, oidc_provider,"
                " is_platform_admin, status, created_at FROM operators"
                " ORDER BY created_at ASC"
            )
        )

    rows = result.fetchall()
    data = [_operator_row_to_dict(r) for r in rows]
    return JSONResponse({"data": data, "next_cursor": None})


# ---------------------------------------------------------------------------
# POST /v1/operators — create an operator (PlatformAdmin only)
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_operator(
    body: CreateOperatorRequest,
    _authz: None = Depends(require_platform_admin_session),
    session: AsyncSession = Depends(get_db_session),
    ctx: Any = Depends(get_session_context),
) -> JSONResponse:
    """
    Promote a (Keycloak realm-`mintkey`) user to a Mintkey operator. PlatformAdmin only.

    No Keycloak call is made — oidc_sub is optional and binds lazily on first OIDC
    login (ADR-0031 D3). The operator is also given an Admin membership in its home
    tenant, mirroring the seed-job path. Emits operator.created.

    Duplicate (tenant_id, email) or oidc_sub → 409 duplicate_resource.

    Source: ADR-0031 D3/D6; openapi.yaml createOperator; apps/seed-job/create_operator.py.
    """
    await _set_platform_admin_rls(session)

    # Decode the home tenant wire ID → UUID string — 422 on failure.
    try:
        tenant_uuid = wire_to_db_uuid(body.tenant_id, "tenant")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid tenant_id"},
        )

    # INSERT the operator row. internal_password_hash is NULL — S-SEC-1.
    try:
        result = await session.execute(
            text(
                "INSERT INTO operators"
                " (tenant_id, email, display_name, internal_password_hash, oidc_sub,"
                "  is_platform_admin, status)"
                " VALUES"
                " (:tenant_id, :email, :display_name, NULL, :oidc_sub,"
                "  :is_platform_admin, 'active')"
                " RETURNING id, tenant_id, email, display_name, oidc_sub, oidc_provider,"
                " is_platform_admin, status, created_at"
            ),
            {
                "tenant_id": tenant_uuid,
                "email": body.email,
                "display_name": body.display_name,
                "oidc_sub": body.oidc_sub,
                "is_platform_admin": body.is_platform_admin,
            },
        )
    except sa_exc.IntegrityError:
        return JSONResponse(
            status_code=409,
            content={
                "mintkey:code": "duplicate_resource",
                "title": "An operator with this email or oidc_sub already exists",
            },
        )

    row = result.fetchone()
    assert row is not None
    operator_uuid = uuid.UUID(str(row.id))
    tenant_id_uuid = uuid.UUID(tenant_uuid)

    # Give the operator an Admin membership in its home tenant (mirrors seed-job).
    await session.execute(
        text(
            "INSERT INTO operator_tenant_memberships (operator_id, tenant_id, role)"
            " VALUES (:operator_id, :tenant_id, 'Admin')"
            " ON CONFLICT (operator_id, tenant_id) DO NOTHING"
        ),
        {"operator_id": str(operator_uuid), "tenant_id": tenant_uuid},
    )

    # Emit audit event — actor from session, no password/hash in payload (D6, S-SEC-1).
    await audit_emit(
        session=session,
        tenant_id=tenant_id_uuid,
        event_type="operator.created",
        actor_id=_actor_id(ctx),
        actor_type="platform_admin",
        target_id=operator_uuid,
        target_type="operator",
        payload={
            "operator_id": db_uuid_to_wire(operator_uuid, "operator"),
            "username": body.display_name or body.email,
            "email": body.email,
            "platform_admin": body.is_platform_admin,
        },
    )

    return JSONResponse(status_code=201, content=_operator_row_to_dict(row))


# ---------------------------------------------------------------------------
# PATCH /v1/operators/{operator_id} — update role/status (PlatformAdmin only)
# ---------------------------------------------------------------------------


@router.patch("/{operator_id}")
async def update_operator(
    operator_id: str,
    body: UpdateOperatorRequest,
    _authz: None = Depends(require_platform_admin_session),
    session: AsyncSession = Depends(get_db_session),
    ctx: Any = Depends(get_session_context),
) -> JSONResponse:
    """
    Update an operator's display_name / is_platform_admin / status. PlatformAdmin only.

    operators has no updated_at column — none is set (ADR-0031 D5). Emits operator.updated.

    Source: ADR-0031 D5/D6; openapi.yaml updateOperator.
    """
    try:
        operator_uuid = wire_to_db_uuid(operator_id, "op")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid operator_id"},
        )
    await _set_platform_admin_rls(session)

    result = await session.execute(
        text(
            "SELECT id, tenant_id, email, display_name, oidc_sub, oidc_provider,"
            " is_platform_admin, status, created_at FROM operators WHERE id = :oid"
        ),
        {"oid": operator_uuid},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Operator not found"},
        )

    # Static COALESCE SQL — no updated_at, no f-string SQL (D5; ADR-0008).
    updated = await session.execute(
        text(
            "UPDATE operators SET"
            "   display_name = COALESCE(:display_name, display_name),"
            "   is_platform_admin = COALESCE(:is_platform_admin, is_platform_admin),"
            "   status = COALESCE(:status, status)"
            " WHERE id = :oid"
            " RETURNING id, tenant_id, email, display_name, oidc_sub, oidc_provider,"
            " is_platform_admin, status, created_at"
        ),
        {
            "display_name": body.display_name,
            "is_platform_admin": body.is_platform_admin,
            "status": body.status,
            "oid": operator_uuid,
        },
    )
    updated_row = updated.fetchone()
    assert updated_row is not None

    tenant_id_uuid = uuid.UUID(str(row.tenant_id))
    await audit_emit(
        session=session,
        tenant_id=tenant_id_uuid,
        event_type="operator.updated",
        actor_id=_actor_id(ctx),
        actor_type="platform_admin",
        target_id=uuid.UUID(str(row.id)),
        target_type="operator",
        payload={
            "operator_id": db_uuid_to_wire(row.id, "operator"),
            "fields_changed": [
                field
                for field, value in (
                    ("display_name", body.display_name),
                    ("is_platform_admin", body.is_platform_admin),
                    ("status", body.status),
                )
                if value is not None
            ],
        },
    )

    return JSONResponse(_operator_row_to_dict(updated_row))


# ---------------------------------------------------------------------------
# DELETE /v1/operators/{operator_id} — soft-deactivate (PlatformAdmin only)
# ---------------------------------------------------------------------------


@router.delete("/{operator_id}", status_code=204)
async def delete_operator(
    operator_id: str,
    _authz: None = Depends(require_platform_admin_session),
    session: AsyncSession = Depends(get_db_session),
    ctx: Any = Depends(get_session_context),
) -> JSONResponse:
    """
    Soft-deactivate an operator by moving it to status="disabled". PlatformAdmin only.

    Idempotent: an already-disabled operator still returns 204 but emits no audit
    event (ADR-0031 D4). Never hard-deletes — sessions / memberships FK-reference
    operators(id). Emits operator.deleted when a row changed.

    Source: ADR-0031 D4/D6; openapi.yaml deleteOperator.
    """
    try:
        operator_uuid = wire_to_db_uuid(operator_id, "op")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid operator_id"},
        )
    await _set_platform_admin_rls(session)

    result = await session.execute(
        text("SELECT id, tenant_id, status FROM operators WHERE id = :oid"),
        {"oid": operator_uuid},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Operator not found"},
        )

    # Idempotent: already disabled → 204 with no state change and no audit event.
    if row.status != "disabled":
        await session.execute(
            text("UPDATE operators SET status = 'disabled' WHERE id = :oid"),
            {"oid": operator_uuid},
        )
        await audit_emit(
            session=session,
            tenant_id=uuid.UUID(str(row.tenant_id)),
            event_type="operator.deleted",
            actor_id=_actor_id(ctx),
            actor_type="platform_admin",
            target_id=uuid.UUID(str(row.id)),
            target_type="operator",
            payload={"operator_id": db_uuid_to_wire(row.id, "operator")},
        )

    return JSONResponse(status_code=204, content=None)
