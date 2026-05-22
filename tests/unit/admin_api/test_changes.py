"""
Unit tests: Change channel reconciliation endpoint.

GET /v1/changes?since=<event_id> — returns change events after cursor.
If since cursor is unknown/expired → 410 Gone per ADR-0017.7.

Sources:
  - ADR-0010 (change channel)
  - ADR-0017.7 (since_unknown → 410 Gone)
  - T-1.9.3 (change channel reconciliation endpoint)
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

CHANGES_PATH = "/v1/changes"
KNOWN_EVENT_ID = "change_00000000000000000000000001"
OLDEST_EVENT_ID = "change_00000000000000000000000000"


def _make_session_with_event(event_id: str, oldest_id: str | None = None):
    """Return a mock session where the given event_id exists in audit_events."""
    session = MagicMock()
    session._execute_calls = []

    mock_event_row = MagicMock()
    mock_event_row.id = event_id

    mock_oldest_row = MagicMock()
    mock_oldest_row.id = oldest_id or event_id

    call_count = [0]

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        call_count[0] += 1
        result = MagicMock()
        # First SELECT (existence check) returns the row; subsequent for events list
        result.fetchone.return_value = mock_event_row
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _make_session_without_event(oldest_id: str | None = None):
    """Return a mock session where event_id is NOT in audit_events."""
    session = MagicMock()
    session._execute_calls = []

    mock_oldest_row = MagicMock()
    mock_oldest_row.id = oldest_id or OLDEST_EVENT_ID

    call_count = [0]

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            # First SELECT: event not found
            result.fetchone.return_value = None
        else:
            # Second SELECT: oldest known event
            result.fetchone.return_value = mock_oldest_row
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _make_session_empty():
    """Return a mock session with no events at all."""
    session = MagicMock()
    session._execute_calls = []

    async def _execute(*args, **kwargs):
        session._execute_calls.append((args, kwargs))
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _create_changes_app(session_factory):
    from fastapi import FastAPI
    from admin_api.api.changes import router as changes_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(changes_router)

    async def mock_db_session():
        yield session_factory()

    app.dependency_overrides[get_db_session] = mock_db_session
    csrf_exempt(CHANGES_PATH)
    app.add_middleware(CsrfMiddleware)
    return app


# ---------------------------------------------------------------------------
# GET /v1/changes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_changes_endpoint_returns_200() -> None:
    """
    GET /v1/changes without since param returns 200 with {"events": [...]} — T-1.9.3.
    """
    app = _create_changes_app(_make_session_empty)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(CHANGES_PATH)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "events" in body
    assert isinstance(body["events"], list)


@pytest.mark.asyncio
async def test_changes_unknown_since_returns_410() -> None:
    """
    GET /v1/changes?since=<unknown> returns 410 with code=since_unknown
    and oldest_known_event_id — ADR-0017.7; T-1.9.3.
    """
    app = _create_changes_app(
        lambda: _make_session_without_event(oldest_id=OLDEST_EVENT_ID)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(CHANGES_PATH, params={"since": "change_unknownid0000000000000001"})

    assert resp.status_code == 410, resp.text
    body = resp.json()
    assert body.get("code") == "mintkey:since_unknown", f"Unexpected body: {body}"
    assert "oldest_known_event_id" in body, f"Missing oldest_known_event_id: {body}"


@pytest.mark.asyncio
async def test_changes_returns_events_after_cursor() -> None:
    """
    GET /v1/changes?since=<known_event_id> returns 200 with events — T-1.9.3.
    """
    app = _create_changes_app(
        lambda: _make_session_with_event(KNOWN_EVENT_ID, oldest_id=OLDEST_EVENT_ID)
    )
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get(CHANGES_PATH, params={"since": KNOWN_EVENT_ID})

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "events" in body
    assert isinstance(body["events"], list)
