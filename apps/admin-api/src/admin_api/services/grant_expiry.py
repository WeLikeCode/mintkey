"""The expiry rules and the agent grant cap (stubs for the red step)."""

from __future__ import annotations

from datetime import datetime


class GrantExpiryError(Exception):
    pass


def agent_grant_max_ttl_seconds() -> int:
    raise NotImplementedError


def is_expired(expires_at: datetime | None, now: datetime) -> bool:
    raise NotImplementedError


def check_grant_expiry(
    expires_at: datetime | None, grantor_type: str, now: datetime
) -> None:
    raise NotImplementedError
