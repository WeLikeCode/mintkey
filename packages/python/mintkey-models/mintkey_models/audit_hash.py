"""
Canonical audit hash form shared by the audit writer and every verifier.

Source: specs/audit-chain/spec.md — "One canonical form for the audit event
hash" and "The chain is verified from the stored columns by its links";
design.md D1-D6; ADR-0014.7.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping, Sequence


def genesis_hash(tenant_id: str) -> bytes:
    raise NotImplementedError


def canonical_at(at: datetime) -> str:
    raise NotImplementedError


def canonical_id(value: object) -> str | None:
    raise NotImplementedError


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
    raise NotImplementedError


def canonical_json_bytes(fields: Mapping[str, Any]) -> bytes:
    raise NotImplementedError


def chain_hash(canonical: bytes, prev_hash: bytes) -> bytes:
    raise NotImplementedError


def event_hash(event: Any) -> bytes:
    raise NotImplementedError


def chain_event_from_row(row: Any) -> Any:
    raise NotImplementedError


def verify_events(events: Sequence[Any]) -> Any:
    raise NotImplementedError
