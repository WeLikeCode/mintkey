"""
A REST tool call whose agent key could not be judged gets 503 auth_unavailable.

These tests build the app the way ``test_bearer_auth._build_app`` does: a fake
``validate_agent_key`` is installed on ``mcp_server.main`` and
``get_db_session`` is overridden with a lightweight mock session.

Source: agent-key-auth — "A REST request whose agent key could not be checked
gets 503 auth_unavailable".
"""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator, Callable
from unittest.mock import AsyncMock, MagicMock

from httpx import ASGITransport, AsyncClient

_TEST_AGENT_ID = str(uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"))
_TEST_TENANT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_FAKE_KEY = "mk_" + "agent_" + "rest_unavailable_key_0001"


def _build_app(
    fake_validate_agent_key: Callable,
) -> tuple[object, MagicMock, tuple[object, object]]:
    """Build the ASGI app and return it with the mock DB session and orig validator."""
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.main import create_app

    _orig_validate = _main_mod.validate_agent_key
    _main_mod.validate_agent_key = fake_validate_agent_key

    app = create_app()

    session = AsyncMock()
    result_mock = MagicMock()
    result_mock.fetchall.return_value = []
    result_mock.fetchone.return_value = None
    session.execute = AsyncMock(return_value=result_mock)

    async def _fake_db_session() -> AsyncGenerator:
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session

    return app, session, (_orig_validate, _main_mod)


def _run(app: object, method: str, path: str, **httpx_kwargs):
    """Send a single request through the ASGI stack."""

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await getattr(client, method)(path, **httpx_kwargs)

    return asyncio.run(_inner())


def _restore(restore_info) -> None:
    _orig_validate, _main_mod = restore_info
    _main_mod.validate_agent_key = _orig_validate


def test_C_0bbc396d_list_services_unjudged_key_gets_503_without_using_session() -> None:
    """C-0bbc396d: no verdict on a Bearer key gives 503 and the route does not run."""

    async def _fake_validate(key: str):
        return None, "service_unavailable"

    app, session, restore_info = _build_app(_fake_validate)
    try:
        resp = _run(
            app,
            "get",
            "/v1/tools/list_services",
            headers={"Authorization": f"Bearer {_FAKE_KEY}"},
        )
    finally:
        _restore(restore_info)

    assert resp.status_code == 503, (
        f"Expected 503 for an unjudged key, got {resp.status_code}: {resp.text}"
    )
    assert resp.json() == {"code": "mintkey:auth_unavailable"}
    assert resp.headers["Retry-After"] == "1"
    session.execute.assert_not_called()


def test_C_9a964586_request_token_unjudged_x_api_key_gets_same_503() -> None:
    """C-9a964586: the X-API-Key form gets the same 503 and the body hides the key."""

    async def _fake_validate(key: str):
        return None, "service_unavailable"

    app, _session, restore_info = _build_app(_fake_validate)
    try:
        resp = _run(
            app,
            "post",
            "/v1/tools/request_token",
            headers={"X-API-Key": _FAKE_KEY},
            json={
                "service_id": "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd",
                "action": "call",
            },
        )
    finally:
        _restore(restore_info)

    assert resp.status_code == 503, (
        f"Expected 503 for an unjudged key, got {resp.status_code}: {resp.text}"
    )
    assert resp.json() == {"code": "mintkey:auth_unavailable"}
    assert resp.headers["Retry-After"] == "1"
    assert _FAKE_KEY not in resp.text
