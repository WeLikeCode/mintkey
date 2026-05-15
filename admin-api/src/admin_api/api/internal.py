"""
Internal endpoints consumed by other Mintkey services (not operator-facing).

POST /v1/internal/validate-agent-key  — called by MCP Server to validate an
    agent API key.  Uses constant-time Argon2id verify.  Returns identical
    body for all failure modes to prevent agent enumeration.

POST /v1/internal/proxy-hit  — called by Egress Proxy to record a proxy.hit
    audit event.  Accepts optional api-key fields for the classical-key branch
    (auth_method, api_key_id, key_fingerprint, used_at) — Req 8.7, 10.5.

POST /v1/internal/audit/emit  — generic audit-emit endpoint consumed by broker
    (token.issued) and proxy-plugin (proxy.hit, proxy.error) via their async
    WAL queue.  Accepts the auditq.Event wire shape and calls audit_emit().
    Authenticated by X-Mintkey-Service-Token (any registered service token).

Source: ADR-0009; Req 6 AC1, AC2; ADR-0017.5; long-lived-api-keys task 7.5;
        #22 async audit emission.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

import argon2
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.internal import DUMMY_HASH
from admin_api.db.deps import get_db_session
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(prefix="/v1/internal")

_ph = argon2.PasswordHasher()

INVALID_KEY_RESPONSE: dict = {
    "type": "https://mintkey.internal/errors/invalid-agent-key",
    "title": "Invalid agent key",
    "status": 401,
    "mintkey:code": "mintkey:invalid_agent_key",
}


class ValidateAgentKeyRequest(BaseModel):
    api_key: str  # The mk_agent_-prefixed plaintext key


@router.post("/validate-agent-key")
async def validate_agent_key(
    body: ValidateAgentKeyRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Validate an agent API key for the MCP Server.

    Lookup is by fingerprint (sha256[:8]) to avoid full-table scan.
    Argon2id verify always runs — against the stored hash for known agents,
    against DUMMY_HASH for unknown ones — so timing is equalized across all
    failure modes (ADR-0017.5).

    Returns {agent_id, tenant_id, status} on success, 401 on any failure.

    Source: ADR-0009; Req 6 AC1, AC2; ADR-0017.5.
    """
    api_key = body.api_key

    # Compute fingerprint — same algorithm as agents.py _generate_agent_api_key
    fingerprint = hashlib.sha256(api_key.encode()).digest()[:8].hex()

    # Enable cross-tenant lookup. PostgreSQL does not short-circuit OR in RLS
    # USING clauses, so ''::uuid throws even when platform_admin_view='on'.
    # Set a sentinel UUID so the cast is valid, then enable platform_admin_view.
    # Pattern mirrors proxy.py._proxy_call and auth/internal.py.
    # ADR-0016.3 — platform_admin_view is the correct escape hatch here.
    await session.execute(
        text(
            "SELECT set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', true),"
            "       set_config('app.platform_admin_view', 'on', true)"
        )
    )

    result = await session.execute(
        text(
            "SELECT id, tenant_id, api_key_hash, status"
            " FROM agents WHERE api_key_fingerprint = :fp"
        ),
        {"fp": fingerprint},
    )
    row = result.fetchone()

    if row is None:
        # Equalize timing against DUMMY_HASH — ADR-0017.5
        try:
            _ph.verify(DUMMY_HASH, api_key)
        except Exception:
            pass
        return JSONResponse(status_code=401, content=INVALID_KEY_RESPONSE)

    try:
        _ph.verify(row.api_key_hash, api_key)
    except VerifyMismatchError:
        return JSONResponse(status_code=401, content=INVALID_KEY_RESPONSE)
    except Exception:
        return JSONResponse(status_code=401, content=INVALID_KEY_RESPONSE)

    if row.status != "active":
        # Revoked/suspended — same body as any other failure (Req 6 AC2)
        return JSONResponse(status_code=401, content=INVALID_KEY_RESPONSE)

    return JSONResponse(
        status_code=200,
        content={
            "agent_id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "status": row.status,
        },
    )


# ---------------------------------------------------------------------------
# proxy.hit — Egress Proxy audit emission (Task 7.5; Req 8.7, 10.5)
# ---------------------------------------------------------------------------


class ProxyHitRequest(BaseModel):
    service_id: str
    status_code: int
    method: str
    path_template: str
    latency_ms: int
    tenant_id: Optional[str] = None
    # Classical-key extension (ADR-0018; Req 8.7, 10.5)
    auth_method: Optional[str] = None   # "api_key" | "brokered_jwt"
    api_key_id: Optional[str] = None
    key_fingerprint: Optional[str] = None
    used_at: Optional[datetime] = None


@router.post("/proxy-hit")
async def proxy_hit(
    body: ProxyHitRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Record a proxy.hit audit event from the Egress Proxy.

    When auth_method=="api_key" and used_at is present, also updates
    service_api_keys.last_used_at (greatest(existing, used_at)) — Req 10.5.

    Source: long-lived-api-keys task 7.5; Req 8.7; 10.5; ADR-0014.7.
    """
    tid_str = body.tenant_id
    try:
        tenant_uuid = UUID(tid_str) if tid_str else None
    except (ValueError, TypeError):
        tenant_uuid = None

    if tenant_uuid:
        await set_tenant_context(session, tenant_uuid)

    payload: dict = {
        "service_id": body.service_id,
        "status_code": body.status_code,
        "method": body.method,
        "path_template": body.path_template,
        "latency_ms": body.latency_ms,
    }
    if body.auth_method:
        payload["auth_method"] = body.auth_method
    if body.api_key_id:
        payload["api_key_id"] = body.api_key_id
    if body.key_fingerprint:
        payload["key_fingerprint"] = body.key_fingerprint
    if body.used_at:
        payload["used_at"] = body.used_at.isoformat()

    if tenant_uuid:
        await audit_emit(
            session=session,
            tenant_id=tenant_uuid,
            event_type="proxy.hit",
            actor_id=None,
            actor_type="proxy",
            target_id=uuid.uuid4(),
            target_type="proxy_request",
            payload=payload,
        )

        # Update last_used_at for classical-key requests (Req 10.5)
        if body.auth_method == "api_key" and body.api_key_id and body.used_at:
            await session.execute(
                text(
                    "UPDATE service_api_keys"
                    " SET last_used_at = GREATEST(last_used_at, :used_at)"
                    " WHERE id = :kid AND tenant_id = :tid"
                ),
                {
                    "used_at": body.used_at,
                    "kid": body.api_key_id,
                    "tid": str(tenant_uuid),
                },
            )

    return JSONResponse(status_code=200, content={"status": "ok"})


# ---------------------------------------------------------------------------
# audit/emit — generic async audit-event ingress (#22)
# ---------------------------------------------------------------------------
# Allowed event types for this endpoint (broker + proxy-plugin events).
# Admin-api's own events go through audit_emit() directly in their handlers.
_ALLOWED_EVENT_TYPES = frozenset(
    {
        "token.issued",
        "proxy.hit",
        "proxy.error",
    }
)

# Registered service tokens that may call this endpoint.
# We accept any of the known service-to-service secrets so broker and
# proxy-plugin can both use the same endpoint without sharing a token.
_SERVICE_TOKEN_VARS = [
    "MINTKEY_BROKER_SERVICE_TOKEN",
    "MINTKEY_PROXY_SERVICE_TOKEN",
    "MINTKEY_MCP_SERVICE_TOKEN",
]


def _get_allowed_service_tokens() -> set[str]:
    """Return the set of non-empty service tokens from environment variables."""
    import os
    return {
        t for var in _SERVICE_TOKEN_VARS
        if (t := os.getenv(var, ""))
    }


class AuditEmitRequest(BaseModel):
    event_type: str
    tenant_id: str
    actor_id: Optional[str] = None
    actor_type: str = "system"
    target_id: Optional[str] = None
    target_type: Optional[str] = None
    payload: dict = {}


@router.post("/audit/emit")
async def audit_emit_endpoint(
    request: Request,
    body: AuditEmitRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Generic audit-event ingress for broker and proxy-plugin async queues.

    Accepts the auditq.Event wire shape (Go struct).  Authenticates via
    X-Mintkey-Service-Token.  Validates event_type against the allowlist and
    delegates to audit_emit() which serialises via the per-tenant advisory lock
    (hash chain safe for concurrent callers).

    Source: #22; ADR-0014.7; S-SEC-1.
    """
    # Authenticate: any known service token is accepted.
    svc_token = request.headers.get("X-Mintkey-Service-Token", "")
    allowed = _get_allowed_service_tokens()
    if not svc_token or svc_token not in allowed:
        return JSONResponse(status_code=401, content={"mintkey:code": "unauthenticated"})

    # Validate event type.
    if body.event_type not in _ALLOWED_EVENT_TYPES:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "invalid_event_type",
                "title": f"event_type '{body.event_type}' not in allowlist",
            },
        )

    # Parse tenant_id.
    try:
        tenant_uuid = UUID(body.tenant_id)
    except (ValueError, TypeError):
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_tenant_id"},
        )

    await set_tenant_context(session, tenant_uuid)

    actor_uuid: Optional[UUID] = None
    if body.actor_id:
        try:
            actor_uuid = UUID(body.actor_id)
        except (ValueError, TypeError):
            actor_uuid = None

    target_uuid: Optional[UUID] = None
    if body.target_id:
        try:
            target_uuid = UUID(body.target_id)
        except (ValueError, TypeError):
            target_uuid = None

    await audit_emit(
        session=session,
        tenant_id=tenant_uuid,
        event_type=body.event_type,
        actor_id=actor_uuid,
        actor_type=body.actor_type,
        target_id=target_uuid,
        target_type=body.target_type,
        payload=body.payload,
    )

    return JSONResponse(status_code=200, content={"status": "ok"})
