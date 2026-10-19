"""
Unit tests: the whoami cache forgets a logged-out token (task 2.1,
operator-logout).

Source: operator-logout › The whoami cache forgets a logged-out token
  - C-7700945c  Eviction removes only that token
  - C-fe62049f  Evicting a token that is not cached
  - C-4bb6f563  A lookup in flight during logout is not cached

``_evict_whoami`` lives in admin_api.api.auth and the lookup's identity query
runs against a fake AsyncSessionLocal (patched at admin_api.db.session,
which _whoami_lookup imports inside the function).
"""
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from admin_api.api import auth


class _FakeResult:
    """Answer of the fake session's execute()."""

    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._row


class _FakeTransaction:
    """Async context manager returned by the fake session's begin()."""

    def __init__(self, session: "_FakeSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_FakeSession":
        return self._session

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakeSession:
    """Answers every execute() with the same identity row."""

    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self._row = row

    def begin(self) -> _FakeTransaction:
        return _FakeTransaction(self)

    async def execute(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> _FakeResult:
        return _FakeResult(self._row)


class _FakeSessionContext:
    """Async context manager yielded by calling the fake session factory."""

    def __init__(self, session: "_FakeSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_FakeSession":
        return self._session

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakeSessionLocal:
    """Callable standing in for admin_api.db.session.AsyncSessionLocal."""

    def __init__(self, row: tuple[Any, ...] | None) -> None:
        self.session = _FakeSession(row)

    def __call__(self) -> _FakeSessionContext:
        return _FakeSessionContext(self.session)


@pytest.fixture()
def app() -> Any:
    from admin_api.main import create_app

    return create_app()


@pytest.mark.l4("C-7700945c")
def test_evicting_cached_token_removes_only_it() -> None:
    """Evicting A removes A, keeps B's fresh entry, and moves the counter."""
    now = time.monotonic()
    auth._WHOAMI_CACHE.clear()
    auth._WHOAMI_CACHE["token-a"] = ({"operator_id": "a"}, now)
    auth._WHOAMI_CACHE["token-b"] = ({"operator_id": "b"}, now)
    before = getattr(auth, "_WHOAMI_EVICTIONS", 0)

    auth._evict_whoami("token-a")

    assert "token-a" not in auth._WHOAMI_CACHE
    assert auth._WHOAMI_CACHE["token-b"][0] == {"operator_id": "b"}
    assert getattr(auth, "_WHOAMI_EVICTIONS", 0) == before + 1


@pytest.mark.l4("C-fe62049f")
def test_evicting_uncached_token_keeps_other_entries() -> None:
    """An uncached token raises nothing, keeps B's entry, and still moves the
    counter, so a no-op zero-value stub cannot pass."""
    now = time.monotonic()
    auth._WHOAMI_CACHE.clear()
    auth._WHOAMI_CACHE["token-b"] = ({"operator_id": "b"}, now)
    before = getattr(auth, "_WHOAMI_EVICTIONS", 0)

    auth._evict_whoami("token-missing")

    assert auth._WHOAMI_CACHE["token-b"][0] == {"operator_id": "b"}
    assert len(auth._WHOAMI_CACHE) == 1
    assert getattr(auth, "_WHOAMI_EVICTIONS", 0) == before + 1


@pytest.mark.asyncio
@pytest.mark.l4("C-4bb6f563", "C-fe62049f")
async def test_lookup_in_flight_during_logout_is_not_cached(app: Any) -> None:
    """Eviction after session validation but before the lookup stores its
    result: the request still answers 200 and the token is not cached."""
    token = "11111111-1111-1111-1111-111111111111"
    operator_id = uuid4()
    tenant_id = uuid4()
    row = (operator_id, tenant_id, "op@example.test", True, "internal")
    ctx = SimpleNamespace(operator_id=operator_id, tenant_id=tenant_id)

    auth._WHOAMI_CACHE.clear()

    async def validate_then_evict(session_token: str) -> Any:
        assert session_token == token
        auth._evict_whoami(session_token)
        return ctx

    with (
        patch(
            "admin_api.api.auth.validate_session",
            new=validate_then_evict,
        ),
        patch(
            "admin_api.db.session.AsyncSessionLocal",
            _FakeSessionLocal(row),
        ),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get(
                "/v1/auth/whoami", cookies={"mintkey_session": token}
            )

    assert response.status_code == 200
    assert response.json()["operator"]["email"] == "op@example.test"
    assert token not in auth._WHOAMI_CACHE
