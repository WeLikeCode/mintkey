"""Token lifetime bounded by a grant's expiry.

Sources:
  - ``openspec/changes/grant-expiry/spec.md`` — A token never outlives its grant
  - ``openspec/changes/grant-expiry/design.md`` — D4
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Final

MAX_TOKEN_TTL_SECONDS: Final[int] = 600
MIN_TOKEN_TTL_SECONDS: Final[int] = 5


def grant_ttl_seconds(expires_at: object, now: datetime) -> int | None:
    """Return the token lifetime allowed by a grant's expiry.

    A missing or non-datetime expiry gives the default 600 s.  Otherwise the
    lifetime is the floor of the seconds until ``expires_at`` capped at 600 s;
    below 5 s nothing is left to issue, so the result is ``None``.  A naive
    datetime reads as UTC.
    """
    if not isinstance(expires_at, datetime):
        return MAX_TOKEN_TTL_SECONDS
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    ttl = math.floor((expires_at - now).total_seconds())
    if ttl < MIN_TOKEN_TTL_SECONDS:
        return None
    return min(ttl, MAX_TOKEN_TTL_SECONDS)
