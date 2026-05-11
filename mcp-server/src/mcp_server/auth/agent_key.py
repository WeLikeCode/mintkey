"""
Agent API key validation via admin-api internal endpoint.

Calls POST /v1/internal/validate-agent-key and returns the agent context on
success.  All failure paths (bad format, unknown key, revoked) produce the
same response body so callers cannot enumerate agents by timing or body diff.

Source: ADR-0009; Req 6 AC1, AC2.
"""
from __future__ import annotations

import os

import httpx

ADMIN_API_BASE = os.getenv("ADMIN_API_BASE_URL", "http://admin-api:8080")

INVALID_KEY_RESPONSE: dict[str, str] = {"mintkey:code": "mintkey:invalid_agent_key"}


async def validate_agent_key(api_key: str) -> tuple[dict | None, str | None]:
    """
    Validate an agent API key by calling admin-api's internal endpoint.

    Returns (agent_context, None) on success where agent_context contains
    {agent_id, tenant_id, status}.  Returns (None, failure_reason) on any
    failure — the caller must NOT distinguish failure reasons in the response.

    Source: ADR-0009; Req 6 AC1, AC2.
    """
    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{ADMIN_API_BASE}/v1/internal/validate-agent-key",
                json={"api_key": api_key},
                timeout=5.0,
            )
            if resp.status_code == 200:
                return resp.json(), None
            return None, "invalid_key"
    except Exception:
        return None, "service_unavailable"
