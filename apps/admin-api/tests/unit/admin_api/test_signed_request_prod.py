"""
Tests for AdminUiSignedRequestMiddleware production enforcement.

Source: openspec/changes/kubernetes-readiness/specs/admin-ui-key-bootstrap/spec.md
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import PlainTextResponse

from admin_api.auth.signed_request import AdminUiSignedRequestMiddleware


def _make_app(public_key=None) -> FastAPI:
    app = FastAPI()
    app.add_middleware(AdminUiSignedRequestMiddleware, public_key=public_key)

    @app.post("/write")
    async def write_endpoint():
        return PlainTextResponse("ok")

    return app


class TestProductionEnforcement:
    def test_production_no_key_rejects_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MINTKEY_ENV", "production")
        client = TestClient(_make_app(public_key=None), raise_server_exceptions=False)
        resp = client.post("/write")
        assert resp.status_code == 401
        assert resp.json()["code"] == "mintkey:signed_request_required"

    def test_dev_no_key_allows_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("MINTKEY_ENV", "dev")
        client = TestClient(_make_app(public_key=None), raise_server_exceptions=False)
        resp = client.post("/write")
        assert resp.status_code == 200
