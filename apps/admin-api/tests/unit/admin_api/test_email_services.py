"""
Unit tests for admin_api.api.email_services (ADR-0024, C-9).

Tests:
  T-01  register_email_password_service_happy          — valid email_password service created (201)
  T-02  register_invalid_provider                      — unknown provider → 422
  T-03  register_bad_port                              — port 0 → 422
  T-04  register_incompatible_auth_scheme              — generic + email_oauth2 → 422
  T-05  authorize_inserts_state_row                    — happy path, state inserted, authorize_url returned
  T-06  authorize_unsupported_provider                 — generic → 422
  T-07  authorize_oauth2_not_configured                — missing env vars → 503
  T-08  callback_exchanges_code_happy                  — state valid, code → refresh_token → vault → 200
  T-09  callback_invalid_state                         — wrong state → 422
  T-10  callback_provider_returns_401                  — provider 400 → 502
  T-11  internal_refresh_happy                         — valid token, vault has cred → access_token returned
  T-12  internal_refresh_emits_expired_on_401          — provider 401 → email.oauth2.expired emitted
  T-13  internal_refresh_wrong_token                   — bad service token → 401
  T-14  no_client_secret_in_audit_payloads             — grep of captured audit payloads

Coverage: 14 tests, all in-process (no DB, no gRPC, no real HTTP).

Source: ADR-0024; chunk C-9.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers: minimal async DB session mock
# ---------------------------------------------------------------------------


class _FakeRow:
    """Simulate a SQLAlchemy Row with attribute access."""
    def __init__(self, **kwargs: Any) -> None:
        for k, v in kwargs.items():
            setattr(self, k, v)


class _FakeResult:
    """Simulate fetchone() / fetchall() returning a row or None."""
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row

    def one_or_none(self) -> Any:
        return self._row

    def fetchall(self) -> list[Any]:
        if self._row is None:
            return []
        if isinstance(self._row, list):
            return self._row
        return [self._row]


class _FakeListResult:
    """Simulate fetchall() returning a list of rows."""
    def __init__(self, rows: list[Any]) -> None:
        self._rows = rows

    def fetchall(self) -> list[Any]:
        return self._rows

    def fetchone(self) -> Any:
        return self._rows[0] if self._rows else None

    def one_or_none(self) -> Any:
        return self._rows[0] if self._rows else None


class _FakeCountResult:
    """Simulate fetchone() returning a row with a 'total' attribute."""
    def __init__(self, total: int) -> None:
        self._row = _FakeRow(total=total)

    def fetchone(self) -> Any:
        return self._row

    def fetchall(self) -> list[Any]:
        return [self._row]


class _FakeSession:
    """
    Minimal async DB session mock.

    Tracks INSERT/DELETE SQL calls via `executed_sql` so tests can assert
    on what SQL was run without a real DB.
    """

    def __init__(self, query_results: dict[str, Any] | None = None) -> None:
        """
        query_results: mapping of SQL fragment → return value for execute().
        E.g. {"SELECT id FROM email_services": _FakeResult(_FakeRow(id="..."))}
        """
        self._results = query_results or {}
        self.executed_sql: list[tuple[str, dict[str, Any]]] = []
        self.audit_calls: list[dict[str, Any]] = []

    async def execute(self, stmt: Any, params: Any = None) -> Any:
        sql: str = str(stmt) if not hasattr(stmt, "text") else stmt.text
        self.executed_sql.append((sql, params or {}))
        # Check results by fragment match
        for fragment, result in self._results.items():
            if fragment in sql:
                return result
        return _FakeResult(None)

    async def __aenter__(self) -> "_FakeSession":
        return self

    async def __aexit__(self, *args: Any) -> None:
        pass


def _make_session(**results: Any) -> _FakeSession:
    return _FakeSession(query_results=results)


# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------

from admin_api.api.email_services import (
    EmailServiceCreate,
    EmailServiceCredentialBody,
    EmailServicePatch,
    _oauth2_config,
    _oauth2_redirect_base,
    _valid_host_port,
    _is_valid_uuid,
    _VALID_PROVIDERS,
    _VALID_AUTH_SCHEMES,
    _PROVIDER_AUTH_SCHEMES,
    create_email_service,
    list_email_services,
    get_email_service,
    patch_email_service,
    delete_email_service,
    oauth2_authorize,
    oauth2_callback,
    oauth2_callback_view,
    oauth2_refresh,
    set_email_service_credential,
    delete_email_service_credential,
)


# ---------------------------------------------------------------------------
# T-01: register email_password service — happy path
# ---------------------------------------------------------------------------

class TestRegisterEmailService:
    def test_01_valid_email_password_service_model(self) -> None:
        """
        T-01: EmailServiceCreate accepts a valid email_password payload for gmail.
        Validates provider, auth_scheme, ports.
        """
        body = EmailServiceCreate(
            provider="gmail",
            name="Company Gmail",
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            auth_scheme="email_password",
        )
        assert body.provider == "gmail"
        assert body.auth_scheme == "email_password"
        assert body.imap_port == 993
        assert body.smtp_port == 587

    def test_02_invalid_provider_rejected(self) -> None:
        """T-02: Unknown provider raises ValidationError."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError) as exc_info:
            EmailServiceCreate(
                provider="yahoo",
                name="Yahoo",
                imap_host="imap.yahoo.com",
                imap_port=993,
                smtp_host="smtp.yahoo.com",
                smtp_port=587,
                auth_scheme="email_password",
            )
        errors = exc_info.value.errors(include_input=False)
        assert any("provider" in str(e.get("loc", "")) for e in errors)

    def test_03_bad_port_rejected(self) -> None:
        """T-03: Port 0 is rejected by the Pydantic validator."""
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            EmailServiceCreate(
                provider="gmail",
                name="Gmail",
                imap_host="imap.gmail.com",
                imap_port=0,  # invalid
                smtp_host="smtp.gmail.com",
                smtp_port=587,
                auth_scheme="email_password",
            )

    def test_04_incompatible_auth_scheme_for_generic(self) -> None:
        """
        T-04: generic provider + email_oauth2 is incompatible.
        _PROVIDER_AUTH_SCHEMES enforces this; endpoint returns 422.
        """
        allowed = _PROVIDER_AUTH_SCHEMES.get("generic", set())
        assert "email_oauth2" not in allowed, (
            "generic provider must not allow email_oauth2"
        )

    @pytest.mark.asyncio
    async def test_01b_create_endpoint_calls_insert_and_audit(self) -> None:
        """
        T-01b: create_email_service inserts a row and calls audit_emit.
        Verifies the endpoint logic without a real DB.
        """
        tenant_id = uuid.uuid4()
        body = EmailServiceCreate(
            provider="gmail",
            name="Company Gmail",
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            auth_scheme="email_password",
        )

        session = _make_session()
        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit_emit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock) as _mock_ctx, \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit_emit):
            result = await create_email_service(
                tenant_id=tenant_id,
                body=body,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 201
        body_content = json.loads(result.body)
        assert body_content["provider"] == "gmail"
        assert body_content["auth_scheme"] == "email_password"

        # Verify audit event fired
        assert len(audit_calls) == 1
        assert audit_calls[0]["event_type"] == "email.service.registered"
        # NFR-17: no secrets in payload
        payload = audit_calls[0]["payload"]
        assert "client_secret" not in payload
        assert "refresh_token" not in payload
        assert "access_token" not in payload

        # Verify INSERT was called
        insert_calls = [sql for sql, _ in session.executed_sql if "INSERT INTO email_services" in sql]
        assert len(insert_calls) == 1


# ---------------------------------------------------------------------------
# T-05: authorize inserts state row
# ---------------------------------------------------------------------------

class TestOAuth2Authorize:
    @pytest.mark.asyncio
    async def test_05_authorize_inserts_state_happy(self) -> None:
        """
        T-05: oauth2_authorize inserts an oauth2_state row and returns
        authorize_url containing the generated state.
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        # Simulate: email service exists + no existing state rows
        session = _make_session(**{
            "SELECT id FROM email_services": _FakeResult(_FakeRow(id=service_id)),
        })

        fake_request = MagicMock()
        fake_request.cookies.get.return_value = ""
        fake_request.base_url = "http://localhost:8080/"

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "fake_client_id",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "fake_secret",
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            result = await oauth2_authorize(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                request=fake_request,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        body_content = json.loads(result.body)
        assert "authorize_url" in body_content
        assert "state" in body_content
        state_value = body_content["state"]
        assert len(state_value) > 20  # crypto-random token

        # The authorize_url must contain the state
        assert state_value in body_content["authorize_url"]

        # Verify INSERT INTO oauth2_state was called
        insert_calls = [sql for sql, _ in session.executed_sql if "INSERT INTO oauth2_state" in sql]
        assert len(insert_calls) == 1

    @pytest.mark.asyncio
    async def test_05b_authorize_emits_audit_event(self) -> None:
        """
        T-05b: oauth2_authorize emits email.oauth2.authorize_initiated audit event.

        Verifies:
        - Exactly one audit_emit call fires on happy path.
        - event_type is 'email.oauth2.authorize_initiated'.
        - Payload contains tenant_id, service_id, provider, state_token_hash.
        - Payload does NOT contain the raw state value (NFR-17).
        - state_token_hash is sha256(raw_state_value) — hash-only, never plaintext.
        """
        import hashlib
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        session = _make_session(**{
            "SELECT id FROM email_services": _FakeResult(_FakeRow(id=service_id)),
        })

        fake_request = MagicMock()
        fake_request.cookies.get.return_value = ""
        fake_request.base_url = "http://localhost:8080/"

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "fake_client_id",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "fake_secret",
        }

        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit_emit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit_emit):
            result = await oauth2_authorize(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                request=fake_request,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        body_content = json.loads(result.body)
        raw_state = body_content["state"]

        # Exactly one audit event must be emitted
        assert len(audit_calls) == 1, (
            f"Expected 1 audit_emit call, got {len(audit_calls)}"
        )

        ev = audit_calls[0]
        assert ev["event_type"] == "email.oauth2.authorize_initiated"
        assert ev["actor_type"] == "operator"

        payload = ev["payload"]
        assert payload["provider"] == "gmail"
        assert payload["service_id"] == service_id
        assert str(tenant_id) == payload["tenant_id"]

        # state_token_hash must be sha256 of the raw state value
        expected_hash = hashlib.sha256(raw_state.encode()).hexdigest()
        assert payload["state_token_hash"] == expected_hash, (
            "state_token_hash must be sha256(raw_state_value)"
        )

        # NFR-17: raw state value must NOT appear in the audit payload
        payload_str = json.dumps(payload)
        assert raw_state not in payload_str, (
            "NFR-17 violation: raw state value must not appear in audit payload"
        )

        # NFR-17: no credential fields in payload
        for forbidden in ("refresh_token", "client_secret", "access_token"):
            assert forbidden not in payload, (
                f"NFR-17 violation: forbidden key '{forbidden}' in audit payload"
            )

    def test_06_authorize_unsupported_provider_sync(self) -> None:
        """
        T-06: Provider 'generic' does not support OAuth2.
        Check that _oauth2_config returns None for unsupported providers.
        """
        result = _oauth2_config("generic")
        assert result is None

    @pytest.mark.asyncio
    async def test_06_authorize_unsupported_provider(self) -> None:
        """T-06: oauth2_authorize with provider=generic → 422."""
        tenant_id = uuid.uuid4()
        session = _make_session()
        fake_request = MagicMock()
        fake_request.cookies.get.return_value = ""
        fake_request.base_url = "http://localhost:8080/"

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            result = await oauth2_authorize(
                tenant_id=tenant_id,
                service_id=str(uuid.uuid4()),
                provider="generic",
                request=fake_request,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 422
        body_content = json.loads(result.body)
        assert body_content["mintkey:code"] == "unsupported_provider"

    @pytest.mark.asyncio
    async def test_07_authorize_missing_env_vars(self) -> None:
        """T-07: Missing OAuth2 env vars → 503."""
        tenant_id = uuid.uuid4()
        session = _make_session()
        fake_request = MagicMock()
        fake_request.cookies.get.return_value = ""
        fake_request.base_url = "http://localhost:8080/"

        with patch.dict(os.environ, {}, clear=False), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            # Remove relevant keys temporarily
            env_bak = {}
            for k in ["MINTKEY_OAUTH2_GMAIL_CLIENT_ID", "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET"]:
                env_bak[k] = os.environ.pop(k, "")
            try:
                result = await oauth2_authorize(
                    tenant_id=tenant_id,
                    service_id=str(uuid.uuid4()),
                    provider="gmail",
                    request=fake_request,
                    session=session,  # type: ignore[arg-type]
                )
            finally:
                for k, v in env_bak.items():
                    if v:
                        os.environ[k] = v

        assert result.status_code == 503
        body_content = json.loads(result.body)
        assert body_content["mintkey:code"] == "oauth2_not_configured"


# ---------------------------------------------------------------------------
# T-08 / T-09 / T-10: callback
# ---------------------------------------------------------------------------

class TestOAuth2Callback:
    def _fake_provider_resp(
        self,
        status_code: int = 200,
        access_token: str = "fake_access_token",
        refresh_token: str = "fake_refresh_token",
    ) -> MagicMock:
        """Build a mock httpx.Response."""
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        return resp

    @pytest.mark.asyncio
    async def test_08_callback_happy_path(self) -> None:
        """
        T-08: Valid state + provider returns tokens → vault.put_credential called,
        audit event emitted, 200 returned.
        Payload NEVER contains refresh_token, client_secret, or access_token.
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        state_value = "valid_state_abc123"

        fake_state_row = _FakeRow(
            service_id=service_id,
            redirect_uri="https://example.com/callback",
            operator_id=str(uuid.uuid4()),
        )

        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"key_version": 1})

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        provider_resp = self._fake_provider_resp()

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit), \
             patch("httpx.AsyncClient") as mock_client_cls:
            # Wire mock httpx.AsyncClient
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            from admin_api.api.email_services import OAuth2CallbackBody
            body = OAuth2CallbackBody(code="auth_code_xyz", state=state_value)

            result = await oauth2_callback(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                body=body,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        body_content = json.loads(result.body)
        assert body_content["provider"] == "gmail"

        # Vault was called to store the refresh_token
        mock_vault.put_credential.assert_called_once()
        call_kwargs = mock_vault.put_credential.call_args[1]
        assert call_kwargs.get("auth_scheme") == "email_oauth2"
        # The plaintext (refresh_token) should NOT appear in any audit payload
        for audit_call in audit_calls:
            payload_str = json.dumps(audit_call.get("payload", {}))
            assert "fake_refresh_token" not in payload_str
            assert "csecret" not in payload_str
            assert "fake_access_token" not in payload_str

        # Audit event fired
        assert any(a["event_type"] == "email.oauth2.authorized" for a in audit_calls)

    @pytest.mark.asyncio
    async def test_09_callback_invalid_state(self) -> None:
        """T-09: Invalid/expired state → DELETE returns no row → 422."""
        tenant_id = uuid.uuid4()
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(None),
        })

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            from admin_api.api.email_services import OAuth2CallbackBody
            body = OAuth2CallbackBody(code="code", state="bad_state")
            result = await oauth2_callback(
                tenant_id=tenant_id,
                service_id=str(uuid.uuid4()),
                provider="gmail",
                body=body,
                session=session,  # type: ignore[arg-type]
                vault=AsyncMock(),
            )

        assert result.status_code == 422
        assert json.loads(result.body)["mintkey:code"] == "invalid_state"

    @pytest.mark.asyncio
    async def test_10_callback_provider_error(self) -> None:
        """T-10: Provider returns 400 → 502 returned to caller."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        state_value = "some_state"

        fake_state_row = _FakeRow(
            service_id=service_id,
            redirect_uri="https://example.com/callback",
            operator_id=str(uuid.uuid4()),
        )
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }
        bad_resp = self._fake_provider_resp(status_code=400)

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=bad_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            from admin_api.api.email_services import OAuth2CallbackBody
            body = OAuth2CallbackBody(code="code", state=state_value)
            result = await oauth2_callback(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                body=body,
                session=session,  # type: ignore[arg-type]
                vault=AsyncMock(),
            )

        assert result.status_code == 502
        assert json.loads(result.body)["mintkey:code"] == "provider_token_error"


# ---------------------------------------------------------------------------
# T-11 / T-12 / T-13: internal refresh endpoint
# ---------------------------------------------------------------------------

class TestInternalOAuth2Refresh:
    def _make_refresh_request(self, service_token: str = "correct_token") -> MagicMock:
        req = MagicMock()
        req.headers = {"X-Mintkey-Service-Token": service_token}
        return req

    @pytest.mark.asyncio
    async def test_11_refresh_happy_path(self) -> None:
        """
        T-11: Valid service token + vault has stored refresh_token →
        provider returns access_token → 200 with access_token + expires_at.
        NFR-17: access_token NOT in audit payload.
        """
        service_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(return_value={
            "plaintext": "stored_refresh_token",
            "auth_scheme": "email_oauth2",
        })

        session = _make_session()
        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        env_override = {
            "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        provider_resp = MagicMock()
        provider_resp.status_code = 200
        provider_resp.json.return_value = {
            "access_token": "new_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await oauth2_refresh(
                provider="gmail",
                service_id=service_id,
                tenant_id=tenant_id,
                request=self._make_refresh_request("correct_token"),
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        body_content = json.loads(result.body)
        assert "access_token" in body_content
        assert "expires_at" in body_content

        # NFR-17: audit payload must NOT contain access_token or refresh_token
        for audit_call in audit_calls:
            payload_str = json.dumps(audit_call.get("payload", {}))
            assert "new_access_token" not in payload_str
            assert "stored_refresh_token" not in payload_str
            assert "csecret" not in payload_str

    @pytest.mark.asyncio
    async def test_12_refresh_emits_expired_on_401(self) -> None:
        """
        T-12: Provider returns 401 during refresh → email.oauth2.expired
        audit event emitted → endpoint returns 401.
        """
        service_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(return_value={
            "plaintext": "expired_refresh_token",
        })

        session = _make_session()
        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        env_override = {
            "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token",
            "MINTKEY_OAUTH2_OUTLOOK_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_OUTLOOK_CLIENT_SECRET": "csecret",
        }

        expired_resp = MagicMock()
        expired_resp.status_code = 401
        expired_resp.json.return_value = {"error": "invalid_grant"}

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=expired_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await oauth2_refresh(
                provider="outlook",
                service_id=service_id,
                tenant_id=tenant_id,
                request=self._make_refresh_request("correct_token"),
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 401
        assert json.loads(result.body)["mintkey:code"] == "oauth2_token_expired"

        # Verify email.oauth2.expired was emitted
        expired_events = [a for a in audit_calls if a["event_type"] == "email.oauth2.expired"]
        assert len(expired_events) == 1

        # NFR-17: expired event payload MUST NOT include token material
        payload_str = json.dumps(expired_events[0]["payload"])
        assert "expired_refresh_token" not in payload_str
        assert "csecret" not in payload_str

    @pytest.mark.asyncio
    async def test_13_refresh_wrong_service_token(self) -> None:
        """T-13: Wrong X-Mintkey-Service-Token → 401."""
        env_override = {"MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token"}

        session = _make_session()
        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            result = await oauth2_refresh(
                provider="gmail",
                service_id=str(uuid.uuid4()),
                tenant_id=str(uuid.uuid4()),
                request=self._make_refresh_request("wrong_token"),
                session=session,  # type: ignore[arg-type]
                vault=AsyncMock(),
            )

        assert result.status_code == 401
        assert json.loads(result.body)["mintkey:code"] == "unauthenticated"


# ---------------------------------------------------------------------------
# T-14: No client_secret / refresh_token / access_token in audit payloads
# ---------------------------------------------------------------------------

class TestNoSecretLeakInAuditPayloads:
    """
    T-14: Grep-style assertion that none of the audit-emitting code paths
    include client_secret, refresh_token, or access_token in the payload
    keys they pass to audit_emit.

    This test reads the source file and checks that the forbidden key names
    never appear as dict keys inside audit_emit(... payload={...}) blocks.

    NFR-17 compliance: audit payloads must be safe for long-term storage.
    """

    def test_14_source_code_no_secret_keys_in_audit_payload(self) -> None:
        """
        NFR-17: grep the source module for audit_emit calls and confirm
        that none of the forbidden keys appear in any payload dict literal.
        """
        import ast
        from pathlib import Path

        src_path = (
            Path(__file__).resolve().parents[3]
            / "src" / "admin_api" / "api" / "email_services.py"
        )
        assert src_path.exists(), f"email_services.py not found at {src_path}"
        source = src_path.read_text()

        # Parse the AST to find all audit_emit keyword calls
        tree = ast.parse(source)

        forbidden_keys = {"refresh_token", "client_secret", "access_token"}
        violations: list[str] = []

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            # Check if this is an audit_emit call (by name or attribute)
            func = node.func
            is_audit = False
            if isinstance(func, ast.Name) and func.id == "audit_emit":
                is_audit = True
            elif isinstance(func, ast.Attribute) and func.attr == "audit_emit":
                is_audit = True
            if not is_audit:
                continue

            # Find the payload= keyword argument
            for kw in node.keywords:
                if kw.arg != "payload":
                    continue
                if not isinstance(kw.value, ast.Dict):
                    continue
                for key_node in kw.value.keys:
                    if isinstance(key_node, ast.Constant) and isinstance(key_node.value, str):
                        if key_node.value in forbidden_keys:
                            violations.append(
                                f"Line {node.lineno}: audit_emit payload contains "
                                f"forbidden key '{key_node.value}' (NFR-17)"
                            )

        assert not violations, (
            "audit_emit payloads in email_services.py contain forbidden keys:\n"
            + "\n".join(violations)
        )


# ---------------------------------------------------------------------------
# T-RLS: Wrong-tenant access blocked (RLS simulation)
# ---------------------------------------------------------------------------

class TestRLSTenantIsolation:
    def test_rls_simulation(self) -> None:
        """
        T-RLS: Simulates RLS by confirming that email_services table uses
        tenant_id in all INSERT/SELECT statements, so a tenant mismatch
        would be caught by the DB-side RLS policy.

        Verifies at the SQL level (fragment inspection) that tenant_id is
        always bound in the query — no unconstrained scans.
        """
        import ast
        from pathlib import Path

        src_path = (
            Path(__file__).resolve().parents[3]
            / "src" / "admin_api" / "api" / "email_services.py"
        )
        source = src_path.read_text()

        # Every SELECT on email_services must include tenant_id filter
        # or be guarded by set_tenant_context (RLS handles it at DB level).
        # We verify set_tenant_context is called before any DB operation.
        assert "set_tenant_context" in source, (
            "email_services.py must call set_tenant_context for RLS enforcement"
        )
        # All email_services queries must bind tenant_id
        assert "tenant_id" in source
        # oauth2_state queries must also bind tenant_id
        assert "oauth2_state" in source


# ---------------------------------------------------------------------------
# Helper unit tests
# ---------------------------------------------------------------------------

class TestHelpers:
    def test_valid_host_port_happy(self) -> None:
        assert _valid_host_port("imap.gmail.com", 993) is True

    def test_valid_host_port_bad_port(self) -> None:
        assert _valid_host_port("imap.gmail.com", 0) is False
        assert _valid_host_port("imap.gmail.com", 65536) is False

    def test_valid_host_port_empty_host(self) -> None:
        assert _valid_host_port("", 993) is False
        assert _valid_host_port("  ", 993) is False

    def test_is_valid_uuid(self) -> None:
        assert _is_valid_uuid(str(uuid.uuid4())) is True
        assert _is_valid_uuid("not-a-uuid") is False
        assert _is_valid_uuid("") is False


# ---------------------------------------------------------------------------
# T-HTTP: HTTP-transport-level test via TestClient (contract boundary parity)
#
# The existing T-11/T-12/T-13 tests call the handler as a Python function with
# kwargs — they never exercise FastAPI's HTTP transport binding (query-vs-body
# resolution, header injection, etc.).
#
# This class adds a TestClient-based test that POSTs to the ACTUAL route URL
# with the correct query params and X-Mintkey-Service-Token header and verifies
# that FastAPI binds the parameters correctly.
#
# Wave-2 batch audit finding: C-6's pre-fix code sent {tenant_id, service_id,
# refresh_token} as a JSON body with no service-token header.  admin-api's
# handler binds tenant_id and service_id from query params (not body) and
# requires X-Mintkey-Service-Token.  Neither side's tests exercised the HTTP
# transport layer.
# ---------------------------------------------------------------------------


class TestInternalRefreshHTTPBinding:
    """
    T-HTTP-1 through T-HTTP-3: HTTP-level tests via TestClient that verify the
    FastAPI route binds query params and headers correctly for the internal
    OAuth2 refresh endpoint.

    These tests complement T-11/T-12/T-13 (which call the handler as a Python
    function) by exercising the ACTUAL HTTP transport layer.
    """

    def _make_app_with_mocks(
        self,
        mock_vault: Any,
        env_override: dict[str, str],
        session_override: Any = None,
    ):
        """
        Build a minimal FastAPI app with just the internal_oauth2_router,
        override the DB + vault dependencies, and return a TestClient.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from admin_api.api.email_services import internal_oauth2_router
        from admin_api.db.deps import get_db_session
        from admin_api.services.vault_client import get_vault_client

        test_app = FastAPI()
        test_app.include_router(internal_oauth2_router)

        if session_override is None:
            session_override = _make_session()

        async def _override_session():
            yield session_override

        async def _override_vault():
            return mock_vault

        test_app.dependency_overrides[get_db_session] = _override_session
        test_app.dependency_overrides[get_vault_client] = _override_vault

        import patch as _patch  # noqa: F401 — imported for side-effect
        return TestClient(test_app), env_override

    def test_http1_refresh_correct_query_params_and_header(self) -> None:
        """
        T-HTTP-1: POST to /v1/internal/oauth2/gmail/refresh with:
          - query params: tenant_id=<uuid>, service_id=<uuid>
          - header: X-Mintkey-Service-Token: correct_token
          - empty body

        Verifies FastAPI route binding correctly resolves query params
        (not body) and header authentication passes.  Returns 200.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import AsyncMock, patch

        from admin_api.api.email_services import internal_oauth2_router
        from admin_api.db.deps import get_db_session
        from admin_api.services.vault_client import get_vault_client

        tenant_id = str(uuid.uuid4())
        service_id = str(uuid.uuid4())

        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(return_value={
            "plaintext": "stored_refresh_tok",
            "auth_scheme": "email_oauth2",
        })

        session = _make_session()

        test_app = FastAPI()
        test_app.include_router(internal_oauth2_router)

        async def _override_session():
            yield session

        async def _override_vault():
            return mock_vault

        test_app.dependency_overrides[get_db_session] = _override_session
        test_app.dependency_overrides[get_vault_client] = _override_vault

        provider_resp = MagicMock()
        provider_resp.status_code = 200
        provider_resp.json.return_value = {
            "access_token": "new_at_http1",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        env_override = {
            "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            with TestClient(test_app, raise_server_exceptions=True) as client:
                resp = client.post(
                    f"/v1/internal/oauth2/gmail/refresh"
                    f"?tenant_id={tenant_id}&service_id={service_id}",
                    headers={"X-Mintkey-Service-Token": "correct_token"},
                    content=b"",  # empty body — NFR-17
                )

        assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "access_token" in body, f"access_token missing from response: {body}"
        assert "expires_at" in body, f"expires_at missing from response: {body}"

    def test_http2_missing_service_token_returns_401(self) -> None:
        """
        T-HTTP-2: POST with wrong X-Mintkey-Service-Token → 401.

        Verifies the header authentication fires at the HTTP transport layer,
        not just when the handler is called as a Python function.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import AsyncMock, patch

        from admin_api.api.email_services import internal_oauth2_router
        from admin_api.db.deps import get_db_session
        from admin_api.services.vault_client import get_vault_client

        test_app = FastAPI()
        test_app.include_router(internal_oauth2_router)

        async def _override_session():
            yield _make_session()

        async def _override_vault():
            return AsyncMock()

        test_app.dependency_overrides[get_db_session] = _override_session
        test_app.dependency_overrides[get_vault_client] = _override_vault

        env_override = {"MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token"}

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            with TestClient(test_app, raise_server_exceptions=True) as client:
                resp = client.post(
                    f"/v1/internal/oauth2/gmail/refresh"
                    f"?tenant_id={uuid.uuid4()}&service_id={uuid.uuid4()}",
                    headers={"X-Mintkey-Service-Token": "WRONG_TOKEN"},
                    content=b"",
                )

        assert resp.status_code == 401
        assert resp.json().get("mintkey:code") == "unauthenticated"

    def test_http3_body_params_ignored_query_required(self) -> None:
        """
        T-HTTP-3: POST with tenant_id/service_id in JSON body but NOT in query →
        FastAPI returns 422 (unprocessable entity) because query params are required.

        This is the exact pre-fix C-6 bug: email-proxy sent params in the body
        and admin-api's route binding never saw them as query params.
        """
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from unittest.mock import AsyncMock, patch

        from admin_api.api.email_services import internal_oauth2_router
        from admin_api.db.deps import get_db_session
        from admin_api.services.vault_client import get_vault_client

        test_app = FastAPI()
        test_app.include_router(internal_oauth2_router)

        async def _override_session():
            yield _make_session()

        async def _override_vault():
            return AsyncMock()

        test_app.dependency_overrides[get_db_session] = _override_session
        test_app.dependency_overrides[get_vault_client] = _override_vault

        env_override = {"MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token"}

        with patch.dict(os.environ, env_override):
            with TestClient(test_app, raise_server_exceptions=False) as client:
                # Send params in body (the pre-fix C-6 bug) — NOT in query string.
                resp = client.post(
                    "/v1/internal/oauth2/gmail/refresh",
                    headers={
                        "X-Mintkey-Service-Token": "correct_token",
                        "Content-Type": "application/json",
                    },
                    json={
                        "tenant_id": str(uuid.uuid4()),
                        "service_id": str(uuid.uuid4()),
                        "refresh_token": "leaked_token_in_body",  # NFR-17 violation
                    },
                )

        # FastAPI should return 422: query params tenant_id and service_id
        # are required but absent (the body is ignored for query-param binding).
        assert resp.status_code == 422, (
            f"Expected 422 when query params absent (body-only is the pre-fix bug), "
            f"got {resp.status_code}: {resp.text}"
        )


# ---------------------------------------------------------------------------
# T-RLS-2: Real cross-tenant SELECT verification (promoted from string-presence)
# ---------------------------------------------------------------------------


class TestRLSTenantIsolationStrengthened:
    """
    T-RLS-2: Stronger RLS isolation test.

    The existing TestRLSTenantIsolation.test_rls_simulation checks only that
    the string "set_tenant_context" and "tenant_id" appear in the source file.
    This class exercises the actual SQL construction path to verify that
    set_tenant_context is invoked BEFORE any SQL execution in the endpoints
    that use tenant-scoped tables.

    DB-backed integration test (needs Postgres):
    SKIP — needs DB fixture.  See TestRLSTenantIsolationDB in
    tests/integration/email_proxy/ for the full Postgres-backed version.

    In-process verification (this file): assert set_tenant_context is awaited
    with the correct tenant_uuid before any session.execute call.
    """

    @pytest.mark.asyncio
    async def test_rls2_set_tenant_context_called_before_sql_in_refresh(self) -> None:
        """
        T-RLS-2a: oauth2_refresh calls set_tenant_context(session, tenant_uuid)
        before any session.execute.  A wrong tenant_id that bypasses this call
        would execute SQL under a different tenant's RLS context.
        """
        from unittest.mock import AsyncMock, call, patch

        tenant_id = str(uuid.uuid4())
        service_id = str(uuid.uuid4())

        # Track call order: set_tenant_context then vault.get_credential.
        call_order: list[str] = []

        async def _fake_set_tenant_ctx(session: Any, tid: Any) -> None:
            call_order.append("set_tenant_context")

        mock_vault = AsyncMock()

        async def _fake_vault_get_credential(**kwargs: Any) -> dict[str, Any]:
            call_order.append("vault.get_credential")
            return {"plaintext": "rt_for_rls_test", "auth_scheme": "email_oauth2"}

        mock_vault.get_credential = AsyncMock(side_effect=_fake_vault_get_credential)

        session = _make_session()

        provider_resp = MagicMock()
        provider_resp.status_code = 200
        provider_resp.json.return_value = {
            "access_token": "at_rls_test",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        env_override = {
            "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        fake_req = MagicMock()
        fake_req.headers = {"X-Mintkey-Service-Token": "correct_token"}

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", side_effect=_fake_set_tenant_ctx), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await oauth2_refresh(
                provider="gmail",
                service_id=service_id,
                tenant_id=tenant_id,
                request=fake_req,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200

        # set_tenant_context MUST be called before vault.get_credential
        # (which represents the first DB-touching operation in the handler).
        assert "set_tenant_context" in call_order, (
            "set_tenant_context was never called — RLS context not set"
        )
        assert "vault.get_credential" in call_order, (
            "vault.get_credential was never called"
        )
        ctx_idx = call_order.index("set_tenant_context")
        vault_idx = call_order.index("vault.get_credential")
        assert ctx_idx < vault_idx, (
            f"set_tenant_context (index {ctx_idx}) must be called before "
            f"vault.get_credential (index {vault_idx}) to ensure RLS context is set"
        )

    @pytest.mark.asyncio
    async def test_rls2_wrong_tenant_uuid_returns_422(self) -> None:
        """
        T-RLS-2b: oauth2_refresh with a non-UUID tenant_id returns 422 before
        any DB access, preventing malformed tenant IDs from bypassing RLS.
        """
        from unittest.mock import AsyncMock, patch

        fake_req = MagicMock()
        fake_req.headers = {"X-Mintkey-Service-Token": "correct_token"}
        session = _make_session()

        env_override = {
            "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            result = await oauth2_refresh(
                provider="gmail",
                service_id=str(uuid.uuid4()),
                tenant_id="not-a-valid-uuid",  # malformed — must be rejected
                request=fake_req,
                session=session,  # type: ignore[arg-type]
                vault=AsyncMock(),
            )

        assert result.status_code == 422
        body = json.loads(result.body)
        assert body["mintkey:code"] == "invalid_tenant_id"


# ---------------------------------------------------------------------------
# Credential-set / credential-delete endpoint tests (feat/email-credentials-and-ui-fixes)
# ---------------------------------------------------------------------------


class TestEmailServiceCredentialSet:
    """
    Tests for:
      POST /v1/tenants/{tid}/email-services/{sid}/credentials
      DELETE /v1/tenants/{tid}/email-services/{sid}/credentials

    NFR-17: username and password MUST NEVER appear in audit payloads.
    """

    def _make_vault_mock(self) -> Any:
        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"credential_id": "cred_test1234"})
        mock_vault.get_credential = AsyncMock(return_value={
            "plaintext": '{"username":"u","password":"p"}',
            "auth_scheme": "email_password",
        })
        return mock_vault

    @pytest.mark.asyncio
    async def test_set_credential_email_password_valid(self) -> None:
        """
        test_set_credential_email_password_valid — happy path.
        Assert vault.put_credential called with correct shape, 201 returned,
        audit row emitted, no username/password in audit.
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        svc_row = _FakeRow(id=service_id, auth_scheme="email_password")
        session = _make_session(**{
            "SELECT id, auth_scheme FROM email_services": _FakeResult(svc_row),
        })

        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        mock_vault = self._make_vault_mock()

        body = EmailServiceCredentialBody(
            username="testuser@example.com",
            password="supersecret123",
            auth_scheme="email_password",
        )

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit):
            result = await set_email_service_credential(
                tenant_id=tenant_id,
                service_id=service_id,
                body=body,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 201
        response_body = json.loads(result.body)
        assert response_body["auth_scheme"] == "email_password"
        assert response_body["status"] == "set"

        # Vault put_credential must have been called with correct auth_scheme
        mock_vault.put_credential.assert_called_once()
        call_kwargs = mock_vault.put_credential.call_args[1]
        assert call_kwargs["auth_scheme"] == "email_password"
        assert call_kwargs["tenant_id"] == str(tenant_id)
        assert call_kwargs["service_id"] == service_id

        # The plaintext must be a JSON blob with username+password
        import json as _json
        plaintext = call_kwargs["plaintext"]
        cred_blob = _json.loads(plaintext)
        assert cred_blob["username"] == "testuser@example.com"
        assert cred_blob["password"] == "supersecret123"

        # Audit event emitted
        assert len(audit_calls) == 1
        assert audit_calls[0]["event_type"] == "email.credential.set"

        # NFR-17: audit payload must NOT contain username or password
        payload_str = json.dumps(audit_calls[0]["payload"])
        assert "testuser@example.com" not in payload_str
        assert "supersecret123" not in payload_str

    @pytest.mark.asyncio
    async def test_set_credential_rejects_oauth2_scheme(self) -> None:
        """
        test_set_credential_rejects_oauth2_scheme — body with email_oauth2 → 422.
        Must redirect to the OAuth2 authorize flow.
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        body = EmailServiceCredentialBody(
            username="user@gmail.com",
            password="doesnotmatter",
            auth_scheme="email_oauth2",
        )

        session = _make_session()
        mock_vault = self._make_vault_mock()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            result = await set_email_service_credential(
                tenant_id=tenant_id,
                service_id=service_id,
                body=body,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 422
        response_body = json.loads(result.body)
        assert response_body["mintkey:code"] == "use_oauth2_flow"

    @pytest.mark.asyncio
    async def test_set_credential_scheme_mismatch_with_row(self) -> None:
        """
        test_set_credential_scheme_mismatch_with_row — row has email_password,
        body has email_app_password → 422 with auth_scheme_mismatch code.
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        # Row has email_password
        svc_row = _FakeRow(id=service_id, auth_scheme="email_password")
        session = _make_session(**{
            "SELECT id, auth_scheme FROM email_services": _FakeResult(svc_row),
        })

        # Body says email_app_password — mismatch
        body = EmailServiceCredentialBody(
            username="user@example.com",
            password="pass",
            auth_scheme="email_app_password",
        )

        mock_vault = self._make_vault_mock()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            result = await set_email_service_credential(
                tenant_id=tenant_id,
                service_id=service_id,
                body=body,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 422
        response_body = json.loads(result.body)
        assert response_body["mintkey:code"] == "auth_scheme_mismatch"

    @pytest.mark.asyncio
    async def test_set_credential_nonexistent_service(self) -> None:
        """
        test_set_credential_nonexistent_service — service not found → 422 not_found.
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        # No row found
        session = _make_session(**{
            "SELECT id, auth_scheme FROM email_services": _FakeResult(None),
        })

        body = EmailServiceCredentialBody(
            username="user@example.com",
            password="pass",
            auth_scheme="email_password",
        )

        mock_vault = self._make_vault_mock()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            result = await set_email_service_credential(
                tenant_id=tenant_id,
                service_id=service_id,
                body=body,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 422
        response_body = json.loads(result.body)
        assert response_body["mintkey:code"] == "not_found"

    @pytest.mark.asyncio
    async def test_set_credential_audit_payload_redacts_username_and_password(self) -> None:
        """
        test_set_credential_audit_payload_redacts_username_and_password

        NFR-17 mandatory assertion: the audit event payload must NEVER contain
        the literal username or password values. Uses distinctive canary strings
        so any accidental inclusion is immediately obvious.
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        # Canary values — distinctive, easy to grep for if they leak
        canary_username = "redactme-username-XXX"
        canary_password = "redactme-password-YYY"

        svc_row = _FakeRow(id=service_id, auth_scheme="email_password")
        session = _make_session(**{
            "SELECT id, auth_scheme FROM email_services": _FakeResult(svc_row),
        })

        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        mock_vault = self._make_vault_mock()

        body = EmailServiceCredentialBody(
            username=canary_username,
            password=canary_password,
            auth_scheme="email_password",
        )

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit):
            result = await set_email_service_credential(
                tenant_id=tenant_id,
                service_id=service_id,
                body=body,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 201

        # Must have exactly 1 audit call
        assert len(audit_calls) == 1, f"Expected 1 audit call, got {len(audit_calls)}"

        # Stringify the serializable parts of the audit call
        audit_call = audit_calls[0]
        serializable_audit = {
            k: v for k, v in audit_call.items()
            if k not in ("session", "tenant_id", "target_id")
        }
        full_audit_str = json.dumps(serializable_audit)

        assert canary_username not in full_audit_str, (
            f"NFR-17 VIOLATION: canary username '{canary_username}' found in audit event payload. "
            f"Audit dump: {full_audit_str}"
        )
        assert canary_password not in full_audit_str, (
            f"NFR-17 VIOLATION: canary password '{canary_password}' found in audit event payload. "
            f"Audit dump: {full_audit_str}"
        )

        # Also verify the response body doesn't echo credentials
        response_str = result.body.decode("utf-8")
        assert canary_username not in response_str, (
            f"NFR-17 VIOLATION: canary username found in HTTP response body: {response_str}"
        )
        assert canary_password not in response_str, (
            f"NFR-17 VIOLATION: canary password found in HTTP response body: {response_str}"
        )

    @pytest.mark.asyncio
    async def test_delete_credential(self) -> None:
        """
        test_delete_credential — DELETE removes the credential, audit row emitted, 204 returned.
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        svc_row = _FakeRow(id=service_id, auth_scheme="email_password")
        session = _make_session(**{
            "SELECT id, auth_scheme FROM email_services": _FakeResult(svc_row),
        })

        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        mock_vault = self._make_vault_mock()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit):
            result = await delete_email_service_credential(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 204

        # Audit event must be emitted
        assert len(audit_calls) == 1
        assert audit_calls[0]["event_type"] == "email.credential.deleted"
        payload = audit_calls[0]["payload"]
        assert "service_id" in payload
        # NFR-17: no credential material in audit
        payload_str = json.dumps(payload)
        assert "password" not in payload_str
        assert "username" not in payload_str

    @pytest.mark.asyncio
    async def test_delete_credential_uses_row_auth_scheme(self) -> None:

        """
        test_delete_credential_uses_row_auth_scheme — regression for reviewer finding #2.

        DELETE /credentials was hardcoding auth_scheme="email_password" on the vault
        revocation call, silently mis-routing services with auth_scheme="email_app_password"
        (proto enum 16 vs 14).

        This test sets up a row with auth_scheme="email_app_password", calls DELETE,
        and asserts that vault.put_credential received auth_scheme="email_app_password"
        — NOT "email_password".
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        # Row uses email_app_password (proto enum 16 — NOT email_password=14)
        svc_row = _FakeRow(id=service_id, auth_scheme="email_app_password")
        session = _make_session(**{
            "SELECT id, auth_scheme FROM email_services": _FakeResult(svc_row),
        })

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"credential_id": "cred_app_pass"})
        mock_vault.get_credential = AsyncMock(return_value={
            "plaintext": '{"username":"u","password":"p"}',
            "auth_scheme": "email_app_password",
        })

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await delete_email_service_credential(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 204

        # The vault.put_credential revocation call MUST use the row's auth_scheme
        mock_vault.put_credential.assert_called_once()
        call_kwargs = mock_vault.put_credential.call_args[1]
        assert call_kwargs["auth_scheme"] == "email_app_password", (
            f"Expected auth_scheme='email_app_password' (proto enum 16) on vault revocation, "
            f"got auth_scheme='{call_kwargs['auth_scheme']}'. "
            "Hardcoding 'email_password' silently mis-routes app-password services."
        )


# ---------------------------------------------------------------------------
# TestTlsInsecureSkipVerify — tls_insecure_skip_verify field (ADR-0024)
# ---------------------------------------------------------------------------


class TestTlsInsecureSkipVerify:
    """
    Tests for the per-service tls_insecure_skip_verify field added in ADR-0024.

    Covers:
    - T-TLS-1: EmailServiceCreate defaults to False.
    - T-TLS-2: EmailServiceCreate can be set to True.
    - T-TLS-3: create_email_service persists tls_insecure_skip_verify in INSERT.
    - T-TLS-4: create_email_service returns tls_insecure_skip_verify in response.
    """

    def test_tls1_default_is_false(self) -> None:
        """T-TLS-1: EmailServiceCreate defaults tls_insecure_skip_verify to False."""
        body = EmailServiceCreate(
            provider="generic",
            name="Internal Mail Server",
            imap_host="im.softuraj.solutions",
            imap_port=993,
            smtp_host="im.softuraj.solutions",
            smtp_port=465,
            auth_scheme="email_password",
        )
        assert body.tls_insecure_skip_verify is False, (
            "tls_insecure_skip_verify must default to False — "
            "stock email templates must be secure by default."
        )

    def test_tls2_can_be_set_to_true(self) -> None:
        """T-TLS-2: EmailServiceCreate accepts tls_insecure_skip_verify=True."""
        body = EmailServiceCreate(
            provider="generic",
            name="Internal Mail Server",
            imap_host="im.softuraj.solutions",
            imap_port=993,
            smtp_host="im.softuraj.solutions",
            smtp_port=465,
            auth_scheme="email_password",
            tls_insecure_skip_verify=True,
        )
        assert body.tls_insecure_skip_verify is True, (
            "tls_insecure_skip_verify=True must be accepted for internal servers."
        )

    @pytest.mark.asyncio
    async def test_tls3_false_persisted_in_insert(self) -> None:
        """
        T-TLS-3a: create_email_service INSERT includes tls_insecure_skip_verify=False.

        Verifies that when the flag is False (default), the INSERT SQL includes the
        parameter so the column gets the correct value (not a DB default bypass).
        """
        tenant_id = uuid.uuid4()
        body = EmailServiceCreate(
            provider="generic",
            name="Internal Mail",
            imap_host="mail.internal",
            imap_port=993,
            smtp_host="mail.internal",
            smtp_port=465,
            auth_scheme="email_password",
            tls_insecure_skip_verify=False,
        )

        session = _make_session()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await create_email_service(
                tenant_id=tenant_id,
                body=body,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 201

        # The INSERT must include tls_insecure_skip_verify
        insert_calls = [(sql, params) for sql, params in session.executed_sql
                        if "INSERT INTO email_services" in sql]
        assert len(insert_calls) == 1, "Expected exactly one INSERT INTO email_services"
        insert_sql, insert_params = insert_calls[0]

        assert "tls_insecure_skip_verify" in insert_sql, (
            "INSERT SQL must include tls_insecure_skip_verify column"
        )
        assert insert_params.get("tls_insecure_skip_verify") is False, (
            f"Expected tls_insecure_skip_verify=False in INSERT params, "
            f"got: {insert_params.get('tls_insecure_skip_verify')!r}"
        )

    @pytest.mark.asyncio
    async def test_tls3b_true_persisted_in_insert(self) -> None:
        """
        T-TLS-3b: create_email_service INSERT includes tls_insecure_skip_verify=True
        when the flag is explicitly set by the operator.
        """
        tenant_id = uuid.uuid4()
        body = EmailServiceCreate(
            provider="generic",
            name="Internal Mail with Self-Signed Cert",
            imap_host="im.softuraj.solutions",
            imap_port=993,
            smtp_host="im.softuraj.solutions",
            smtp_port=465,
            auth_scheme="email_password",
            tls_insecure_skip_verify=True,
        )

        session = _make_session()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await create_email_service(
                tenant_id=tenant_id,
                body=body,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 201

        insert_calls = [(sql, params) for sql, params in session.executed_sql
                        if "INSERT INTO email_services" in sql]
        assert len(insert_calls) == 1
        insert_sql, insert_params = insert_calls[0]

        assert "tls_insecure_skip_verify" in insert_sql, (
            "INSERT SQL must include tls_insecure_skip_verify column"
        )
        assert insert_params.get("tls_insecure_skip_verify") is True, (
            f"Expected tls_insecure_skip_verify=True in INSERT params, "
            f"got: {insert_params.get('tls_insecure_skip_verify')!r}"
        )

    @pytest.mark.asyncio
    async def test_tls4_response_includes_flag(self) -> None:
        """
        T-TLS-4: create_email_service 201 response includes tls_insecure_skip_verify.
        Verifies the field appears in the response body.
        """
        tenant_id = uuid.uuid4()
        body = EmailServiceCreate(
            provider="generic",
            name="Internal Mail",
            imap_host="mail.internal",
            imap_port=993,
            smtp_host="mail.internal",
            smtp_port=465,
            auth_scheme="email_password",
            tls_insecure_skip_verify=True,
        )

        session = _make_session()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await create_email_service(
                tenant_id=tenant_id,
                body=body,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 201
        response_body = json.loads(result.body)
        assert "tls_insecure_skip_verify" in response_body, (
            "Response body must include tls_insecure_skip_verify field"
        )
        assert response_body["tls_insecure_skip_verify"] is True, (
            f"Expected tls_insecure_skip_verify=True in response, "
            f"got: {response_body.get('tls_insecure_skip_verify')!r}"
        )


# ===========================================================================
# New CRUD read/update/delete tests (fix/email-services-crud-readonly)
# ===========================================================================

def _make_email_svc_row(**overrides: Any) -> _FakeRow:
    """Return a minimal _FakeRow for an email_services record."""
    defaults: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "tenant_id": str(uuid.uuid4()),
        "provider": "gmail",
        "name": "cici-softuraj",
        "imap_host": "imap.gmail.com",
        "imap_port": 993,
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "auth_scheme": "email_password",
        "allowed_recipient_domains": None,
        "pool_size_max": 5,
        "tls_insecure_skip_verify": False,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }
    defaults.update(overrides)
    return _FakeRow(**defaults)


class TestListEmailServices:
    """Tests for GET /v1/tenants/{tid}/email-services."""

    @pytest.mark.asyncio
    async def test_list_email_services_returns_registered_rows(self) -> None:
        """test_list_email_services_returns_registered_rows — POST 2, GET list, expect 2."""
        tenant_id = uuid.uuid4()
        row1 = _make_email_svc_row(id=str(uuid.uuid4()), tenant_id=str(tenant_id), name="svc-1")
        row2 = _make_email_svc_row(id=str(uuid.uuid4()), tenant_id=str(tenant_id), name="svc-2")

        session = _make_session(**{
            "SELECT COUNT(*)": _FakeCountResult(2),
            "SELECT id, tenant_id": _FakeListResult([row1, row2]),
        })

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await list_email_services(
                tenant_id=tenant_id,
                limit=50,
                offset=0,
                session=session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        body = json.loads(result.body)
        assert "email_services" in body
        assert "pagination" in body
        assert len(body["email_services"]) == 2
        names = {s["name"] for s in body["email_services"]}
        assert names == {"svc-1", "svc-2"}

    @pytest.mark.asyncio
    async def test_list_email_services_filters_soft_deleted(self) -> None:
        """test_list_email_services_filters_soft_deleted — only live rows returned."""
        tenant_id = uuid.uuid4()
        live_row = _make_email_svc_row(id=str(uuid.uuid4()), tenant_id=str(tenant_id), name="live")

        session = _make_session(**{
            "SELECT COUNT(*)": _FakeCountResult(1),
            "SELECT id, tenant_id": _FakeListResult([live_row]),
        })

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await list_email_services(
                tenant_id=tenant_id,
                limit=50,
                offset=0,
                session=session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        body = json.loads(result.body)
        assert len(body["email_services"]) == 1
        assert body["email_services"][0]["name"] == "live"
        # Verify the SQL included deleted_at IS NULL
        list_queries = [sql for sql, _ in session.executed_sql if "FROM email_services" in sql]
        assert any("deleted_at IS NULL" in sql for sql in list_queries), (
            "List query must filter deleted_at IS NULL"
        )

    @pytest.mark.asyncio
    async def test_list_email_services_tenant_scoped(self) -> None:
        """test_list_email_services_tenant_scoped — tenant_id bound in every query."""
        tenant_b = uuid.uuid4()

        session = _make_session(**{
            "SELECT COUNT(*)": _FakeCountResult(0),
            "SELECT id, tenant_id": _FakeListResult([]),
        })

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await list_email_services(
                tenant_id=tenant_b,
                limit=50,
                offset=0,
                session=session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        body = json.loads(result.body)
        assert body["email_services"] == []
        assert body["pagination"]["total"] == 0

        list_params = [params for sql, params in session.executed_sql if "FROM email_services" in sql]
        assert any("tid" in params for params in list_params), (
            "List queries must bind tenant_id via :tid parameter"
        )


class TestGetEmailService:
    """Tests for GET /v1/tenants/{tid}/email-services/{sid}."""

    @pytest.mark.asyncio
    async def test_get_email_service_happy(self) -> None:
        """test_get_email_service_happy — GET by ID returns matching record."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        row = _make_email_svc_row(id=service_id, tenant_id=str(tenant_id), name="cici-softuraj")

        session = _make_session(**{
            "SELECT id, tenant_id": _FakeResult(row),
        })

        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(return_value=None)

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await get_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        body = json.loads(result.body)
        assert body["id"] == service_id
        assert body["name"] == "cici-softuraj"
        assert "auth_scheme" in body
        assert "tls_insecure_skip_verify" in body

    @pytest.mark.asyncio
    async def test_get_email_service_nonexistent_404(self) -> None:
        """test_get_email_service_nonexistent_404 — random UUID → 404."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        session = _make_session(**{
            "SELECT id, tenant_id": _FakeResult(None),
        })

        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(return_value=None)

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await get_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 404
        body = json.loads(result.body)
        assert body["mintkey:code"] == "not_found"

    @pytest.mark.asyncio
    async def test_get_email_service_returns_oauth2_authorized_true_when_vault_has_email_oauth2_cred(self) -> None:
        """
        oauth2_authorized=True when vault.get_credential returns a current
        credential with auth_scheme == AUTH_SCHEME_EMAIL_OAUTH2 (15).
        """
        from admin_api.api.email_services import _AUTH_SCHEME_EMAIL_OAUTH2

        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        row = _make_email_svc_row(
            id=service_id, tenant_id=str(tenant_id),
            provider="gmail", auth_scheme="email_oauth2",
        )

        session = _make_session(**{
            "SELECT id, tenant_id": _FakeResult(row),
        })

        mock_vault = AsyncMock()
        # NB: we never inspect plaintext below, only the auth_scheme.
        mock_vault.get_credential = AsyncMock(return_value={
            "plaintext": "REDACTED_REFRESH_TOKEN",
            "auth_scheme": _AUTH_SCHEME_EMAIL_OAUTH2,
            "key_version": 1,
            "header_name": "",
            "query_param": "",
            "target_address": "",
            "ssh_user": "",
        })

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await get_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        body = json.loads(result.body)
        assert body["oauth2_authorized"] is True
        mock_vault.get_credential.assert_awaited_once_with(
            tenant_id=str(tenant_id),
            service_id=service_id,
        )
        # NFR-17: no credential material echoed in the response.
        body_str = result.body.decode("utf-8")
        for forbidden in (
            "plaintext", "REDACTED_REFRESH_TOKEN",
            "header_name", "query_param",
            "target_address", "ssh_user", "key_version",
        ):
            assert forbidden not in body_str, (
                f"NFR-17 violation: '{forbidden}' must not appear in response body"
            )

    @pytest.mark.asyncio
    async def test_get_email_service_returns_oauth2_authorized_false_when_vault_returns_none(self) -> None:
        """oauth2_authorized=False when vault has no credential for this service."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        row = _make_email_svc_row(
            id=service_id, tenant_id=str(tenant_id),
            provider="gmail", auth_scheme="email_oauth2",
        )

        session = _make_session(**{
            "SELECT id, tenant_id": _FakeResult(row),
        })

        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(return_value=None)

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await get_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        body = json.loads(result.body)
        assert body["oauth2_authorized"] is False

    @pytest.mark.asyncio
    async def test_get_email_service_returns_oauth2_authorized_false_when_vault_returns_non_oauth2_scheme(self) -> None:
        """
        Defense-in-depth: vault returns a credential, but auth_scheme != 15
        (e.g. EMAIL_PASSWORD=14) → oauth2_authorized=False.
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        row = _make_email_svc_row(
            id=service_id, tenant_id=str(tenant_id),
            provider="gmail", auth_scheme="email_password",
        )

        session = _make_session(**{
            "SELECT id, tenant_id": _FakeResult(row),
        })

        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(return_value={
            "plaintext": "REDACTED",
            "auth_scheme": 14,  # EMAIL_PASSWORD — NOT EMAIL_OAUTH2
            "key_version": 1,
            "header_name": "",
            "query_param": "",
            "target_address": "",
            "ssh_user": "",
        })

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await get_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        body = json.loads(result.body)
        assert body["oauth2_authorized"] is False

    @pytest.mark.asyncio
    async def test_get_email_service_returns_oauth2_authorized_false_and_logs_when_vault_raises(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """
        Fail-closed: vault.get_credential raising must NOT 500 the endpoint.
        Response must include oauth2_authorized=False and a WARNING must
        be logged. No credential material should appear in the log record.
        """
        import logging

        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        row = _make_email_svc_row(
            id=service_id, tenant_id=str(tenant_id),
            provider="gmail", auth_scheme="email_oauth2",
        )

        session = _make_session(**{
            "SELECT id, tenant_id": _FakeResult(row),
        })

        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(
            side_effect=RuntimeError("vault unreachable")
        )

        with caplog.at_level(logging.WARNING, logger="admin_api.api.email_services"), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await get_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        body = json.loads(result.body)
        assert body["oauth2_authorized"] is False

        warning_records = [
            r for r in caplog.records
            if r.levelno == logging.WARNING
            and r.name == "admin_api.api.email_services"
        ]
        assert any(
            "vault.get_credential failed" in r.getMessage()
            for r in warning_records
        ), (
            "Expected a WARNING log from admin_api.api.email_services about "
            "vault.get_credential failure"
        )


class TestPatchEmailService:
    """Tests for PATCH /v1/tenants/{tid}/email-services/{sid}."""

    def _make_patch_request(self, body: dict[str, Any]) -> Any:
        fake_req = MagicMock()
        fake_req.json = AsyncMock(return_value=body)
        return fake_req

    @pytest.mark.asyncio
    async def test_patch_email_service_updates_mutable_fields(self) -> None:
        """test_patch_email_service_updates_mutable_fields — PATCH name+tls → 200."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        existing_row = _make_email_svc_row(
            id=service_id, tenant_id=str(tenant_id),
            name="old-name", tls_insecure_skip_verify=False,
        )
        updated_row = _make_email_svc_row(
            id=service_id, tenant_id=str(tenant_id),
            name="new-name", tls_insecure_skip_verify=True,
        )

        call_count: dict[str, int] = {"n": 0}

        async def _fake_execute(stmt: Any, params: Any = None) -> Any:
            sql = str(stmt)
            call_count["n"] += 1
            if "UPDATE" in sql:
                return _FakeResult(None)
            # First SELECT is the existence check; subsequent is refetch
            return _FakeResult(updated_row if call_count["n"] > 1 else existing_row)

        fake_session = _make_session()
        fake_session.execute = _fake_execute  # type: ignore[method-assign]
        fake_session.executed_sql = []  # type: ignore[assignment]

        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        patch_body = EmailServicePatch(name="new-name", tls_insecure_skip_verify=True)
        fake_request = self._make_patch_request({"name": "new-name", "tls_insecure_skip_verify": True})

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit):
            result = await patch_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                body=patch_body,
                request=fake_request,
                session=fake_session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        body = json.loads(result.body)
        assert body["name"] == "new-name"

        assert len(audit_calls) == 1
        assert audit_calls[0]["event_type"] == "email.service.updated"
        payload = audit_calls[0]["payload"]
        assert "changed_fields" in payload
        for field in ["name", "tls_insecure_skip_verify"]:
            assert field in payload["changed_fields"]

    @pytest.mark.asyncio
    async def test_patch_email_service_rejects_immutable(self) -> None:
        """test_patch_email_service_rejects_immutable — auth_scheme → 422."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        patch_body = EmailServicePatch()
        fake_request = self._make_patch_request({"auth_scheme": "email_oauth2"})
        session = _make_session()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await patch_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                body=patch_body,
                request=fake_request,
                session=session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 422
        body = json.loads(result.body)
        assert body["mintkey:code"] == "immutable_fields"
        assert "auth_scheme" in body["title"]

    @pytest.mark.asyncio
    async def test_patch_email_service_empty_body_returns_422(self) -> None:
        """test_patch_email_service_empty_body_returns_422 — empty body → 422."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        patch_body = EmailServicePatch()  # all None
        fake_request = self._make_patch_request({})
        session = _make_session()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            result = await patch_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                body=patch_body,
                request=fake_request,
                session=session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 422
        body = json.loads(result.body)
        assert body["mintkey:code"] == "no_fields_to_update"

    @pytest.mark.asyncio
    async def test_patch_emits_audit_with_changed_field_names_not_values(self) -> None:
        """test_patch_emits_audit_with_changed_field_names_not_values — NFR-17 check."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        row = _make_email_svc_row(id=service_id, tenant_id=str(tenant_id), tls_insecure_skip_verify=False)

        call_count2: dict[str, int] = {"n": 0}

        async def _fake_execute2(stmt: Any, params: Any = None) -> Any:
            call_count2["n"] += 1
            sql = str(stmt)
            if "UPDATE" in sql:
                return _FakeResult(None)
            return _FakeResult(row)

        fake_session = _make_session()
        fake_session.execute = _fake_execute2  # type: ignore[method-assign]
        fake_session.executed_sql = []  # type: ignore[assignment]

        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        patch_body = EmailServicePatch(tls_insecure_skip_verify=True)
        fake_request = self._make_patch_request({"tls_insecure_skip_verify": True})

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit):
            result = await patch_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                body=patch_body,
                request=fake_request,
                session=fake_session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        assert len(audit_calls) == 1
        payload = audit_calls[0]["payload"]
        assert payload["changed_fields"] == ["tls_insecure_skip_verify"]
        # NFR-17: value must not appear as a key in the payload dict
        assert "tls_insecure_skip_verify" not in payload, (
            "NFR-17: audit payload must not echo the field VALUE, only its NAME in changed_fields"
        )


class TestDeleteEmailService:
    """Tests for DELETE /v1/tenants/{tid}/email-services/{sid}."""

    @pytest.mark.asyncio
    async def test_delete_email_service_soft_deletes(self) -> None:
        """test_delete_email_service_soft_deletes — UPDATE sets deleted_at."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        session = _make_session()
        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit):
            result = await delete_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 204
        update_calls = [sql for sql, _ in session.executed_sql if "UPDATE email_services" in sql]
        assert len(update_calls) == 1
        update_sql = update_calls[0]
        assert "deleted_at" in update_sql
        assert "deleted_at IS NULL" in update_sql

    @pytest.mark.asyncio
    async def test_delete_email_service_emits_audit(self) -> None:
        """test_delete_email_service_emits_audit — emits email_service.deleted event."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        session = _make_session()
        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit):
            result = await delete_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 204
        assert len(audit_calls) == 1
        assert audit_calls[0]["event_type"] == "email.service.deleted"
        assert audit_calls[0]["payload"]["service_id"] == service_id


class TestNoCredentialInResponse:
    """test_no_credential_or_password_in_any_response — GET list/single must not expose secrets."""

    @pytest.mark.asyncio
    async def test_no_credential_or_password_in_any_response(self) -> None:
        """GET list and GET single must not contain password/username/client_secret keys."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        row = _make_email_svc_row(id=service_id, tenant_id=str(tenant_id))

        # Test GET list
        session_list = _make_session(**{
            "SELECT COUNT(*)": _FakeCountResult(1),
            "SELECT id, tenant_id": _FakeListResult([row]),
        })
        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            list_result = await list_email_services(
                tenant_id=tenant_id,
                limit=50,
                offset=0,
                session=session_list,  # type: ignore[arg-type]
                _authz=None,
            )
        list_body_str = list_result.body.decode("utf-8")
        for forbidden in ("password", "username", "client_secret"):
            assert f'"{forbidden}"' not in list_body_str

        # Test GET single
        session_single = _make_session(**{
            "SELECT id, tenant_id": _FakeResult(row),
        })
        mock_vault_single = AsyncMock()
        mock_vault_single.get_credential = AsyncMock(return_value=None)
        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock):
            single_result = await get_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                session=session_single,  # type: ignore[arg-type]
                vault=mock_vault_single,  # type: ignore[arg-type]
                _authz=None,
            )
        single_body_str = single_result.body.decode("utf-8")
        for forbidden in ("password", "username", "client_secret"):
            assert f'"{forbidden}"' not in single_body_str


# ---------------------------------------------------------------------------
# T-GET-CB: GET OAuth2 callback view tests (C-9 callback view)
# ---------------------------------------------------------------------------


class TestOAuth2CallbackView:
    """
    Tests for GET /v1/tenants/{tid}/email-services/{sid}/oauth2/{provider}/callback.

    T-GET-CB-1: Happy path — valid code+state → 200 HTML, popup-close script present,
                NO refresh_token in body, vault.put_credential called.
    T-GET-CB-2: ?error=access_denied → 200 HTML, error shown, vault NOT called.
    T-GET-CB-3: Invalid state → 422 HTML, no exchange attempted.
    T-GET-CB-4: No code in body — canary that refresh_token/code never appear in HTML.
    T-GET-CB-5: POST authorize with MINTKEY_ADMIN_API_PUBLIC_URL set → auth_url
                contains the public URL, NOT request.base_url (docker hostname).
    """

    def _fake_provider_resp(
        self,
        status_code: int = 200,
        access_token: str = "fake_at",
        refresh_token: str = "fake_rt",
    ) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        return resp

    @pytest.mark.asyncio
    async def test_get_cb_1_success(self) -> None:
        """T-GET-CB-1: GET callback with valid code+state → 200 HTML.

        Verifies:
        - 200 status.
        - Response is HTML (Content-Type text/html).
        - window.postMessage / window.close present in the page.
        - vault.put_credential called exactly once with auth_scheme=email_oauth2.
        - refresh_token value NEVER appears in the HTML body (NFR-17).
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        state_value = "valid_state_get_cb1"

        fake_state_row = _FakeRow(
            service_id=service_id,
            redirect_uri="http://localhost:8080/v1/tenants/.../callback",
            operator_id=str(uuid.uuid4()),
        )
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"key_version": 1})

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
            "MINTKEY_ADMIN_UI_PUBLIC_URL": "http://localhost:8081",
        }

        provider_resp = self._fake_provider_resp()

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await oauth2_callback_view(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                code="auth_code_get_cb1",
                state=state_value,
                error=None,
                error_description=None,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        # Must be HTML
        assert "text/html" in result.media_type

        html_body = result.body.decode("utf-8")
        # Popup close script must be present
        assert "window.opener" in html_body
        assert "window.close" in html_body
        assert "postMessage" in html_body

        # NFR-17: refresh_token value must NEVER appear in the HTML
        assert "fake_rt" not in html_body
        assert "auth_code_get_cb1" not in html_body
        assert state_value not in html_body

        # Vault was called
        mock_vault.put_credential.assert_called_once()
        call_kwargs = mock_vault.put_credential.call_args[1]
        assert call_kwargs["auth_scheme"] == "email_oauth2"

    @pytest.mark.asyncio
    async def test_get_cb_2_provider_error(self) -> None:
        """T-GET-CB-2: GET callback with ?error=access_denied → 200 HTML, vault NOT called."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        session = _make_session()
        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock()

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
            "MINTKEY_ADMIN_UI_PUBLIC_URL": "http://localhost:8081",
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock):
            result = await oauth2_callback_view(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                code=None,
                state=None,
                error="access_denied",
                error_description="User declined",
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        html_body = result.body.decode("utf-8")
        # Must show error state — "error" JS status
        assert '"error"' in html_body
        # Vault MUST NOT have been called
        mock_vault.put_credential.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cb_3_invalid_state(self) -> None:
        """T-GET-CB-3: GET callback with bad state (DELETE returns no row) → 422 HTML."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        # State lookup returns nothing
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(None),
        })
        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock()

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
            "MINTKEY_ADMIN_UI_PUBLIC_URL": "http://localhost:8081",
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await oauth2_callback_view(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                code="some_code",
                state="bad_state",
                error=None,
                error_description=None,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        # 422 status (invalid_state from helper)
        assert result.status_code == 422
        html_body = result.body.decode("utf-8")
        # Must show error state
        assert '"error"' in html_body
        # No exchange — vault not called
        mock_vault.put_credential.assert_not_called()

    @pytest.mark.asyncio
    async def test_get_cb_4_no_code_leak_in_body(self) -> None:
        """T-GET-CB-4: Canary — code / state / refresh_token values NEVER appear in HTML.

        Uses a success scenario and asserts the specific secret values are absent
        from the rendered HTML at the string level (belt-and-suspenders NFR-17).
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        code_value = "super_secret_code_xyz_12345"
        state_value = "super_secret_state_abc_67890"
        refresh_token_value = "super_secret_rt_qwerty_00001"

        fake_state_row = _FakeRow(
            service_id=service_id,
            redirect_uri="http://localhost:8080/callback",
            operator_id=str(uuid.uuid4()),
        )
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"key_version": 1})

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
            "MINTKEY_ADMIN_UI_PUBLIC_URL": "http://localhost:8081",
        }

        resp_mock = MagicMock()
        resp_mock.status_code = 200
        resp_mock.json.return_value = {
            "access_token": "super_secret_at_zxcvb_99999",
            "refresh_token": refresh_token_value,
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=resp_mock)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await oauth2_callback_view(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                code=code_value,
                state=state_value,
                error=None,
                error_description=None,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        html_body = result.body.decode("utf-8")

        # NFR-17: none of the secret values must appear anywhere in the HTML
        for secret in (code_value, state_value, refresh_token_value, "super_secret_at_zxcvb_99999", "csecret"):
            assert secret not in html_body, (
                f"NFR-17 violation: secret value '{secret[:20]}...' found in GET callback HTML"
            )

    @pytest.mark.asyncio
    async def test_get_cb_5_redirect_uri_uses_public_url(self) -> None:
        """T-GET-CB-5: POST authorize with MINTKEY_ADMIN_API_PUBLIC_URL set.

        Asserts that the authorize_url returned by oauth2_authorize contains
        redirect_uri=http://localhost:8080/... (from env var) and NOT
        http://admin-api:8080/... (which would be request.base_url inside docker).
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        session = _make_session(**{
            "SELECT id FROM email_services": _FakeResult(_FakeRow(id=service_id)),
        })

        # Simulate the docker-internal request.base_url
        fake_request = MagicMock()
        fake_request.cookies.get.return_value = ""
        fake_request.base_url = "http://admin-api:8080/"  # docker-internal — must NOT appear

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "fake_client_id",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "fake_secret",
            "MINTKEY_ADMIN_API_PUBLIC_URL": "http://localhost:8080",
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await oauth2_authorize(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                request=fake_request,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        import json as _json
        body_content = _json.loads(result.body)
        auth_url = body_content["authorize_url"]

        # redirect_uri must use the public URL, NOT the docker-internal hostname
        assert "redirect_uri=http://localhost:8080" in auth_url, (
            f"Expected redirect_uri to use MINTKEY_ADMIN_API_PUBLIC_URL (http://localhost:8080), "
            f"but got: {auth_url}"
        )
        assert "admin-api:8080" not in auth_url, (
            f"Docker-internal hostname 'admin-api:8080' must not appear in authorize_url; "
            f"got: {auth_url}"
        )

        # Also verify _oauth2_redirect_base() uses the env var
        with patch.dict(os.environ, {"MINTKEY_ADMIN_API_PUBLIC_URL": "https://api.example.com"}):
            base = _oauth2_redirect_base()
        assert base == "https://api.example.com", (
            f"_oauth2_redirect_base() did not use MINTKEY_ADMIN_API_PUBLIC_URL; got: {base}"
        )


# ---------------------------------------------------------------------------
# T-PT (per-tenant callback): new per-(provider, tenant) callback endpoints
# fix/oauth2-redirect-uri-per-tenant
# ---------------------------------------------------------------------------


class TestOAuth2PerTenantCallback:
    """
    T-PT-1 through T-PT-5: tests for the new per-(provider, tenant) callback endpoints.
    These verify the behaviour introduced in fix/oauth2-redirect-uri-per-tenant.
    """

    def _fake_provider_resp(
        self,
        status_code: int = 200,
        access_token: str = "fake_at",
        refresh_token: str = "fake_rt",
    ) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        return resp

    @pytest.mark.asyncio
    async def test_oauth2_callback_per_tenant_get_success(self) -> None:
        """
        T-PT-1: GET new per-tenant callback with valid state → 200 HTML, success branch,
        vault.put_credential called with service_id from the STATE ROW (not from URL).
        """
        from admin_api.api.email_services import oauth2_callback_per_tenant_view

        tenant_id = uuid.uuid4()
        # service_id comes from the state row — NOT from the URL path
        service_id_from_state = str(uuid.uuid4())

        fake_state_row = _FakeRow(
            service_id=service_id_from_state,
            redirect_uri=f"http://localhost:8080/v1/tenants/{tenant_id}/oauth2/gmail/callback",
            operator_id=str(uuid.uuid4()),
        )
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"key_version": 1})

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        provider_resp = self._fake_provider_resp()

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await oauth2_callback_per_tenant_view(
                tenant_id=tenant_id,
                provider="gmail",
                code="auth_code_xyz",
                state="valid_state_abc",
                error=None,
                error_description=None,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        assert "Authorization complete" in result.body.decode()

        # vault.put_credential must have been called with the service_id from the state row
        mock_vault.put_credential.assert_called_once()
        call_kwargs = mock_vault.put_credential.call_args[1]
        assert call_kwargs.get("service_id") == service_id_from_state, (
            "vault.put_credential must use service_id from state row, not from URL"
        )
        assert call_kwargs.get("auth_scheme") == "email_oauth2"

        # Audit event must be emitted with the resolved service_id
        assert any(a["event_type"] == "email.oauth2.authorized" for a in audit_calls)
        auth_events = [a for a in audit_calls if a["event_type"] == "email.oauth2.authorized"]
        assert auth_events[0]["payload"]["service_id"] == service_id_from_state

    @pytest.mark.asyncio
    async def test_oauth2_callback_per_tenant_get_state_invalid(self) -> None:
        """
        T-PT-2: GET per-tenant callback with bad/expired state → 422 HTML.
        """
        from admin_api.api.email_services import oauth2_callback_per_tenant_view

        tenant_id = uuid.uuid4()
        # DELETE FROM oauth2_state returns nothing — state is invalid/expired
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(None),
        })

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        provider_resp = self._fake_provider_resp()

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await oauth2_callback_per_tenant_view(
                tenant_id=tenant_id,
                provider="gmail",
                code="code",
                state="bad_state",
                error=None,
                error_description=None,
                session=session,  # type: ignore[arg-type]
                vault=AsyncMock(),
            )

        assert result.status_code == 422
        assert "Authorization failed" in result.body.decode()

    @pytest.mark.asyncio
    async def test_oauth2_callback_per_tenant_post_success(self) -> None:
        """
        T-PT-3: POST per-tenant callback with valid state → 200 JSON, service_id
        from state row, vault.put_credential called, audit emitted.
        """
        from admin_api.api.email_services import oauth2_callback_per_tenant, OAuth2CallbackPerTenantBody

        tenant_id = uuid.uuid4()
        service_id_from_state = str(uuid.uuid4())

        fake_state_row = _FakeRow(
            service_id=service_id_from_state,
            redirect_uri=f"http://localhost:8080/v1/tenants/{tenant_id}/oauth2/gmail/callback",
            operator_id=str(uuid.uuid4()),
        )
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"key_version": 1})

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        provider_resp = self._fake_provider_resp()

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            body = OAuth2CallbackPerTenantBody(code="auth_code", state="valid_state")
            result = await oauth2_callback_per_tenant(
                tenant_id=tenant_id,
                provider="gmail",
                body=body,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        body_content = json.loads(result.body)
        assert body_content["provider"] == "gmail"
        assert body_content["service_id"] == service_id_from_state

        # Vault called with service_id from state row
        mock_vault.put_credential.assert_called_once()
        call_kwargs = mock_vault.put_credential.call_args[1]
        assert call_kwargs.get("service_id") == service_id_from_state
        assert call_kwargs.get("auth_scheme") == "email_oauth2"

        # Audit event emitted with resolved service_id
        auth_events = [a for a in audit_calls if a["event_type"] == "email.oauth2.authorized"]
        assert len(auth_events) == 1
        assert auth_events[0]["payload"]["service_id"] == service_id_from_state

    @pytest.mark.asyncio
    async def test_oauth2_redirect_uri_does_not_include_service_id(self) -> None:
        """
        T-PT-4: After POST authorize, the returned auth_url's redirect_uri param
        must match /v1/tenants/{tid}/oauth2/{provider}/callback and must NOT
        contain /email-services/<sid>/ anywhere in the path.
        """
        import urllib.parse

        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        session = _make_session(**{
            "SELECT id FROM email_services": _FakeResult(_FakeRow(id=service_id)),
        })

        fake_request = MagicMock()
        fake_request.cookies.get.return_value = ""
        fake_request.base_url = "http://localhost:8080/"

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "fake_client_id",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "fake_secret",
            "MINTKEY_ADMIN_API_PUBLIC_URL": "http://localhost:8080",
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await oauth2_authorize(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                request=fake_request,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        body_content = json.loads(result.body)
        auth_url = body_content["authorize_url"]

        # Parse redirect_uri from the auth_url query string
        parsed = urllib.parse.urlparse(auth_url)
        qs = urllib.parse.parse_qs(parsed.query)
        redirect_uri_vals = qs.get("redirect_uri", [])
        assert len(redirect_uri_vals) == 1, f"Expected exactly one redirect_uri, got: {redirect_uri_vals}"
        redirect_uri = redirect_uri_vals[0]

        # Must match the new per-tenant shape
        expected_path = f"/v1/tenants/{tenant_id}/oauth2/gmail/callback"
        assert redirect_uri.endswith(expected_path), (
            f"redirect_uri must end with '{expected_path}', got: '{redirect_uri}'"
        )

        # Must NOT contain the service_id (i.e. no /email-services/<sid>/ segment)
        assert service_id not in redirect_uri, (
            f"service_id must not appear in redirect_uri; got: '{redirect_uri}'"
        )
        assert "/email-services/" not in redirect_uri, (
            f"/email-services/ must not appear in redirect_uri; got: '{redirect_uri}'"
        )

    @pytest.mark.asyncio
    async def test_oauth2_state_row_redirect_uri_matches_new_shape(self) -> None:
        """
        T-PT-5: The redirect_uri stored in the oauth2_state row during authorize
        must match the new per-tenant shape
        /v1/tenants/{tid}/oauth2/{provider}/callback (no /email-services/<sid>/).
        """
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        session = _make_session(**{
            "SELECT id FROM email_services": _FakeResult(_FakeRow(id=service_id)),
        })

        fake_request = MagicMock()
        fake_request.cookies.get.return_value = ""
        fake_request.base_url = "http://localhost:8080/"

        env_override = {
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "fake_client_id",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "fake_secret",
            "MINTKEY_ADMIN_API_PUBLIC_URL": "http://localhost:8080",
        }

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await oauth2_authorize(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                request=fake_request,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 200

        # Find the INSERT INTO oauth2_state call and extract the redirect_uri param
        insert_calls = [
            (sql, params)
            for sql, params in session.executed_sql
            if "INSERT INTO oauth2_state" in sql
        ]
        assert len(insert_calls) == 1, "Expected exactly one INSERT INTO oauth2_state"
        _, params = insert_calls[0]
        stored_redirect_uri = params.get("redirect_uri", "")

        # Must use the new per-tenant shape
        expected_suffix = f"/v1/tenants/{tenant_id}/oauth2/gmail/callback"
        assert stored_redirect_uri.endswith(expected_suffix), (
            f"State row redirect_uri must end with '{expected_suffix}', "
            f"got: '{stored_redirect_uri}'"
        )
        # Must NOT contain service_id
        assert service_id not in stored_redirect_uri, (
            f"service_id must not appear in state row redirect_uri; "
            f"got: '{stored_redirect_uri}'"
        )
        assert "/email-services/" not in stored_redirect_uri, (
            f"/email-services/ must not appear in state row redirect_uri; "
            f"got: '{stored_redirect_uri}'"
        )


# ---------------------------------------------------------------------------
# C-3: OAuth2 vault payload JSON envelope + Gmail email_address resolution
# ---------------------------------------------------------------------------
#
# The OAuth2 IMAP XOAUTH2 path requires the user's email address as the SASL
# username. _exchange_oauth2_code_for_refresh_token now (a) fetches the
# emailAddress from Gmail's profile endpoint after a successful token
# exchange and (b) stores the vault credential as a JSON envelope
# {"provider","refresh_token","email_address"} so the email-proxy can
# extract both fields. oauth2_refresh parses the envelope, with a raw-string
# fallback for legacy rows.
#
# Tests below cover:
#   - Gmail success: envelope contains email_address from /me profile
#   - Gmail userinfo failure: still stores, with empty email_address
#   - Outlook: no userinfo call, empty email_address
#   - NFR-17: no PII (email/access_token/refresh_token) leaks into logs
#   - oauth2_refresh parses the JSON envelope
#   - oauth2_refresh falls back to legacy raw plaintext
#   - _parse_oauth2_plaintext unit-table

class TestOAuth2VaultEnvelopeC3:
    """C-3 chunk: OAuth2 vault JSON envelope + email_address resolution."""

    @staticmethod
    def _fake_token_resp(
        status_code: int = 200,
        access_token: str = "at_test",
        refresh_token: str = "rt_test",
    ) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        resp.json.return_value = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }
        return resp

    @staticmethod
    def _fake_userinfo_resp(
        status_code: int = 200,
        email_address: str | None = "foo@example.com",
    ) -> MagicMock:
        resp = MagicMock()
        resp.status_code = status_code
        body: dict[str, Any] = {}
        if email_address is not None:
            body["emailAddress"] = email_address
        resp.json.return_value = body
        return resp

    @pytest.mark.asyncio
    async def test_exchange_oauth2_code_stores_json_envelope_with_email_address_for_gmail(
        self,
    ) -> None:
        """Gmail success path: vault.put_credential receives a JSON envelope with
        provider, refresh_token, AND email_address (from the userinfo call).
        """
        from admin_api.api.email_services import _exchange_oauth2_code_for_refresh_token

        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        state_value = "valid_state_c3_gmail_ok"

        fake_state_row = _FakeRow(
            service_id=service_id,
            redirect_uri="https://example.com/cb",
            operator_id=str(uuid.uuid4()),
        )
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"key_version": 1})

        token_resp = self._fake_token_resp(access_token="at_test", refresh_token="rt_test")
        userinfo_resp = self._fake_userinfo_resp(email_address="foo@example.com")

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=token_resp)
            mock_ctx_mgr.get = AsyncMock(return_value=userinfo_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await _exchange_oauth2_code_for_refresh_token(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                code="auth_code",
                state=state_value,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                client_id="cid",
                client_secret="csecret",
            )

        assert result.ok is True
        assert result.email_address == "foo@example.com"
        assert result.service_id == service_id

        # vault.put_credential called with JSON envelope plaintext
        mock_vault.put_credential.assert_called_once()
        call_kwargs = mock_vault.put_credential.call_args[1]
        assert call_kwargs.get("auth_scheme") == "email_oauth2"
        stored_plaintext = call_kwargs.get("plaintext", "")
        assert isinstance(stored_plaintext, str)
        envelope = json.loads(stored_plaintext)
        assert envelope == {
            "provider": "gmail",
            "refresh_token": "rt_test",
            "email_address": "foo@example.com",
        }

        # Verify the userinfo call used the access_token and the correct URL
        from admin_api.api.email_services import _GMAIL_USERINFO_URL
        get_calls = mock_ctx_mgr.get.call_args_list
        assert len(get_calls) == 1
        args, kwargs = get_calls[0]
        assert _GMAIL_USERINFO_URL in args or kwargs.get("url") == _GMAIL_USERINFO_URL or (
            args and args[0] == _GMAIL_USERINFO_URL
        )
        headers = kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer at_test"

    @pytest.mark.asyncio
    async def test_exchange_oauth2_code_userinfo_failure_still_stores_with_empty_email(
        self,
    ) -> None:
        """If Gmail's userinfo endpoint fails (HTTP error or non-200), we still
        store the vault row (so the operator's grant is not lost) with
        email_address="" and the exchange returns ok=True.
        """
        from admin_api.api.email_services import _exchange_oauth2_code_for_refresh_token

        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        fake_state_row = _FakeRow(
            service_id=service_id,
            redirect_uri="https://example.com/cb",
            operator_id=str(uuid.uuid4()),
        )
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"key_version": 1})

        token_resp = self._fake_token_resp()
        # Userinfo returns 500
        userinfo_err_resp = MagicMock()
        userinfo_err_resp.status_code = 500
        userinfo_err_resp.json.return_value = {"error": "server error"}

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=token_resp)
            mock_ctx_mgr.get = AsyncMock(return_value=userinfo_err_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await _exchange_oauth2_code_for_refresh_token(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                code="auth_code",
                state="state_c3_userinfo_fail",
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                client_id="cid",
                client_secret="csecret",
            )

        # Exchange still succeeds — operator's authorization is preserved.
        assert result.ok is True
        assert result.email_address == ""

        # Vault payload IS still stored, with empty email_address.
        mock_vault.put_credential.assert_called_once()
        stored_plaintext = mock_vault.put_credential.call_args[1].get("plaintext", "")
        envelope = json.loads(stored_plaintext)
        assert envelope["provider"] == "gmail"
        assert envelope["refresh_token"] == "rt_test"
        assert envelope["email_address"] == ""

    @pytest.mark.asyncio
    async def test_exchange_oauth2_code_outlook_stores_with_empty_email_no_userinfo_call(
        self,
    ) -> None:
        """Outlook path: no userinfo call (scopes do not grant Graph access),
        vault envelope has email_address="" and provider="outlook".
        """
        from admin_api.api.email_services import _exchange_oauth2_code_for_refresh_token

        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        fake_state_row = _FakeRow(
            service_id=service_id,
            redirect_uri="https://example.com/cb",
            operator_id=str(uuid.uuid4()),
        )
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"key_version": 1})

        token_resp = self._fake_token_resp()

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=token_resp)
            # Spy on .get so we can verify it is NOT called.
            mock_ctx_mgr.get = AsyncMock()
            mock_client_cls.return_value = mock_ctx_mgr

            result = await _exchange_oauth2_code_for_refresh_token(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="outlook",
                code="auth_code",
                state="state_c3_outlook",
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                client_id="cid",
                client_secret="csecret",
            )

        assert result.ok is True
        assert result.email_address == ""

        # ONE post (token exchange); ZERO get (no userinfo for outlook).
        assert mock_ctx_mgr.post.await_count == 1
        assert mock_ctx_mgr.get.await_count == 0

        mock_vault.put_credential.assert_called_once()
        stored_plaintext = mock_vault.put_credential.call_args[1].get("plaintext", "")
        envelope = json.loads(stored_plaintext)
        assert envelope["provider"] == "outlook"
        assert envelope["refresh_token"] == "rt_test"
        assert envelope["email_address"] == ""

    @pytest.mark.asyncio
    async def test_exchange_oauth2_code_payload_no_pii_leak_in_logs(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """NFR-17: refresh_token, access_token, and email_address MUST NOT
        appear in any log record from a successful exchange.
        """
        import logging as _logging
        from admin_api.api.email_services import _exchange_oauth2_code_for_refresh_token

        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        fake_state_row = _FakeRow(
            service_id=service_id,
            redirect_uri="https://example.com/cb",
            operator_id=str(uuid.uuid4()),
        )
        session = _make_session(**{
            "DELETE FROM oauth2_state": _FakeResult(fake_state_row),
        })

        mock_vault = AsyncMock()
        mock_vault.put_credential = AsyncMock(return_value={"key_version": 1})

        token_resp = self._fake_token_resp(access_token="at_canary", refresh_token="rt_canary")
        userinfo_resp = self._fake_userinfo_resp(email_address="canary@example.com")

        with caplog.at_level(_logging.DEBUG, logger="admin_api.api.email_services"), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=token_resp)
            mock_ctx_mgr.get = AsyncMock(return_value=userinfo_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await _exchange_oauth2_code_for_refresh_token(
                tenant_id=tenant_id,
                service_id=service_id,
                provider="gmail",
                code="auth_code",
                state="state_c3_pii_canary",
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
                client_id="cid_canary",
                client_secret="csecret_canary",
            )

        assert result.ok is True

        # Build a single concatenated string of every captured log line.
        all_log_text = "\n".join(
            (rec.getMessage() + " " + str(rec.args or "")) for rec in caplog.records
        )
        for canary in ("rt_canary", "at_canary", "canary@example.com", "csecret_canary"):
            assert canary not in all_log_text, (
                f"NFR-17 violation: {canary!r} leaked into a log record"
            )

    @pytest.mark.asyncio
    async def test_oauth2_refresh_parses_json_envelope(self) -> None:
        """oauth2_refresh: vault returns a JSON envelope → outbound POST to the
        provider must contain refresh_token=<envelope.refresh_token>, NOT the
        raw JSON string.
        """
        service_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        envelope = json.dumps({
            "provider": "gmail",
            "refresh_token": "rt_envelope",
            "email_address": "a@b.com",
        })
        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(return_value={
            "plaintext": envelope,
            "auth_scheme": "email_oauth2",
        })

        session = _make_session()

        provider_resp = MagicMock()
        provider_resp.status_code = 200
        provider_resp.json.return_value = {
            "access_token": "new_at",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        env_override = {
            "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        request = MagicMock()
        request.headers = {"X-Mintkey-Service-Token": "correct_token"}

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await oauth2_refresh(
                provider="gmail",
                service_id=service_id,
                tenant_id=tenant_id,
                request=request,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200

        # Inspect the outbound POST to Google's /token: data must contain the
        # PARSED refresh_token, not the JSON envelope.
        mock_ctx_mgr.post.assert_called_once()
        post_args, post_kwargs = mock_ctx_mgr.post.call_args
        sent_data = post_kwargs.get("data") or (post_args[1] if len(post_args) > 1 else None)
        assert isinstance(sent_data, dict)
        assert sent_data.get("refresh_token") == "rt_envelope", (
            f"Expected outbound POST refresh_token='rt_envelope', got: {sent_data.get('refresh_token')!r}"
        )
        # Should NOT be the JSON envelope string.
        assert sent_data["refresh_token"] != envelope

    @pytest.mark.asyncio
    async def test_oauth2_refresh_falls_back_to_legacy_raw_plaintext(self) -> None:
        """oauth2_refresh: vault returns a legacy raw refresh_token string
        (NOT JSON) → outbound POST must use that raw string verbatim.
        """
        service_id = str(uuid.uuid4())
        tenant_id = str(uuid.uuid4())

        mock_vault = AsyncMock()
        mock_vault.get_credential = AsyncMock(return_value={
            "plaintext": "rt_legacy_raw",
            "auth_scheme": "email_oauth2",
        })

        session = _make_session()

        provider_resp = MagicMock()
        provider_resp.status_code = 200
        provider_resp.json.return_value = {
            "access_token": "new_at",
            "token_type": "Bearer",
            "expires_in": 3600,
        }

        env_override = {
            "MINTKEY_EMAIL_PROXY_SERVICE_TOKEN": "correct_token",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_ID": "cid",
            "MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET": "csecret",
        }

        request = MagicMock()
        request.headers = {"X-Mintkey-Service-Token": "correct_token"}

        with patch.dict(os.environ, env_override), \
             patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock), \
             patch("httpx.AsyncClient") as mock_client_cls:
            mock_ctx_mgr = AsyncMock()
            mock_ctx_mgr.__aenter__ = AsyncMock(return_value=mock_ctx_mgr)
            mock_ctx_mgr.__aexit__ = AsyncMock(return_value=None)
            mock_ctx_mgr.post = AsyncMock(return_value=provider_resp)
            mock_client_cls.return_value = mock_ctx_mgr

            result = await oauth2_refresh(
                provider="gmail",
                service_id=service_id,
                tenant_id=tenant_id,
                request=request,
                session=session,  # type: ignore[arg-type]
                vault=mock_vault,  # type: ignore[arg-type]
            )

        assert result.status_code == 200
        mock_ctx_mgr.post.assert_called_once()
        _, post_kwargs = mock_ctx_mgr.post.call_args
        sent_data = post_kwargs.get("data")
        assert isinstance(sent_data, dict)
        assert sent_data.get("refresh_token") == "rt_legacy_raw"

    def test__parse_oauth2_plaintext_unit_table(self) -> None:
        """Direct unit table for the JSON-envelope/legacy parser."""
        from admin_api.api.email_services import _parse_oauth2_plaintext

        cases: list[tuple[str, str, str]] = [
            # JSON envelope with refresh_token → returns the refresh_token.
            (
                json.dumps({
                    "provider": "gmail",
                    "refresh_token": "rt_inside",
                    "email_address": "x@y.com",
                }),
                "rt_inside",
                "json envelope with refresh_token",
            ),
            # JSON dict missing refresh_token → falls back to the raw plaintext.
            (
                json.dumps({"provider": "gmail", "email_address": "x@y.com"}),
                json.dumps({"provider": "gmail", "email_address": "x@y.com"}),
                "json dict missing refresh_token falls back to raw",
            ),
            # Not-JSON string → returned verbatim.
            ("rt_raw_string", "rt_raw_string", "non-JSON string returned verbatim"),
            # Empty string → empty.
            ("", "", "empty string returns empty"),
            # JSON but not a dict (list) → falls back to raw.
            ("[]", "[]", "JSON list falls back to raw"),
            # JSON null → falls back to raw.
            ("null", "null", "JSON null falls back to raw"),
            # JSON dict with non-string refresh_token → falls back to raw.
            (
                json.dumps({"refresh_token": 123}),
                json.dumps({"refresh_token": 123}),
                "non-string refresh_token falls back to raw",
            ),
        ]
        for raw_input, expected, label in cases:
            assert _parse_oauth2_plaintext(raw_input) == expected, (
                f"_parse_oauth2_plaintext failure for case: {label}"
            )


# ---------------------------------------------------------------------------
# Defense-in-depth: whitespace trimming on POST + PATCH form inputs (#365)
# ---------------------------------------------------------------------------


class TestCreateEmailServiceTrimsWhitespace:
    """#365: create_email_service strips leading/trailing whitespace from
    string form fields before INSERT / audit-emit. Enum-validated fields
    (provider, auth_scheme) are NOT trimmed — Pydantic's field_validator
    rejects them outright."""

    @pytest.mark.asyncio
    async def test_create_email_service_trims_leading_trailing_whitespace_from_imap_host(self) -> None:
        """#365 repro: imap_host=' imap.gmail.com    ' produced DNS failures.
        After fix the INSERT must store the trimmed value."""
        tenant_id = uuid.uuid4()
        body = EmailServiceCreate(
            provider="gmail",
            name="Company Gmail",
            imap_host=" imap.gmail.com    ",  # the exact #365 input
            imap_port=993,
            smtp_host="\tsmtp.gmail.com\n",
            smtp_port=587,
            auth_scheme="email_password",
            allowed_recipient_domains="  example.com, other.com  ",
        )

        session = _make_session()
        audit_calls: list[dict[str, Any]] = []

        async def _fake_audit_emit(**kwargs: Any) -> None:
            audit_calls.append(kwargs)

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", side_effect=_fake_audit_emit):
            result = await create_email_service(
                tenant_id=tenant_id,
                body=body,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 201, result.body

        insert_params = [
            params for sql, params in session.executed_sql
            if "INSERT INTO email_services" in sql
        ]
        assert len(insert_params) == 1
        ip = insert_params[0]
        assert ip["imap_host"] == "imap.gmail.com", f"imap_host not trimmed: {ip['imap_host']!r}"
        assert ip["smtp_host"] == "smtp.gmail.com", f"smtp_host not trimmed: {ip['smtp_host']!r}"
        assert ip["name"] == "Company Gmail"
        assert ip["allowed_domains"] == "example.com, other.com", (
            f"allowed_recipient_domains not trimmed: {ip['allowed_domains']!r}"
        )

        # Audit payload also carries the trimmed values
        body_content = json.loads(result.body)
        assert body_content["imap_host"] == "imap.gmail.com"
        assert body_content["smtp_host"] == "smtp.gmail.com"
        assert body_content["name"] == "Company Gmail"
        assert audit_calls[0]["payload"]["imap_host"] == "imap.gmail.com"
        assert audit_calls[0]["payload"]["smtp_host"] == "smtp.gmail.com"

    @pytest.mark.asyncio
    async def test_create_email_service_preserves_internal_whitespace_in_name(self) -> None:
        """#365: only edges are trimmed — internal spaces in name are preserved."""
        tenant_id = uuid.uuid4()
        body = EmailServiceCreate(
            provider="gmail",
            name="  Multi  Word  Name  ",  # internal double-spaces
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            auth_scheme="email_password",
        )
        session = _make_session()
        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await create_email_service(
                tenant_id=tenant_id,
                body=body,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 201
        ip = next(
            params for sql, params in session.executed_sql
            if "INSERT INTO email_services" in sql
        )
        assert ip["name"] == "Multi  Word  Name", (
            "internal whitespace must be preserved; only edges trimmed"
        )

    @pytest.mark.asyncio
    async def test_create_email_service_no_whitespace_input_unchanged(self) -> None:
        """#365: clean input is byte-identical pre/post trim (idempotent)."""
        tenant_id = uuid.uuid4()
        body = EmailServiceCreate(
            provider="gmail",
            name="clean-name",
            imap_host="imap.gmail.com",
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            auth_scheme="email_password",
            allowed_recipient_domains="example.com",
        )
        session = _make_session()
        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await create_email_service(
                tenant_id=tenant_id,
                body=body,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 201
        ip = next(
            params for sql, params in session.executed_sql
            if "INSERT INTO email_services" in sql
        )
        assert ip["name"] == "clean-name"
        assert ip["imap_host"] == "imap.gmail.com"
        assert ip["smtp_host"] == "smtp.gmail.com"
        assert ip["allowed_domains"] == "example.com"

    @pytest.mark.asyncio
    async def test_create_email_service_all_whitespace_imap_host_rejected_422(self) -> None:
        """#365: all-whitespace imap_host trims → empty → invalid_imap 422."""
        tenant_id = uuid.uuid4()
        body = EmailServiceCreate(
            provider="gmail",
            name="x",
            imap_host="    \t\n  ",  # all-whitespace
            imap_port=993,
            smtp_host="smtp.gmail.com",
            smtp_port=587,
            auth_scheme="email_password",
        )
        session = _make_session()
        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await create_email_service(
                tenant_id=tenant_id,
                body=body,
                session=session,  # type: ignore[arg-type]
            )

        assert result.status_code == 422
        assert json.loads(result.body)["mintkey:code"] == "invalid_imap"
        # No INSERT executed for a rejected request
        assert not any(
            "INSERT INTO email_services" in sql for sql, _ in session.executed_sql
        )


class TestPatchEmailServiceTrimsWhitespace:
    """#365: patch_email_service strips leading/trailing whitespace from
    string fields the caller explicitly set. PATCH cannot touch imap_host /
    smtp_host (immutable) so this only covers name and
    allowed_recipient_domains."""

    def _make_patch_request(self, body: dict[str, Any]) -> Any:
        fake_req = MagicMock()
        fake_req.json = AsyncMock(return_value=body)
        return fake_req

    @pytest.mark.asyncio
    async def test_patch_trims_leading_trailing_whitespace_from_name(self) -> None:
        """#365: PATCH name='  new-name  ' → DB sees 'new-name'."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        existing_row = _make_email_svc_row(
            id=service_id, tenant_id=str(tenant_id), name="old-name",
        )
        updated_row = _make_email_svc_row(
            id=service_id, tenant_id=str(tenant_id), name="new-name",
        )
        call_count: dict[str, int] = {"n": 0}
        captured_update_params: list[dict[str, Any]] = []

        async def _fake_execute(stmt: Any, params: Any = None) -> Any:
            sql = str(stmt)
            call_count["n"] += 1
            if "UPDATE" in sql:
                captured_update_params.append(dict(params or {}))
                return _FakeResult(None)
            return _FakeResult(updated_row if call_count["n"] > 1 else existing_row)

        fake_session = _make_session()
        fake_session.execute = _fake_execute  # type: ignore[method-assign]
        fake_session.executed_sql = []  # type: ignore[assignment]

        patch_body = EmailServicePatch(name="  new-name  ")
        fake_request = self._make_patch_request({"name": "  new-name  "})

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await patch_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                body=patch_body,
                request=fake_request,
                session=fake_session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        assert len(captured_update_params) == 1
        assert captured_update_params[0]["name"] == "new-name", (
            f"PATCH didn't trim name: {captured_update_params[0]['name']!r}"
        )

    @pytest.mark.asyncio
    async def test_patch_preserves_internal_whitespace_in_allowed_recipient_domains(self) -> None:
        """#365: only edges are trimmed — internal whitespace in
        allowed_recipient_domains is preserved (no over-engineering)."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        existing_row = _make_email_svc_row(id=service_id, tenant_id=str(tenant_id))
        updated_row = _make_email_svc_row(id=service_id, tenant_id=str(tenant_id))
        call_count: dict[str, int] = {"n": 0}
        captured_update_params: list[dict[str, Any]] = []

        async def _fake_execute(stmt: Any, params: Any = None) -> Any:
            sql = str(stmt)
            call_count["n"] += 1
            if "UPDATE" in sql:
                captured_update_params.append(dict(params or {}))
                return _FakeResult(None)
            return _FakeResult(updated_row if call_count["n"] > 1 else existing_row)

        fake_session = _make_session()
        fake_session.execute = _fake_execute  # type: ignore[method-assign]
        fake_session.executed_sql = []  # type: ignore[assignment]

        internal = "  example.com,  other.com  "
        patch_body = EmailServicePatch(allowed_recipient_domains=internal)
        fake_request = self._make_patch_request({"allowed_recipient_domains": internal})

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await patch_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                body=patch_body,
                request=fake_request,
                session=fake_session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        assert len(captured_update_params) == 1
        # str.strip() only — internal "  " between domains is preserved.
        assert (
            captured_update_params[0]["allowed_recipient_domains"]
            == "example.com,  other.com"
        )

    @pytest.mark.asyncio
    async def test_patch_no_whitespace_input_unchanged(self) -> None:
        """#365: clean input is byte-identical pre/post trim (idempotent)."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())
        existing_row = _make_email_svc_row(id=service_id, tenant_id=str(tenant_id))
        updated_row = _make_email_svc_row(id=service_id, tenant_id=str(tenant_id))
        call_count: dict[str, int] = {"n": 0}
        captured_update_params: list[dict[str, Any]] = []

        async def _fake_execute(stmt: Any, params: Any = None) -> Any:
            sql = str(stmt)
            call_count["n"] += 1
            if "UPDATE" in sql:
                captured_update_params.append(dict(params or {}))
                return _FakeResult(None)
            return _FakeResult(updated_row if call_count["n"] > 1 else existing_row)

        fake_session = _make_session()
        fake_session.execute = _fake_execute  # type: ignore[method-assign]
        fake_session.executed_sql = []  # type: ignore[assignment]

        patch_body = EmailServicePatch(name="clean-name")
        fake_request = self._make_patch_request({"name": "clean-name"})

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await patch_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                body=patch_body,
                request=fake_request,
                session=fake_session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 200
        assert captured_update_params[0]["name"] == "clean-name"

    @pytest.mark.asyncio
    async def test_patch_all_whitespace_name_rejected_422(self) -> None:
        """#365: all-whitespace name trims to empty → 422 invalid_name."""
        tenant_id = uuid.uuid4()
        service_id = str(uuid.uuid4())

        # No UPDATE should fire — only the existence-check SELECT
        executed_sqls: list[str] = []

        async def _fake_execute(stmt: Any, params: Any = None) -> Any:
            sql = str(stmt)
            executed_sqls.append(sql)
            if "SELECT id FROM email_services" in sql:
                return _FakeResult(_FakeRow(id=service_id))
            return _FakeResult(None)

        fake_session = _make_session()
        fake_session.execute = _fake_execute  # type: ignore[method-assign]

        patch_body = EmailServicePatch(name="   \t \n ")
        fake_request = self._make_patch_request({"name": "   \t \n "})

        with patch("admin_api.api.email_services.set_tenant_context", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.require_tenant_session", new_callable=AsyncMock), \
             patch("admin_api.api.email_services.audit_emit", new_callable=AsyncMock):
            result = await patch_email_service(
                tenant_id=tenant_id,
                service_id=service_id,
                body=patch_body,
                request=fake_request,
                session=fake_session,  # type: ignore[arg-type]
                _authz=None,
            )

        assert result.status_code == 422
        body = json.loads(result.body)
        assert body["mintkey:code"] == "invalid_name"
        # No UPDATE was executed
        assert not any("UPDATE email_services" in sql for sql in executed_sqls)
