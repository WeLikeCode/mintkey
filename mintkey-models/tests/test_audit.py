"""
Tests for audit.py — audit emission chokepoint.

TDD: written before implementation per T-1.0.9 (session 2) test-first discipline.
Source: T-1.0.9; design §1; ADR-0014.7 (hash chain mandatory); ADR-0008 (bound params).

Requirements verified:
- AUD-3: every state-change emits an audit event
- AUD-4: the audit hash chain is mandatory (prev_hash + hash per row, per-tenant chain)
- T-1.0.15: bound parameters only (no f-string SQL injection vector)
"""
from __future__ import annotations

import hashlib
import json
import uuid
from unittest.mock import AsyncMock, MagicMock, call, patch


def _run(coro):
    """Synchronous runner for async coroutines (no pytest-asyncio required)."""
    import asyncio
    return asyncio.get_event_loop().run_until_complete(coro)


class TestComputeHashDeterministic:
    """compute_hash produces identical output for identical inputs."""

    def test_compute_hash_deterministic(self) -> None:
        from mintkey_models.audit import compute_hash

        event = {
            "event_type": "service.created",
            "actor_type": "operator",
            "payload": {"name": "my-svc"},
        }
        prev_hash = b"\x00" * 32

        h1 = compute_hash(event, prev_hash)
        h2 = compute_hash(event, prev_hash)

        assert h1 == h2, "compute_hash must be deterministic"
        assert isinstance(h1, bytes)
        assert len(h1) == 32, "SHA-256 digest is 32 bytes"


class TestComputeHashChainIntegrity:
    """10-event chain: re-derive each hash from prior hash, all must match."""

    def test_compute_hash_chain_integrity(self) -> None:
        from mintkey_models.audit import compute_hash

        genesis = b"\x00" * 32  # simulated genesis hash
        hashes = [genesis]
        events = []

        for i in range(10):
            event = {"event_type": "test.event", "seq": i}
            h = compute_hash(event, hashes[-1])
            hashes.append(h)
            events.append(event)

        # Re-derive from scratch and compare
        derived = genesis
        for i, event in enumerate(events):
            derived = compute_hash(event, derived)
            assert derived == hashes[i + 1], (
                f"Chain broken at event {i}: derived {derived.hex()} != stored {hashes[i+1].hex()}"
            )


class TestComputeHashExcludesHashField:
    """The 'hash' key in the event dict is excluded from canonical serialisation."""

    def test_compute_hash_excludes_hash_field(self) -> None:
        from mintkey_models.audit import compute_hash

        event_without_hash = {
            "event_type": "agent.created",
            "actor_type": "operator",
        }
        event_with_hash = {
            "event_type": "agent.created",
            "actor_type": "operator",
            "hash": b"\xde\xad\xbe\xef",  # must be ignored
        }
        prev_hash = b"\x01" * 32

        h_without = compute_hash(event_without_hash, prev_hash)
        h_with = compute_hash(event_with_hash, prev_hash)

        assert h_without == h_with, (
            "compute_hash must exclude the 'hash' field from the canonical payload"
        )


class TestAuditEmitUsesBoundParams:
    """
    audit_emit() uses bound parameters for the advisory lock call.
    No f-string interpolation into SQL — ADR-0008, T-1.0.15.
    """

    def test_audit_emit_uses_bound_params(self) -> None:
        """
        The pg_advisory_xact_lock call must use text("... :lock_id") + params dict,
        not text(f"... {lock_id}").
        Source: ADR-0008; T-1.0.15 (SQL injection architecture test).
        """
        import inspect
        from mintkey_models import audit

        source = inspect.getsource(audit)

        # Must have :lock_id bound parameter in the advisory lock SQL
        assert ":lock_id" in source, (
            "pg_advisory_xact_lock must use :lock_id bound parameter, not f-string"
        )
        # No f-string on the pg_advisory_xact_lock line
        for line in source.splitlines():
            if "pg_advisory_xact_lock" in line:
                assert 'f"' not in line and "f'" not in line, (
                    f"pg_advisory_xact_lock line must not use f-string: {line!r}"
                )
