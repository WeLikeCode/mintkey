"""
Audit emission chokepoint — shared between admin-api and mcp-server.

Every state change that passes through the FastAPI admin REST API calls
audit_emit(). The function:

  1. Takes a per-tenant advisory lock (bound parameter — ADR-0008, T-1.0.15).
  2. Reads the current chain head (SELECT ... FOR UPDATE).
  3. Builds the canonical event payload (sort_keys, no "hash" field).
  4. Computes hash = sha256(canonical_bytes + prev_hash_bytes).
  5. INSERTs into audit_events.
  6. UPDATEs audit_chain_state.

Source: design §1; ADR-0014.7 (hash chain mandatory);
        ADR-0008 (bound parameters — no f-string SQL);
        Req AUD-3 (every state change emits); Req AUD-4 (hash chain).
"""
from __future__ import annotations

import hashlib
import json
import struct
from datetime import datetime, timezone
from typing import Any, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Prometheus audit metrics — OPS-N
# Idempotent declaration pattern: try/except ValueError handles module reimport
# and shared-registry scenarios (multiple processes sharing the same registry).
# ---------------------------------------------------------------------------
_PROMETHEUS_AVAILABLE = False
_audit_events_total = None
_audit_chain_ok = None

try:
    from prometheus_client import Counter, Gauge, REGISTRY

    try:
        _audit_events_total = Counter(
            "mintkey_audit_events_total",
            "Total audit events emitted",
            ["event_type"],
        )
    except ValueError:
        # Registry lookup returns Collector; cast to Counter for strict-mode compat.
        _audit_events_total = cast(
            Counter, REGISTRY._names_to_collectors.get("mintkey_audit_events_total")
        )

    try:
        _audit_chain_ok = Gauge(
            "mintkey_audit_chain_ok",
            "1 when the last audit chain insert succeeded, 0 on verify failure",
        )
    except ValueError:
        # Registry lookup returns Collector; cast to Gauge for strict-mode compat.
        _audit_chain_ok = cast(
            Gauge, REGISTRY._names_to_collectors.get("mintkey_audit_chain_ok")
        )

    _PROMETHEUS_AVAILABLE = True
except ImportError:
    pass


def compute_hash(event_dict: dict[str, Any], prev_hash: bytes) -> bytes:
    """
    Compute sha256(canonical_json_bytes + prev_hash_bytes).

    The "hash" key is excluded from the canonical payload so this function
    can be called on a dict that already has a "hash" field without changing
    the result.

    Source: ADR-0014.7; design §1.
    """
    # Exclude "hash" field from canonical payload — ADR-0014.7
    canonical_dict = {k: v for k, v in event_dict.items() if k != "hash"}
    canonical_bytes = json.dumps(
        canonical_dict, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")
    return hashlib.sha256(canonical_bytes + prev_hash).digest()


async def audit_emit(
    session: AsyncSession,
    tenant_id: UUID,
    event_type: str,
    actor_id: UUID | None,
    actor_type: str,
    target_id: UUID | None,
    target_type: str | None,
    payload: dict[str, Any],
) -> None:
    """
    Single audit chokepoint. Computes prev_hash + hash, INSERTs into
    audit_events, and advances audit_chain_state.

    Must run inside the caller's transaction. Never call outside a transaction.

    Source: design §1; ADR-0014.7; Req AUD-3/4.
    """
    # Step 1: per-tenant advisory lock (bound parameter — ADR-0008 / T-1.0.15)
    # Lock key derived from first 8 bytes of tenant_id bytes (deterministic int64)
    lock_id = struct.unpack(">q", tenant_id.bytes[:8])[0]
    await session.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": lock_id},
    )

    # Step 2: read chain head (FOR UPDATE to serialise concurrent writers)
    row = await session.execute(
        text(
            "SELECT head_hash FROM audit_chain_state"
            " WHERE tenant_id = :tid FOR UPDATE"
        ),
        {"tid": str(tenant_id)},
    )
    chain_row = row.fetchone()
    prev_hash: bytes = chain_row[0] if chain_row else b"\x00" * 32

    # Step 3 + 4: build canonical event and compute hash
    now = datetime.now(timezone.utc)
    from uuid import uuid4
    event_id = uuid4()

    event_fields: dict[str, Any] = {
        "id": str(event_id),
        "tenant_id": str(tenant_id),
        "event_type": event_type,
        "actor_id": str(actor_id) if actor_id is not None else None,
        "actor_type": actor_type,
        "target_id": str(target_id) if target_id is not None else None,
        "target_type": target_type,
        "payload": payload,
        "at": now.isoformat(),
    }
    h = compute_hash(event_fields, prev_hash)

    # Step 5: INSERT into audit_events
    # Use CAST(:payload AS jsonb) rather than :payload::jsonb — asyncpg
    # misparses the :: cast operator when it follows a named bind parameter.
    await session.execute(
        text(
            "INSERT INTO audit_events"
            " (id, tenant_id, event_type, actor_id, actor_type,"
            "  target_id, target_type, payload, prev_hash, hash, at)"
            " VALUES"
            " (:id, :tenant_id, :event_type, :actor_id, :actor_type,"
            "  :target_id, :target_type, CAST(:payload AS jsonb), :prev_hash, :hash, :at)"
        ),
        {
            "id": str(event_id),
            "tenant_id": str(tenant_id),
            "event_type": event_type,
            "actor_id": str(actor_id) if actor_id is not None else None,
            "actor_type": actor_type,
            "target_id": str(target_id) if target_id is not None else None,
            "target_type": target_type,
            "payload": json.dumps(payload),
            "prev_hash": prev_hash,
            "hash": h,
            "at": now,
        },
    )

    # Step 6: UPDATE audit_chain_state
    await session.execute(
        text(
            "UPDATE audit_chain_state"
            " SET head_hash = :hash, head_event_id = :event_id"
            " WHERE tenant_id = :tid"
        ),
        {"hash": h, "event_id": str(event_id), "tid": str(tenant_id)},
    )

    # Prometheus metrics — OPS-N
    # Increment after both INSERT and UPDATE succeed (still inside the caller's
    # transaction, but the DB work is done and will be committed by the caller).
    if _PROMETHEUS_AVAILABLE and _audit_events_total is not None:
        try:
            _audit_events_total.labels(event_type=event_type).inc()
        except Exception:
            pass  # Never let metric export break an audit write
    if _PROMETHEUS_AVAILABLE and _audit_chain_ok is not None:
        try:
            _audit_chain_ok.set(1.0)
        except Exception:
            pass
