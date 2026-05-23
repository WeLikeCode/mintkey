"""
Audit chain verification — pure computation logic.

Importable without a database connection.  The DB entrypoint is main.py.

Architecture constraints:
  - Genesis hash = sha256("mintkey-audit-genesis-v1:" + tenant_id) — ADR-0014.7.
  - Per-event hash = sha256(canonical_json + prev_hash_bytes) — ADR-0014.7.
  - canonical_json = json.dumps({event_type, tenant_id, payload},
                                sort_keys=True, separators=(',',':')).
  - Chain is ordered by insertion (events list must be in chain order).

Source: T-1.13.2; ADR-0014.7; Req AUD-4.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import List, Optional

GENESIS_PREFIX = "mintkey-audit-genesis-v1:"


@dataclass
class AuditEvent:
    id: str
    event_type: str
    tenant_id: str
    payload: dict
    hash: bytes        # stored hash (bytes)
    prev_hash: bytes   # stored prev_hash (bytes)


@dataclass
class VerifyResult:
    ok: bool
    chain_length: int
    first_bad_event_id: Optional[str]
    message: str


def compute_event_hash(event: AuditEvent, prev_hash: bytes) -> bytes:
    """
    Recompute sha256(canonical_json_bytes + prev_hash_bytes).

    canonical_json = json.dumps(
        {event_type, tenant_id, payload},
        sort_keys=True, separators=(',',':')
    ).encode()

    Source: ADR-0014.7.
    """
    canonical = json.dumps(
        {
            "event_type": event.event_type,
            "tenant_id": event.tenant_id,
            "payload": event.payload,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return hashlib.sha256(canonical + prev_hash).digest()


def genesis_hash(tenant_id: str) -> bytes:
    """
    sha256("mintkey-audit-genesis-v1:" + tenant_id) as bytes.
    Source: ADR-0014.7; T-1.12.1.
    """
    return hashlib.sha256((GENESIS_PREFIX + tenant_id).encode()).digest()


def verify_chain(events: List[AuditEvent]) -> VerifyResult:
    """
    Verify that a list of AuditEvents form an intact hash chain.

    Algorithm:
      1. The first event's prev_hash must equal genesis_hash(tenant_id).
      2. For each event, recompute the hash from its canonical fields + prev_hash.
      3. Verify the stored hash matches the recomputed hash.
      4. The expected_prev for the next event is the recomputed hash.

    Returns VerifyResult with ok=True if the entire chain is intact, or
    ok=False with the first_bad_event_id of the first failing event.

    Source: T-1.13.2; ADR-0014.7; Req AUD-4.
    """
    if not events:
        return VerifyResult(
            ok=True,
            chain_length=0,
            first_bad_event_id=None,
            message="empty chain",
        )

    tenant_id = events[0].tenant_id
    expected_prev = genesis_hash(tenant_id)

    for i, event in enumerate(events):
        # Verify prev_hash matches expected
        if event.prev_hash != expected_prev:
            return VerifyResult(
                ok=False,
                chain_length=i,
                first_bad_event_id=event.id,
                message="prev_hash mismatch at event " + event.id,
            )

        # Recompute and verify stored hash
        computed = compute_event_hash(event, event.prev_hash)
        if event.hash != computed:
            return VerifyResult(
                ok=False,
                chain_length=i,
                first_bad_event_id=event.id,
                message="hash mismatch at event " + event.id,
            )

        expected_prev = computed

    return VerifyResult(
        ok=True,
        chain_length=len(events),
        first_bad_event_id=None,
        message="chain intact",
    )
