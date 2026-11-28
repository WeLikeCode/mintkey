"""Unit tests: the credential write emits the event its contract defines.

Task 1.3 of agent-service-routes-fix-1 — feedback FB-003. The scenario
"service.credential.set matches its schema" decides:

  - when an agent sets the credential of a service it owns, the emitted
    ``service.credential.set`` event carries ``target_type`` ``service`` and
    ``target_id`` the service's id, and
  - the emitted event validates against ``$defs/ev_service_credential_set`` in
    ``docs/architecture/contracts/events/audit-event.schema.json``.

Sources:
  - `openspec/changes/agent-service-routes-fix-1/specs/agent-service-credential/spec.md`
    — service.credential.set matches its schema
  - `openspec/changes/agent-service-routes/design.md` — D8 (the definition
    pins `target_type` `service` and the payload `{service_id, key_version,
    auth_scheme}`)
  - `docs/architecture/contracts/events/audit-event.schema.json`
"""

# ruff: noqa: E402 — the service packages are imported after sys.path setup.
from __future__ import annotations

import json
import re
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

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ab")

SECRET = "s3cret-value-123"

SCHEMA_PATH = (
    REPO_ROOT
    / "docs"
    / "architecture"
    / "contracts"
    / "events"
    / "audit-event.schema.json"
)


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class _Result:
    """The slice of a SQLAlchemy result the handler uses."""

    def __init__(self, row: Any | None = None) -> None:
        self._row = row

    def fetchone(self) -> Any | None:
        return self._row


class _AuditCapturingSession:
    """Record every statement and the full ``audit_events`` INSERT parameters.

    The ownership SELECT returns ``service_row``; the metadata writes answer
    empty results, and ``audit_emit`` / ``notify_change`` run for real so the
    emitted event is captured exactly as the handler writes it to the
    database.
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
                    "event_id": bound.get("id"),
                    "event_type": bound.get("event_type"),
                    "tenant_id": bound.get("tenant_id"),
                    "actor_id": bound.get("actor_id"),
                    "actor_type": bound.get("actor_type"),
                    "target_id": bound.get("target_id"),
                    "target_type": bound.get("target_type"),
                    "at": bound.get("at"),
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
    """Answer ``put_credential`` with a key version."""

    def __init__(self, key_version: int = 1) -> None:
        self.key_version = key_version

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
        return {"key_version": self.key_version}


def _principal() -> AgentPrincipal:
    return AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="publisher")


def _service_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=SERVICE_ID,
        tenant_id=TENANT_ID,
        name="My Service",
        slug="my-service",
        display_name="My Service",
        description="A service",
        base_url="https://api.example.com",
        auth_scheme="bearer_token",
        openapi_url=None,
        status="active",
        owner_agent_id=AGENT_ID,
        created_by_agent_id=AGENT_ID,
        credential_set=True,
        created_at=datetime(2026, 2, 3, 4, 5, 6, tzinfo=timezone.utc),
        updated_at=datetime(2026, 2, 3, 4, 5, 7, tzinfo=timezone.utc),
    )


def _request(payload: Any) -> Request:
    raw = json.dumps(payload).encode()

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


async def _put(
    session: _AuditCapturingSession,
    vault: _FakeVault,
    payload: Any,
) -> tuple[int, dict[str, Any]]:
    try:
        response = await agent_services._put_agent_credential(
            service_ref="my-service",
            request=_request(payload),
            principal=_principal(),
            session=session,
            vault=vault,
        )
    except AgentApiError as exc:
        return exc.status_code, exc.body
    assert response is not None, "the PUT handler returned no response"
    assert isinstance(response, JSONResponse), type(response)
    return response.status_code, json.loads(bytes(response.body))


# ---------------------------------------------------------------------------
# A minimal validator for the definition's own fields
# ---------------------------------------------------------------------------


def _resolve(schema: dict[str, Any], defs: dict[str, Any]) -> dict[str, Any]:
    """Follow a local ``$ref`` to its definition."""
    while "$ref" in schema:
        ref = schema["$ref"]
        assert ref.startswith("#/$defs/"), ref
        schema = defs[ref.split("/")[-1]]
    return schema


def _validate_value(
    value: Any,
    schema: dict[str, Any],
    defs: dict[str, Any],
    path: str,
) -> None:
    """Check a value against the subset of JSON Schema the contract uses."""
    schema = _resolve(schema, defs)
    if "const" in schema:
        assert value == schema["const"], f"{path}: {value!r} != {schema['const']!r}"
    if "enum" in schema:
        assert value in schema["enum"], f"{path}: {value!r} not in {schema['enum']}"

    kind = schema.get("type")
    if kind == "object":
        assert isinstance(value, dict), f"{path}: {value!r} is not an object"
        properties = schema.get("properties", {})
        for required in schema.get("required", []):
            assert required in value, f"{path}: missing required {required}"
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            assert not extra, f"{path}: unexpected keys {sorted(extra)}"
        for key, sub_schema in properties.items():
            if key in value:
                _validate_value(value[key], sub_schema, defs, f"{path}.{key}")
    elif kind == "string":
        assert isinstance(value, str), f"{path}: {value!r} is not a string"
        if "pattern" in schema:
            assert re.match(schema["pattern"], value), (
                f"{path}: {value!r} does not match {schema['pattern']!r}"
            )
        if "minLength" in schema:
            assert len(value) >= schema["minLength"], f"{path}: too short"
        if "maxLength" in schema:
            assert len(value) <= schema["maxLength"], f"{path}: too long"
    elif kind == "integer":
        assert isinstance(value, int) and not isinstance(value, bool), (
            f"{path}: {value!r} is not an integer"
        )
        if "minimum" in schema:
            assert value >= schema["minimum"], f"{path}: below minimum"
    elif kind == "array":
        assert isinstance(value, list), f"{path}: {value!r} is not an array"
        for index, item in enumerate(value):
            _validate_value(item, schema["items"], defs, f"{path}[{index}]")


def _assert_event_matches_definition(event: dict[str, Any]) -> None:
    """Validate the emitted event against ``ev_service_credential_set``."""
    schema: dict[str, Any] = json.loads(SCHEMA_PATH.read_text())
    defs: dict[str, Any] = schema["$defs"]
    definition = defs["ev_service_credential_set"]
    properties = definition["properties"]

    # The definition pins the event type, the target type and the payload.
    _validate_value(event["event_type"], properties["event_type"], defs, "event_type")
    _validate_value(event["target_type"], properties["target_type"], defs, "target_type")
    _validate_value(event["payload"], properties["payload"], defs, "payload")

    # Every envelope field the definition requires is present on the event.
    envelope = defs["envelope"]
    for required in envelope["required"]:
        assert required in event, f"event is missing envelope field {required}"


# ---------------------------------------------------------------------------
# C-50c7880c — the emitted event matches its schema
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-50c7880c")
@pytest.mark.asyncio
async def test_C_50c7880c_credential_set_event_targets_the_service_and_validates() -> None:
    session = _AuditCapturingSession(service_row=_service_row())
    vault = _FakeVault(key_version=1)

    status, body = await _put(session, vault, {"value": SECRET})

    assert status == 200, body
    events = [
        event
        for event in session.audit_events
        if event["event_type"] == "service.credential.set"
    ]
    assert len(events) == 1, session.audit_events
    event = events[0]

    # The event is about the service, not the credential row.
    assert event["target_type"] == "service"
    assert event["target_id"] == str(SERVICE_ID)

    # The emitted event conforms to the definition this unit adds.
    _assert_event_matches_definition(event)
