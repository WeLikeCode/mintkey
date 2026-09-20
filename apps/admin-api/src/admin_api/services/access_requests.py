"""
Agent-access-requests service layer — pure validation helpers (T-3.1).

This module currently holds only the *pure* validation helpers used by the
create/list/approve logic that lands in later tasks (T-3.3, T-3.5, T-5.x).
They perform no DB access and no I/O beyond reusing the existing shared SSRF
allowlist check (``credential_service.validate_token_url_ssrf``).

Helpers:
  - ``find_secret_denylist_field`` / ``config_has_secret_field`` — reject any
    proposed-config field whose name matches the secret denylist
    (``*_secret``, ``*_password``, ``*_passphrase``, ``private_key``, ``token``,
    ``api_key``) so a secret value can never be written to ``proposed_config``
    (Req 2.4, P-1).
  - ``is_ssh_auth_scheme`` / ``validate_ssh_base_url`` — enforce the
    ``ssh://host:port`` ``base_url`` form for SSH auth schemes (Req 2.5,
    ADR-0023).
  - ``validate_openapi_url`` — enforce HTTPS + the existing SSRF allowlist on a
    proposed ``openapi_url`` (Req 2.8, 2.9), reusing the single shared SSRF
    resolver rather than reimplementing it.
  - ``compute_expires_at`` — the RFC-3339 UTC ``expires_at = created_at + 30d``
    computation (Req 9.1).

Source: T-3.1; design §Components / §Data Models; Req 2.4, 2.5, 2.6, 2.8, 2.9,
        9.1; ADR-0023 (SSH upstream base_url canonical); S-SEC-1 (shared SSRF).
"""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Literal, Mapping, Optional
from urllib.parse import urlsplit

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.changes.publisher import notify_change
from admin_api.middleware.tenant import set_tenant_context
from admin_api.services.credential_service import validate_token_url_ssrf
from admin_api.services.vault_client import VaultAdapterClient
from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid
from mintkey_models.access_request_metrics import record_transition
from mintkey_models.audit import audit_emit

# ---------------------------------------------------------------------------
# Secret-field denylist — Req 2.4 / P-1
# ---------------------------------------------------------------------------
# A proposed-config field name is denied if it ends with one of the suffixes
# below OR exactly equals one of the exact names below. This is the ONLY place
# the denylist is defined; create logic (T-3.3) calls into it.
_DENYLIST_SUFFIXES: tuple[str, ...] = ("_secret", "_password", "_passphrase")
_DENYLIST_EXACT: frozenset[str] = frozenset({"private_key", "token", "api_key"})


def _is_denylisted_field_name(name: str) -> bool:
    """Return True if *name* matches the secret denylist (case-insensitive)."""
    lowered = name.lower()
    if lowered in _DENYLIST_EXACT:
        return True
    return any(lowered.endswith(suffix) for suffix in _DENYLIST_SUFFIXES)


def find_secret_denylist_field(config: Mapping[str, Any]) -> Optional[str]:
    """Return the first config key that matches the secret denylist, else None.

    Matches field names ending with ``_secret`` / ``_password`` /
    ``_passphrase`` and the exact names ``private_key`` / ``token`` /
    ``api_key`` (Req 2.4). Non-secret names such as ``client_id``,
    ``token_url``, ``ssh_user``, ``header_name`` are accepted.

    The offending field name is returned so the caller can surface it in the
    ``secret_field_not_allowed`` error (Req 2.4).
    """
    for key in config:
        if _is_denylisted_field_name(key):
            return key
    return None


def config_has_secret_field(config: Mapping[str, Any]) -> bool:
    """Return True if *config* contains any denylisted (secret) field name."""
    return find_secret_denylist_field(config) is not None


# ---------------------------------------------------------------------------
# SSH base_url validation — Req 2.5 / ADR-0023
# ---------------------------------------------------------------------------
# SSH auth schemes carry the canonical upstream as ``ssh://host:port`` in
# ``base_url``; ``target_address`` is deprecated (AGENTS.md, ADR-0023).
_SSH_AUTH_SCHEMES: frozenset[str] = frozenset(
    {"ssh_private_key", "ssh_ca", "ssh_password"}
)


def is_ssh_auth_scheme(auth_scheme: str) -> bool:
    """Return True if *auth_scheme* is one of the SSH schemes (ADR-0023)."""
    return auth_scheme in _SSH_AUTH_SCHEMES


def validate_ssh_base_url(base_url: str) -> bool:
    """Return True if *base_url* is a well-formed ``ssh://host:port`` URL.

    Requires the ``ssh`` scheme, a non-empty host, and an explicit numeric
    port in the valid TCP range (1–65535) per ADR-0023. Any other form
    (missing scheme, missing port, non-numeric port, extra path/query) is
    rejected so callers can return ``invalid_argument`` (Req 2.5).
    """
    parts = urlsplit(base_url)

    if parts.scheme != "ssh":
        return False
    if not parts.hostname:
        return False
    # A path/query/fragment on an ssh:// upstream is not a valid host:port form.
    if parts.path not in ("", "/") or parts.query or parts.fragment:
        return False

    try:
        port = parts.port
    except ValueError:
        # Non-numeric / out-of-range port raises ValueError on access.
        return False
    if port is None:
        return False

    return True


# ---------------------------------------------------------------------------
# openapi_url validation — Req 2.8, 2.9 (reuse the shared SSRF check)
# ---------------------------------------------------------------------------


def validate_openapi_url(openapi_url: str) -> tuple[bool, str]:
    """Validate a proposed ``openapi_url`` — HTTPS + existing SSRF allowlist.

    Returns ``(is_valid, reason_if_invalid)``. The URL must use the HTTPS
    scheme and pass the existing SSRF allowlist check before it is stored
    (Req 2.8); a non-HTTPS or SSRF-blocked URL is rejected (Req 2.9).

    This delegates to ``credential_service.validate_token_url_ssrf`` — the
    single shared SSRF resolver used for ``token_url``/``base_url`` checks —
    rather than reimplementing the scheme/allowlist logic (S-SEC-1).
    """
    return validate_token_url_ssrf(openapi_url)


# ---------------------------------------------------------------------------
# Default 30-day expiration — Req 9.1
# ---------------------------------------------------------------------------
DEFAULT_REQUEST_TTL = timedelta(days=30)


def compute_expires_at(created_at: datetime) -> datetime:
    """Return ``created_at + 30 days`` as a UTC (RFC-3339-serialisable) datetime.

    The Default_Request_TTL is a single documented value of 30 days (Req 9.1,
    9.6). A naive ``created_at`` is treated as UTC; an aware value is
    normalised to UTC so the result always carries an explicit UTC offset.
    """
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    else:
        created_at = created_at.astimezone(timezone.utc)
    return created_at + DEFAULT_REQUEST_TTL


def is_elapsed(expires_at: datetime, *, now: datetime | None = None) -> bool:
    """Return True iff a pending request with *expires_at* has elapsed — Req 9.2/9.3.

    A pending request is treated as ``expired`` at any time ``t`` for which
    ``t >= expires_at``, and remains ``pending`` while ``t < expires_at``
    (Req 9.2, 9.3, Property 9 — the boundary is inclusive of ``expires_at``).
    ``now`` defaults to the current UTC time; both operands are normalised to
    UTC so a naive stored ``expires_at`` (treated as UTC) compares correctly.

    This pure predicate backs BOTH the lazy-on-read guard (``approve`` /
    ``reject`` / ``get_request``) and the scheduled sweep, so the two agree on
    the exact boundary.
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
    status (including a persisted ``expired`` written by the sweep) is returned
    unchanged. This is an in-memory inference ONLY — it neither persists the
    flip nor emits an audit event; the scheduled sweep owns persistence + the
    ``access_request.expired`` audit event (design §Expiration Mechanism).
    """
    if status == "pending" and is_elapsed(expires_at):
        return "expired"
    return status


# ---------------------------------------------------------------------------
# Create logic for all three kinds — T-3.3
# ---------------------------------------------------------------------------
# Everything below builds on the pure helpers above. It performs the DB reads
# and the single INSERT for a new access/integration/share request, under the
# caller's tenant GUC (P-3, ADR-0008), and returns the ``request_`` wire ID.
#
# Error signalling follows the codebase convention that services raise an
# exception the router translates to a ``{"mintkey:code": ...}`` JSONResponse
# (see api/permissions.py, api/email_services.py). There is no pre-existing
# shared service-exception type, so this feature introduces one small, closed
# exception (``AccessRequestError``) carrying an error code that is a member of
# the closed ``mintkey:code`` / ``error_code`` enums (T-1.4). The router wiring
# lives in T-6.1.
#
# Source: T-3.3; design §Components / §Sequence (create paths) / §Data Models;
#         Req 1.1–1.6, 2.1–2.3, 2.7, 3.1–3.9; P-1, P-2, P-3;
#         ADR-0008 (tenant GUC), ADR-0017.11 (prefixed ULID),
#         ADR-0023 (SSH base_url), ADR-0014.7 (audit chokepoint).

# Crockford base32 alphabet (uppercase, no I/L/O/U) — ADR-0017.11.
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"

# Closed ``auth_scheme`` enum — mirrors ``#/$defs/auth_scheme`` in
# docs/architecture/contracts/mcp/tools.yaml (ADR-0016.5, ADR-0021, ADR-0024).
# An integration proposal whose ``auth_scheme`` is not a member is rejected with
# ``invalid_argument`` (Req 2.3).
_AUTH_SCHEME_ENUM: frozenset[str] = frozenset(
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

AccessRequestKind = Literal["access", "integration", "share"]
ShareDirection = Literal["outbound", "inbound"]

# Error codes this create path can raise. Every member is present in BOTH closed
# enums (openapi.yaml ``mintkey:code`` + tools.yaml ``error_code``) per T-1.4.
CreateErrorCode = Literal[
    "invalid_argument",
    "service_not_found",
    "agent_not_found",
    "action_not_granted",
    "already_granted",
    "request_already_pending",
    "secret_field_not_allowed",
]

# Additional codes raised by the read paths (list/get, T-3.5). ``request_not_found``
# is likewise a member of BOTH closed enums (T-1.4).
ReadErrorCode = Literal["request_not_found"]

# Additional codes raised by the approve path (T-5.1). Every member is present
# in the closed ``mintkey:code`` enum in openapi.yaml (T-1.4):
#   - ``request_not_pending``    — approve/reject a non-pending row (Req 5.6, 7.4)
#   - ``missing_secret_material``— integration finalize with a blank secret (Req 6.6)
#   - ``vault_unavailable``      — Vault Adapter down at finalize (Req 6.7)
# (``service_not_found`` — reused for a share whose service vanished, Req 7.3.)
ApproveErrorCode = Literal[
    "request_not_pending",
    "missing_secret_material",
    "vault_unavailable",
]

# Additional code raised by the reject path (T-5.3). ``reason_required`` is a
# member of BOTH closed enums (openapi.yaml ``mintkey:code`` + tools.yaml
# ``error_code``) per T-1.4:
#   - ``reason_required`` — reject with a missing/empty/whitespace-only or
#     over-1000-char ``reason`` (Req 8.2).
# (``request_not_pending`` / ``request_not_found`` are reused from above.)
RejectErrorCode = Literal["reason_required"]

# Union of every code this module's exception may carry.
AccessRequestErrorCode = Literal[
    "invalid_argument",
    "service_not_found",
    "agent_not_found",
    "action_not_granted",
    "already_granted",
    "request_already_pending",
    "secret_field_not_allowed",
    "request_not_found",
    "request_not_pending",
    "missing_secret_material",
    "vault_unavailable",
    "reason_required",
]


class AccessRequestError(Exception):
    """
    Service-layer error carrying a closed ``mintkey:code`` error code.

    The router (T-6.1) maps this to a ``{"mintkey:code": code, "title": ...}``
    JSONResponse, matching how the rest of admin-api surfaces domain errors
    (api/permissions.py, api/email_services.py). ``field`` names the offending
    input where the requirement asks the API to indicate it (Req 1.3, 2.2, 2.4,
    3.3).
    """

    def __init__(
        self,
        code: AccessRequestErrorCode,
        message: str,
        *,
        field: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code: AccessRequestErrorCode = code
        self.title: str = message
        self.field: str | None = field


def _new_request_id() -> str:
    """Generate a ULID-format ID with the ``request_`` prefix — ADR-0017.11.

    Mirrors ``api/permissions.py:_new_perm_id`` (48-bit ms timestamp + 80 bits
    of randomness, Crockford base32) so the ID sorts by creation time and maps
    1:1 to an internal DB UUID via the shared decoder.
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

    return "request_" + "".join(t_enc) + "".join(r_enc)


def _request_wire_to_uuid(wire_id: str) -> uuid.UUID:
    """Decode a ``request_`` ULID back to its internal DB UUID (ADR-0017.11)."""
    tail = wire_id[len("request_"):]
    val = 0
    for ch in tail.upper():
        val = (val << 5) | _CROCKFORD.index(ch)
    val &= (1 << 128) - 1
    return uuid.UUID(int=val)


@dataclass(frozen=True)
class CreatedRequest:
    """Result of a successful create: the wire ID plus the persisted status."""

    request_id: str
    status: str
    share_direction: ShareDirection | None = None


def _norm(value: str | None) -> str:
    """Return a stripped string; treats None as empty (Req 1.3, 2.2, 3.3)."""
    return (value or "").strip()


async def _agent_exists(
    session: AsyncSession, tenant_id: uuid.UUID, agent_uuid: uuid.UUID
) -> bool:
    result = await session.execute(
        text("SELECT 1 FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": str(agent_uuid), "tid": str(tenant_id)},
    )
    return result.fetchone() is not None


async def _service_exists(
    session: AsyncSession, tenant_id: uuid.UUID, service_uuid: uuid.UUID
) -> bool:
    result = await session.execute(
        text("SELECT 1 FROM services WHERE id = :sid AND tenant_id = :tid"),
        {"sid": str(service_uuid), "tid": str(tenant_id)},
    )
    return result.fetchone() is not None


async def _grant_exists(
    session: AsyncSession,
    tenant_id: uuid.UUID,
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
            "tid": str(tenant_id),
        },
    )
    return result.fetchone() is not None


async def _pending_duplicate_exists(
    session: AsyncSession,
    tenant_id: uuid.UUID,
    requesting_agent_uuid: uuid.UUID,
    service_uuid: uuid.UUID,
    action: str,
) -> bool:
    """True if an identical pending access request already exists (Req 1.6)."""
    result = await session.execute(
        text(
            "SELECT 1 FROM access_requests"
            " WHERE kind = 'access' AND status = 'pending'"
            "   AND requesting_agent_id = :aid AND service_id = :sid"
            "   AND action = :action AND tenant_id = :tid"
        ),
        {
            "aid": str(requesting_agent_uuid),
            "sid": str(service_uuid),
            "action": action,
            "tid": str(tenant_id),
        },
    )
    return result.fetchone() is not None


async def _insert_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_uuid: uuid.UUID,
    kind: AccessRequestKind,
    requesting_agent_uuid: uuid.UUID,
    service_uuid: uuid.UUID | None,
    action: str | None,
    target_agent_uuid: uuid.UUID | None,
    share_direction: ShareDirection | None,
    proposed_config: dict[str, Any] | None,
    created_at: datetime,
    expires_at: datetime,
) -> None:
    """INSERT the umbrella row. Secrets never reach this row (P-1)."""
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
            "tenant_id": str(tenant_id),
            "kind": kind,
            "requesting_agent_id": str(requesting_agent_uuid),
            "service_id": str(service_uuid) if service_uuid else None,
            "action": action,
            "target_agent_id": str(target_agent_uuid) if target_agent_uuid else None,
            "share_direction": share_direction,
            "proposed_config": (
                json.dumps(proposed_config) if proposed_config is not None else None
            ),
            "expires_at": expires_at,
            "created_at": created_at,
            "created_by": str(requesting_agent_uuid),
        },
    )


async def _emit_created_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_uuid: uuid.UUID,
    requesting_agent_uuid: uuid.UUID,
    request_id: str,
    kind: AccessRequestKind,
    expires_at: datetime,
    payload_target: dict[str, Any],
) -> None:
    """Emit ``access_request.created`` through the single audit chokepoint.

    The design's create sequences (§Sequence) show ``audit.emit(
    access_request.created, actor=agent)`` fired atomically inside the create
    transaction, so it is wired here (Req 10.1, 10.4). ``actor_type`` is
    ``agent`` — the request is agent-initiated (Req 10.5, Property 11).

    Payload conforms to ``ev_access_request_created`` in
    audit-event.schema.json (T-1.3): ``request_id`` + ``kind`` + ``status`` +
    ``requesting_agent_id`` + ``expires_at`` are always present; per-kind target
    refs (``service_id``/``action``/``target_agent_id``/``share_direction``) are
    threaded via ``payload_target``. The schema is ``additionalProperties:
    false``, so only allowlisted keys may appear.

    Payload is identifier/metadata-only — no secret or denylisted values
    (Req 10.3); ``proposed_config`` is intentionally NOT included here.
    """
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
        tenant_id=tenant_id,
        event_type="access_request.created",
        actor_id=requesting_agent_uuid,
        actor_type="agent",
        target_id=request_uuid,
        target_type="access_request",
        payload=payload,
    )
    # T-9.2 — increment access_request_created_total{kind,tenant_id} and emit
    # the structured transition log (request_id/kind/status only, Req 11.2/11.4).
    # Single funnel for all three create paths (access/integration/share).
    record_transition(
        "created", request_id=request_id, kind=kind, tenant_id=str(tenant_id)
    )


async def create_access_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    requesting_agent_id: uuid.UUID,
    service_id: uuid.UUID | None,
    action: str | None,
) -> CreatedRequest:
    """Create an ``access`` request — Req 1.1–1.6.

    Validation order (Req 1): required fields → service exists in tenant → not
    already granted → no duplicate pending. On success, INSERT the row and emit
    ``access_request.created`` in the same transaction; return the ``request_``
    wire ID.
    """
    await set_tenant_context(session, tenant_id)

    if service_id is None:
        raise AccessRequestError(
            "invalid_argument", "service_id is required", field="service_id"
        )
    action_norm = _norm(action)
    if not action_norm:
        raise AccessRequestError(
            "invalid_argument", "action is required", field="action"
        )

    if not await _service_exists(session, tenant_id, service_id):
        raise AccessRequestError("service_not_found", "service not found")

    if await _grant_exists(
        session, tenant_id, requesting_agent_id, service_id, action_norm
    ):
        raise AccessRequestError(
            "already_granted",
            "requesting agent already holds this (service, action) grant",
        )

    if await _pending_duplicate_exists(
        session, tenant_id, requesting_agent_id, service_id, action_norm
    ):
        raise AccessRequestError(
            "request_already_pending",
            "an identical pending access request already exists",
        )

    request_id = _new_request_id()
    request_uuid = _request_wire_to_uuid(request_id)
    now = datetime.now(timezone.utc)

    await _insert_request(
        session,
        tenant_id=tenant_id,
        request_uuid=request_uuid,
        kind="access",
        requesting_agent_uuid=requesting_agent_id,
        service_uuid=service_id,
        action=action_norm,
        target_agent_uuid=None,
        share_direction=None,
        proposed_config=None,
        created_at=now,
        expires_at=(expires_at := compute_expires_at(now)),
    )
    await _emit_created_audit(
        session,
        tenant_id=tenant_id,
        request_uuid=request_uuid,
        requesting_agent_uuid=requesting_agent_id,
        request_id=request_id,
        kind="access",
        expires_at=expires_at,
        payload_target={
            "service_id": db_uuid_to_wire(service_id, "svc"),
            "action": action_norm,
        },
    )
    return CreatedRequest(request_id=request_id, status="pending")


async def create_integration_proposal(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    requesting_agent_id: uuid.UUID,
    name: str | None,
    base_url: str | None,
    auth_scheme: str | None,
    openapi_url: str | None,
    config: Mapping[str, Any] | None,
) -> CreatedRequest:
    """Create an ``integration`` proposal — Req 2.1–2.3, 2.5–2.9, 2.7.

    Validation order: required fields present → ``auth_scheme`` enum-valid →
    config secret-denylist gate → SSH rules (``ssh://host:port`` base_url; no
    ``target_address``) → ``openapi_url`` HTTPS + SSRF check. Stores only the
    non-secret ``proposed_config`` on the row and creates **no** ``services``
    row (Req 2.7). Secrets never reach this row (P-1).
    """
    await set_tenant_context(session, tenant_id)

    name_norm = _norm(name)
    if not name_norm:
        raise AccessRequestError(
            "invalid_argument", "name is required", field="name"
        )
    base_url_norm = _norm(base_url)
    if not base_url_norm:
        raise AccessRequestError(
            "invalid_argument", "base_url is required", field="base_url"
        )
    auth_scheme_norm = _norm(auth_scheme)
    if not auth_scheme_norm:
        raise AccessRequestError(
            "invalid_argument", "auth_scheme is required", field="auth_scheme"
        )

    # Req 2.3 — auth_scheme must be a member of the closed enum.
    if auth_scheme_norm not in _AUTH_SCHEME_ENUM:
        raise AccessRequestError(
            "invalid_argument",
            f"auth_scheme '{auth_scheme_norm}' is not a member of the "
            "closed auth_scheme enum",
            field="auth_scheme",
        )

    config_map: Mapping[str, Any] = config or {}

    # Req 2.4 — reject any secret field before it can be stored (P-1).
    offending = find_secret_denylist_field(config_map)
    if offending is not None:
        raise AccessRequestError(
            "secret_field_not_allowed",
            f"config field '{offending}' matches the secret denylist and "
            "must be supplied by the operator, not proposed by the agent",
            field=offending,
        )

    # Req 2.5 / 2.6 — SSH schemes: ssh://host:port base_url, no target_address.
    if is_ssh_auth_scheme(auth_scheme_norm):
        if not validate_ssh_base_url(base_url_norm):
            raise AccessRequestError(
                "invalid_argument",
                "base_url must be in ssh://host:port form for SSH auth schemes",
                field="base_url",
            )
        if "target_address" in config_map:
            raise AccessRequestError(
                "invalid_argument",
                "target_address is not accepted for SSH auth schemes; the "
                "upstream host:port is carried by base_url (ADR-0023)",
                field="target_address",
            )

    # Req 2.8 / 2.9 — openapi_url (when supplied) must be HTTPS + pass SSRF.
    openapi_url_norm = _norm(openapi_url)
    if openapi_url_norm:
        ok, reason = validate_openapi_url(openapi_url_norm)
        if not ok:
            raise AccessRequestError(
                "invalid_argument",
                f"openapi_url was rejected: {reason}",
                field="openapi_url",
            )

    # Assemble the non-secret proposed config actually persisted on the row.
    # The denylist gate above guarantees no secret field is present here (P-1).
    proposed_config: dict[str, Any] = dict(config_map)
    proposed_config["name"] = name_norm
    proposed_config["base_url"] = base_url_norm
    proposed_config["auth_scheme"] = auth_scheme_norm
    if openapi_url_norm:
        proposed_config["openapi_url"] = openapi_url_norm

    request_id = _new_request_id()
    request_uuid = _request_wire_to_uuid(request_id)
    now = datetime.now(timezone.utc)

    await _insert_request(
        session,
        tenant_id=tenant_id,
        request_uuid=request_uuid,
        kind="integration",
        requesting_agent_uuid=requesting_agent_id,
        service_uuid=None,
        action=None,
        target_agent_uuid=None,
        share_direction=None,
        proposed_config=proposed_config,
        created_at=now,
        expires_at=(expires_at := compute_expires_at(now)),
    )
    # For kind=integration no ``services`` row exists yet, so the created event
    # carries no ``service_id``/``action``; the non-secret proposed name/scheme
    # are intentionally NOT put on the audit payload (schema is
    # ``additionalProperties: false`` — only allowlisted keys allowed, Req 10.3).
    await _emit_created_audit(
        session,
        tenant_id=tenant_id,
        request_uuid=request_uuid,
        requesting_agent_uuid=requesting_agent_id,
        request_id=request_id,
        kind="integration",
        expires_at=expires_at,
        payload_target={},
    )
    return CreatedRequest(request_id=request_id, status="pending")


async def create_share_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    requesting_agent_id: uuid.UUID,
    service_id: uuid.UUID | None,
    action: str | None,
    target_agent_id: uuid.UUID | None,
) -> CreatedRequest:
    """Create a ``share`` request — Req 3.1–3.9.

    ``share_direction`` is ``outbound`` when the requester shares a grant it
    holds, ``inbound`` when it asks for access owned by another agent. Because
    the request always names a Target_Agent that would receive access, the
    distinguishing fact is whether the *requester* currently holds the
    ``(service, action)`` grant: if it does, this is an outbound share; if not,
    it is an inbound ask.

    Validation order (Req 3): required fields → no self-target → service exists
    → target exists → (outbound only) requester holds the grant → target not
    already granted.
    """
    await set_tenant_context(session, tenant_id)

    if service_id is None:
        raise AccessRequestError(
            "invalid_argument", "service_id is required", field="service_id"
        )
    action_norm = _norm(action)
    if not action_norm:
        raise AccessRequestError(
            "invalid_argument", "action is required", field="action"
        )
    if target_agent_id is None:
        raise AccessRequestError(
            "invalid_argument",
            "target_agent_id is required",
            field="target_agent_id",
        )

    # Req 3.4 — no self-target.
    if target_agent_id == requesting_agent_id:
        raise AccessRequestError(
            "invalid_argument",
            "target_agent_id must differ from the requesting agent",
            field="target_agent_id",
        )

    # Req 3.5 — service must exist in the requester's tenant.
    if not await _service_exists(session, tenant_id, service_id):
        raise AccessRequestError("service_not_found", "service not found")

    # Req 3.6 — target agent must exist in the requester's tenant.
    if not await _agent_exists(session, tenant_id, target_agent_id):
        raise AccessRequestError("agent_not_found", "target agent not found")

    # Determine share_direction from whether the requester holds the grant.
    requester_holds = await _grant_exists(
        session, tenant_id, requesting_agent_id, service_id, action_norm
    )
    share_direction: ShareDirection = "outbound" if requester_holds else "inbound"

    # Req 3.7 — outbound requires the requester to actually hold the grant.
    # (By construction outbound == requester_holds, so this only guards against
    # a future caller forcing a direction; kept explicit for the requirement.)
    if share_direction == "outbound" and not requester_holds:
        raise AccessRequestError(
            "action_not_granted",
            "requesting agent does not hold the (service, action) grant it "
            "is attempting to share",
        )

    # Req 3.8 — the target must not already hold the grant.
    if await _grant_exists(
        session, tenant_id, target_agent_id, service_id, action_norm
    ):
        raise AccessRequestError(
            "already_granted",
            "target agent already holds this (service, action) grant",
        )

    request_id = _new_request_id()
    request_uuid = _request_wire_to_uuid(request_id)
    now = datetime.now(timezone.utc)

    await _insert_request(
        session,
        tenant_id=tenant_id,
        request_uuid=request_uuid,
        kind="share",
        requesting_agent_uuid=requesting_agent_id,
        service_uuid=service_id,
        action=action_norm,
        target_agent_uuid=target_agent_id,
        share_direction=share_direction,
        proposed_config=None,
        created_at=now,
        expires_at=(expires_at := compute_expires_at(now)),
    )
    await _emit_created_audit(
        session,
        tenant_id=tenant_id,
        request_uuid=request_uuid,
        requesting_agent_uuid=requesting_agent_id,
        request_id=request_id,
        kind="share",
        expires_at=expires_at,
        payload_target={
            "service_id": db_uuid_to_wire(service_id, "svc"),
            "action": action_norm,
            "target_agent_id": db_uuid_to_wire(target_agent_id, "agent"),
            "share_direction": share_direction,
        },
    )
    return CreatedRequest(
        request_id=request_id, status="pending", share_direction=share_direction
    )


# ---------------------------------------------------------------------------
# Operator review — list + get — T-3.5
# ---------------------------------------------------------------------------
# Read paths for the Requests_Review_Area (Req 4). Both are tenant-scoped by
# the RLS ``tenant_isolation`` policy: ``set_tenant_context`` sets
# ``app.current_tenant`` for the transaction, so a request row from another
# tenant is simply not visible — a cross-tenant ``request_id`` therefore yields
# ``request_not_found`` without revealing cross-tenant existence (Req 4.4,
# 12.3, P-3).
#
# Wire form: internal UUIDs are translated to ULID-prefixed wire IDs on the way
# out via the shared ``db_uuid_to_wire`` encoder (``request_``/``agent_``/
# ``svc_``, ADR-0017.11). Incoming ``request_id`` is decoded with the shared
# ``wire_to_db_uuid`` decoder (which also accepts the legacy hex form).
#
# Source: T-3.5; design §Components / §Wire Contracts (AccessRequest shape);
#         Req 4.1, 4.2, 4.3, 4.4, 4.6; ADR-0008 (tenant GUC),
#         ADR-0017.11 (prefixed ULID), P-1 / P-3.

# Closed enums for the ``status`` / ``kind`` list filters — Req 4.3. A supplied
# filter value that is not a member is rejected with ``invalid_argument``.
_STATUS_ENUM: frozenset[str] = frozenset(
    {"pending", "approved", "rejected", "expired", "cancelled"}
)
_KIND_ENUM: frozenset[str] = frozenset({"access", "integration", "share"})

# Operator-supplied secret field names per auth_scheme — Req 4.6.
#
# The request row NEVER holds secrets (P-1); these are the field *names* the
# operator must fill during finalize, presented BLANK on the integration
# detail. We do not invent values — the ``dict`` values are always empty
# strings. Names mirror the credential-envelope conventions used at
# finalize/registration (api/services.py, api/_ssh_test.py).
_OPERATOR_SECRET_FIELDS: dict[str, tuple[str, ...]] = {
    "api_key_header": ("credential_value",),
    "api_key_query": ("credential_value",),
    "bearer_token": ("credential_value",),
    "basic_auth": ("credential_value",),
    "http_digest": ("credential_value",),
    "apple_jwt": ("credential_value",),
    "email_password": ("credential_value",),
    "email_app_password": ("credential_value",),
    "oauth2_client_credentials": ("client_secret",),
    "oidc_client_secret": ("client_secret",),
    "email_oauth2": ("client_secret",),
    "mtls": ("private_key_pem", "passphrase"),
    "ssh_private_key": ("private_key_pem", "passphrase"),
    "ssh_ca": ("private_key_pem", "passphrase"),
    "ssh_password": ("password",),
    "google_service_account": ("private_key",),
}


@dataclass(frozen=True)
class RequestListItem:
    """One row of the operator review list — Req 4.2 required fields.

    ``target`` is the kind-appropriate reference: ``service_id``/``action`` for
    access & share, ``target_agent_id``/``share_direction`` additionally for
    share, and a non-secret proposed-config summary for integration.
    """

    request_id: str
    kind: str
    status: str
    requesting_agent_id: str
    service_id: str | None
    action: str | None
    target_agent_id: str | None
    share_direction: ShareDirection | None
    proposed_config: dict[str, Any] | None
    created_at: datetime
    expires_at: datetime


@dataclass(frozen=True)
class RequestDetail:
    """Full request detail — Req 4.6.

    For an integration proposal, ``proposed_config`` carries the non-secret
    config and ``operator_secret_fields`` names the blank, operator-supplied
    secret fields (values always empty — the row never holds secrets, P-1).
    For non-integration kinds ``operator_secret_fields`` is ``None``.
    """

    request_id: str
    kind: str
    status: str
    requesting_agent_id: str
    service_id: str | None
    action: str | None
    target_agent_id: str | None
    share_direction: ShareDirection | None
    proposed_config: dict[str, Any] | None
    reason: str | None
    created_at: datetime
    expires_at: datetime
    resolved_at: datetime | None
    operator_secret_fields: dict[str, str] | None


def _wire_agent(uuid_value: uuid.UUID | None) -> str | None:
    return db_uuid_to_wire(uuid_value, "agent") if uuid_value is not None else None


def _wire_service(uuid_value: uuid.UUID | None) -> str | None:
    return db_uuid_to_wire(uuid_value, "svc") if uuid_value is not None else None


def _blank_operator_secret_fields(
    proposed_config: Mapping[str, Any] | None,
) -> dict[str, str] | None:
    """Return the blank operator-supplied secret fields for an integration.

    Derives the required secret field names from the proposed ``auth_scheme``
    and returns them mapped to empty strings (Req 4.6). Never reads or invents
    a secret value — the request row holds none (P-1). Returns ``None`` when the
    scheme is unknown/absent so the detail simply exposes no secret inputs.
    """
    if not proposed_config:
        return None
    scheme = proposed_config.get("auth_scheme")
    if not isinstance(scheme, str):
        return None
    field_names = _OPERATOR_SECRET_FIELDS.get(scheme)
    if not field_names:
        return None
    return {name: "" for name in field_names}


async def list_requests(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    status: str | None = None,
    kind: str | None = None,
) -> list[RequestListItem]:
    """List the tenant's access requests — Req 4.1, 4.2, 4.3.

    Tenant-scoped by RLS (the tenant GUC is set here); optional ``status`` and
    ``kind`` filters must be members of their respective closed enums else
    ``invalid_argument`` (Req 4.3). Ordered ``created_at`` descending (Req 4.1).
    Each item carries the Req 4.2 required fields, with internal UUIDs
    translated to prefixed-ULID wire form.
    """
    status_norm = _norm(status)
    if status_norm and status_norm not in _STATUS_ENUM:
        raise AccessRequestError(
            "invalid_argument",
            f"status '{status_norm}' is not a member of the status enum",
            field="status",
        )
    kind_norm = _norm(kind)
    if kind_norm and kind_norm not in _KIND_ENUM:
        raise AccessRequestError(
            "invalid_argument",
            f"kind '{kind_norm}' is not a member of the kind enum",
            field="kind",
        )

    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, kind, status, requesting_agent_id, service_id, action,"
            "       target_agent_id, share_direction, proposed_config,"
            "       created_at, expires_at"
            "  FROM access_requests"
            " WHERE tenant_id = :tid"
            "   AND (CAST(:status AS text) IS NULL OR status = CAST(:status AS text))"
            "   AND (CAST(:kind AS text) IS NULL OR kind = CAST(:kind AS text))"
            " ORDER BY created_at DESC, id DESC"
        ),
        {
            "tid": str(tenant_id),
            "status": status_norm or None,
            "kind": kind_norm or None,
        },
    )

    items: list[RequestListItem] = []
    for row in result.mappings():
        proposed = row["proposed_config"]
        items.append(
            RequestListItem(
                request_id=db_uuid_to_wire(row["id"], "request"),
                kind=row["kind"],
                # Lazy-on-read guard (Req 9.2): a pending-but-elapsed row reads
                # as ``expired`` without persisting the flip; the sweep owns
                # persistence + the audit event (design §Expiration Mechanism).
                status=effective_status(row["status"], row["expires_at"]),
                requesting_agent_id=db_uuid_to_wire(
                    row["requesting_agent_id"], "agent"
                ),
                service_id=_wire_service(row["service_id"]),
                action=row["action"],
                target_agent_id=_wire_agent(row["target_agent_id"]),
                share_direction=row["share_direction"],
                proposed_config=dict(proposed) if proposed is not None else None,
                created_at=row["created_at"],
                expires_at=row["expires_at"],
            )
        )
    return items


async def get_request(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_id: str,
) -> RequestDetail:
    """Return the full detail for one request — Req 4.4, 4.6.

    The row is loaded under the tenant GUC, so a cross-tenant or non-existent
    ``request_id`` is invisible and yields ``request_not_found`` without
    revealing cross-tenant existence (Req 4.4, 12.3, P-3). For an integration
    proposal the detail exposes the non-secret ``proposed_config`` plus the
    blank operator-supplied secret fields (Req 4.6); the row never holds
    secrets (P-1).
    """
    try:
        db_uuid = wire_to_db_uuid(request_id, "request")
    except ValueError:
        # A malformed request_ id can never name a visible row; treat it as
        # not-found rather than leaking a distinct error (Req 4.4).
        raise AccessRequestError("request_not_found", "request not found")

    await set_tenant_context(session, tenant_id)

    result = await session.execute(
        text(
            "SELECT id, kind, status, requesting_agent_id, service_id, action,"
            "       target_agent_id, share_direction, proposed_config, reason,"
            "       created_at, expires_at, resolved_at"
            "  FROM access_requests"
            " WHERE id = :id AND tenant_id = :tid"
        ),
        {"id": str(db_uuid), "tid": str(tenant_id)},
    )
    row = result.mappings().fetchone()
    if row is None:
        raise AccessRequestError("request_not_found", "request not found")

    proposed = row["proposed_config"]
    proposed_config = dict(proposed) if proposed is not None else None

    operator_secret_fields: dict[str, str] | None = None
    if row["kind"] == "integration":
        operator_secret_fields = _blank_operator_secret_fields(proposed_config)

    return RequestDetail(
        request_id=db_uuid_to_wire(row["id"], "request"),
        kind=row["kind"],
        # Lazy-on-read guard (Req 9.2): a pending-but-elapsed row reads as
        # ``expired`` here without persisting the flip or emitting an audit
        # event — the scheduled sweep owns persistence + the system-actor
        # audit event (design §Expiration Mechanism).
        status=effective_status(row["status"], row["expires_at"]),
        requesting_agent_id=db_uuid_to_wire(row["requesting_agent_id"], "agent"),
        service_id=_wire_service(row["service_id"]),
        action=row["action"],
        target_agent_id=_wire_agent(row["target_agent_id"]),
        share_direction=row["share_direction"],
        proposed_config=proposed_config,
        reason=row["reason"],
        created_at=row["created_at"],
        expires_at=row["expires_at"],
        resolved_at=row["resolved_at"],
        operator_secret_fields=operator_secret_fields,
    )


# ---------------------------------------------------------------------------
# Operator approval — branch by kind (reuse existing machinery) — T-5.1
# ---------------------------------------------------------------------------
# Approval is the single operator action that turns a ``pending`` request into
# a real grant / service / credential. It REUSES the existing machinery through
# the same interfaces the live endpoints use rather than reimplementing it
# (Req 14.4, design §Components "Reuse, don't reimplement"):
#
#   - grant creation mirrors ``api/permissions.py:grant_permission`` — the same
#     ``perm_`` ULID→UUID derivation, the same ``permission_grants`` INSERT
#     columns, and the same ``agent.permission.granted`` audit event. (There is
#     no importable grant *service* function today; the canonical logic lives in
#     the route handler, so the reuse here is the identical INSERT+audit shape.)
#     Two deliberate T-5.5 refinements over the canonical handler: this path
#     uses the schema-conformant payload key ``permission_id`` (the canonical
#     handler currently emits ``perm_id``, which does not match
#     ``ev_agent_permission_granted`` in audit-event.schema.json — a
#     pre-existing, out-of-scope non-conformance left untouched here) and sets
#     ``actor_id`` to the validated-session operator (``resolved_by``) rather
#     than ``None`` (Req 10.5).
#   - integration finalize creates the ``services`` row with the same columns as
#     ``api/services.py:create_service`` and stores the operator secret through
#     the EXISTING credential/Vault interface — ``VaultAdapterClient.put_credential``
#     (the same call ``api/credentials.py:create_credential`` makes). The
#     plaintext secret is passed only to that call; it never lands on the request
#     row, a log, an audit payload, or a span (P-1, S-SEC-1, ADR-0017.6).
#
# Tenant scope: ``set_tenant_context`` sets ``app.current_tenant`` so a
# cross-tenant / non-existent ``request_id`` is simply invisible under RLS and
# yields ``request_not_found`` (Req 5.5, 12.3, P-3).
#
# Change propagation: on any grant creation this publishes on the GLOBAL
# ``mintkey:agent`` channel (ADR-0010, ADR-0014.1) so the proxy/broker/MCP
# invalidate cached agent state within ≤ 5s (Req 5.7, 7.2, P-9). The grant route
# handler does NOT notify on create, so the publish is done here explicitly.
#
# Vault-down finalize: if ``put_credential`` raises, the whole transaction is
# left un-committed and ``vault_unavailable`` is raised, so NO ``services`` row,
# NO credential row, and NO secret is persisted (Req 6.7). The router owns the
# transaction boundary (``session.begin()``), so raising here rolls it all back.
#
# Audit at every state change (T-5.5, DONE): every approve branch emits the
# ``access_request.approved`` state-change event through the single
# ``audit.emit()`` chokepoint, in the SAME transaction as the state change and
# the reused ``agent.permission.granted`` / ``service.registered`` /
# ``credential.registered`` events (Req 10.1, 10.4, 10.6). ``actor_type`` is
# ``operator`` and ``actor_id`` is the validated-session operator id threaded in
# as ``resolved_by`` (ADR-0019, Req 10.5, Property 11). Because audit_emit runs
# in the caller-owned transaction, a failing audit write aborts the whole
# approval — grant/service/credential/status-update all roll back (Req 10.6,
# Property 12). The router (T-6.1) owns the ``session.begin()`` boundary; this
# service never commits independently, so atomicity holds.
#
# The reused ``agent.permission.granted`` payload includes the created
# ``permission_id``, which is threaded into the ``access_request.approved``
# payload so the two events correlate. The OTel counters / span-attribute
# allowlist are T-9.x.


@dataclass(frozen=True)
class ApprovedRequest:
    """Result of a successful approve: the wire ID plus the new status."""

    request_id: str
    status: str
    kind: str


def _new_prefixed_id(prefix: str) -> tuple[str, uuid.UUID]:
    """Return ``(wire_id, internal_uuid)`` for a fresh ``<prefix>_`` ULID.

    Mirrors the ULID→UUID derivation used by ``api/permissions.py`` (perm_) and
    ``api/services.py`` (svc_): a 48-bit ms timestamp + 80 random bits encoded
    in Crockford base32, with the internal DB UUID derived from the same 128-bit
    value so the wire form decodes back to the stored PK (ADR-0017.11).
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

    wire_id = f"{prefix}_" + "".join(t_enc) + "".join(r_enc)
    val = 0
    for ch in (wire_id[len(prefix) + 1:]).upper():
        val = (val << 5) | _CROCKFORD.index(ch)
    val &= (1 << 128) - 1
    return wire_id, uuid.UUID(int=val)


async def _create_grant(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    agent_uuid: uuid.UUID,
    service_uuid: uuid.UUID,
    action: str,
    granted_by: uuid.UUID | None,
) -> str | None:
    """Create a ``(agent, service, action)`` grant, idempotently (Req 5.1, 7.1, 7.5).

    Mirrors ``api/permissions.py:grant_permission`` exactly: derive a ``perm_``
    ULID→UUID, INSERT the same ``permission_grants`` columns (empty constraints),
    and emit ``agent.permission.granted`` through the audit chokepoint. If a
    grant for the exact ``(agent, service, action)`` already exists, this is a
    no-op (no duplicate row, no second audit) so approval stays idempotent
    (Req 7.5, Property 6). The grant is created under the caller's already-set
    tenant GUC.

    Returns the ``perm_`` wire id of the newly created grant so the caller can
    correlate it into the ``access_request.approved`` audit payload, or ``None``
    when the grant already existed (idempotent no-op).

    T-5.5: ``agent.permission.granted`` carries ``actor_type="operator"`` and
    ``actor_id=granted_by`` — the validated-session operator identity threaded
    from the router (ADR-0019, Req 10.5).
    """
    if await _grant_exists(session, tenant_id, agent_uuid, service_uuid, action):
        return None  # idempotent — grant already present (Req 7.5)

    perm_wire_id, perm_uuid = _new_prefixed_id("perm")
    now = datetime.now(timezone.utc)
    await session.execute(
        text(
            "INSERT INTO permission_grants"
            " (id, tenant_id, agent_id, service_id, action, constraints,"
            "  created_at, created_by)"
            " VALUES"
            " (:id, :tenant_id, :agent_id, :service_id, :action,"
            "  CAST(:constraints AS jsonb), :created_at, :created_by)"
        ),
        {
            "id": str(perm_uuid),
            "tenant_id": str(tenant_id),
            "agent_id": str(agent_uuid),
            "service_id": str(service_uuid),
            "action": action,
            "constraints": json.dumps({}),
            "created_at": now,
            "created_by": str(granted_by) if granted_by is not None else str(agent_uuid),
        },
    )
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="agent.permission.granted",
        actor_id=granted_by,
        actor_type="operator",
        target_id=perm_uuid,
        target_type="permission",
        payload={
            "permission_id": perm_wire_id,
            "agent_id": db_uuid_to_wire(agent_uuid, "agent"),
            "service_id": db_uuid_to_wire(service_uuid, "svc"),
            "action": action,
        },
    )
    return perm_wire_id


async def _publish_agent_grant_change(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    agent_uuid: uuid.UUID,
    service_uuid: uuid.UUID,
    action: str,
) -> None:
    """Publish a grant change on the global ``mintkey:agent`` channel (P-9).

    Reuses ``changes.publisher.notify_change`` with bound parameters. The
    channel is global; the tenant filter lives in the consumer wrapper
    (ADR-0014.1). Dependent components observe the new grant within ≤ 5s
    (Req 5.7, 7.2).
    """
    await notify_change(
        session,
        "mintkey:agent",
        {
            "event": "agent.permission.granted",
            "tenant_id": str(tenant_id),
            "agent_id": db_uuid_to_wire(agent_uuid, "agent"),
            "service_id": db_uuid_to_wire(service_uuid, "svc"),
            "action": action,
        },
    )


async def _mark_approved(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_uuid: uuid.UUID,
    resolved_by: uuid.UUID | None,
) -> None:
    """Set the request ``status = approved`` with ``resolved_at``/``resolved_by``.

    ``resolved_by`` is the operator identity from the validated session (ADR-0019);
    the router passes it in. It may be ``None`` until T-6.1 threads the session
    identity through.
    """
    await session.execute(
        text(
            "UPDATE access_requests"
            "   SET status = 'approved', resolved_at = :now, resolved_by = :by"
            " WHERE id = :id AND tenant_id = :tid"
        ),
        {
            "now": datetime.now(timezone.utc),
            "by": str(resolved_by) if resolved_by is not None else None,
            "id": str(request_uuid),
            "tid": str(tenant_id),
        },
    )


async def _emit_approved_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_uuid: uuid.UUID,
    request_id: str,
    kind: str,
    resolved_by: uuid.UUID | None,
    service_uuid: uuid.UUID | None = None,
    action: str | None = None,
    requesting_agent_uuid: uuid.UUID | None = None,
    target_agent_uuid: uuid.UUID | None = None,
    permission_id: str | None = None,
) -> None:
    """Emit ``access_request.approved`` through the single audit chokepoint (T-5.5).

    Fired in the SAME transaction as the state change and the reused
    grant/service/credential events, so a failed audit write rolls the whole
    approval back (Req 10.1, 10.4, 10.6, Property 12). ``actor_type`` is
    ``operator`` and ``actor_id`` is the validated-session operator identity
    (``resolved_by``, ADR-0019, Req 10.5, Property 11).

    Payload conforms to ``ev_access_request_approved`` (T-1.3, schema is
    ``additionalProperties: false``): ``request_id`` + ``kind`` + ``status`` are
    required; ``service_id`` / ``action`` / ``requesting_agent_id`` /
    ``target_agent_id`` / ``permission_id`` are threaded per branch. All values
    are identifier/metadata-only — no secret or denylisted values (Req 10.3).
    """
    payload: dict[str, Any] = {
        "request_id": request_id,
        "kind": kind,
        "status": "approved",
    }
    if service_uuid is not None:
        payload["service_id"] = db_uuid_to_wire(service_uuid, "svc")
    if action is not None:
        payload["action"] = action
    if requesting_agent_uuid is not None:
        payload["requesting_agent_id"] = db_uuid_to_wire(
            requesting_agent_uuid, "agent"
        )
    if target_agent_uuid is not None:
        payload["target_agent_id"] = db_uuid_to_wire(target_agent_uuid, "agent")
    if permission_id is not None:
        payload["permission_id"] = permission_id

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="access_request.approved",
        actor_id=resolved_by,
        actor_type="operator",
        target_id=request_uuid,
        target_type="access_request",
        payload=payload,
    )
    # T-9.2 — increment access_request_approved_total{kind,tenant_id} and emit
    # the structured transition log (request_id/kind/status only, Req 11.2/11.4).
    # Single funnel for all three approve branches (access/share/integration).
    record_transition(
        "approved", request_id=request_id, kind=kind, tenant_id=str(tenant_id)
    )


async def emit_expired_audit(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_uuid: uuid.UUID,
    request_id: str,
    kind: str,
    expires_at: datetime,
) -> None:
    """Emit ``access_request.expired`` through the single audit chokepoint.

    **Left for T-5.7** — the lazy-on-read guard + scheduled sweep. The sweep
    flips ``pending → expired`` and calls this helper once per row, in the SAME
    transaction as the status update, so the expiry audit is atomic like every
    other state change (Req 10.1). ``actor_type`` is ``system`` — expiry is not
    operator- or agent-initiated (Req 10.5, Property 11); ``actor_id`` is
    ``None`` (no human/agent actor).

    Payload conforms to ``ev_access_request_expired`` (T-1.3, schema is
    ``additionalProperties: false``): required ``request_id`` + ``kind`` +
    ``status`` (const ``expired``) + ``expires_at``. Identifier/metadata-only
    (Req 10.3).

    T-5.7 owns computing which rows are elapsed and setting ``status =
    'expired'``; it need only call this helper for each swept row.
    """
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="access_request.expired",
        actor_id=None,
        actor_type="system",
        target_id=request_uuid,
        target_type="access_request",
        payload={
            "request_id": request_id,
            "kind": kind,
            "status": "expired",
            "expires_at": expires_at.astimezone(timezone.utc).isoformat(),
        },
    )


# ---------------------------------------------------------------------------
# Scheduled expiry sweep — persist pending → expired + system audit — T-5.7
# ---------------------------------------------------------------------------
# The lazy-on-read guard above prevents any expired row from being actioned,
# but it never persists the flip and never emits the system-actor
# ``access_request.expired`` audit event that Req 10.1 requires. The scheduled
# sweep is what makes the stored status accurate for the review list and
# extends the per-tenant audit chain (design §Expiration Mechanism, both).
#
# It follows the ``apps/audit-verify-job/`` precedent for cross-tenant iteration
# (enumerate the tenants, then work each one), with one important difference:
# ``audit.emit()`` takes a per-tenant advisory lock and reads/writes the
# per-tenant ``audit_chain_state`` (see mintkey_models.audit), and
# ``access_requests`` is RLS-protected. So the sweep sets the tenant GUC via
# ``set_tenant_context`` for each tenant (P-3, ADR-0008) and emits inside that
# tenant's scope, rather than using the platform_admin_view escape hatch — the
# per-tenant audit chain must be advanced under its own tenant context.
#
# Atomicity (Req 10.1, 10.6): the caller owns the transaction boundary (the job
# entrypoint opens one ``session.begin()`` per tenant). For each swept row the
# status UPDATE and the ``access_request.expired`` emit run in that same
# transaction, so a failed audit write rolls the flip back — no row is marked
# expired without its audit event.
#
# Source: T-5.7; design §Expiration Mechanism; Req 9.2, 9.4, 10.1, 10.5;
#         ADR-0008 (tenant GUC), ADR-0014.7 (audit chokepoint),
#         apps/audit-verify-job/ (cross-tenant job precedent).


async def sweep_tenant_expired(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    now: datetime | None = None,
) -> int:
    """Flip this tenant's elapsed ``pending`` rows to ``expired`` — Req 9.2, 9.4, 10.1.

    Sets the tenant GUC (RLS scope + per-tenant audit chain, P-3, ADR-0008),
    selects the tenant's ``pending`` rows whose ``expires_at`` has elapsed
    (``now() >= expires_at``, inclusive boundary matching ``is_elapsed`` /
    Property 9), and for each row: UPDATEs ``status = 'expired'`` (recording
    ``resolved_at``, ``resolved_by`` left NULL — expiry is system-initiated)
    and emits one ``access_request.expired`` event through the single
    ``audit.emit()`` chokepoint with ``actor_type = system`` (Req 10.5),
    reusing ``emit_expired_audit`` (T-5.5). Creates NO grant/service/credential
    (Req 9.4).

    Runs inside the caller's transaction so the flip + audit are atomic
    (Req 10.6). Returns the number of rows expired for this tenant.
    """
    current = now or datetime.now(timezone.utc)

    await set_tenant_context(session, tenant_id)

    rows = (
        await session.execute(
            text(
                "SELECT id, kind, expires_at FROM access_requests"
                " WHERE tenant_id = :tid AND status = 'pending'"
                "   AND expires_at <= :now"
                " ORDER BY created_at ASC, id ASC"
                " FOR UPDATE"
            ),
            {"tid": str(tenant_id), "now": current},
        )
    ).mappings().fetchall()

    expired_count = 0
    for row in rows:
        request_uuid: uuid.UUID = row["id"]
        await session.execute(
            text(
                "UPDATE access_requests"
                "   SET status = 'expired', resolved_at = :now"
                " WHERE id = :id AND tenant_id = :tid AND status = 'pending'"
            ),
            {"now": current, "id": str(request_uuid), "tid": str(tenant_id)},
        )
        # One access_request.expired per row through the single chokepoint,
        # in this same transaction (Req 10.1, 10.6). Reuses the T-5.5 helper.
        expired_wire_id = db_uuid_to_wire(request_uuid, "request")
        await emit_expired_audit(
            session,
            tenant_id=tenant_id,
            request_uuid=request_uuid,
            request_id=expired_wire_id,
            kind=row["kind"],
            expires_at=row["expires_at"],
        )
        # T-9.2 — increment access_request_expired_total{kind,tenant_id} and emit
        # the structured transition log (request_id/kind/status only,
        # Req 11.2/11.4), once per swept row.
        record_transition(
            "expired",
            request_id=expired_wire_id,
            kind=row["kind"],
            tenant_id=str(tenant_id),
        )
        expired_count += 1

    return expired_count


def _extract_secret_value(credential: Mapping[str, Any] | None) -> str:
    """Return the operator-supplied secret plaintext, or raise ``missing_secret_material``.

    The finalize body carries the secret under ``credential`` (x-mintkey-sensitive).
    A ``credential_value`` (single-secret schemes) or any non-empty secret field is
    required; a missing/blank secret is rejected with ``missing_secret_material``
    (Req 6.6) BEFORE any service row or Vault write. The value is returned to the
    caller only to be handed straight to the Vault Adapter — it is never persisted,
    logged, audited, or spanned (P-1, S-SEC-1).
    """
    if not credential:
        raise AccessRequestError(
            "missing_secret_material",
            "the integration's required secret material is blank",
        )
    raw = credential.get("credential_value", credential.get("value"))
    if isinstance(raw, str) and raw.strip():
        return raw
    # Non-``credential_value`` schemes (e.g. a structured JSON envelope) — accept
    # the credential as a JSON string only when it carries at least one non-blank
    # value; an all-blank payload is treated as missing.
    if any(isinstance(v, str) and v.strip() for v in credential.values()):
        return json.dumps({k: v for k, v in credential.items()})
    raise AccessRequestError(
        "missing_secret_material",
        "the integration's required secret material is blank",
    )


async def approve(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_id: str,
    vault: VaultAdapterClient,
    resolved_by: uuid.UUID | None = None,
    credential: Mapping[str, Any] | None = None,
    config: Mapping[str, Any] | None = None,
) -> ApprovedRequest:
    """Approve a pending request, branching by ``kind`` — Req 5, 6.2/6.5–6.7, 7.

    Reuses the existing grant, service-registration, and credential/Vault
    machinery (Req 14.4). The router owns the transaction and passes the
    operator ``resolved_by`` from the validated session (ADR-0019), the Vault
    client, and — for an integration finalize — the operator-supplied secret
    ``credential`` (x-mintkey-sensitive) plus any edited non-secret ``config``.

    Branches:
      - ``access``      → grant ``(requesting_agent, service, action)``.
      - ``share``       → grant ``(target_agent, service, action)``; re-verify the
                          service still exists (``service_not_found``, Req 7.3);
                          idempotent if the grant already exists (Req 7.5).
      - ``integration`` → apply operator config edits over the proposed config
                          (Req 6.2), create the ``services`` row (existing
                          registration columns), then store the secret via
                          ``vault.put_credential`` (existing credential/Vault
                          path). A blank secret → ``missing_secret_material``
                          (Req 6.6, before any write); a Vault outage →
                          ``vault_unavailable`` with nothing persisted (Req 6.7).

    Errors: ``request_not_found`` (missing/cross-tenant, Req 5.5/12.3),
    ``request_not_pending`` (Req 5.6/7.4), ``service_not_found`` (share, Req 7.3),
    ``missing_secret_material`` (Req 6.6), ``vault_unavailable`` (Req 6.7).
    """
    # Vault-down detection reuses the same gRPC error type the vault client
    # surfaces from ``put_credential`` (imported lazily to keep the pure-helper
    # import surface free of grpc for callers that only use validation helpers).
    import grpc  # noqa: PLC0415

    try:
        db_uuid = wire_to_db_uuid(request_id, "request")
    except ValueError:
        # Malformed request_ id can never name a visible row — Req 5.5 / 12.3.
        raise AccessRequestError("request_not_found", "request not found")

    await set_tenant_context(session, tenant_id)

    row = (
        await session.execute(
            text(
                "SELECT id, kind, status, requesting_agent_id, service_id,"
                "       action, target_agent_id, proposed_config, expires_at"
                "  FROM access_requests"
                " WHERE id = :id AND tenant_id = :tid"
                " FOR UPDATE"
            ),
            {"id": str(db_uuid), "tid": str(tenant_id)},
        )
    ).mappings().fetchone()

    if row is None:
        raise AccessRequestError("request_not_found", "request not found")
    # Lazy-on-read guard (Req 9.5): a row whose stored status is pending but
    # whose expires_at has elapsed is treated as expired, so approve is refused
    # with request_not_pending — no expired request is ever actioned regardless
    # of sweep timing (design §Expiration Mechanism). The guard does NOT persist
    # the flip or emit an audit event here; the sweep owns that.
    if effective_status(row["status"], row["expires_at"]) != "pending":
        raise AccessRequestError(
            "request_not_pending",
            f"request is {effective_status(row['status'], row['expires_at'])}, "
            "not pending",
        )

    kind: str = row["kind"]
    request_uuid: uuid.UUID = row["id"]

    if kind == "access":
        agent_uuid: uuid.UUID = row["requesting_agent_id"]
        service_uuid: uuid.UUID = row["service_id"]
        action: str = row["action"]
        perm_wire_id = await _create_grant(
            session,
            tenant_id=tenant_id,
            agent_uuid=agent_uuid,
            service_uuid=service_uuid,
            action=action,
            granted_by=resolved_by,
        )
        await _mark_approved(
            session, tenant_id=tenant_id, request_uuid=request_uuid,
            resolved_by=resolved_by,
        )
        # T-5.5 — emit the approved state-change event in the same transaction.
        await _emit_approved_audit(
            session,
            tenant_id=tenant_id,
            request_uuid=request_uuid,
            request_id=request_id,
            kind=kind,
            resolved_by=resolved_by,
            service_uuid=service_uuid,
            action=action,
            requesting_agent_uuid=agent_uuid,
            permission_id=perm_wire_id,
        )
        await _publish_agent_grant_change(
            session, tenant_id=tenant_id, agent_uuid=agent_uuid,
            service_uuid=service_uuid, action=action,
        )
        return ApprovedRequest(request_id=request_id, status="approved", kind=kind)

    if kind == "share":
        target_uuid: uuid.UUID = row["target_agent_id"]
        requesting_uuid: uuid.UUID = row["requesting_agent_id"]
        service_uuid = row["service_id"]
        action = row["action"]
        # Req 7.3 — the service must still exist at approval time.
        if not await _service_exists(session, tenant_id, service_uuid):
            raise AccessRequestError("service_not_found", "service not found")
        perm_wire_id = await _create_grant(
            session,
            tenant_id=tenant_id,
            agent_uuid=target_uuid,
            service_uuid=service_uuid,
            action=action,
            granted_by=resolved_by,
        )
        await _mark_approved(
            session, tenant_id=tenant_id, request_uuid=request_uuid,
            resolved_by=resolved_by,
        )
        # T-5.5 — emit the approved state-change event in the same transaction.
        await _emit_approved_audit(
            session,
            tenant_id=tenant_id,
            request_uuid=request_uuid,
            request_id=request_id,
            kind=kind,
            resolved_by=resolved_by,
            service_uuid=service_uuid,
            action=action,
            requesting_agent_uuid=requesting_uuid,
            target_agent_uuid=target_uuid,
            permission_id=perm_wire_id,
        )
        await _publish_agent_grant_change(
            session, tenant_id=tenant_id, agent_uuid=target_uuid,
            service_uuid=service_uuid, action=action,
        )
        return ApprovedRequest(request_id=request_id, status="approved", kind=kind)

    # kind == "integration" — finalize (create service + store secret).
    proposed = row["proposed_config"]
    proposed_config: dict[str, Any] = dict(proposed) if proposed is not None else {}
    # Req 6.2 — operator config edits override the agent-proposed values.
    if config:
        proposed_config.update(dict(config))

    # Req 6.6 — a blank secret is rejected BEFORE any service row or Vault write.
    # The plaintext is used only for the Vault call below (P-1); never persisted.
    secret_plaintext = _extract_secret_value(credential)

    name = str(proposed_config.get("name") or "").strip()
    base_url = str(proposed_config.get("base_url") or "").strip()
    auth_scheme = str(proposed_config.get("auth_scheme") or "").strip()
    openapi_url = proposed_config.get("openapi_url")
    display_name = proposed_config.get("display_name")
    description = proposed_config.get("description")
    header_name = str(proposed_config.get("header_name") or "")
    query_param = str(proposed_config.get("query_param") or "")
    ssh_user = str(proposed_config.get("ssh_user") or "")

    svc_wire_id, svc_uuid = _new_prefixed_id("svc")
    now = datetime.now(timezone.utc)
    slug = name.lower().replace(" ", "-")

    # Create the services row using the same columns as api/services.py:create_service
    # (existing service-registration path — Req 6.5, 14.4).
    await session.execute(
        text(
            "INSERT INTO services"
            " (id, tenant_id, name, slug, display_name, description,"
            "  base_url, auth_scheme, openapi_url, status, created_at, updated_at)"
            " VALUES"
            " (:id, :tenant_id, :name, :slug, :display_name, :description,"
            "  :base_url, :auth_scheme, :openapi_url, 'active', :created_at, :updated_at)"
        ),
        {
            "id": str(svc_uuid),
            "tenant_id": str(tenant_id),
            "name": name,
            "slug": slug,
            "display_name": display_name,
            "description": description,
            "base_url": base_url,
            "auth_scheme": auth_scheme,
            "openapi_url": openapi_url,
            "created_at": now,
            "updated_at": now,
        },
    )
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="service.registered",
        actor_id=resolved_by,
        actor_type="operator",
        target_id=svc_uuid,
        target_type="service",
        payload={
            "service_id": svc_wire_id,
            "name": name,
            "base_url": base_url,
            "auth_scheme": auth_scheme,
            "actions": [],
            "display_name": str(display_name) if display_name else name,
        },
    )

    # Store the secret via the EXISTING credential/Vault interface. The plaintext
    # leaves scope here and only here; the Vault Adapter encrypts it (ADR-0014.4,
    # P-1). A Vault outage surfaces as an AioRpcError — we translate it to
    # ``vault_unavailable`` and let the router's transaction roll back, so NO
    # services row and NO credential/secret are persisted (Req 6.7).
    try:
        vault_result = await vault.put_credential(
            tenant_id=str(tenant_id),
            service_id=str(svc_uuid),
            auth_scheme=auth_scheme,
            plaintext=secret_plaintext,  # secret leaves scope only here
            target_url=base_url,
            header_name=header_name,
            query_param=query_param,
            target_address="",
            ssh_user=ssh_user,
        )
    except grpc.aio.AioRpcError:
        # Do NOT commit anything: raising aborts the router-owned transaction so
        # the services INSERT above is rolled back and no secret is persisted.
        raise AccessRequestError(
            "vault_unavailable", "the credential store is unavailable"
        )

    key_version = int(vault_result.get("key_version", 1))  # type: ignore[call-overload]
    cred_wire_id, cred_uuid = _new_prefixed_id("cred")
    # Metadata-only credentials row (NO plaintext) — mirrors api/credentials.py.
    await session.execute(
        text(
            "INSERT INTO credentials"
            " (id, tenant_id, service_id, key_version, ciphertext, nonce,"
            "  wrapped_dek, auth_scheme, status, created_at)"
            " VALUES"
            " (:id, :tenant_id, :service_id, :key_version, :ciphertext, :nonce,"
            "  :wrapped_dek, :auth_scheme, 'active', :created_at)"
        ),
        {
            "id": str(cred_uuid),
            "tenant_id": str(tenant_id),
            "service_id": str(svc_uuid),
            "key_version": key_version,
            "ciphertext": b"",
            "nonce": b"",
            "wrapped_dek": b"",
            "auth_scheme": auth_scheme,
            "created_at": now,
        },
    )
    await session.execute(
        text(
            "UPDATE services SET current_key_version = :kv, updated_at = :now"
            " WHERE id = :sid AND tenant_id = :tid"
        ),
        {"kv": key_version, "now": now, "sid": str(svc_uuid), "tid": str(tenant_id)},
    )
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="credential.registered",
        actor_id=resolved_by,
        actor_type="operator",
        target_id=cred_uuid,
        target_type="credential",
        payload={
            "credential_id": cred_wire_id,
            "service_id": svc_wire_id,
            "key_version": key_version,
            "auth_scheme": auth_scheme,
        },
    )

    await _mark_approved(
        session, tenant_id=tenant_id, request_uuid=request_uuid,
        resolved_by=resolved_by,
    )
    # T-5.5 — emit the approved state-change event in the same transaction. The
    # newly registered service is the target; no grant/permission is created on
    # the integration finalize path, so no ``permission_id`` is carried.
    await _emit_approved_audit(
        session,
        tenant_id=tenant_id,
        request_uuid=request_uuid,
        request_id=request_id,
        kind=kind,
        resolved_by=resolved_by,
        service_uuid=svc_uuid,
        requesting_agent_uuid=row["requesting_agent_id"],
    )
    return ApprovedRequest(request_id=request_id, status="approved", kind=kind)


# ---------------------------------------------------------------------------
# Operator rejection — record a reason, create no artifacts — T-5.3
# ---------------------------------------------------------------------------
# Reject is the operator action that turns a ``pending`` request into a terminal
# ``rejected`` state carrying a human-readable ``reason``. Unlike approve it
# creates NO grant, service, or credential (Req 8.3) — it only mutates the
# request row.
#
# It follows the same seams the rest of the module established:
#   - ``set_tenant_context`` sets ``app.current_tenant`` so a cross-tenant /
#     non-existent ``request_id`` is invisible under RLS and yields
#     ``request_not_found`` without revealing cross-tenant existence
#     (Req 8.6, 12.3, P-3).
#   - the row is loaded ``FOR UPDATE`` under the tenant GUC and its ``status``
#     is guarded ``== pending`` else ``request_not_pending`` — leaving the
#     existing ``status`` and ``reason`` unchanged (Req 8.7).
#   - ``reason`` is validated first: a missing / empty / whitespace-only /
#     over-1000-char ``reason`` is rejected with ``reason_required`` and no row
#     change (Req 8.2). Whitespace-only counts as empty. The length bound is
#     checked on the ORIGINAL (untrimmed) value so a >1000-char reason is
#     rejected even if it would trim shorter, matching the OpenAPI
#     ``maxLength: 1000`` on the raw body.
#
# Audit (T-5.5, DONE): the ``access_request.rejected`` state-change event is
# emitted inline through the single ``audit.emit()`` chokepoint in the same
# transaction as the status update (same atomic-in-txn convention as the create
# and approve paths, Req 10.1, 10.4, 10.6). It carries ``actor_type="operator"``
# with ``actor_id=resolved_by`` — the validated-session operator identity
# (ADR-0019, Req 10.5). A failing audit write aborts the reject (Property 12).
#
# Source: T-5.3; design §Components / §Sequence (reject path); Req 8.1, 8.2,
#         8.3, 8.6, 8.7, 10.1; ADR-0008 (tenant GUC), ADR-0017.11 (prefixed
#         ULID), ADR-0014.7 (audit chokepoint), ADR-0019 (session identity).

# The reject ``reason`` upper bound mirrors the OpenAPI ``maxLength: 1000`` on
# the AccessRequestReject body (Req 8.2).
MAX_REJECT_REASON_LEN = 1000


@dataclass(frozen=True)
class RejectedRequest:
    """Result of a successful reject: the wire ID, the new status, the reason."""

    request_id: str
    status: str
    reason: str


async def _mark_rejected(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_uuid: uuid.UUID,
    reason: str,
    resolved_by: uuid.UUID | None,
) -> None:
    """Set the request ``status = rejected`` with ``reason``/``resolved_at``/``resolved_by``.

    Mirrors ``_mark_approved`` on the approve path. ``resolved_by`` is the
    operator identity from the validated session (ADR-0019); the router passes
    it in and it may be ``None`` until T-6.1 threads the session identity
    through. Creates no grant/service/credential (Req 8.3) — this is the only
    write.
    """
    await session.execute(
        text(
            "UPDATE access_requests"
            "   SET status = 'rejected', reason = :reason,"
            "       resolved_at = :now, resolved_by = :by"
            " WHERE id = :id AND tenant_id = :tid"
        ),
        {
            "reason": reason,
            "now": datetime.now(timezone.utc),
            "by": str(resolved_by) if resolved_by is not None else None,
            "id": str(request_uuid),
            "tid": str(tenant_id),
        },
    )


async def reject(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_id: str,
    reason: str | None,
    resolved_by: uuid.UUID | None = None,
) -> RejectedRequest:
    """Reject a pending request, recording a reason — Req 8.1, 8.2, 8.3, 8.6, 8.7.

    Validation order:
      1. ``reason`` — required, non-empty, non-whitespace-only, ≤ 1000 chars;
         else ``reason_required`` with no row change (Req 8.2).
      2. load the row ``FOR UPDATE`` under the tenant GUC — a missing /
         cross-tenant ``request_id`` → ``request_not_found`` (Req 8.6, 12.3).
      3. guard ``status == pending`` — else ``request_not_pending`` leaving the
         existing ``status`` and ``reason`` unchanged (Req 8.7).

    On success it sets ``status = rejected``, stores the trimmed ``reason``, and
    sets ``resolved_at``/``resolved_by``. It creates NO grant, service, or
    credential (Req 8.3). The ``access_request.rejected`` audit event is emitted
    in the same transaction through the single chokepoint (T-5.5).
    """
    # Req 8.2 — validate the reason BEFORE any DB access so an invalid reason
    # leaves the request entirely unchanged. The length bound is checked on the
    # raw value (matching OpenAPI maxLength: 1000); emptiness is checked after
    # trimming so a whitespace-only reason counts as empty.
    if reason is None or len(reason) > MAX_REJECT_REASON_LEN:
        raise AccessRequestError(
            "reason_required",
            "a non-empty rejection reason of at most "
            f"{MAX_REJECT_REASON_LEN} characters is required",
            field="reason",
        )
    reason_norm = reason.strip()
    if not reason_norm:
        raise AccessRequestError(
            "reason_required",
            "a non-empty rejection reason is required",
            field="reason",
        )

    try:
        db_uuid = wire_to_db_uuid(request_id, "request")
    except ValueError:
        # Malformed request_ id can never name a visible row — Req 8.6 / 12.3.
        raise AccessRequestError("request_not_found", "request not found")

    await set_tenant_context(session, tenant_id)

    row = (
        await session.execute(
            text(
                "SELECT id, kind, status, expires_at FROM access_requests"
                " WHERE id = :id AND tenant_id = :tid"
                " FOR UPDATE"
            ),
            {"id": str(db_uuid), "tid": str(tenant_id)},
        )
    ).mappings().fetchone()

    if row is None:
        raise AccessRequestError("request_not_found", "request not found")
    # Lazy-on-read guard (Req 9.5): a pending-but-elapsed row is treated as
    # expired, so reject is refused with request_not_pending and the existing
    # status/reason are left unchanged (design §Expiration Mechanism). The guard
    # does NOT persist the flip or emit an audit event; the sweep owns that.
    if effective_status(row["status"], row["expires_at"]) != "pending":
        raise AccessRequestError(
            "request_not_pending",
            f"request is {effective_status(row['status'], row['expires_at'])}, "
            "not pending",
        )

    request_uuid: uuid.UUID = row["id"]
    kind: str = row["kind"]

    await _mark_rejected(
        session,
        tenant_id=tenant_id,
        request_uuid=request_uuid,
        reason=reason_norm,
        resolved_by=resolved_by,
    )
    # T-5.5: emit the rejected state-change event through the single audit
    # chokepoint, atomically in this transaction (Req 10.1, 10.4, 10.6).
    # ``actor_type=operator`` / ``actor_id=resolved_by`` (validated-session
    # identity, Req 10.5). Payload is identifier/metadata-only — the reason is
    # operator-authored non-secret text (no secret/denylisted values, Req 10.3).
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="access_request.rejected",
        actor_id=resolved_by,
        actor_type="operator",
        target_id=request_uuid,
        target_type="access_request",
        payload={
            "request_id": request_id,
            "kind": kind,
            "status": "rejected",
            "reason": reason_norm,
        },
    )
    # T-9.2 — increment access_request_rejected_total{kind,tenant_id} and emit
    # the structured transition log (request_id/kind/status only, Req 11.2/11.4).
    # The operator ``reason`` is NOT placed on the metric label or the log line.
    record_transition(
        "rejected", request_id=request_id, kind=kind, tenant_id=str(tenant_id)
    )
    return RejectedRequest(
        request_id=request_id, status="rejected", reason=reason_norm
    )


# ---------------------------------------------------------------------------
# Connection_Test — secret-free upstream handshake (10s timeout) — T-5.4
# ---------------------------------------------------------------------------
# The operator, before finalizing an ``integration`` proposal, triggers a
# Connection_Test (``POST .../{request_id}/test``) to confirm the credential +
# base URL produce a successful upstream handshake. This REUSES the existing
# transient-test machinery behind ``POST /services/test-transient`` rather than
# reimplementing the per-scheme handshake logic and the egress allowlist
# (Req 14.4; ADR-0007; design §Components "Connection_Test service"):
#
#   - We assemble a ``TransientTestRequest`` (candidate service config +
#     inline credential + test params) from the request row's ``proposed_config``
#     merged with the operator-supplied edited ``config`` and the
#     operator-supplied ``credential`` secret — all in-memory, nothing persisted.
#   - We delegate to ``api.services.test_service_transient`` — the single code
#     path that already: applies the SSRF/egress allowlist (``_is_forbidden_
#     destination`` + ``_validate_test_url`` + ``_check_ssrf_hostname``), builds
#     the authenticated request per ``auth_scheme`` (REST) or dials TCP+SSH to
#     ``ssh://host:port`` (SSH via ``_test_ssh_credential``), and returns a
#     secret-free ``{ok, status_code, latency_ms, ...}`` diagnostic.
#
# Timeout (Req 6.3/6.4): the transient machinery already honours the per-call
# ``timeout_ms`` budget (httpx timeout for REST; split connect/session budget
# for SSH). We pass ``timeout_ms = 10_000`` AND wrap the whole delegation in a
# hard ``asyncio.wait_for(..., 10.0)`` ceiling so a handshake that overruns 10s
# for any reason still yields an ``ok: false`` timeout result — we NEVER raise
# on timeout (Req 6.4).
#
# Secret handling (Req 6.3, P-1, S-SEC-1): the operator secret is used only to
# build the in-memory ``TransientCredentialCandidate.value`` handed to the
# transient path; it is never persisted on the request row, and the transient
# machinery guarantees the returned diagnostic carries no secret material
# (OPS-T, ADR-0014.4). This function copies only the safe ``{ok, status_code,
# latency_ms, diagnostic}`` fields out of the transient result.
#
# Tenant scope (Req 12.3, P-3): the request row is loaded under the tenant GUC,
# so a cross-tenant / non-existent ``request_id`` is invisible and yields
# ``request_not_found``.
#
# Source: T-5.4; design §Components (Connection_Test service) / §Sequence
#         (integration test step); Req 6.3, 6.4; P-1; S-SEC-1; ADR-0007;
#         ADR-0023 (SSH base_url); openapi.yaml operationId=testAccessRequestConnection.

# The Connection_Test handshake budget — Req 6.3/6.4. A single documented value.
CONNECTION_TEST_TIMEOUT_S = 10.0


@dataclass(frozen=True)
class ConnectionTestResult:
    """Secret-free Connection_Test diagnostic — matches OpenAPI ``TestRunResponse``.

    ``ok`` is True iff the upstream handshake produced a 2xx (REST) / successful
    SSH session and no transport error. ``status_code`` / ``latency_ms`` mirror
    the transient-test result. ``diagnostic`` is a human-readable, secret-free
    message (the transient machinery's ``response_body_truncated``); ``error`` is
    the transport error category when not ``ok`` (e.g. ``timeout``). No field
    ever contains secret material (Req 6.3, P-1).
    """

    ok: bool
    latency_ms: int
    diagnostic: str
    status_code: int | None = None
    error: str | None = None


def _build_transient_value(
    auth_scheme: str, credential: Mapping[str, Any]
) -> str:
    """Assemble the inline transient-credential ``value`` for *auth_scheme*.

    The transient-test path expects a single ``value`` string:
      - SSH schemes (``_test_ssh_credential``) expect a JSON envelope carrying
        the private-key PEM + ``ssh_user`` (``ssh_private_key``/``ssh_ca``) or
        ``username`` + ``password`` (``ssh_password``).
      - REST schemes expect the raw secret string (bearer token / api key /
        ``username:password`` etc.).

    The operator ``credential`` mapping mirrors the OpenAPI
    ``RegisterCredentialRequest`` (``value`` for single-secret REST schemes;
    ``private_key_pem``/``ssh_user`` or ``username``/``password`` for SSH). The
    assembled envelope is used in-memory ONLY and never persisted (P-1).
    """
    if auth_scheme in ("ssh_private_key", "ssh_ca"):
        envelope = {
            "scheme": "ssh_private_key",
            "private_key_pem": str(credential.get("private_key_pem", "")),
            "ssh_user": str(
                credential.get("ssh_user") or credential.get("username") or ""
            ),
        }
        return json.dumps(envelope)
    if auth_scheme == "ssh_password":
        envelope = {
            "scheme": "ssh_password",
            "username": str(
                credential.get("username") or credential.get("ssh_user") or ""
            ),
            "password": str(credential.get("password", "")),
        }
        return json.dumps(envelope)
    # REST/API schemes — the raw secret string.
    raw = credential.get("value", credential.get("credential_value", ""))
    return raw if isinstance(raw, str) else str(raw)


async def connection_test(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    request_id: str,
    credential: Mapping[str, Any] | None,
    config: Mapping[str, Any] | None = None,
) -> ConnectionTestResult:
    """Run a secret-free Connection_Test for an ``integration`` proposal — Req 6.3, 6.4.

    Loads the proposal under the tenant GUC (cross-tenant / missing →
    ``request_not_found``), merges the row's ``proposed_config`` with the
    operator-supplied edited ``config`` and the operator-supplied ``credential``
    secret — all in-memory, nothing persisted — and delegates the actual
    per-scheme handshake to the existing transient-test machinery behind
    ``POST /services/test-transient`` (REST schemes hit a health/base path; SSH
    schemes open TCP+SSH to ``ssh://host:port``), with the egress allowlist
    applied there (ADR-0007) and a hard 10s timeout (Req 6.3/6.4).

    Returns ``{ok, status_code, latency_ms, diagnostic}`` with NO secret
    material (Req 6.3, P-1). A handshake that exceeds the 10s budget yields an
    ``ok: false`` result whose diagnostic notes the timeout — it never raises
    (Req 6.4).

    Errors: ``request_not_found`` (missing / cross-tenant / non-integration
    kind, Req 12.3), ``missing_secret_material`` (blank secret, mirrors
    finalize's Req 6.6 precondition).
    """
    # Imported lazily so the pure-helper import surface (used by callers that
    # only need validation helpers / the create path) stays free of the heavier
    # api.services module and its httpx/asyncssh dependencies.
    import asyncio  # noqa: PLC0415

    from admin_api.api.services import (  # noqa: PLC0415
        TransientCredentialCandidate,
        TransientServiceCandidate,
        TransientTestParams,
        TransientTestRequest,
        test_service_transient,
    )

    try:
        db_uuid = wire_to_db_uuid(request_id, "request")
    except ValueError:
        # A malformed request_ id can never name a visible row — Req 12.3.
        raise AccessRequestError("request_not_found", "request not found")

    await set_tenant_context(session, tenant_id)

    row = (
        await session.execute(
            text(
                "SELECT id, kind, proposed_config FROM access_requests"
                " WHERE id = :id AND tenant_id = :tid"
            ),
            {"id": str(db_uuid), "tid": str(tenant_id)},
        )
    ).mappings().fetchone()

    if row is None or row["kind"] != "integration":
        # Non-integration kinds carry no proposed config to test; treat a
        # missing / wrong-kind row as not-found without revealing which.
        raise AccessRequestError("request_not_found", "request not found")

    proposed = row["proposed_config"]
    merged_config: dict[str, Any] = dict(proposed) if proposed is not None else {}
    # Req 6.2 semantics reused here — operator edits override proposed values
    # for the purpose of the test (nothing is persisted).
    if config:
        merged_config.update(dict(config))

    base_url = str(merged_config.get("base_url") or "").strip()
    auth_scheme = str(merged_config.get("auth_scheme") or "").strip()

    # A blank secret cannot produce a meaningful handshake — mirror finalize's
    # missing_secret_material precondition (Req 6.6) rather than dialling with
    # an empty credential.
    cred_map: Mapping[str, Any] = credential or {}
    transient_value = _build_transient_value(auth_scheme, cred_map)
    if not transient_value.strip() or transient_value in ("{}", '{"scheme": ""}'):
        raise AccessRequestError(
            "missing_secret_material",
            "the integration's required secret material is blank",
        )

    # Assemble the in-memory transient request. The credential value is used
    # ONLY to build this candidate and is handed to the transient path; it is
    # never persisted, logged, audited, or spanned (P-1, S-SEC-1).
    transient_body = TransientTestRequest(
        service=TransientServiceCandidate(
            name=str(merged_config.get("name") or "candidate"),
            base_url=base_url,
            auth_scheme=auth_scheme,
        ),
        credential=TransientCredentialCandidate(
            value=transient_value,
            header_name=merged_config.get("header_name"),
            query_param=merged_config.get("query_param"),
        ),
        test=TransientTestParams(timeout_ms=int(CONNECTION_TEST_TIMEOUT_S * 1000)),
    )

    # Delegate to the existing transient-test handler (reuse: per-scheme
    # handshake + egress allowlist). Wrap in a hard 10s ceiling so any overrun
    # becomes an ok:false timeout result rather than a raised error (Req 6.4).
    try:
        response = await asyncio.wait_for(
            test_service_transient(
                tenant_id=tenant_id,
                body=transient_body,
                session=session,
                _authz=None,
            ),
            timeout=CONNECTION_TEST_TIMEOUT_S,
        )
    except (asyncio.TimeoutError, TimeoutError):
        # Req 6.4 — a timeout is a fail RESULT, not an exception. Diagnostic
        # carries no secret material.
        return ConnectionTestResult(
            ok=False,
            latency_ms=int(CONNECTION_TEST_TIMEOUT_S * 1000),
            diagnostic=(
                "Connection test timed out after "
                f"{int(CONNECTION_TEST_TIMEOUT_S)}s"
            ),
            error="timeout",
        )

    # The transient handler returns a JSONResponse whose body is the secret-free
    # result dict. Decode it and copy ONLY the safe fields into our result shape
    # — never echo the request credential or any additional payload (P-1).
    payload: dict[str, Any] = json.loads(bytes(response.body))

    ok = bool(payload.get("ok", False))
    status_code = payload.get("status_code")
    latency_ms = int(payload.get("latency_ms", 0))
    diagnostic = str(payload.get("response_body_truncated", "") or "")
    error = payload.get("error")

    # The transient path reports REST timeouts as error="timeout" with ok=False
    # (never raising); surface a diagnostic for that case too (Req 6.4).
    if error == "timeout" and not diagnostic:
        diagnostic = (
            f"Connection test timed out after {int(CONNECTION_TEST_TIMEOUT_S)}s"
        )

    return ConnectionTestResult(
        ok=ok,
        latency_ms=latency_ms,
        diagnostic=diagnostic,
        status_code=int(status_code) if isinstance(status_code, int) else None,
        error=str(error) if error is not None else None,
    )
