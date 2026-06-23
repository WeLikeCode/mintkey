"""
Typed async HTTP client for admin-api calls made by the MCP server.

This module is the single declared boundary for admin-api HTTP calls (INV-2).
Built from Task-0 notes (.kiro/specs/mcp-token-optimization/admin-api-client-notes.md).

Existing agent-key validation in mcp_server.auth.agent_key is unchanged; this client
provides the typed contract for any future admin-api HTTP call introduced by this spec
and serves as the declared import target per NFR-6.

Source: .kiro/specs/mcp-token-optimization/ (FR-20, NFR-1, NFR-2, INV-2).
"""
from __future__ import annotations

import os

import httpx
from pydantic import BaseModel

_VALIDATE_PATH = "/v1/internal/validate-agent-key"


class AgentContext(BaseModel):
    agent_id: str
    tenant_id: str


class AdminApiClient:
    def __init__(self, base_url: str | None = None, timeout: float = 5.0) -> None:
        self._base_url: str = (
            base_url if base_url is not None
            else os.getenv("ADMIN_API_BASE_URL", "http://admin-api:8080")
        )
        self._timeout = timeout

    async def validate_agent_key(self, api_key: str) -> AgentContext | None:
        """POST agent-key validation. Returns typed context on 200, None otherwise."""
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            resp = await client.post(
                f"{self._base_url}{_VALIDATE_PATH}",
                json={"api_key": api_key},
            )
        if resp.status_code != 200:
            return None
        data = resp.json()
        return AgentContext(agent_id=data["agent_id"], tenant_id=str(data["tenant_id"]))
