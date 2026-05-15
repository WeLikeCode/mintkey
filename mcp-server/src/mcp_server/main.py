"""
MCP Server FastAPI application factory.

Agents authenticate with Agent API keys validated against admin-api's
/v1/internal/validate-agent-key endpoint.

Source: ADR-0009; Req 6.
"""
from __future__ import annotations

from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse

from mcp_server.auth.agent_key import validate_agent_key
from mcp_server.tools.bootstrap import router as bootstrap_router
from mcp_server.tools.discovery import router as discovery_router
from mcp_server.tools.request_token import router as request_token_router

# ---------------------------------------------------------------------------
# Prometheus metrics — T-1.10.2
# ---------------------------------------------------------------------------
try:
    from prometheus_client import (
        Counter,
        Histogram,
        CONTENT_TYPE_LATEST,
        generate_latest,
        REGISTRY,
    )

    try:
        _REQUESTS_TOTAL = Counter(
            "mintkey_requests_total",
            "Total HTTP requests processed by mcp-server",
            ["method", "path", "status"],
        )
    except ValueError:
        _REQUESTS_TOTAL = REGISTRY._names_to_collectors.get("mintkey_requests_total")
    try:
        _REQUEST_DURATION = Histogram(
            "mintkey_request_duration_seconds",
            "HTTP request duration in seconds",
            ["method", "path"],
        )
    except ValueError:
        _REQUEST_DURATION = REGISTRY._names_to_collectors.get("mintkey_request_duration_seconds")
    _PROMETHEUS_AVAILABLE = True
except ImportError:
    _PROMETHEUS_AVAILABLE = False


def create_app() -> FastAPI:
    app = FastAPI(title="Mintkey MCP Server", version="0.1.0-experimental")

    # Wire OTel OTLP exporter — gracefully skipped when the SDK/exporter packages
    # are not installed (e.g. in the host test environment).
    try:
        from mcp_server.middleware.otel import configure_otel
        configure_otel(app)
    except Exception:  # noqa: BLE001
        pass

    @app.middleware("http")
    async def agent_key_middleware(request: Request, call_next):
        # Health check, metrics, instructions, and bootstrap bypass auth.
        # /v1/tools/bootstrap is intentionally unauthenticated — it is the
        # pre-auth entry point that teaches agents how to authenticate (R6).
        if request.url.path in ("/health", "/v1/health", "/metrics", "/v1/tools/instructions", "/v1/tools/bootstrap"):
            return await call_next(request)

        # Accept both Authorization: Bearer <key> and X-API-Key: <key>
        token = None
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            candidate = auth[len("Bearer "):]
            if candidate.startswith("mk_agent_"):
                token = candidate
        if token is None:
            x_api_key = request.headers.get("X-API-Key", "")
            if x_api_key.startswith("mk_agent_"):
                token = x_api_key
        if token is not None:
            ctx, err = await validate_agent_key(token)
            if ctx is not None:
                request.state.agent_context = ctx
        return await call_next(request)

    @app.get("/health")
    async def health():
        return JSONResponse({"status": "ok"})

    @app.get("/metrics")
    async def metrics():
        """Prometheus metrics endpoint — T-1.10.2."""
        if not _PROMETHEUS_AVAILABLE:
            return Response("# prometheus-client not installed\n", media_type="text/plain")
        return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)

    # bootstrap router first — it has no auth; registers GET /v1/tools/bootstrap (R6)
    app.include_router(bootstrap_router)
    app.include_router(discovery_router)
    app.include_router(request_token_router)
    return app


app = create_app()
