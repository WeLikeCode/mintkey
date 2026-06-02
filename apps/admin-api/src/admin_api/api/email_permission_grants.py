"""
Email permission grant/revoke endpoints (feat/email-permission-grants).

POST   /v1/tenants/{tenant_id}/email-permission-grants          (201)
GET    /v1/tenants/{tenant_id}/email-permission-grants          (200, list)
GET    /v1/tenants/{tenant_id}/email-permission-grants/{gid}    (200, get)
DELETE /v1/tenants/{tenant_id}/email-permission-grants/{gid}    (204)

Design decisions (user-explicit):
  - Separate table from permission_grants — email_permission_grants.email_service_id
    FK's to email_services(id).  No polymorphic kind column; no extension of
    permission_grants.
  - Backend enforcement duplicated vs permission_grants (acceptable cost).

Architecture constraints:
  - Tenant context via bound parameters — ADR-0008, T-1.0.15.
  - Audit emit on every state change — ADR-0014.7.
  - All text(...) calls use static string literals + bound params — no f-strings.
  - Unique constraint violation → 409 Conflict.
  - Cross-tenant: agent or email_service not in tenant → 422.

Source: feat/email-permission-grants.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.deps import get_db_session
from admin_api.utils.wire_ids import wire_to_db_uuid
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context


def _decode_id(value: str, prefix: str) -> str:
    """Accept either bare UUID or wire-form ``<prefix>_<crockford>``; return UUID string.

    The admin-ui AgentCombobox / EmailServiceCombobox pass the wire form when a
    record is selected from the picker; raw curl callers may pass the UUID
    directly. Both must work — ADR-0017.11.
    """
    if value.startswith(prefix + "_"):
        return wire_to_db_uuid(value, prefix)
    return value

router = APIRouter(prefix="/v1/tenants/{tenant_id}/email-permission-grants")


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


class EmailPermissionGrantCreate(BaseModel):
    agent_id: str
    email_service_id: str


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_email_permission_grant(
    tenant_id: UUID,
    body: EmailPermissionGrantCreate,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Grant an agent access to an email service.

    - Validates agent + email_service both exist and belong to this tenant.
    - Unique constraint (tenant_id, agent_id, email_service_id) → 409 on duplicate.
    - Emits email_permission_grant.created audit event.

    Source: feat/email-permission-grants.
    """
    await set_tenant_context(session, tenant_id)

    # Decode wire-form prefixes (agent_<crockford>, esvc_<crockford>) → UUID.
    # AdminJS pickers (AgentCombobox, EmailServiceCombobox) pass the wire form;
    # raw curl callers may pass UUIDs directly. Accept both.
    try:
        agent_uuid = _decode_id(body.agent_id, "agent")
        email_service_uuid = _decode_id(body.email_service_id, "esvc")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "invalid_id",
                "title": "agent_id or email_service_id is not a valid wire-form or UUID",
            },
        )

    # Validate agent exists in this tenant
    agent_result = await session.execute(
        text("SELECT id FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": agent_uuid, "tid": str(tenant_id)},
    )
    if agent_result.fetchone() is None:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "not_found",
                "title": "Agent not found or does not belong to this tenant",
            },
        )

    # Validate email_service exists in this tenant
    esvc_result = await session.execute(
        text(
            "SELECT id FROM email_services"
            " WHERE id = :esid AND tenant_id = :tid AND deleted_at IS NULL"
        ),
        {"esid": email_service_uuid, "tid": str(tenant_id)},
    )
    if esvc_result.fetchone() is None:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "not_found",
                "title": "Email service not found or does not belong to this tenant",
            },
        )

    grant_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    try:
        await session.execute(
            text(
                "INSERT INTO email_permission_grants"
                " (id, tenant_id, agent_id, email_service_id, created_at, updated_at)"
                " VALUES"
                " (:id, :tenant_id, :agent_id, :email_service_id, :now, :now)"
            ),
            {
                "id": str(grant_id),
                "tenant_id": str(tenant_id),
                "agent_id": agent_uuid,
                "email_service_id": email_service_uuid,
                "now": now,
            },
        )
    except Exception as exc:
        exc_str = str(exc).lower()
        if "unique" in exc_str or "duplicate" in exc_str or "uq_email_permission_grants" in exc_str:
            return JSONResponse(
                status_code=409,
                content={
                    "mintkey:code": "already_exists",
                    "title": "An email permission grant for this agent and email service already exists",
                },
            )
        raise

    # Emit audit event (record the canonical UUIDs we wrote to the DB)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email_permission_grant.created",
        actor_id=None,
        actor_type="operator",
        target_id=grant_id,
        target_type="email_permission_grant",
        payload={
            "agent_id": agent_uuid,
            "email_service_id": email_service_uuid,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": str(grant_id),
            "tenant_id": str(tenant_id),
            "agent_id": agent_uuid,
            "email_service_id": email_service_uuid,
            "created_at": now.isoformat(),
            "updated_at": now.isoformat(),
        },
    )


@router.get("", status_code=200)
async def list_email_permission_grants(
    tenant_id: UUID,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List all email permission grants for a tenant.

    Returns {"grants": [...]} list.

    Source: feat/email-permission-grants.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, tenant_id, agent_id, email_service_id, created_at, updated_at"
            " FROM email_permission_grants"
            " WHERE tenant_id = :tid"
            " ORDER BY created_at"
        ),
        {"tid": str(tenant_id)},
    )
    rows = result.fetchall()

    grants = [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "agent_id": str(row.agent_id),
            "email_service_id": str(row.email_service_id),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]
    return JSONResponse({"grants": grants})


@router.get("/{grant_id}", status_code=200)
async def get_email_permission_grant(
    tenant_id: UUID,
    grant_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Get a single email permission grant by ID.

    Returns 404 if the grant does not exist or does not belong to this tenant.

    Source: feat/email-permission-grants.
    """
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, tenant_id, agent_id, email_service_id, created_at, updated_at"
            " FROM email_permission_grants"
            " WHERE id = :gid AND tenant_id = :tid"
        ),
        {"gid": str(grant_id), "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Email permission grant not found"},
        )

    return JSONResponse(
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "agent_id": str(row.agent_id),
            "email_service_id": str(row.email_service_id),
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
    )


@router.delete("/{grant_id}", status_code=204)
async def delete_email_permission_grant(
    tenant_id: UUID,
    grant_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """
    Revoke an email permission grant.

    Emits email_permission_grant.revoked audit event. Returns 204.

    Source: feat/email-permission-grants.
    """
    await set_tenant_context(session, tenant_id)

    # Fetch first so we can include agent_id + email_service_id in the audit payload
    fetch_result = await session.execute(
        text(
            "SELECT id, agent_id, email_service_id"
            " FROM email_permission_grants"
            " WHERE id = :gid AND tenant_id = :tid"
        ),
        {"gid": str(grant_id), "tid": str(tenant_id)},
    )
    row = fetch_result.fetchone()

    await session.execute(
        text(
            "DELETE FROM email_permission_grants"
            " WHERE id = :gid AND tenant_id = :tid"
        ),
        {"gid": str(grant_id), "tid": str(tenant_id)},
    )

    # Emit audit event regardless of whether the row existed (idempotent revoke)
    agent_id_val = str(row.agent_id) if row else grant_id
    esvc_id_val = str(row.email_service_id) if row else ""

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="email_permission_grant.revoked",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="email_permission_grant",
        payload={
            "grant_id": str(grant_id),
            "agent_id": agent_id_val,
            "email_service_id": esvc_id_val,
        },
    )

    return Response(status_code=204)
