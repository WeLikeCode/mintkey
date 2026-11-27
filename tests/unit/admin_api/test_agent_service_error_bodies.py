"""Unit tests: every error of the service routes has one body.

Task 3.1 of agent-service-routes. The scenario "one body shape" of the
requirement "Every error of the service routes has one body" provokes every
refusal of the create and update routes and checks that each answer is the
exact agent error object of its cause: ``{"code": "mintkey:<name>", "title":
<fixed text>, ...detail}``, never the operator key ``mintkey:code``, and never
a value the caller sent.

The create cases already hold (task 2.1); the patch cases are red until the
PATCH route exists, so this test stays red as a whole.

Sources:
  - `openspec/changes/agent-service-routes/spec.md` — Every error of the
    service routes has one body; A publisher creates a service; A publisher
    updates only its own services
  - `openspec/changes/agent-service-routes/design.md` — D10
"""

# ruff: noqa: E402 — the service packages are imported after sys.path setup.
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from urllib.parse import urlsplit
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
from mintkey_models.egress import TargetNotAllowed

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
OTHER_AGENT_ID = UUID("00000000-0000-0000-0000-000000000023")
SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ab")


class _Result:
    """The slice of a SQLAlchemy result the handlers use."""

    def __init__(self, row: Any | None = None) -> None:
        self._row = row

    def fetchone(self) -> Any | None:
        return self._row

    def fetchall(self) -> list[Any]:
        return [] if self._row is None else [self._row]


class _FakeSession:
    """Record every statement and answer the service reads like the database."""

    def __init__(
        self,
        *,
        service_row: Any | None = None,
        slug_taken: bool = False,
    ) -> None:
        self.service_row = service_row
        self.slug_taken = slug_taken
        self.statements: list[tuple[str, dict[str, Any]]] = []

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

        if upper.startswith("SELECT") and "FROM SERVICES" in upper:
            if "SLUG" in upper and "OWNER_AGENT_ID" not in upper:
                return _Result(
                    SimpleNamespace(id=SERVICE_ID) if self.slug_taken else None
                )
            return _Result(self.service_row)

        return _Result()

    async def commit(self) -> None:
        return None

    async def rollback(self) -> None:
        return None

    async def flush(self) -> None:
        return None


def _principal() -> AgentPrincipal:
    return AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="publisher")


def _service_row(*, owner: UUID | None = AGENT_ID) -> SimpleNamespace:
    row = SimpleNamespace(
        id=SERVICE_ID,
        tenant_id=TENANT_ID,
        name="My Service",
        slug="my-service",
        display_name="My Service",
        description=None,
        base_url="https://api.example.com",
        auth_scheme="bearer_token",
        openapi_url=None,
        status="active",
        owner_agent_id=owner,
        created_by_agent_id=AGENT_ID,
        credential_set=True,
        created_at=None,
        updated_at=None,
    )
    return row


def _request(raw: bytes) -> Request:
    async def receive() -> dict[str, Any]:
        return {"type": "http.request", "body": raw, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/v1/agent/services",
            "raw_path": b"/v1/agent/services",
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


def _patch_target(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace the egress check: https passes, anything else is refused."""

    async def _check(url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise TargetNotAllowed("not_https")

    monkeypatch.setattr(agent_services, "check_agent_target_url", _check)


async def _capture(coro: Any) -> tuple[int, dict[str, Any]]:
    try:
        response = await coro
    except AgentApiError as exc:
        return exc.status_code, exc.body
    assert response is not None, "the handler returned no response"
    assert isinstance(response, JSONResponse), type(response)
    return response.status_code, json.loads(response.body)


async def _create(
    session: _FakeSession,
    payload: Any,
    *,
    raw: bool = False,
) -> tuple[int, dict[str, Any]]:
    request = _request(payload) if raw else _json_request(payload)
    return await _capture(
        agent_services.create_agent_service(
            request=request,
            principal=_principal(),
            session=session,
        )
    )


async def _patch(
    session: _FakeSession,
    payload: Any,
    *,
    service_ref: str = "my-service",
) -> tuple[int, dict[str, Any]]:
    return await _capture(
        agent_services._update_agent_service(
            service_ref=service_ref,
            request=_json_request(payload),
            principal=_principal(),
            session=session,
        )
    )


# ---------------------------------------------------------------------------
# C-00b5d763 — one body shape
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-00b5d763")
@pytest.mark.asyncio
async def test_C_00b5d763_every_refusal_has_one_exact_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_target(monkeypatch)

    validation = {
        "code": "mintkey:validation_failed",
        "title": "Invalid request body",
    }
    answers: list[tuple[int, dict[str, Any]]] = []

    # Create refusals.
    answers.append(
        await _create(
            _FakeSession(),
            {
                "name": "My Service",
                "base_url": "https://api.example.com",
                "auth_scheme": "ssh_private_key",
            },
        )
    )
    answers.append(
        await _create(
            _FakeSession(),
            {
                "name": "../x",
                "base_url": "https://api.example.com",
                "auth_scheme": "bearer_token",
            },
        )
    )
    answers.append(await _create(_FakeSession(), [1]))
    answers.append(await _create(_FakeSession(), b"{", raw=True))
    answers.append(
        await _create(
            _FakeSession(),
            {
                "name": "My Service",
                "base_url": "http://example.com",
                "auth_scheme": "bearer_token",
            },
        )
    )
    answers.append(
        await _create(
            _FakeSession(slug_taken=True),
            {
                "name": "My Service",
                "base_url": "https://api.example.com",
                "auth_scheme": "bearer_token",
            },
        )
    )

    # Patch refusals (red until the PATCH route exists).
    answers.append(
        await _patch(
            _FakeSession(service_row=_service_row(owner=OTHER_AGENT_ID)),
            {"display_name": "Renamed"},
        )
    )
    answers.append(
        await _patch(
            _FakeSession(service_row=None),
            {"display_name": "Renamed"},
            service_ref="unknown-slug",
        )
    )
    answers.append(
        await _patch(
            _FakeSession(service_row=_service_row()),
            {
                "display_name": "Renamed",
                "owner_agent_id": db_uuid_to_wire(AGENT_ID, "agent"),
            },
        )
    )

    expected = [
        (422, {**validation, "field": "auth_scheme"}),
        (422, {**validation, "field": "name"}),
        (422, {**validation, "field": None}),
        (422, {**validation, "field": None}),
        (
            400,
            {
                "code": "mintkey:target_not_allowed",
                "title": "Target not allowed",
                "field": "base_url",
                "reason": "not_https",
            },
        ),
        (
            409,
            {
                "code": "mintkey:slug_conflict",
                "title": "Service name already in use",
            },
        ),
        (
            403,
            {
                "code": "mintkey:not_owner",
                "title": "Not the owner of this service",
            },
        ),
        (
            404,
            {"code": "mintkey:not_found", "title": "Service not found"},
        ),
        (422, {**validation, "field": None}),
    ]

    assert len(answers) == len(expected)
    for (status, body), (expected_status, expected_body) in zip(
        answers, expected, strict=True
    ):
        assert status == expected_status, body
        assert body == expected_body
        assert "mintkey:code" not in body

    answer_text = " ".join(json.dumps(body) for _status, body in answers)
    assert "ssh_private_key" not in answer_text
    assert "../x" not in answer_text
    assert "http://example.com" not in answer_text
    assert "owner_agent_id" not in answer_text
