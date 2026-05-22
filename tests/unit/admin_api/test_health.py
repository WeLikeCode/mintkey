"""
Unit tests: /v1/health (liveness) and /v1/ready (readiness).

Sources:
  - Req 1 AC7: GET /v1/health → 200 {"status": "ok"} (liveness only, no deps)
  - Req 1 AC8: GET /v1/ready → 200 only after {DB, Liquibase, Vault Adapter, change-channel}
               all confirmed; otherwise 503 with mintkey:code=not_ready
  - design §4 health.py
"""
from __future__ import annotations

import importlib
import sys
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

# Ensure admin-api src is importable
import os

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
if ADMIN_API_SRC not in sys.path:
    sys.path.insert(0, ADMIN_API_SRC)


@pytest.fixture()
def app():
    from admin_api.main import create_app
    return create_app()


@pytest.mark.asyncio
async def test_health_always_200(app) -> None:
    """
    GET /v1/health returns 200 {"status": "ok"} regardless of dependencies.
    Source: Req 1 AC7, design §4.
    """
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_503_when_db_unavailable(app) -> None:
    """
    GET /v1/ready returns 503 with mintkey:code=not_ready when DB check fails.
    Source: Req 1 AC8.
    """
    with patch("admin_api.api.health.check_db", new=AsyncMock(return_value=False)):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/v1/ready")

    assert response.status_code == 503
    body = response.json()
    assert body.get("code") == "mintkey:not_ready"
    assert "failing" in body


@pytest.mark.asyncio
async def test_ready_503_when_liquibase_not_done(app) -> None:
    """
    GET /v1/ready returns 503 when Liquibase check fails.
    Source: Req 1 AC8.
    """
    with (
        patch("admin_api.api.health.check_db", new=AsyncMock(return_value=True)),
        patch("admin_api.api.health.check_liquibase", new=AsyncMock(return_value=False)),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/v1/ready")

    assert response.status_code == 503


@pytest.mark.asyncio
async def test_ready_200_when_all_checks_pass(app) -> None:
    """
    GET /v1/ready returns 200 when all dependency checks pass.
    Source: Req 1 AC8.
    """
    with (
        patch("admin_api.api.health.check_db", new=AsyncMock(return_value=True)),
        patch("admin_api.api.health.check_liquibase", new=AsyncMock(return_value=True)),
        patch("admin_api.api.health.check_vault_adapter", new=AsyncMock(return_value=True)),
        patch("admin_api.api.health.check_change_channel", new=AsyncMock(return_value=True)),
    ):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/v1/ready")

    assert response.status_code == 200
    assert response.json()["status"] == "ready"
