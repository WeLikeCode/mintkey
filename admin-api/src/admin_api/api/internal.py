"""
Internal endpoints consumed by other Mintkey services (not operator-facing).

POST /v1/internal/validate-agent-key  — called by MCP Server to validate an
    agent API key.  Uses constant-time Argon2id verify.  Returns identical
    body for all failure modes to prevent agent enumeration.

POST /v1/internal/proxy-hit  — called by Egress Proxy to record a proxy.hit
    audit event.  Accepts optional api-key fields for the classical-key branch
    (auth_method, api_key_id, key_fingerprint, used_at) — Req 8.7, 10.5.

Source: ADR-0009; Req 6 AC1, AC2; ADR-0017.5; long-lived-api-keys task 7.5.
"""
from __future__ import annotations

import hashlib
import uuid
from datetime import datetime
from typing import Optional
from uuid import UUID

import argon2
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends
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
