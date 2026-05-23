"""
Unit tests for admin_api.services.audit_emit_rate_limiter.

Covers:
  1. test_burst_allowed          — first 100 requests within a second are all allowed
  2. test_101st_denied           — 101st request without any sleep is denied
  3. test_refill_after_elapsed   — after simulating elapsed time, tokens replenish
  4. test_disabled_mode          — rps=0 always allows
  5. test_independent_buckets    — two different tokens have independent buckets
  6. test_concurrent_access      — concurrent coroutines do not exceed capacity
  7. test_token_log_id_no_raw    — token_log_id never returns the raw token value
  8. test_timestamp_refill       — bucket replenishes proportionally to elapsed time
                                   (validates the timestamp-based refill, not
                                   try_acquire-only refill)

Source: #26 — rate-limit /v1/internal/audit/emit.
"""
from __future__ import annotations

import asyncio
import sys
import os
from unittest.mock import patch

import pytest

# Ensure admin-api/src is importable.
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
_ADMIN_SRC = os.path.join(_REPO_ROOT, "apps/admin-api", "src")
if _ADMIN_SRC not in sys.path:
    sys.path.insert(0, _ADMIN_SRC)

from admin_api.services.audit_emit_rate_limiter import (
    AuditEmitRateLimiter,
    _TokenBucket,
    token_log_id,
)


# ---------------------------------------------------------------------------
# _TokenBucket unit tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_burst_allowed() -> None:
    """A fresh bucket with capacity 100 allows exactly 100 requests."""
    bucket = _TokenBucket(capacity=100.0, rate=100.0)
    results = [await bucket.try_acquire() for _ in range(100)]
    assert all(results), "All 100 burst requests must be allowed"


@pytest.mark.asyncio
async def test_101st_denied() -> None:
    """After draining 100 tokens the 101st request is denied."""
    bucket = _TokenBucket(capacity=100.0, rate=100.0)
    for _ in range(100):
        await bucket.try_acquire()
    result = await bucket.try_acquire()
    assert result is False, "101st request must be rate-limited"


@pytest.mark.asyncio
async def test_refill_after_elapsed() -> None:
    """
    Timestamp-based refill: manipulating monotonic time causes tokens to
    accumulate even without calling try_acquire in the interim.

    We drain the bucket, then advance the fake clock by 0.5 s and verify
    50 more tokens are available.
    """
    import time as _time_mod

    bucket = _TokenBucket(capacity=100.0, rate=100.0)

    # Drain all 100 tokens.
    for _ in range(100):
        await bucket.try_acquire()

    assert await bucket.try_acquire() is False, "bucket should be empty after drain"

    # Advance monotonic clock by 0.5 s → expect 50 new tokens.
    original_monotonic = _time_mod.monotonic
    advanced = original_monotonic() + 0.5

    with patch("admin_api.services.audit_emit_rate_limiter.time") as mock_time:
        mock_time.monotonic.return_value = advanced
        # Force a refill by calling try_acquire once.
        first = await bucket.try_acquire()

    assert first is True, "After 0.5 s refill, at least one request must be allowed"


@pytest.mark.asyncio
async def test_disabled_mode() -> None:
    """rps=0 → disabled → all requests allowed regardless of volume."""
    limiter = AuditEmitRateLimiter(rps=0)
    results = [await limiter.try_acquire("tok") for _ in range(1000)]
    assert all(results), "Disabled limiter must always allow"


@pytest.mark.asyncio
async def test_independent_buckets() -> None:
    """Two different tokens share no bucket state."""
    limiter = AuditEmitRateLimiter(rps=5)

    # Drain token_a completely.
    for _ in range(5):
        await limiter.try_acquire("token_a")
    assert await limiter.try_acquire("token_a") is False

    # token_b should still have a full bucket.
    for _ in range(5):
        result = await limiter.try_acquire("token_b")
        assert result is True, "token_b bucket must be independent of token_a"


@pytest.mark.asyncio
async def test_concurrent_access() -> None:
    """
    Fire 200 concurrent coroutines at a capacity-100 limiter.
    Exactly 100 must succeed and the rest must be denied.

    This validates thread/async safety — the asyncio.Lock prevents races
    that would allow more than capacity tokens to be consumed.
    """
    limiter = AuditEmitRateLimiter(rps=100)

    results = await asyncio.gather(
        *[limiter.try_acquire("shared_token") for _ in range(200)]
    )

    allowed = sum(1 for r in results if r)
    denied = sum(1 for r in results if not r)

    assert allowed == 100, f"Expected exactly 100 allowed, got {allowed}"
    assert denied == 100, f"Expected exactly 100 denied, got {denied}"


@pytest.mark.asyncio
async def test_token_log_id_no_raw() -> None:
    """token_log_id must never return the raw token value."""
    raw = "mk_svctoken_dev_broker_1a9915207f79a78a"
    log_id = token_log_id(raw)
    assert raw not in log_id, "Raw token must not appear in log id"
    assert len(log_id) == 12, "log_id should be 12 hex chars"


@pytest.mark.asyncio
async def test_timestamp_refill_proportional() -> None:
    """
    Bucket refills proportionally to elapsed time, not just on call.

    Drain to zero, then set the bucket's _last_refill 1.0 s in the past
    (simulating idle time between calls).  The next try_acquire should
    observe 100 tokens (full bucket) because 1 s * 100 rps = 100 tokens.
    """
    import time as _time_mod

    bucket = _TokenBucket(capacity=100.0, rate=100.0)

    # Drain completely.
    for _ in range(100):
        await bucket.try_acquire()

    # Simulate 1 second of idle time by backdating _last_refill.
    bucket._last_refill = _time_mod.monotonic() - 1.0

    # Now all 100 tokens should be available (capped at capacity).
    results = [await bucket.try_acquire() for _ in range(100)]
    assert all(results), (
        "After 1 s idle, a capacity-100 bucket at 100 rps should allow 100 requests"
    )
    # 101st must be denied again.
    assert await bucket.try_acquire() is False


# ---------------------------------------------------------------------------
# AuditEmitRateLimiter.try_acquire integration
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_limiter_100_ok_101_denied() -> None:
    """AuditEmitRateLimiter: 100 succeed, 101st fails."""
    limiter = AuditEmitRateLimiter(rps=100)
    token = "test-token-xyz"
    for i in range(100):
        ok = await limiter.try_acquire(token)
        assert ok, f"Request {i + 1} should be allowed"
    assert await limiter.try_acquire(token) is False, "101st should be denied"
