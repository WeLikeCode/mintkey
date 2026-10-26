"""
Audit chain verification — pure computation logic.

Importable without a database connection.  The DB entrypoint is main.py.

The canonical hash form lives in ``mintkey_models.audit_hash`` and is shared
with the writer (``audit_emit``); this module only adapts the job's dataclasses
and database rows to it.

Architecture constraints:
  - Genesis hash = sha256("mintkey-audit-genesis-v1:" + tenant_id) — ADR-0014.7.
  - Per-event hash = sha256(canonical_json + prev_hash_bytes) — ADR-0014.7.
  - The chain is followed by its links (prev_hash -> previous hash), so the
    order of the events given to a verifier does not matter.

Source: T-1.13.2; ADR-0014.7; Req AUD-4; specs/audit-chain/spec.md.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, List, Optional, Sequence

from mintkey_models.audit_hash import (
    GENESIS_PREFIX,
    ChainEvent,
    chain_event_from_row,
    event_hash,
    genesis_hash,
    verify_events,
)

__all__ = [
    "GENESIS_PREFIX",
    "AuditEvent",
    "VerifyResult",
    "compute_event_hash",
    "genesis_hash",
    "verify_chain",
    "verify_rows",
]


@dataclass
class AuditEvent:
    id: str
    event_type: str
    tenant_id: str
    payload: dict
    hash: bytes        # stored hash (bytes)
    prev_hash: bytes   # stored prev_hash (bytes)
    actor_id: str | None = None
    actor_type: str | None = None
    target_id: str | None = None
    target_type: str | None = None
    at: datetime | None = None
    request_id: str | None = None
    trace_id: str | None = None


@dataclass
class VerifyResult:
    ok: bool
    chain_length: int
    first_bad_event_id: Optional[str]
    message: str


def _chain_event(event: AuditEvent, prev_hash: bytes) -> ChainEvent:
    """Adapt an ``AuditEvent`` to the canonical ``ChainEvent``."""
    if event.at is None:
        raise ValueError("event has no at")
    return ChainEvent(
        id=event.id,
        tenant_id=event.tenant_id,
        event_type=event.event_type,
        actor_id=event.actor_id,
        actor_type=event.actor_type,
        target_id=event.target_id,
        target_type=event.target_type,
        payload=event.payload,
        at=event.at,
        prev_hash=prev_hash,
        hash=event.hash,
        request_id=event.request_id,
        trace_id=event.trace_id,
    )


def compute_event_hash(event: AuditEvent, prev_hash: bytes) -> bytes:
    """
    Recompute the canonical hash of the event's fields with ``prev_hash``.

    Raises ``ValueError`` when the event has no time.

    Source: ADR-0014.7; specs/audit-chain/spec.md.
    """
    return event_hash(_chain_event(event, prev_hash))


def verify_chain(events: List[AuditEvent]) -> VerifyResult:
    """
    Verify that a list of AuditEvents form an intact hash chain.

    The chain is followed by its links, so the order of ``events`` does not
    matter.  Returns a ``VerifyResult`` with the first failing event named.

    Source: T-1.13.2; ADR-0014.7; Req AUD-4.
    """
    result = verify_events([_chain_event(event, event.prev_hash) for event in events])
    return VerifyResult(
        ok=result.ok,
        chain_length=result.chain_length,
        first_bad_event_id=result.first_bad_event_id,
        message=result.message,
    )


def verify_rows(rows: Sequence[Any]) -> VerifyResult:
    """
    Verify stored ``audit_events`` rows with the canonical form.

    Source: specs/audit-chain/spec.md — "The verify job checks a chain with
    the canonical form"; design.md D6.
    """
    result = verify_events([chain_event_from_row(row) for row in rows])
    return VerifyResult(
        ok=result.ok,
        chain_length=result.chain_length,
        first_bad_event_id=result.first_bad_event_id,
        message=result.message,
    )
