"""
Canonical audit hash form shared by the audit writer and every verifier.

Source: specs/audit-chain/spec.md — "One canonical form for the audit event
hash" and "The chain is verified from the stored columns by its links";
design.md D1-D6; ADR-0014.7.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Final, Mapping, Sequence
from uuid import UUID

GENESIS_PREFIX: Final[str] = "mintkey-audit-genesis-v1:"


def genesis_hash(tenant_id: str) -> bytes:
    """The first ``prev_hash`` of a tenant's chain."""
    return hashlib.sha256((GENESIS_PREFIX + tenant_id).encode("utf-8")).digest()


def canonical_at(at: datetime) -> str:
    """The canonical text of an event time: UTC, ``datetime.isoformat()``."""
    if at.tzinfo is None:
        raise ValueError("at must be timezone-aware")
    return at.astimezone(timezone.utc).isoformat()


def canonical_id(value: object) -> str | None:
    """Canonical text for an id column: lowercase UUID text where it is one."""
    if value is None:
        return None
    text = str(value)
    try:
        return str(UUID(text))
    except ValueError:
        return text


def canonical_event_fields(
    *,
    event_id: object,
    tenant_id: object,
    event_type: str,
    actor_id: object,
    actor_type: str | None,
    target_id: object,
    target_type: str | None,
    payload: Mapping[str, Any],
    at: datetime,
) -> dict[str, Any]:
    """The nine hashed fields of an audit event, serialised from stored values."""
    return {
        "id": canonical_id(event_id),
        "tenant_id": canonical_id(tenant_id),
        "event_type": event_type,
        "actor_id": canonical_id(actor_id),
        "actor_type": actor_type,
        "target_id": canonical_id(target_id),
        "target_type": target_type,
        "payload": dict(payload),
        "at": canonical_at(at),
    }


def canonical_json_bytes(fields: Mapping[str, Any]) -> bytes:
    """The canonical JSON bytes of the hashed fields, without the ``hash`` key."""
    canonical = {key: value for key, value in fields.items() if key != "hash"}
    return json.dumps(
        canonical, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def chain_hash(canonical: bytes, prev_hash: bytes) -> bytes:
    """One link of the chain: ``sha256(canonical + prev_hash)``."""
    return hashlib.sha256(canonical + prev_hash).digest()


@dataclass(frozen=True)
class ChainEvent:
    """The 13 stored columns of one audit event."""

    id: str
    tenant_id: str
    event_type: str
    actor_id: str | None
    actor_type: str | None
    target_id: str | None
    target_type: str | None
    payload: Mapping[str, Any]
    at: datetime
    prev_hash: bytes
    hash: bytes
    request_id: str | None = None
    trace_id: str | None = None


def event_hash(event: ChainEvent) -> bytes:
    """The hash the writer would store for this event's current field values."""
    return chain_hash(
        canonical_json_bytes(
            canonical_event_fields(
                event_id=event.id,
                tenant_id=event.tenant_id,
                event_type=event.event_type,
                actor_id=event.actor_id,
                actor_type=event.actor_type,
                target_id=event.target_id,
                target_type=event.target_type,
                payload=event.payload,
                at=event.at,
            )
        ),
        event.prev_hash,
    )


def chain_event_from_row(row: Any) -> ChainEvent:
    """Build a :class:`ChainEvent` from a database row of ``audit_events``."""
    event_id = canonical_id(row.id)
    tenant_id = canonical_id(row.tenant_id)
    if event_id is None or tenant_id is None:
        raise ValueError("audit event row without id or tenant_id")

    raw_payload = row.payload
    payload: Mapping[str, Any]
    if raw_payload is None:
        payload = {}
    elif isinstance(raw_payload, str):
        payload = json.loads(raw_payload)
    else:
        payload = raw_payload

    return ChainEvent(
        id=event_id,
        tenant_id=tenant_id,
        event_type=row.event_type,
        actor_id=canonical_id(row.actor_id),
        actor_type=row.actor_type,
        target_id=canonical_id(row.target_id),
        target_type=row.target_type,
        payload=payload,
        at=row.at,
        prev_hash=bytes(row.prev_hash),
        hash=bytes(row.hash),
        request_id=canonical_id(row.request_id),
        trace_id=canonical_id(row.trace_id),
    )


@dataclass(frozen=True)
class ChainResult:
    """The outcome of verifying a tenant's chain."""

    ok: bool
    chain_length: int
    last_event_id: str | None
    first_bad_event_id: str | None
    expected_hash: bytes | None
    actual_hash: bytes | None
    message: str


def verify_events(events: Sequence[ChainEvent]) -> ChainResult:
    """Verify a chain by its links, independent of the order of ``events``."""
    if not events:
        return ChainResult(True, 0, None, None, None, None, "empty chain")

    current = genesis_hash(events[0].tenant_id)
    visited = [False] * len(events)
    chain_length = 0
    last_event_id: str | None = None

    for _ in range(len(events)):
        index = next(
            (
                i
                for i, candidate in enumerate(events)
                if not visited[i] and candidate.prev_hash == current
            ),
            None,
        )
        if index is None:
            break

        event = events[index]
        visited[index] = True
        computed = event_hash(event)
        if computed != event.hash:
            return ChainResult(
                False,
                chain_length,
                last_event_id,
                event.id,
                computed,
                event.hash,
                f"hash mismatch at event {event.id}",
            )
        if event.request_id is not None or event.trace_id is not None:
            return ChainResult(
                False,
                chain_length,
                last_event_id,
                event.id,
                None,
                None,
                f"event {event.id} has request_id or trace_id set",
            )
        current = event.hash
        chain_length += 1
        last_event_id = event.id

    if chain_length < len(events):
        first_bad = next(
            event
            for i, event in enumerate(events)
            if not visited[i]
        )
        return ChainResult(
            False,
            chain_length,
            last_event_id,
            first_bad.id,
            current,
            first_bad.prev_hash,
            f"event {first_bad.id} does not follow the chain",
        )

    return ChainResult(
        True, chain_length, last_event_id, None, None, None, "chain intact"
    )
