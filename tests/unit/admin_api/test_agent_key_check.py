"""
Tests for the one shared agent-key check.

Source: openspec/changes/agent-principal-and-egress (task 2.1; spec
agent-principal, requirement "The key check is one function").
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from admin_api.api import internal

# Built at run time so no test file holds a token-shaped value whole.
API_KEY = "mk_" + "agent_" + "A" * 24

AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")

Verifier = Callable[[str, str], Awaitable[None]]


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    """The slice of a SQLAlchemy result the key check reads."""

    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row


class _RecordingSession:
    """Records every statement and answers the ``agents`` lookup by substring."""

    def __init__(self, row: Any = None) -> None:
        self._row = row
        self.statements: list[tuple[str, dict[str, Any]]] = []

    async def execute(
        self,
        statement: Any,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _Result:
        sql = " ".join(str(statement).split())
        self.statements.append((sql, dict(params or {})))
        if "from agents" in sql.lower():
            return _Result(self._row)
        return _Result()


async def _verify_ok(_stored_hash: str, _secret: str) -> None:
    return None


def _raise_with(exc: BaseException) -> Verifier:
    async def _raiser(_stored_hash: str, _secret: str) -> None:
        raise exc

    return _raiser


def _active_row(
    *, role: str = "publisher", expires_at: datetime | None = None
) -> SimpleNamespace:
    return SimpleNamespace(
        id=AGENT_ID,
        tenant_id=TENANT_ID,
        api_key_hash="$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        status="active",
        api_key_expires_at=expires_at,
        api_key_fingerprint="deadbeefdeadbeef",
        role=role,
    )


def _invalid_key_body() -> dict[str, Any]:
    return {
        "type": "https://mintkey.internal/errors/invalid-agent-key",
        "title": "Invalid agent key",
        "status": 401,
        "mintkey:code": "mintkey:invalid_agent_key",
    }


def _compact(sql: str) -> str:
    """Collapse whitespace so a reformatted statement still matches."""

    return re.sub(r"\s+", " ", sql).replace(", ", ",")


def _assert_first_two_statements(session: _RecordingSession) -> None:
    assert len(session.statements) >= 2, session.statements
    first = _compact(session.statements[0][0])
    second = session.statements[1][0]
    assert (
        "set_config('app.platform_admin_view','on',true)" in first
    ), session.statements[0][0]
    assert "from agents" in second.lower(), session.statements[1][0]


# ---------------------------------------------------------------------------
# C-9a0d1912 — the check returns the row or the answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-9a0d1912")
async def test_C_9a0d1912_valid_key_returns_the_row_and_none(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _active_row(role="publisher")
    session = _RecordingSession(row)
    monkeypatch.setattr(internal, "_verify_argon2", _verify_ok)

    found, response = await internal.check_agent_key(session, API_KEY)

    assert found is not None
    assert found is row
    assert found.id == AGENT_ID
    assert found.tenant_id == TENANT_ID
    assert found.status == "active"
    assert found.role == "publisher"
    assert response is None
    _assert_first_two_statements(session)


@pytest.mark.asyncio
@pytest.mark.l4("C-9a0d1912")
async def test_C_9a0d1912_unknown_key_returns_the_invalid_key_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _RecordingSession(None)
    monkeypatch.setattr(internal, "_verify_argon2", _verify_ok)

    found, response = await internal.check_agent_key(session, API_KEY)

    assert found is None
    assert response is not None
    assert response.status_code == 401
    assert json.loads(response.body) == _invalid_key_body()
    _assert_first_two_statements(session)


@pytest.mark.asyncio
@pytest.mark.l4("C-9a0d1912")
async def test_C_9a0d1912_expired_key_returns_the_expired_401(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    row = _active_row(expires_at=expires_at)
    session = _RecordingSession(row)
    monkeypatch.setattr(internal, "_verify_argon2", _verify_ok)

    found, response = await internal.check_agent_key(session, API_KEY)

    assert found is None
    assert response is not None
    assert response.status_code == 401
    body = json.loads(response.body)
    assert body["title"] == "API key expired"
    assert body["mintkey:code"] == "agent_api_key_expired"
    assert "title" in body
    assert "hint" in body
    assert body["hint"] == (
        f"This agent's API key expired on {expires_at.isoformat()}. "
        "Operator must rotate the key via the admin UI Rotate Key action."
    )
    _assert_first_two_statements(session)


@pytest.mark.asyncio
@pytest.mark.l4("C-9a0d1912")
async def test_C_9a0d1912_verify_failure_returns_the_503(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _RecordingSession(_active_row())
    monkeypatch.setattr(internal, "_verify_argon2", _raise_with(MemoryError()))

    found, response = await internal.check_agent_key(session, API_KEY)

    assert found is None
    assert response is not None
    assert response.status_code == 503
    assert json.loads(response.body) == {"mintkey:code": "mintkey:verify_unavailable"}
    _assert_first_two_statements(session)


# ---------------------------------------------------------------------------
# C-083b1a5a — the endpoint is unchanged
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-083b1a5a", "C-9a0d1912")
async def test_C_083b1a5a_C_9a0d1912_validate_agent_key_issues_no_statement_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _active_row(role="publisher")
    session = _RecordingSession(row)
    monkeypatch.setattr(internal, "_verify_argon2", _verify_ok)

    real_check = internal.check_agent_key
    calls: list[tuple[Any, str]] = []
    statements_before: list[int] = []

    async def _spy(
        check_session: Any, api_key: str
    ) -> tuple[Any, Any]:
        calls.append((check_session, api_key))
        statements_before.append(len(check_session.statements))
        return await real_check(check_session, api_key)

    monkeypatch.setattr(internal, "check_agent_key", _spy)

    response = await internal.validate_agent_key(
        internal.ValidateAgentKeyRequest(api_key=API_KEY), session
    )

    assert response is not None
    assert response.status_code == 200, response.body
    body = json.loads(response.body)
    assert body["agent_id"] == str(AGENT_ID)
    assert body["tenant_id"] == str(TENANT_ID)
    assert body["status"] == "active"
    assert body["role"] == "publisher"

    # The endpoint delegated, and it issued none of the statements itself:
    # the recording session was untouched when check_agent_key was entered.
    assert statements_before == [0], statements_before
    assert calls == [(session, API_KEY)], calls
    assert len(session.statements) == 2, session.statements
    _assert_first_two_statements(session)
