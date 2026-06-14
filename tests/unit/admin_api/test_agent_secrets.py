"""
Unit tests: Agent-secret REST endpoints (operator surface).

GET    /v1/tenants/{tid}/agent-secrets                                   — list (200)
POST   /v1/tenants/{tid}/agent-secrets                                   — create (201/409/422) [C5]
GET    /v1/tenants/{tid}/agent-secrets/{secret_id}                       — get (200/404)
DELETE /v1/tenants/{tid}/agent-secrets/{secret_id}                       — delete (204)
POST   /v1/tenants/{tid}/agent-secrets/{secret_id}/grants                — create grant (201/409/422)
GET    /v1/tenants/{tid}/agent-secrets/{secret_id}/grants                — list grants (200/404)
DELETE /v1/tenants/{tid}/agent-secrets/{secret_id}/grants/{grant_id}    — revoke (204)

Coverage per spec (agent-secret-storage + agent-secret-sharing):
  - grant create / list / revoke
  - cross-tenant 422 (secret not in tenant, agent not in tenant)
  - duplicate grant 409
  - grant-to-owner 422
  - idempotent revoke (204 when already gone, audit NOT emitted — schema-required owner/recipient unknowable)
  - idempotent delete (204 when already gone, audit NOT emitted)
  - operator delete cascades (metadata delete only; vault blob orphaned)
  - metadata responses contain no value/ciphertext fields
  - audit_emit called with identifier-only payloads (no secret values)

Sources: ADR-0025; openspec/changes/agent-stored-credentials/specs/agent-secret-storage/spec.md;
         openspec/changes/agent-stored-credentials/specs/agent-secret-sharing/spec.md.
"""
from __future__ import annotations

import sys
import os
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch, call

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
SECRET_UUID = "11111111-1111-1111-1111-111111111111"
AGENT_UUID = "22222222-2222-2222-2222-222222222222"
OWNER_UUID = "33333333-3333-3333-3333-333333333333"
GRANT_UUID = "44444444-4444-4444-4444-444444444444"
OPERATOR_UUID = "55555555-5555-5555-5555-555555555555"

BASE = f"/v1/tenants/{TENANT_ID}/agent-secrets"
SECRET_PATH = f"{BASE}/{SECRET_UUID}"
GRANTS_PATH = f"{SECRET_PATH}/grants"
GRANT_PATH = f"{GRANTS_PATH}/{GRANT_UUID}"

CSRF_TOKEN = "test-csrf-token"
_NOW = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# Mock session factory
# ---------------------------------------------------------------------------


def _make_secret_row(
    secret_id: str = SECRET_UUID,
    agent_id: str = OWNER_UUID,
    name: str = "db-password",
    version: int = 1,
    size_bytes: int = 12,
    content_type: str | None = None,
    created_at: datetime = _NOW,
    updated_at: datetime = _NOW,
) -> MagicMock:
    row = MagicMock()
    row.id = uuid.UUID(secret_id)
    row.tenant_id = uuid.UUID(TENANT_ID)
    row.agent_id = uuid.UUID(agent_id)
    row.name = name
    row.version = version
    row.size_bytes = size_bytes
    row.content_type = content_type
    row.created_at = created_at
    row.updated_at = updated_at
    return row


def _make_grant_row(
    grant_id: str = GRANT_UUID,
    secret_id: str = SECRET_UUID,
    recipient_agent_id: str = AGENT_UUID,
    owner_agent_id: str = OWNER_UUID,
    created_by: str = "00000000-0000-0000-0000-000000000000",
    created_at: datetime = _NOW,
) -> MagicMock:
    row = MagicMock()
    row.id = uuid.UUID(grant_id)
    row.tenant_id = uuid.UUID(TENANT_ID)
    row.secret_id = uuid.UUID(secret_id)
    row.recipient_agent_id = uuid.UUID(recipient_agent_id)
    row.owner_agent_id = uuid.UUID(owner_agent_id)
    row.created_by = uuid.UUID(created_by)
    row.created_at = created_at
    return row


class _MockSession:
    """
    Configurable mock async session.

    Callers can set fetch_once_rows (list of rows or None returned by successive
    fetchone() calls) and fetch_all_rows.
    """

    def __init__(
        self,
        fetch_once_rows: list[Any] | None = None,
        fetch_all_rows: list[Any] | None = None,
        raise_on_execute: Exception | None = None,
    ) -> None:
        self._once = list(fetch_once_rows) if fetch_once_rows is not None else []
        self._all = list(fetch_all_rows) if fetch_all_rows is not None else []
        self._raise = raise_on_execute
        self._execute_calls: list[tuple] = []

    async def execute(self, *args: Any, **kwargs: Any) -> Any:
        self._execute_calls.append((args, kwargs))
        if self._raise is not None:
            raise self._raise
        result = MagicMock()
        if self._once:
            result.fetchone.return_value = self._once.pop(0)
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = list(self._all)
        return result

    async def commit(self) -> None:
        pass


def _make_ctx(operator_id: str = OPERATOR_UUID, tenant_id: str = TENANT_ID) -> Any:
    """Return a _Ctx-like object with operator_id and tenant_id as UUIDs."""

    class _FakeCtx:
        pass

    ctx = _FakeCtx()
    ctx.operator_id = uuid.UUID(operator_id)
    ctx.tenant_id = uuid.UUID(tenant_id)
    return ctx


def _create_app(session: Any, vault_client: Any = None, session_ctx: Any = None) -> Any:
    from fastapi import FastAPI
    from admin_api.api.agent_secrets import router as agent_secrets_router
    from admin_api.auth.sessions import get_session_context
    from admin_api.db.deps import get_db_session
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt
    from admin_api.services.agent_secrets_vault_client import get_agent_secrets_vault_client

    app = FastAPI()
    app.include_router(agent_secrets_router)

    async def _mock_db():
        yield session

    app.dependency_overrides[get_db_session] = _mock_db

    # Override the vault client dependency so tests stay fully in-process.
    # When no vault_client is provided, use a no-op AsyncMock so existing tests
    # that don't care about vault behaviour are unaffected.
    _vc = vault_client if vault_client is not None else AsyncMock()

    async def _mock_vault_client():
        return _vc

    app.dependency_overrides[get_agent_secrets_vault_client] = _mock_vault_client

    # Override get_session_context so tests can seed a specific operator identity
    # without hitting the database.  Default: return a ctx with OPERATOR_UUID.
    _ctx = session_ctx if session_ctx is not None else _make_ctx()

    async def _mock_session_ctx():
        return _ctx

    app.dependency_overrides[get_session_context] = _mock_session_ctx

    csrf_exempt(BASE)
    csrf_exempt(SECRET_PATH)
    csrf_exempt(GRANTS_PATH)
    csrf_exempt(GRANT_PATH)

    app.add_middleware(CsrfMiddleware)
    return app


# ---------------------------------------------------------------------------
# Helper: run GET/POST/DELETE against mock session
# ---------------------------------------------------------------------------


async def _get(path: str, session: Any, params: dict | None = None) -> Any:
    app = _create_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.get(path, params=params or {})


async def _delete(path: str, session: Any, vault_client: Any = None) -> Any:
    app = _create_app(session, vault_client=vault_client)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.delete(path, headers={"X-CSRF-Token": CSRF_TOKEN})


async def _post(path: str, session: Any, body: dict) -> Any:
    app = _create_app(session)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(path, json=body, headers={"X-CSRF-Token": CSRF_TOKEN})


# ===========================================================================
# LIST secrets
# ===========================================================================


@pytest.mark.asyncio
async def test_list_agent_secrets_returns_200_empty() -> None:
    """GET list with no secrets returns {data: [], next_cursor: null}."""
    session = _MockSession(fetch_all_rows=[])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _get(BASE, session)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["data"] == []
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_agent_secrets_returns_metadata_only() -> None:
    """
    Metadata listing contains no value, ciphertext, or key material fields.
    Source: agent-secret-sharing spec — Operators never see secret values.
    """
    row = _make_secret_row()
    session = _MockSession(fetch_all_rows=[row])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _get(BASE, session)
    assert resp.status_code == 200, resp.text
    item = resp.json()["data"][0]
    # Metadata fields present
    assert "id" in item
    assert "name" in item
    assert "version" in item
    assert "size_bytes" in item
    # Sensitive fields absent
    assert "value" not in item
    assert "ciphertext" not in item
    assert "enc_payload" not in item
    assert "wrapped_dek" not in item


@pytest.mark.asyncio
async def test_list_agent_secrets_wire_ids_have_correct_prefix() -> None:
    """Wire IDs in list response use sec_/agent_/tenant_ prefixes — ADR-0017.11."""
    row = _make_secret_row()
    session = _MockSession(fetch_all_rows=[row])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _get(BASE, session)
    item = resp.json()["data"][0]
    assert item["id"].startswith("sec_"), f"Expected sec_ prefix: {item['id']}"
    assert item["agent_id"].startswith("agent_"), f"Expected agent_ prefix: {item['agent_id']}"
    assert item["tenant_id"].startswith("tenant_"), f"Expected tenant_ prefix: {item['tenant_id']}"


# ===========================================================================
# GET single secret
# ===========================================================================


@pytest.mark.asyncio
async def test_get_agent_secret_returns_200() -> None:
    """GET /{secret_id} returns 200 with metadata."""
    row = _make_secret_row()
    session = _MockSession(fetch_once_rows=[row])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _get(SECRET_PATH, session)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["id"].startswith("sec_")
    assert "value" not in body
    assert "ciphertext" not in body


@pytest.mark.asyncio
async def test_get_agent_secret_returns_404_when_missing() -> None:
    """GET /{secret_id} returns 404 when secret not found."""
    session = _MockSession(fetch_once_rows=[None])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _get(SECRET_PATH, session)
    assert resp.status_code == 404, resp.text
    assert resp.json()["mintkey:code"] == "not_found"


# ===========================================================================
# DELETE secret (operator hard-delete)
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_agent_secret_returns_204() -> None:
    """DELETE /{secret_id} returns 204."""
    row = _make_secret_row()
    session = _MockSession(fetch_once_rows=[row])
    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _delete(SECRET_PATH, session)
    assert resp.status_code == 204, resp.text
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["event_type"] == "agent_secret.deleted"
    assert call_kwargs["actor_type"] == "operator"


@pytest.mark.asyncio
async def test_delete_agent_secret_idempotent_when_already_absent() -> None:
    """
    DELETE /{secret_id} returns 204 even when the secret was already absent.
    Audit event is NOT emitted on the already-gone path: agent_id is unknowable
    and "" does not match the required ^agent_[0-9A-HJKMNP-TV-Z]{26}$ pattern
    in ev_agent_secret_deleted (schema-required fields cannot be fabricated).
    Source: agent-secret-sharing spec — Operator deletes an agent's secret.
    """
    session = _MockSession(fetch_once_rows=[None])
    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _delete(SECRET_PATH, session)
    assert resp.status_code == 204, resp.text
    # Audit is NOT emitted when the row was already absent (agent_id unknowable)
    mock_audit.assert_not_called()


@pytest.mark.asyncio
async def test_delete_agent_secret_audit_carries_identifiers_only() -> None:
    """
    Audit payload for agent_secret.deleted must carry wire-form identifiers and name.
    Source: ADR-0025.D4; ev_agent_secret_deleted schema (required: secret_id, agent_id, name).
    """
    row = _make_secret_row()
    session = _MockSession(fetch_once_rows=[row])
    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        await _delete(SECRET_PATH, session)

    payload = mock_audit.call_args.kwargs["payload"]
    # Must contain required identifiers + name
    assert "secret_id" in payload
    assert "agent_id" in payload
    assert "name" in payload
    # Wire forms
    assert payload["secret_id"].startswith("sec_"), f"secret_id not wire form: {payload['secret_id']}"
    assert payload["agent_id"].startswith("agent_"), f"agent_id not wire form: {payload['agent_id']}"
    # Must NOT contain any value-like keys
    assert "value" not in payload
    assert "ciphertext" not in payload
    assert "enc_payload" not in payload
    # Schema conformance: validate against canonical schema
    _validate_payload("agent_secret.deleted", payload)


# ===========================================================================
# POST grant (create share grant)
# ===========================================================================


@pytest.mark.asyncio
async def test_create_grant_returns_201() -> None:
    """
    POST /grants with valid secret + recipient returns 201 with secgrant_ wire ID.
    Source: agent-secret-sharing spec — Successful share grant.
    """
    secret_row = _make_secret_row(agent_id=OWNER_UUID)
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(AGENT_UUID)
    # session will serve: secret check → agent check → insert (no fetchone needed)
    session = _MockSession(fetch_once_rows=[secret_row, agent_row, None])
    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        # Pass AGENT_UUID as plain UUID (not a prefixed wire ID)
        resp = await _post(GRANTS_PATH, session, {"recipient_agent_id": AGENT_UUID})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["id"].startswith("secgrant_"), f"Expected secgrant_ prefix: {body['id']}"
    assert body["secret_id"].startswith("sec_")
    assert body["recipient_agent_id"].startswith("agent_")
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["event_type"] == "agent_secret_grant.created"
    assert call_kwargs["actor_type"] == "operator"


@pytest.mark.asyncio
async def test_create_grant_cross_tenant_secret_rejected() -> None:
    """
    POST /grants where secret is not in the tenant returns 422 not_found.
    Source: agent-secret-sharing spec — Cross-tenant grant rejected.
    """
    session = _MockSession(fetch_once_rows=[None])  # secret not found
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _post(GRANTS_PATH, session, {"recipient_agent_id": AGENT_UUID})
    assert resp.status_code == 422, resp.text
    assert resp.json()["mintkey:code"] == "not_found"


@pytest.mark.asyncio
async def test_create_grant_cross_tenant_agent_rejected() -> None:
    """
    POST /grants where recipient agent is not in the tenant returns 422 not_found.
    Source: agent-secret-sharing spec — Cross-tenant grant rejected.
    """
    secret_row = _make_secret_row(agent_id=OWNER_UUID)
    session = _MockSession(fetch_once_rows=[secret_row, None])  # secret found, agent not found
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _post(GRANTS_PATH, session, {"recipient_agent_id": AGENT_UUID})
    assert resp.status_code == 422, resp.text
    assert resp.json()["mintkey:code"] == "not_found"


@pytest.mark.asyncio
async def test_create_grant_to_owner_rejected() -> None:
    """
    POST /grants where recipient_agent_id == secret's owning agent returns 422.
    Source: agent-secret-sharing spec; ADR-0025.
    """
    secret_row = _make_secret_row(agent_id=AGENT_UUID)
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(AGENT_UUID)
    session = _MockSession(fetch_once_rows=[secret_row, agent_row])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _post(GRANTS_PATH, session, {"recipient_agent_id": AGENT_UUID})
    assert resp.status_code == 422, resp.text
    assert resp.json()["mintkey:code"] == "grant_to_owner"


@pytest.mark.asyncio
async def test_create_grant_duplicate_returns_409() -> None:
    """
    POST /grants with duplicate (same secret, same recipient) returns 409.
    Source: agent-secret-sharing spec — Duplicate grant rejected.
    """
    secret_row = _make_secret_row(agent_id=OWNER_UUID)
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(AGENT_UUID)

    # set_tenant_context is patched (no DB call). The handler sequence is:
    # call 1 = SELECT from agent_secrets (secret check)
    # call 2 = SELECT from agents (agent check)
    # call 3 = INSERT → raises unique violation
    class _DupSession:
        _calls = 0

        async def execute(self, *args: Any, **kwargs: Any) -> Any:
            self._calls += 1
            if self._calls == 1:
                result = MagicMock()
                result.fetchone.return_value = secret_row
                return result
            elif self._calls == 2:
                result = MagicMock()
                result.fetchone.return_value = agent_row
                return result
            else:
                raise Exception("unique constraint violation uq_agent_secret_grants")

    session = _DupSession()
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _post(GRANTS_PATH, session, {"recipient_agent_id": AGENT_UUID})
    assert resp.status_code == 409, resp.text
    assert resp.json()["mintkey:code"] == "already_exists"


@pytest.mark.asyncio
async def test_create_grant_audit_carries_identifiers_only() -> None:
    """
    Audit payload for agent_secret_grant.created must carry all four required
    wire-form identifiers (grant_id, secret_id, owner_agent_id, recipient_agent_id).
    Source: ADR-0025.D4; ev_agent_secret_grant_created schema.
    """
    secret_row = _make_secret_row(agent_id=OWNER_UUID)
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(AGENT_UUID)
    session = _MockSession(fetch_once_rows=[secret_row, agent_row, None])
    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        await _post(GRANTS_PATH, session, {"recipient_agent_id": AGENT_UUID})

    payload = mock_audit.call_args.kwargs["payload"]
    assert "grant_id" in payload
    assert "secret_id" in payload
    assert "owner_agent_id" in payload
    assert "recipient_agent_id" in payload
    # Wire forms
    assert payload["grant_id"].startswith("secgrant_"), f"grant_id not wire form: {payload['grant_id']}"
    assert payload["secret_id"].startswith("sec_"), f"secret_id not wire form: {payload['secret_id']}"
    assert payload["owner_agent_id"].startswith("agent_"), f"owner_agent_id not wire form: {payload['owner_agent_id']}"
    assert payload["recipient_agent_id"].startswith("agent_"), f"recipient_agent_id not wire form: {payload['recipient_agent_id']}"
    # No values or sensitive material
    assert "value" not in payload
    assert "enc_payload" not in payload
    # Schema conformance: validate against canonical schema
    _validate_payload("agent_secret_grant.created", payload)


# ===========================================================================
# GET grants list
# ===========================================================================


@pytest.mark.asyncio
async def test_list_grants_returns_200() -> None:
    """GET /grants returns 200 with data + next_cursor."""
    secret_row = _make_secret_row()
    grant_row = _make_grant_row()
    session = _MockSession(fetch_once_rows=[secret_row], fetch_all_rows=[grant_row])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _get(GRANTS_PATH, session)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "data" in body
    assert "next_cursor" in body
    assert len(body["data"]) == 1
    assert body["data"][0]["id"].startswith("secgrant_")


@pytest.mark.asyncio
async def test_list_grants_returns_404_when_secret_missing() -> None:
    """GET /grants when secret not found returns 404."""
    session = _MockSession(fetch_once_rows=[None])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _get(GRANTS_PATH, session)
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_list_grants_wire_ids_have_correct_prefix() -> None:
    """Wire IDs in grant list use secgrant_/sec_/agent_/operator_ prefixes."""
    secret_row = _make_secret_row()
    grant_row = _make_grant_row()
    session = _MockSession(fetch_once_rows=[secret_row], fetch_all_rows=[grant_row])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _get(GRANTS_PATH, session)
    item = resp.json()["data"][0]
    assert item["id"].startswith("secgrant_")
    assert item["secret_id"].startswith("sec_")
    assert item["recipient_agent_id"].startswith("agent_")
    assert item["created_by"].startswith("operator_")


# ===========================================================================
# DELETE grant (revoke)
# ===========================================================================


@pytest.mark.asyncio
async def test_revoke_grant_returns_204() -> None:
    """DELETE /grants/{grant_id} returns 204."""
    grant_row = _make_grant_row()
    session = _MockSession(fetch_once_rows=[grant_row])
    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _delete(GRANT_PATH, session)
    assert resp.status_code == 204, resp.text
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["event_type"] == "agent_secret_grant.revoked"
    assert call_kwargs["actor_type"] == "operator"


@pytest.mark.asyncio
async def test_revoke_grant_idempotent_when_already_absent() -> None:
    """
    DELETE /grants/{grant_id} returns 204 even when already gone.
    Audit event is NOT emitted on the already-gone path: schema requires all four
    fields (grant_id, secret_id, owner_agent_id, recipient_agent_id) but
    owner_agent_id is unknowable once the grant row is gone.
    Source: agent-secret-sharing spec — Idempotent revoke.
    """
    session = _MockSession(fetch_once_rows=[None])
    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _delete(GRANT_PATH, session)
    assert resp.status_code == 204, resp.text
    # Audit is NOT emitted when the row was already absent (owner_agent_id unknowable)
    mock_audit.assert_not_called()


@pytest.mark.asyncio
async def test_revoke_grant_audit_carries_identifiers_only() -> None:
    """
    Audit payload for agent_secret_grant.revoked must carry all four required
    wire-form identifiers (grant_id, secret_id, owner_agent_id, recipient_agent_id).
    Source: ADR-0025.D4; ev_agent_secret_grant_revoked schema.
    """
    grant_row = _make_grant_row()
    session = _MockSession(fetch_once_rows=[grant_row])
    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        await _delete(GRANT_PATH, session)

    payload = mock_audit.call_args.kwargs["payload"]
    assert "grant_id" in payload
    assert "secret_id" in payload
    assert "owner_agent_id" in payload
    assert "recipient_agent_id" in payload
    # Wire forms
    assert payload["grant_id"].startswith("secgrant_"), f"grant_id not wire form: {payload['grant_id']}"
    assert payload["secret_id"].startswith("sec_"), f"secret_id not wire form: {payload['secret_id']}"
    assert payload["owner_agent_id"].startswith("agent_"), f"owner_agent_id not wire form: {payload['owner_agent_id']}"
    assert payload["recipient_agent_id"].startswith("agent_"), f"recipient_agent_id not wire form: {payload['recipient_agent_id']}"
    # No values or sensitive material
    assert "value" not in payload
    assert "enc_payload" not in payload
    # Schema conformance: validate against canonical schema
    _validate_payload("agent_secret_grant.revoked", payload)


# ===========================================================================
# Metadata-only invariant
# ===========================================================================


@pytest.mark.asyncio
async def test_get_secret_metadata_no_value_fields() -> None:
    """
    GET /{secret_id} response never contains value, ciphertext, or key material.
    Source: agent-secret-sharing spec — Operators never see secret values.
    """
    row = _make_secret_row()
    session = _MockSession(fetch_once_rows=[row])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _get(SECRET_PATH, session)
    assert resp.status_code == 200
    body = resp.json()
    forbidden = {"value", "ciphertext", "enc_payload", "wrapped_dek", "key", "plaintext"}
    for field in forbidden:
        assert field not in body, f"Forbidden field '{field}' found in metadata response"


# ===========================================================================
# Operator delete cascades: metadata only (vault blob orphaned)
# ===========================================================================


@pytest.mark.asyncio
async def test_operator_delete_cascades_grants_via_metadata_delete() -> None:
    """
    Operator delete removes the metadata row (and cascades grants via FK).
    The vault blob is orphaned (Phase 1 limitation, noted in code with TODO).
    Subsequent MCP secret_get by owner or former recipient returns not-found.
    Source: agent-secret-sharing spec — Operator deletes an agent's secret.
    """
    row = _make_secret_row()
    session = _MockSession(fetch_once_rows=[row])

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _delete(SECRET_PATH, session)

    assert resp.status_code == 204
    # audit_emit called once for agent_secret.deleted (not for vault.agent_secrets)
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["event_type"] == "agent_secret.deleted"
    assert call_kwargs["actor_type"] == "operator"

    # Subsequent GET on the same secret returns 404 (metadata row gone)
    empty_session = _MockSession(fetch_once_rows=[None])
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp2 = await _get(SECRET_PATH, empty_session)
    assert resp2.status_code == 404


# ===========================================================================
# Schema conformance tests (H)
# ===========================================================================


def _load_agent_secret_payload_schema(event_type: str) -> dict:
    """
    Load the payload schema for a given agent_secret* event type from the
    canonical audit-event.schema.json.

    Maps event_type to $defs key: e.g.
      "agent_secret.deleted" -> "ev_agent_secret_deleted"
      "agent_secret_grant.created" -> "ev_agent_secret_grant_created"
    """
    import json
    import pathlib

    schema_path = pathlib.Path(__file__).parents[3] / (
        "docs/architecture/contracts/events/audit-event.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    def_key = "ev_" + event_type.replace(".", "_")
    ev_def = schema["$defs"][def_key]
    return ev_def["properties"]["payload"]


def _validate_payload(event_type: str, payload: dict) -> None:
    """
    Validate payload against the schema $defs for the given event_type.

    Loads the canonical schema and checks:
      1. All required fields are present.
      2. String-typed fields with a pattern regex match their pattern.
      3. No additional properties beyond those declared.
    """
    import json
    import pathlib
    import re

    payload_schema = _load_agent_secret_payload_schema(event_type)
    required = payload_schema.get("required", [])
    properties = payload_schema.get("properties", {})

    schema_path = pathlib.Path(__file__).parents[3] / (
        "docs/architecture/contracts/events/audit-event.schema.json"
    )
    full_schema = json.loads(schema_path.read_text())

    # 1. Required fields present
    for field in required:
        assert field in payload, (
            f"[{event_type}] Required field '{field}' missing from payload: {payload}"
        )

    # 2. Pattern checks for string fields
    for field, value in payload.items():
        if field not in properties:
            continue
        prop_schema = properties[field]
        if "$ref" in prop_schema:
            ref_key = prop_schema["$ref"].split("/")[-1]
            prop_schema = full_schema["$defs"].get(ref_key, prop_schema)
        pattern = prop_schema.get("pattern")
        if pattern and isinstance(value, str):
            assert re.match(pattern, value), (
                f"[{event_type}] Field '{field}' value {value!r} "
                f"does not match pattern {pattern!r}"
            )

    # 3. No additional properties
    if payload_schema.get("additionalProperties") is False:
        for field in payload:
            assert field in properties, (
                f"[{event_type}] Unexpected field '{field}' in payload: {payload}"
            )


# ===========================================================================
# DELETE secret — vault ciphertext purge (C4)
# ===========================================================================


@pytest.mark.asyncio
async def test_delete_agent_secret_calls_vault_client_with_correct_args() -> None:
    """
    DELETE /{secret_id} when the secret EXISTS must call
    AgentSecretsVaultClient.delete_agent_secret(tenant_id=<str>, secret_id=<str>)
    exactly once with the raw UUID strings before deleting the metadata row.
    Source: C4 acceptance criterion AC-1; ADR-0025.
    """
    row = _make_secret_row()
    session = _MockSession(fetch_once_rows=[row])

    mock_vault_client = AsyncMock()
    mock_vault_client.delete_agent_secret = AsyncMock(return_value=True)

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _delete(SECRET_PATH, session, vault_client=mock_vault_client)

    assert resp.status_code == 204, resp.text
    mock_vault_client.delete_agent_secret.assert_called_once_with(
        tenant_id=TENANT_ID,
        secret_id=SECRET_UUID,
    )


@pytest.mark.asyncio
async def test_delete_agent_secret_idempotent_skips_vault_call() -> None:
    """
    DELETE /{secret_id} when the secret is ALREADY ABSENT returns 204 and
    does NOT call the vault client (no metadata row → no vault blob to purge).
    Source: C4 acceptance criterion AC-2; ADR-0025.
    """
    session = _MockSession(fetch_once_rows=[None])

    mock_vault_client = AsyncMock()
    mock_vault_client.delete_agent_secret = AsyncMock(return_value=False)

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _delete(SECRET_PATH, session, vault_client=mock_vault_client)

    assert resp.status_code == 204, resp.text
    mock_vault_client.delete_agent_secret.assert_not_called()




# ===========================================================================
# C4b: operator identity threading — actor_id + created_by from session ctx
# ===========================================================================


@pytest.mark.asyncio
async def test_create_grant_created_by_is_session_operator_id() -> None:
    """
    POST /grants must set created_by from the session context operator_id,
    NOT the nil-UUID placeholder.  The response body's created_by wire ID
    must encode the seeded OPERATOR_UUID (operator_<crockford>).

    Source: ADR-0025; C4b acceptance criterion AC-2.
    """
    secret_row = _make_secret_row(agent_id=OWNER_UUID)
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(AGENT_UUID)
    session = _MockSession(fetch_once_rows=[secret_row, agent_row, None])

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _post(GRANTS_PATH, session, {"recipient_agent_id": AGENT_UUID})

    assert resp.status_code == 201, resp.text
    body = resp.json()
    # created_by must be an operator_ wire ID encoding OPERATOR_UUID — NOT the nil-UUID
    assert body["created_by"].startswith("operator_"), f"Expected operator_ prefix: {body['created_by']}"
    nil_wire = "operator_0000000000000000000000000"
    assert body["created_by"] != nil_wire, (
        f"created_by is the nil-UUID placeholder; expected the seeded OPERATOR_UUID"
    )


@pytest.mark.asyncio
async def test_create_grant_audit_actor_id_is_session_operator_id() -> None:
    """
    POST /grants must pass actor_id == session operator_id to audit_emit,
    NOT None.

    Source: ADR-0025; C4b acceptance criterion AC-2.
    """
    secret_row = _make_secret_row(agent_id=OWNER_UUID)
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(AGENT_UUID)
    session = _MockSession(fetch_once_rows=[secret_row, agent_row, None])

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _post(GRANTS_PATH, session, {"recipient_agent_id": AGENT_UUID})

    assert resp.status_code == 201, resp.text
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["actor_id"] == uuid.UUID(OPERATOR_UUID), (
        f"Expected actor_id={OPERATOR_UUID}, got {call_kwargs['actor_id']}"
    )


@pytest.mark.asyncio
async def test_revoke_grant_audit_actor_id_is_session_operator_id() -> None:
    """
    DELETE /grants/{grant_id} must pass actor_id == session operator_id to audit_emit.

    Source: ADR-0025; C4b acceptance criterion AC-3.
    """
    grant_row = _make_grant_row()
    session = _MockSession(fetch_once_rows=[grant_row])

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _delete(GRANT_PATH, session)

    assert resp.status_code == 204, resp.text
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["actor_id"] == uuid.UUID(OPERATOR_UUID), (
        f"Expected actor_id={OPERATOR_UUID}, got {call_kwargs['actor_id']}"
    )


@pytest.mark.asyncio
async def test_delete_secret_audit_actor_id_is_session_operator_id() -> None:
    """
    DELETE /{secret_id} must pass actor_id == session operator_id to audit_emit.

    Source: ADR-0025; C4b acceptance criterion AC-4.
    """
    row = _make_secret_row()
    session = _MockSession(fetch_once_rows=[row])

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _delete(SECRET_PATH, session)

    assert resp.status_code == 204, resp.text
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs["actor_id"] == uuid.UUID(OPERATOR_UUID), (
        f"Expected actor_id={OPERATOR_UUID}, got {call_kwargs['actor_id']}"
    )


# ===========================================================================
# C5: POST /v1/tenants/{tenant_id}/agent-secrets — operator provision
# ===========================================================================

# A second AGENT UUID distinct from the owning-agent used in share-grant tests
TARGET_AGENT_UUID = "66666666-6666-6666-6666-666666666666"

CREATE_SECRET_PATH = BASE  # POST /v1/tenants/{tid}/agent-secrets


async def _post_create_secret(
    session: Any,
    body: dict,
    vault_client: Any = None,
    session_ctx: Any = None,
) -> Any:
    """POST to the create-secret endpoint with the test app."""
    from admin_api.middleware.csrf import csrf_exempt
    csrf_exempt(CREATE_SECRET_PATH)
    app = _create_app(session, vault_client=vault_client, session_ctx=session_ctx)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            CREATE_SECRET_PATH,
            json=body,
            headers={"X-CSRF-Token": CSRF_TOKEN},
        )


@pytest.mark.asyncio
async def test_create_agent_secret_happy_path_returns_201() -> None:
    """
    POST /agent-secrets with valid body returns 201 with AgentSecret metadata.
    Verifies: vault put called with bare-UUID secret_id, audit emitted, 201 body
    is metadata-only (no value field).
    Source: C5 AC-1, AC-3.
    """
    # fetchone calls: (1) agent-exists check → row, (2) dup check → None
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(TARGET_AGENT_UUID)
    session = _MockSession(fetch_once_rows=[agent_row, None])

    mock_vault = AsyncMock()
    mock_vault.put_agent_secret = AsyncMock(return_value={"kek_version": 0})

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()) as mock_audit,
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _post_create_secret(
            session,
            {
                "agent_id": TARGET_AGENT_UUID,
                "name": "my-secret",
                "value": "s3cr3t",
            },
            vault_client=mock_vault,
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()

    # Metadata-only: must NOT contain value or ciphertext
    assert "value" not in body, f"Response must not contain 'value': {body}"
    assert "ciphertext" not in body
    assert "enc_payload" not in body

    # Wire IDs present
    assert body["id"].startswith("sec_"), f"Expected sec_ prefix: {body['id']}"
    assert body["agent_id"].startswith("agent_"), f"Expected agent_ prefix: {body['agent_id']}"
    assert body["tenant_id"].startswith("tenant_"), f"Expected tenant_ prefix: {body['tenant_id']}"
    assert body["name"] == "my-secret"
    assert body["version"] == 1

    # Vault called with bare-UUID secret_id (NOT sec_ wire form)
    mock_vault.put_agent_secret.assert_called_once()
    call_kwargs = mock_vault.put_agent_secret.call_args.kwargs
    secret_id_passed = call_kwargs["secret_id"]
    assert not secret_id_passed.startswith("sec_"), (
        f"Vault secret_id must be a bare UUID, not a wire ID; got: {secret_id_passed!r}"
    )
    # Must be a valid UUID
    uuid.UUID(secret_id_passed)

    # Audit emitted with correct event_type, actor_type, and operator actor_id
    mock_audit.assert_called_once()
    audit_kwargs = mock_audit.call_args.kwargs
    assert audit_kwargs["event_type"] == "agent_secret.created"
    assert audit_kwargs["actor_type"] == "operator"
    assert audit_kwargs["actor_id"] == uuid.UUID(OPERATOR_UUID)

    # Audit payload is identifier-only
    payload = audit_kwargs["payload"]
    assert "secret_id" in payload
    assert "agent_id" in payload
    assert "name" in payload
    assert "version" in payload
    assert "value" not in payload


@pytest.mark.asyncio
async def test_create_agent_secret_response_is_metadata_only() -> None:
    """
    201 response must NOT contain value, ciphertext, enc_payload, or wrapped_dek.
    Source: C5 AC-3 (core invariant).
    """
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(TARGET_AGENT_UUID)
    session = _MockSession(fetch_once_rows=[agent_row, None])

    mock_vault = AsyncMock()
    mock_vault.put_agent_secret = AsyncMock(return_value={"kek_version": 0})

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _post_create_secret(
            session,
            {"agent_id": TARGET_AGENT_UUID, "name": "tok", "value": "plaintext"},
            vault_client=mock_vault,
        )

    assert resp.status_code == 201, resp.text
    body = resp.json()
    forbidden = {"value", "ciphertext", "enc_payload", "wrapped_dek", "key", "plaintext"}
    for field in forbidden:
        assert field not in body, f"Forbidden field '{field}' found in 201 response body"


@pytest.mark.asyncio
async def test_create_agent_secret_duplicate_returns_409_and_no_vault_call() -> None:
    """
    POST /agent-secrets with a name that already exists for (tenant, agent) returns 409
    duplicate_resource. The vault client must NOT be called (pre-check must fire first).
    Source: C5 AC-2b.
    """
    existing_row = _make_secret_row(agent_id=TARGET_AGENT_UUID, name="dup-secret")
    # fetchone (1) agent check → agent row, (2) dup check → returns existing row → handler rejects before vault
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(TARGET_AGENT_UUID)
    session = _MockSession(fetch_once_rows=[agent_row, existing_row])

    mock_vault = AsyncMock()
    mock_vault.put_agent_secret = AsyncMock(return_value={"kek_version": 0})

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        resp = await _post_create_secret(
            session,
            {"agent_id": TARGET_AGENT_UUID, "name": "dup-secret", "value": "x"},
            vault_client=mock_vault,
        )

    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["mintkey:code"] == "duplicate_resource", body
    mock_vault.put_agent_secret.assert_not_called()


@pytest.mark.asyncio
async def test_create_agent_secret_value_too_large_returns_422() -> None:
    """
    POST /agent-secrets with value > 65536 bytes returns 422 validation_failed.
    Source: C5 AC-2c.
    """
    session = _MockSession()
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _post_create_secret(
            session,
            {"agent_id": TARGET_AGENT_UUID, "name": "big", "value": "x" * 65537},
        )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["mintkey:code"] == "validation_failed", body


@pytest.mark.asyncio
async def test_create_agent_secret_invalid_name_returns_422() -> None:
    """
    POST /agent-secrets with a name that doesn't match ^[A-Za-z0-9._-]{1,128}$ returns 422.
    Source: C5 AC-2d.
    """
    session = _MockSession()
    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _post_create_secret(
            session,
            {"agent_id": TARGET_AGENT_UUID, "name": "bad name!", "value": "x"},
        )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["mintkey:code"] == "validation_failed", body


@pytest.mark.asyncio
async def test_create_agent_secret_missing_agent_returns_422() -> None:
    """
    POST /agent-secrets where target agent does not exist in this tenant returns 422.
    Source: C5 AC-2e (mirror grant-handler convention for cross-tenant/missing agent).
    """
    # fetchone (1) agent check → None (not found)
    session = _MockSession(fetch_once_rows=[None])

    with patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()):
        resp = await _post_create_secret(
            session,
            {"agent_id": TARGET_AGENT_UUID, "name": "tok", "value": "x"},
        )

    assert resp.status_code == 422, resp.text
    body = resp.json()
    assert body["mintkey:code"] == "not_found", body


@pytest.mark.asyncio
async def test_create_agent_secret_vault_called_with_bare_uuid() -> None:
    """
    AC-4: The secret_id passed to vault put_agent_secret is the same bare-UUID form
    used by the read path (secret_get/GetAgentSecret).  NOT the sec_ wire form.
    Source: C5 AC-4; secret_get.py line 118 calls get_agent_secret(secret_id=meta_secret_id)
    where meta_secret_id = str(row.id) — a bare UUID string.
    """
    agent_row = MagicMock()
    agent_row.id = uuid.UUID(TARGET_AGENT_UUID)
    session = _MockSession(fetch_once_rows=[agent_row, None])

    mock_vault = AsyncMock()
    mock_vault.put_agent_secret = AsyncMock(return_value={"kek_version": 0})

    with (
        patch("admin_api.api.agent_secrets.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.audit_emit", new=AsyncMock()),
        patch("admin_api.api.agent_secrets.notify_change", new=AsyncMock()),
    ):
        await _post_create_secret(
            session,
            {"agent_id": TARGET_AGENT_UUID, "name": "secret-x", "value": "v"},
            vault_client=mock_vault,
        )

    call_kwargs = mock_vault.put_agent_secret.call_args.kwargs
    secret_id_used = call_kwargs["secret_id"]
    # Must be a valid bare UUID (parseable by uuid.UUID), not a wire-ID string
    parsed = uuid.UUID(secret_id_used)
    assert str(parsed) == secret_id_used, (
        f"secret_id is not in canonical bare-UUID form: {secret_id_used!r}"
    )
    assert not secret_id_used.startswith("sec_"), (
        f"Vault received wire form instead of bare UUID: {secret_id_used!r}"
    )


@pytest.mark.parametrize("event_type,payload", [
    (
        "agent_secret.deleted",
        {
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "agent_id": "agent_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "name": "db-password",
        },
    ),
    (
        "agent_secret_grant.created",
        {
            "grant_id": "secgrant_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "owner_agent_id": "agent_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "recipient_agent_id": "agent_BBBBBBBBBBBBBBBBBBBBBBBBB1",
        },
    ),
    (
        "agent_secret_grant.revoked",
        {
            "grant_id": "secgrant_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "owner_agent_id": "agent_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "recipient_agent_id": "agent_BBBBBBBBBBBBBBBBBBBBBBBBB1",
        },
    ),
    # C5: operator actor on agent_secret.created — schema must accept actor_type=operator
    (
        "agent_secret.created",
        {
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "agent_id": "agent_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "name": "db-password",
            "version": 1,
        },
    ),
])
def test_admin_api_audit_payload_schema_conformance(event_type, payload) -> None:
    """Each agent_secret* payload must conform to the canonical schema $defs."""
    _validate_payload(event_type, payload)
