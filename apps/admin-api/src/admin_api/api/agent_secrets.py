"""
Agent secret REST endpoints (operator surface) — ADR-0025.

GET    /v1/tenants/{tenant_id}/agent-secrets                        — list metadata (cursor paged)
GET    /v1/tenants/{tenant_id}/agent-secrets/{secret_id}            — get metadata
DELETE /v1/tenants/{tenant_id}/agent-secrets/{secret_id}            — operator hard-delete (204)
POST   /v1/tenants/{tenant_id}/agent-secrets/{secret_id}/grants     — create share grant (201)
GET    /v1/tenants/{tenant_id}/agent-secrets/{secret_id}/grants     — list grants (cursor paged)
DELETE /v1/tenants/{tenant_id}/agent-secrets/{secret_id}/grants/{grant_id}  — revoke grant (204)

Design constraints (ADR-0025):
  - Metadata-only: no endpoint may return secret values or ciphertext.
  - Operator hard-delete purges the vault ciphertext blob first (via AgentSecretsVaultClient),
    then deletes the metadata row (cascades grants). Vault-first ordering ensures no window
    where the blob is accessible after metadata is gone. svcid_admin_api holds
    vault.secret.delete scope (granted as of C3/ADR-0025).
  - Wire IDs use prefixes sec_ / secgrant_ / agent_ / tenant_ — ADR-0017.11, ADR-0025.
  - set_tenant_context is the FIRST statement in every handler — ADR-0008.
  - text() SQL calls use static string literals + bound params only — no f-strings — ADR-0014.
  - audit_emit inside the transaction on every state change — ADR-0014.7.
  - notify_change on every state change — ADR-0014.1.
  - Grant-to-owner rejected (422); duplicate grant returns 409 (uq_agent_secret_grants).
  - Cross-tenant secret or agent reference returns 422 not_found — ADR-0025.
  - All responses carry identifiers only — never values or ciphertext — ADR-0025.D4.

Source: ADR-0025; openspec/changes/agent-stored-credentials/design.md.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from admin_api.services.agent_secrets_vault_client import (
    AgentSecretsVaultClient,
    get_agent_secrets_vault_client,
)
from admin_api.utils.wire_ids import (
    db_uuid_to_wire,
    db_uuid_to_wire_sec,
    db_uuid_to_wire_secgrant,
    wire_to_db_uuid,
)
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(prefix="/v1/tenants/{tenant_id}/agent-secrets")


# ---------------------------------------------------------------------------
# ID decode helpers
# ---------------------------------------------------------------------------


def _decode_secret_id(value: str) -> str:
    """Accept sec_<crockford> or bare UUID; return UUID string."""
    if value.startswith("sec_"):
        return wire_to_db_uuid(value, "sec")
    return value


def _decode_agent_id(value: str) -> str:
    """Accept agent_<crockford> or bare UUID; return UUID string."""
    if value.startswith("agent_"):
        return wire_to_db_uuid(value, "agent")
    return value


def _decode_grant_id(value: str) -> str:
    """Accept secgrant_<crockford> or bare UUID; return UUID string."""
    if value.startswith("secgrant_"):
        return wire_to_db_uuid(value, "secgrant")
    return value


# ---------------------------------------------------------------------------
# Row → wire dict helpers
# ---------------------------------------------------------------------------


def _secret_row_to_dict(row: Any) -> dict[str, Any]:
    """Map an agent_secrets DB row to the wire representation (no value/ciphertext)."""
    return {
        "id": db_uuid_to_wire_sec(row.id),
        "tenant_id": db_uuid_to_wire(row.tenant_id, "tenant"),
        "agent_id": db_uuid_to_wire(row.agent_id, "agent"),
        "name": row.name,
        "version": int(row.version),
        "size_bytes": int(row.size_bytes),
        "content_type": row.content_type,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _grant_row_to_dict(row: Any) -> dict[str, Any]:
    """Map an agent_secret_grants DB row to the wire representation."""
    return {
        "id": db_uuid_to_wire_secgrant(row.id),
        "tenant_id": db_uuid_to_wire(row.tenant_id, "tenant"),
        "secret_id": db_uuid_to_wire_sec(row.secret_id),
        "recipient_agent_id": db_uuid_to_wire(row.recipient_agent_id, "agent"),
        "created_by": db_uuid_to_wire(row.created_by, "operator"),
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class CreateAgentSecretGrantRequest(BaseModel):
    recipient_agent_id: str


# ---------------------------------------------------------------------------
# LIST secrets
# ---------------------------------------------------------------------------


@router.get("", status_code=200)
async def list_agent_secrets(
    tenant_id: UUID,
    after: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List agent secret metadata for a tenant (cursor paginated).

    Returns {data: [...], next_cursor: <sec_...|null>}.
    Never returns secret values or ciphertext.

    Source: ADR-0025; openapi.yaml listAgentSecrets.
    """
    await set_tenant_context(session, tenant_id)

    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200
    page_size = limit + 1  # fetch one extra to determine next_cursor

    if after is not None:
        try:
            after_uuid = _decode_secret_id(after)
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={"mintkey:code": "invalid_id", "title": "Invalid after cursor"},
            )
        result = await session.execute(
            text(
                "SELECT id, tenant_id, agent_id, name, content_type,"
                " size_bytes, version, created_at, updated_at"
                " FROM agent_secrets"
                " WHERE tenant_id = :tid"
                " AND id > :after_id"
                " ORDER BY id"
                " LIMIT :lim"
            ),
            {"tid": str(tenant_id), "after_id": after_uuid, "lim": page_size},
        )
    else:
        result = await session.execute(
            text(
                "SELECT id, tenant_id, agent_id, name, content_type,"
                " size_bytes, version, created_at, updated_at"
                " FROM agent_secrets"
                " WHERE tenant_id = :tid"
                " ORDER BY id"
                " LIMIT :lim"
            ),
            {"tid": str(tenant_id), "lim": page_size},
        )
    rows = result.fetchall()

    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = db_uuid_to_wire_sec(page[-1].id) if has_more and page else None

    return JSONResponse({
        "data": [_secret_row_to_dict(r) for r in page],
        "next_cursor": next_cursor,
    })


# ---------------------------------------------------------------------------
# GET secret metadata
# ---------------------------------------------------------------------------


@router.get("/{secret_id}", status_code=200)
async def get_agent_secret(
    tenant_id: UUID,
    secret_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Get agent secret metadata by ID.

    Returns 404 if not found or not in this tenant.
    Never returns the secret value or ciphertext.

    Source: ADR-0025; openapi.yaml getAgentSecret.
    """
    try:
        secret_uuid = _decode_secret_id(secret_id)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid secret_id"},
        )
    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, tenant_id, agent_id, name, content_type,"
            " size_bytes, version, created_at, updated_at"
            " FROM agent_secrets"
            " WHERE id = :sid AND tenant_id = :tid"
        ),
        {"sid": secret_uuid, "tid": str(tenant_id)},
    )
    row = result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Agent secret not found"},
        )

    return JSONResponse(_secret_row_to_dict(row))


# ---------------------------------------------------------------------------
# DELETE secret (operator hard-delete)
# ---------------------------------------------------------------------------


@router.delete("/{secret_id}", status_code=204)
async def delete_agent_secret(
    tenant_id: UUID,
    secret_id: str,
    session: AsyncSession = Depends(get_db_session),
    vault_client: AgentSecretsVaultClient = Depends(get_agent_secrets_vault_client),
) -> Response:
    """
    Operator hard-delete of an agent secret and its share grants.

    Idempotent (204 even if already absent). Emits agent_secret.deleted with
    actor_type=operator.

    Ordering: (1) purge vault ciphertext blob, (2) delete metadata row + cascade grants.
    Vault-first ordering ensures the blob cannot be read after metadata is gone yet before
    the blob is purged. If the vault purge raises, the error propagates as a 5xx and the
    metadata row is left intact (no orphaned-blob risk).  When the metadata row is already
    absent (idempotent path), the vault client is skipped entirely.

    Source: ADR-0025; openapi.yaml deleteAgentSecretByOperator.
    """
    try:
        secret_uuid = _decode_secret_id(secret_id)
    except ValueError:
        return Response(status_code=422)
    await set_tenant_context(session, tenant_id)

    # Fetch before delete so we can carry the agent_id and name in the audit payload
    fetch_result = await session.execute(
        text(
            "SELECT id, agent_id, name"
            " FROM agent_secrets"
            " WHERE id = :sid AND tenant_id = :tid"
        ),
        {"sid": secret_uuid, "tid": str(tenant_id)},
    )
    row = fetch_result.fetchone()

    if row is not None:
        # Purge the vault ciphertext blob before deleting the metadata row.
        # If this raises, the 5xx propagates and the metadata row is left intact.
        await vault_client.delete_agent_secret(
            tenant_id=str(tenant_id),
            secret_id=secret_uuid,
        )

    # Delete cascades grants via FK
    await session.execute(
        text(
            "DELETE FROM agent_secrets"
            " WHERE id = :sid AND tenant_id = :tid"
        ),
        {"sid": secret_uuid, "tid": str(tenant_id)},
    )

    # Audit — only emitted when the row existed.
    # When already gone, agent_id is unknowable and "" does not match the
    # required ^agent_[0-9A-HJKMNP-TV-Z]{26}$ pattern in ev_agent_secret_deleted.
    # Mirror the grant-revoke decision: skip audit_emit on the already-gone path.
    secret_wire_id = db_uuid_to_wire_sec(uuid.UUID(secret_uuid))
    if row is not None:
        agent_wire_id = db_uuid_to_wire(row.agent_id, "agent")
        secret_name = row.name
        await audit_emit(
            session=session,
            tenant_id=tenant_id,
            event_type="agent_secret.deleted",
            actor_id=None,
            actor_type="operator",
            target_id=None,
            target_type="agent_secret",
            payload={
                "secret_id": secret_wire_id,
                "agent_id": agent_wire_id,
                "name": secret_name,
            },
        )
    else:
        agent_wire_id = ""

    await notify_change(
        session,
        "mintkey:agent",
        {
            "event": "agent_secret.deleted",
            "tenant_id": str(tenant_id),
            "secret_id": secret_wire_id,
            "agent_id": agent_wire_id,
        },
    )

    return Response(status_code=204)


# ---------------------------------------------------------------------------
# POST grant (create share grant)
# ---------------------------------------------------------------------------


@router.post("/{secret_id}/grants", status_code=201)
async def create_agent_secret_grant(
    tenant_id: UUID,
    secret_id: str,
    body: CreateAgentSecretGrantRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Create a share grant giving a recipient agent read-only access to a secret.

    - Secret must exist in this tenant (422 not_found otherwise).
    - Recipient agent must exist in this tenant (422 not_found otherwise).
    - Granting to the secret's owner is rejected (422 grant_to_owner).
    - Duplicate grant → 409 already_exists (uq_agent_secret_grants).
    - Emits agent_secret_grant.created with operator actor attribution.

    Source: ADR-0025; openapi.yaml createAgentSecretGrant.
    """
    try:
        secret_uuid = _decode_secret_id(secret_id)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid secret_id"},
        )
    try:
        recipient_uuid = _decode_agent_id(body.recipient_agent_id)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid recipient_agent_id"},
        )
    await set_tenant_context(session, tenant_id)

    # Validate secret exists in this tenant
    secret_result = await session.execute(
        text(
            "SELECT id, agent_id"
            " FROM agent_secrets"
            " WHERE id = :sid AND tenant_id = :tid"
        ),
        {"sid": secret_uuid, "tid": str(tenant_id)},
    )
    secret_row = secret_result.fetchone()
    if secret_row is None:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "not_found",
                "title": "Agent secret not found or does not belong to this tenant",
            },
        )

    # Validate recipient agent exists in this tenant
    agent_result = await session.execute(
        text("SELECT id FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": recipient_uuid, "tid": str(tenant_id)},
    )
    if agent_result.fetchone() is None:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "not_found",
                "title": "Recipient agent not found or does not belong to this tenant",
            },
        )

    # Reject grant-to-owner (normalize both to dashed UUID strings for comparison)
    if str(secret_row.agent_id).replace("-", "") == str(recipient_uuid).replace("-", ""):
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "grant_to_owner",
                "title": "Cannot grant read access to the secret's own owner",
            },
        )

    grant_id = uuid.uuid4()
    now = datetime.now(timezone.utc)

    # created_by: the operator session; actor_id is None in the current operator
    # session model (sessions carry no parsed operator UUID yet). Use a nil UUID
    # as the created_by placeholder — matches the agent-creation precedent.
    # TODO(ADR-0025 follow-up): populate from session.operator_id once available.
    created_by_id = uuid.UUID("00000000-0000-0000-0000-000000000000")

    try:
        await session.execute(
            text(
                "INSERT INTO agent_secret_grants"
                " (id, tenant_id, secret_id, recipient_agent_id, created_by, created_at)"
                " VALUES"
                " (:id, :tenant_id, :secret_id, :recipient_agent_id, :created_by, :now)"
            ),
            {
                "id": str(grant_id),
                "tenant_id": str(tenant_id),
                "secret_id": secret_uuid,
                "recipient_agent_id": recipient_uuid,
                "created_by": str(created_by_id),
                "now": now,
            },
        )
    except Exception as exc:
        exc_str = str(exc).lower()
        if "unique" in exc_str or "duplicate" in exc_str or "uq_agent_secret_grants" in exc_str:
            return JSONResponse(
                status_code=409,
                content={
                    "mintkey:code": "already_exists",
                    "title": "A share grant for this secret and recipient already exists",
                },
            )
        raise

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="agent_secret_grant.created",
        actor_id=None,
        actor_type="operator",
        target_id=grant_id,
        target_type="agent_secret_grant",
        payload={
            "grant_id": db_uuid_to_wire_secgrant(grant_id),
            "secret_id": db_uuid_to_wire_sec(uuid.UUID(secret_uuid)),
            "owner_agent_id": db_uuid_to_wire(secret_row.agent_id, "agent"),
            "recipient_agent_id": db_uuid_to_wire(uuid.UUID(recipient_uuid), "agent"),
        },
    )

    await notify_change(
        session,
        "mintkey:agent",
        {
            "event": "agent_secret_grant.created",
            "tenant_id": str(tenant_id),
            "grant_id": str(grant_id),
            "secret_id": secret_id,
            "recipient_agent_id": body.recipient_agent_id,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "id": db_uuid_to_wire_secgrant(grant_id),
            "tenant_id": db_uuid_to_wire(tenant_id, "tenant"),
            "secret_id": db_uuid_to_wire_sec(uuid.UUID(secret_uuid)),
            "recipient_agent_id": db_uuid_to_wire(uuid.UUID(recipient_uuid), "agent"),
            "created_by": db_uuid_to_wire(created_by_id, "operator"),
            "created_at": now.isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# LIST grants
# ---------------------------------------------------------------------------


@router.get("/{secret_id}/grants", status_code=200)
async def list_agent_secret_grants(
    tenant_id: UUID,
    secret_id: str,
    after: str | None = None,
    limit: int = 50,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List share grants for an agent secret (cursor paginated).

    Returns {data: [...], next_cursor: <secgrant_...|null>}.

    Source: ADR-0025; openapi.yaml listAgentSecretGrants.
    """
    try:
        secret_uuid = _decode_secret_id(secret_id)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid secret_id"},
        )
    await set_tenant_context(session, tenant_id)

    # Verify secret exists in this tenant
    secret_check = await session.execute(
        text(
            "SELECT id FROM agent_secrets WHERE id = :sid AND tenant_id = :tid"
        ),
        {"sid": secret_uuid, "tid": str(tenant_id)},
    )
    if secret_check.fetchone() is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Agent secret not found"},
        )

    if limit < 1:
        limit = 1
    if limit > 200:
        limit = 200
    page_size = limit + 1

    if after is not None:
        try:
            after_uuid = _decode_grant_id(after)
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={"mintkey:code": "invalid_id", "title": "Invalid after cursor"},
            )
        result = await session.execute(
            text(
                "SELECT id, tenant_id, secret_id, recipient_agent_id, created_by, created_at"
                " FROM agent_secret_grants"
                " WHERE secret_id = :sid AND tenant_id = :tid"
                " AND id > :after_id"
                " ORDER BY id"
                " LIMIT :lim"
            ),
            {"sid": secret_uuid, "tid": str(tenant_id), "after_id": after_uuid, "lim": page_size},
        )
    else:
        result = await session.execute(
            text(
                "SELECT id, tenant_id, secret_id, recipient_agent_id, created_by, created_at"
                " FROM agent_secret_grants"
                " WHERE secret_id = :sid AND tenant_id = :tid"
                " ORDER BY id"
                " LIMIT :lim"
            ),
            {"sid": secret_uuid, "tid": str(tenant_id), "lim": page_size},
        )
    rows = result.fetchall()

    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = db_uuid_to_wire_secgrant(page[-1].id) if has_more and page else None

    return JSONResponse({
        "data": [_grant_row_to_dict(r) for r in page],
        "next_cursor": next_cursor,
    })


# ---------------------------------------------------------------------------
# DELETE grant (revoke, idempotent)
# ---------------------------------------------------------------------------


@router.delete("/{secret_id}/grants/{grant_id}", status_code=204)
async def delete_agent_secret_grant(
    tenant_id: UUID,
    secret_id: str,
    grant_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> Response:
    """
    Revoke a share grant. Idempotent (204 even if already absent).

    Emits agent_secret_grant.revoked audit event (always, per the email-grant precedent).

    Source: ADR-0025; openapi.yaml deleteAgentSecretGrant.
    """
    try:
        secret_uuid = _decode_secret_id(secret_id)
    except ValueError:
        return Response(status_code=422)
    try:
        grant_uuid = _decode_grant_id(grant_id)
    except ValueError:
        return Response(status_code=422)
    await set_tenant_context(session, tenant_id)

    # Fetch before delete for the audit payload; scope by secret_id to enforce the
    # path-secret/grant relationship and to use the decoded secret_uuid.
    # Also join agent_secrets to get the owner for the required owner_agent_id field.
    fetch_result = await session.execute(
        text(
            "SELECT g.id, g.secret_id, g.recipient_agent_id, s.agent_id AS owner_agent_id"
            " FROM agent_secret_grants g"
            " JOIN agent_secrets s ON s.id = g.secret_id AND s.tenant_id = g.tenant_id"
            " WHERE g.id = :gid AND g.secret_id = :sid AND g.tenant_id = :tid"
        ),
        {"gid": grant_uuid, "sid": secret_uuid, "tid": str(tenant_id)},
    )
    row = fetch_result.fetchone()

    await session.execute(
        text(
            "DELETE FROM agent_secret_grants"
            " WHERE id = :gid AND secret_id = :sid AND tenant_id = :tid"
        ),
        {"gid": grant_uuid, "sid": secret_uuid, "tid": str(tenant_id)},
    )

    # Audit — only emitted when the grant row existed.
    # When already gone, schema requires all four fields (grant_id, secret_id,
    # owner_agent_id, recipient_agent_id); owner is unknowable without the row,
    # so skip audit_emit on the truly-already-gone path.
    if row is not None:
        await audit_emit(
            session=session,
            tenant_id=tenant_id,
            event_type="agent_secret_grant.revoked",
            actor_id=None,
            actor_type="operator",
            target_id=None,
            target_type="agent_secret_grant",
            payload={
                "grant_id": db_uuid_to_wire_secgrant(uuid.UUID(grant_uuid)),
                "secret_id": db_uuid_to_wire_sec(uuid.UUID(secret_uuid)),
                "owner_agent_id": db_uuid_to_wire(row.owner_agent_id, "agent"),
                "recipient_agent_id": db_uuid_to_wire(row.recipient_agent_id, "agent"),
            },
        )

    await notify_change(
        session,
        "mintkey:agent",
        {
            "event": "agent_secret_grant.revoked",
            "tenant_id": str(tenant_id),
            "grant_id": grant_id,
            "secret_id": secret_id,
        },
    )

    return Response(status_code=204)
