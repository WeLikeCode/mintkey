"""
Unit tests for C-4 + C-5 fixes in rotate_credential / create_credential.

C-4: Rotating without new plaintext must carry forward target_address, ssh_user,
     header_name, query_param from the prior is_current vault credential.
     Previously the new vault.credentials row was created with empty routing
     metadata, causing ssh-proxy to fail with "no target address specified".

C-5: services.current_key_version must be updated atomically alongside the
     credential write so the stored column stays in sync with the vault's
     is_current flag.  Previously the column was not updated on rotate or
     create, causing the UI Show page to display a stale version number.

Test cases:
  1. test_rotate_without_value_carries_forward_routing_metadata
       → new put_credential call receives prior target_address + ssh_user
  2. test_rotate_with_explicit_value_overrides_carry_forward
       → explicit target_address/ssh_user in request override carry-forward
  3. test_rotate_syncs_services_current_key_version
       → services UPDATE executed with new_key_version after rotate
  4. test_create_credential_syncs_services_current_key_version
       → services UPDATE executed after credential INSERT
  5. test_rotate_carry_forward_bearer_token_scheme
       → non-SSH scheme: put_credential called without target_address/ssh_user
         but get_credential is still called for header_name/query_param carry-forward

Source: C-4 + C-5 chunk goal; ADR-0013 §3.1; ADR-0021.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from admin_api.api.credentials import (
    CredentialCreate,
    CredentialRotateRequest,
    create_credential,
    rotate_credential,
)

# ---------------------------------------------------------------------------
# Shared test constants
# ---------------------------------------------------------------------------

_TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_SERVICE_UUID = "11111111-2222-3333-4444-555555555555"  # DB UUID form
_TARGET_ADDRESS = "ssh-target:2222"
_SSH_USER = "testuser"
_HEADER_NAME = "X-API-Key"
_QUERY_PARAM = "api_key"
_BASE_URL = "https://api.example.com"

_FAKE_PEM = (
    "-----BEGIN OPENSSH PRIVATE KEY-----\n"
    "b3BlbnNzaC1rZXktdjEAAAAA fakekeyfortest\n"
    "-----END OPENSSH PRIVATE KEY-----\n"
)


# ---------------------------------------------------------------------------
# Helpers — mock DB session
# ---------------------------------------------------------------------------


def _make_session(
    *,
    svc_row_base_url: str = _BASE_URL,
    old_cred_key_version: int = 2,
    old_cred_id: str | None = None,
) -> MagicMock:
    """Return an async-compatible mock AsyncSession.

    Configures execute() to return appropriate rows for:
      - services SELECT (base_url lookup)
      - credentials SELECT (old active credential for rotate)
    """
    session = MagicMock()
    session.execute = AsyncMock()

    # Build mock rows
    svc_row = MagicMock()
    svc_row.id = _SERVICE_UUID
    svc_row.base_url = svc_row_base_url

    cred_row = MagicMock()
    cred_row.id = old_cred_id or str(uuid.uuid4())
    cred_row.key_version = old_cred_key_version
    cred_row.status = "active"

    svc_result = MagicMock()
    svc_result.fetchone.return_value = svc_row

    cred_result = MagicMock()
    cred_result.fetchone.return_value = cred_row

    # The session returns different results based on call order:
    # 1st execute → services SELECT
    # 2nd execute → credentials SELECT
    # subsequent execute calls (INSERT/UPDATE) → empty result
    empty_result = MagicMock()
    empty_result.fetchone.return_value = None
    empty_result.fetchall.return_value = []

    session.execute.side_effect = [
        svc_result,   # SELECT FROM services
        cred_result,  # SELECT FROM credentials (old active row)
        empty_result, # UPDATE credentials (supersede old)
        empty_result, # INSERT INTO credentials (new row)
        empty_result, # UPDATE services (current_key_version sync)
    ]

    return session


def _make_vault(
    *,
    prior_target_address: str = _TARGET_ADDRESS,
    prior_ssh_user: str = _SSH_USER,
    prior_header_name: str = "",
    prior_query_param: str = "",
    new_key_version: int = 3,
) -> MagicMock:
    """Return a mock VaultAdapterClient.

    get_credential returns the prior routing metadata.
    put_credential returns {key_version: new_key_version}.
    """
    vault = MagicMock()
    vault.get_credential = AsyncMock(return_value={
        "plaintext": "old-secret-value",
        "auth_scheme": "ssh_password",
        "key_version": 2,
        "header_name": prior_header_name,
        "query_param": prior_query_param,
        "target_address": prior_target_address,
        "ssh_user": prior_ssh_user,
    })
    vault.put_credential = AsyncMock(return_value={
        "credential_id": f"cred_test_{uuid.uuid4().hex[:8]}",
        "key_version": new_key_version,
        "created_at": datetime.now(timezone.utc).timestamp(),
    })
    return vault


# ---------------------------------------------------------------------------
# Patches applied to all tests: audit_emit, notify_change, set_tenant_context,
# wire_to_db_uuid (so wire-ID decoding doesn't fail on fake service IDs).
# ---------------------------------------------------------------------------

def _wire_to_db_side_effect(wire_id: str, prefix: str) -> str:
    """
    Mock for _wire_to_db in credentials.py.

    For service_id / plain UUIDs: return as-is.
    For cred_ wire IDs generated by _new_cred_id(): return a valid UUID hex
    so that uuid.UUID(result) succeeds in rotate_credential/create_credential.
    """
    if wire_id.startswith("cred_"):
        # Generate a deterministic fake UUID from the wire ID so the call is repeatable.
        return str(uuid.uuid5(uuid.NAMESPACE_OID, wire_id)).replace("-", "")
    return wire_id


_COMMON_PATCHES = [
    patch("admin_api.api.credentials.audit_emit", new_callable=AsyncMock),
    patch("admin_api.api.credentials.notify_change", new_callable=AsyncMock),
    patch("admin_api.api.credentials.set_tenant_context", new_callable=AsyncMock),
    # _wire_to_db: handle svc_/plain UUIDs pass-through + cred_ → valid UUID hex.
    patch(
        "admin_api.api.credentials._wire_to_db",
        side_effect=_wire_to_db_side_effect,
    ),
]


def _apply_patches(fn):
    """Decorator that applies all common patches."""
    for p in reversed(_COMMON_PATCHES):
        fn = p(fn)
    return fn


# ---------------------------------------------------------------------------
# Test 1: rotate without new value → carry-forward routing metadata
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_rotate_without_value_carries_forward_routing_metadata(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """Rotating with body.value=None must pass prior target_address+ssh_user to vault."""
    session = _make_session(old_cred_key_version=2)
    vault = _make_vault(
        prior_target_address=_TARGET_ADDRESS,
        prior_ssh_user=_SSH_USER,
        new_key_version=3,
    )

    body = CredentialRotateRequest(
        auth_scheme="ssh_password",
        value=None,   # ← UI "Rotate Credential" button — no new plaintext
    )

    response = await rotate_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # vault.get_credential must have been called to fetch prior metadata
    vault.get_credential.assert_awaited_once()

    # vault.put_credential must have been called with the carried-forward values
    vault.put_credential.assert_awaited_once()
    put_kwargs = vault.put_credential.call_args.kwargs
    assert put_kwargs["target_address"] == _TARGET_ADDRESS, (
        f"C-4: target_address not carried forward; got '{put_kwargs['target_address']}'"
    )
    assert put_kwargs["ssh_user"] == _SSH_USER, (
        f"C-4: ssh_user not carried forward; got '{put_kwargs['ssh_user']}'"
    )


# ---------------------------------------------------------------------------
# Test 2: rotate WITH explicit value + overrides → overrides win
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_rotate_with_explicit_value_overrides_carry_forward(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """Explicit target_address/ssh_user in the SSH payload override carry-forward."""
    new_target = "new-host:2222"
    new_user = "newuser"
    new_password_payload = json.dumps({
        "username": new_user,
        "password": "brand-new-secret-password",
        "target_address": new_target,
    })

    session = _make_session(old_cred_key_version=2)
    vault = _make_vault(
        prior_target_address=_TARGET_ADDRESS,  # old values
        prior_ssh_user=_SSH_USER,
        new_key_version=3,
    )

    body = CredentialRotateRequest(
        auth_scheme="ssh_password",
        value=new_password_payload,
    )

    response = await rotate_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code == 200

    put_kwargs = vault.put_credential.call_args.kwargs
    assert put_kwargs["target_address"] == new_target, (
        f"C-4: expected override target '{new_target}', got '{put_kwargs['target_address']}'"
    )
    assert put_kwargs["ssh_user"] == new_user, (
        f"C-4: expected override ssh_user '{new_user}', got '{put_kwargs['ssh_user']}'"
    )


# ---------------------------------------------------------------------------
# Test 3: rotate → services.current_key_version synced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_rotate_syncs_services_current_key_version(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """rotate_credential must UPDATE services.current_key_version to new_key_version."""
    new_kv = 5
    session = _make_session(old_cred_key_version=4)
    vault = _make_vault(new_key_version=new_kv)

    body = CredentialRotateRequest(
        auth_scheme="ssh_password",
        value=None,
    )

    response = await rotate_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code == 200

    # Find the UPDATE services call among all execute() calls.
    services_update_found = False
    for c in session.execute.call_args_list:
        args = c.args
        if args and hasattr(args[0], "text"):
            sql = str(args[0])
            if "UPDATE services" in sql and "current_key_version" in sql:
                params = c.args[1] if len(c.args) > 1 else {}
                assert params.get("kv") == new_kv, (
                    f"C-5: services.current_key_version should be {new_kv}, "
                    f"got {params.get('kv')}"
                )
                services_update_found = True
                break

    assert services_update_found, (
        "C-5: No 'UPDATE services SET current_key_version' found in execute() calls"
    )


# ---------------------------------------------------------------------------
# Test 4: create_credential → services.current_key_version synced
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_create_credential_syncs_services_current_key_version(
    mock_wire_to_db: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """create_credential must UPDATE services.current_key_version after INSERT."""
    new_kv = 1
    session = MagicMock()
    session.execute = AsyncMock()

    svc_row = MagicMock()
    svc_row.base_url = _BASE_URL
    svc_result = MagicMock()
    svc_result.fetchone.return_value = svc_row

    empty_result = MagicMock()
    empty_result.fetchone.return_value = None
    empty_result.fetchall.return_value = []

    # create_credential does:
    #   1. SELECT FROM services  → svc_result
    #   2. PUT credential (vault, not DB)
    #   3. INSERT INTO credentials  → empty_result
    #   4. UPDATE services  → empty_result
    #   5. audit_emit (mocked)
    #   6. notify_change (mocked)
    session.execute.side_effect = [
        svc_result,   # SELECT FROM services
        empty_result, # INSERT INTO credentials
        empty_result, # UPDATE services (current_key_version)
    ]

    vault = MagicMock()
    vault.put_credential = AsyncMock(return_value={
        "credential_id": "cred_test_xxx",
        "key_version": new_kv,
        "created_at": datetime.now(timezone.utc).timestamp(),
    })

    body = CredentialCreate(
        auth_scheme="bearer_token",
        value="super-secret-bearer-token-value",
    )

    response = await create_credential(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_UUID,
        body=body,
        session=session,
        vault=vault,
    )

    assert response.status_code == 201

    services_update_found = False
    for c in session.execute.call_args_list:
        args = c.args
        if args and hasattr(args[0], "text"):
            sql = str(args[0])
            if "UPDATE services" in sql and "current_key_version" in sql:
                params = c.args[1] if len(c.args) > 1 else {}
                assert params.get("kv") == new_kv, (
                    f"C-5: services.current_key_version should be {new_kv}, "
                    f"got {params.get('kv')}"
                )
                services_update_found = True
                break

    assert services_update_found, (
        "C-5: No 'UPDATE services SET current_key_version' found in create_credential execute() calls"
    )
