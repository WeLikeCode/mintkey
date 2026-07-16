"""
Unit tests for _budget_period_bounds utility — design §3; T-BUD-2.5.

Covers:
  - Hourly: mid-hour returns (top of current hour, +1 hour).
  - Daily: mid-day returns (midnight, +24h).
  - Weekly: mid-week returns (Monday 00:00, +7 days).
  - Monthly: mid-month returns (1st 00:00, 1st of next month 00:00).
  - Edge cases:
    - February 28 non-leap year → period_end is March 1.
    - February 29 leap year → period_end is March 1.
    - December 15 → period_end is January 1 next year.
    - January 1 at midnight (exact boundary).
    - Monday at midnight (exact weekly boundary).

Source: design §3; T-BUD-2.5; requirements FR-4.
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from admin_api.api.permissions import _budget_period_bounds


# ---------------------------------------------------------------------------
# Hourly period
# ---------------------------------------------------------------------------


class TestHourlyPeriod:
    """Hourly period — start is top of current hour, end is +1 hour."""

    def test_mid_hour(self) -> None:
        now = datetime(2026, 6, 15, 14, 37, 22)
        start, end = _budget_period_bounds("hourly", now)
        assert start == datetime(2026, 6, 15, 14, 0, 0)
        assert end == datetime(2026, 6, 15, 15, 0, 0)

    def test_exact_top_of_hour(self) -> None:
        now = datetime(2026, 6, 15, 14, 0, 0)
        start, end = _budget_period_bounds("hourly", now)
        assert start == datetime(2026, 6, 15, 14, 0, 0)
        assert end == datetime(2026, 6, 15, 15, 0, 0)

    def test_one_second_before_next_hour(self) -> None:
        now = datetime(2026, 6, 15, 23, 59, 59)
        start, end = _budget_period_bounds("hourly", now)
        assert start == datetime(2026, 6, 15, 23, 0, 0)
        assert end == datetime(2026, 6, 16, 0, 0, 0)

    def test_microseconds_truncated(self) -> None:
        now = datetime(2026, 6, 15, 10, 30, 45, 123456)
        start, end = _budget_period_bounds("hourly", now)
        assert start == datetime(2026, 6, 15, 10, 0, 0)
        assert start.microsecond == 0
        assert end == datetime(2026, 6, 15, 11, 0, 0)


# ---------------------------------------------------------------------------
# Daily period
# ---------------------------------------------------------------------------


class TestDailyPeriod:
    """Daily period — start is midnight UTC, end is +24 hours."""

    def test_mid_day(self) -> None:
        now = datetime(2026, 6, 15, 14, 37, 22)
        start, end = _budget_period_bounds("daily", now)
        assert start == datetime(2026, 6, 15, 0, 0, 0)
        assert end == datetime(2026, 6, 16, 0, 0, 0)

    def test_exact_midnight(self) -> None:
        now = datetime(2026, 6, 15, 0, 0, 0)
        start, end = _budget_period_bounds("daily", now)
        assert start == datetime(2026, 6, 15, 0, 0, 0)
        assert end == datetime(2026, 6, 16, 0, 0, 0)

    def test_last_second_of_day(self) -> None:
        now = datetime(2026, 6, 15, 23, 59, 59)
        start, end = _budget_period_bounds("daily", now)
        assert start == datetime(2026, 6, 15, 0, 0, 0)
        assert end == datetime(2026, 6, 16, 0, 0, 0)

    def test_end_minus_start_is_24h(self) -> None:
        now = datetime(2026, 3, 10, 8, 0, 0)
        start, end = _budget_period_bounds("daily", now)
        assert end - start == timedelta(hours=24)


# ---------------------------------------------------------------------------
# Weekly period
# ---------------------------------------------------------------------------


class TestWeeklyPeriod:
    """Weekly period — start is Monday 00:00 UTC, end is +7 days."""

    def test_mid_week_wednesday(self) -> None:
        # 2026-06-17 is a Wednesday
        now = datetime(2026, 6, 17, 10, 30, 0)
        start, end = _budget_period_bounds("weekly", now)
        assert start == datetime(2026, 6, 15, 0, 0, 0)  # Monday
        assert end == datetime(2026, 6, 22, 0, 0, 0)  # next Monday
        assert start.weekday() == 0  # Monday

    def test_exact_monday_midnight(self) -> None:
        # 2026-06-15 is a Monday
        now = datetime(2026, 6, 15, 0, 0, 0)
        start, end = _budget_period_bounds("weekly", now)
        assert start == datetime(2026, 6, 15, 0, 0, 0)
        assert end == datetime(2026, 6, 22, 0, 0, 0)

    def test_sunday_late_night(self) -> None:
        # 2026-06-21 is a Sunday
        now = datetime(2026, 6, 21, 23, 59, 59)
        start, end = _budget_period_bounds("weekly", now)
        assert start == datetime(2026, 6, 15, 0, 0, 0)  # Monday before
        assert end == datetime(2026, 6, 22, 0, 0, 0)

    def test_end_minus_start_is_7_days(self) -> None:
        now = datetime(2026, 6, 18, 12, 0, 0)
        start, end = _budget_period_bounds("weekly", now)
        assert end - start == timedelta(days=7)

    def test_week_spanning_month_boundary(self) -> None:
        # 2026-06-29 is a Monday, week ends July 6
        now = datetime(2026, 7, 1, 10, 0, 0)  # Wednesday
        start, end = _budget_period_bounds("weekly", now)
        assert start == datetime(2026, 6, 29, 0, 0, 0)  # Monday Jun 29
        assert end == datetime(2026, 7, 6, 0, 0, 0)


# ---------------------------------------------------------------------------
# Monthly period
# ---------------------------------------------------------------------------


class TestMonthlyPeriod:
    """Monthly period — start is 1st 00:00 UTC, end is 1st of next month."""

    def test_mid_month(self) -> None:
        now = datetime(2026, 6, 15, 14, 37, 22)
        start, end = _budget_period_bounds("monthly", now)
        assert start == datetime(2026, 6, 1, 0, 0, 0)
        assert end == datetime(2026, 7, 1, 0, 0, 0)

    def test_first_of_month_midnight(self) -> None:
        now = datetime(2026, 6, 1, 0, 0, 0)
        start, end = _budget_period_bounds("monthly", now)
        assert start == datetime(2026, 6, 1, 0, 0, 0)
        assert end == datetime(2026, 7, 1, 0, 0, 0)

    def test_last_day_of_month(self) -> None:
        now = datetime(2026, 6, 30, 23, 59, 59)
        start, end = _budget_period_bounds("monthly", now)
        assert start == datetime(2026, 6, 1, 0, 0, 0)
        assert end == datetime(2026, 7, 1, 0, 0, 0)

    def test_february_non_leap_year(self) -> None:
        """Feb 28 in non-leap year → period_end is March 1."""
        now = datetime(2027, 2, 28, 12, 0, 0)  # 2027 is not a leap year
        start, end = _budget_period_bounds("monthly", now)
        assert start == datetime(2027, 2, 1, 0, 0, 0)
        assert end == datetime(2027, 3, 1, 0, 0, 0)

    def test_february_leap_year(self) -> None:
        """Feb 29 in leap year → period_end is March 1."""
        now = datetime(2028, 2, 29, 12, 0, 0)  # 2028 is a leap year
        start, end = _budget_period_bounds("monthly", now)
        assert start == datetime(2028, 2, 1, 0, 0, 0)
        assert end == datetime(2028, 3, 1, 0, 0, 0)

    def test_february_leap_year_duration(self) -> None:
        """Leap year February has 29 days between start and end."""
        now = datetime(2028, 2, 15, 0, 0, 0)
        start, end = _budget_period_bounds("monthly", now)
        assert end - start == timedelta(days=29)

    def test_february_non_leap_year_duration(self) -> None:
        """Non-leap year February has 28 days between start and end."""
        now = datetime(2027, 2, 15, 0, 0, 0)
        start, end = _budget_period_bounds("monthly", now)
        assert end - start == timedelta(days=28)

    def test_december_rolls_to_next_year(self) -> None:
        """December 15 → period_end is January 1 next year."""
        now = datetime(2026, 12, 15, 10, 0, 0)
        start, end = _budget_period_bounds("monthly", now)
        assert start == datetime(2026, 12, 1, 0, 0, 0)
        assert end == datetime(2027, 1, 1, 0, 0, 0)

    def test_january_31_day_month(self) -> None:
        """January (31 days) → end is Feb 1."""
        now = datetime(2026, 1, 20, 0, 0, 0)
        start, end = _budget_period_bounds("monthly", now)
        assert start == datetime(2026, 1, 1, 0, 0, 0)
        assert end == datetime(2026, 2, 1, 0, 0, 0)
        assert end - start == timedelta(days=31)


# ---------------------------------------------------------------------------
# Invalid period
# ---------------------------------------------------------------------------


class TestInvalidPeriod:
    """Unknown period values raise ValueError."""

    def test_unknown_period_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown budget period"):
            _budget_period_bounds("yearly", datetime(2026, 6, 15, 0, 0, 0))

    def test_empty_string_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown budget period"):
            _budget_period_bounds("", datetime(2026, 6, 15, 0, 0, 0))
