"""
MCP request_token tool.

POST /v1/tools/request_token

Looks up the permission_grant for (agent_id, service_id, action), evaluates
rate_limit and time_window constraints, and — if permitted — issues a stub JWT
(full broker call deferred to T-1.6.x).

Constraint split:
  - MCP Server evaluates: rate_limit, time_window.
  - Proxy plugin evaluates: request_path_prefix, source_ip_allowlist.

All denials emit a token.denied audit event (ADR-0014.7).

Email services path (feat/agent-email-e2e):
  If the service_id resolves to an email_services row (not a services row),
  this handler checks email_permission_grants instead of permission_grants and
  issues a JWT with service_kind=email so email-proxy can route correctly.

Source: Req 6 AC5, AC10; ADR-0016.4; ADR-0014.7; ADR-0008.
"""
from __future__ import annotations

import os
from typing import Optional

import httpx

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context
from mcp_server.db.session import get_db_session
from mcp_server.policy.constraints import RateLimiter, evaluate_rate_limit, evaluate_time_window
from mcp_server.tools.discovery import get_agent_context
from mcp_server.config.public_urls import resolve_ssh_proxy_public_host
from mcp_server.utils.wire_ids import ServiceNotFound, db_uuid_to_wire, resolve_email_service_id, resolve_service_id

# Auth scheme IDs that indicate SSH transport (ssh-proxy handles these, not Kong).
_SSH_AUTH_SCHEMES = {"ssh_private_key", "ssh_password", "ssh_ca"}

router = APIRouter(prefix="/v1/tools")

# Module-level rate limiter — persists across requests within the same process.
_rate_limiter = RateLimiter()


def _denial_hint(reason: str, agent_id: str, service_id: str, action: str) -> Optional[str]:
    """
    Return an agent-facing hint string for a denial reason, or None if the
    reason is unrecognised (so callers can omit the field rather than emit a
    placeholder).

    UX-FB-A: every denial path that has a known reason gets a verbatim hint
    that names the agent, service, and action and tells the agent what to do.
    """
    if reason == "permission_not_found":
        return (
            f"No permission grant exists for this (agent, service, action) triple. "
            f"Ask the operator to grant '{action}' on service '{service_id}' to agent "
            f"'{agent_id}'. Operators do this in the admin UI under Permissions > New."
        )
    if reason == "constraint_failed:rate_limit":
        return (
            "Rate limit exceeded for this grant. Back off and retry; check "
            "describe_service.your_constraints.rate_limit for the cap."
        )
    if reason == "constraint_failed:time_window":
        return (
            "Current time is outside the time_window constraint on this grant. "
            "Check describe_service.your_constraints.time_window for allowed hours/days."
        )
    return None


class TokenRequest(BaseModel):
    service_id: str
    action: str


@router.post("/request_token")
async def request_token(
    request: Request,
    body: TokenRequest,
    session: AsyncSession = Depends(get_db_session),
    agent_ctx: Optional[dict] = Depends(get_agent_context),
) -> JSONResponse:
    """
    Issue a short-lived token for an agent to call a service.

    Steps:
      1. Auth check (agent context present).
      2. Set tenant context (RLS — ADR-0008).
      3. Look up permission_grant.
      4. Evaluate rate_limit constraint.
      5. Evaluate time_window constraint.
      6. Stub: generate token (broker call in T-1.6.x).

    All denials emit token.denied audit events (ADR-0014.7).
    """
    if agent_ctx is None:
        return JSONResponse(
            status_code=401, content={"code": "mintkey:auth_required"}
        )

    agent_id: str = agent_ctx["agent_id"]
    tenant_id: str = agent_ctx["tenant_id"]

    # Set tenant RLS context before any DB query (including slug lookup).
    await set_tenant_context(session, tenant_id)

    # Resolve service_id to a UUID. This may be a services UUID or an
    # email_services UUID — we determine which after the permission_grants check.
    #
    # Slug inputs are resolved via DB lookup against services.slug. If not found,
    # they return 404 (slugs are not supported for email_services).
    #
    # svc_ wire form and raw UUID inputs are decoded without a DB check here.
    # We detect whether the UUID belongs to email_services AFTER a permission_grants
    # miss (see the "email fallback" below) — this avoids adding a new DB round-trip
    # to the hot path and preserves the call-sequence expected by existing tests.
    #
    # We canonicalise to the svc_ wire form for audit events / response body
    # regardless of what the caller passed — ADR-0017.11; OPS-CC.

    try:
        db_service_uuid = await resolve_service_id(body.service_id, tenant_id, session)
    except ServiceNotFound as exc:
        return JSONResponse(
            status_code=404,
            content={
                "code": "mintkey:not_found",
                "reason_code": "service_not_found",
                "service_id_input": exc.service_id_input,
                "hint": (
                    "Use the 'id' field from list_services (e.g., 'svc_…') "
                    "or the service slug ('github'). Slugs are case-sensitive."
                ),
            },
        )

    db_service_id = str(db_service_uuid)
    # Canonicalise to wire form for audit log (operator-readable).
    try:
        wire_service_id = db_uuid_to_wire(db_service_id, "svc")
    except Exception:
        wire_service_id = body.service_id  # fallback — should not happen

    # Whether the input is a svc_ wire form or raw UUID — these forms can
    # refer to either services or email_services (same UUID namespace, different
    # tables). Slug inputs can only refer to services (email_services has no slug).
    _is_wire_or_uuid = (
        body.service_id.startswith("svc_")
        or (len(body.service_id) == 36 and body.service_id.count("-") == 4)
    )

    # -----------------------------------------------------------------------
    # HTTP / SSH services path.
    # -----------------------------------------------------------------------

    # 1. Look up permission grant in services / permission_grants.
    result = await session.execute(
        text(
            "SELECT agent_id, service_id, action, constraints"
            " FROM permission_grants"
            " WHERE agent_id = :aid AND service_id = :sid AND action = :action"
            " LIMIT 1"
        ),
        {"aid": agent_id, "sid": db_service_id, "action": body.action},
    )
    grant = result.fetchone()

    if grant is None:
        # -----------------------------------------------------------------------
        # Email services fallback (feat/agent-email-e2e):
        # If no permission_grant found AND input is wire/UUID form, check whether
        # this UUID is actually an email_service and the agent has an
        # email_permission_grant. If so, route to the email path.
        # -----------------------------------------------------------------------
        if _is_wire_or_uuid:
            email_esvc_uuid = await resolve_email_service_id(body.service_id, tenant_id, session)
            if email_esvc_uuid is not None:
                return await _handle_email_service_token(
                    session=session,
                    agent_id=agent_id,
                    tenant_id=tenant_id,
                    db_service_id=str(email_esvc_uuid),
                    wire_service_id=db_uuid_to_wire(str(email_esvc_uuid), "svc"),
                    action=body.action,
                )

        _reason = "permission_not_found"
        _hint = _denial_hint(_reason, agent_id, wire_service_id, body.action)
        await _emit_denial(
            session, tenant_id, agent_id, wire_service_id, body.action,
            _reason,
            remediation_hint=_hint,
        )
        _body: dict = {
            "code": "mintkey:not_authorized",
            "reason_code": _reason,
            "agent_id": agent_id,
            "service_id": wire_service_id,
            "action": body.action,
        }
        if _hint is not None:
            _body["hint"] = _hint
        return JSONResponse(status_code=403, content=_body)

    constraints: dict = grant.constraints or {}

    # 2. Evaluate rate_limit constraint
    if rate_limit := constraints.get("rate_limit"):
        key = f"{agent_id}:{wire_service_id}:{body.action}"
        allowed, reason = evaluate_rate_limit(_rate_limiter, key, rate_limit)
        if not allowed:
            _hint = _denial_hint(reason, agent_id, wire_service_id, body.action)
            await _emit_denial(
                session, tenant_id, agent_id, wire_service_id, body.action, reason,
                remediation_hint=_hint,
            )
            _body = {
                "code": "mintkey:not_authorized",
                "reason_code": reason,
                "agent_id": agent_id,
                "service_id": wire_service_id,
                "action": body.action,
            }
            if _hint is not None:
                _body["hint"] = _hint
            return JSONResponse(status_code=403, content=_body)

    # 3. Evaluate time_window constraint
    if time_window := constraints.get("time_window"):
        allowed, reason = evaluate_time_window(time_window)
        if not allowed:
            _hint = _denial_hint(reason, agent_id, wire_service_id, body.action)
            await _emit_denial(
                session, tenant_id, agent_id, wire_service_id, body.action, reason,
                remediation_hint=_hint,
            )
            _body = {
                "code": "mintkey:not_authorized",
                "reason_code": reason,
                "agent_id": agent_id,
                "service_id": wire_service_id,
                "action": body.action,
            }
            if _hint is not None:
                _body["hint"] = _hint
            return JSONResponse(status_code=403, content=_body)

    # 4. Query service auth_scheme to determine transport (SSH vs HTTP).
    svc_result = await session.execute(
        text("SELECT auth_scheme FROM services WHERE id = :sid"),
        {"sid": db_service_id},
    )
    svc_row = svc_result.fetchone()
    svc_auth_scheme: str = svc_row.auth_scheme if svc_row else ""
    is_ssh = svc_auth_scheme in _SSH_AUTH_SCHEMES

    # 5. Call broker to issue a real JWT.
    # Pass the DB UUID to the broker — broker is downstream and always uses UUIDs.
    # DO NOT change the broker payload format (out-of-scope for OPS-CC).
    broker_url = os.getenv("BROKER_BASE_URL", "http://broker:8083")
    mcp_token = os.getenv("MINTKEY_MCP_SERVICE_TOKEN", "")
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{broker_url}/v1/issue",
            json={
                "agent_id": agent_id,
                "service_id": db_service_id,
                "tenant_id": tenant_id,
                "scope": body.action,
                "ttl_seconds": 600,
            },
            headers={"X-Mintkey-Service-Token": mcp_token},
            timeout=5.0,
        )
    if resp.status_code != 200:
        return JSONResponse(
            status_code=502,
            content={"code": "mintkey:broker_error", "title": "Broker unavailable"},
        )
    data = resp.json()

    # 6. Build transport-specific response.
    #    SSH services: return ssh_connect block — omit proxy_url (Kong is HTTP-only).
    #    HTTP services: return service_id only (proxy_url in discover/bootstrap).
    if is_ssh:
        ext_host, ext_port = resolve_ssh_proxy_public_host()
        ssh_connect = {
            "host": "ssh-proxy",
            "port": 2222,
            "external_host": ext_host,
            "external_port": ext_port,
            "ssh_user": agent_id,
            "auth_method": "password",
            "password_is_jwt": True,
            "hint": (
                f"ssh -p {ext_port} {agent_id}@{ext_host} "
                "— use the token above as the SSH password"
            ),
        }
        return JSONResponse({
            "token": data["token"],
            "ssh_connect": ssh_connect,
            "expires_at": data["expires_at"],
            "service_id": wire_service_id,
            "action": body.action,
        })

    return JSONResponse(
        {"token": data["token"], "expires_at": data["expires_at"], "service_id": wire_service_id}
    )


async def _handle_email_service_token(
    *,
    session,
    agent_id: str,
    tenant_id: str,
    db_service_id: str,
    wire_service_id: str,
    action: str,
) -> JSONResponse:
    """
    Issue a JWT for an email_service (feat/agent-email-e2e).

    Checks email_permission_grants for (agent_id, email_service_id).
    If a grant exists, calls broker /v1/issue with service_kind=email.
    Returns the JWT response with service_kind=email in the body so email-proxy
    and the caller both know this is an email-scoped token.
    """
    # Check email_permission_grants — no constraints (no rate_limit/time_window
    # columns on email_permission_grants in the current schema).
    grant_result = await session.execute(
        text(
            "SELECT id FROM email_permission_grants"
            " WHERE agent_id = :aid AND email_service_id = :esid"
            " LIMIT 1"
        ),
        {"aid": agent_id, "esid": db_service_id},
    )
    grant = grant_result.fetchone()

    if grant is None:
        _reason = "permission_not_found"
        _hint = (
            f"No email_permission_grant exists for this agent on email service "
            f"'{wire_service_id}'. Ask the operator to add one in the admin UI under "
            "Email Permission Grants > New."
        )
        await _emit_denial(
            session, tenant_id, agent_id, wire_service_id, action,
            _reason,
            remediation_hint=_hint,
        )
        return JSONResponse(
            status_code=403,
            content={
                "code": "mintkey:not_authorized",
                "reason_code": _reason,
                "agent_id": agent_id,
                "service_id": wire_service_id,
                "action": action,
                "hint": _hint,
            },
        )

    # Grant exists — call broker with service_kind=email.
    broker_url = os.getenv("BROKER_BASE_URL", "http://broker:8083")
    mcp_token = os.getenv("MINTKEY_MCP_SERVICE_TOKEN", "")

    # Map the action to an email scope that email-proxy understands.
    # Agents pass "call" (the default action); email-proxy checks for
    # "read:email" / "send:email". We always issue "read:email send:email"
    # (full access) because the grant itself is the authorisation boundary —
    # email_permission_grants has no per-action scoping.
    email_scope = "read:email send:email"

    async with httpx.AsyncClient() as client:
        resp = await client.post(
            f"{broker_url}/v1/issue",
            json={
                "agent_id": agent_id,
                "service_id": db_service_id,
                "tenant_id": tenant_id,
                "scope": email_scope,
                "service_kind": "email",
                "ttl_seconds": 600,
            },
            headers={"X-Mintkey-Service-Token": mcp_token},
            timeout=5.0,
        )
    if resp.status_code != 200:
        return JSONResponse(
            status_code=502,
            content={"code": "mintkey:broker_error", "title": "Broker unavailable"},
        )
    data = resp.json()

    email_proxy_url = os.getenv("EMAIL_PROXY_BASE_URL", "http://email-proxy:8088")
    return JSONResponse({
        "token": data["token"],
        "expires_at": data["expires_at"],
        "service_id": wire_service_id,
        "service_kind": "email",
        "email_proxy_url": email_proxy_url,
        "hint": (
            f"Use this token as 'Authorization: Bearer <token>' when calling "
            f"{email_proxy_url}/v1/email-proxy/* with ?service_id={wire_service_id}"
        ),
    })


async def _emit_denial(
    session: AsyncSession,
    tenant_id: str,
    agent_id: str,
    service_id: str,
    action: str,
    reason_code: str,
    *,
    remediation_hint: Optional[str] = None,
) -> None:
    """Emit token.denied audit event for any denial path. ADR-0014.7.

    ``remediation_hint`` (UX-FB-A) is the same human-readable string returned
    in the 403 response body's ``hint`` field.  It is included in the audit
    payload only when non-null so that future audit filters can target it
    independently of the agent-facing ``hint``.
    """
    from uuid import UUID
    _tid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
    _payload: dict = {
        "agent_id": agent_id,
        "service_id": service_id,
        "action": action,
        "reason_code": reason_code,
    }
    if remediation_hint is not None:
        _payload["remediation_hint"] = remediation_hint
    await audit_emit(
        session=session,
        tenant_id=_tid,
        event_type="token.denied",
        actor_id=None,
        actor_type="agent",
        target_id=None,
        target_type="service",
        payload=_payload,
    )
