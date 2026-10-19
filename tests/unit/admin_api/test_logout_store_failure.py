"""
Unit tests: a failed session delete during logout (task 3.2, operator-logout).

Source: operator-logout › A failed session delete is reported
  - C-efb11918  The session store raises
  - C-22d8b961  The contract lists the outcomes

``delete_session`` is patched at the name ``auth.py`` imports. The ASGI
transport is built with ``raise_app_exceptions=False`` so that the old
unhandled ``OSError`` surfaces as a 500 response and the test fails by
assertion, not by an exception escaping the request.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
import yaml
from httpx import ASGITransport, AsyncClient

from admin_api.api import auth

_OPENAPI = (
    Path(__file__).resolve().parents[3]
    / "docs"
    / "architecture"
    / "contracts"
    / "rest"
    / "openapi.yaml"
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
@pytest.mark.l4("C-efb11918")
async def test_delete_session_failure_answers_503_and_still_evicts(
    app: Any, caplog: pytest.LogCaptureFixture
) -> None:
    """delete_session raises OSError: logout answers 503 with the
    session_store_unavailable body, evicts the cached token, clears both
    cookies, and logs the failure at ERROR without the token."""
    token = str(uuid4())
    auth._WHOAMI_CACHE[token] = ({"operator_id": "op"}, time.monotonic())

    failure = AsyncMock(side_effect=OSError("session store down"))

    with (
        patch("admin_api.api.auth.delete_session", new=failure, create=True),
        caplog.at_level(logging.ERROR, logger="admin_api.api.auth"),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app, raise_app_exceptions=False),
            base_url="http://test",
        ) as client:
            response = await client.post(
                "/v1/auth/logout", cookies={"mintkey_session": token}
            )

    failure.assert_awaited_once_with(token)
    assert response.status_code == 503, response.text
    assert response.headers["content-type"].startswith("application/json")
    assert response.json() == {
        "mintkey:code": "session_store_unavailable",
        "title": "Session store unavailable",
    }
    assert token not in auth._WHOAMI_CACHE
    _assert_clears_both_cookies(response)

    error_records = [
        record
        for record in caplog.records
        if record.name == "admin_api.api.auth" and record.levelno == logging.ERROR
    ]
    assert error_records, [record.name for record in caplog.records]
    assert any(
        record.getMessage().startswith("auth.logout_session_delete_failed")
        for record in error_records
    ), [record.getMessage() for record in error_records]
    assert any("OSError" in record.getMessage() for record in error_records), [
        record.getMessage() for record in error_records
    ]

    logged_text = "\n".join(
        record.getMessage() for record in caplog.records
    )
    assert token not in logged_text


@pytest.mark.l4("C-22d8b961")
def test_openapi_logout_lists_204_and_503() -> None:
    """The REST contract lists exactly 204 and 503 for POST /v1/auth/logout,
    with 503 pointing at the existing ServiceUnavailable response."""
    contract = yaml.safe_load(_OPENAPI.read_text())
    responses = contract["paths"]["/v1/auth/logout"]["post"]["responses"]

    assert set(responses) == {"204", "503"}
    assert responses["503"] == {
        "$ref": "#/components/responses/ServiceUnavailable"
    }
    assert "ServiceUnavailable" in contract["components"]["responses"]
