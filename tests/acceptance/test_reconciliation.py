"""
Acceptance tests: change channel reconciliation endpoint — 410 behavior.

GET /v1/changes?since=<unknown_cursor> → 410 with mintkey:since_unknown + oldest_known_event_id.
GET /v1/changes?since=<valid_cursor>   → 200 with events list.
GET /v1/changes                        → 200 with events list (recent).

Sources:
  - ADR-0017.7 (since_unknown → 410 Gone; oldest_known_event_id in body)
  - ADR-0010 (change channel)
  - T-1.9.3 (reconciliation endpoint)
"""
from __future__ import annotations

import sys
import os
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

CHANGES_PATH = "/v1/changes"
KNOWN_CURSOR = "change_00000000000000000000000001"
OLDEST_KNOWN = "change_00000000000000000000000000"


# ---------------------------------------------------------------------------
# Session factory helpers (synchronous wrappers for TestClient compatibility)
# ---------------------------------------------------------------------------

def _session_unknown_cursor(oldest_id: str = OLDEST_KNOWN):
    """
    Session where the since cursor does NOT exist in audit_events.
    First execute() returns no row; second returns oldest known.
    """
    session = MagicMock()
    call_count = [0]

    async def _execute(*args, **kwargs):
        call_count[0] += 1
        result = MagicMock()
        if call_count[0] == 1:
            result.fetchone.return_value = None           # cursor not found
        else:
            row = MagicMock()
            row.id = oldest_id
            result.fetchone.return_value = row            # oldest known event
        return result

    session.execute = _execute
    return session


def _session_known_cursor(event_id: str = KNOWN_CURSOR):
    """Session where the since cursor exists in audit_events."""
    session = MagicMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        row = MagicMock()
        row.id = event_id
        result.fetchone.return_value = row
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _session_empty():
    """Session with no events at all (since omitted)."""
    session = MagicMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _make_client(session_factory) -> TestClient:
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
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_unknown_cursor_returns_410() -> None:
    """
    GET /v1/changes?since=<unknown_id> → 410 with code=mintkey:since_unknown.

    ADR-0017.7: never silently start from the beginning; return 410 instead.
    """
    client = _make_client(lambda: _session_unknown_cursor())
    resp = client.get(CHANGES_PATH, params={"since": "change_unknownid0000000000000001"})

    assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body.get("code") == "mintkey:since_unknown", (
        f"Expected code='mintkey:since_unknown', got: {body}"
    )


def test_unknown_cursor_includes_oldest_known() -> None:
    """
    410 response body must include oldest_known_event_id so subscribers know
    where to resync from — ADR-0017.7.
    """
    client = _make_client(lambda: _session_unknown_cursor(oldest_id=OLDEST_KNOWN))
    resp = client.get(CHANGES_PATH, params={"since": "change_unknownid0000000000000001"})

    assert resp.status_code == 410, f"Expected 410, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "oldest_known_event_id" in body, (
        f"Missing oldest_known_event_id field in 410 body: {body}"
    )
    assert body["oldest_known_event_id"] == OLDEST_KNOWN, (
        f"Expected oldest_known_event_id={OLDEST_KNOWN!r}, got: {body['oldest_known_event_id']!r}"
    )


def test_valid_cursor_returns_events() -> None:
    """
    GET /v1/changes?since=<known_id> → 200 with events list — T-1.9.3.
    """
    client = _make_client(lambda: _session_known_cursor(event_id=KNOWN_CURSOR))
    resp = client.get(CHANGES_PATH, params={"since": KNOWN_CURSOR})

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "events" in body, f"Missing events field: {body}"
    assert isinstance(body["events"], list), f"events must be a list: {body}"


def test_no_since_param_returns_recent_events() -> None:
    """
    GET /v1/changes without since → 200 with events list — T-1.9.3.
    No 410 when since is omitted.
    """
    client = _make_client(_session_empty)
    resp = client.get(CHANGES_PATH)

    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert "events" in body, f"Missing events field: {body}"
    assert isinstance(body["events"], list), f"events must be a list: {body}"
