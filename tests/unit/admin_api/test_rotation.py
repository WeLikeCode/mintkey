"""
Unit tests: Credential rotation (T-1.8.2).

Tests that a second POST to the same service is detected as a rotation:
  - key_version increments (comes from vault)
  - audit event type becomes "credential.rotated" when key_version > 1
  - audit payload includes "previous_key_version"
  - NOTIFY is called on "mintkey:credential"

Sources:
  - ADR-0014.1 (global channel "mintkey:credential")
  - ADR-0014.7 (audit emit on every state change)
  - T-1.8.2 (rotation detection)
"""
from __future__ import annotations

import sys
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

TENANT_ID = "00000000-0000-0000-0000-000000000001"
SERVICE_ID = "00000000-0000-0000-0000-000000000002"
BASE_URL_PATH = f"/v1/tenants/{TENANT_ID}/services/{SERVICE_ID}/credentials"

_PLAINTEXT_VALUE = "sk-secret-test-credential-value-xyz"


def _make_mock_session():
    """Return an async-capable mock DB session.

    Call sequence for create_credential (WS-9):
      0: set_tenant_context (SELECT set_config)
      1: SELECT base_url FROM services WHERE ... → fake service row for target_url
      2+: INSERT, notify, etc. → None
    """
    session = MagicMock()
    _call_count = {"n": 0}

    async def _execute(*args, **kwargs):
        result = MagicMock()
        _call_count["n"] += 1
        n = _call_count["n"]
        if n == 2:
            # create_credential: second execute is SELECT base_url FROM services
            svc_row = MagicMock()
            svc_row.id = SERVICE_ID
            svc_row.base_url = "http://mock-backend:8999"
            result.fetchone.return_value = svc_row
        else:
            result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result

    session.execute = _execute
    return session


def _make_app_with_vault(vault_client_instance):
    """Build a FastAPI test app with the given vault client instance."""
    from fastapi import FastAPI
    from admin_api.api.credentials import router as credentials_router
    from admin_api.db.deps import get_db_session
    from admin_api.services.vault_client import get_vault_client
    from admin_api.middleware.csrf import CsrfMiddleware, csrf_exempt

    app = FastAPI()
    app.include_router(credentials_router)

    async def mock_db_session():
        yield _make_mock_session()

    app.dependency_overrides[get_db_session] = mock_db_session

    async def mock_vault():
        return vault_client_instance

    app.dependency_overrides[get_vault_client] = mock_vault

    csrf_exempt(BASE_URL_PATH)
    app.add_middleware(CsrfMiddleware)

    return app


# ---------------------------------------------------------------------------
# Test 1: key_version increments across calls (vault controls versioning)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotation_increments_key_version() -> None:
    """
    Second POST to the same service returns key_version=2 when the vault
    client returns key_version=2 on the second call.

    Source: T-1.8.2.
    """
    from admin_api.services.vault_client import VaultAdapterClient

    call_count = 0

    class _CyclingVaultClient(VaultAdapterClient):
        async def put_credential(
            self, tenant_id, service_id, auth_scheme, plaintext, target_url="",
            header_name="", query_param="", target_address="", ssh_user=""
        ):
            nonlocal call_count
            call_count += 1
            return {
                "credential_id": f"cred_abc123xyz0000000000000000{call_count}",
                "key_version": call_count,
                "created_at": 1_700_000_000.0,
            }

    app = _make_app_with_vault(_CyclingVaultClient())

    with patch("admin_api.api.credentials.audit_emit", new=AsyncMock()):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp1 = await client.post(
                BASE_URL_PATH,
                json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
            )
            resp2 = await client.post(
                BASE_URL_PATH,
                json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
            )

    assert resp1.status_code == 201, resp1.text
    assert resp2.status_code == 201, resp2.text
    assert resp1.json()["key_version"] == 1, f"Expected 1, got: {resp1.json()}"
    assert resp2.json()["key_version"] == 2, f"Expected 2, got: {resp2.json()}"


# ---------------------------------------------------------------------------
# Test 2: rotation audit event type and previous_key_version payload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotation_audit_event_has_previous_version() -> None:
    """
    When vault returns key_version=2, audit_emit is called with:
      - event_type="credential.rotated"
      - payload["previous_key_version"] == 1

    Source: T-1.8.2; ADR-0014.7.
    """
    from admin_api.services.vault_client import VaultAdapterClient

    class _RotationVaultClient(VaultAdapterClient):
        async def put_credential(
            self, tenant_id, service_id, auth_scheme, plaintext, target_url="",
            header_name="", query_param="", target_address="", ssh_user=""
        ):
            return {
                "credential_id": "cred_abc123xyz00000000000000002",
                "key_version": 2,
                "created_at": 1_700_000_000.0,
            }

    app = _make_app_with_vault(_RotationVaultClient())

    mock_audit = AsyncMock()
    with patch("admin_api.api.credentials.audit_emit", new=mock_audit):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                BASE_URL_PATH,
                json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
            )

    assert resp.status_code == 201, resp.text
    mock_audit.assert_called_once()
    call_kwargs = mock_audit.call_args.kwargs
    assert call_kwargs.get("event_type") == "credential.rotated", (
        f"Expected event_type='credential.rotated', got: {call_kwargs.get('event_type')}"
    )
    payload = call_kwargs.get("payload", {})
    assert payload.get("previous_key_version") == 1, (
        f"Expected previous_key_version=1 in payload, got: {payload}"
    )
    assert payload.get("key_version") == 2, (
        f"Expected key_version=2 in payload, got: {payload}"
    )


# ---------------------------------------------------------------------------
# Test 3: NOTIFY is called on mintkey:credential for rotations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rotation_notifies_credential_channel() -> None:
    """
    NOTIFY is called on the "mintkey:credential" global channel for a rotation.

    Source: T-1.8.2; ADR-0014.1.
    """
    from admin_api.services.vault_client import VaultAdapterClient

    class _RotationVaultClient(VaultAdapterClient):
        async def put_credential(
            self, tenant_id, service_id, auth_scheme, plaintext, target_url="",
            header_name="", query_param="", target_address="", ssh_user=""
        ):
            return {
                "credential_id": "cred_abc123xyz00000000000000002",
                "key_version": 2,
                "created_at": 1_700_000_000.0,
            }

    app = _make_app_with_vault(_RotationVaultClient())

    notified_channels = []

    async def _mock_notify(session, channel, payload):
        notified_channels.append(channel)

    with patch("admin_api.api.credentials.audit_emit", new=AsyncMock()), \
         patch("admin_api.api.credentials.notify_change", new=_mock_notify):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            resp = await client.post(
                BASE_URL_PATH,
                json={"auth_scheme": "bearer_token", "value": _PLAINTEXT_VALUE},
            )

    assert resp.status_code == 201, resp.text
    assert "mintkey:credential" in notified_channels, (
        f"Expected NOTIFY on 'mintkey:credential', got: {notified_channels}"
    )
