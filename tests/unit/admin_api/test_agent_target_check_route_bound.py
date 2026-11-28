"""The agent service routes bound the target check themselves.

Criterion C-3f78eec5 (feedback FB-002): when an agent creates or updates a
service whose ``base_url`` or ``openapi_url`` names a host that resolves
slowly or not at all, the check finishes within a bounded time and answers
``mintkey:target_not_allowed`` with reason ``unresolvable`` when it runs out,
and the request holds no database connection or transaction while it waits
for the resolver.

The timeout used to live only in ``mintkey_models.egress`` (part 2 of the
diff): the route awaited whatever that module returned. These tests pin the
bound where the request is made instead — ``_check_target`` in
``agent_services`` (part 1) must bound the check itself, so a check that never
returns still ends the request in time. The resolver seam is replaced by a
coroutine that records the session's state and then sleeps far past the test
bound; nothing outside the route can rescue it.

Source: openspec/changes/agent-service-routes-fix-5 — feedback FB-002.
"""

# ruff: noqa: E402 — the service packages are imported after sys.path setup.
from __future__ import annotations

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi import Request

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
MODELS_SRC = REPO_ROOT / "packages" / "python" / "mintkey-models"
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from admin_api.api import agent_services
from admin_api.auth.agent_principal import AgentApiError, AgentPrincipal

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ab")

#: The most the route may take to give up on its target check. The production
#: bound is smaller; the test only requires that a bound exists below this.
CHECK_BOUND_SECONDS = 6.0

#: How long the replaced target check waits if the route does not bound it.
#: Much longer than CHECK_BOUND_SECONDS, so an unbounded route overruns this.
HANG_SECONDS = 60.0

#: The host named in the test URL. Its value never matters: the check itself
#: is replaced, so only the route's own bound can end the request.
SLOW_URL = "https://slow.example.com/"


class _Result:
    """The slice of a SQLAlchemy result the handlers use."""

    def __init__(self, row: Any | None = None) -> None:
        self._row = row

    def fetchone(self) -> Any | None:
        return self._row

    def fetchall(self) -> list[Any]:
        return [] if self._row is None else [self._row]


class _RecordingSession:
    """A session that records statements and whether a connection is open.

    A real ``AsyncSession`` acquires a pooled connection on the first
    statement and returns it on ``commit``/``rollback``; this fake mirrors
    that, so the replaced target check can record whether the route was
    holding a connection while it waited.
    """

    def __init__(self, *, service_row: Any | None = None) -> None:
        self.service_row = service_row
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.connection_open = False
        self.commits = 0
        self.rollbacks = 0
        self.audit_events: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []

    async def execute(
        self,
        statement: Any,
        params: Any = None,
        **kwargs: Any,
    ) -> _Result:
        self.connection_open = True
        sql = " ".join(str(statement).split())
        bound: dict[str, Any] = params if isinstance(params, dict) else {}
        self.statements.append((sql, bound))
        upper = sql.upper()

        if "INSERT INTO AUDIT_EVENTS" in upper:
            self.audit_events.append(
                {
                    "event_type": bound.get("event_type"),
                    "payload": json.loads(bound.get("payload") or "{}"),
                }
            )
            return _Result()
        if "PG_NOTIFY" in upper:
            self.notifications.append(
                {
                    "channel": bound.get("channel"),
                    "payload": json.loads(bound.get("payload") or "{}"),
                }
            )
            return _Result()
        if "INSERT INTO SERVICES" in upper:
            return _Result(self.service_row)
        if upper.startswith("UPDATE SERVICES"):
            return _Result(self.service_row)
        if upper.startswith("DELETE"):
            return _Result()
        if upper.startswith("SELECT") and "FROM SERVICES" in upper:
            if "SLUG" in upper and "OWNER_AGENT_ID" not in upper:
                return _Result(None)
            return _Result(self.service_row)
        return _Result()

    async def commit(self) -> None:
        self.connection_open = False
        self.commits += 1

    async def rollback(self) -> None:
        self.connection_open = False
        self.rollbacks += 1

    async def flush(self) -> None:
        return None


def _principal() -> AgentPrincipal:
    return AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="publisher")


def _service_row() -> SimpleNamespace:
    row = SimpleNamespace(
        id=SERVICE_ID,
        tenant_id=TENANT_ID,
        name="My Service",
        slug="my-service",
        display_name="My Service Display",
        description="A service",
        base_url="https://api.example.com",
        auth_scheme="bearer_token",
        openapi_url=None,
        status="active",
        owner_agent_id=AGENT_ID,
        created_by_agent_id=AGENT_ID,
        credential_set=True,
    )
    row.created_at = datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc)
    row.updated_at = datetime(2026, 2, 3, 4, 5, 7, tzinfo=timezone.utc)
    return row


def _request(method: str, payload: dict[str, Any], path: str) -> Request:
    raw = json.dumps(payload).encode()

    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": method,
            "path": path,
            "raw_path": path.encode(),
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        },
        receive,
    )


def _replace_target_check(
    monkeypatch: pytest.MonkeyPatch,
    session: _RecordingSession,
    seen: dict[str, Any],
) -> None:
    """Make the target check never return, recording the session first.

    No error is raised and no connection is touched by the check itself: the
    only way the request can finish in time is the route's own bound.
    """

    async def _hang(url: str) -> None:
        seen["url"] = url
        seen["statements"] = len(session.statements)
        seen["connection_open"] = session.connection_open
        seen["in_transaction"] = session.connection_open
        await asyncio.sleep(HANG_SECONDS)
        raise AssertionError("the target check returned; it should never return")

    monkeypatch.setattr(agent_services, "check_agent_target_url", _hang)


def _writes(session: _RecordingSession) -> list[str]:
    return [
        sql
        for sql, _params in session.statements
        if sql.upper().startswith(("INSERT INTO SERVICES", "UPDATE", "DELETE"))
    ]


def _assert_bounded_target_refusal(
    seen: dict[str, Any],
    error: AgentApiError | None,
    field: str,
) -> None:
    assert seen.get("url") == SLOW_URL, "the target check was never called"
    assert error is not None, "a check that never returns was accepted or hung"
    assert error.status_code == 400
    assert error.body == {
        "code": "mintkey:target_not_allowed",
        "title": "Target not allowed",
        "field": field,
        "reason": "unresolvable",
    }


async def _created_response(
    session: _RecordingSession,
    payload: dict[str, Any],
) -> Any:
    return await agent_services.create_agent_service(
        request=_request("POST", payload, "/v1/agent/services"),
        principal=_principal(),
        session=session,
    )


async def _updated_response(
    session: _RecordingSession,
    payload: dict[str, Any],
) -> Any:
    return await agent_services._update_agent_service(
        service_ref="my-service",
        request=_request("PATCH", payload, "/v1/agent/services/my-service"),
        principal=_principal(),
        session=session,
    )


# ---------------------------------------------------------------------------
# C-3f78eec5 — create bounds the target check at the route
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3f78eec5")
@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["base_url", "openapi_url"])
async def test_C_3f78eec5_create_bounds_a_check_that_never_returns(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    session = _RecordingSession(service_row=_service_row())
    seen: dict[str, Any] = {}
    _replace_target_check(monkeypatch, session, seen)

    payload: dict[str, Any] = {
        "name": "My Service",
        "base_url": "https://api.example.com",
        "auth_scheme": "bearer_token",
    }
    payload[field] = SLOW_URL

    error: AgentApiError | None = None
    started = time.monotonic()
    try:
        await asyncio.wait_for(
            _created_response(session, payload), timeout=CHECK_BOUND_SECONDS
        )
    except asyncio.TimeoutError:
        pytest.fail(
            "the create route did not bound its target check: it was still "
            f"waiting after {CHECK_BOUND_SECONDS} seconds"
        )
    except AgentApiError as exc:
        error = exc
    elapsed = time.monotonic() - started

    assert elapsed < CHECK_BOUND_SECONDS
    _assert_bounded_target_refusal(seen, error, field)

    # The check ran before the route touched the database: no connection and
    # no transaction were held while it waited.
    assert seen["statements"] == 0
    assert seen["connection_open"] is False
    assert seen["in_transaction"] is False
    assert _writes(session) == []


# ---------------------------------------------------------------------------
# C-3f78eec5 — update bounds the target check at the route
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3f78eec5")
@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["base_url", "openapi_url"])
async def test_C_3f78eec5_update_bounds_a_check_that_never_returns(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    session = _RecordingSession(service_row=_service_row())
    seen: dict[str, Any] = {}
    _replace_target_check(monkeypatch, session, seen)

    error: AgentApiError | None = None
    started = time.monotonic()
    try:
        await asyncio.wait_for(
            _updated_response(session, {field: SLOW_URL}),
            timeout=CHECK_BOUND_SECONDS,
        )
    except asyncio.TimeoutError:
        pytest.fail(
            "the update route did not bound its target check: it was still "
            f"waiting after {CHECK_BOUND_SECONDS} seconds"
        )
    except AgentApiError as exc:
        error = exc
    elapsed = time.monotonic() - started

    assert elapsed < CHECK_BOUND_SECONDS
    _assert_bounded_target_refusal(seen, error, field)

    # The stored row had to be read to know the target changed, so the route
    # must have ended that transaction before waiting for the check.
    assert seen["connection_open"] is False
    assert seen["in_transaction"] is False
    assert _writes(session) == []
