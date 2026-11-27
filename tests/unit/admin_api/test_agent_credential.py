"""Unit tests: a credential is written, never read, and bound to its target.

Task 4.1 of agent-service-routes. The four scenarios of "A credential is
written, never read, and bound to its target" decide:

  1. a bearer credential is passed once to the vault with the service's target
     and ``egress_scope`` ``public``, the metadata rows are written in the
     request's transaction, the answer is exactly
     ``{service_id, credential_set, updated_at}``, one ``mintkey:credential``
     NOTIFY is sent, and no answer, event, NOTIFY or statement repeats the
     value;
  2. the header and query-parameter names are validated against the service's
     scheme (``api_key_header`` needs ``header_name``, ``api_key_query`` needs
     ``query_param``, the other schemes take neither);
  3. a bad value, another owner, a failing vault or an unsupported scheme
     answers the one agent error body and writes no metadata and no event;
  4. the service row is locked (``FOR UPDATE``) before the vault write, and
     every metadata statement and audit event follows the vault call.

Sources:
  - `openspec/changes/agent-service-routes/spec.md` — A credential is written,
    never read, and bound to its target
  - `openspec/changes/agent-service-routes/design.md` — D3, D7, D10, D11
"""

# ruff: noqa: E402 — the service packages are imported after sys.path setup.
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from fastapi import Request
from fastapi.responses import JSONResponse

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
MODELS_SRC = REPO_ROOT / "packages" / "python" / "mintkey-models"
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from admin_api.api import agent_services
from admin_api.auth.agent_principal import AgentApiError, AgentPrincipal
from admin_api.utils.wire_ids import db_uuid_to_wire

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
OTHER_AGENT_ID = UUID("00000000-0000-0000-0000-000000000023")
SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ab")

SECRET = "s3cret-value-123"

VALIDATION_BODY: dict[str, Any] = {
    "code": "mintkey:validation_failed",
    "title": "Invalid request body",
}
NOT_OWNER_BODY: dict[str, Any] = {
    "code": "mintkey:not_owner",
    "title": "Not the owner of this service",
}
VAULT_UNAVAILABLE_BODY: dict[str, Any] = {
    "code": "mintkey:vault_unavailable",
    "title": "Credential store unavailable",
}


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    """The slice of a SQLAlchemy result the handlers use."""

    def __init__(self, row: Any | None = None) -> None:
        self._row = row

    def fetchone(self) -> Any | None:
        return self._row

    def fetchall(self) -> list[Any]:
        return [] if self._row is None else [self._row]


class _FakeSession:
    """Record every statement, event and NOTIFY the credential route runs.

    The ownership SELECT returns ``service_row`` (or nothing), the supersede
    and metadata writes are recorded, and the ``services`` update answers a row
    carrying the bound ``updated_at``. ``audit_emit`` and ``notify_change`` run
    for real against this session, so their statements and parameters appear
    like every other statement.
    """

    def __init__(self, *, service_row: Any | None = None) -> None:
        self.service_row = service_row
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.audit_events: list[dict[str, Any]] = []
        self.notifications: list[dict[str, Any]] = []

    async def execute(
        self,
        statement: Any,
        params: Any = None,
        **kwargs: Any,
    ) -> _Result:
        sql = " ".join(str(statement).split())
        bound: dict[str, Any] = params if isinstance(params, dict) else {}
        self.statements.append((sql, bound))
        upper = sql.upper()

        if "INSERT INTO AUDIT_EVENTS" in upper:
            self.audit_events.append(
                {
                    "event_type": bound.get("event_type"),
                    "actor_id": bound.get("actor_id"),
                    "actor_type": bound.get("actor_type"),
                    "payload": json.loads(bound.get("payload") or "{}"),
                }
            )
            return _Result()

        if "PG_NOTIFY" in upper:
            self.notifications.append(
                {
                    "channel": bound.get("channel"),
                    "payload": json.loads(bound.get("payload") or "{}"),
                }
            )
            return _Result()

        if upper.startswith("SELECT") and "FROM SERVICES" in upper:
            return _Result(self.service_row)

        if upper.startswith("UPDATE SERVICES") and "CURRENT_KEY_VERSION" in upper:
            now = next(
                (value for value in bound.values() if isinstance(value, datetime)),
                None,
            )
            return _Result(
                SimpleNamespace(
                    id=getattr(self.service_row, "id", SERVICE_ID),
                    updated_at=now,
                )
            )

        return _Result()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def flush(self) -> None:
        return None


class _FakeVault:
    """Record each ``put_credential`` call and its keywords, or raise."""

    def __init__(
        self,
        *,
        session: _FakeSession | None = None,
        key_version: int = 1,
        error: Exception | None = None,
    ) -> None:
        self.session = session
        self.key_version = key_version
        self.error = error
        self.calls: list[dict[str, Any]] = []
        self.positions: list[int] = []

    async def put_credential(
        self,
        tenant_id: str,
        service_id: str,
        auth_scheme: str,
        plaintext: str,
        target_url: str = "",
        header_name: str = "",
        query_param: str = "",
        target_address: str = "",
        ssh_user: str = "",
        egress_scope: str = "",
    ) -> dict[str, object]:
        self.calls.append(
            {
                "tenant_id": tenant_id,
                "service_id": service_id,
                "auth_scheme": auth_scheme,
                "plaintext": plaintext,
                "target_url": target_url,
                "header_name": header_name,
                "query_param": query_param,
                "target_address": target_address,
                "ssh_user": ssh_user,
                "egress_scope": egress_scope,
            }
        )
        self.positions.append(
            len(self.session.statements) if self.session is not None else 0
        )
        if self.error is not None:
            raise self.error
        return {"key_version": self.key_version}


def _principal() -> AgentPrincipal:
    return AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="publisher")


def _service_row(
    *,
    owner: UUID | None = AGENT_ID,
    auth_scheme: str = "bearer_token",
    base_url: str = "https://api.example.com",
    credential_set: bool = True,
) -> SimpleNamespace:
    row = SimpleNamespace(
        id=SERVICE_ID,
        tenant_id=TENANT_ID,
        name="My Service",
        slug="my-service",
        display_name="My Service",
        description="A service",
        base_url=base_url,
        auth_scheme=auth_scheme,
        openapi_url=None,
        status="active",
        owner_agent_id=owner,
        created_by_agent_id=AGENT_ID,
        credential_set=credential_set,
        created_at=datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 3, 4, 5, 7, tzinfo=timezone.utc),
    )
    return row


def _request(raw: bytes) -> Request:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "PUT",
            "path": "/v1/agent/services/my-service/credential",
            "raw_path": b"/v1/agent/services/my-service/credential",
            "query_string": b"",
            "headers": [],
            "scheme": "http",
            "server": ("testserver", 80),
            "client": ("testclient", 123),
        },
        receive,
    )


def _json_request(payload: Any) -> Request:
    return _request(json.dumps(payload).encode())


async def _put(
    session: _FakeSession,
    vault: _FakeVault,
    payload: Any,
    *,
    raw: bytes | None = None,
    service_ref: str = "my-service",
    principal: AgentPrincipal | None = None,
) -> tuple[int, dict[str, Any]]:
    """Call the PUT handler directly and return its status and body."""
    request = _request(raw) if raw is not None else _json_request(payload)
    try:
        response = await agent_services._put_agent_credential(
            service_ref=service_ref,
            request=request,
            principal=principal or _principal(),
            session=session,
            vault=vault,
        )
    except AgentApiError as exc:
        return exc.status_code, exc.body
    assert response is not None, "the PUT handler returned no response"
    assert isinstance(response, JSONResponse), type(response)
    return response.status_code, json.loads(response.body)


def _metadata_statements(
    session: _FakeSession,
) -> list[tuple[int, str, dict[str, Any]]]:
    """The credential metadata writes, never the ownership read."""
    metadata: list[tuple[int, str, dict[str, Any]]] = []
    for index, (sql, params) in enumerate(session.statements):
        upper = sql.upper()
        if upper.startswith("UPDATE CREDENTIALS"):
            metadata.append((index, sql, params))
        elif upper.startswith("INSERT INTO CREDENTIALS"):
            metadata.append((index, sql, params))
        elif upper.startswith("UPDATE SERVICES") and "CURRENT_KEY_VERSION" in upper:
            metadata.append((index, sql, params))
    return metadata


def _statement_text(session: _FakeSession) -> str:
    """Every statement and its parameters as one searchable string."""
    parts: list[str] = []
    for sql, params in session.statements:
        parts.append(sql)
        parts.extend(repr(value) for value in params.values())
    return "\n".join(parts)


def _datetime_values(params: dict[str, Any]) -> list[datetime]:
    return [value for value in params.values() if isinstance(value, datetime)]


# ---------------------------------------------------------------------------
# C-4b7e8c8f — a bearer credential
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-4b7e8c8f")
@pytest.mark.asyncio
async def test_C_4b7e8c8f_bearer_credential_is_written_and_never_echoed() -> None:
    row = _service_row(auth_scheme="bearer_token", base_url="https://api.example.com")
    session = _FakeSession(service_row=row)
    vault = _FakeVault(session=session, key_version=1)

    status, body = await _put(session, vault, {"value": SECRET})

    assert status == 200, body
    assert set(body) == {"service_id", "credential_set", "updated_at"}
    assert body["service_id"] == db_uuid_to_wire(SERVICE_ID, "svc")
    assert body["credential_set"] is True

    # The vault saw the value once, with the service's target and public scope.
    assert len(vault.calls) == 1
    call = vault.calls[0]
    assert call["plaintext"] == SECRET
    assert call["target_url"] == row.base_url
    assert call["egress_scope"] == "public"
    assert call["auth_scheme"] == "bearer_token"
    assert str(call["tenant_id"]) == str(TENANT_ID)
    assert str(call["service_id"]) == str(SERVICE_ID)

    # The egress scope is a vault argument, never a statement.
    assert all("EGRESS_SCOPE" not in sql.upper() for sql, _params in session.statements)

    # The metadata writes: supersede the active rows, insert one, sync the
    # service with the one `now` value the answer reports.
    supersedes = [
        sql
        for sql, _params in session.statements
        if sql.upper().startswith("UPDATE CREDENTIALS")
        and "SUPERSEDED" in sql.upper()
    ]
    assert len(supersedes) == 1

    inserts = [
        (index, sql, params)
        for index, (sql, params) in enumerate(session.statements)
        if sql.upper().startswith("INSERT INTO CREDENTIALS")
    ]
    assert len(inserts) == 1
    _insert_index, _insert_sql, insert_params = inserts[0]

    service_updates = [
        (index, sql, params)
        for index, (sql, params) in enumerate(session.statements)
        if sql.upper().startswith("UPDATE SERVICES")
        and "CURRENT_KEY_VERSION" in sql.upper()
    ]
    assert len(service_updates) == 1
    service_update_index, _service_update_sql, service_update_params = service_updates[0]

    service_nows = _datetime_values(service_update_params)
    assert len(service_nows) == 1
    assert body["updated_at"] == service_nows[0].isoformat()
    assert _datetime_values(insert_params) == service_nows

    # No re-read after the write.
    later_service_selects = [
        sql
        for sql, _params in session.statements[service_update_index + 1 :]
        if sql.upper().startswith("SELECT") and "FROM SERVICES" in sql.upper()
    ]
    assert later_service_selects == []

    # One NOTIFY on the credential channel, ids only.
    assert len(session.notifications) == 1
    notification = session.notifications[0]
    assert notification["channel"] == "mintkey:credential"
    assert notification["payload"]["event"] == "credential.registered"
    assert notification["payload"]["tenant_id"] == str(TENANT_ID)
    assert notification["payload"]["service_id"] == db_uuid_to_wire(
        SERVICE_ID, "svc"
    )
    assert str(notification["payload"]["credential_id"]).startswith("cred_")

    # One audit event, actor the agent, the contract's payload.
    events = [
        event
        for event in session.audit_events
        if event["event_type"] == "service.credential.set"
    ]
    assert len(events) == 1
    event = events[0]
    assert event["actor_type"] == "agent"
    assert event["actor_id"] == str(AGENT_ID)
    assert event["payload"] == {
        "service_id": db_uuid_to_wire(SERVICE_ID, "svc"),
        "key_version": 1,
        "auth_scheme": "bearer_token",
    }

    # The tenant context is set first.
    first_sql, first_params = session.statements[0]
    assert "SET_CONFIG" in first_sql.upper()
    assert "APP.CURRENT_TENANT" in first_sql
    assert str(TENANT_ID) in {str(value) for value in first_params.values()}

    # No answer, NOTIFY, audit event or statement repeats the value.
    texts = [
        json.dumps(body),
        json.dumps(session.notifications),
        json.dumps([item["payload"] for item in session.audit_events]),
        _statement_text(session),
    ]
    for text in texts:
        assert SECRET not in text


# ---------------------------------------------------------------------------
# C-3be566fb — header and query names
# ---------------------------------------------------------------------------


HEADER_QUERY_CASES = [
    pytest.param(
        "api_key_header",
        {"value": SECRET},
        422,
        "header_name",
        id="header_missing",
    ),
    pytest.param(
        "api_key_header",
        {"value": SECRET, "header_name": "Host"},
        422,
        "header_name",
        id="header_host",
    ),
    pytest.param(
        "api_key_header",
        {"value": SECRET, "header_name": "X-Mintkey-Test"},
        422,
        "header_name",
        id="header_x_mintkey",
    ),
    pytest.param(
        "api_key_header",
        {"value": SECRET, "header_name": "content-length"},
        422,
        "header_name",
        id="header_content_length",
    ),
    pytest.param(
        "api_key_header",
        {"value": SECRET, "header_name": "Transfer-Encoding"},
        422,
        "header_name",
        id="header_transfer_encoding",
    ),
    pytest.param(
        "api_key_header",
        {"value": SECRET, "header_name": "CONNECTION"},
        422,
        "header_name",
        id="header_connection",
    ),
    pytest.param(
        "api_key_header",
        {"value": SECRET, "header_name": "x-mintkey-test"},
        422,
        "header_name",
        id="header_x_mintkey_lower",
    ),
    pytest.param(
        "api_key_header",
        {"value": SECRET, "header_name": "X Api Key"},
        422,
        "header_name",
        id="header_bad_characters",
    ),
    pytest.param(
        "api_key_header",
        {"value": SECRET, "header_name": "X-Api-Key"},
        200,
        None,
        id="header_valid",
    ),
    pytest.param(
        "bearer_token",
        {"value": SECRET, "header_name": "X-Api-Key"},
        422,
        "header_name",
        id="bearer_with_header",
    ),
    pytest.param(
        "api_key_query",
        {"value": SECRET},
        422,
        "query_param",
        id="query_missing",
    ),
    pytest.param(
        "api_key_query",
        {"value": SECRET, "query_param": "api_key"},
        200,
        None,
        id="query_valid",
    ),
    pytest.param(
        "bearer_token",
        {"value": SECRET, "query_param": "api_key"},
        422,
        "query_param",
        id="bearer_with_query",
    ),
]


@pytest.mark.l4("C-3be566fb")
@pytest.mark.asyncio
@pytest.mark.parametrize(("auth_scheme", "payload", "status", "field"), HEADER_QUERY_CASES)
async def test_C_3be566fb_header_and_query_names_follow_the_scheme(
    auth_scheme: str,
    payload: dict[str, Any],
    status: int,
    field: str | None,
) -> None:
    row = _service_row(auth_scheme=auth_scheme)
    session = _FakeSession(service_row=row)
    vault = _FakeVault(session=session)

    answer_status, body = await _put(session, vault, payload)

    assert answer_status == status, body
    if status == 422:
        assert body == {**VALIDATION_BODY, "field": field}
        assert SECRET not in json.dumps(body)
        assert vault.calls == []
        assert _metadata_statements(session) == []
        assert session.audit_events == []
        assert session.notifications == []
    else:
        assert len(vault.calls) == 1
        call = vault.calls[0]
        if auth_scheme == "api_key_header":
            assert call["header_name"] == "X-Api-Key"
            assert call["query_param"] == ""
        else:
            assert call["query_param"] == "api_key"
            assert call["header_name"] == ""


# ---------------------------------------------------------------------------
# C-08831467 — bad values, other owners, a failing vault, an unsupported scheme
# ---------------------------------------------------------------------------


BAD_VALUES = [
    pytest.param("", id="empty"),
    pytest.param("x" * 8193, id="too_long"),
    pytest.param(SECRET + "\n", id="line_feed"),
    pytest.param(SECRET + "\r", id="carriage_return"),
    pytest.param(SECRET + "\x00", id="nul"),
]


@pytest.mark.l4("C-08831467")
@pytest.mark.asyncio
@pytest.mark.parametrize("value", BAD_VALUES)
async def test_C_08831467_bad_value_answers_422_without_a_write(
    value: str,
) -> None:
    row = _service_row(auth_scheme="bearer_token")
    session = _FakeSession(service_row=row)
    vault = _FakeVault(session=session)

    status, body = await _put(session, vault, {"value": value})

    assert status == 422, body
    assert body == {**VALIDATION_BODY, "field": "value"}
    if value:
        assert value not in json.dumps(body)
    assert vault.calls == []
    assert _metadata_statements(session) == []
    assert session.audit_events == []
    assert session.notifications == []


@pytest.mark.l4("C-08831467")
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("payload", "raw"),
    [
        pytest.param([1], None, id="array"),
        pytest.param(None, b"{", id="unreadable_json"),
        pytest.param({"value": SECRET, "owner_agent_id": "agent_x"}, None, id="extra_key"),
    ],
)
async def test_C_08831467_bad_body_shape_answers_422_without_a_write(
    payload: Any,
    raw: bytes | None,
) -> None:
    session = _FakeSession(service_row=_service_row())
    vault = _FakeVault(session=session)

    status, body = await _put(session, vault, payload, raw=raw)

    assert status == 422, body
    assert body == {**VALIDATION_BODY, "field": None}
    assert SECRET not in json.dumps(body)
    assert vault.calls == []
    assert _metadata_statements(session) == []
    assert session.audit_events == []
    assert session.notifications == []


@pytest.mark.l4("C-08831467")
@pytest.mark.asyncio
async def test_C_08831467_other_owner_answers_403_without_a_write() -> None:
    session = _FakeSession(service_row=_service_row(owner=OTHER_AGENT_ID))
    vault = _FakeVault(session=session)

    status, body = await _put(session, vault, {"value": SECRET})

    assert status == 403, body
    assert body == NOT_OWNER_BODY
    assert SECRET not in json.dumps(body)
    assert vault.calls == []
    assert _metadata_statements(session) == []
    assert session.audit_events == []
    assert session.notifications == []


@pytest.mark.l4("C-08831467")
@pytest.mark.asyncio
async def test_C_08831467_failing_vault_answers_502_before_metadata() -> None:
    session = _FakeSession(service_row=_service_row())
    vault = _FakeVault(session=session, error=RuntimeError("vault is down"))

    status, body = await _put(session, vault, {"value": SECRET})

    assert status == 502, body
    assert body == VAULT_UNAVAILABLE_BODY
    assert SECRET not in json.dumps(body)
    assert len(vault.calls) == 1
    assert _metadata_statements(session) == []
    assert session.audit_events == []
    assert session.notifications == []


@pytest.mark.l4("C-08831467")
@pytest.mark.asyncio
async def test_C_08831467_unsupported_scheme_answers_422_without_a_vault_call() -> None:
    session = _FakeSession(service_row=_service_row(auth_scheme="ssh_private_key"))
    vault = _FakeVault(session=session)

    status, body = await _put(session, vault, {"value": SECRET})

    assert status == 422, body
    assert body == {**VALIDATION_BODY, "field": "auth_scheme"}
    assert SECRET not in json.dumps(body)
    assert vault.calls == []
    assert _metadata_statements(session) == []
    assert session.audit_events == []
    assert session.notifications == []


# ---------------------------------------------------------------------------
# C-6d26cd39 — the row is locked before the vault write
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-6d26cd39")
@pytest.mark.asyncio
async def test_C_6d26cd39_row_is_locked_before_the_vault_write() -> None:
    row = _service_row()
    session = _FakeSession(service_row=row)
    vault = _FakeVault(session=session)

    status, body = await _put(session, vault, {"value": SECRET})

    assert status == 200, body
    assert len(vault.positions) == 1
    put_position = vault.positions[0]

    # The first statement that names services (after the tenant context)
    # locks the row.
    assert session.statements[0][0].upper().startswith("SELECT SET_CONFIG")
    service_statements = [
        (index, sql)
        for index, (sql, _params) in enumerate(session.statements)
        if "SERVICES" in sql.upper()
    ]
    assert service_statements, "no statement named services"
    first_index, first_sql = service_statements[0]
    assert "FOR UPDATE" in first_sql.upper()
    assert put_position > first_index

    # Every metadata statement and audit write follows the vault call.
    metadata = _metadata_statements(session)
    assert metadata, "the credential wrote no metadata"
    assert all(index >= put_position for index, _sql, _params in metadata)

    audit_indexes = [
        index
        for index, (sql, _params) in enumerate(session.statements)
        if "INSERT INTO AUDIT_EVENTS" in sql.upper()
    ]
    assert audit_indexes, "the credential wrote no audit event"
    assert all(index >= put_position for index in audit_indexes)
