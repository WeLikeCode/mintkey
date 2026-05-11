"""
Integration test: GET /v1/health → 200.

Uses the `admin_app` fixture from conftest.py which provides a real
TestClient backed by a PostgreSQL 16 testcontainer with Liquibase
migrations applied.

The /v1/health endpoint is a pure liveness probe — it never touches
the DB — so this test verifies the app boots correctly against a real
Postgres and the endpoint responds as expected.
"""
from __future__ import annotations

from starlette.testclient import TestClient


def test_health_returns_200(admin_app: TestClient) -> None:
    response = admin_app.get("/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
