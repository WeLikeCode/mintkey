"""
MCP-D-C: Regression tests for both Authorization: Bearer and X-API-Key auth forms.

main.py:71-82 already accepts both header forms. The MCP spec (2025-06-18) only
specifies Bearer, so vanilla MCP clients (Claude Code, Cursor, mcp-cli) will use
it. These tests lock in both forms so future refactors don't accidentally break
either.

Tests:
  T1  Bearer header accepted on GET /v1/tools/list_services
  T2  X-API-Key header accepted on GET /v1/tools/list_services (regression)
  T3  Bearer with non-mintkey-prefix token → 401
  T4  No auth header → 401
  T5  Both headers present, Bearer wins (matches middleware code order)
  T6  Bearer accepted on POST /v1/tools/request_token (non-401 response)
  T7  Empty Bearer string → 401

Source: MCP-DISCOVER-DESIGN Section 5; MCP spec 2025-06-18 §authorization.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock

import pytest

# ---------------------------------------------------------------------------
# Constants shared by all tests
# ---------------------------------------------------------------------------

_TEST_AGENT_ID = str(uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
_TEST_TENANT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_FAKE_KEY = "mk_agent_test123"

_FAKE_CTX = {
    "agent_id": _TEST_AGENT_ID,
    "tenant_id": _TEST_TENANT_ID,
    "name": "test-agent",
    "status": "active",
}


# ---------------------------------------------------------------------------
# ASGI harness helpers
# ---------------------------------------------------------------------------


def _build_app(fake_validate_agent_key):
    """
    Build a FastAPI app with:
      - validate_agent_key replaced by fake_validate_agent_key on mcp_server.main
      - get_db_session overridden with a lightweight AsyncMock that returns empty results
      - get_agent_context NOT overridden — we deliberately let the middleware set it,
        which is the behaviour under test.
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.main import create_app

    _orig_validate = _main_mod.validate_agent_key
    _main_mod.validate_agent_key = fake_validate_agent_key

    app = create_app()

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.fetchall.return_value = []   # list_services → empty list
        result_mock.fetchone.return_value = None  # request_token → permission_not_found
        session.execute = AsyncMock(return_value=result_mock)
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session

    return app, _orig_validate, _main_mod


def _run(app, method: str, path: str, **httpx_kwargs):
    """Send a single request through the ASGI stack; returns the httpx.Response."""
    from httpx import AsyncClient, ASGITransport

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await getattr(client, method)(path, **httpx_kwargs)

    return asyncio.run(_inner())


# ---------------------------------------------------------------------------
# T1 — Bearer header accepted on /v1/tools/list_services
# ---------------------------------------------------------------------------


def test_bearer_header_accepted_on_list_services() -> None:
    """
    Authorization: Bearer mk_agent_<key> must be accepted by the middleware and
    result in a 200 from list_services (empty service list is fine — the point
    is that the response is NOT 401).

    Source: MCP-D-C T1; MCP spec 2025-06-18 §authorization.
    """

    async def _fake_validate(key):
        if key == _FAKE_KEY:
            return _FAKE_CTX, None
        return None, "invalid_key"

    app, _orig, _main_mod = _build_app(_fake_validate)
    try:
        resp = _run(
            app, "get", "/v1/tools/list_services",
            headers={"Authorization": f"Bearer {_FAKE_KEY}"},
        )
    finally:
        _main_mod.validate_agent_key = _orig

    assert resp.status_code == 200, (
        f"T1: Expected 200 with Bearer header, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "services" in body, f"T1: Missing 'services' key in body: {body}"


# ---------------------------------------------------------------------------
# T2 — X-API-Key header still accepted (regression guard)
# ---------------------------------------------------------------------------


def test_xapikey_header_accepted_on_list_services() -> None:
    """
    X-API-Key: mk_agent_<key> must remain accepted so existing agents don't break.
    This is the legacy header form — must continue to work alongside Bearer.

    Source: MCP-D-C T2; backward-compat requirement.
    """

    async def _fake_validate(key):
        if key == _FAKE_KEY:
            return _FAKE_CTX, None
        return None, "invalid_key"

    app, _orig, _main_mod = _build_app(_fake_validate)
    try:
        resp = _run(
            app, "get", "/v1/tools/list_services",
            headers={"X-API-Key": _FAKE_KEY},
        )
    finally:
        _main_mod.validate_agent_key = _orig

    assert resp.status_code == 200, (
        f"T2: Expected 200 with X-API-Key header, got {resp.status_code}: {resp.text}"
    )
    body = resp.json()
    assert "services" in body, f"T2: Missing 'services' key in body: {body}"


# ---------------------------------------------------------------------------
# T3 — Bearer with non-mintkey-prefix token → 401
# ---------------------------------------------------------------------------


def test_bearer_non_mintkey_token_rejected() -> None:
    """
    Authorization: Bearer <token> where the token does NOT start with 'mk_agent_'
    must result in 401.  The middleware only promotes the candidate to a validated
    token when the prefix matches — other Bearer values are silently dropped.

    Source: MCP-D-C T3; main.py:74-76.
    """
    calls: list[str] = []

    async def _fake_validate(key):
        calls.append(key)
        return _FAKE_CTX, None  # would succeed if reached

    app, _orig, _main_mod = _build_app(_fake_validate)
    try:
        resp = _run(
            app, "get", "/v1/tools/list_services",
            headers={"Authorization": "Bearer not_a_mintkey_token"},
        )
    finally:
        _main_mod.validate_agent_key = _orig

    assert resp.status_code == 401, (
        f"T3: Expected 401 for non-mk_agent_ Bearer token, got {resp.status_code}: {resp.text}"
    )
    # validate_agent_key must NOT have been called — the prefix check happens before it
    assert calls == [], (
        f"T3: validate_agent_key should not be called for non-mintkey Bearer; "
        f"called with: {calls}"
    )


# ---------------------------------------------------------------------------
# T4 — No auth header → 401
# ---------------------------------------------------------------------------


def test_no_auth_header_rejected() -> None:
    """
    A request with no Authorization or X-API-Key header must result in 401.

    Source: MCP-D-C T4.
    """

    async def _fake_validate(key):
        return _FAKE_CTX, None  # would succeed if reached

    app, _orig, _main_mod = _build_app(_fake_validate)
    try:
        resp = _run(app, "get", "/v1/tools/list_services")
    finally:
        _main_mod.validate_agent_key = _orig

    assert resp.status_code == 401, (
        f"T4: Expected 401 with no auth header, got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# T5 — Both headers present, Bearer takes precedence
# ---------------------------------------------------------------------------


def test_bearer_precedence_over_xapikey() -> None:
    """
    When both Authorization: Bearer and X-API-Key are present, the middleware
    must use the Bearer value and never fall through to X-API-Key.

    This is verified by tracking which key is passed to validate_agent_key.

    Source: MCP-D-C T5; main.py:71-82 (Bearer checked first, X-API-Key only
    consulted when token is still None after Bearer check).
    """
    captured_keys: list[str] = []

    async def _fake_validate(key):
        captured_keys.append(key)
        if key.startswith("mk_agent_"):
            return _FAKE_CTX, None
        return None, "invalid_key"

    app, _orig, _main_mod = _build_app(_fake_validate)
    try:
        resp = _run(
            app, "get", "/v1/tools/list_services",
            headers={
                "Authorization": "Bearer mk_agent_FROM_BEARER",
                "X-API-Key": "mk_agent_FROM_XAPIKEY",
            },
        )
    finally:
        _main_mod.validate_agent_key = _orig

    assert resp.status_code == 200, (
        f"T5: Expected 200 when Bearer is valid, got {resp.status_code}: {resp.text}"
    )
    assert "mk_agent_FROM_BEARER" in captured_keys, (
        f"T5: Bearer key was not passed to validate_agent_key; calls: {captured_keys}"
    )
    assert "mk_agent_FROM_XAPIKEY" not in captured_keys, (
        f"T5: X-API-Key should NOT be consulted when Bearer succeeds; calls: {captured_keys}"
    )


# ---------------------------------------------------------------------------
# T6 — Bearer accepted on POST /v1/tools/request_token
# ---------------------------------------------------------------------------


def test_bearer_on_request_token_post() -> None:
    """
    POST /v1/tools/request_token with Authorization: Bearer must not be rejected
    by the auth layer (response must NOT be 401).

    With no permission grant in the mocked DB, the endpoint returns 403
    (permission_not_found) or 404 (service_not_found) depending on slug
    resolution — either is acceptable; the key assertion is status != 401.

    Source: MCP-D-C T6.
    """

    async def _fake_validate(key):
        if key == _FAKE_KEY:
            return _FAKE_CTX, None
        return None, "invalid_key"

    app, _orig, _main_mod = _build_app(_fake_validate)
    try:
        resp = _run(
            app, "post", "/v1/tools/request_token",
            headers={"Authorization": f"Bearer {_FAKE_KEY}"},
            json={"service_id": "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd", "action": "call"},
        )
    finally:
        _main_mod.validate_agent_key = _orig

    assert resp.status_code != 401, (
        f"T6: Bearer auth should not produce 401 on request_token POST; "
        f"got {resp.status_code}: {resp.text}"
    )


# ---------------------------------------------------------------------------
# T7 — Empty Bearer string → 401
# ---------------------------------------------------------------------------


def test_empty_bearer_rejected() -> None:
    """
    Authorization: Bearer  (with trailing space but empty candidate) must result
    in 401.  The middleware strips 'Bearer ' to get the candidate — an empty
    string does not start with 'mk_agent_', so token stays None.

    Source: MCP-D-C T7; main.py:74-76.
    """
    calls: list[str] = []

    async def _fake_validate(key):
        calls.append(key)
        return _FAKE_CTX, None

    app, _orig, _main_mod = _build_app(_fake_validate)
    try:
        # "Bearer" (no trailing space) → auth[len("Bearer "):] = "" → no mk_agent_ prefix
        resp = _run(
            app, "get", "/v1/tools/list_services",
            headers={"Authorization": "Bearer"},
        )
    finally:
        _main_mod.validate_agent_key = _orig

    assert resp.status_code == 401, (
        f"T7: Expected 401 for empty Bearer token, got {resp.status_code}: {resp.text}"
    )
    assert calls == [], (
        f"T7: validate_agent_key should not be called for empty Bearer; calls: {calls}"
    )
