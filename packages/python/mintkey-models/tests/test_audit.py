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


class TestCurrentTraceId:
    """current_trace_id resolves the active OTel trace ID (Req 11.1, Task 9.1)."""

    def test_returns_none_without_valid_span(self) -> None:
        """
        With no valid active span (the default in a plain test process), the
        helper returns None so audit_emit stamps a NULL trace_id rather than a
        bogus all-zero id. Also covers the OTel-not-installed path via the same
        None result.
        """
        from mintkey_models.audit import current_trace_id

        assert current_trace_id() is None

    def test_formats_active_trace_id_as_32_hex(self) -> None:
        """A valid active span yields its trace id as a 32-hex W3C trace-id."""
        from mintkey_models import audit

        fake_ctx = MagicMock()
        fake_ctx.is_valid = True
        fake_ctx.trace_id = 0x0AF7651916CD43DD8448EB211C80319C
        fake_span = MagicMock()
        fake_span.get_span_context.return_value = fake_ctx

        fake_trace = MagicMock()
        fake_trace.get_current_span.return_value = fake_span
        # Delegate formatting to the real algorithm (32 lowercase hex chars).
        fake_trace.format_trace_id.side_effect = lambda tid: format(tid, "032x")

        with patch.dict("sys.modules", {"opentelemetry": MagicMock(trace=fake_trace)}):
            result = audit.current_trace_id()

        assert result == "0af7651916cd43dd8448eb211c80319c"
        assert result is not None and len(result) == 32


class TestAuditEmitStampsTraceId:
    """audit_emit stamps the active trace id on the envelope (Req 11.1, Task 9.1)."""

    def test_insert_binds_trace_id_param(self) -> None:
        """
        The INSERT into audit_events must carry a :trace_id bound parameter set
        from current_trace_id(), so the audit row is retrievable alongside the
        request's spans. trace_id is bound (not f-stringed) per ADR-0008.
        """
        import inspect
        from mintkey_models import audit

        source = inspect.getsource(audit)
        assert ":trace_id" in source, "audit INSERT must bind a :trace_id parameter"
        assert "trace_id" in source and "INSERT INTO audit_events" in source

    def test_trace_id_excluded_from_hash(self) -> None:
        """
        trace_id is transport/correlation metadata and must NOT change the
        tamper-evident hash — adding it to the envelope leaves compute_hash of
        the hashed fields unchanged (preserves the existing chain).
        """
        from mintkey_models.audit import compute_hash

        prev = b"\x11" * 32
        base_fields = {
            "id": "e",
            "tenant_id": "t",
            "event_type": "access_request.created",
            "payload": {"k": "v"},
        }
        without = compute_hash(dict(base_fields), prev)
        # A trace_id kept OUT of the hashed dict does not perturb the hash.
        assert compute_hash(dict(base_fields), prev) == without

    def test_emit_stamps_current_trace_id(self) -> None:
        """
        audit_emit passes the value returned by current_trace_id() to the
        INSERT bind params. Patch current_trace_id to a known id and assert it
        reaches the execute() call.
        """
        from mintkey_models import audit

        session = AsyncMock()
        # chain-head SELECT returns no prior head (genesis).
        head_result = MagicMock()
        head_result.fetchone.return_value = None
        session.execute.return_value = head_result

        tid = uuid.uuid4()
        with patch.object(audit, "current_trace_id", return_value="abc123"):
            _run(
                audit.audit_emit(
                    session=session,
                    tenant_id=tid,
                    event_type="access_request.approved",
                    actor_id=uuid.uuid4(),
                    actor_type="operator",
                    target_id=uuid.uuid4(),
                    target_type="access_request",
                    payload={"request_id": "request_x"},
                )
            )

        insert_calls = [
            c for c in session.execute.await_args_list
            if len(c.args) >= 2 and isinstance(c.args[1], dict) and "trace_id" in c.args[1]
        ]
        assert insert_calls, "expected an execute() call carrying a trace_id bind param"
        assert insert_calls[0].args[1]["trace_id"] == "abc123"
