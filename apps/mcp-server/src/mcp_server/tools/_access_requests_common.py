"""
Shared helpers for the agent-access-request MCP tools (T-7.1).

The four access-request tools (``request_access``, ``propose_integration``,
``request_share``, ``list_my_requests``) create/list rows in the shared
``access_requests`` table. The canonical create/list logic lives in the
admin-api service layer (``apps/admin-api/src/admin_api/services/access_requests.py``,
T-3.x). The MCP Server, however, **cannot import that package at runtime** —
its container image copies only ``mcp_server`` + ``mintkey_models`` (see
``apps/mcp-server/Dockerfile`` and the note atop ``mcp_server/utils/wire_ids.py``).

So — exactly as ``request_token``/``secret_put`` do their own in-process DB work
against the shared schema — these tools mirror the admin-api service layer's SQL,
validation, prefixed-ULID derivation, and single ``audit.emit()`` chokepoint,
using the MCP Server's own async session (``mcp_server.db.session``) and the
shared ``mintkey_models`` package. This module holds the pieces the three
create tools share so each handler file stays a thin, per-tool surface.

Keep this file in lock-step with the reference logic in
``admin_api/services/access_requests.py`` (the architect-owned service layer).

Source: T-7.1; design §Components (MCP Server); Req 1.1, 1.7, 2.1, 3.1, 3.2,
        13.2; ADR-0009 (tenant from auth ctx), ADR-0017.11 (prefixed ULID),
        ADR-0023 (SSH base_url), ADR-0014.7 (audit chokepoint), P-1/P-3.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping, Optional
from urllib.parse import urlsplit

from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Crockford base32 alphabet (uppercase, no I/L/O/U) — ADR-0017.11.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Default 30-day expiration — Req 9.1.
DEFAULT_REQUEST_TTL = timedelta(days=30)

# Secret-field denylist — Req 2.4 / P-1. Mirrors the admin-api service layer.
_DENYLIST_SUFFIXES: tuple[str, ...] = ("_secret", "_password", "_passphrase")
_DENYLIST_EXACT: frozenset[str] = frozenset({"private_key", "token", "api_key"})

# Closed ``auth_scheme`` enum — mirrors ``#/$defs/auth_scheme`` in tools.yaml
# and the ``_AUTH_SCHEME_ENUM`` in the admin-api service layer.
AUTH_SCHEME_ENUM: frozenset[str] = frozenset(
    {
        "api_key_header",
        "api_key_query",
        "bearer_token",
        "basic_auth",
        "oauth2_client_credentials",
        "oidc_client_secret",
        "mtls",
        "apple_jwt",
        "google_service_account",
        "ssh_private_key",
        "ssh_ca",
        "ssh_password",
        "email_password",
        "email_oauth2",
        "email_app_password",
        "http_digest",
    }
)

# SSH auth schemes — carry the upstream as ``ssh://host:port`` in ``base_url``
# (ADR-0023); ``target_address`` is deprecated.
_SSH_AUTH_SCHEMES: frozenset[str] = frozenset(
    {"ssh_private_key", "ssh_ca", "ssh_password"}
)

# Closed list-filter enums — Req list_my_requests (mirrors tools.yaml).
STATUS_ENUM: frozenset[str] = frozenset(
    {"pending", "approved", "rejected", "expired", "cancelled"}
)
KIND_ENUM: frozenset[str] = frozenset({"access", "integration", "share"})


class AccessRequestToolError(Exception):
    """Raised by a create/list helper; the tool maps ``code`` to a JSON body.

    ``code`` is a member of the closed ``error_code`` enum in tools.yaml
    (T-1.4). ``field`` names the offending input where the requirement asks the
    tool to indicate it (Req 1.3, 2.2, 3.3).
    """

    def __init__(self, code: str, message: str, *, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.title = message
        self.field = field


# ---------------------------------------------------------------------------
# Prefixed-ULID helpers (ADR-0017.11) — mirror admin-api service layer.
# ---------------------------------------------------------------------------


def new_request_id() -> tuple[str, uuid.UUID]:
    """Return ``(wire_id, internal_uuid)`` for a fresh ``request_`` ULID.

    48-bit ms timestamp + 80 random bits, Crockford base32, with the internal
    DB UUID derived from the same 128-bit value so the wire form decodes back to
    the stored PK — identical derivation to the admin-api service layer.
    """
    ts_ms = int(time.time() * 1000)
    rand = int.from_bytes(uuid.uuid4().bytes[:10], "big")

    t_enc: list[str] = []
    v = ts_ms
    for _ in range(10):
        t_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    t_enc.reverse()

    r_enc: list[str] = []
    v = rand
    for _ in range(16):
        r_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    r_enc.reverse()

    wire_id = "request_" + "".join(t_enc) + "".join(r_enc)
    val = 0
    for ch in wire_id[len("request_"):]:
        val = (val << 5) | _CROCKFORD.index(ch)
    val &= (1 << 128) - 1
    return wire_id, uuid.UUID(int=val)


# ---------------------------------------------------------------------------
# Pure validation helpers — mirror admin-api service layer.
# ---------------------------------------------------------------------------


def norm(value: str | None) -> str:
    """Return a stripped string; treats None as empty (Req 1.3, 2.2, 3.3)."""
    return (value or "").strip()


def is_denylisted_field_name(name: str) -> bool:
    """Return True if *name* matches the secret denylist (case-insensitive)."""
    lowered = name.lower()
    if lowered in _DENYLIST_EXACT:
        return True
    return any(lowered.endswith(suffix) for suffix in _DENYLIST_SUFFIXES)


def find_secret_denylist_field(config: Mapping[str, Any]) -> Optional[str]:
    """Return the first config key matching the secret denylist, else None (Req 2.4)."""
    for key in config:
        if is_denylisted_field_name(key):
            return key
    return None


def is_ssh_auth_scheme(auth_scheme: str) -> bool:
    """Return True if *auth_scheme* is one of the SSH schemes (ADR-0023)."""
    return auth_scheme in _SSH_AUTH_SCHEMES


def validate_ssh_base_url(base_url: str) -> bool:
    """Return True if *base_url* is a well-formed ``ssh://host:port`` URL (ADR-0023)."""
    parts = urlsplit(base_url)
    if parts.scheme != "ssh":
        return False
    if not parts.hostname:
        return False
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        return False
    try:
        port = parts.port
    except ValueError:
        return False
    return port is not None


def compute_expires_at(created_at: datetime) -> datetime:
    """Return ``created_at + 30 days`` as a UTC datetime (Req 9.1)."""
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)
    return created_at + DEFAULT_REQUEST_TTL


def is_elapsed(expires_at: datetime, *, now: datetime | None = None) -> bool:
    """Return True iff a pending request with *expires_at* has elapsed (Req 9.2/9.3).

    The boundary is inclusive of ``expires_at`` (``t >= expires_at``), matching
    the admin-api service layer so the lazy-on-read view agrees with the sweep.
    """
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    else:
        current = current.astimezone(timezone.utc)
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    else:
        expires_at = expires_at.astimezone(timezone.utc)
    return current >= expires_at


def effective_status(status: str, expires_at: datetime) -> str:
    """Return the read-time effective status, applying the lazy-expiry guard.

    A row whose stored ``status`` is ``pending`` but whose ``expires_at`` has
    elapsed reads as ``expired`` (Req 9.2, lazy-on-read); every other stored
    status is returned unchanged. In-memory inference only — it neither persists
    the flip nor emits an audit event (the scheduled sweep owns that).
    """
    if status == "pending" and is_elapsed(expires_at):
        return "expired"
    return status


# ---------------------------------------------------------------------------
# Shared DB reads — mirror admin-api service layer.
# ---------------------------------------------------------------------------


async def service_exists(
    session: AsyncSession, tenant_id: str, service_uuid: uuid.UUID
) -> bool:
    result = await session.execute(
        text("SELECT 1 FROM services WHERE id = :sid AND tenant_id = :tid"),
        {"sid": str(service_uuid), "tid": tenant_id},
    )
    return result.fetchone() is not None


async def agent_exists(
    session: AsyncSession, tenant_id: str, agent_uuid: uuid.UUID
) -> bool:
    result = await session.execute(
        text("SELECT 1 FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": str(agent_uuid), "tid": tenant_id},
    )
    return result.fetchone() is not None


async def grant_exists(
    session: AsyncSession,
    tenant_id: str,
    agent_uuid: uuid.UUID,
    service_uuid: uuid.UUID,
    action: str,
) -> bool:
    result = await session.execute(
        text(
            "SELECT 1 FROM permission_grants"
            " WHERE agent_id = :aid AND service_id = :sid"
            "   AND action = :action AND tenant_id = :tid"
        ),
        {
            "aid": str(agent_uuid),
            "sid": str(service_uuid),
            "action": action,
            "tid": tenant_id,
        },
    )
    return result.fetchone() is not None


# ---------------------------------------------------------------------------
# Wire-ID decode for incoming svc_ / agent_ arguments.
# ---------------------------------------------------------------------------
# The tool inputs carry svc_/agent_ wire-form IDs (tools.yaml #/$defs). Decode
# them to internal UUIDs via the shared wire_ids decoder. A malformed id is a
# client error surfaced as ``invalid_argument`` (it can never name a real row).


def decode_wire_id(
    wire_id: str, prefix: str, *, field: str
) -> uuid.UUID:
    """Decode a ``<prefix>_`` wire ID to a UUID, else raise ``invalid_argument``.

    Uses the shared ``mcp_server.utils.wire_ids.wire_to_db_uuid`` decoder (same
    encoder/decoder the discovery + token tools use). A value that does not
    decode to a UUID is rejected with ``invalid_argument`` naming *field*.
    """
    from mcp_server.utils.wire_ids import wire_to_db_uuid

    try:
        return uuid.UUID(wire_to_db_uuid(wire_id, prefix))
    except (ValueError, AttributeError):
        raise AccessRequestToolError(
            "invalid_argument", f"{field} is malformed", field=field
        )


# ---------------------------------------------------------------------------
# Shared INSERT + created-audit — mirror admin-api service layer.
# ---------------------------------------------------------------------------


async def insert_request(
    session: AsyncSession,
    *,
    tenant_id: str,
    request_uuid: uuid.UUID,
    kind: str,
    requesting_agent_uuid: uuid.UUID,
    service_uuid: uuid.UUID | None,
    action: str | None,
    target_agent_uuid: uuid.UUID | None,
    share_direction: str | None,
    proposed_config: dict[str, Any] | None,
    created_at: datetime,
    expires_at: datetime,
) -> None:
    """INSERT the umbrella ``access_requests`` row. Secrets never reach it (P-1).

    Mirrors ``admin_api.services.access_requests._insert_request`` column-for-column.
    """
    import json

    await session.execute(
        text(
            "INSERT INTO access_requests"
            " (id, tenant_id, kind, status, requesting_agent_id, service_id,"
            "  action, target_agent_id, share_direction, proposed_config,"
            "  reason, expires_at, created_at, resolved_at, created_by,"
            "  resolved_by)"
            " VALUES"
            " (:id, :tenant_id, :kind, 'pending', :requesting_agent_id,"
            "  :service_id, :action, :target_agent_id, :share_direction,"
            "  CAST(:proposed_config AS jsonb), NULL, :expires_at, :created_at,"
            "  NULL, :created_by, NULL)"
        ),
        {
            "id": str(request_uuid),
            "tenant_id": tenant_id,
            "kind": kind,
            "requesting_agent_id": str(requesting_agent_uuid),
            "service_id": str(service_uuid) if service_uuid else None,
            "action": action,
            "target_agent_id": (
                str(target_agent_uuid) if target_agent_uuid else None
            ),
            "share_direction": share_direction,
            "proposed_config": (
                json.dumps(proposed_config) if proposed_config is not None else None
            ),
            "expires_at": expires_at,
            "created_at": created_at,
            "created_by": str(requesting_agent_uuid),
        },
    )


async def emit_created_audit(
    session: AsyncSession,
    *,
    tenant_id: str,
    request_uuid: uuid.UUID,
    requesting_agent_uuid: uuid.UUID,
    request_id: str,
    kind: str,
    expires_at: datetime,
    payload_target: dict[str, Any],
) -> None:
    """Emit ``access_request.created`` through the single audit chokepoint.

    ``actor_type`` is ``agent`` — the request is agent-initiated (Req 10.5).
    Payload is identifier/metadata-only, conforming to
    ``ev_access_request_created`` (``additionalProperties: false``); no secret
    or denylisted values (Req 10.3). Mirrors the admin-api service layer.
    """
    from mintkey_models.audit import audit_emit
    from mintkey_models.access_request_metrics import record_transition
    from mcp_server.utils.wire_ids import db_uuid_to_wire

    payload: dict[str, Any] = {
        "request_id": request_id,
        "kind": kind,
        "status": "pending",
        "requesting_agent_id": db_uuid_to_wire(requesting_agent_uuid, "agent"),
        "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        **payload_target,
    }
    await audit_emit(
        session=session,
        tenant_id=uuid.UUID(tenant_id),
        event_type="access_request.created",
        actor_id=requesting_agent_uuid,
        actor_type="agent",
        target_id=request_uuid,
        target_type="access_request",
        payload=payload,
    )
    # T-9.2 — increment access_request_created_total{kind,tenant_id} and emit
    # the structured transition log (request_id/kind/status only, Req 11.2/11.4).
    # This is the single MCP-side create funnel shared by the three create tools
    # (request_access / propose_integration / request_share); it fires here so
    # the ``created`` counter increments wherever an MCP tool mints a row,
    # matching the admin-api service layer's ``_emit_created_audit``.
    record_transition(
        "created", request_id=request_id, kind=kind, tenant_id=tenant_id
    )


# ---------------------------------------------------------------------------
# Error → JSON body mapping for the tools.
# ---------------------------------------------------------------------------
# The MCP tools surface a service-authored error as the project's standard
# ``{"code": "mintkey:<code>", "title": ...}`` body (matching request_token's
# denial bodies). ``field`` is included when the service named an offending
# input. All create/list validation failures are client errors → HTTP 422.


def tool_error_response(err: "AccessRequestToolError") -> JSONResponse:
    """Map an ``AccessRequestToolError`` to a 422 JSONResponse."""
    content: dict[str, Any] = {"code": f"mintkey:{err.code}", "title": err.title}
    if err.field is not None:
        content["field"] = err.field
    return JSONResponse(status_code=422, content=content)


# ---------------------------------------------------------------------------
# openapi_url scheme check — Req 2.8 / 2.9 (HTTPS gate).
# ---------------------------------------------------------------------------
# The admin-api service layer validates a proposed ``openapi_url`` with HTTPS +
# the shared SSRF allowlist resolver (``credential_service.validate_token_url_ssrf``).
# The MCP container cannot import that resolver (admin-api is not on its runtime
# path). The tool therefore applies the deterministic HTTPS-scheme gate here so
# a plainly non-HTTPS URL is rejected at proposal time (Req 2.9); the
# authoritative SSRF-allowlist check runs in admin-api on the approval/finalize
# path (T-5.1), which reuses the shared resolver before any ``services`` row or
# credential is created. A pending proposal creates no upstream connection, so
# no SSRF egress happens until that operator-driven finalize.


def validate_openapi_url_scheme(openapi_url: str) -> bool:
    """Return True if *openapi_url* uses the HTTPS scheme with a host (Req 2.8/2.9)."""
    parts = urlsplit(openapi_url)
    return parts.scheme == "https" and bool(parts.hostname)
