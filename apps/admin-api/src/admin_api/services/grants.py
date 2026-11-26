"""The one write path that creates and removes permission grants.

Every caller that grants or revokes access goes through this module: the
operator API now, the agent grant tools and access-request approvals later.
The SQL lives here; the caller keeps the audit event and the change-channel
NOTIFY.

Sources:
  - ``openspec/changes/grant-expiry/spec.md`` — One write path creates and
    removes grants
  - ``openspec/changes/grant-expiry/design.md`` — D6, D7, D7b, D8
"""

from __future__ import annotations

import json
import time
import uuid
from calendar import monthrange
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Final
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.services.grant_expiry import (
    GRANTOR_AGENT,
    GRANTOR_OPERATOR,
    check_grant_expiry,
    is_expired,
)
from admin_api.utils.wire_ids import db_uuid_to_wire, wire_to_db_uuid

# Crockford base32 alphabet (uppercase, no I/L/O/U) — ADR-0017.11
_CROCKFORD: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


@dataclass(frozen=True)
class Grantor:
    """Who gave a grant: an operator or an agent, by DB uuid text."""

    type: str
    id: str | None


@dataclass(frozen=True)
class GrantRecord:
    """A permission grant as the service sees it (ids as DB uuid text)."""

    id: str
    wire_id: str
    agent_id: str
    service_id: str
    action: str
    constraints: dict[str, Any]
    expires_at: datetime | None
    grantor_type: str
    grantor_id: str | None
    created_at: datetime | None
    created: bool


class GrantConflict(Exception):
    """A live grant has different constraints or another expiry."""


# ---------------------------------------------------------------------------
# ID generation — ADR-0017.11
# ---------------------------------------------------------------------------


def _new_perm_id() -> str:
    """Generate a ULID-format ID with the 'perm_' prefix — ADR-0017.11."""
    ts_ms = int(time.time() * 1000)
    rand = int.from_bytes(uuid.uuid4().bytes[:10], "big")

    t_enc = []
    v = ts_ms
    for _ in range(10):
        t_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    t_enc.reverse()

    r_enc = []
    v = rand
    for _ in range(16):
        r_enc.append(_CROCKFORD[v & 0x1F])
        v >>= 5
    r_enc.reverse()

    return "perm_" + "".join(t_enc) + "".join(r_enc)


def _perm_id_to_uuid(perm_id: str) -> uuid.UUID:
    """Derive the internal DB UUID from a ``perm_`` ULID's bits — ADR-0017.11."""
    tail = perm_id[len("perm_"):] if perm_id.startswith("perm_") else perm_id
    value = 0
    for char in tail.upper():
        value = (value << 5) | _CROCKFORD.index(char)
    value &= (1 << 128) - 1
    return uuid.UUID(int=value)


# ---------------------------------------------------------------------------
# Budget period boundary helper — design §3; T-BUD-2.2
# ---------------------------------------------------------------------------


def _budget_period_bounds(
    period: str, now: datetime
) -> tuple[datetime, datetime]:
    """
    Compute UTC-aligned (start, end) for the given period containing `now`.

    | Period   | Start                   | End                          |
    |----------|-------------------------|------------------------------|
    | hourly   | Top of the hour         | +1 hour                      |
    | daily    | 00:00:00Z               | +24 hours                    |
    | weekly   | Monday 00:00:00Z        | +7 days                      |
    | monthly  | 1st of month 00:00:00Z  | 1st of next month 00:00:00Z  |

    Source: design §3; T-BUD-2.5.
    """
    if period == "hourly":
        start = now.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
    elif period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
    elif period == "weekly":
        # Monday 00:00:00Z of the current week
        days_since_monday = now.weekday()  # Monday=0
        start = (now - timedelta(days=days_since_monday)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        end = start + timedelta(days=7)
    elif period == "monthly":
        start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        _, days_in_month = monthrange(now.year, now.month)
        end = start + timedelta(days=days_in_month)
    else:
        raise ValueError(f"Unknown budget period: {period}")

    return start, end


# ---------------------------------------------------------------------------
# Row coercion — a stored value of the wrong type reads as its default
# ---------------------------------------------------------------------------


def _as_datetime(value: Any) -> datetime | None:
    """Return ``value`` when it is a datetime, otherwise None."""
    return value if isinstance(value, datetime) else None


def _as_text(value: Any) -> str | None:
    """Return a DB uuid (or any text) as text, otherwise None."""
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, str):
        return value
    return None


def _grantor_type(value: Any) -> str:
    """A missing or non-text grantor type reads as ``operator``."""
    if isinstance(value, str) and value:
        return value
    return GRANTOR_OPERATOR


def _parse_constraints(value: Any) -> Any:
    """Decode a JSONB text payload; leave dicts, None and junk as they are."""
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
    return value


def _constraints_dict(value: Any) -> dict[str, Any]:
    parsed = _parse_constraints(value)
    if isinstance(parsed, dict):
        return parsed
    return {}


def _wire(value: Any, prefix: str) -> str | None:
    """Encode a DB uuid as a wire id; pass any other text through unchanged."""
    text_value = _as_text(value)
    if text_value is None:
        return None
    try:
        return db_uuid_to_wire(text_value, prefix)
    except (TypeError, ValueError):
        return text_value


def _grantor_wire_id(grantor_type: str, grantor_id: Any) -> str | None:
    """An agent grantor is a wire id; an operator grantor keeps its UUID text."""
    text_value = _as_text(grantor_id)
    if text_value is None:
        return None
    if grantor_type == GRANTOR_AGENT:
        return _wire(text_value, "agent")
    return text_value


def _record_from_row(row: Any, *, created: bool) -> GrantRecord:
    """Build a :class:`GrantRecord` from a stored row, defaults for bad types."""
    row_id = str(row.id)
    grantor_type = _grantor_type(getattr(row, "grantor_type", None))
    return GrantRecord(
        id=row_id,
        wire_id=_wire(row_id, "perm") or row_id,
        agent_id=str(row.agent_id),
        service_id=str(row.service_id),
        action=str(row.action),
        constraints=_constraints_dict(getattr(row, "constraints", None)),
        expires_at=_as_datetime(getattr(row, "expires_at", None)),
        grantor_type=grantor_type,
        grantor_id=_as_text(getattr(row, "grantor_id", None)),
        created_at=_as_datetime(getattr(row, "created_at", None)),
        created=created,
    )


# ---------------------------------------------------------------------------
# The write path
# ---------------------------------------------------------------------------


async def write_grant(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    agent_id: str,
    service_id: str,
    action: str,
    constraints: dict[str, Any],
    expires_at: datetime | None,
    grantor: Grantor,
    now: datetime | None = None,
) -> GrantRecord:
    """Create a grant, or return the identical live one.

    The expiry rules run before any statement. A transaction-level advisory
    lock serialises concurrent writers of one (agent, service, action); then
    the longest-lasting row decides: an identical live row is returned with
    ``created`` false, a live row with another constraint or expiry raises
    :class:`GrantConflict`, and an expired row is deleted and replaced.
    """
    current = now if now is not None else datetime.now(timezone.utc)
    check_grant_expiry(expires_at, grantor.type, current)

    tenant_text = str(tenant_id)
    lock_key = f"grant:{tenant_text}:{agent_id}:{service_id}:{action}"
    await session.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": lock_key},
    )

    existing_result = await session.execute(
        text(
            "SELECT id, agent_id, service_id, action, constraints, expires_at,"
            " grantor_type, grantor_id, created_at"
            " FROM permission_grants"
            " WHERE tenant_id = :tid AND agent_id = :aid"
            "   AND service_id = :sid AND action = :action"
            " ORDER BY (expires_at IS NULL) DESC, expires_at DESC,"
            "          created_at DESC, id"
            " LIMIT 1"
        ),
        {
            "tid": tenant_text,
            "aid": agent_id,
            "sid": service_id,
            "action": action,
        },
    )
    existing = existing_result.fetchone()

    if existing is not None:
        existing_expiry = _as_datetime(getattr(existing, "expires_at", None))
        if not is_expired(existing_expiry, current):
            identical = (
                _parse_constraints(getattr(existing, "constraints", None))
                == constraints
                and existing_expiry == expires_at
            )
            if identical:
                return _record_from_row(existing, created=False)
            raise GrantConflict(
                "a live permission grant for this agent, service and action"
                " has different constraints or another expiry"
            )
        await session.execute(
            text(
                "DELETE FROM permission_grants"
                " WHERE id = :pid AND tenant_id = :tid"
            ),
            {"pid": _as_text(getattr(existing, "id", None)), "tid": tenant_text},
        )

    perm_id = _new_perm_id()
    internal_id = _perm_id_to_uuid(perm_id)
    created_at = current

    await session.execute(
        text(
            "INSERT INTO permission_grants"
            " (id, tenant_id, agent_id, service_id, action, constraints,"
            "  expires_at, grantor_type, grantor_id, created_at, created_by)"
            " VALUES"
            " (:id, :tenant_id, :agent_id, :service_id, :action,"
            "  CAST(:constraints AS jsonb), :expires_at, :grantor_type,"
            "  :grantor_id, :created_at, :created_by)"
        ),
        {
            "id": str(internal_id),
            "tenant_id": tenant_text,
            "agent_id": agent_id,
            "service_id": service_id,
            "action": action,
            "constraints": json.dumps(constraints),
            "expires_at": expires_at,
            "grantor_type": grantor.type,
            "grantor_id": grantor.id,
            "created_at": created_at,
            "created_by": grantor.id or agent_id,
        },
    )

    budget_cfg = constraints.get("budget")
    if budget_cfg:
        period_start, period_end = _budget_period_bounds(
            budget_cfg["period"], created_at
        )
        await session.execute(
            text(
                "INSERT INTO budget_counters"
                " (permission_id, period_start, period_end, ceiling, used, tenant_id)"
                " VALUES (:pid, :ps, :pe, :ceiling, 0, :tid)"
                " ON CONFLICT (permission_id, period_start) DO UPDATE"
                " SET ceiling = :ceiling, period_end = :pe"
            ),
            {
                "pid": str(internal_id),
                "ps": period_start,
                "pe": period_end,
                "ceiling": budget_cfg["ceiling"],
                "tid": tenant_text,
            },
        )

    return GrantRecord(
        id=str(internal_id),
        wire_id=perm_id,
        agent_id=agent_id,
        service_id=service_id,
        action=action,
        constraints=constraints,
        expires_at=expires_at,
        grantor_type=grantor.type,
        grantor_id=grantor.id,
        created_at=created_at,
        created=True,
    )


async def delete_grant(
    session: AsyncSession,
    *,
    tenant_id: UUID,
    grant_id: str,
    agent_id: str | None = None,
) -> GrantRecord | None:
    """Delete a stored grant and return its record, or None when absent."""
    db_id = wire_to_db_uuid(grant_id, "perm")
    tenant_text = str(tenant_id)
    params: dict[str, Any] = {"pid": db_id, "tid": tenant_text}

    if agent_id is None:
        select_sql = (
            "SELECT id, agent_id, service_id, action, constraints, expires_at,"
            " grantor_type, grantor_id, created_at"
            " FROM permission_grants"
            " WHERE id = :pid AND tenant_id = :tid"
        )
        delete_sql = (
            "DELETE FROM permission_grants"
            " WHERE id = :pid AND tenant_id = :tid"
        )
    else:
        params["aid"] = agent_id
        select_sql = (
            "SELECT id, agent_id, service_id, action, constraints, expires_at,"
            " grantor_type, grantor_id, created_at"
            " FROM permission_grants"
            " WHERE id = :pid AND tenant_id = :tid AND agent_id = :aid"
        )
        delete_sql = (
            "DELETE FROM permission_grants"
            " WHERE id = :pid AND tenant_id = :tid AND agent_id = :aid"
        )

    existing_result = await session.execute(text(select_sql), params)
    existing = existing_result.fetchone()
    if existing is None:
        return None

    await session.execute(text(delete_sql), params)
    return _record_from_row(existing, created=False)


# ---------------------------------------------------------------------------
# Audit and NOTIFY payload builders — the caller emits them
# ---------------------------------------------------------------------------


def grant_granted_audit_payload(record: GrantRecord) -> dict[str, Any]:
    """The ``agent.permission.granted`` payload for one grant."""
    return {
        "perm_id": record.wire_id,
        "agent_id": _wire(record.agent_id, "agent"),
        "service_id": _wire(record.service_id, "svc"),
        "action": record.action,
        "constraints": record.constraints,
        "expires_at": (
            record.expires_at.isoformat()
            if isinstance(record.expires_at, datetime)
            else None
        ),
        "grantor_type": record.grantor_type,
        "grantor_id": _grantor_wire_id(
            record.grantor_type, record.grantor_id
        ),
    }


def grant_revoked_audit_payload(
    record: GrantRecord, revoked_by: Grantor
) -> dict[str, Any]:
    """The ``agent.permission.revoked`` payload, naming the grantor and actor."""
    return {
        "permission_id": record.wire_id,
        "agent_id": _wire(record.agent_id, "agent"),
        "service_id": _wire(record.service_id, "svc"),
        "action": record.action,
        "grantor_type": record.grantor_type,
        "grantor_id": _grantor_wire_id(
            record.grantor_type, record.grantor_id
        ),
        "revoked_by_type": revoked_by.type,
        "revoked_by_id": _grantor_wire_id(revoked_by.type, revoked_by.id),
    }


def grant_revoked_notify_payload(
    tenant_id: UUID, record: GrantRecord, revoked_at: datetime
) -> dict[str, Any]:
    """The ``mintkey:agent`` NOTIFY payload, ``revoked_at`` as UTC ISO-8601."""
    if revoked_at.tzinfo is None:
        normalized = revoked_at.replace(tzinfo=timezone.utc)
    else:
        normalized = revoked_at.astimezone(timezone.utc)
    return {
        "event": "agent.permission.revoked",
        "tenant_id": str(tenant_id),
        "agent_id": _wire(record.agent_id, "agent"),
        "permission_id": record.wire_id,
        "service_id": _wire(record.service_id, "svc"),
        "revoked_at": normalized.isoformat(),
    }


def grant_wire_fields(record_or_row: Any, now: datetime) -> dict[str, Any]:
    """The four expiry/grantor fields every grant object in the API carries."""
    expires_at = _as_datetime(getattr(record_or_row, "expires_at", None))
    grantor_type = _grantor_type(getattr(record_or_row, "grantor_type", None))
    return {
        "expires_at": (
            expires_at.isoformat() if expires_at is not None else None
        ),
        "expired": is_expired(expires_at, now),
        "grantor_type": grantor_type,
        "grantor_id": _grantor_wire_id(
            grantor_type, getattr(record_or_row, "grantor_id", None)
        ),
    }
