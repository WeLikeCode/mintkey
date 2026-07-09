"""
Unit tests for admin_api.auth.oidc_state.FakeOidcStateRepository.

These tests exercise the hermetic in-memory fake (the unit CI lane has no
Postgres). The fake mirrors OidcStateRepository's semantics exactly, so
these assertions double as a spec for the real Postgres-backed repository.

Tests:
  test_put_then_pop_returns_stored_values      — round trip returns the
                                                   correct code_verifier +
                                                   redirect_uri
  test_cross_replica_pop_succeeds              — put via one repository
                                                   instance, pop via a
                                                   SECOND instance sharing
                                                   the backing dict succeeds
                                                   (the multi-replica fix)
  test_expired_state_pop_returns_none          — negative TTL → pop returns
                                                   None
  test_single_use_second_pop_returns_none      — first pop consumes the
                                                   state; second pop of the
                                                   same state returns None
  test_opportunistic_gc_on_put                 — an expired entry is
                                                   evicted from the backing
                                                   store when a fresh entry
                                                   is put()

Source: fix/oidc-shared-pkce-state; admin_api/auth/oidc_state.py.
"""
from __future__ import annotations

import pytest

from admin_api.auth.oidc_state import FakeOidcStateRepository

_STATE = "test-state-abc123"
_CODE_VERIFIER = "test-code-verifier-xyz"
_REDIRECT_URI = "https://admin-api.example.com/v1/auth/oidc/callback"


@pytest.mark.asyncio
async def test_put_then_pop_returns_stored_values() -> None:
    """put() then pop() returns the correct code_verifier + redirect_uri."""
    store: dict[str, tuple[str, str, float]] = {}
    repo = FakeOidcStateRepository(store)

    await repo.put(_STATE, _CODE_VERIFIER, _REDIRECT_URI, ttl_seconds=600)
    result = await repo.pop(_STATE)

    assert result is not None
    assert result["code_verifier"] == _CODE_VERIFIER
    assert result["redirect_uri"] == _REDIRECT_URI


@pytest.mark.asyncio
async def test_cross_replica_pop_succeeds() -> None:
    """Put via one repository instance, pop via a second sharing the same
    backing dict succeeds — this is the core multi-replica fix assertion.
    Simulates /login landing on pod A and /callback landing on pod B.
    """
    shared_store: dict[str, tuple[str, str, float]] = {}
    repo_pod_a = FakeOidcStateRepository(shared_store)
    repo_pod_b = FakeOidcStateRepository(shared_store)

    await repo_pod_a.put(_STATE, _CODE_VERIFIER, _REDIRECT_URI, ttl_seconds=600)
    result = await repo_pod_b.pop(_STATE)

    assert result is not None
    assert result["code_verifier"] == _CODE_VERIFIER
    assert result["redirect_uri"] == _REDIRECT_URI


@pytest.mark.asyncio
async def test_expired_state_pop_returns_none() -> None:
    """A state stored with a negative (already-expired) TTL is not returned
    by pop() — unknown and expired states both yield None so the caller
    treats them identically (state_mismatch), never a 500.
    """
    store: dict[str, tuple[str, str, float]] = {}
    repo = FakeOidcStateRepository(store)

    await repo.put(_STATE, _CODE_VERIFIER, _REDIRECT_URI, ttl_seconds=-1)
    result = await repo.pop(_STATE)

    assert result is None


@pytest.mark.asyncio
async def test_single_use_second_pop_returns_none() -> None:
    """First pop() consumes the state; a second pop() of the same state
    returns None (single-use)."""
    store: dict[str, tuple[str, str, float]] = {}
    repo = FakeOidcStateRepository(store)

    await repo.put(_STATE, _CODE_VERIFIER, _REDIRECT_URI, ttl_seconds=600)

    first = await repo.pop(_STATE)
    second = await repo.pop(_STATE)

    assert first is not None
    assert second is None


@pytest.mark.asyncio
async def test_opportunistic_gc_on_put() -> None:
    """put() opportunistically GCs already-expired entries: an expired
    entry is gone from the backing store once a fresh entry is put()."""
    store: dict[str, tuple[str, str, float]] = {}
    repo = FakeOidcStateRepository(store)

    expired_state = "expired-state"
    await repo.put(expired_state, _CODE_VERIFIER, _REDIRECT_URI, ttl_seconds=-1)
    assert expired_state in store  # sanity: the expired row was written

    await repo.put(_STATE, _CODE_VERIFIER, _REDIRECT_URI, ttl_seconds=600)

    assert expired_state not in store, (
        "opportunistic GC on put() must evict already-expired rows"
    )
    assert _STATE in store
