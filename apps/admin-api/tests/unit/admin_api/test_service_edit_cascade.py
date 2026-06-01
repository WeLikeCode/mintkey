"""
Unit tests for C-6a: base_url cascade to vault.credentials.target_address.

When update_service is called with a new base_url for an SSH service:
  - vault.credentials.target_address is updated in the same transaction.
  - Non-SSH services are not cascaded.
  - Malformed ssh:// URLs are rejected with HTTP 400 before any DB write.
  - SSH services with no credential yet are handled gracefully (no-op cascade).

Test cases:
  1. test_update_ssh_service_base_url_cascades_to_target_address
       → PATCH base_url on ssh_password service triggers UPDATE vault.credentials
         with new target_address='172.24.1.234:22'
  2. test_update_non_ssh_service_base_url_does_not_cascade
       → PATCH base_url on bearer_token service: no vault.credentials UPDATE
  3. test_malformed_ssh_base_url_rejected_400
       → PATCH base_url=ssh://no-port returns 400 with structured detail;
         service NOT updated
  4. test_update_ssh_base_url_no_credential_yet
       → PATCH succeeds; cascade UPDATE is a no-op (no credential exists yet)
  5. test_parse_ssh_host_port_ipv6_loopback
       → _parse_ssh_host_port("ssh://[::1]:22") → "[::1]:22"
  6. test_parse_ssh_host_port_ipv6_link_local
       → _parse_ssh_host_port("ssh://[fe80::1]:2222") → "[fe80::1]:2222"
  7. test_parse_ssh_host_port_ipv4_unchanged
       → _parse_ssh_host_port("ssh://172.24.1.234:22") → "172.24.1.234:22"
  8. test_parse_ssh_host_port_hostname_unchanged
       → _parse_ssh_host_port("ssh://host.example:22") → "host.example:22"
  9. test_parse_ssh_host_port_ipv6_no_port_raises
       → _parse_ssh_host_port("ssh://[::1]") → ValueError
  10. test_update_ssh_service_ipv6_base_url_cascades
       → PATCH base_url=ssh://[::1]:22, cascade writes target_address='[::1]:22'
  11. test_update_ssh_service_ipv6_link_local_cascades
       → PATCH base_url=ssh://[fe80::1]:2222, cascade writes '[fe80::1]:2222'

Source: C-6a chunk goal; C-6 round-2 IPv6 fix; ADR-0021; ADR-0008.
"""
from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from admin_api.api.services import ServiceUpdate, _parse_ssh_host_port, update_service

# ---------------------------------------------------------------------------
# Shared constants
# ---------------------------------------------------------------------------

_TENANT_ID = uuid.UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
_SERVICE_ID = "11111111-2222-3333-4444-555555555555"  # plain UUID (no svc_ prefix)
_OLD_BASE_URL = "ssh://ssh-target:2222"
_NEW_BASE_URL = "ssh://172.24.1.234:22"
_NEW_TARGET_ADDRESS = "172.24.1.234:22"

# ---------------------------------------------------------------------------
# Common patches applied to all tests
# ---------------------------------------------------------------------------

_COMMON_PATCHES = [
    patch("admin_api.api.services.audit_emit", new_callable=AsyncMock),
    patch("admin_api.api.services.notify_change", new_callable=AsyncMock),
    patch("admin_api.api.services.set_tenant_context", new_callable=AsyncMock),
    patch("admin_api.api.services.require_tenant_session"),
    # Bypass SSRF check for private IPs so we can use 172.x addresses in tests.
    patch("admin_api.api.services._is_forbidden_destination", return_value=False),
    # Wire-ID decoder: return input unchanged (test uses plain UUID form).
    patch(
        "admin_api.api.services._wire_id_to_db_uuid",
        side_effect=lambda x: x,
    ),
]


def _apply_patches(fn):
    """Decorator that applies all common patches."""
    for p in reversed(_COMMON_PATCHES):
        fn = p(fn)
    return fn


# ---------------------------------------------------------------------------
# Helper — build a mock AsyncSession
# ---------------------------------------------------------------------------


def _make_service_session(
    *,
    stored_auth_scheme: str = "ssh_password",
    service_found: bool = True,
) -> MagicMock:
    """Return a mock AsyncSession for update_service.

    Execute call order (when body.auth_scheme is None and base_url changes):
      1. SELECT services WHERE id=:sid AND tenant_id=:tid  → stored auth_scheme lookup
      2. UPDATE services  → the actual service update
      3. UPDATE vault.credentials  → cascade (SSH only)
      4. SELECT services JOIN ...  → re-fetch for response

    When body.auth_scheme is explicitly set, step 1 is skipped.
    """
    session = MagicMock()
    session.execute = AsyncMock()

    svc_lookup_row = MagicMock()
    svc_lookup_row.auth_scheme = stored_auth_scheme

    svc_lookup_result = MagicMock()
    svc_lookup_result.fetchone.return_value = svc_lookup_row if service_found else None

    # Re-fetch response row after UPDATE
    response_row = MagicMock()
    response_row.id = _SERVICE_ID
    response_row.tenant_id = str(_TENANT_ID)
    response_row.name = "test-service"
    response_row.slug = "test-service"
    response_row.display_name = None
    response_row.description = None
    response_row.base_url = _NEW_BASE_URL
    response_row.auth_scheme = stored_auth_scheme
    response_row.openapi_url = None
    response_row.status = "active"
    response_row.current_key_version = 1
    response_row.created_at = None
    response_row.updated_at = None
    response_row.template_id = None

    response_result = MagicMock()
    response_result.fetchone.return_value = response_row

    empty_result = MagicMock()
    empty_result.fetchone.return_value = None

    # Side effects: lookup → update → cascade → re-fetch
    session.execute.side_effect = [
        svc_lookup_result,  # SELECT auth_scheme (C-6a lookup when body.auth_scheme=None)
        empty_result,       # UPDATE services
        empty_result,       # UPDATE vault.credentials (cascade)
        response_result,    # SELECT for response
    ]

    return session


def _make_service_session_explicit_scheme(
    *,
    stored_auth_scheme: str = "ssh_password",
) -> MagicMock:
    """Session for tests where body.auth_scheme is explicitly provided.

    No auth_scheme lookup SELECT is needed because the scheme is in the request.
    Call order:
      1. UPDATE services
      2. UPDATE vault.credentials (cascade for SSH)
      3. SELECT for response
    """
    session = MagicMock()
    session.execute = AsyncMock()

    response_row = MagicMock()
    response_row.id = _SERVICE_ID
    response_row.tenant_id = str(_TENANT_ID)
    response_row.name = "test-service"
    response_row.slug = "test-service"
    response_row.display_name = None
    response_row.description = None
    response_row.base_url = _NEW_BASE_URL
    response_row.auth_scheme = stored_auth_scheme
    response_row.openapi_url = None
    response_row.status = "active"
    response_row.current_key_version = 1
    response_row.created_at = None
    response_row.updated_at = None
    response_row.template_id = None

    response_result = MagicMock()
    response_result.fetchone.return_value = response_row

    empty_result = MagicMock()
    empty_result.fetchone.return_value = None

    session.execute.side_effect = [
        empty_result,   # UPDATE services
        empty_result,   # UPDATE vault.credentials (cascade for SSH)
        response_result,  # SELECT for response
    ]

    return session


def _make_non_ssh_session() -> MagicMock:
    """Session for non-SSH services where body.auth_scheme is None.

    Call order (non-SSH, no cascade):
      1. SELECT auth_scheme lookup
      2. UPDATE services
      3. SELECT for response
    """
    session = MagicMock()
    session.execute = AsyncMock()

    svc_lookup_row = MagicMock()
    svc_lookup_row.auth_scheme = "bearer_token"

    svc_lookup_result = MagicMock()
    svc_lookup_result.fetchone.return_value = svc_lookup_row

    response_row = MagicMock()
    response_row.id = _SERVICE_ID
    response_row.tenant_id = str(_TENANT_ID)
    response_row.name = "test-service"
    response_row.slug = "test-service"
    response_row.display_name = None
    response_row.description = None
    response_row.base_url = "https://api.example.com/v2"
    response_row.auth_scheme = "bearer_token"
    response_row.openapi_url = None
    response_row.status = "active"
    response_row.current_key_version = 1
    response_row.created_at = None
    response_row.updated_at = None
    response_row.template_id = None

    response_result = MagicMock()
    response_result.fetchone.return_value = response_row

    empty_result = MagicMock()
    empty_result.fetchone.return_value = None

    # No cascade: lookup → UPDATE services → SELECT
    session.execute.side_effect = [
        svc_lookup_result,  # SELECT auth_scheme
        empty_result,       # UPDATE services
        response_result,    # SELECT for response
    ]

    return session


# ---------------------------------------------------------------------------
# Test 1: SSH service base_url change cascades to vault.credentials
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_update_ssh_service_base_url_cascades_to_target_address(
    mock_wire_to_db: Any,
    mock_forbidden: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """PATCH base_url on an ssh_password service must UPDATE vault.credentials.target_address."""
    session = _make_service_session(stored_auth_scheme="ssh_password")

    body = ServiceUpdate(base_url=_NEW_BASE_URL)  # auth_scheme=None → lookup stored scheme

    response = await update_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID,
        body=body,
        session=session,
        _authz=None,
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Find the vault.credentials UPDATE call
    vault_update_found = False
    for c in session.execute.call_args_list:
        args = c.args
        if args and hasattr(args[0], "text"):
            sql = str(args[0])
            if "vault.credentials" in sql and "target_address" in sql:
                params = c.args[1] if len(c.args) > 1 else {}
                assert params.get("target_address") == _NEW_TARGET_ADDRESS, (
                    f"C-6a: expected target_address='{_NEW_TARGET_ADDRESS}', "
                    f"got '{params.get('target_address')}'"
                )
                vault_update_found = True
                break

    assert vault_update_found, (
        "C-6a: No 'UPDATE vault.credentials SET target_address' found in execute() calls. "
        f"Calls: {[str(c.args[0]) for c in session.execute.call_args_list if c.args]}"
    )


# ---------------------------------------------------------------------------
# Test 2: Non-SSH service base_url change does NOT cascade
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_update_non_ssh_service_base_url_does_not_cascade(
    mock_wire_to_db: Any,
    mock_forbidden: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """PATCH base_url on a bearer_token service must NOT UPDATE vault.credentials."""
    session = _make_non_ssh_session()

    body = ServiceUpdate(base_url="https://api.example.com/v2")

    response = await update_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID,
        body=body,
        session=session,
        _authz=None,
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # Ensure NO vault.credentials UPDATE was executed
    for c in session.execute.call_args_list:
        args = c.args
        if args and hasattr(args[0], "text"):
            sql = str(args[0])
            assert "vault.credentials" not in sql, (
                "C-6a: vault.credentials was updated for a non-SSH service — should not cascade. "
                f"SQL: {sql}"
            )


# ---------------------------------------------------------------------------
# Test 3: Malformed ssh:// base_url rejected with 400
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_malformed_ssh_base_url_rejected_400(
    mock_wire_to_db: Any,
    mock_forbidden: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """PATCH base_url=ssh://no-port-here must return 400; no service UPDATE executed."""
    session = MagicMock()
    session.execute = AsyncMock()

    # With explicit SSH scheme (body.auth_scheme='ssh_password'), no lookup needed.
    body = ServiceUpdate(
        auth_scheme="ssh_password",
        base_url="ssh://no-port-here",  # missing port
    )

    response = await update_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID,
        body=body,
        session=session,
        _authz=None,
    )

    assert response.status_code == 400, f"Expected 400, got {response.status_code}"
    import json as _json
    body_data = _json.loads(response.body)
    assert body_data.get("mintkey:code") == "invalid_ssh_base_url", (
        f"C-6a: expected mintkey:code='invalid_ssh_base_url', got {body_data}"
    )

    # No DB writes should have happened
    session.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Test 4: SSH service base_url change succeeds when no credential exists
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@_apply_patches
async def test_update_ssh_base_url_no_credential_yet(
    mock_wire_to_db: Any,
    mock_forbidden: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """PATCH base_url on SSH service with no credential yet: service UPDATE succeeds, cascade is no-op."""
    # The vault.credentials UPDATE will match 0 rows (no credential yet), which is fine.
    session = _make_service_session_explicit_scheme(stored_auth_scheme="ssh_password")

    body = ServiceUpdate(
        auth_scheme="ssh_password",
        base_url=_NEW_BASE_URL,
    )

    response = await update_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID,
        body=body,
        session=session,
        _authz=None,
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    # The vault.credentials UPDATE call must still have been attempted (no-op is fine).
    vault_update_attempted = any(
        hasattr(c.args[0], "text") and "vault.credentials" in str(c.args[0])
        for c in session.execute.call_args_list
        if c.args
    )
    assert vault_update_attempted, (
        "C-6a: vault.credentials UPDATE was not attempted even with explicit ssh_password scheme. "
        f"Calls: {[str(c.args[0]) for c in session.execute.call_args_list if c.args]}"
    )


# ---------------------------------------------------------------------------
# Tests 5-9: _parse_ssh_host_port unit tests (IPv6 + regression)
# ---------------------------------------------------------------------------


def test_parse_ssh_host_port_ipv6_loopback() -> None:
    """ssh://[::1]:22 must produce '[::1]:22' so Go net.SplitHostPort can parse it."""
    assert _parse_ssh_host_port("ssh://[::1]:22") == "[::1]:22"


def test_parse_ssh_host_port_ipv6_link_local() -> None:
    """ssh://[fe80::1]:2222 must produce '[fe80::1]:2222'."""
    assert _parse_ssh_host_port("ssh://[fe80::1]:2222") == "[fe80::1]:2222"


def test_parse_ssh_host_port_ipv4_unchanged() -> None:
    """IPv4 addresses must not be double-bracketed."""
    assert _parse_ssh_host_port("ssh://172.24.1.234:22") == "172.24.1.234:22"


def test_parse_ssh_host_port_hostname_unchanged() -> None:
    """Plain hostnames must not be bracketed."""
    assert _parse_ssh_host_port("ssh://host.example:22") == "host.example:22"


def test_parse_ssh_host_port_ipv6_no_port_raises() -> None:
    """ssh://[::1] (no port) must raise ValueError."""
    with pytest.raises(ValueError, match="missing port"):
        _parse_ssh_host_port("ssh://[::1]")


# ---------------------------------------------------------------------------
# Tests 10-11: IPv6 cascade end-to-end via update_service
# ---------------------------------------------------------------------------


def _make_service_session_ipv6(base_url: str, target_address: str) -> MagicMock:
    """Session for IPv6 cascade tests (explicit auth_scheme, no lookup SELECT)."""
    session = MagicMock()
    session.execute = AsyncMock()

    response_row = MagicMock()
    response_row.id = _SERVICE_ID
    response_row.tenant_id = str(_TENANT_ID)
    response_row.name = "test-service"
    response_row.slug = "test-service"
    response_row.display_name = None
    response_row.description = None
    response_row.base_url = base_url
    response_row.auth_scheme = "ssh_password"
    response_row.openapi_url = None
    response_row.status = "active"
    response_row.current_key_version = 1
    response_row.created_at = None
    response_row.updated_at = None
    response_row.template_id = None

    response_result = MagicMock()
    response_result.fetchone.return_value = response_row

    empty_result = MagicMock()
    empty_result.fetchone.return_value = None

    session.execute.side_effect = [
        empty_result,     # UPDATE services
        empty_result,     # UPDATE vault.credentials (cascade)
        response_result,  # SELECT for response
    ]
    return session


@pytest.mark.asyncio
@_apply_patches
async def test_update_ssh_service_ipv6_base_url_cascades(
    mock_wire_to_db: Any,
    mock_forbidden: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """PATCH base_url=ssh://[::1]:22 must cascade target_address='[::1]:22'."""
    ipv6_url = "ssh://[::1]:22"
    expected_addr = "[::1]:22"
    session = _make_service_session_ipv6(ipv6_url, expected_addr)

    body = ServiceUpdate(auth_scheme="ssh_password", base_url=ipv6_url)

    response = await update_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID,
        body=body,
        session=session,
        _authz=None,
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    vault_update_found = False
    for c in session.execute.call_args_list:
        args = c.args
        if args and hasattr(args[0], "text"):
            sql = str(args[0])
            if "vault.credentials" in sql and "target_address" in sql:
                params = c.args[1] if len(c.args) > 1 else {}
                assert params.get("target_address") == expected_addr, (
                    f"IPv6 cascade: expected target_address='{expected_addr}', "
                    f"got '{params.get('target_address')}'"
                )
                vault_update_found = True
                break

    assert vault_update_found, (
        "IPv6 cascade: No vault.credentials UPDATE with target_address found. "
        f"Calls: {[str(c.args[0]) for c in session.execute.call_args_list if c.args]}"
    )


@pytest.mark.asyncio
@_apply_patches
async def test_update_ssh_service_ipv6_link_local_cascades(
    mock_wire_to_db: Any,
    mock_forbidden: Any,
    mock_require_tenant: Any,
    mock_set_tenant: Any,
    mock_notify: Any,
    mock_audit: Any,
) -> None:
    """PATCH base_url=ssh://[fe80::1]:2222 must cascade target_address='[fe80::1]:2222'."""
    ipv6_url = "ssh://[fe80::1]:2222"
    expected_addr = "[fe80::1]:2222"
    session = _make_service_session_ipv6(ipv6_url, expected_addr)

    body = ServiceUpdate(auth_scheme="ssh_password", base_url=ipv6_url)

    response = await update_service(
        tenant_id=_TENANT_ID,
        service_id=_SERVICE_ID,
        body=body,
        session=session,
        _authz=None,
    )

    assert response.status_code == 200, f"Expected 200, got {response.status_code}"

    vault_update_found = False
    for c in session.execute.call_args_list:
        args = c.args
        if args and hasattr(args[0], "text"):
            sql = str(args[0])
            if "vault.credentials" in sql and "target_address" in sql:
                params = c.args[1] if len(c.args) > 1 else {}
                assert params.get("target_address") == expected_addr, (
                    f"IPv6 link-local cascade: expected target_address='{expected_addr}', "
                    f"got '{params.get('target_address')}'"
                )
                vault_update_found = True
                break

    assert vault_update_found, (
        "IPv6 link-local cascade: No vault.credentials UPDATE with target_address found. "
        f"Calls: {[str(c.args[0]) for c in session.execute.call_args_list if c.args]}"
    )
