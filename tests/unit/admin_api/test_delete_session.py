"""
Unit tests: admin_api.auth.sessions.delete_session (task 1.1, operator-logout).

Source: operator-logout › delete_session removes a session row
  - C-c5131b3d  A session row is deleted
  - C-279c765d  No row to delete
  - C-52ed0cc6  A token that is not a UUID

The fake AsyncSessionLocal (patched at admin_api.db.session.AsyncSessionLocal,
which delete_session imports inside the function) records every statement and
its bound params, and answers with a fixed rowcount.
"""
from __future__ import annotations

from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest

from admin_api.auth.sessions import delete_session


class _FakeResult:
    """Answer of the fake session's execute(): rowcount + fetchone()."""

    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount

    def fetchone(self) -> None:
        return None


class _FakeTransaction:
    """Async context manager returned by the fake session's begin()."""

    def __init__(self, session: "_FakeSession") -> None:
        self._session = session

    async def __aenter__(self) -> "_FakeSession":
        return self._session

    async def __aexit__(self, *exc: Any) -> None:
        return None


class _FakeSession:
    """Records str(statement) and the params of every execute() call."""

    def __init__(self, rowcount: int) -> None:
        self.rowcount = rowcount
        self.statements: list[str] = []
        self.params: list[dict[str, Any] | None] = []
        self.begin_calls = 0

    def begin(self) -> _FakeTransaction:
        self.begin_calls += 1
        return _FakeTransaction(self)

    async def execute(
        self, statement: Any, params: dict[str, Any] | None = None
    ) -> _FakeResult:
        self.statements.append(str(statement))
        self.params.append(params)
        return _FakeResult(self.rowcount)


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

    def __init__(self, rowcount: int) -> None:
        self.calls = 0
        self.session = _FakeSession(rowcount)

    def __call__(self) -> _FakeSessionContext:
        self.calls += 1
        return _FakeSessionContext(self.session)


@pytest.mark.asyncio
@pytest.mark.l4("C-c5131b3d")
async def test_delete_session_deletes_row_and_returns_true() -> None:
    """One row deleted: the two set_config statements run first, then the
    DELETE by id with the token bound as ``token`` and no expires_at
    condition, in one transaction; the call returns True."""
    token = str(uuid4())
    local = _FakeSessionLocal(rowcount=1)

    with patch("admin_api.db.session.AsyncSessionLocal", local):
        result = await delete_session(token)

    assert result is True
    session = local.session
    assert session.begin_calls == 1
    assert len(session.statements) == 3
    assert "set_config" in session.statements[0]
    assert "app.current_tenant" in session.statements[0]
    assert "00000000-0000-0000-0000-000000000000" in session.statements[0]
    assert "set_config" in session.statements[1]
    assert "app.platform_admin_view" in session.statements[1]
    assert "'on'" in session.statements[1]
    delete_sql = session.statements[2]
    assert "DELETE FROM sessions" in delete_sql
    assert "CAST(:token AS uuid)" in delete_sql
    assert "expires_at" not in delete_sql
    assert session.params[2] == {"token": token}


@pytest.mark.asyncio
@pytest.mark.l4("C-279c765d", "C-52ed0cc6")
async def test_delete_session_returns_false_when_no_row() -> None:
    """Zero rows deleted: the same statements run (the RLS set_config pair,
    then the DELETE with the bound token) and the call returns False."""
    token = str(uuid4())
    local = _FakeSessionLocal(rowcount=0)

    with patch("admin_api.db.session.AsyncSessionLocal", local):
        result = await delete_session(token)

    assert result is False
    assert len(local.session.statements) == 3
    assert "DELETE FROM sessions" in local.session.statements[2]
    assert "CAST(:token AS uuid)" in local.session.statements[2]
    assert local.session.params[2] == {"token": token}


@pytest.mark.asyncio
@pytest.mark.l4("C-52ed0cc6")
async def test_delete_session_non_uuid_opens_no_database() -> None:
    """A non-UUID token returns False and opens no database session; a UUID
    token in the same test really deletes (guards against a zero-value
    stub that just returns False)."""
    local = _FakeSessionLocal(rowcount=1)

    with patch("admin_api.db.session.AsyncSessionLocal", local):
        result = await delete_session("not-a-uuid")

    assert result is False
    assert local.calls == 0
    assert local.session.statements == []

    token = str(uuid4())
    with patch("admin_api.db.session.AsyncSessionLocal", local):
        real = await delete_session(token)

    assert real is True
    assert "DELETE FROM sessions" in local.session.statements[2]
    assert local.session.params[2] == {"token": token}
