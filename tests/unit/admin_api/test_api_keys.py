"""
Unit tests: Service API key CRUD endpoints.

POST   /v1/tenants/{tid}/agents/{aid}/api-keys            — create (201)
GET    /v1/tenants/{tid}/agents/{aid}/api-keys            — list   (200)
GET    /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}      — get    (200)
POST   /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/revoke  — revoke (200)
POST   /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}/rotate  — rotate (201)

Test cases (Tasks 7.1–7.6; long-lived-api-keys spec):
  1.  Create: allowed_actions ⊄ grants → 422 api_key_actions_exceed_grant
  2.  Create: require_expiry=True, no expiry → 422 api_key_policy_violation
  3.  Create: require_ip_allowlist=True, no source_ip_allowlist → 422 api_key_policy_violation
  4.  Create: max_expiry_days exceeded → 422 api_key_policy_violation
  5.  Create: happy path → 201, body has plaintext_key (mk_svckey_ prefix), key_fingerprint, api_key_id
  6.  Create: plaintext absent from audit payload (no plaintext in key_hash or audit record)
  7.  Create: agent not found → 404
  8.  List: returns list of keys without plaintext
  9.  Get: returns single key without plaintext
  10. Get: absent key → 404
  11. Revoke: happy path → 200; audit api_key.revoked emitted; NOTIFY mintkey:agent
  12. Revoke: already revoked → 200 (idempotent)
  13. Revoke: absent key → 404
  14. Rotate: happy path → 201; new plaintext returned; audit api_key.rotated; old key not revoked
  15. proxy.hit internal endpoint: accepts auth_method/api_key_id/key_fingerprint/used_at

Sources:
  - long-lived-api-keys requirements 1.1–1.6, 4.1, 4.5, 5.1–5.2, 8.1–8.7, 10.4, 10.5
  - ADR-0018 §1–§2
  - ADR-0008 (RLS + bound params)
  - ADR-0014.7 (audit chokepoint)
  - ADR-0017.11 (ULID prefixes)
"""
from __future__ import annotations

import json
import sys
import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
AGENT_ID = "agent_00000000000000000000000001"
SVC_ID = "svc_00000000000000000000000001"
KEY_ID = "svckey_00000000000000000000000001"
BASE_URL = f"/v1/tenants/{TENANT_ID}/agents/{AGENT_ID}/api-keys"
KEY_URL = f"{BASE_URL}/{KEY_ID}"

_FUTURE_DT = datetime.now(timezone.utc) + timedelta(days=30)
_FUTURE = _FUTURE_DT.isoformat()

# ---------------------------------------------------------------------------
# Helpers to convert wire-form IDs to DB-form UUIDs for mock row construction.
# The DB stores UUIDs; row.id must be a UUID string so db_uuid_to_wire works.
# ---------------------------------------------------------------------------


def _wire_to_uuid(wire_id: str, prefix: str) -> str:
    """Decode <prefix>_<26Crockford> → dashed UUID string (for mock row IDs)."""
    _CROCKFORD_ALT = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
    tail = wire_id[len(prefix) + 1:]
    val = 0
    for ch in tail.upper():
        val = (val << 5) | _CROCKFORD_ALT.index(ch)
    val &= (1 << 128) - 1
    h = f"{val:032x}"
    return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"


# Pre-decoded UUID strings for mock rows (DB stores UUIDs, not wire IDs)
_AGENT_UUID = _wire_to_uuid(AGENT_ID, "agent")
_SVC_UUID = _wire_to_uuid(SVC_ID, "svc")
_KEY_UUID = _wire_to_uuid(KEY_ID, "svckey")


def _make_mock_row(
    *,
    key_id: str = KEY_ID,    # wire-form (for test reference); row.id is decoded UUID
    agent_id: str = AGENT_ID,
    service_id: str = SVC_ID,
    key_hash: str = "hash",
    key_fingerprint: str = "abcd1234",
    allowed_actions: list | None = None,
    constraints: dict | None = None,
    expires_at: datetime | None = None,
    revoked_at: datetime | None = None,
    created_at: datetime | None = None,
):
    row = MagicMock()
    # Store DB-form UUIDs on row (as the real DB would) — #13 fix
    row.id = _wire_to_uuid(key_id, "svckey")
    row.agent_id = agent_id   # agent_id stays as wire form (tests pass it through)
    row.service_id = _wire_to_uuid(service_id, "svc") if service_id.startswith("svc_") else service_id
    row.key_hash = key_hash
    row.key_fingerprint = key_fingerprint
    row.allowed_actions = allowed_actions or ["read:items"]
    row.constraints = json.dumps(constraints) if constraints else None
    row.expires_at = expires_at
    row.revoked_at = revoked_at
    row.last_used_at = None
    row.created_at = created_at or datetime.now(timezone.utc)
    row.created_by = "operator"
    return row


class _MockDb:
    """Configurable mock DB session for api-keys tests."""

    def __init__(
        self,
        *,
        agent_exists: bool = True,
        grants: list[str] | None = None,
        existing_key=None,
        key_list: list | None = None,
        settings_row=None,
    ):
        self.agent_exists = agent_exists
        self.grants = grants if grants is not None else ["read:items", "write:items"]
        self.existing_key = existing_key
        self.key_list = key_list or []
        self.settings_row = settings_row
        self._call = 0
        self.execute_calls: list = []

    async def execute(self, stmt, params=None):
        self._call += 1
        self.execute_calls.append((str(stmt), params))
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []

        stmt_str = str(stmt).lower()

        if "set_config" in stmt_str:
            pass  # tenant context set
        elif "select" in stmt_str and "agents" in stmt_str:
            if self.agent_exists:
                row = MagicMock()
                row.id = AGENT_ID
                result.fetchone.return_value = row
        elif "select" in stmt_str and "services" in stmt_str:
            # R12: api_keys.py verifies service exists before grants check.
            # Return a mock row so the service-lookup succeeds.
            row = MagicMock()
            row.id = _SVC_UUID
            result.fetchone.return_value = row
        elif "select" in stmt_str and "permission_grants" in stmt_str:
            rows = [MagicMock(action=a) for a in self.grants]
            result.fetchall.return_value = rows
        elif "select" in stmt_str and "admin_settings" in stmt_str:
            if self.settings_row:
                result.fetchone.return_value = self.settings_row
        elif "select" in stmt_str and "service_api_keys" in stmt_str:
            if "limit 1" in stmt_str or "where id" in stmt_str:
                result.fetchone.return_value = self.existing_key
            else:
                result.fetchall.return_value = self.key_list
        return result

    def begin_nested(self):
        """Return a no-op async context manager so _load_api_key_settings works."""
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    async def commit(self):
        pass

    async def rollback(self):
        pass


def _build_settings(
    require_expiry: bool = False,
    allow_no_expiry: bool = True,
    max_expiry_days: int = 365,
    require_ip_allowlist: bool = False,
    proxy_cache_ttl_seconds: int = 60,
):
    row = MagicMock()
    row.value = json.dumps({
        "api_key": {
            "proxy_cache_ttl_seconds": proxy_cache_ttl_seconds,
            "require_expiry": require_expiry,
            "allow_no_expiry": allow_no_expiry,
            "max_expiry_days": max_expiry_days,
            "require_ip_allowlist": require_ip_allowlist,
        }
    })
    return row


def _create_app(db: _MockDb):
    from fastapi import FastAPI
    from fastapi.exceptions import RequestValidationError
    from admin_api.api.api_keys import router as api_keys_router
    from admin_api.api.permissions import validation_error_handler
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(api_keys_router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)

    async def mock_db():
        yield db

    app.dependency_overrides[get_db_session] = mock_db

    csrf_exempt(BASE_URL)
    csrf_exempt(KEY_URL)
    csrf_exempt(f"{KEY_URL}/revoke")
    csrf_exempt(f"{KEY_URL}/rotate")

    app.add_middleware(CsrfMiddleware)
    return app


# ---------------------------------------------------------------------------
# Test 1: allowed_actions ⊄ grants → 422 api_key_actions_exceed_grant
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_actions_exceed_grant():
    """Req 1.3: allowed_actions must be a subset of the agent's permission grants."""
    db = _MockDb(grants=["read:items"])
    app = _create_app(db)

    with patch("admin_api.api.api_keys.audit_emit", new=AsyncMock()), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(BASE_URL, json={
                "service_id": SVC_ID,
                "allowed_actions": ["read:items", "write:items"],  # write not in grants
            })

    assert resp.status_code == 422, resp.text
    assert resp.json()["mintkey:code"] == "api_key_actions_exceed_grant"


# ---------------------------------------------------------------------------
# Test 2: require_expiry=True, no expiry → 422 api_key_policy_violation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_require_expiry_violation():
    """Req 10.4: When operator policy requires expiry, creating without expires_at → 422."""
    db = _MockDb(settings_row=_build_settings(require_expiry=True, allow_no_expiry=False))
    app = _create_app(db)

    with patch("admin_api.api.api_keys.audit_emit", new=AsyncMock()), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(BASE_URL, json={
                "service_id": SVC_ID,
                "allowed_actions": ["read:items"],
                # no expires_at
            })

    assert resp.status_code == 422, resp.text
    assert resp.json()["mintkey:code"] == "api_key_policy_violation"


# ---------------------------------------------------------------------------
# Test 3: require_ip_allowlist=True, no source_ip_allowlist → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_require_ip_allowlist_violation():
    """Req 10.4: When operator policy requires IP allowlist, omitting it → 422."""
    db = _MockDb(settings_row=_build_settings(require_ip_allowlist=True))
    app = _create_app(db)

    with patch("admin_api.api.api_keys.audit_emit", new=AsyncMock()), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(BASE_URL, json={
                "service_id": SVC_ID,
                "allowed_actions": ["read:items"],
                # no source_ip_allowlist in constraints
            })

    assert resp.status_code == 422, resp.text
    assert resp.json()["mintkey:code"] == "api_key_policy_violation"


# ---------------------------------------------------------------------------
# Test 4: max_expiry_days exceeded → 422
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_max_expiry_days_exceeded():
    """Req 10.4: expires_at beyond max_expiry_days policy → 422."""
    db = _MockDb(settings_row=_build_settings(max_expiry_days=7))
    app = _create_app(db)

    far_future = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()

    with patch("admin_api.api.api_keys.audit_emit", new=AsyncMock()), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(BASE_URL, json={
                "service_id": SVC_ID,
                "allowed_actions": ["read:items"],
                "expires_at": far_future,
            })

    assert resp.status_code == 422, resp.text
    assert resp.json()["mintkey:code"] == "api_key_policy_violation"


# ---------------------------------------------------------------------------
# Test 5: Happy path → 201 with plaintext_key (mk_svckey_ prefix)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_happy_path():
    """Req 1.1, 1.2, 8.1: Create returns 201 with plaintext_key having mk_svckey_ prefix."""
    db = _MockDb()
    app = _create_app(db)

    mock_audit = AsyncMock()
    with patch("admin_api.api.api_keys.audit_emit", new=mock_audit), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(BASE_URL, json={
                "service_id": SVC_ID,
                "allowed_actions": ["read:items"],
                "expires_at": _FUTURE,
            })

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "plaintext_key" in body
    assert body["plaintext_key"].startswith("mk_svckey_"), body["plaintext_key"]
    assert "api_key_id" in body
    assert body["api_key_id"].startswith("svckey_"), body["api_key_id"]
    assert "key_fingerprint" in body
    assert len(body["key_fingerprint"]) == 16  # hex(sha256[:8])


# ---------------------------------------------------------------------------
# Test 6: Plaintext absent from audit payload (ADR-0018; Req 10.1)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_no_plaintext_in_audit():
    """Req 10.1, 10.7: The plaintext key must NOT appear in the audit event payload."""
    db = _MockDb()
    app = _create_app(db)

    captured_audit_calls: list = []

    async def capture_audit(**kwargs):
        captured_audit_calls.append(kwargs)

    with patch("admin_api.api.api_keys.audit_emit", side_effect=capture_audit), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(BASE_URL, json={
                "service_id": SVC_ID,
                "allowed_actions": ["read:items"],
            })

    assert resp.status_code == 201, resp.text
    plaintext = resp.json()["plaintext_key"]

    for call in captured_audit_calls:
        payload_str = json.dumps(call.get("payload", {}))
        assert plaintext not in payload_str, "plaintext_key must not appear in audit payload"
        assert "mk_svckey_" not in payload_str or "key_fingerprint" in payload_str


# ---------------------------------------------------------------------------
# Test 7: Agent not found → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_not_found():
    db = _MockDb(agent_exists=False)
    app = _create_app(db)

    with patch("admin_api.api.api_keys.audit_emit", new=AsyncMock()), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(BASE_URL, json={
                "service_id": SVC_ID,
                "allowed_actions": ["read:items"],
            })

    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Test 8: List returns keys without plaintext
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_returns_keys_without_plaintext():
    """Req 8.2: List endpoint returns keys; plaintext never returned."""
    rows = [_make_mock_row(key_id="svckey_00000000000000000000000001"),
            _make_mock_row(key_id="svckey_00000000000000000000000002"),
            ]
    db = _MockDb(key_list=rows)
    app = _create_app(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(BASE_URL)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    assert len(body) == 2
    for item in body:
        assert "plaintext_key" not in item
        assert "key_hash" not in item
        assert "key_fingerprint" in item


# ---------------------------------------------------------------------------
# Test 9: Get single key without plaintext
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_single_key():
    """Req 8.3: Get single key; plaintext never returned."""
    db = _MockDb(existing_key=_make_mock_row())
    app = _create_app(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(KEY_URL)

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "plaintext_key" not in body
    assert "key_hash" not in body
    assert "api_key_id" in body or "id" in body


# ---------------------------------------------------------------------------
# Test 10: Get absent key → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_absent_key():
    db = _MockDb(existing_key=None)
    app = _create_app(db)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get(KEY_URL)

    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Test 11: Revoke happy path → 200, audit, NOTIFY
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_happy_path():
    """Req 4.1, 8.4: Revoke emits audit + NOTIFY; returns 200."""
    db = _MockDb(existing_key=_make_mock_row())
    app = _create_app(db)

    mock_audit = AsyncMock()
    mock_notify = AsyncMock()
    with patch("admin_api.api.api_keys.audit_emit", new=mock_audit), \
         patch("admin_api.api.api_keys.notify_change", new=mock_notify):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"{KEY_URL}/revoke", json={"reason": "test"})

    assert resp.status_code == 200, resp.text
    assert mock_audit.called
    assert mock_notify.called

    # Verify NOTIFY carries api_key.revoked on mintkey:agent — ADR-0014.1
    notify_args = mock_notify.call_args
    channel = notify_args.args[1] if notify_args.args else notify_args.kwargs.get("channel", "")
    payload_arg = notify_args.args[2] if len(notify_args.args) > 2 else notify_args.kwargs.get("payload", {})
    assert channel == "mintkey:agent"
    assert payload_arg.get("event") == "api_key.revoked"
    assert "key_fingerprint" in payload_arg


# ---------------------------------------------------------------------------
# Test 12: Revoke already-revoked → 200 (idempotent)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_idempotent():
    """Req 4.5: Already-revoked key → 200 (no error)."""
    already_revoked = _make_mock_row(revoked_at=datetime.now(timezone.utc))
    db = _MockDb(existing_key=already_revoked)
    app = _create_app(db)

    with patch("admin_api.api.api_keys.audit_emit", new=AsyncMock()), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"{KEY_URL}/revoke", json={"reason": "repeat"})

    assert resp.status_code == 200, resp.text


# ---------------------------------------------------------------------------
# Test 13: Revoke absent key → 404
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_revoke_absent_key():
    db = _MockDb(existing_key=None)
    app = _create_app(db)

    with patch("admin_api.api.api_keys.audit_emit", new=AsyncMock()), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"{KEY_URL}/revoke", json={"reason": "nope"})

    assert resp.status_code == 404, resp.text


# ---------------------------------------------------------------------------
# Test 14: Rotate happy path → 201, new plaintext, old key NOT revoked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotate_happy_path():
    """Req 5.1, 5.2, 8.5: Rotate returns new plaintext; old key is not revoked."""
    existing = _make_mock_row(expires_at=_FUTURE_DT)
    db = _MockDb(existing_key=existing)
    app = _create_app(db)

    mock_audit = AsyncMock()
    with patch("admin_api.api.api_keys.audit_emit", new=mock_audit), \
         patch("admin_api.api.api_keys.notify_change", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(f"{KEY_URL}/rotate")

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert "plaintext_key" in body
    assert body["plaintext_key"].startswith("mk_svckey_")
    assert body["api_key_id"] != KEY_ID  # new key

    # Old key must not be revoked — Req 5.2
    audit_event_types = [c.kwargs.get("event_type") for c in mock_audit.call_args_list]
    assert "api_key.revoked" not in audit_event_types

    # Audit api_key.rotated emitted with old/new ids
    assert "api_key.rotated" in audit_event_types
    rotated_call = next(c for c in mock_audit.call_args_list if c.kwargs.get("event_type") == "api_key.rotated")
    payload = rotated_call.kwargs.get("payload", {})
    assert payload.get("old_api_key_id") == KEY_ID


# ---------------------------------------------------------------------------
# Test 15: proxy.hit internal endpoint accepts new api-key fields
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_internal_proxy_hit_accepts_api_key_fields():
    """Req 8.7, 10.5: proxy.hit accepts auth_method/api_key_id/key_fingerprint/used_at."""
    from fastapi import FastAPI
    from admin_api.api.internal import router as internal_router
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    db = _MockDb()
    app2 = FastAPI()
    app2.include_router(internal_router)

    async def mock_db():
        yield db

    app2.dependency_overrides[get_db_session] = mock_db
    csrf_exempt("/v1/internal/proxy-hit")
    app2.add_middleware(CsrfMiddleware)

    now = datetime.now(timezone.utc).isoformat()
    with patch("admin_api.api.internal.audit_emit", new=AsyncMock()):
        async with AsyncClient(transport=ASGITransport(app=app2), base_url="http://test") as c:
            resp = await c.post("/v1/internal/proxy-hit", json={
                "service_id": SVC_ID,
                "status_code": 200,
                "method": "GET",
                "path_template": "/items",
                "latency_ms": 42,
                "auth_method": "api_key",
                "api_key_id": KEY_ID,
                "key_fingerprint": "abcd1234",
                "used_at": now,
            })

    assert resp.status_code == 200, resp.text
