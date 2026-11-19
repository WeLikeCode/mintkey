"""
Unit tests: Audit chain on-demand verification endpoint.

POST /v1/admin/audit/verify-chain (PlatformAdmin only)

Test cases:
  1. test_verify_chain_ok: mock 5-event intact chain → ok=true
  2. test_verify_chain_tampered: mock tampered chain → ok=false with first_bad_event_id
  3. test_verify_chain_requires_platform_admin: no header → 403
  4. test_verify_chain_tenant_id_param: must specify tenant_id → verifies only that tenant

Sources:
  - ADR-0014.7 (hash chain mandatory)
  - Req AUD-4 (chain verification)
  - T-1.13.3
"""
from __future__ import annotations

import sys
import os
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

from mintkey_models.audit_hash import (  # noqa: E402
    canonical_event_fields,
    canonical_json_bytes,
    chain_hash,
    genesis_hash,
)

VERIFY_URL = "/v1/admin/audit/verify-chain"
TENANT_ID = "tenant_00000000000000000000000001"


async def _noop_platform_admin():
    """Dep override: treat all callers as platform-admin."""
    return None


# ---------------------------------------------------------------------------
# Chain helpers (the canonical form shared with the writer and verifiers)
# ---------------------------------------------------------------------------


def _build_chain_rows(n: int, tenant_id: str = TENANT_ID):
    """Return a list of rows with a valid hash chain, as Postgres returns them."""
    rows = []
    prev = genesis_hash(str(tenant_id))
    for i in range(n):
        payload = {"seq": i}
        at = datetime(2025, 1, 1, tzinfo=timezone.utc) + timedelta(seconds=i)
        fields = canonical_event_fields(
            event_id=f"audit_evt_{i:03d}",
            tenant_id=tenant_id,
            event_type="test.event",
            actor_id=None,
            actor_type="system",
            target_id=None,
            target_type=None,
            payload=payload,
            at=at,
        )
        h = chain_hash(canonical_json_bytes(fields), prev)
        row = SimpleNamespace(
            id=f"audit_evt_{i:03d}",
            tenant_id=tenant_id,
            event_type="test.event",
            actor_id=None,
            actor_type="system",
            target_id=None,
            target_type=None,
            payload=payload,
            at=at,
            prev_hash=prev,
            hash=h,
            request_id=None,
            trace_id=None,
        )
        rows.append(row)
        prev = h
    return rows


def _build_tampered_chain_rows(n: int, tamper_index: int = 2, tenant_id: str = TENANT_ID):
    """Return rows with the event at tamper_index having a corrupted payload."""
    rows = _build_chain_rows(n, tenant_id)
    bad = rows[tamper_index]
    # Corrupt payload but leave stored hash unchanged → mismatch on recompute
    bad.payload = {"seq": 999, "data": "tampered"}
    return rows


# ---------------------------------------------------------------------------
# Test app factory
# ---------------------------------------------------------------------------


def _make_mock_session(rows=None):
    session = MagicMock()

    async def _execute(*args, **kwargs):
        result = MagicMock()
        result.fetchall.return_value = rows or []
        result.fetchone.return_value = None
        return result

    session.execute = _execute
    return session


def _create_test_app(rows=None):
    from fastapi import FastAPI
    from admin_api.api.audit_admin import router as audit_admin_router
    from admin_api.auth.sessions import require_platform_admin_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(audit_admin_router)

    async def mock_db_session():
        yield _make_mock_session(rows=rows)

    app.dependency_overrides[get_db_session] = mock_db_session
    app.dependency_overrides[require_platform_admin_session] = _noop_platform_admin

    csrf_exempt(VERIFY_URL)
    app.add_middleware(CsrfMiddleware)
    return app


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_chain_ok() -> None:
    """
    POST /v1/admin/audit/verify-chain with an intact 5-event chain
    returns {"ok": true, "chain_length": 5, "last_event_id": ..., "verified_at": ...}.
    Source: T-1.13.3; Req AUD-4.
    """
    rows = _build_chain_rows(5)
    app = _create_test_app(rows=rows)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            VERIFY_URL,
            params={"tenant_id": TENANT_ID},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["chain_length"] == 5
    assert body["last_event_id"] == rows[-1].id
    assert "verified_at" in body


@pytest.mark.asyncio
async def test_verify_chain_tampered() -> None:
    """
    POST /v1/admin/audit/verify-chain with a tampered chain returns
    {"ok": false, "first_bad_event_id": ..., "expected_hash": ..., "actual_hash": ...}.
    Source: T-1.13.3; Req AUD-4.
    """
    rows = _build_tampered_chain_rows(5, tamper_index=2)
    app = _create_test_app(rows=rows)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            VERIFY_URL,
            params={"tenant_id": TENANT_ID},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is False
    assert body["first_bad_event_id"] == "audit_evt_002"
    assert "expected_hash" in body
    assert "actual_hash" in body


@pytest.mark.asyncio
async def test_verify_chain_requires_platform_admin() -> None:
    """
    POST /v1/admin/audit/verify-chain without a valid platform-admin session returns 401.
    Session-based authz (ADR-0027 §D2) — no session cookie → 401.
    Source: T-1.13.3.
    """
    from fastapi import FastAPI
    from admin_api.api.audit_admin import router as audit_admin_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    # No dep override — real require_platform_admin_session; no cookie → 401
    app_no_auth = FastAPI()
    app_no_auth.include_router(audit_admin_router)

    async def mock_db_session():
        yield _make_mock_session(rows=[])

    app_no_auth.dependency_overrides[get_db_session] = mock_db_session
    csrf_exempt(VERIFY_URL)
    app_no_auth.add_middleware(CsrfMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app_no_auth), base_url="http://test") as client:
        resp = await client.post(
            VERIFY_URL,
            params={"tenant_id": TENANT_ID},
        )

    assert resp.status_code == 401, resp.text
    body = resp.json()
    detail = body.get("detail", body)
    assert detail.get("mintkey:code") == "unauthenticated"


@pytest.mark.asyncio
async def test_verify_chain_tenant_id_param() -> None:
    """
    POST /v1/admin/audit/verify-chain?tenant_id=... only verifies that tenant's events.
    The DB query must include the tenant_id filter.
    Source: T-1.13.3; ADR-0008.
    """
    rows = _build_chain_rows(3, tenant_id=TENANT_ID)
    session = _make_mock_session(rows=rows)

    from fastapi import FastAPI
    from admin_api.api.audit_admin import router as audit_admin_router
    from admin_api.auth.sessions import require_platform_admin_session
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(audit_admin_router)

    captured_params = []

    async def _execute(*args, **kwargs):
        if args:
            captured_params.append(args)
        result = MagicMock()
        result.fetchall.return_value = rows
        result.fetchone.return_value = None
        return result

    session.execute = _execute

    async def mock_db_session():
        yield session

    app.dependency_overrides[get_db_session] = mock_db_session
    app.dependency_overrides[require_platform_admin_session] = _noop_platform_admin
    csrf_exempt(VERIFY_URL)
    app.add_middleware(CsrfMiddleware)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post(
            VERIFY_URL,
            params={"tenant_id": TENANT_ID},
        )

    assert resp.status_code == 200, resp.text
    # Verify that tenant_id was passed as a bound parameter — at least one execute call
    assert len(captured_params) >= 1
    # Find the call that included the tenant_id bound param
    found_tenant_param = False
    for call_args in captured_params:
        if len(call_args) >= 2 and isinstance(call_args[1], dict):
            if call_args[1].get("tenant_id") == TENANT_ID:
                found_tenant_param = True
                break
    assert found_tenant_param, "tenant_id must be passed as a bound parameter to the DB query"
