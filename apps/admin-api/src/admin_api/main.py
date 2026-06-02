"""
Admin API FastAPI application factory.

Source: design §4 main.py; Req 1 AC7, AC8.
WS-11: lifespan context closes the singleton grpc.aio channel on shutdown.
WS-11 polish: logging.basicConfig wired so stdlib loggers (e.g. vault_client)
  emit to stdout inside the container without needing a separate handler
  on each module logger.
"""
# ruff: noqa: E402  — logging.basicConfig() must run before submodule imports so
# that any logging calls during module-level init of the imported routers and
# middleware are captured by the stdout handler wired here.
from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
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
from admin_api.api.email_permission_grants import router as email_permission_grants_router
from admin_api.api.email_services import router as email_services_router
from admin_api.api.email_services import internal_oauth2_router as email_oauth2_internal_router
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
from admin_api.api.service_templates import router as service_templates_router
from admin_api.api.services import router as services_router
from admin_api.api.settings import router as settings_router
from admin_api.api.tenants import router as tenants_router
from admin_api.db.session import AsyncSessionLocal
from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt
from admin_api.middleware.metrics import MetricsMiddleware
from admin_api.middleware.otel import configure_otel
from admin_api.services.canonical_agents import check_canonical_agents
from admin_api.services.vault_client import close_channel


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ARG001
    """FastAPI lifespan: startup → yield → shutdown."""
    # Startup: run canonical-agent drift check (soft signal — never blocks startup).
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await check_canonical_agents(session)
    except Exception as exc:  # noqa: BLE001
        logging.getLogger(__name__).warning(
            "canonical_agents startup check failed (non-fatal): %s", exc
        )
    yield
    # Shutdown: close the singleton grpc.aio channel cleanly.
    await close_channel()


def create_app() -> FastAPI:
    app = FastAPI(title="Mintkey Admin API", version="0.1.0-preview.1", lifespan=_lifespan)

    app.include_router(health_router)
    app.include_router(auth_router)
    app.include_router(email_permission_grants_router)
    app.include_router(email_services_router)
    app.include_router(email_oauth2_internal_router)
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
    app.include_router(service_templates_router)

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
    # email-proxy → admin-api OAuth2 refresh (machine-to-machine, Bearer token auth)
    csrf_exempt("/v1/internal/oauth2")

    # Proxy endpoint uses Bearer token auth — CSRF not applicable.
    # The dynamic path /v1/proxy/call/{service_id}/{path_suffix} requires the
    # CsrfMiddleware to support prefix matching for full exemption.
    csrf_exempt("/v1/proxy/call")

    app.add_middleware(CsrfMiddleware)

    # MetricsMiddleware added LAST → Starlette reverse-add order makes it the
    # OUTERMOST wrapper, so it measures the full round-trip including all inner
    # middleware and route handler time. Source: OPS-N.
    app.add_middleware(MetricsMiddleware)

    configure_otel(app)

    return app


app = create_app()
