"""FB-002 retake: the target check is bounded and waits without a connection.

Criterion C-3f78eec5: when an agent creates or updates a service whose
``base_url`` or ``openapi_url`` names a host that resolves slowly or not at
all, the check finishes within a bounded time and answers
``mintkey:target_not_allowed`` with reason ``unresolvable`` when it runs out,
and the request holds no database connection or transaction while it waits
for the resolver.

These tests pin the two halves of the requirement in one file, so both are
visible in the same diff:

  1. ``mintkey_models.egress.check_agent_target_url`` bounds its resolver
     call: a name that never resolves is refused as ``unresolvable`` instead
     of hanging, while a public name still passes (the non-vacuous case);
  2. the create route asks the resolver before it issues any statement, so no
     pooled connection and no transaction are held while it waits.

The update route's release of the row lock before the resolver is pinned by
``tests/unit/admin_api/test_agent_target_check_bounded.py``.

Source: openspec/changes/agent-service-routes-fix-4 — feedback FB-002.
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
from admin_api.auth.agent_principal import AgentPrincipal
from mintkey_models import egress

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ab")

#: The host that never resolves within the test's own bound.
SLOW_HOST = "slow.example.com"
SLOW_URL = f"https://{SLOW_HOST}/"

#: The most a bounded target check may take. The production bound is smaller;
#: this test only requires that a bound exists and that it is below this.
CHECK_BOUND_SECONDS = 6.0

#: How long the slow resolver would wait if nothing bounded it. Much longer
#: than CHECK_BOUND_SECONDS, so an unbounded check overruns the test.
SLOW_RESOLVER_SECONDS = 60.0


class _Result:
    """The slice of a SQLAlchemy result the create handler uses."""

    def __init__(self, row: Any | None = None) -> None:
        self._row = row

    def fetchone(self) -> Any | None:
        return self._row

    def fetchall(self) -> list[Any]:
        return [] if self._row is None else [self._row]


class _RecordingSession:
    """A session that records statements and whether a connection is open.

    A real ``AsyncSession`` acquires a pooled connection on its first
    statement and returns it on ``commit``/``rollback``; this fake mirrors
    that, so the slow resolver can read ``connection_open`` and tell whether
    the route was holding a connection while it waited.
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
        credential_set=False,
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


# ---------------------------------------------------------------------------
# C-3f78eec5 — the resolver is bounded in the egress policy itself
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3f78eec5")
@pytest.mark.asyncio
async def test_C_3f78eec5_resolver_timeout_is_bounded_and_unresolvable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A name that never resolves is refused as ``unresolvable`` in time."""

    async def _resolve(host: str) -> list[str]:
        if host == SLOW_HOST:
            await asyncio.sleep(SLOW_RESOLVER_SECONDS)
        return ["93.184.216.34"]

    monkeypatch.setattr(egress, "resolve_host", _resolve)

    started = time.monotonic()
    try:
        await asyncio.wait_for(
            egress.check_agent_target_url(SLOW_URL), timeout=CHECK_BOUND_SECONDS
        )
    except asyncio.TimeoutError:
        pytest.fail(
            "the resolver call was not bounded: the check did not finish "
            f"within {CHECK_BOUND_SECONDS} seconds"
        )
    except egress.TargetNotAllowed as exc:
        elapsed = time.monotonic() - started
        assert exc.reason == "unresolvable"
    else:
        pytest.fail("a host that never resolves was accepted")

    assert elapsed < CHECK_BOUND_SECONDS

    # A public name still passes, so a policy that refused every URL (or a
    # stub returning the zero value) would not satisfy this test.
    assert await egress.check_agent_target_url("https://api.example.com/") is None


# ---------------------------------------------------------------------------
# C-3f78eec5 — create asks the resolver before it opens a connection
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-3f78eec5")
@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["base_url", "openapi_url"])
async def test_C_3f78eec5_create_waits_without_a_connection(
    monkeypatch: pytest.MonkeyPatch,
    field: str,
) -> None:
    """The target check runs before the request issues any statement."""
    session = _RecordingSession(service_row=_service_row())
    seen: dict[str, Any] = {}

    async def _resolve(host: str) -> list[str]:
        if host == SLOW_HOST:
            # Record the session's state at the moment the route waits.
            seen["host"] = host
            seen["statements"] = len(session.statements)
            seen["connection_open"] = session.connection_open
            await asyncio.sleep(0.05)
        return ["93.184.216.34"]

    monkeypatch.setattr(egress, "resolve_host", _resolve)

    payload: dict[str, Any] = {
        "name": "My Service",
        "base_url": "https://api.example.com",
        "auth_scheme": "bearer_token",
    }
    payload[field] = SLOW_URL

    response = await agent_services.create_agent_service(
        request=_request("POST", payload, "/v1/agent/services"),
        principal=_principal(),
        session=session,
    )

    assert response.status_code == 201
    body = json.loads(bytes(response.body))
    assert body["id"].startswith("svc_")
    assert body["credential_set"] is False

    assert seen.get("host") == SLOW_HOST, "the resolver was never asked for the target"
    assert seen["statements"] == 0
    assert seen["connection_open"] is False
