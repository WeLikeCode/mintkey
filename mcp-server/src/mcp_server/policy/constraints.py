"""
Constraint evaluation for MCP token issuance.

The MCP Server evaluates rate_limit and time_window constraints.
The proxy plugin evaluates request_path_prefix and source_ip_allowlist.

Source: Req 6 AC5, AC10; ADR-0016.4.
"""
from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime
from typing import Any, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo  # type: ignore[no-redef]


class RateLimiter:
    """Sliding-window rate limiter per (agent_id, service_id, action) key."""

    def __init__(self) -> None:
        self._buckets: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def check(self, key: str, requests_per_second: int, burst: int) -> bool:
        """Return True if allowed, False if rate limited."""
        now = time.time()
        window = burst / requests_per_second if requests_per_second > 0 else float(burst)
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = deque()
            bucket = self._buckets[key]
            cutoff = now - window
            while bucket and bucket[0] <= cutoff:
                bucket.popleft()
            if len(bucket) >= burst:
                return False
            bucket.append(now)
            return True


def evaluate_rate_limit(
    limiter: RateLimiter, key: str, constraint: dict[str, Any]
) -> tuple[bool, str]:
    """Return (allowed, reason_code)."""
    rps = constraint.get("requests_per_second", 10)
    burst = constraint.get("burst", 20)
    if not limiter.check(key, rps, burst):
        return False, "constraint_failed:rate_limit"
    return True, ""


def evaluate_time_window(
    constraint: dict[str, Any], now: Optional[datetime] = None
) -> tuple[bool, str]:
    """Return (allowed, reason_code). now is injectable for testing."""
    tz = ZoneInfo(constraint["timezone"])
    if now is None:
        local_now = datetime.now(tz)
    else:
        local_now = now.astimezone(tz)

    day_name = local_now.strftime("%a")  # "Mon", "Tue", etc.
    if day_name not in constraint.get("days", []):
        return False, "constraint_failed:time_window"

    current_time = local_now.strftime("%H:%M")
    start = constraint["start_local"]
    end = constraint["end_local"]
    if not (start <= current_time <= end):
        return False, "constraint_failed:time_window"

    return True, ""
