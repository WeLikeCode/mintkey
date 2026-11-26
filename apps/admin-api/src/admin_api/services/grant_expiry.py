"""The expiry rules and the agent grant cap.

One implementation of "may this grant carry this expiry, and has it expired?"
shared by every caller that creates or reads a permission grant.

Sources:
  - ``openspec/changes/grant-expiry/spec.md`` — The expiry rules and the cap
    have one implementation
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta
from typing import Final

AGENT_GRANT_MAX_TTL_DEFAULT_SECONDS: Final[int] = 604_800
AGENT_GRANT_MAX_TTL_CEILING_SECONDS: Final[int] = 7_776_000
GRANTOR_OPERATOR: Final[str] = "operator"
GRANTOR_AGENT: Final[str] = "agent"

_ENV_VAR: Final[str] = "MINTKEY_AGENT_GRANT_MAX_TTL"

# The reasons a grant's expiry can be refused.
REASON_EXPIRES_AT_TIMEZONE_REQUIRED: Final[str] = "expires_at_timezone_required"
REASON_EXPIRES_AT_IN_PAST: Final[str] = "expires_at_in_past"
REASON_EXPIRES_AT_REQUIRED: Final[str] = "expires_at_required"
REASON_EXPIRES_AT_TOO_FAR: Final[str] = "expires_at_too_far"


class GrantExpiryError(Exception):
    """A grant's expiry violates one of the rules; ``reason`` names which."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def agent_grant_max_ttl_seconds() -> int:
    """Read ``MINTKEY_AGENT_GRANT_MAX_TTL`` as decimal seconds.

    Unset, empty, not a decimal integer or below 1 gives the default (7 days);
    a value above the ceiling gives the ceiling (90 days).
    """
    raw = os.getenv(_ENV_VAR, "")
    try:
        seconds = int(raw)
    except (TypeError, ValueError):
        return AGENT_GRANT_MAX_TTL_DEFAULT_SECONDS
    if seconds < 1:
        return AGENT_GRANT_MAX_TTL_DEFAULT_SECONDS
    if seconds > AGENT_GRANT_MAX_TTL_CEILING_SECONDS:
        return AGENT_GRANT_MAX_TTL_CEILING_SECONDS
    return seconds


def is_expired(expires_at: datetime | None, now: datetime) -> bool:
    """True exactly when ``expires_at`` is set and is not after ``now``."""
    return expires_at is not None and expires_at <= now


def check_grant_expiry(
    expires_at: datetime | None, grantor_type: str, now: datetime
) -> None:
    """Raise :class:`GrantExpiryError` unless the expiry is allowed.

    A datetime without an offset is refused first, then a value not after
    ``now``; an agent grantor must name an expiry within the agent cap. An
    operator may leave the expiry open or set any later time.
    """
    if expires_at is not None:
        if expires_at.utcoffset() is None:
            raise GrantExpiryError(REASON_EXPIRES_AT_TIMEZONE_REQUIRED)
        if expires_at <= now:
            raise GrantExpiryError(REASON_EXPIRES_AT_IN_PAST)

    if grantor_type == GRANTOR_AGENT:
        if expires_at is None:
            raise GrantExpiryError(REASON_EXPIRES_AT_REQUIRED)
        cap = timedelta(seconds=agent_grant_max_ttl_seconds())
        if expires_at > now + cap:
            raise GrantExpiryError(REASON_EXPIRES_AT_TOO_FAR)
