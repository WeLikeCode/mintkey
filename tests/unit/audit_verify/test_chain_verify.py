"""
Unit tests: Audit chain verification logic.

Tests verify.py (audit-verify-job/verify.py) without any DB connection.

Sources:
  - ADR-0014.7 (hash chain mandatory)
  - Req AUD-4 (chain verification)
  - T-1.13.2 (audit-verify-job)
"""
from __future__ import annotations

import hashlib
import json
import sys
import os

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
VERIFY_JOB_DIR = os.path.join(REPO_ROOT, "audit-verify-job")
if VERIFY_JOB_DIR not in sys.path:
    sys.path.insert(0, VERIFY_JOB_DIR)

from verify import (  # noqa: E402
    AuditEvent,
    VerifyResult,
    compute_event_hash,
    genesis_hash,
    verify_chain,
)

TENANT_ID = "tenant_00000000000000000000000001"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_chain(n: int, tenant_id: str = TENANT_ID):
    """
    Build a list of n AuditEvents with a valid hash chain starting from genesis.
    Returns (events, list_of_computed_hashes).
    """
    events = []
    prev = genesis_hash(tenant_id)
    for i in range(n):
        payload = {"seq": i, "data": "event-" + str(i)}
        event = AuditEvent(
            id="evt_" + str(i).zfill(3),
            event_type="test.event",
            tenant_id=tenant_id,
            payload=payload,
            hash=b"\x00" * 32,   # placeholder, filled below
            prev_hash=prev,
        )
        computed = compute_event_hash(event, prev)
        event.hash = computed
        events.append(event)
        prev = computed
    return events


# ---------------------------------------------------------------------------
# 1. Intact chain returns ok=True, chain_length=N
# ---------------------------------------------------------------------------


def test_intact_chain_returns_ok() -> None:
    """
    A correctly constructed 5-event chain → ok=True, chain_length=5.
    Source: T-1.13.2; Req AUD-4.
    """
    events = _build_chain(5)
    result = verify_chain(events)
    assert result.ok is True
    assert result.chain_length == 5
    assert result.first_bad_event_id is None


# ---------------------------------------------------------------------------
# 2. Tampered chain detects first bad event
# ---------------------------------------------------------------------------


def test_tampered_chain_detects_first_bad_event() -> None:
    """
    Corrupting row 3's payload makes verify_chain report first_bad_event_id=row3.id.
    Source: T-1.13.2; Req AUD-4; ADR-0014.7.
    """
    events = _build_chain(5)

    # Corrupt row index 2 (0-based → "evt_002") payload after building
    # The stored hash no longer matches the corrupted payload.
    bad_event = events[2]
    bad_event.payload = {"seq": 999, "data": "tampered"}
    # Leave bad_event.hash unchanged → mismatch on recompute

    result = verify_chain(events)
    assert result.ok is False
    assert result.first_bad_event_id == "evt_002"
    assert result.chain_length == 2  # first 2 events (indices 0,1) were ok


# ---------------------------------------------------------------------------
# 3. Genesis hash verification
# ---------------------------------------------------------------------------


def test_genesis_hash_verification() -> None:
    """
    The first event's prev_hash must equal sha256("mintkey-audit-genesis-v1:"+tenant_id).
    A chain with wrong genesis prev_hash → ok=False at first event.
    Source: T-1.13.2; ADR-0014.7.
    """
    events = _build_chain(3)

    # Corrupt the first event's prev_hash (not the genesis hash)
    events[0].prev_hash = b"\xff" * 32

    result = verify_chain(events)
    assert result.ok is False
    assert result.first_bad_event_id == "evt_000"


def test_genesis_hash_value() -> None:
    """
    genesis_hash() returns sha256("mintkey-audit-genesis-v1:" + tenant_id) as bytes.
    Source: T-1.12.1; ADR-0014.7.
    """
    tid = "tenant_ABC"
    expected = hashlib.sha256(
        ("mintkey-audit-genesis-v1:" + tid).encode()
    ).digest()
    assert genesis_hash(tid) == expected


# ---------------------------------------------------------------------------
# 4. Empty chain
# ---------------------------------------------------------------------------


def test_empty_chain_is_ok() -> None:
    """Empty event list → ok=True, chain_length=0."""
    result = verify_chain([])
    assert result.ok is True
    assert result.chain_length == 0
    assert result.first_bad_event_id is None
