"""Token lifetime bounded by a grant's expiry (stubs for the red step).

Sources:
  - ``openspec/changes/grant-expiry/spec.md`` — A token never outlives its grant
"""

from __future__ import annotations

from datetime import datetime


def grant_ttl_seconds(expires_at: object, now: datetime) -> int | None:
    raise NotImplementedError
