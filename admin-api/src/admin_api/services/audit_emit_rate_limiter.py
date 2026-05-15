"""
In-process token-bucket rate limiter for /v1/internal/audit/emit.

One bucket per service-token string.  Capacity and refill rate are both
MINTKEY_AUDIT_EMIT_RATE_LIMIT_RPS (default 100), giving a burst of 100
requests and a sustained rate of 100 req/s.

Design notes
------------
- Timestamp-based refill: elapsed wall-clock time is used to compute how
  many tokens to add back each time try_acquire() is called.  This avoids
  the common bug where a bucket only refills when it is queried — tokens
  accumulate correctly even across idle periods.
- Thread / async safety: a single asyncio.Lock per bucket serialises
  concurrent coroutines.  The lock is created lazily.
- Disabled mode: set MINTKEY_AUDIT_EMIT_RATE_LIMIT_RPS=0 to bypass rate
  limiting entirely (useful for test environments that do not need it).
- The module exports a singleton `_limiter` used by internal.py.  Tests
  inject a fresh AuditEmitRateLimiter instance via FastAPI dependency
  override so state does not leak between test runs.

Source: #26 — rate-limit /v1/internal/audit/emit.
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import time
from typing import Optional

_log = logging.getLogger("admin_api.services.audit_emit_rate_limiter")


def _rps_from_env() -> int:
    """Read MINTKEY_AUDIT_EMIT_RATE_LIMIT_RPS, default 100.  0 = disabled."""
    raw = os.getenv("MINTKEY_AUDIT_EMIT_RATE_LIMIT_RPS", "100")
    try:
        v = int(raw)
    except (ValueError, TypeError):
        _log.warning(
            "MINTKEY_AUDIT_EMIT_RATE_LIMIT_RPS=%r is not an integer; using 100",
            raw,
        )
        v = 100
    return max(0, v)


class _TokenBucket:
    """
    Single token bucket for one service-token identity.

    capacity  — maximum tokens held (== burst ceiling)
    rate      — tokens added per second (== sustained rate)
    """

    __slots__ = ("capacity", "rate", "tokens", "_last_refill", "_lock")

    def __init__(self, capacity: float, rate: float) -> None:
        self.capacity = capacity
        self.rate = rate
        self.tokens = capacity  # start full
        self._last_refill: float = time.monotonic()
        self._lock: Optional[asyncio.Lock] = None

    def _get_lock(self) -> asyncio.Lock:
        # Lazy creation so the lock is bound to the correct event loop.
        if self._lock is None:
            self._lock = asyncio.Lock()
        return self._lock

    def _refill(self) -> None:
        """Add tokens proportional to elapsed time since last refill."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        self._last_refill = now
        gain = elapsed * self.rate
        self.tokens = min(self.capacity, self.tokens + gain)

    async def try_acquire(self) -> bool:
        """
        Attempt to consume one token.

        Returns True if the request is allowed, False if the bucket is empty.
        """
        async with self._get_lock():
            self._refill()
            if self.tokens >= 1.0:
                self.tokens -= 1.0
                return True
            return False


class AuditEmitRateLimiter:
    """
    Per-service-token rate limiter backed by in-process token buckets.

    Instantiate once (module singleton) or inject a fresh instance per test.
    """

    def __init__(self, rps: Optional[int] = None) -> None:
        self._rps: int = rps if rps is not None else _rps_from_env()
        self._buckets: dict[str, _TokenBucket] = {}
        self._map_lock = asyncio.Lock()

    @property
    def disabled(self) -> bool:
        return self._rps == 0

    async def _get_bucket(self, token: str) -> _TokenBucket:
        """Return (creating if needed) the bucket for *token*."""
        async with self._map_lock:
            if token not in self._buckets:
                self._buckets[token] = _TokenBucket(
                    capacity=float(self._rps),
                    rate=float(self._rps),
                )
            return self._buckets[token]

    async def try_acquire(self, token: str) -> bool:
        """
        Check whether this token has budget remaining.

        Returns True (allow) or False (rate-limited).
        When disabled (rps==0), always returns True.
        """
        if self.disabled:
            return True
        bucket = await self._get_bucket(token)
        return await bucket.try_acquire()


def token_log_id(token: str) -> str:
    """
    Return a safe, non-reversible identifier for log messages.

    We use SHA-256 of the raw token and take the first 12 hex chars.
    This gives enough entropy for correlation while never leaking the secret.
    """
    return hashlib.sha256(token.encode()).hexdigest()[:12]


# ---------------------------------------------------------------------------
# Module-level singleton — used by default in production.
# Tests override this via FastAPI dependency injection.
# ---------------------------------------------------------------------------

_limiter = AuditEmitRateLimiter()


def get_rate_limiter() -> AuditEmitRateLimiter:
    """FastAPI dependency — returns the singleton rate limiter."""
    return _limiter
