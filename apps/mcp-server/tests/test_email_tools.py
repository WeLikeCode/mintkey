"""
Unit tests for MCP email tools (feat/agent-email-e2e).

Tests email_list_mailboxes, email_fetch_message, email_search_messages,
email_send — each with mocked DB, broker, and email-proxy HTTP calls.

Uses the synchronous asyncio.run pattern consistent with the rest of this
test suite (see test_request_token.py for the established pattern).

Source: feat/agent-email-e2e.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from typing import AsyncGenerator, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_TEST_AGENT_ID = "agent_test00000000000000000001"
_TEST_TENANT_ID = str(uuid.uuid4())
_TEST_ESVC_UUID = "d28eec49-bb20-4991-866c-675c3be41aea"
# Crockford wire form of _TEST_ESVC_UUID — same as real smoke test value.
_TEST_ESVC_WIRE = "svc_6JHVP4KES0968RCV37BGXY86QA"
_TEST_JWT = "header.claims.sig"
_TEST_GRANT_ID = "00000000-0000-0000-0000-000000000001"


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------

def _build_email_app(
    *,
    esvc_exists: bool = True,       # whether email_services row exists
    grant_exists: bool = True,       # whether email_permission_grants row exists
):
    """
    Build a FastAPI app with mocked agent context and DB session for email tools.

    The DB session mock distinguishes queries by their parameter key patterns:
      - esid + tid (no aid)  → resolve_email_service_id  (email_services lookup)
      - sid (no aid, no esid) → services table existence check (returns None)
      - aid + esid            → email_permission_grants lookup
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _fake_agent_context():
        return {"agent_id": _TEST_AGENT_ID, "tenant_id": _TEST_TENANT_ID}

    app.dependency_overrides[get_agent_context] = _fake_agent_context

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()

        async def _execute(stmt, params=None, **kw):
            result = MagicMock()
            result.fetchone = MagicMock(return_value=None)
            result.fetchall = MagicMock(return_value=[])
            p = params or {}

            if "esid" in p and "tid" in p and "aid" not in p:
                # resolve_email_service_id — email_services table lookup
                if esvc_exists:
                    row = MagicMock()
                    row.id = _TEST_ESVC_UUID
                    result.fetchone.return_value = row
                else:
                    result.fetchone.return_value = None
            elif "aid" in p and "esid" in p:
                # email_permission_grants lookup
                if grant_exists:
                    row = MagicMock()
                    row.id = _TEST_GRANT_ID
                    result.fetchone.return_value = row
                else:
                    result.fetchone.return_value = None
            # All other queries (set_tenant_context SET LOCAL, etc.) return empty.
            return result

        session.execute = _execute
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session
    return app


def _run(coro):
    """Run an async coroutine in a new event loop (test helper)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests for email_list_mailboxes
# ---------------------------------------------------------------------------

def test_email_list_mailboxes_success():
    """email_list_mailboxes returns 200 with mailbox list when grant exists."""
    app = _build_email_app()

    mailbox_resp = MagicMock()
    mailbox_resp.status_code = 200
    mailbox_resp.json = MagicMock(
        return_value={"mailboxes": [{"name": "INBOX"}, {"name": "Sent"}]}
    )

    broker_resp = MagicMock()
    broker_resp.status_code = 200
    broker_resp.json = MagicMock(return_value={"token": _TEST_JWT, "expires_at": 9999999999})

    async def _inner():
        with (
            patch(
                "mcp_server.tools.email_list_mailboxes._get_email_jwt",
                new=AsyncMock(return_value=_TEST_JWT),
            ),
            patch(
                "mcp_server.tools.email_list_mailboxes.httpx.AsyncClient"
            ) as mock_proxy_cls,
        ):
            mock_proxy = AsyncMock()
            mock_proxy.get = AsyncMock(return_value=mailbox_resp)
            mock_proxy_cls.return_value.__aenter__ = AsyncMock(return_value=mock_proxy)
            mock_proxy_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/v1/tools/email_list_mailboxes?email_service_id={_TEST_ESVC_WIRE}",
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    resp = _run(_inner())
    assert resp.status_code == 200
    data = resp.json()
    assert "mailboxes" in data
    assert len(data["mailboxes"]) == 2


def test_email_list_mailboxes_no_grant_returns_403():
    """email_list_mailboxes returns 403 when agent has no email_permission_grant."""
    app = _build_email_app(grant_exists=False)

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(
                f"/v1/tools/email_list_mailboxes?email_service_id={_TEST_ESVC_WIRE}",
                headers={"Authorization": "Bearer mk_agent_test"},
            )

    resp = _run(_inner())
    assert resp.status_code == 403
    assert resp.json()["code"] == "mintkey:not_authorized"


def test_email_list_mailboxes_service_not_found_returns_404():
    """email_list_mailboxes returns 404 when email service is not found."""
    app = _build_email_app(esvc_exists=False)

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            # Use a non-existent UUID wire form (24 zeros + "AA")
            return await client.get(
                "/v1/tools/email_list_mailboxes?email_service_id=svc_00000000000000000000000000",
                headers={"Authorization": "Bearer mk_agent_test"},
            )

    resp = _run(_inner())
    assert resp.status_code == 404


def test_email_list_mailboxes_broker_error_returns_502():
    """email_list_mailboxes returns 502 when broker call fails."""
    app = _build_email_app()

    async def _inner():
        with patch(
            "mcp_server.tools.email_list_mailboxes._get_email_jwt",
            new=AsyncMock(return_value=None),  # None = broker error
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/v1/tools/email_list_mailboxes?email_service_id={_TEST_ESVC_WIRE}",
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    resp = _run(_inner())
    assert resp.status_code == 502


# ---------------------------------------------------------------------------
# Tests for email_send
# ---------------------------------------------------------------------------

def test_email_send_success():
    """email_send returns 200 when broker + email-proxy both succeed."""
    app = _build_email_app()

    send_resp = MagicMock()
    send_resp.status_code = 200
    send_resp.json = MagicMock(
        return_value={"message_id": "msg_001", "sent_at": "2026-06-02T10:00:00Z"}
    )
    send_resp.text = '{"message_id":"msg_001"}'

    async def _inner():
        with (
            patch(
                "mcp_server.tools.email_send._get_email_jwt",
                new=AsyncMock(return_value=_TEST_JWT),
            ),
            patch("mcp_server.tools.email_send.httpx.AsyncClient") as mock_cls,
        ):
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=send_resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/email_send",
                    json={
                        "email_service_id": _TEST_ESVC_WIRE,
                        "to": ["recipient@example.com"],
                        "subject": "Test",
                        "body": "Hello from test",
                    },
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    resp = _run(_inner())
    assert resp.status_code == 200


def test_email_send_no_grant_returns_403():
    """email_send returns 403 when agent has no email_permission_grant."""
    app = _build_email_app(grant_exists=False)

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/v1/tools/email_send",
                json={
                    "email_service_id": _TEST_ESVC_WIRE,
                    "to": ["r@example.com"],
                    "subject": "X",
                    "body": "Y",
                },
                headers={"Authorization": "Bearer mk_agent_test"},
            )

    resp = _run(_inner())
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Tests for email_search_messages
# ---------------------------------------------------------------------------

def test_email_search_messages_success():
    """email_search_messages returns 200 with search results."""
    app = _build_email_app()

    search_resp = MagicMock()
    search_resp.status_code = 200
    search_resp.json = MagicMock(return_value={"messages": [{"uid": 1, "subject": "Hello"}]})

    async def _inner():
        with (
            patch(
                "mcp_server.tools.email_search_messages._get_email_jwt",
                new=AsyncMock(return_value=_TEST_JWT),
            ),
            patch("mcp_server.tools.email_search_messages.httpx.AsyncClient") as mock_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=search_resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/v1/tools/email_search_messages"
                    f"?email_service_id={_TEST_ESVC_WIRE}&query=UNSEEN",
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    resp = _run(_inner())
    assert resp.status_code == 200
    assert "messages" in resp.json()


# ---------------------------------------------------------------------------
# Tests for email_fetch_message
# ---------------------------------------------------------------------------

def test_email_fetch_message_success():
    """email_fetch_message returns 200 with the message."""
    app = _build_email_app()

    fetch_resp = MagicMock()
    fetch_resp.status_code = 200
    fetch_resp.json = MagicMock(return_value={"uid": 42, "subject": "Hi", "body": "Hello"})

    async def _inner():
        with (
            patch(
                "mcp_server.tools.email_fetch_message._get_email_jwt",
                new=AsyncMock(return_value=_TEST_JWT),
            ),
            patch("mcp_server.tools.email_fetch_message.httpx.AsyncClient") as mock_cls,
        ):
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=fetch_resp)
            mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    f"/v1/tools/email_fetch_message"
                    f"?email_service_id={_TEST_ESVC_WIRE}&message_id=42",
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    resp = _run(_inner())
    assert resp.status_code == 200
    assert resp.json()["uid"] == 42


# ---------------------------------------------------------------------------
# Tests for request_token email path
# ---------------------------------------------------------------------------

def _build_request_token_email_app():
    """
    Build app with mocked DB for testing request_token with an email_service_id.

    DB mock rules for request_token's query sequence:
      - SELECT id FROM services WHERE id = :sid  → None (not in services table)
      - SELECT id FROM email_services WHERE ...   → returns row (in email_services)
      - SELECT id FROM email_permission_grants ... → returns row (grant exists)
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _fake_agent_context():
        return {"agent_id": _TEST_AGENT_ID, "tenant_id": _TEST_TENANT_ID}

    app.dependency_overrides[get_agent_context] = _fake_agent_context

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()

        async def _execute(stmt, params=None, **kw):
            result = MagicMock()
            result.fetchone = MagicMock(return_value=None)
            result.fetchall = MagicMock(return_value=[])
            p = params or {}

            if "sid" in p and "slug" not in p and "aid" not in p and "esid" not in p and "tid" not in p:
                # SELECT id FROM services WHERE id = :sid — not in services
                result.fetchone.return_value = None
            elif "esid" in p and "tid" in p and "aid" not in p:
                # resolve_email_service_id — found in email_services
                row = MagicMock()
                row.id = _TEST_ESVC_UUID
                result.fetchone.return_value = row
            elif "aid" in p and "esid" in p:
                # email_permission_grants lookup — grant exists
                row = MagicMock()
                row.id = _TEST_GRANT_ID
                result.fetchone.return_value = row
            # slug lookup, set_tenant_context, etc. → empty
            return result

        session.execute = _execute
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session
    return app


def test_request_token_email_service_returns_service_kind_email():
    """
    request_token returns service_kind=email when the service_id resolves to
    an email_service rather than an HTTP service.
    """
    app = _build_request_token_email_app()

    broker_resp = MagicMock()
    broker_resp.status_code = 200
    broker_resp.json = MagicMock(return_value={"token": _TEST_JWT, "expires_at": 9999999999})

    async def _inner():
        with patch(
            "mcp_server.tools.request_token.httpx.AsyncClient"
        ) as mock_broker_cls:
            mock_broker = AsyncMock()
            mock_broker.post = AsyncMock(return_value=broker_resp)
            mock_broker_cls.return_value.__aenter__ = AsyncMock(return_value=mock_broker)
            mock_broker_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/request_token",
                    json={"service_id": _TEST_ESVC_WIRE, "action": "call"},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    resp = _run(_inner())
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text}"
    data = resp.json()
    assert data.get("service_kind") == "email", (
        f"Expected service_kind=email in response, got: {data}"
    )
    assert "token" in data


def test_request_token_broker_called_with_service_kind_email():
    """
    request_token passes service_kind=email to the broker when the service is
    an email service.
    """
    app = _build_request_token_email_app()

    broker_resp = MagicMock()
    broker_resp.status_code = 200
    broker_resp.json = MagicMock(return_value={"token": _TEST_JWT, "expires_at": 9999999999})
    captured_payload: list = []

    async def _inner():
        with patch(
            "mcp_server.tools.request_token.httpx.AsyncClient"
        ) as mock_broker_cls:
            async def _fake_post(url, *, json=None, headers=None, timeout=None):
                captured_payload.append(json or {})
                return broker_resp

            mock_broker = AsyncMock()
            mock_broker.post = _fake_post
            mock_broker_cls.return_value.__aenter__ = AsyncMock(return_value=mock_broker)
            mock_broker_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/request_token",
                    json={"service_id": _TEST_ESVC_WIRE, "action": "call"},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    _run(_inner())
    # The broker may be called multiple times (agent key validation + JWT issue).
    # Find the JWT issue call by looking for agent_id in the payload.
    issue_calls = [p for p in captured_payload if "agent_id" in p]
    assert len(issue_calls) == 1, (
        f"Broker should have been called exactly once for JWT issue, got: {issue_calls}"
    )
    payload = issue_calls[0]
    assert payload.get("service_kind") == "email", (
        f"Broker payload should have service_kind=email, got: {payload}"
    )
    assert "read:email" in payload.get("scope", ""), (
        f"Broker payload scope should include read:email, got: {payload.get('scope')}"
    )
