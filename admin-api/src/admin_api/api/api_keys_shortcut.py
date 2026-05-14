"""
Flat tenant-level API key list endpoint — WS-5 (ADR-0018).

GET /v1/tenants/{tenant_id}/api-keys
    List all service API keys in the tenant across all agents.
    Used by: admin-ui RestResource (listPath="/v1/tenants/{tenantId}/api-keys",
    listKey="api_keys") — tasks 9.1–9.3; Req 9.1.

This is the "shortcut" (prefix-less) counterpart to the agent-scoped
api_keys_router (/v1/tenants/{tid}/agents/{aid}/api-keys).  It mirrors the
pattern of tenant_permissions_router in permissions.py — same RLS discipline,
no plaintext or key_hash exposure.

Architecture constraints:
  - RLS via set_tenant_context — ADR-0008.
  - Bound parameters only — ADR-0008, T-1.0.15.
  - Never returns key_hash or plaintext — ADR-0018 §1.3; Req 10.1.
  - Response key "api_keys" matches admin-ui RestResource listKey.

Source: long-lived-api-keys tasks 9.1–9.3; ADR-0018; ADR-0008; ADR-0017.11.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.api.api_keys import _escape_like
from admin_api.db.deps import get_db_session
from mintkey_models.tenant_ctx import set_tenant_context

api_keys_shortcut_router = APIRouter(prefix="/v1/tenants/{tenant_id}/api-keys")


@api_keys_shortcut_router.get("")
async def list_tenant_api_keys(
    tenant_id: UUID,
    q: Optional[str] = None,
    service_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List all service API keys in the tenant across all agents.

    Never returns plaintext or key_hash (ADR-0018 §1.3; Req 10.1).

    Optional query parameters:
      q          — case-insensitive substring match on key_fingerprint.
      service_id — filter to keys for a specific service (UUID or svc_ wire-ID).

    Response: {"api_keys": [...]} — listKey matches admin-ui RestResource config.

    Source: long-lived-api-keys tasks 9.1–9.3; Req 9.1; ADR-0018; ADR-0008.
    """
    await set_tenant_context(session, tenant_id)

    params: dict = {"tid": str(tenant_id)}
    base_sql = (
        "SELECT id, agent_id, key_fingerprint, service_id, allowed_actions,"
        "       constraints, expires_at, last_used_at, created_at, created_by, revoked_at"
        " FROM service_api_keys"
        " WHERE tenant_id = :tid"
    )

    if q is not None:
        escaped = _escape_like(q)
        pattern = f"%{escaped}%"
        base_sql += " AND key_fingerprint ILIKE :pat ESCAPE '\\'"
        params["pat"] = pattern

    if service_id is not None:
        svc_uuid = service_id
        if service_id.startswith("svc_"):
            hex_part = service_id[4:]
            if len(hex_part) == 32:
                svc_uuid = (
                    f"{hex_part[:8]}-{hex_part[8:12]}-{hex_part[12:16]}"
                    f"-{hex_part[16:20]}-{hex_part[20:]}"
                )
        base_sql += " AND service_id = :svc_id"
        params["svc_id"] = svc_uuid

    base_sql += " ORDER BY created_at DESC"

    rows_result = await session.execute(text(base_sql), params)
    rows = rows_result.fetchall()

    items = []
    for r in rows:
        status = "revoked" if r.revoked_at else "active"
        if not r.revoked_at and r.expires_at:
            expires = r.expires_at
            if hasattr(expires, "isoformat"):
                if expires < datetime.now(timezone.utc):
                    status = "expired"
        items.append({
            "id": str(r.id),
            "agent_id": str(r.agent_id) if r.agent_id else None,
            "key_fingerprint": r.key_fingerprint,
            "service_id": str(r.service_id) if r.service_id else None,
            "allowed_actions": r.allowed_actions,
            "constraints": json.loads(r.constraints) if r.constraints else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "created_by": str(r.created_by) if r.created_by else None,
            "status": status,
        })

    return JSONResponse(status_code=200, content={"api_keys": items})
