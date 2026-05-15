"""
Admin API FastAPI application factory.

Source: design §4 main.py; Req 1 AC7, AC8.
WS-11: lifespan context closes the singleton grpc.aio channel on shutdown.
WS-11 polish: logging.basicConfig wired so stdlib loggers (e.g. vault_client)
  emit to stdout inside the container without needing a separate handler
  on each module logger.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

# Wire a stdout handler for the root stdlib logger so all modules that use
# logging.getLogger(__name__) — including vault_client — emit to container
# stdout and appear in `docker compose logs admin-api`.
# uvicorn also respects this setup; setting it here (before app creation)
# ensures the handler is present from the first request.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError

from admin_api.api.agents import router as agents_router
from admin_api.api.api_keys import router as api_keys_router
from admin_api.api.api_keys_shortcut import api_keys_shortcut_router
from admin_api.api.audit import router as audit_router
from admin_api.api.audit_admin import router as audit_admin_router
from admin_api.api.auth import router as auth_router
from admin_api.api.changes import router as changes_router
from admin_api.api.credentials import router as credentials_router
from admin_api.api.health import router as health_router
from admin_api.api.internal import router as internal_router
from admin_api.api.permissions import router as permissions_router, tenant_permissions_router, validation_error_handler
from admin_api.api.proxy import router as proxy_router
from admin_api.api.services import router as services_router
from admin_api.api.settings import router as settings_router
from admin_api.api.tenants import router as tenants_router
from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt
from admin_api.middleware.otel import configure_otel
from admin_api.services.vault_client import close_channel


@asynccontextmanager
async def _lifespan(app: FastAPI):  # noqa: ARG001
    """FastAPI lifespan: startup → yield → shutdown."""
    # Nothing to do on startup — channel opens lazily on first call.
    yield
    # Shutdown: close the singleton grpc.aio channel cleanly.
    await close_channel()


def create_app() -> FastAPI:
    app = FastAPI(title="Mintkey Admin API", version="0.1.0-experimental", lifespan=_lifespan)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(services_router)
    app.include_router(agents_router)
    app.include_router(api_keys_router)
    app.include_router(api_keys_shortcut_router)
    app.include_router(changes_router)
    app.include_router(credentials_router)
    app.include_router(internal_router)
    app.include_router(permissions_router)
    app.include_router(tenant_permissions_router)
    app.include_router(audit_router)
    app.include_router(audit_admin_router)
    app.include_router(settings_router)
    app.include_router(tenants_router)
    app.include_router(proxy_router)

    app.add_exception_handler(RequestValidationError, validation_error_handler)

    # Login endpoints are CSRF-exempt — they are the bootstrap surface.
    # @no_csrf decorator on the handler sets the attribute; we also register paths
    # explicitly here since routing hasn't happened yet at middleware time.
    csrf_exempt("/v1/auth/internal-login")
    csrf_exempt("/v1/auth/logout")
    csrf_exempt("/v1/auth/oidc/callback")

    # Internal endpoints are machine-to-machine (MCP server → admin-api).
    # They never originate from a browser, so CSRF is not applicable.
    # validate-agent-key and proxy-hit are called by Go/Python services.
    csrf_exempt("/v1/internal")

    # Proxy endpoint uses Bearer token auth — CSRF not applicable.
    # The dynamic path /v1/proxy/call/{service_id}/{path_suffix} requires the
    # CsrfMiddleware to support prefix matching for full exemption.
    csrf_exempt("/v1/proxy/call")

    app.add_middleware(CsrfMiddleware)

    configure_otel(app)

    return app


app = create_app()
