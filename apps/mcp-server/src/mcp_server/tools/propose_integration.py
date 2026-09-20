"""
MCP propose_integration tool.

POST /v1/tools/propose_integration

Proposes registering a brand-new backend service. The agent supplies the
service name, base_url, auth_scheme, an optional openapi_url, and a NON-SECRET
config object. Secret material is deliberately omitted — the operator supplies
it at finalize. Any config key matching the secret denylist (*_secret,
*_password, *_passphrase, private_key, token, api_key) is rejected. Creates an
integration proposal (kind=integration, status=pending) with a default 30-day
expiration. Emits access_request.created (actor=agent).

Input  : {name, base_url, auth_scheme, openapi_url?, config}  (no tenant_id)
Output : {request_id, status}

The tenant is resolved from the Agent API Key context (ADR-0009); no tenant
argument is accepted (Req 13.2). Mirrors the admin-api service-layer create
logic in-process — the MCP container cannot import the admin-api package (see
tools/_access_requests_common.py). Stores only the non-secret proposed_config
and creates NO services row (Req 2.7). Secrets never reach the row (P-1).

Source: T-7.1; tools.yaml propose_integration; Req 2.1-2.9, 13.2; ADR-0009,
        ADR-0023 (SSH base_url), ADR-0017.11, ADR-0014.7, P-1.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.tools import _access_requests_common as arc
from mcp_server.tools.discovery import get_agent_context

router = APIRouter(prefix="/v1/tools")


class ProposeIntegrationInput(BaseModel):
    name: str
    base_url: str
    auth_scheme: str
    config: dict[str, Any]
    openapi_url: Optional[str] = None


@router.post("/propose_integration")
async def propose_integration(
    request: Request,
    body: ProposeIntegrationInput,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict[str, str]] = Depends(get_agent_context),
) -> JSONResponse:
    """Create an ``integration`` proposal for the calling agent — Req 2.1-2.9."""
    if agent_ctx is None:
        return JSONResponse(status_code=401, content={"code": "mintkey:auth_required"})

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    try:
        name = arc.norm(body.name)
        if not name:
            raise arc.AccessRequestToolError(
                "invalid_argument", "name is required", field="name"
            )
        base_url = arc.norm(body.base_url)
        if not base_url:
            raise arc.AccessRequestToolError(
                "invalid_argument", "base_url is required", field="base_url"
            )
        auth_scheme = arc.norm(body.auth_scheme)
        if not auth_scheme:
            raise arc.AccessRequestToolError(
                "invalid_argument", "auth_scheme is required", field="auth_scheme"
            )

        # Req 2.3 — auth_scheme must be a member of the closed enum.
        if auth_scheme not in arc.AUTH_SCHEME_ENUM:
            raise arc.AccessRequestToolError(
                "invalid_argument",
                f"auth_scheme '{auth_scheme}' is not a member of the closed "
                "auth_scheme enum",
                field="auth_scheme",
            )

        config: dict[str, Any] = dict(body.config or {})

        # Req 2.4 — reject any secret field before it can be stored (P-1).
        offending = arc.find_secret_denylist_field(config)
        if offending is not None:
            raise arc.AccessRequestToolError(
                "secret_field_not_allowed",
                f"config field '{offending}' matches the secret denylist and "
                "must be supplied by the operator, not proposed by the agent",
                field=offending,
            )

        # Req 2.5 / 2.6 — SSH schemes: ssh://host:port base_url, no target_address.
        if arc.is_ssh_auth_scheme(auth_scheme):
            if not arc.validate_ssh_base_url(base_url):
                raise arc.AccessRequestToolError(
                    "invalid_argument",
                    "base_url must be ssh://host:port for SSH auth schemes",
                    field="base_url",
                )
            if "target_address" in config:
                raise arc.AccessRequestToolError(
                    "invalid_argument",
                    "target_address is not accepted for SSH auth schemes; the "
                    "upstream host:port is carried by base_url (ADR-0023)",
                    field="target_address",
                )

        # Req 2.8 / 2.9 — openapi_url (when supplied) must be HTTPS. The full
        # SSRF allowlist check runs authoritatively in admin-api at finalize.
        openapi_url = arc.norm(body.openapi_url)
        if openapi_url and not arc.validate_openapi_url_scheme(openapi_url):
            raise arc.AccessRequestToolError(
                "invalid_argument",
                "openapi_url was rejected: must use the HTTPS scheme",
                field="openapi_url",
            )

        # Assemble the non-secret proposed config actually persisted on the row.
        # The denylist gate above guarantees no secret field is present (P-1).
        proposed_config: dict[str, Any] = dict(config)
        proposed_config["name"] = name
        proposed_config["base_url"] = base_url
        proposed_config["auth_scheme"] = auth_scheme
        if openapi_url:
            proposed_config["openapi_url"] = openapi_url

        requesting_agent_uuid = uuid.UUID(agent_id)
        await set_tenant_context(session, uuid.UUID(tenant_id))

        request_id, request_uuid = arc.new_request_id()
        now = datetime.now(timezone.utc)
        expires_at = arc.compute_expires_at(now)

        await arc.insert_request(
            session,
            tenant_id=tenant_id,
            request_uuid=request_uuid,
            kind="integration",
            requesting_agent_uuid=requesting_agent_uuid,
            service_uuid=None,
            action=None,
            target_agent_uuid=None,
            share_direction=None,
            proposed_config=proposed_config,
            created_at=now,
            expires_at=expires_at,
        )
        # kind=integration has no services row yet, so the created event carries
        # no service_id/action; the non-secret proposed name/scheme are NOT put
        # on the audit payload (schema is additionalProperties: false, Req 10.3).
        await arc.emit_created_audit(
            session,
            tenant_id=tenant_id,
            request_uuid=request_uuid,
            requesting_agent_uuid=requesting_agent_uuid,
            request_id=request_id,
            kind="integration",
            expires_at=expires_at,
            payload_target={},
        )
    except arc.AccessRequestToolError as err:
        return arc.tool_error_response(err)

    await session.commit()
    return JSONResponse({"request_id": request_id, "status": "pending"})
