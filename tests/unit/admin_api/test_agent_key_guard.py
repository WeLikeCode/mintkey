"""The agent routes' own bounded key-check capacity (feedback FB-001).

Criterion C-c2386573: a burst of well-formed but unknown ``mk_agent_`` keys on
``/v1/agent/`` must not delay ``/v1/internal/validate-agent-key``.  The agent
routes verify keys with a bounded capacity of their own; a request that finds
that capacity full answers ``503 mintkey:auth_unavailable`` at once; and a
bearer that is not ``mk_agent_`` followed by the exact length and alphabet of
a real key answers ``401 mintkey:auth_required`` without a password-hash
verification.

Source: openspec/changes/agent-service-routes-fix-1 — Feedback FB-001.
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from admin_api.api import internal  # noqa: E402
from admin_api.auth import agent_key_guard, agent_principal  # noqa: E402
from admin_api.db.deps import get_db_session  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")

SERVICES_PATH = "/v1/agent/services"
AUTH_REQUIRED_BODY = {
    "code": "mintkey:auth_required",
    "title": "Agent key required",
}


# ---------------------------------------------------------------------------
# Keys are built at run time so no test file holds a token-shaped value whole.
# ---------------------------------------------------------------------------


def _real_shaped_key() -> str:
    """A key with the exact shape of a real agent key: prefix + 52 chars."""
    return "mk_" + "agent_" + "A" * 52


def _wrong_shaped_key(case: str) -> str:
    """Build one bearer that is not the exact shape of a real key."""
    if case == "short":
        return "mk_" + "agent_" + "A" * 51
    if case == "long":
        return "mk_" + "agent_" + "A" * 53
    if case == "bad_alphabet":
        return "mk_" + "agent_" + "U" * 52
    if case == "lowercase":
        return "mk_" + "agent_" + "a" * 52
    if case == "empty":
        return "mk_" + "agent_"
    if case == "no_prefix":
        return "not_an_agent_key"
    raise AssertionError(case)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    """The slice of a SQLAlchemy result these routes read."""

    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row

    def fetchall(self) -> list[Any]:
        return [] if self._row is None else [self._row]


class _RecordingSession:
    """An async-context-manager session recording statements and commits."""

    def __init__(self, *, row: Any = None) -> None:
        self.row = row
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0
        self.closed = False

    async def __aenter__(self) -> "_RecordingSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.close()

    async def close(self) -> None:
        self.closed = True

    async def commit(self) -> None:
        self.commits += 1

    async def execute(
        self,
        statement: Any,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _Result:
        sql = " ".join(str(statement).split())
        self.statements.append((sql, dict(params or {})))
        if "from agents" in sql.lower():
            return _Result(self.row)
        return _Result()


class _RecordingFactory:
    """Stand-in for ``AsyncSessionLocal`` that hands out one session."""

    def __init__(self, session: _RecordingSession) -> None:
        self.session = session
        self.calls = 0

    def __call__(self) -> _RecordingSession:
        self.calls += 1
        return self.session


def _active_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=AGENT_ID,
        tenant_id=TENANT_ID,
        api_key_hash="$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        status="active",
        api_key_expires_at=None,
        api_key_fingerprint="deadbeefdeadbeef",
        role="publisher",
    )


class _FakeHasher:
    """A PasswordHasher whose verify always succeeds and records the secrets."""

    def __init__(self) -> None:
        self.verified: list[str] = []

    def verify(self, stored_hash: str, secret: str) -> None:
        self.verified.append(secret)


# ---------------------------------------------------------------------------
# App helpers
# ---------------------------------------------------------------------------


def _build_app() -> Any:
    """Build the real app with the env the route-table test uses."""
    os.environ.setdefault("MINTKEY_AUDIT_HMAC_KEY", "aa" * 32)
    os.environ.setdefault("MINTKEY_VAULT_BACKEND", "sqlite")

    from admin_api.main import create_app

    return create_app()


async def _get_services(app: Any, key: str | None) -> Any:
    headers: dict[str, str] = {}
    if key is not None:
        headers["Authorization"] = "Bearer " + key
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(SERVICES_PATH, headers=headers)


async def _fill(capacity: asyncio.Semaphore) -> int:
    """Acquire every free slot; return how many this test now holds."""
    held = 0
    while not capacity.locked():
        await capacity.acquire()
        held += 1
        assert held <= 1024, "the capacity never became full"
    assert held > 0, "the capacity has no slot"
    return held


def _release(capacity: asyncio.Semaphore, held: int) -> None:
    for _ in range(held):
        capacity.release()


# ---------------------------------------------------------------------------
# C-c2386573 — a bearer of the wrong shape is 401 before any verify
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-c2386573")
@pytest.mark.parametrize(
    "case", ["short", "long", "bad_alphabet", "lowercase", "empty", "no_prefix"]
)
async def test_C_c2386573_wrong_shape_is_401_without_a_verify(
    monkeypatch: pytest.MonkeyPatch,
    case: str,
) -> None:
    key = _wrong_shaped_key(case)
    capacity = agent_key_guard.agent_verify_capacity()
    assert agent_key_guard.agent_key_shape_is_valid(key) is False

    session = _RecordingSession()
    factory = _RecordingFactory(session)
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
    verify = AsyncMock()
    monkeypatch.setattr(internal, "_verify_argon2", verify)

    response = await _get_services(_build_app(), key)

    assert response.status_code == 401, response.text
    assert response.json() == AUTH_REQUIRED_BODY
    verify.assert_not_awaited()
    assert factory.calls == 0, "a wrong-shaped bearer opened a key-check session"
    assert not capacity.locked(), "a wrong-shaped bearer took a verify slot"


# ---------------------------------------------------------------------------
# C-c2386573 — a full agent capacity answers 503 at once
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-c2386573")
async def test_C_c2386573_full_agent_capacity_answers_503_at_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    capacity = agent_key_guard.agent_verify_capacity()
    held = await _fill(capacity)
    try:
        session = _RecordingSession()
        factory = _RecordingFactory(session)
        monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
        hasher = _FakeHasher()
        monkeypatch.setattr(internal, "_ph", hasher)

        started = time.monotonic()
        response = await asyncio.wait_for(
            _get_services(_build_app(), _real_shaped_key()), timeout=2.0
        )
        elapsed = time.monotonic() - started

        assert response.status_code == 503, response.text
        assert response.json()["code"] == "mintkey:auth_unavailable"
        assert elapsed < 0.5, f"the full capacity waited {elapsed:.3f}s"
        assert hasher.verified == [], (
            "a full capacity still ran a password-hash verify"
        )
        assert factory.calls == 0, "a full capacity still opened a key-check session"
        assert capacity.locked(), "the test did not keep the capacity full"

        # validate-agent-key keeps working while the agent capacity is full.
        internal_session = _RecordingSession(row=_active_row())
        checked = await asyncio.wait_for(
            internal.validate_agent_key(
                internal.ValidateAgentKeyRequest(api_key=_real_shaped_key()),
                internal_session,
            ),
            timeout=1.0,
        )
        assert checked is not None
        assert checked.status_code == 200, checked.body
        assert len(hasher.verified) == 1
    finally:
        _release(capacity, held)


# ---------------------------------------------------------------------------
# C-c2386573 — the agent capacity is separate from validate-agent-key's
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-c2386573")
async def test_C_c2386573_agent_keys_do_not_wait_on_internal_capacity(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    key = _real_shaped_key()
    assert agent_key_guard.agent_key_shape_is_valid(key) is True

    agent_capacity = agent_key_guard.agent_verify_capacity()
    assert agent_capacity is not internal._verify_semaphore

    internal_held = await _fill(internal._verify_semaphore)
    try:
        session = _RecordingSession(row=_active_row())
        factory = _RecordingFactory(session)
        monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
        # Argon2 success, without parsing the fake stored hash.
        monkeypatch.setattr(internal, "_ph", _FakeHasher())

        route_session = _RecordingSession()
        app = _build_app()

        async def _route_db() -> Any:
            yield route_session

        app.dependency_overrides[get_db_session] = _route_db

        started = time.monotonic()
        response = await asyncio.wait_for(
            _get_services(app, key), timeout=2.0
        )
        elapsed = time.monotonic() - started

        assert response.status_code == 200, response.text
        assert response.json() == {"services": []}
        assert elapsed < 1.0, (
            f"an agent key waited on the internal verify capacity ({elapsed:.3f}s)"
        )
        assert factory.calls == 1
        assert not agent_capacity.locked(), (
            "the agent capacity was not released after the request"
        )
    finally:
        _release(internal._verify_semaphore, internal_held)
