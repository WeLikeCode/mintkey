"""
Unit tests: discovery hides the grants that the database says are expired.

Requirement: grant-expiry › An expired grant is absent for the agent

  - discovery hides what the database says is expired (C-e07d9989)

Each handler is called directly with a recording fake session so the test can
read the statements it executed.  The list/discovery joins use the `pg` alias
for `permission_grants`; the `describe_service` lookup uses the bare column
names.

Sources:
  - `openspec/changes/grant-expiry/spec.md` — An expired grant is absent for the
    agent; discovery hides what the database says is expired
  - `openspec/changes/grant-expiry/design.md` — D3
"""
from __future__ import annotations

import asyncio
import re
import types
import uuid
from unittest.mock import MagicMock

import pytest

import mcp_server.tools.discovery as discovery

_AGENT_ID = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
_TENANT_ID = uuid.UUID("11111111-2222-3333-4444-555555555555")
_SERVICE_UUID = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
_AGENT_CTX = {"agent_id": _AGENT_ID, "tenant_id": _TENANT_ID}


class _Result:
    """The small slice of a SQLAlchemy result a handler uses."""

    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def fetchall(self) -> list[object]:
        return list(self._rows)

    def fetchone(self) -> object | None:
        return self._rows[0] if self._rows else None


class _RecordingSession:
    """Records every statement and answers the reads the handler performs."""

    def __init__(self, service_row: object | None = None) -> None:
        self.statements: list[str] = []
        self._service_row = service_row

    async def execute(self, statement, params=None, **kwargs):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        if "set_config" in sql:
            return _Result([])
        if "JOIN permission_grants" in sql:
            return _Result([])
        if "FROM email_services" in sql:
            return _Result([])
        if "FROM permission_grants" in sql:
            return _Result([])
        if "FROM services" in sql:
            return _Result([self._service_row] if self._service_row else [])
        return _Result([])


def _service_row() -> types.SimpleNamespace:
    return types.SimpleNamespace(
        id=_SERVICE_UUID,
        name="test-svc",
        slug="test-svc",
        base_url="https://example.com",
        auth_scheme="api_key_header",
        description=None,
        openapi_url=None,
    )


def _statements_reading_whole_word(
    session: _RecordingSession, table: str
) -> list[str]:
    """Q-002: match the table name as a whole word.

    `_` is a word character, so the email grants table
    `email_permission_grants` is not counted, while every statement that
    reads `permission_grants` (any whitespace or line break around it) is.
    """
    return [
        statement
        for statement in session.statements
        if re.search(rf"\b{re.escape(table)}\b", statement)
    ]


@pytest.mark.l4("C-e07d9989")
def test_C_e07d9989_list_services_filters_expired_grants() -> None:
    """The list_services join only reads grants that have not expired."""
    session = _RecordingSession()

    response = asyncio.run(
        discovery.list_services(
            request=MagicMock(),
            session=session,
            agent_ctx=dict(_AGENT_CTX),
        )
    )

    assert response.status_code == 200
    statements = _statements_reading_whole_word(session, "permission_grants")
    assert statements, "list_services must read permission_grants"
    for statement in statements:
        assert "pg.expires_at IS NULL OR pg.expires_at > now()" in statement


@pytest.mark.l4("C-e07d9989")
def test_C_e07d9989_discover_filters_expired_grants() -> None:
    """The discover join only reads grants that have not expired."""
    session = _RecordingSession()

    response = asyncio.run(
        discovery.discover(
            request=MagicMock(),
            session=session,
            agent_ctx=dict(_AGENT_CTX),
        )
    )

    assert response.status_code == 200
    statements = _statements_reading_whole_word(session, "permission_grants")
    assert statements, "discover must read permission_grants"
    for statement in statements:
        assert "pg.expires_at IS NULL OR pg.expires_at > now()" in statement


@pytest.mark.l4("C-e07d9989")
def test_C_e07d9989_describe_service_filters_expired_grants() -> None:
    """The describe_service lookup only reads grants that have not expired."""
    session = _RecordingSession(service_row=_service_row())

    response = asyncio.run(
        discovery.describe_service(
            _SERVICE_UUID,
            request=MagicMock(),
            session=session,
            agent_ctx=dict(_AGENT_CTX),
        )
    )

    assert response.status_code == 200
    statements = _statements_reading_whole_word(session, "permission_grants")
    assert statements, "describe_service must read permission_grants"
    for statement in statements:
        assert "expires_at IS NULL OR expires_at > now()" in statement


@pytest.mark.l4("C-e07d9989")
def test_C_e07d9989_list_services_grant_reads_hide_expired_rows() -> None:
    """list_services reads permission_grants only where the grant is live (Q-002 whole-word helper)."""
    session = _RecordingSession()

    response = asyncio.run(
        discovery.list_services(
            request=MagicMock(),
            session=session,
            agent_ctx=dict(_AGENT_CTX),
        )
    )

    assert response.status_code == 200
    statements = _statements_reading_whole_word(session, "permission_grants")
    assert statements, "list_services must read permission_grants"
    for statement in statements:
        assert "pg.expires_at IS NULL OR pg.expires_at > now()" in statement


@pytest.mark.l4("C-e07d9989")
def test_C_e07d9989_discover_grant_reads_hide_expired_rows() -> None:
    """discover reads permission_grants only where the grant is live (Q-002 whole-word helper)."""
    session = _RecordingSession()

    response = asyncio.run(
        discovery.discover(
            request=MagicMock(),
            session=session,
            agent_ctx=dict(_AGENT_CTX),
        )
    )

    assert response.status_code == 200
    statements = _statements_reading_whole_word(session, "permission_grants")
    assert statements, "discover must read permission_grants"
    for statement in statements:
        assert "pg.expires_at IS NULL OR pg.expires_at > now()" in statement


@pytest.mark.l4("C-e07d9989")
def test_C_e07d9989_describe_service_grant_reads_hide_expired_rows() -> None:
    """describe_service reads permission_grants only where the grant is live (Q-002 whole-word helper)."""
    session = _RecordingSession(service_row=_service_row())

    response = asyncio.run(
        discovery.describe_service(
            _SERVICE_UUID,
            request=MagicMock(),
            session=session,
            agent_ctx=dict(_AGENT_CTX),
        )
    )

    assert response.status_code == 200
    statements = _statements_reading_whole_word(session, "permission_grants")
    assert statements, "describe_service must read permission_grants"
    for statement in statements:
        assert "expires_at IS NULL OR expires_at > now()" in statement
