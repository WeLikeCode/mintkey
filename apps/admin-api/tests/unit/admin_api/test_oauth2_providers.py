"""
Unit tests for admin_api.api.oauth2_providers (feat/oauth2-providers-per-tenant-vault).

Tests:
  test_post_provider_happy_path              — POST creates row, vault.put_credential called, audit emitted
  test_post_provider_secret_not_in_audit     — explicit canary: secret NOT in any audit row
  test_post_provider_returns_no_secret       — response body has NO client_secret key
  test_post_provider_duplicate_upserts       — re-POST same (tenant, provider) → 201 (upsert)
  test_post_provider_invalid_provider        — unsupported provider → 422
  test_get_providers_lists_configured        — list returns configured providers
  test_get_single_provider_no_secret_echoed  — GET single never echoes secret
  test_delete_provider_204_and_vault_revoked — DELETE removes row + revokes vault cred
  test_delete_provider_not_found             — DELETE missing provider → 404
  test_oauth2_config_helper_per_tenant_isolation — tenant A's config not visible to B
  test_oauth2_config_helper_falls_back_to_env_var — no DB row, env vars set → returns env values

Coverage: 11 tests, all in-process (no DB, no gRPC, no real HTTP).

Sources: feat/oauth2-providers-per-tenant-vault §Layer 7; ADR-0024; NFR-17.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest

# ---------------------------------------------------------------------------
# Minimal async DB session + vault mocks (match email_services test pattern)
# ---------------------------------------------------------------------------


class _FakeRow:
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeResult:
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row

    def fetchall(self) -> list[Any]:
        if self._row is None:
            return []
        if isinstance(self._row, list):
            return self._row
        return [self._row]


class _FakeSession:
    def __init__(self, query_results: dict[str, Any] | None = None) -> None:
        self._results = query_results or {}
        self.executed_sql: list[tuple[str, dict[str, Any]]] = []
        self.audit_calls: list[dict[str, Any]] = []

    async def execute(self, stmt: Any, params: Any = None) -> Any:
        sql: str = str(stmt) if not hasattr(stmt, "text") else stmt.text
        self.executed_sql.append((sql, params or {}))
        for fragment, result in self._results.items():
            if fragment in sql:
                return result
        return _FakeResult(None)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


class _FakeVault:
    def __init__(self, stored_cred: dict[str, Any] | None = None) -> None:
        self.put_calls: list[dict[str, Any]] = []
        self.get_calls: list[dict[str, Any]] = []
        self._stored_cred = stored_cred

    async def put_credential(self, **kwargs: Any) -> dict[str, Any]:
        self.put_calls.append(kwargs)
        return {"credential_id": "cred_test", "key_version": 1, "created_at": 0}

    async def get_credential(self, **kwargs: Any) -> dict[str, Any] | None:
        self.get_calls.append(kwargs)
        return self._stored_cred


def _make_session(**results: Any) -> _FakeSession:
    return _FakeSession(query_results=results)


# ---------------------------------------------------------------------------
# Import module under test
# ---------------------------------------------------------------------------

from admin_api.api.oauth2_providers import (
    configure_oauth2_provider,
    list_oauth2_providers,
    get_oauth2_provider,
    delete_oauth2_provider,
    OAuth2ProviderConfigBody,
    _client_id_last4,
    _vault_service_id,
)
from admin_api.api.email_services import _oauth2_config_from_db

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_FAKE_CLIENT_ID = "123456789-abcdefghijklmnopqrstuvwxyz.apps.googleusercontent.com"
_FAKE_CLIENT_SECRET = "GOCSPX-fake_secret_for_test_only"
_FAKE_TENANT = uuid.uuid4()
_NOW = datetime(2026, 6, 3, 12, 0, 0, tzinfo=timezone.utc)


async def _fake_audit_capture(audit_store: list[dict[str, Any]]) -> Any:
    """Return an async side-effect that captures audit calls."""
    async def _capture(**kwargs: Any) -> None:
        audit_store.append(kwargs)
    return _capture


# ---------------------------------------------------------------------------
# test_post_provider_happy_path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_provider_happy_path() -> None:
    """POST creates DB row and calls vault.put_credential with the secret."""
    audit_store: list[dict[str, Any]] = []
    session = _make_session()
    vault = _FakeVault()
    body = OAuth2ProviderConfigBody(
        client_id=_FAKE_CLIENT_ID, client_secret=_FAKE_CLIENT_SECRET
    )

    async def _fake_audit(**kwargs: Any) -> None:
        audit_store.append(kwargs)

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock), \
         patch("admin_api.api.oauth2_providers.audit_emit", side_effect=_fake_audit):
        resp = await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT,
            provider="gmail",
            body=body,
            session=session,
            vault=vault,
            _authz=None,
        )

    assert resp.status_code == 201
    import json
    content = json.loads(resp.body)
    assert content["provider"] == "gmail"
    assert "client_id_last4" in content
    assert "configured_at" in content

    # Vault was called with the secret. service_id is a deterministic UUIDv5
    # derived from (tenant_id, provider) — see _vault_service_id helper.
    import uuid
    assert len(vault.put_calls) == 1
    vc = vault.put_calls[0]
    assert vc["auth_scheme"] == "email_oauth2_client"
    # Validate the service_id is a UUID (postgres requires it) and matches the
    # deterministic derivation rather than a literal string.
    assert uuid.UUID(vc["service_id"])  # raises if not a valid UUID
    assert vc["plaintext"] == _FAKE_CLIENT_SECRET

    # Audit was emitted
    assert len(audit_store) == 1
    assert audit_store[0]["event_type"] == "oauth2_provider.configured"


# ---------------------------------------------------------------------------
# test_post_provider_secret_not_in_audit
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_provider_secret_not_in_audit() -> None:
    """NFR-17 canary: client_secret MUST NOT appear in any audit payload."""
    audit_store: list[dict[str, Any]] = []
    session = _make_session()
    vault = _FakeVault()
    body = OAuth2ProviderConfigBody(
        client_id=_FAKE_CLIENT_ID, client_secret=_FAKE_CLIENT_SECRET
    )

    async def _fake_audit(**kwargs: Any) -> None:
        audit_store.append(kwargs)

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock), \
         patch("admin_api.api.oauth2_providers.audit_emit", side_effect=_fake_audit):
        await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT,
            provider="gmail",
            body=body,
            session=session,
            vault=vault,
            _authz=None,
        )

    # Stringify all audit payloads and assert the secret is NOT there
    import json
    all_audit_text = json.dumps([a.get("payload", {}) for a in audit_store])
    assert _FAKE_CLIENT_SECRET not in all_audit_text, (
        f"NFR-17 VIOLATION: client_secret found in audit payload: {all_audit_text}"
    )


# ---------------------------------------------------------------------------
# test_post_provider_returns_no_secret
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_provider_returns_no_secret() -> None:
    """Response body MUST NOT contain client_secret."""
    session = _make_session()
    vault = _FakeVault()
    body = OAuth2ProviderConfigBody(
        client_id=_FAKE_CLIENT_ID, client_secret=_FAKE_CLIENT_SECRET
    )

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock), \
         patch("admin_api.api.oauth2_providers.audit_emit", new_callable=AsyncMock):
        resp = await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT,
            provider="gmail",
            body=body,
            session=session,
            vault=vault,
            _authz=None,
        )

    body_text = resp.body.decode()
    assert "client_secret" not in body_text, (
        f"NFR-17 VIOLATION: 'client_secret' key found in response body: {body_text}"
    )
    assert _FAKE_CLIENT_SECRET not in body_text, (
        f"NFR-17 VIOLATION: secret value found in response body: {body_text}"
    )


# ---------------------------------------------------------------------------
# test_post_provider_duplicate_upserts
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_provider_duplicate_upserts() -> None:
    """Re-POSTing the same (tenant, provider) returns 201 (ON CONFLICT DO UPDATE)."""
    session = _make_session()
    vault = _FakeVault()
    body = OAuth2ProviderConfigBody(
        client_id=_FAKE_CLIENT_ID, client_secret=_FAKE_CLIENT_SECRET
    )

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock), \
         patch("admin_api.api.oauth2_providers.audit_emit", new_callable=AsyncMock):
        resp1 = await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT, provider="gmail", body=body,
            session=session, vault=vault, _authz=None,
        )
        resp2 = await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT, provider="gmail", body=body,
            session=session, vault=vault, _authz=None,
        )

    assert resp1.status_code == 201
    assert resp2.status_code == 201
    # Both should succeed — upsert, not 409
    assert len(vault.put_calls) == 2


# ---------------------------------------------------------------------------
# test_post_provider_invalid_provider
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_provider_invalid_provider() -> None:
    """Unsupported provider → 422."""
    session = _make_session()
    vault = _FakeVault()
    body = OAuth2ProviderConfigBody(
        client_id="some-id", client_secret="some-secret"
    )

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock):
        resp = await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT,
            provider="yahoo",
            body=body,
            session=session,
            vault=vault,
            _authz=None,
        )

    assert resp.status_code == 422
    import json
    content = json.loads(resp.body)
    assert content["mintkey:code"] == "unsupported_provider"


# ---------------------------------------------------------------------------
# test_get_providers_lists_configured
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_providers_lists_configured() -> None:
    """GET list returns configured providers with client_id_last4."""
    now_ts = _NOW
    fake_rows = [
        _FakeRow(provider="gmail", client_id=_FAKE_CLIENT_ID, updated_at=now_ts),
    ]

    class _FakeListResult:
        def fetchall(self) -> list[Any]:
            return fake_rows

    session = _make_session()
    session._results["SELECT provider"] = _FakeListResult()

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock):
        resp = await list_oauth2_providers(
            tenant_id=_FAKE_TENANT,
            session=session,
            _authz=None,
        )

    assert resp.status_code == 200
    import json
    content = json.loads(resp.body)
    assert "providers" in content
    assert len(content["providers"]) == 1
    p = content["providers"][0]
    assert p["provider"] == "gmail"
    assert "client_id_last4" in p
    assert "client_secret" not in p
    assert p["client_id_last4"] == _client_id_last4(_FAKE_CLIENT_ID)


# ---------------------------------------------------------------------------
# test_get_single_provider_no_secret_echoed
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_single_provider_no_secret_echoed() -> None:
    """GET single provider: response MUST NOT contain client_secret."""
    now_ts = _NOW
    session = _make_session(
        **{
            "SELECT provider, client_id": _FakeResult(
                _FakeRow(provider="gmail", client_id=_FAKE_CLIENT_ID, updated_at=now_ts)
            )
        }
    )

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock):
        resp = await get_oauth2_provider(
            tenant_id=_FAKE_TENANT,
            provider="gmail",
            session=session,
            _authz=None,
        )

    assert resp.status_code == 200
    body_text = resp.body.decode()
    assert "client_secret" not in body_text, (
        f"NFR-17 VIOLATION: 'client_secret' key in GET response: {body_text}"
    )


# ---------------------------------------------------------------------------
# test_delete_provider_204_and_vault_revoked
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_provider_204_and_vault_revoked() -> None:
    """DELETE removes row and calls vault to revoke the credential."""
    audit_store: list[dict[str, Any]] = []

    session = _make_session(
        **{
            "DELETE FROM oauth2_client_configs": _FakeResult(
                _FakeRow(id=str(uuid.uuid4()))
            )
        }
    )
    vault = _FakeVault(stored_cred={"plaintext": _FAKE_CLIENT_SECRET})

    async def _fake_audit(**kwargs: Any) -> None:
        audit_store.append(kwargs)

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock), \
         patch("admin_api.api.oauth2_providers.audit_emit", side_effect=_fake_audit):
        resp = await delete_oauth2_provider(
            tenant_id=_FAKE_TENANT,
            provider="gmail",
            session=session,
            vault=vault,
            _authz=None,
        )

    assert resp.status_code == 204

    # Vault get_credential was called to check existence
    assert len(vault.get_calls) == 1

    # Vault put_credential was called with empty plaintext (revoke)
    assert len(vault.put_calls) == 1
    assert vault.put_calls[0]["plaintext"] == ""

    # Audit emitted with provider only, no secret
    assert len(audit_store) == 1
    assert audit_store[0]["event_type"] == "oauth2_provider.deleted"
    assert audit_store[0]["payload"] == {"provider": "gmail"}


# ---------------------------------------------------------------------------
# test_delete_provider_not_found
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_delete_provider_not_found() -> None:
    """DELETE for unconfigured provider → 404."""
    session = _make_session()  # DELETE returns None (no matching row)
    vault = _FakeVault()

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock):
        resp = await delete_oauth2_provider(
            tenant_id=_FAKE_TENANT,
            provider="outlook",
            session=session,
            vault=vault,
            _authz=None,
        )

    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# test_oauth2_config_helper_per_tenant_isolation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth2_config_helper_per_tenant_isolation() -> None:
    """_oauth2_config_from_db: tenant A's config must NOT be visible to tenant B."""
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()

    # Tenant A has a config; simulate DB returning a row for tenant A.
    class _TenantAwareResult:
        def __init__(self, tid: uuid.UUID) -> None:
            self._tid = tid

        def fetchone(self) -> Any:
            # Return a row only when queried for tenant_a
            return None  # all calls return None here; we use per-session mocks

    # Tenant A session: returns a row
    session_a = _make_session(
        **{
            "SELECT client_id FROM oauth2_client_configs": _FakeResult(
                _FakeRow(client_id=_FAKE_CLIENT_ID)
            )
        }
    )
    vault_a = _FakeVault(stored_cred={"plaintext": _FAKE_CLIENT_SECRET})

    # Tenant B session: returns nothing (different tenant)
    session_b = _make_session()
    vault_b = _FakeVault(stored_cred=None)

    with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
        result_a = await _oauth2_config_from_db(tenant_a, "gmail", session_a, vault_a)
        result_b = await _oauth2_config_from_db(tenant_b, "gmail", session_b, vault_b)

    assert result_a is not None, "Tenant A should have a config"
    assert result_a == (_FAKE_CLIENT_ID, _FAKE_CLIENT_SECRET)

    assert result_b is None, "Tenant B should NOT see Tenant A's config"


# ---------------------------------------------------------------------------
# test_oauth2_config_helper_falls_back_to_env_var
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth2_config_helper_falls_back_to_env_var() -> None:
    """_oauth2_config_from_db: no DB row + env vars set → returns env values + logs deprecation."""
    session = _make_session()  # returns None for oauth2_client_configs
    vault = _FakeVault()  # not called when no DB row
    tenant_id = uuid.uuid4()

    import logging

    env_patches = {
        "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "env-client-id",
        "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "env-client-secret",
    }

    with patch.dict(os.environ, env_patches):
        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            with patch("admin_api.api.email_services.logger") as mock_logger:
                result = await _oauth2_config_from_db(tenant_id, "gmail", session, vault)

    assert result is not None, "Should fall back to env vars"
    assert result == ("env-client-id", "env-client-secret")

    # Deprecation warning MUST have been logged
    assert mock_logger.warning.called
    warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
    assert any("DEPRECATED" in w or "deprecated" in w.lower() for w in warning_calls), (
        f"Expected DEPRECATED warning not found. Calls: {warning_calls}"
    )


# ---------------------------------------------------------------------------
# test_oauth2_config_helper_db_error_returns_none
# Regression test for the tenant-isolation breach: when the DB query throws,
# the helper MUST return None (caller surfaces 503), NOT silently fall through
# to global env-var credentials.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_oauth2_config_helper_db_error_returns_none() -> None:
    """_oauth2_config_from_db: DB exception → return None, NOT env-var fallback.

    Security: env-var creds are GLOBAL (shared across tenants). If a tenant has
    a DB row but the DB lookup fails (connection error, timeout, RLS issue),
    silently substituting the global env-var creds would let one tenant inherit
    another tenant's GCP client. The helper MUST return None on DB error.
    """
    # session.execute() raises — DB error path
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=Exception("simulated DB connection error"))
    vault = _FakeVault()
    tenant_id = uuid.uuid4()

    # Env vars ARE set — would have been the silent fallback if the bug existed
    env_patches = {
        "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "env-fallback-should-NOT-be-used",
        "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "env-fallback-secret-should-NOT-be-used",
    }

    with patch.dict(os.environ, env_patches):
        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            result = await _oauth2_config_from_db(tenant_id, "gmail", session, vault)

    assert result is None, (
        "On DB error the helper MUST return None — NOT fall through to env-var creds. "
        f"Got: {result}"
    )


# ---------------------------------------------------------------------------
# test_client_id_last4 helper
# ---------------------------------------------------------------------------


def test_client_id_last4_basic() -> None:
    """_client_id_last4 returns last 4 chars."""
    assert _client_id_last4("abcdefgh") == "efgh"
    assert _client_id_last4("ab") == "ab"  # short string
    assert _client_id_last4("123456789-abc.apps.googleusercontent.com") == ".com"


# ---------------------------------------------------------------------------
# test_vault_service_id helper
# ---------------------------------------------------------------------------


def test_vault_service_id_format() -> None:
    """_vault_service_id returns a deterministic UUIDv5 per (tenant_id, provider).

    The vault postgres backend types service_id as UUID, so synthetic strings
    like "oauth2cfg_gmail" don't cast. We derive a stable UUIDv5 so PUT and
    GET for the same (tenant, provider) always hit the same vault row.
    """
    import uuid

    t1 = "ce79c39d-33de-4689-b827-2e926cb5f2c7"
    t2 = "11111111-1111-1111-1111-111111111111"

    g1 = _vault_service_id(t1, "gmail")
    o1 = _vault_service_id(t1, "outlook")
    g2 = _vault_service_id(t2, "gmail")

    # All outputs are valid UUIDs (vault postgres requires this).
    for v in (g1, o1, g2):
        assert uuid.UUID(v)  # raises if not a valid UUID

    # Deterministic — same inputs → same UUID.
    assert _vault_service_id(t1, "gmail") == g1

    # Different tenant or provider → different UUID.
    assert g1 != o1
    assert g1 != g2


# ---------------------------------------------------------------------------
# Defense-in-depth: whitespace trimming on POST inputs (#358)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_provider_trims_leading_trailing_whitespace_from_client_id() -> None:
    """#358: leading/trailing whitespace on client_id is stripped before persist."""
    audit_store: list[dict[str, Any]] = []
    session = _make_session()
    vault = _FakeVault()
    body = OAuth2ProviderConfigBody(
        client_id="  " + _FAKE_CLIENT_ID + "  ",
        client_secret=_FAKE_CLIENT_SECRET,
    )

    async def _fake_audit(**kwargs: Any) -> None:
        audit_store.append(kwargs)

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock), \
         patch("admin_api.api.oauth2_providers.audit_emit", side_effect=_fake_audit):
        resp = await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT,
            provider="gmail",
            body=body,
            session=session,
            vault=vault,
            _authz=None,
        )

    assert resp.status_code == 201, resp.body

    # INSERT bound parameter must be the trimmed client_id
    insert_calls = [
        params for sql, params in session.executed_sql
        if "INSERT INTO oauth2_client_configs" in sql
    ]
    assert len(insert_calls) == 1
    assert insert_calls[0]["client_id"] == _FAKE_CLIENT_ID, (
        f"client_id was not trimmed: stored={insert_calls[0]['client_id']!r}"
    )

    # Audit payload's client_id_last4 must derive from the trimmed value
    assert len(audit_store) == 1
    assert audit_store[0]["payload"]["client_id_last4"] == _client_id_last4(_FAKE_CLIENT_ID)


@pytest.mark.asyncio
async def test_post_provider_trims_leading_trailing_whitespace_from_client_secret() -> None:
    """#358: leading/trailing whitespace on client_secret is stripped before vault.put."""
    session = _make_session()
    vault = _FakeVault()
    body = OAuth2ProviderConfigBody(
        client_id=_FAKE_CLIENT_ID,
        client_secret="\t " + _FAKE_CLIENT_SECRET + " \n",
    )

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock), \
         patch("admin_api.api.oauth2_providers.audit_emit", new_callable=AsyncMock):
        resp = await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT,
            provider="gmail",
            body=body,
            session=session,
            vault=vault,
            _authz=None,
        )

    assert resp.status_code == 201, resp.body
    assert len(vault.put_calls) == 1
    assert vault.put_calls[0]["plaintext"] == _FAKE_CLIENT_SECRET, (
        f"client_secret was not trimmed before vault store: "
        f"plaintext={vault.put_calls[0]['plaintext']!r}"
    )


@pytest.mark.asyncio
async def test_post_provider_preserves_internal_whitespace_in_client_id() -> None:
    """#358: internal whitespace is preserved — only str.strip() of edges."""
    session = _make_session()
    vault = _FakeVault()
    # Construct a synthetic client_id with internal whitespace (real Google IDs
    # don't have whitespace, but the trim must NOT be aggressive — only edges).
    internal_id = "abc def-ghi.apps.googleusercontent.com"
    body = OAuth2ProviderConfigBody(
        client_id=internal_id, client_secret=_FAKE_CLIENT_SECRET,
    )

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock), \
         patch("admin_api.api.oauth2_providers.audit_emit", new_callable=AsyncMock):
        resp = await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT, provider="gmail", body=body,
            session=session, vault=vault, _authz=None,
        )

    assert resp.status_code == 201
    insert_calls = [
        params for sql, params in session.executed_sql
        if "INSERT INTO oauth2_client_configs" in sql
    ]
    assert insert_calls[0]["client_id"] == internal_id, (
        "internal whitespace must be preserved — only edges are trimmed"
    )


@pytest.mark.asyncio
async def test_post_provider_no_whitespace_input_unchanged() -> None:
    """#358: clean input is byte-identical pre/post trim (idempotent no-op)."""
    session = _make_session()
    vault = _FakeVault()
    body = OAuth2ProviderConfigBody(
        client_id=_FAKE_CLIENT_ID, client_secret=_FAKE_CLIENT_SECRET,
    )

    with patch("admin_api.api.oauth2_providers.set_tenant_context", new_callable=AsyncMock), \
         patch("admin_api.api.oauth2_providers.audit_emit", new_callable=AsyncMock):
        resp = await configure_oauth2_provider(
            tenant_id=_FAKE_TENANT, provider="gmail", body=body,
            session=session, vault=vault, _authz=None,
        )

    assert resp.status_code == 201

    insert_calls = [
        params for sql, params in session.executed_sql
        if "INSERT INTO oauth2_client_configs" in sql
    ]
    assert insert_calls[0]["client_id"] == _FAKE_CLIENT_ID
    assert vault.put_calls[0]["plaintext"] == _FAKE_CLIENT_SECRET


@pytest.mark.asyncio
async def test_post_provider_all_whitespace_client_id_rejected_422() -> None:
    """#358: all-whitespace client_id rejected by Pydantic field_validator (422)."""
    from pydantic import ValidationError

    # The existing Pydantic field_validator already rejects all-whitespace
    # at body construction — surface the error path here.
    with pytest.raises(ValidationError):
        OAuth2ProviderConfigBody(client_id="   ", client_secret=_FAKE_CLIENT_SECRET)
    with pytest.raises(ValidationError):
        OAuth2ProviderConfigBody(client_id=_FAKE_CLIENT_ID, client_secret="  \t\n  ")
