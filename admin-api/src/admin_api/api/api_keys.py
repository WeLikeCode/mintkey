"""
Service API key CRUD endpoints — long-lived-api-keys feature.

POST   /v1/tenants/{tid}/agents/{aid}/api-keys              — create (201)
GET    /v1/tenants/{tid}/agents/{aid}/api-keys              — list   (200)
GET    /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}        — get    (200)
POST   /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/revoke — revoke (200)
POST   /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/rotate — rotate (201)

Architecture constraints:
  - Plaintext returned once at creation; never stored unencrypted (ADR-0018 §1.3).
  - key_hash = argon2id(plaintext); key_fingerprint = hex(sha256(plaintext)[:8]).
  - allowed_actions must be a subset of the agent's permission grants (Req 1.3).
  - Operator policy enforcement from AdminSettings.api_key (Req 10.4).
  - audit_emit on every state change — ADR-0014.7.
  - NOTIFY mintkey:agent on revoke (api_key.revoked) — ADR-0014.1.
  - RLS via set_tenant_context — ADR-0008.
  - Bound parameters only — ADR-0008, T-1.0.15.
  - ULID IDs with svckey_ prefix — ADR-0017.11.

Source: long-lived-api-keys tasks 7.1–7.5; ADR-0018; ADR-0008; ADR-0014.7; ADR-0017.11.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

import argon2
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.api.agents import _wire_id_to_uuid as _decode_agent_wire_id
from admin_api.changes.publisher import notify_change
from admin_api.db.deps import get_db_session
from admin_api.utils.wire_ids import db_uuid_to_wire
from mintkey_models.audit import audit_emit
from mintkey_models.tenant_ctx import set_tenant_context

router = APIRouter(prefix="/v1/tenants/{tenant_id}/agents/{agent_id}/api-keys")

_ph = argon2.PasswordHasher(
    time_cost=1,
    memory_cost=65536,
    parallelism=4,
    hash_len=32,
)

# Crockford base32 alphabet (uppercase, no I/L/O/U) — ADR-0017.11
_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


# ---------------------------------------------------------------------------
# ID generation — ADR-0017.11
# ---------------------------------------------------------------------------


def _new_svckey_id() -> str:
    """Generate a ULID-format ID with the 'svckey_' prefix — ADR-0017.11."""
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

    return "svckey_" + "".join(t_enc) + "".join(r_enc)


# ---------------------------------------------------------------------------
# Key generation (ADR-0018 §1)
# ---------------------------------------------------------------------------


def _generate_plaintext() -> str:
    """Generate mk_svckey_<crockford32(32 random bytes)>."""
    rand_bytes = secrets.token_bytes(32)
    rand_int = int.from_bytes(rand_bytes, "big")
    chars: list[str] = []
    for _ in range(52):  # ceil(256/5) = 52 chars
        chars.append(_CROCKFORD[rand_int & 0x1F])
        rand_int >>= 5
    chars.reverse()
    return "mk_svckey_" + "".join(chars)


def _fingerprint(plaintext: str) -> str:
    """hex(sha256(plaintext)[:8]) — ADR-0018 §1."""
    return hashlib.sha256(plaintext.encode()).digest()[:8].hex()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------


class ServiceApiKeyCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    service_id: str
    allowed_actions: list[str]
    constraints: Optional[dict] = None
    expires_at: Optional[datetime] = None


class RevokeRequest(BaseModel):
    reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Settings helper
# ---------------------------------------------------------------------------


async def _load_api_key_settings(session: AsyncSession) -> dict:
    """Load AdminSettings.api_key block; return defaults if not configured."""
    defaults = {
        "proxy_cache_ttl_seconds": 60,
        "require_expiry": False,
        "allow_no_expiry": True,
        "max_expiry_days": 365,
        "require_ip_allowlist": False,
    }
    # Use a savepoint so a missing admin_settings table doesn't abort the
    # outer transaction — asyncpg propagates the Postgres error to the
    # connection level otherwise.
    try:
        async with session.begin_nested():
            row = await session.execute(text("SELECT value FROM admin_settings LIMIT 1"))
            r = row.fetchone()
            if r:
                data = json.loads(r.value)
                return data.get("api_key", defaults)
    except Exception:
        pass
    return defaults


# ---------------------------------------------------------------------------
# Policy enforcement (Req 10.4)
# ---------------------------------------------------------------------------


def _check_policy(settings: dict, body: ServiceApiKeyCreate) -> str | None:
    """Return mintkey:code if a policy is violated, else None."""
    require_expiry = settings.get("require_expiry", False)
    allow_no_expiry = settings.get("allow_no_expiry", True)
    max_expiry_days = settings.get("max_expiry_days", 365)
    require_ip_allowlist = settings.get("require_ip_allowlist", False)

    if require_expiry and not allow_no_expiry and body.expires_at is None:
        return "api_key_policy_violation"

    if body.expires_at is not None:
        now = datetime.now(timezone.utc)
        expires = body.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if (expires - now).days > max_expiry_days:
            return "api_key_policy_violation"

    if require_ip_allowlist:
        constraints = body.constraints or {}
        if not constraints.get("source_ip_allowlist"):
            return "api_key_policy_violation"

    return None


# ---------------------------------------------------------------------------
# Wire-form key ID resolver — ADR-0017.11; R11a
# ---------------------------------------------------------------------------


async def _resolve_api_key_id(api_key_id: str, session: AsyncSession, tenant_id) -> str | None:
    """
    Resolve a svckey_ wire-form ID to the DB UUID stored in service_api_keys.

    create_api_key returns a Crockford ULID wire ID (svckey_<26>), but the DB
    stores an independent uuid4().  Look up via audit_events payload where
    new_api_key_id or api_key_id matches — returning the target_id (DB UUID).

    Returns None if not resolvable (caller should return 404).
    Returns the input as-is if it's already a plain UUID.

    Source: R11a; ADR-0017.11.
    """
    if not api_key_id.startswith("svckey_"):
        return api_key_id  # Already a plain UUID or other form

    row = await session.execute(
        text(
            "SELECT target_id FROM audit_events"
            " WHERE event_type IN ('api_key.created', 'api_key.rotated')"
            "   AND tenant_id = :tid"
            "   AND (payload->>'api_key_id' = :kid OR payload->>'new_api_key_id' = :kid)"
            " LIMIT 1"
        ),
        {"tid": str(tenant_id), "kid": api_key_id},
    )
    found = row.fetchone()
    if found is None:
        return None
    return str(found.target_id)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post("", status_code=201)
async def create_api_key(
    tenant_id: UUID,
    agent_id: str,
    body: ServiceApiKeyCreate,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Create a service API key for an agent.

    - Validates allowed_actions ⊆ grants (Req 1.3).
    - Enforces operator policies (Req 10.4).
    - Returns plaintext once in 201 body; never stored unencrypted (ADR-0018 §1.3).
    - Emits api_key.created audit event (ADR-0014.7).

    Source: long-lived-api-keys task 7.1; ADR-0018; ADR-0008; ADR-0014.7; ADR-0017.11.
    """
    # 0. Decode wire-prefixed agent_id → UUID — ADR-0017.11; R9
    try:
        agent_uuid = _decode_agent_wire_id(agent_id, "agent_")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
        )

    await set_tenant_context(session, tenant_id)

    # 1. Verify agent exists in this tenant
    agent_result = await session.execute(
        text("SELECT id FROM agents WHERE id = :aid AND tenant_id = :tid"),
        {"aid": agent_uuid, "tid": str(tenant_id)},
    )
    if agent_result.fetchone() is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "Agent not found"},
        )

    # 2. Resolve svc_ wire-form to DB UUID — R12; ADR-0017.11
    #    Same pattern as grant_permission's _resolve_service_uuid helper:
    #    Primary path decodes Crockford ULID via _decode_agent_wire_id (works for post-R12
    #    services where internal_id is derived from the same ULID bits).
    #    Fallback path checks audit_events for pre-R12 services whose uuid4() was independent.
    svc_input = body.service_id
    if svc_input.startswith("svc_"):
        try:
            decoded_svc_uuid = _decode_agent_wire_id(svc_input, "svc_")
        except ValueError:
            return JSONResponse(
                status_code=422,
                content={"mintkey:code": "invalid_service_id", "title": "Invalid service_id"},
            )
        # Primary path: verify decoded UUID exists (post-R12 services resolve here directly)
        exists_result = await session.execute(
            text("SELECT 1 FROM services WHERE id = :sid AND tenant_id = :tid"),
            {"sid": decoded_svc_uuid, "tid": str(tenant_id)},
        )
        if exists_result.fetchone() is not None:
            svc_uuid = decoded_svc_uuid
        else:
            # Fallback: pre-R12 service — look up via audit_events wire-form
            svc_lookup = await session.execute(
                text(
                    "SELECT target_id FROM audit_events"
                    " WHERE event_type = 'service.registered'"
                    "   AND tenant_id = :tid"
                    "   AND payload->>'svc_id' = :svc_wire"
                    " LIMIT 1"
                ),
                {"tid": str(tenant_id), "svc_wire": svc_input},
            )
            svc_row = svc_lookup.fetchone()
            if svc_row is None:
                return JSONResponse(
                    status_code=404,
                    content={"mintkey:code": "not_found", "title": "Service not found"},
                )
            svc_uuid = str(svc_row.target_id)
    else:
        svc_uuid = svc_input

    # 3a. Load agent's grants for the requested service_id
    grants_result = await session.execute(
        text(
            "SELECT action FROM permission_grants"
            " WHERE agent_id = :aid AND service_id = :sid AND tenant_id = :tid"
        ),
        {"aid": agent_uuid, "sid": svc_uuid, "tid": str(tenant_id)},
    )
    grant_actions = {row.action for row in grants_result.fetchall()}

    # 3b. allowed_actions must be a subset of grants (Req 1.3)
    requested = set(body.allowed_actions)
    if not requested.issubset(grant_actions):
        return JSONResponse(
            status_code=422,
            content={
                "mintkey:code": "api_key_actions_exceed_grant",
                "title": "allowed_actions exceed the agent's permission grants for this service",
            },
        )

    # 4. Load operator policy and enforce (Req 10.4)
    settings = await _load_api_key_settings(session)
    policy_violation = _check_policy(settings, body)
    if policy_violation:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": policy_violation, "title": "Operator policy violation"},
        )

    # 5. Generate key material (ADR-0018 §1)
    plaintext = _generate_plaintext()
    fp = _fingerprint(plaintext)
    key_hash = _ph.hash(plaintext)
    key_id = _new_svckey_id()
    # Derive internal DB UUID from ULID bits — same pattern as agents/services (#13).
    # This ensures list/get can emit the Crockford wire ID by re-encoding the stored UUID.
    _svckey_tail = key_id[len("svckey_"):]
    _svckey_val = 0
    for _ch in _svckey_tail.upper():
        _svckey_val = (_svckey_val << 5) | _CROCKFORD.index(_ch)
    _svckey_val &= (1 << 128) - 1
    internal_id = uuid.UUID(int=_svckey_val)
    now = datetime.now(timezone.utc)

    # 6. INSERT (bound params only — ADR-0008 / T-1.0.15)
    await session.execute(
        text(
            "INSERT INTO service_api_keys"
            " (id, tenant_id, agent_id, service_id, key_hash, key_fingerprint,"
            "  allowed_actions, constraints, expires_at, created_at, created_by)"
            " VALUES"
            " (:id, :tid, :aid, :sid, :key_hash, :fp,"
            "  CAST(:actions AS text[]), CAST(:constraints AS jsonb), :expires_at, :now, :created_by)"
        ),
        {
            "id": str(internal_id),
            "tid": str(tenant_id),
            "aid": agent_uuid,
            "sid": svc_uuid,
            "key_hash": key_hash,
            "fp": fp,
            "actions": body.allowed_actions,
            "constraints": json.dumps(body.constraints) if body.constraints else None,
            "expires_at": body.expires_at,
            "now": now,
            "created_by": agent_uuid,
        },
    )

    # 7. Emit audit — no plaintext in payload (ADR-0018 §1.3; Req 10.1)
    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="api_key.created",
        actor_id=None,
        actor_type="operator",
        target_id=internal_id,
        target_type="api_key",
        payload={
            "api_key_id": key_id,
            "agent_id": agent_uuid,
            "service_id": body.service_id,
            "key_fingerprint": fp,
            "allowed_actions": body.allowed_actions,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "api_key_id": key_id,
            "plaintext_key": plaintext,
            "key_fingerprint": fp,
            "agent_id": agent_id,
            "service_id": body.service_id,
            "allowed_actions": body.allowed_actions,
            "constraints": body.constraints,
            "expires_at": body.expires_at.isoformat() if body.expires_at else None,
            "created_at": now.isoformat(),
        },
    )


def _escape_like(value: str) -> str:
    """Escape LIKE metacharacters so user input cannot glob-match unexpectedly."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@router.get("")
async def list_api_keys(
    tenant_id: UUID,
    agent_id: str,
    q: Optional[str] = None,
    service_id: Optional[str] = None,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    List API keys for an agent. Never returns plaintext or key_hash.

    Optional query parameters:
      q          — prefix/substring filter on key_fingerprint (case-insensitive).
      service_id — filter to keys for a specific service (UUID or svc_ wire-ID).

    Source: long-lived-api-keys task 7.2; Req 8.2; ADR-0008.
    """
    # Decode wire-prefixed agent_id → UUID — ADR-0017.11; R11a
    try:
        agent_uuid = _decode_agent_wire_id(agent_id, "agent_")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
        )

    await set_tenant_context(session, tenant_id)

    # Defense-in-depth: pass only full string literals to text() so the
    # SQL is statically verifiable with no dynamic concatenation.
    # Option B: explicit branches — each text() call has a constant argument.
    _BASE = (
        "SELECT id, key_fingerprint, service_id, allowed_actions, constraints,"
        "       expires_at, last_used_at, created_at, created_by, revoked_at"
        " FROM service_api_keys"
        " WHERE agent_id = :aid AND tenant_id = :tid"
    )
    _ORDER = " ORDER BY created_at DESC"

    q_pattern: str | None = None
    if q is not None:
        q_pattern = f"%{_escape_like(q)}%"

    svc_uuid: str | None = None
    if service_id is not None:
        # Accept svc_ wire-ID (Crockford or legacy 32-hex) or plain UUID
        from admin_api.utils.wire_ids import wire_to_db_uuid as _decode_wire  # noqa: PLC0415
        svc_uuid = _decode_wire(service_id, "svc")

    if q_pattern is not None and svc_uuid is not None:
        rows_result = await session.execute(
            text(
                "SELECT id, key_fingerprint, service_id, allowed_actions, constraints,"
                "       expires_at, last_used_at, created_at, created_by, revoked_at"
                " FROM service_api_keys"
                " WHERE agent_id = :aid AND tenant_id = :tid"
                " AND key_fingerprint ILIKE :pat ESCAPE '\\'"
                " AND service_id = :svc_id"
                " ORDER BY created_at DESC"
            ),
            {"aid": agent_uuid, "tid": str(tenant_id), "pat": q_pattern, "svc_id": svc_uuid},
        )
    elif q_pattern is not None:
        rows_result = await session.execute(
            text(
                "SELECT id, key_fingerprint, service_id, allowed_actions, constraints,"
                "       expires_at, last_used_at, created_at, created_by, revoked_at"
                " FROM service_api_keys"
                " WHERE agent_id = :aid AND tenant_id = :tid"
                " AND key_fingerprint ILIKE :pat ESCAPE '\\'"
                " ORDER BY created_at DESC"
            ),
            {"aid": agent_uuid, "tid": str(tenant_id), "pat": q_pattern},
        )
    elif svc_uuid is not None:
        rows_result = await session.execute(
            text(
                "SELECT id, key_fingerprint, service_id, allowed_actions, constraints,"
                "       expires_at, last_used_at, created_at, created_by, revoked_at"
                " FROM service_api_keys"
                " WHERE agent_id = :aid AND tenant_id = :tid"
                " AND service_id = :svc_id"
                " ORDER BY created_at DESC"
            ),
            {"aid": agent_uuid, "tid": str(tenant_id), "svc_id": svc_uuid},
        )
    else:
        rows_result = await session.execute(
            text(
                "SELECT id, key_fingerprint, service_id, allowed_actions, constraints,"
                "       expires_at, last_used_at, created_at, created_by, revoked_at"
                " FROM service_api_keys"
                " WHERE agent_id = :aid AND tenant_id = :tid"
                " ORDER BY created_at DESC"
            ),
            {"aid": agent_uuid, "tid": str(tenant_id)},
        )
    rows = rows_result.fetchall()

    items = []
    for r in rows:
        status = "revoked" if r.revoked_at else "active"
        if not r.revoked_at and r.expires_at:
            expires = r.expires_at
            if hasattr(expires, "isoformat"):
                if expires < datetime.now(timezone.utc):
                    status = "expired"
        items.append({
            "api_key_id": db_uuid_to_wire(r.id, "svckey"),
            "key_fingerprint": r.key_fingerprint,
            "service_id": db_uuid_to_wire(r.service_id, "svc") if r.service_id else None,
            "allowed_actions": r.allowed_actions,
            "constraints": json.loads(r.constraints) if r.constraints else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "last_used_at": r.last_used_at.isoformat() if r.last_used_at else None,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "created_by": str(r.created_by) if r.created_by else None,
            "status": status,
        })

    return JSONResponse(status_code=200, content=items)


@router.get("/{api_key_id}")
async def get_api_key(
    tenant_id: UUID,
    agent_id: str,
    api_key_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Get a single API key. Never returns plaintext or key_hash.

    Source: long-lived-api-keys task 7.2; Req 8.3; ADR-0008.
    """
    # Decode wire-prefixed agent_id → UUID — ADR-0017.11; R11a
    try:
        agent_uuid = _decode_agent_wire_id(agent_id, "agent_")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
        )

    await set_tenant_context(session, tenant_id)

    row_result = await session.execute(
        text(
            "SELECT id, key_fingerprint, service_id, allowed_actions, constraints,"
            "       expires_at, last_used_at, created_at, created_by, revoked_at"
            " FROM service_api_keys"
            " WHERE agent_id = :aid AND tenant_id = :tid AND id = :kid"
            " LIMIT 1"
        ),
        {"aid": agent_uuid, "tid": str(tenant_id), "kid": api_key_id},
    )
    row = row_result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "API key not found"},
        )

    status = "revoked" if row.revoked_at else "active"
    return JSONResponse(
        status_code=200,
        content={
            "api_key_id": db_uuid_to_wire(row.id, "svckey"),
            "key_fingerprint": row.key_fingerprint,
            "service_id": db_uuid_to_wire(row.service_id, "svc") if row.service_id else None,
            "allowed_actions": row.allowed_actions,
            "constraints": json.loads(row.constraints) if row.constraints else None,
            "expires_at": row.expires_at.isoformat() if row.expires_at else None,
            "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "created_by": str(row.created_by) if row.created_by else None,
            "status": status,
        },
    )


@router.post("/{api_key_id}/revoke")
async def revoke_api_key(
    tenant_id: UUID,
    agent_id: str,
    api_key_id: str,
    body: RevokeRequest,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Revoke an API key.

    Idempotent: already-revoked → 200. Absent → 404.
    Emits api_key.revoked audit + NOTIFY mintkey:agent (ADR-0014.1; Req 4.1; 4.5).

    Source: long-lived-api-keys task 7.3; ADR-0014.7; ADR-0014.1; ADR-0008.
    """
    # Decode wire-prefixed agent_id → UUID — ADR-0017.11; R11a
    try:
        agent_uuid = _decode_agent_wire_id(agent_id, "agent_")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
        )

    await set_tenant_context(session, tenant_id)

    row_result = await session.execute(
        text(
            "SELECT id, key_fingerprint, service_id, revoked_at"
            " FROM service_api_keys"
            " WHERE agent_id = :aid AND tenant_id = :tid AND id = :kid"
            " LIMIT 1"
        ),
        {"aid": agent_uuid, "tid": str(tenant_id), "kid": api_key_id},
    )
    row = row_result.fetchone()
    if row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "API key not found"},
        )

    if row.revoked_at is not None:
        return JSONResponse(status_code=200, content={"status": "already_revoked"})

    now = datetime.now(timezone.utc)
    await session.execute(
        text(
            "UPDATE service_api_keys"
            " SET revoked_at = :now, revoked_by = :by, revoke_reason = :reason"
            " WHERE id = :kid AND tenant_id = :tid"
        ),
        {
            "now": now,
            "by": None,
            "reason": body.reason,
            "kid": api_key_id,
            "tid": str(tenant_id),
        },
    )

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="api_key.revoked",
        actor_id=None,
        actor_type="operator",
        target_id=None,
        target_type="api_key",
        payload={
            "api_key_id": api_key_id,
            "agent_id": agent_id,
            "service_id": str(row.service_id) if row.service_id is not None else None,
            "key_fingerprint": row.key_fingerprint,
            "reason": body.reason,
        },
    )

    # NOTIFY for proxy cache eviction — ADR-0014.1; change-event schema
    await notify_change(
        session,
        "mintkey:agent",
        {
            "event": "api_key.revoked",
            "tenant_id": str(tenant_id),
            "api_key_id": api_key_id,
            "key_fingerprint": row.key_fingerprint,
            "reason": body.reason,
        },
    )

    return JSONResponse(status_code=200, content={"status": "revoked"})


@router.post("/{api_key_id}/rotate", status_code=201)
async def rotate_api_key(
    tenant_id: UUID,
    agent_id: str,
    api_key_id: str,
    session: AsyncSession = Depends(get_db_session),
) -> JSONResponse:
    """
    Rotate an API key — creates a new key with the same binding; old key is NOT revoked.

    Returns 201 with new plaintext (shown once). Emits api_key.rotated audit.
    The old key continues working until the operator explicitly revokes it (Req 5.2).

    Source: long-lived-api-keys task 7.4; Req 5.1; 5.2; ADR-0018; ADR-0014.7; ADR-0017.11.
    """
    # Decode wire-prefixed agent_id → UUID — ADR-0017.11; R11a
    try:
        agent_uuid = _decode_agent_wire_id(agent_id, "agent_")
    except ValueError:
        return JSONResponse(
            status_code=422,
            content={"mintkey:code": "invalid_id", "title": "Invalid agent_id"},
        )

    await set_tenant_context(session, tenant_id)

    row_result = await session.execute(
        text(
            "SELECT id, agent_id, service_id, allowed_actions, constraints,"
            "       expires_at, created_at"
            " FROM service_api_keys"
            " WHERE agent_id = :aid AND tenant_id = :tid AND id = :kid"
            " LIMIT 1"
        ),
        {"aid": agent_uuid, "tid": str(tenant_id), "kid": api_key_id},
    )
    old_row = row_result.fetchone()
    if old_row is None:
        return JSONResponse(
            status_code=404,
            content={"mintkey:code": "not_found", "title": "API key not found"},
        )

    # Recompute expiry: preserve relative duration (Req 5.1)
    new_expires_at = None
    if old_row.expires_at:
        duration = old_row.expires_at - old_row.created_at
        new_expires_at = datetime.now(timezone.utc) + duration

    plaintext = _generate_plaintext()
    fp = _fingerprint(plaintext)
    key_hash = _ph.hash(plaintext)
    new_key_id = _new_svckey_id()
    # Derive internal DB UUID from ULID bits — same pattern as agents/services (#13).
    _rot_tail = new_key_id[len("svckey_"):]
    _rot_val = 0
    for _ch in _rot_tail.upper():
        _rot_val = (_rot_val << 5) | _CROCKFORD.index(_ch)
    _rot_val &= (1 << 128) - 1
    new_internal_id = uuid.UUID(int=_rot_val)
    now = datetime.now(timezone.utc)

    await session.execute(
        text(
            "INSERT INTO service_api_keys"
            " (id, tenant_id, agent_id, service_id, key_hash, key_fingerprint,"
            "  allowed_actions, constraints, expires_at, created_at, created_by)"
            " VALUES"
            " (:id, :tid, :aid, :sid, :key_hash, :fp,"
            "  CAST(:actions AS text[]), CAST(:constraints AS jsonb), :expires_at, :now, :created_by)"
        ),
        {
            "id": str(new_internal_id),
            "tid": str(tenant_id),
            "aid": agent_uuid,
            "sid": old_row.service_id,
            "key_hash": key_hash,
            "fp": fp,
            "actions": old_row.allowed_actions,
            "constraints": old_row.constraints,
            "expires_at": new_expires_at,
            "now": now,
            "created_by": agent_uuid,
        },
    )

    await audit_emit(
        session=session,
        tenant_id=tenant_id,
        event_type="api_key.rotated",
        actor_id=None,
        actor_type="operator",
        target_id=new_internal_id,
        target_type="api_key",
        payload={
            "old_api_key_id": api_key_id,
            "new_api_key_id": new_key_id,
            "agent_id": agent_id,
            "service_id": str(old_row.service_id) if old_row.service_id else None,
            "key_fingerprint": fp,
        },
    )

    return JSONResponse(
        status_code=201,
        content={
            "api_key_id": new_key_id,
            "plaintext_key": plaintext,
            "key_fingerprint": fp,
            "agent_id": agent_id,
            "service_id": str(old_row.service_id) if old_row.service_id else None,
            "allowed_actions": old_row.allowed_actions,
            "expires_at": new_expires_at.isoformat() if new_expires_at else None,
            "created_at": now.isoformat(),
        },
    )
