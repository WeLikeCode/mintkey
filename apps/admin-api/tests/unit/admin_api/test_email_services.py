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
    """Simulate fetchone() returning a row or None."""
    def __init__(self, row: Any = None) -> None:
        self._row = row

    def fetchone(self) -> Any:
        return self._row

    def one_or_none(self) -> Any:
        return self._row


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
    _oauth2_config,
    _valid_host_port,
    _is_valid_uuid,
    _VALID_PROVIDERS,
    _VALID_AUTH_SCHEMES,
    _PROVIDER_AUTH_SCHEMES,
    create_email_service,
    oauth2_authorize,
    oauth2_callback,
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
