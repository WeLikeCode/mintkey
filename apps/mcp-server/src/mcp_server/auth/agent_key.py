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
    {agent_id, tenant_id, status}.  Returns (None, failure_reason) on failure.

    failure_reason distinguishes a genuine key rejection from a transient
    infrastructure fault so callers can respond differently:
      - "invalid_key"        — admin-api returned 4xx: the key is genuinely
                               bad/unknown/revoked. NOT retryable.
      - "service_unavailable" — timeout / connection error / admin-api 5xx:
                               the key was never actually judged. Retryable.
    Callers MUST NOT leak which failure_reason occurred into a response body
    that an untrusted agent can observe (agent-enumeration guard, Req 6 AC2),
    but MAY use it to pick the JSON-RPC error code (transient vs auth).

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
            # 5xx means admin-api failed to render a verdict (overload, crash,
            # dependency outage) — treat as transient, not as a key rejection.
            if resp.status_code >= 500:
                return None, "service_unavailable"
            return None, "invalid_key"
    except Exception:
        return None, "service_unavailable"
