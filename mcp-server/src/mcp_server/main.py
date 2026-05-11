"""
MCP Server FastAPI application factory.

Agents authenticate with Agent API keys validated against admin-api's
/v1/internal/validate-agent-key endpoint.

Source: ADR-0009; Req 6.
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from mcp_server.auth.agent_key import validate_agent_key
from mcp_server.tools.discovery import router as discovery_router
from mcp_server.tools.request_token import router as request_token_router


def create_app() -> FastAPI:
    app = FastAPI(title="Mintkey MCP Server", version="0.1.0-experimental")

    @app.middleware("http")
    async def agent_key_middleware(request: Request, call_next):
        # Health check bypasses auth
        if request.url.path in ("/health", "/v1/health"):
            return await call_next(request)

        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[len("Bearer "):]
            if token.startswith("mk_agent_"):
                ctx, err = await validate_agent_key(token)
                if ctx is not None:
                    request.state.agent_context = ctx
        return await call_next(request)

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    app.include_router(discovery_router)
    app.include_router(request_token_router)
    return app


app = create_app()
