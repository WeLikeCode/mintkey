"""
Unit tests: POST /v1/auth/logout deletes the server-side session (task 3.1,
operator-logout).

Source: operator-logout › Logout deletes the server-side session
  - C-25c3e029  The old cookie is refused after logout inside the cache window
  - C-33f55440  Logout clears both cookies
  - C-6f9d4126  Logout without a session cookie
  - C-8f0418a0  Logout twice with the same cookie
  - C-d633f116  Concurrent logouts with the same cookie
  - C-7c224daa  A cookie that is not a UUID
  - C-a965c3a1  Logout of an expired session

An in-memory set stands in for the sessions table: ``create_session`` adds the
token, ``validate_session`` answers from the set and ``delete_session`` removes
it. The identity query of ``_whoami_lookup`` runs against a fake
``AsyncSessionLocal`` (patched at ``admin_api.db.session``, which the lookup
imports inside the function). ``delete_session`` is patched at the name
``auth.py`` imports (``create=True`` while the red test is written before the
import exists).
"""
from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import argon2
import pytest
from httpx import ASGITransport, AsyncClient

from admin_api.api import auth

_PH = argon2.PasswordHasher()
_PASSWORD = "correct-horse-battery-staple"
_PASSWORD_HASH = _PH.hash(_PASSWORD)


class _FakeResult:
    """Answer of the fake session's execute() for the whoami identity query."""

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


def _make_operator() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid4(),
        tenant_id=uuid4(),
        email="op@example.test",
        internal_password_hash=_PASSWORD_HASH,
        is_platform_admin=True,
        status="active",
    )


def _set_cookies(response: Any) -> dict[str, str]:
    """Map cookie name → full Set-Cookie header of the response."""
    headers: dict[str, str] = {}
    for header in response.headers.get_list("set-cookie"):
        name = header.split("=", 1)[0].strip()
        headers[name] = header
    return headers


def _assert_clears_both_cookies(response: Any) -> None:
    headers = _set_cookies(response)
    for name in ("mintkey_session", "csrf_token"):
        assert name in headers, headers
        assert "Max-Age=0" in headers[name], headers[name]
        assert "Path=/" in headers[name], headers[name]


@pytest.fixture(autouse=True)
def _clear_whoami_cache() -> Any:
    auth._WHOAMI_CACHE.clear()
    yield
    auth._WHOAMI_CACHE.clear()


@pytest.fixture()
def app() -> Any:
    from admin_api.main import create_app

    return create_app()


@pytest.mark.asyncio
@pytest.mark.l4("C-25c3e029")
async def test_old_cookie_refused_after_logout_inside_cache_window(app: Any) -> None:
    """Login, whoami caches the token, logout evicts and deletes it, and the
    replayed old cookie is answered 401 with no wait in between."""
    token = str(uuid4())
    operator = _make_operator()
    store = {token}
    ctx = SimpleNamespace(operator_id=operator.id, tenant_id=operator.tenant_id)
    row = (operator.id, operator.tenant_id, operator.email, True, "internal")

    async def create(
        _operator_id: Any, _tenant_id: Any, auth_method: str = "oidc"
    ) -> str:
        store.add(token)
        return token

    async def validate(value: str) -> Any:
        return ctx if value in store else None

    async def delete(value: str) -> bool:
        if value in store:
            store.remove(value)
            return True
        return False

    with (
        patch("admin_api.api.auth.create_session", new=create),
        patch("admin_api.api.auth.validate_session", new=validate),
        patch("admin_api.api.auth.delete_session", new=delete, create=True),
        patch(
            "admin_api.auth.internal.fetch_operator",
            new=AsyncMock(return_value=operator),
        ),
        patch("admin_api.auth.internal.record_failed_attempt", new=AsyncMock()),
        patch("admin_api.auth.internal.clear_failed_attempts", new=AsyncMock()),
        patch("admin_api.db.session.AsyncSessionLocal", _FakeSessionLocal(row)),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            login = await client.post(
                "/v1/auth/internal-login",
                json={"email": operator.email, "password": _PASSWORD},
            )
            assert login.status_code == 200
            assert login.cookies.get("mintkey_session") == token

            first = await client.get("/v1/auth/whoami")
            assert first.status_code == 200
            assert token in auth._WHOAMI_CACHE

            out = await client.post("/v1/auth/logout")
            assert out.status_code == 204
            assert token not in store
            assert token not in auth._WHOAMI_CACHE

            replay = await client.get(
                "/v1/auth/whoami", cookies={"mintkey_session": token}
            )
            assert replay.status_code == 401
            assert replay.json()["mintkey:code"] == "unauthenticated"


@pytest.mark.asyncio
@pytest.mark.l4("C-33f55440")
async def test_logout_clears_both_cookies(app: Any) -> None:
    """A successful logout answers 204 and sends a clearing Set-Cookie for
    mintkey_session and for csrf_token (Max-Age=0, Path=/)."""
    token = str(uuid4())

    with patch(
        "admin_api.api.auth.delete_session",
        new=AsyncMock(return_value=True),
        create=True,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/auth/logout", cookies={"mintkey_session": token}
            )

    assert response.status_code == 204
    _assert_clears_both_cookies(response)


@pytest.mark.asyncio
@pytest.mark.l4("C-6f9d4126")
async def test_logout_without_session_cookie_does_not_delete_or_evict(app: Any) -> None:
    """No mintkey_session cookie: 204 with both clearing headers, no
    delete_session call and the whoami cache is unchanged."""
    auth._WHOAMI_CACHE["token-b"] = ({"operator_id": "b"}, 0.0)
    delete = AsyncMock(return_value=False)

    with patch(
        "admin_api.api.auth.delete_session", new=delete, create=True
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/v1/auth/logout")

    assert response.status_code == 204
    _assert_clears_both_cookies(response)
    delete.assert_not_awaited()
    assert auth._WHOAMI_CACHE["token-b"][0] == {"operator_id": "b"}
    assert len(auth._WHOAMI_CACHE) == 1


@pytest.mark.asyncio
@pytest.mark.l4("C-8f0418a0")
async def test_logout_twice_with_same_cookie(app: Any) -> None:
    """Two sequential logouts with the same cookie both answer 204, neither
    raises, and the session store no longer holds the token."""
    token = str(uuid4())
    store = {token}

    async def delete(value: str) -> bool:
        if value in store:
            store.remove(value)
            return True
        return False

    with patch("admin_api.api.auth.delete_session", new=delete, create=True):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first = await client.post(
                "/v1/auth/logout", cookies={"mintkey_session": token}
            )
            second = await client.post(
                "/v1/auth/logout", cookies={"mintkey_session": token}
            )

    assert first.status_code == 204
    assert second.status_code == 204
    assert token not in store
    assert token not in auth._WHOAMI_CACHE


@pytest.mark.asyncio
@pytest.mark.l4("C-d633f116")
async def test_concurrent_logouts_with_same_cookie(app: Any) -> None:
    """Two concurrent logouts with the same cookie both answer 204, neither
    raises, and the store/cache no longer hold the token."""
    import asyncio

    token = str(uuid4())
    store = {token}
    auth._WHOAMI_CACHE[token] = ({"operator_id": "op"}, 0.0)

    async def delete(value: str) -> bool:
        if value in store:
            store.remove(value)
            return True
        return False

    with patch("admin_api.api.auth.delete_session", new=delete, create=True):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            first, second = await asyncio.gather(
                client.post(
                    "/v1/auth/logout", cookies={"mintkey_session": token}
                ),
                client.post(
                    "/v1/auth/logout", cookies={"mintkey_session": token}
                ),
            )

    assert first.status_code == 204
    assert second.status_code == 204
    assert token not in store
    assert token not in auth._WHOAMI_CACHE


@pytest.mark.asyncio
@pytest.mark.l4("C-7c224daa")
async def test_logout_with_non_uuid_cookie_clears_both_cookies(app: Any) -> None:
    """A mintkey_session value that is not a UUID still answers 204 with both
    clearing headers."""
    with patch(
        "admin_api.api.auth.delete_session",
        new=AsyncMock(return_value=False),
        create=True,
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/auth/logout",
                cookies={"mintkey_session": "not-a-uuid"},
            )

    assert response.status_code == 204
    _assert_clears_both_cookies(response)


@pytest.mark.asyncio
@pytest.mark.l4("C-a965c3a1")
async def test_logout_of_expired_session_deletes_by_token(app: Any) -> None:
    """A cookie whose row is past expires_at is still deleted by its id:
    logout calls delete_session with the token and answers 204."""
    token = str(uuid4())
    store = {token}

    async def delete(value: str) -> bool:
        if value in store:
            store.remove(value)
            return True
        return False

    with patch("admin_api.api.auth.delete_session", new=delete, create=True):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/v1/auth/logout", cookies={"mintkey_session": token}
            )

    assert response.status_code == 204
    assert token not in store
    assert token not in auth._WHOAMI_CACHE
