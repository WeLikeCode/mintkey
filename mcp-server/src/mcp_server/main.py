"""
MCP Server FastAPI application factory.

Agents authenticate with API keys validated through admin-api's internal
endpoint.  Routers for MCP tool endpoints are added in later tasks
(T-1.5.2, T-1.5.3, …).

Source: ADR-0009; Req 6.
"""
from __future__ import annotations

from fastapi import FastAPI

from mcp_server.tools.discovery import router as discovery_router
from mcp_server.tools.request_token import router as request_token_router


def create_app() -> FastAPI:
    app = FastAPI(title="Mintkey MCP Server", version="0.1.0-experimental")
    app.include_router(discovery_router)
    app.include_router(request_token_router)
    return app


app = create_app()
