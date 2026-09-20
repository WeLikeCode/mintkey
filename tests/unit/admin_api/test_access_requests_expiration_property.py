"""
Property-based test (Hypothesis) for the agent-access-requests expiration
boundary.

Feature: agent-access-requests — Task 5.8.

Property (statement copied verbatim from
``.kiro/specs/agent-access-requests/design.md`` §Correctness Properties):

  - Property 9 — Expiration boundary is exact and 30 days
                 (Validates: Requirements 9.1, 9.2, 9.3)

This exercises the three PURE, DB-free helpers in
``admin_api.services.access_requests``:
  - ``compute_expires_at(created_at)``  → created_at + 30d, UTC-normalized
  - ``is_elapsed(expires_at, now=...)`` → inclusive ``now >= expires_at``
  - ``effective_status(status, expires_at)`` → lazy pending→expired flip

Testing approach (mirrors the repo's established property patterns):
  - Each property runs a MINIMUM of 100 Hypothesis iterations
    (``@settings(max_examples=...)`` with ``>= 100``).
  - This is an ADD-ONLY file. It modifies neither the service code nor any
    existing test (Req 14.2).
  - These helpers are pure — no DB, no I/O, no testcontainers — so the file
    runs fast and independently of Docker.
  - Generators drive ``created_at`` datetimes (naive and tz-aware, spanning a
    wide time range) and ``now`` offsets that straddle the boundary:
    just-before, exactly-at, just-after, and far on each side.

Source: .kiro/specs/agent-access-requests/design.md §Correctness Properties,
        §Expiration Mechanism; requirements.md Req 9.1, 9.2, 9.3;
        apps/admin-api/src/admin_api/services/access_requests.py
        (compute_expires_at / is_elapsed / effective_status / DEFAULT_REQUEST_TTL).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from hypothesis import given, settings
from hypothesis import strategies as st

from admin_api.services.access_requests import (
    DEFAULT_REQUEST_TTL,
    compute_expires_at,
    effective_status,
    is_elapsed,
)

# Minimum iterations per property (Task 5.8 requirement: >= 100).
_MAX_EXAMPLES = 200
_PURE_SETTINGS = settings(max_examples=_MAX_EXAMPLES, deadline=None)

# DEFAULT_REQUEST_TTL is documented as exactly 30 days (Req 9.1); assert the
# constant the helpers build on has that value so the property's premise holds.
_THIRTY_DAYS = timedelta(days=30)


# ``created_at`` datetimes across a wide range so the +30d arithmetic and the
# boundary comparison are exercised at many absolute instants. We generate both
# naive (treated as UTC) and tz-aware values; a tz-aware value carries a
# random whole-minute UTC offset so the UTC-normalization path is covered.
_naive_dt = st.datetimes(
    min_value=datetime(2000, 1, 1, 0, 0, 0),
    max_value=datetime(2100, 1, 1, 0, 0, 0),
)


@st.composite
def _created_at(draw: st.DrawFn) -> datetime:
    """A created_at value: naive (UTC-assumed) or aware with an arbitrary offset."""
    base = draw(_naive_dt)
    make_aware = draw(st.booleans())
    if not make_aware:
        return base
    # Offsets from -14h..+14h in whole minutes (covers all real-world zones).
    offset_minutes = draw(st.integers(min_value=-14 * 60, max_value=14 * 60))
    return base.replace(tzinfo=timezone(timedelta(minutes=offset_minutes)))


# ``now`` offsets relative to ``expires_at`` that straddle the boundary:
#   - exactly zero (at the boundary — must read as elapsed/expired)
#   - tiny amounts just-before (must NOT be elapsed) and just-after (elapsed)
#   - far on each side
_boundary_offsets = st.one_of(
    st.just(timedelta(0)),  # exactly at expires_at
    st.timedeltas(  # just before / just after (sub-second and up to ~a day)
        min_value=timedelta(microseconds=-86_400_000_000),
        max_value=timedelta(microseconds=86_400_000_000),
    ),
    st.sampled_from(
        [
            timedelta(microseconds=-1),  # 1 microsecond before boundary
            timedelta(microseconds=1),  # 1 microsecond after boundary
            timedelta(days=-3650),  # far before
            timedelta(days=3650),  # far after
        ]
    ),
)

# For the ``effective_status`` wall-clock properties we position ``expires_at``
# relative to the REAL ``datetime.now()`` that the helper reads internally.
# Sub-second offsets would race that internal clock read (a test artifact, not
# a code behaviour), so those two properties use a safe margin (>= 1s each side,
# plus far values) while still exercising just-before / just-after / far. The
# exact microsecond-inclusive boundary is proven separately, deterministically,
# by the ``is_elapsed(..., now=...)`` properties above (which pass an explicit
# ``now`` and are immune to wall-clock drift).
_wallclock_offsets = st.one_of(
    st.timedeltas(
        min_value=timedelta(seconds=1),
        max_value=timedelta(days=3650),
    ),  # strictly-after margin (expires_at in the past)
    st.timedeltas(
        min_value=timedelta(days=-3650),
        max_value=timedelta(seconds=-1),
    ),  # strictly-before margin (expires_at in the future)
)


def _as_utc(value: datetime) -> datetime:
    """Normalize any datetime to an explicit-UTC value, matching the helpers."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


# ===========================================================================
# Property 9 — expiration boundary is exact and 30 days (pure; always runs)
# ===========================================================================
# Feature: agent-access-requests, Property 9: Expiration boundary is exact and
# 30 days — expires_at == created_at + 30 days exactly; a pending request is
# expired iff now >= expires_at, and remains pending while now < expires_at
# (boundary inclusive at expires_at).


class TestProperty9ExpirationBoundary:
    """Property 9 — compute_expires_at is +30d exactly; is_elapsed / effective_status
    flip precisely at the (inclusive) expires_at boundary."""

    def test_default_ttl_is_exactly_thirty_days(self) -> None:
        """The Default_Request_TTL constant the helpers use is exactly 30 days."""
        assert DEFAULT_REQUEST_TTL == _THIRTY_DAYS

    @_PURE_SETTINGS
    @given(created_at=_created_at())
    def test_expires_at_is_created_at_plus_30_days_exactly(
        self, created_at: datetime
    ) -> None:
        """compute_expires_at gives exactly created_at + 30 days (UTC-normalized)."""
        expires_at = compute_expires_at(created_at)
        # Result is always UTC-aware.
        assert expires_at.tzinfo is not None
        assert expires_at.utcoffset() == timedelta(0)
        # Exact +30d relative to the UTC-normalized created_at.
        assert expires_at == _as_utc(created_at) + _THIRTY_DAYS

    @_PURE_SETTINGS
    @given(created_at=_created_at(), offset=_boundary_offsets)
    def test_is_elapsed_is_inclusive_at_the_boundary(
        self, created_at: datetime, offset: timedelta
    ) -> None:
        """is_elapsed is False strictly before expires_at, True at and after it."""
        expires_at = compute_expires_at(created_at)
        now = expires_at + offset

        elapsed = is_elapsed(expires_at, now=now)

        if offset < timedelta(0):
            # Strictly before the boundary → not elapsed.
            assert elapsed is False
        else:
            # offset == 0 (exactly at) or > 0 (after) → elapsed (inclusive).
            assert elapsed is True

    @_PURE_SETTINGS
    @given(created_at=_created_at(), offset=_boundary_offsets)
    def test_is_elapsed_matches_the_raw_utc_comparison(
        self, created_at: datetime, offset: timedelta
    ) -> None:
        """is_elapsed(expires_at, now) is exactly (now_utc >= expires_at_utc)."""
        expires_at = compute_expires_at(created_at)
        now = expires_at + offset
        assert is_elapsed(expires_at, now=now) == (_as_utc(now) >= expires_at)

    @_PURE_SETTINGS
    @given(offset=_wallclock_offsets)
    def test_effective_status_flips_pending_at_the_boundary(
        self, offset: timedelta
    ) -> None:
        """effective_status flips pending→expired around the boundary.

        ``effective_status`` has no ``now`` parameter — it compares against the
        real current time — so we position ``expires_at`` at a safe margin
        (>= 1s) on either side of ``now()`` and assert the flip. The exact
        microsecond-inclusive boundary is proven deterministically by the
        ``is_elapsed(..., now=...)`` properties above; here we confirm the
        wall-clock-driven wrapper agrees on either side.
        """
        now = datetime.now(timezone.utc)
        # expires_at = now - offset:
        #   offset >= +1s → expires_at strictly in the past  → expired
        #   offset <= -1s → expires_at strictly in the future → pending
        expires_at = now - offset

        status = effective_status("pending", expires_at)

        if offset < timedelta(0):
            # expires_at is in the future → still pending.
            assert status == "pending"
        else:
            # expires_at is in the past → expired.
            assert status == "expired"

    @_PURE_SETTINGS
    @given(
        offset=_wallclock_offsets,
        status=st.sampled_from(["approved", "rejected", "expired", "cancelled"]),
    )
    def test_effective_status_leaves_non_pending_unchanged(
        self, offset: timedelta, status: str
    ) -> None:
        """A non-pending status is returned unchanged regardless of the boundary."""
        now = datetime.now(timezone.utc)
        expires_at = now - offset
        assert effective_status(status, expires_at) == status
