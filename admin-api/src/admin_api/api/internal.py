"""
Internal endpoints consumed by other Mintkey services (not operator-facing).

POST /v1/internal/validate-agent-key  — called by MCP Server to validate an
    agent API key.  Uses constant-time Argon2id verify.  Returns identical
    body for all failure modes to prevent agent enumeration.

Source: ADR-0009; Req 6 AC1, AC2; ADR-0017.5.
"""
from __future__ import annotations

import hashlib

import argon2
from argon2.exceptions import VerifyMismatchError
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.internal import DUMMY_HASH
from admin_api.db.deps import get_db_session

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
