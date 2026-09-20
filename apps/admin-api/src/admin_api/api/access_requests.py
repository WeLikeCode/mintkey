"""
Agent-access-requests REST router — the five operator-facing endpoints.

  GET    /v1/tenants/{tenant_id}/access-requests                     — listAccessRequests
  GET    /v1/tenants/{tenant_id}/access-requests/{request_id}        — getAccessRequest
  POST   /v1/tenants/{tenant_id}/access-requests/{request_id}/approve — approveAccessRequest
  POST   /v1/tenants/{tenant_id}/access-requests/{request_id}/reject  — rejectAccessRequest
  POST   /v1/tenants/{tenant_id}/access-requests/{request_id}/test    — testAccessRequestConnection

This router is the thin HTTP surface over ``services/access_requests.py`` (T-3.x /
T-5.x). It owns three concerns and nothing else:

  1. **Transaction boundary.** Each handler runs inside the single transaction
     opened by ``get_db_session`` (``async with session.begin()``). The service
     functions never commit themselves, so the audit emission they perform
     participates in the SAME transaction as the state change — a failed audit
     write rolls the whole thing back (Req 10.6 atomicity, T-5.5), and the
     vault-down finalize path rolls back with no ``services`` row and no secret
     persisted (Req 6.7). Raising out of a handler aborts that transaction.

  2. **Effective identity from the session, not the JWT (ADR-0019).** Reads set
     the tenant GUC from the validated operator session; writes additionally
     require the ``AdminUiSignedRequest`` (verified globally by
     ``AdminUiSignedRequestMiddleware`` for state-changing methods, ADR-0019)
     and the ``mintkey_session`` cookie (``require_tenant_session``). The audit
     ``actor_id`` (``resolved_by``) and the tenant scope are both derived from
     the validated SESSION context — never from the signed-request JWT body. If
     no tenant context can be resolved for the caller, the operation is rejected
     rather than executed without a tenant scope (Req 12.2, 12.3, 12.4).

  3. **Error mapping.** ``AccessRequestError.code`` → the HTTP status the
     canonical ``openapi.yaml`` declares for each endpoint, surfaced as the
     project's ``{"mintkey:code": code, "title": ...}`` envelope (matching
     api/permissions.py, api/agent_secrets.py). The service does all validation
     and secret handling; secret-bearing request bodies (``AccessRequestApprove``
     / ``AccessRequestConnectionTest`` — marked ``x-mintkey-sensitive``) are
     forwarded straight to the service and are never logged here (ADR-0026 D7
     precedent — this router logs nothing containing the ``credential`` field).

Source: T-6.1; design §Components (Admin API router); Req 5.2, 5.3, 12.2, 12.3,
        12.4; ADR-0008 (tenant GUC), ADR-0017.11 (prefixed ULID), ADR-0019
        (signed request + session identity), ADR-0014.7 (audit chokepoint),
        ADR-0026 D7 (x-mintkey-sensitive body exclusion); canonical openapi.yaml
        operationIds listAccessRequests / getAccessRequest / approveAccessRequest
        / rejectAccessRequest / testAccessRequestConnection.
"""
from __future__ import annotations

import uuid
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.auth.sessions import get_session_context, require_tenant_session
from admin_api.db.deps import get_db_session
from admin_api.services import access_requests as svc
from admin_api.services.access_request_models import (
    AccessRequestApprove,
    AccessRequestConnectionTest,
    AccessRequestReject,
)
from admin_api.services.access_requests import AccessRequestError
from admin_api.services.vault_client import VaultAdapterClient, get_vault_client

router = APIRouter(prefix="/v1/tenants/{tenant_id}/access-requests")


# ---------------------------------------------------------------------------
# Error-code → HTTP status mapping (canonical openapi.yaml)
# ---------------------------------------------------------------------------
# Every code below is a member of the closed ``mintkey:code`` enum (T-1.4). The
# status each maps to is the one the checked-in openapi.yaml declares for these
# endpoints:
#   - invalid_argument / secret_field_not_allowed / missing_secret_material /
#     reason_required            → 422 (validation_failed family)
#   - request_not_found / service_not_found / agent_not_found → 404
#   - already_granted / action_not_granted / request_already_pending /
#     request_not_pending        → 409 (state conflict)
#   - vault_unavailable          → 503
# ``invalid_argument`` is surfaced with ``mintkey:code = validation_failed`` at
# the REST boundary per ADR-0017.10 (the tool boundary uses ``invalid_argument``).
_STATUS_BY_CODE: dict[str, int] = {
    "invalid_argument": 422,
    "secret_field_not_allowed": 422,
    "missing_secret_material": 422,
    "reason_required": 422,
    "request_not_found": 404,
    "service_not_found": 404,
    "agent_not_found": 404,
    "already_granted": 409,
    "action_not_granted": 409,
    "request_already_pending": 409,
    "request_not_pending": 409,
    "vault_unavailable": 503,
}

# ``invalid_argument`` is remapped to ``validation_failed`` on the wire code
# (ADR-0017.10); all other codes are surfaced verbatim.
_WIRE_CODE_BY_CODE: dict[str, str] = {"invalid_argument": "validation_failed"}


def _error_response(err: AccessRequestError) -> JSONResponse:
    """Map an ``AccessRequestError`` to the ``{"mintkey:code", "title"}`` envelope.

    Mirrors api/permissions.py / api/agent_secrets.py: a plain ``JSONResponse``
    carrying ``mintkey:code`` + ``title`` (and the offending ``field`` when the
    service named one). The status comes from ``_STATUS_BY_CODE`` (defaulting to
    422 for any unmapped code — none exist today). Nothing secret is ever put in
    the body: ``err.title`` is service-authored, secret-free text.
    """
    status = _STATUS_BY_CODE.get(err.code, 422)
    wire_code = _WIRE_CODE_BY_CODE.get(err.code, err.code)
    content: dict[str, Any] = {"mintkey:code": wire_code, "title": err.title}
    if err.field is not None:
        content["field"] = err.field
    return JSONResponse(status_code=status, content=content)


async def _resolve_tenant(
    ctx: Any,
    path_tenant_id: UUID,
) -> UUID | None:
    """Derive the effective tenant from the validated SESSION, not the JWT (ADR-0019).

    ``require_tenant_session`` has already asserted the caller is authenticated
    and — for a non-platform-admin — that ``session.tenant_id == path_tenant_id``.
    We therefore prefer the session's tenant as the effective scope; only when a
    platform admin legitimately operates across tenants (session tenant differs)
    do we fall back to the path tenant they explicitly addressed.

    Returns ``None`` when no tenant context can be resolved at all, so the caller
    rejects the operation rather than executing it without a tenant scope
    (Req 12.4). ``require_tenant_session`` normally makes this unreachable, but
    the guard is explicit so a missing session context can never silently run
    unscoped.
    """
    if ctx is None:
        return None
    session_tenant = getattr(ctx, "tenant_id", None)
    if session_tenant is None:
        return None
    session_tenant_uuid = UUID(str(session_tenant))
    # Non-admins are pinned to their session tenant (== path tenant, already
    # enforced). Platform admins addressing another tenant via the path use the
    # path tenant they explicitly named.
    if session_tenant_uuid == path_tenant_id:
        return session_tenant_uuid
    return path_tenant_id


def _operator_id(ctx: Any) -> uuid.UUID | None:
    """Return the validated-session operator id for audit ``actor_id`` (ADR-0019)."""
    if ctx is None:
        return None
    operator_id = getattr(ctx, "operator_id", None)
    if operator_id is None:
        return None
    return UUID(str(operator_id))


def _no_tenant_context() -> JSONResponse:
    """401 when the caller has no resolvable tenant context (Req 12.4)."""
    return JSONResponse(
        status_code=401,
        content={
            "mintkey:code": "unauthenticated",
            "title": "No resolvable tenant context for the caller",
        },
    )


# ---------------------------------------------------------------------------
# GET / — listAccessRequests (read; tenant GUC from session)
# ---------------------------------------------------------------------------


@router.get("", operation_id="listAccessRequests")
async def list_access_requests(
    tenant_id: UUID,
    status: Optional[str] = None,
    kind: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
    ctx: Any = Depends(get_session_context),
) -> JSONResponse:
    """List the tenant's access requests — operationId ``listAccessRequests``.

    RLS-scoped to the SESSION-derived tenant; optional ``status`` / ``kind``
    filters (an unknown value → 422 ``validation_failed``); ordered
    ``created_at`` descending. Read-only; emits no audit event (Req 4.1–4.3).
    """
    effective_tenant = await _resolve_tenant(ctx, tenant_id)
    if effective_tenant is None:
        return _no_tenant_context()

    try:
        items = await svc.list_requests(
            session, tenant_id=effective_tenant, status=status, kind=kind
        )
    except AccessRequestError as err:
        return _error_response(err)

    data = [
        {
            "request_id": item.request_id,
            "kind": item.kind,
            "status": item.status,
            "requesting_agent_id": item.requesting_agent_id,
            "service_id": item.service_id,
            "action": item.action,
            "target_agent_id": item.target_agent_id,
            "share_direction": item.share_direction,
            "proposed_config": item.proposed_config,
            "reason": None,
            "created_at": item.created_at.isoformat(),
            "expires_at": item.expires_at.isoformat(),
            "resolved_at": None,
        }
        for item in items
    ]
    return JSONResponse({"data": data})


# ---------------------------------------------------------------------------
# GET /{request_id} — getAccessRequest (read; tenant GUC from session)
# ---------------------------------------------------------------------------


@router.get("/{request_id}", operation_id="getAccessRequest")
async def get_access_request(
    tenant_id: UUID,
    request_id: str,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
    ctx: Any = Depends(get_session_context),
) -> JSONResponse:
    """Return one access request's detail — operationId ``getAccessRequest``.

    A ``request_id`` from another tenant is invisible under RLS and yields 404
    ``request_not_found`` without revealing cross-tenant existence (Req 4.4,
    12.3). For an integration proposal the operator-supplied secret fields are
    exposed blank (the row never holds secrets, P-1). Read-only.
    """
    effective_tenant = await _resolve_tenant(ctx, tenant_id)
    if effective_tenant is None:
        return _no_tenant_context()

    try:
        detail = await svc.get_request(
            session, tenant_id=effective_tenant, request_id=request_id
        )
    except AccessRequestError as err:
        return _error_response(err)

    return JSONResponse(
        {
            "request_id": detail.request_id,
            "kind": detail.kind,
            "status": detail.status,
            "requesting_agent_id": detail.requesting_agent_id,
            "service_id": detail.service_id,
            "action": detail.action,
            "target_agent_id": detail.target_agent_id,
            "share_direction": detail.share_direction,
            "proposed_config": detail.proposed_config,
            "reason": detail.reason,
            "created_at": detail.created_at.isoformat(),
            "expires_at": detail.expires_at.isoformat(),
            "resolved_at": (
                detail.resolved_at.isoformat() if detail.resolved_at else None
            ),
        }
    )


# ---------------------------------------------------------------------------
# POST /{request_id}/approve — approveAccessRequest (write; signed + session)
# ---------------------------------------------------------------------------


@router.post("/{request_id}/approve", operation_id="approveAccessRequest")
async def approve_access_request(
    tenant_id: UUID,
    request_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    vault: VaultAdapterClient = Depends(get_vault_client),
    _authz: None = Depends(require_tenant_session),
    ctx: Any = Depends(get_session_context),
) -> JSONResponse:
    """Approve a pending request / finalize an integration — ``approveAccessRequest``.

    Writes require the ``AdminUiSignedRequest`` (verified by the global
    signed-request middleware for POST) plus the operator session; the effective
    identity (audit ``actor_id`` = ``resolved_by``) and tenant scope come from
    the SESSION, not the JWT body (ADR-0019). The body carries the operator
    secret material for an integration finalize (``x-mintkey-sensitive``) — it is
    forwarded straight to the service (→ Vault Adapter) and never logged here.

    The whole approval runs in the ``get_db_session`` transaction: the reused
    grant/service/credential writes and every ``audit.emit()`` share it, so a
    failed audit or a Vault outage rolls everything back (Req 10.6, 6.7).
    """
    effective_tenant = await _resolve_tenant(ctx, tenant_id)
    if effective_tenant is None:
        return _no_tenant_context()

    # Parse the optional sensitive body without logging it. An absent/empty body
    # is valid for access/share approval (all fields optional).
    body = await _parse_optional_body(request, AccessRequestApprove)
    if isinstance(body, JSONResponse):
        return body

    try:
        result = await svc.approve(
            session,
            tenant_id=effective_tenant,
            request_id=request_id,
            vault=vault,
            resolved_by=_operator_id(ctx),
            credential=body.credential if body else None,
            config=body.config if body else None,
        )
    except AccessRequestError as err:
        return _error_response(err)

    return await _detail_response(session, effective_tenant, result.request_id)


# ---------------------------------------------------------------------------
# POST /{request_id}/reject — rejectAccessRequest (write; signed + session)
# ---------------------------------------------------------------------------


@router.post("/{request_id}/reject", operation_id="rejectAccessRequest")
async def reject_access_request(
    tenant_id: UUID,
    request_id: str,
    body: AccessRequestReject,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
    ctx: Any = Depends(get_session_context),
) -> JSONResponse:
    """Reject a pending request with a reason — operationId ``rejectAccessRequest``.

    A missing/blank/over-long ``reason`` is rejected 422 ``reason_required``
    (Req 8.2); a non-pending request is 409 ``request_not_pending`` leaving the
    row unchanged (Req 8.7). Creates no grant/service/credential (Req 8.3).
    ``actor_id`` (``resolved_by``) is the validated-session operator (ADR-0019).
    """
    effective_tenant = await _resolve_tenant(ctx, tenant_id)
    if effective_tenant is None:
        return _no_tenant_context()

    try:
        result = await svc.reject(
            session,
            tenant_id=effective_tenant,
            request_id=request_id,
            reason=body.reason,
            resolved_by=_operator_id(ctx),
        )
    except AccessRequestError as err:
        return _error_response(err)

    return await _detail_response(session, effective_tenant, result.request_id)


# ---------------------------------------------------------------------------
# POST /{request_id}/test — testAccessRequestConnection (write; signed + session)
# ---------------------------------------------------------------------------


@router.post("/{request_id}/test", operation_id="testAccessRequestConnection")
async def test_access_request_connection(
    tenant_id: UUID,
    request_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
    _authz: None = Depends(require_tenant_session),
    ctx: Any = Depends(get_session_context),
) -> JSONResponse:
    """Connection_Test for an integration proposal — ``testAccessRequestConnection``.

    Performs a secret-free upstream handshake (10s timeout, egress allowlist)
    using the operator secret + edited config — nothing is persisted. Returns
    ``TestRunResponse``; a timeout is ``ok: false`` with a timeout diagnostic,
    never an error status. The operator secret (``x-mintkey-sensitive``) is
    forwarded straight to the service and never logged here (Req 6.3, 6.4).
    """
    effective_tenant = await _resolve_tenant(ctx, tenant_id)
    if effective_tenant is None:
        return _no_tenant_context()

    body = await _parse_optional_body(request, AccessRequestConnectionTest)
    if isinstance(body, JSONResponse):
        return body

    try:
        result = await svc.connection_test(
            session,
            tenant_id=effective_tenant,
            request_id=request_id,
            credential=body.credential if body else None,
            config=body.config if body else None,
        )
    except AccessRequestError as err:
        return _error_response(err)

    return JSONResponse(
        {
            "ok": result.ok,
            "latency_ms": result.latency_ms,
            "status_code": result.status_code,
            "response_body_truncated": result.diagnostic or None,
            "error": result.error,
        }
    )


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _parse_optional_body(
    request: Request,
    model: type[AccessRequestApprove] | type[AccessRequestConnectionTest],
) -> AccessRequestApprove | AccessRequestConnectionTest | None | JSONResponse:
    """Parse a possibly-absent sensitive JSON body without logging it.

    Reading the body via ``Request`` (rather than a typed FastAPI body param)
    keeps the ``x-mintkey-sensitive`` ``credential`` field out of framework
    request/validation logging paths and lets us treat an empty body as ``None``
    (valid for access/share approval). A malformed body is surfaced as 422
    ``validation_failed`` — the invalid payload itself is never echoed back
    (ADR-0026 D7; P-1).
    """
    raw = await request.body()
    if not raw or not raw.strip():
        return None
    try:
        return model.model_validate_json(raw)
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "validation_failed",
                "title": "request body failed validation",
            },
        )


async def _detail_response(
    session: AsyncSession,
    tenant_id: UUID,
    request_id: str,
) -> JSONResponse:
    """Return the post-write ``AccessRequest`` detail (Req 5, 7, 8 all return it).

    Approve/reject respond with the updated request in the ``AccessRequest``
    shape. This re-reads within the same transaction so the response reflects
    the committed ``status``/``resolved_at`` and the wire-form fields.
    """
    detail = await svc.get_request(session, tenant_id=tenant_id, request_id=request_id)
    return JSONResponse(
        {
            "request_id": detail.request_id,
            "kind": detail.kind,
            "status": detail.status,
            "requesting_agent_id": detail.requesting_agent_id,
            "service_id": detail.service_id,
            "action": detail.action,
            "target_agent_id": detail.target_agent_id,
            "share_direction": detail.share_direction,
            "proposed_config": detail.proposed_config,
            "reason": detail.reason,
            "created_at": detail.created_at.isoformat(),
            "expires_at": detail.expires_at.isoformat(),
            "resolved_at": (
                detail.resolved_at.isoformat() if detail.resolved_at else None
            ),
        }
    )
