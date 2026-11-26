"""
Unit tests: the grant expiry rules and the agent grant cap.

Requirement: grant-expiry › The expiry rules and the cap have one implementation

  - the cap reader (`agent_grant_max_ttl_seconds`)
  - operator and agent rules (`check_grant_expiry`)
  - the expiry boundary (`is_expired`)

Sources:
  - `openspec/changes/grant-expiry/spec.md` — The expiry rules and the cap
    have one implementation
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
if str(ADMIN_API_SRC) not in sys.path:
    sys.path.insert(0, str(ADMIN_API_SRC))

from admin_api.services.grant_expiry import (  # noqa: E402
    GrantExpiryError,
    agent_grant_max_ttl_seconds,
    check_grant_expiry,
    is_expired,
)

CAP_ENV = "MINTKEY_AGENT_GRANT_MAX_TTL"

NOW = datetime(2026, 11, 25, 12, 0, tzinfo=timezone.utc)


def _assert_reason(
    expires_at: datetime | None, grantor_type: str, reason: str
) -> None:
    with pytest.raises(GrantExpiryError) as exc_info:
        check_grant_expiry(expires_at, grantor_type, NOW)
    assert exc_info.value.reason == reason


@pytest.mark.l4("C-3dca655e")
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        (None, 604_800),
        ("", 604_800),
        ("abc", 604_800),
        ("0", 604_800),
        ("-5", 604_800),
        ("3600", 3_600),
        ("604800", 604_800),
        ("99999999", 7_776_000),
    ],
)
def test_C_3dca655e_cap_reader(
    monkeypatch: pytest.MonkeyPatch, raw: str | None, expected: int
) -> None:
    if raw is None:
        monkeypatch.delenv(CAP_ENV, raising=False)
    else:
        monkeypatch.setenv(CAP_ENV, raw)

    assert agent_grant_max_ttl_seconds() == expected


@pytest.mark.l4("C-c0408375")
def test_C_c0408375_operator_and_agent_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The cap boundary cases assume the default 604800 s cap.
    monkeypatch.delenv(CAP_ENV, raising=False)

    # An operator may leave the expiry open or set it in the future.
    assert check_grant_expiry(None, "operator", NOW) is None
    assert check_grant_expiry(NOW + timedelta(hours=1), "operator", NOW) is None

    # A past expiry is refused for everyone.
    _assert_reason(NOW - timedelta(seconds=1), "operator", "expires_at_in_past")

    # An agent grantor must name an expiry.
    _assert_reason(None, "agent", "expires_at_required")

    # Within the cap (default 604800 s) an agent expiry is accepted, at
    # the cap's boundary included.
    assert check_grant_expiry(NOW + timedelta(days=1), "agent", NOW) is None
    assert check_grant_expiry(NOW + timedelta(seconds=604_800), "agent", NOW) is None
    _assert_reason(
        NOW + timedelta(seconds=604_801),
        "agent",
        "expires_at_too_far",
    )

    # A datetime without an offset is refused before anything else.
    _assert_reason(
        datetime(2030, 1, 1, 0, 0, 0), "operator", "expires_at_timezone_required"
    )


@pytest.mark.l4("C-a3ba81c6")
def test_C_a3ba81c6_expiry_boundary() -> None:
    assert is_expired(NOW, NOW) is True
    assert is_expired(NOW - timedelta(seconds=1), NOW) is True
    assert is_expired(NOW + timedelta(seconds=1), NOW) is False
    assert is_expired(None, NOW) is False
