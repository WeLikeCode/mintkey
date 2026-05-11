"""
Unit tests: CSRF middleware (double-submit cookie pattern).

Sources:
  - design §4; ADR-0013; ADR-0017.3 (CsrfHeader security scheme)
  - admin_api/middleware/csrf.py
"""
from __future__ import annotations

import sys
import os

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "admin-api", "src")
if ADMIN_API_SRC not in sys.path:
    sys.path.insert(0, ADMIN_API_SRC)


def make_test_app():
    from fastapi import FastAPI
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt, _CSRF_EXEMPT_PATHS

    _CSRF_EXEMPT_PATHS.clear()

    test_app = FastAPI()

    @test_app.post("/test-endpoint")
    async def test_post():
        return {"status": "ok"}

    @test_app.get("/v1/health")
    async def health():
        return {"status": "ok"}

    @test_app.post("/v1/exempt-path")
    async def exempt_post():
        return {"status": "ok"}

    csrf_exempt("/v1/exempt-path")

    test_app.add_middleware(CsrfMiddleware)
    return test_app


@pytest.mark.asyncio
async def test_get_request_bypasses_csrf() -> None:
    """
    GET requests (SAFE_METHODS) skip CSRF validation entirely.
    Source: CsrfMiddleware — SAFE_METHODS bypass.
    """
    app = make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_post_without_csrf_header_returns_403() -> None:
    """
    POST with no CSRF cookie or header returns 403 mintkey:csrf_missing.
    Source: CsrfMiddleware — missing cookie/header guard.
    """
    app = make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/test-endpoint")

    assert response.status_code == 403
    assert response.json() == {"code": "mintkey:csrf_missing"}


@pytest.mark.asyncio
async def test_post_with_mismatched_csrf_returns_403() -> None:
    """
    POST with cookie "abc" and header "xyz" returns 403 mintkey:csrf_invalid.
    Source: CsrfMiddleware — hmac.compare_digest mismatch guard.
    """
    app = make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("csrf_token", "abc")
        response = await client.post(
            "/test-endpoint",
            headers={"x-mintkey-csrf": "xyz"},
        )

    assert response.status_code == 403
    assert response.json() == {"code": "mintkey:csrf_invalid"}


@pytest.mark.asyncio
async def test_post_with_valid_csrf_passes() -> None:
    """
    POST with matching cookie and header passes through to the handler.
    Source: CsrfMiddleware — hmac.compare_digest match → call_next.
    """
    token = "secure-test-token-12345"
    app = make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        client.cookies.set("csrf_token", token)
        response = await client.post(
            "/test-endpoint",
            headers={"x-mintkey-csrf": token},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_exempt_path_skips_csrf() -> None:
    """
    POST to an exempt path passes without CSRF cookie or header.
    Source: CsrfMiddleware — _CSRF_EXEMPT_PATHS bypass; csrf_exempt("/v1/exempt-path").
    """
    app = make_test_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/v1/exempt-path")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
