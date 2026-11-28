"""Unit tests: the owned-service lookup is one function.

Task 1.1 of agent-service-routes. The three scenarios of the requirement
"The owned service lookup is one function" decide:

  1. ``parse_service_ref`` turns an ``svc_`` id (canonical or 32-hex) into a
     dashed UUID and anything else into a slug, refusing an id it cannot
     decode with the 404 of the agent error table;
  2. ``require_owned_service`` selects the service pinned to the principal's
     tenant and refuses a service it does not own with 403, one that is not
     there with 404 — locking the row only when asked;
  3. ``service_view`` answers the twelve keys, with an ``svc_`` id, ISO
     timestamps or null, and a boolean credential flag.

Sources:
  - `openspec/changes/agent-service-routes/spec.md` — The owned service lookup
    is one function; Every error of the service routes has one body
  - `openspec/changes/agent-service-routes/design.md` — D2, D5, D10
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
MODELS_SRC = REPO_ROOT / "packages" / "python" / "mintkey-models"
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from admin_api.auth.agent_principal import AgentApiError, AgentPrincipal  # noqa: E402
from admin_api.services.agent_publishing import (  # noqa: E402
    parse_service_ref,
    require_owned_service,
    service_view,
)
from admin_api.utils.wire_ids import db_uuid_to_wire  # noqa: E402

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")
OTHER_AGENT_ID = UUID("00000000-0000-0000-0000-000000000023")
SERVICE_ID = UUID("00000000-0000-0000-0000-0000000000ab")

NOT_FOUND_BODY: dict[str, Any] = {
    "code": "mintkey:not_found",
    "title": "Service not found",
}
NOT_OWNER_BODY: dict[str, Any] = {
    "code": "mintkey:not_owner",
    "title": "Not the owner of this service",
}

VIEW_KEYS = {
    "id",
    "name",
    "slug",
    "display_name",
    "description",
    "base_url",
    "auth_scheme",
    "openapi_url",
    "status",
    "credential_set",
    "created_at",
    "updated_at",
}


class _Result:
    """The slice of a SQLAlchemy result the lookup uses."""

    def __init__(self, row: Any | None) -> None:
        self._row = row

    def fetchone(self) -> Any | None:
        return self._row

    def fetchall(self) -> list[Any]:
        return [] if self._row is None else [self._row]


class _RecordingSession:
    """Record every statement and answer the service read with one row or none."""

    def __init__(self, row: Any | None) -> None:
        self.row = row
        self.statements: list[tuple[str, Any]] = []

    async def execute(
        self, statement: Any, params: Any = None, **kwargs: Any
    ) -> _Result:
        self.statements.append((" ".join(str(statement).split()), params))
        return _Result(self.row)


def _principal() -> AgentPrincipal:
    return AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="publisher")


def _service_row(
    *,
    owner: UUID | None = AGENT_ID,
    credential_set: bool = True,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=SERVICE_ID,
        tenant_id=TENANT_ID,
        name="My service",
        slug="my-svc",
        display_name="My service",
        description=None,
        base_url="https://api.example.com",
        auth_scheme="bearer_token",
        openapi_url=None,
        status="active",
        owner_agent_id=owner,
        created_by_agent_id=AGENT_ID,
        credential_set=credential_set,
    )


def _param_values(params: Any) -> list[Any]:
    """Flatten the values a fake statement was bound with."""
    if params is None:
        return []
    if isinstance(params, dict):
        return list(params.values())
    if isinstance(params, (list, tuple)):
        return list(params)
    return [params]


def _binds_tenant(session: _RecordingSession) -> bool:
    """True when every statement bound the principal's tenant value."""
    if not session.statements:
        return False
    for _sql, params in session.statements:
        values = _param_values(params)
        if TENANT_ID not in values and str(TENANT_ID) not in values:
            return False
    return True


def _has_for_update(session: _RecordingSession) -> bool:
    return any("FOR UPDATE" in sql.upper() for sql, _params in session.statements)


async def _refusal(
    session: _RecordingSession, service_ref: str
) -> AgentApiError:
    with pytest.raises(AgentApiError) as caught:
        await require_owned_service(session, _principal(), service_ref)
    return caught.value


def _assert_refusal_statements(session: _RecordingSession) -> None:
    assert _binds_tenant(session)
    assert not _has_for_update(session)


# ---------------------------------------------------------------------------
# C-b64100a4 — references
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-b64100a4")
def test_C_b64100a4_parse_service_ref_decodes_ids_and_passes_slugs() -> None:
    canonical = db_uuid_to_wire(SERVICE_ID, "svc")
    dashed = str(SERVICE_ID)

    assert parse_service_ref(canonical) == ("id", dashed)
    assert parse_service_ref("svc_" + SERVICE_ID.hex) == ("id", dashed)

    with pytest.raises(AgentApiError) as caught:
        parse_service_ref("svc_xyz")
    assert caught.value.status_code == 404
    assert caught.value.body == NOT_FOUND_BODY

    assert parse_service_ref("my-svc.v2") == ("slug", "my-svc.v2")
    assert parse_service_ref("") == ("slug", "")


# ---------------------------------------------------------------------------
# C-404b5f68 — ownership
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-404b5f68")
@pytest.mark.asyncio
async def test_C_404b5f68_require_owned_service_returns_owned_and_refuses_others() -> None:
    by_id_row = _service_row()
    by_id_session = _RecordingSession(by_id_row)
    assert (
        await require_owned_service(
            by_id_session, _principal(), db_uuid_to_wire(SERVICE_ID, "svc")
        )
        is by_id_row
    )
    assert _binds_tenant(by_id_session)
    assert not _has_for_update(by_id_session)

    by_slug_row = _service_row()
    by_slug_session = _RecordingSession(by_slug_row)
    assert (
        await require_owned_service(by_slug_session, _principal(), "my-svc")
        is by_slug_row
    )
    assert _binds_tenant(by_slug_session)
    assert not _has_for_update(by_slug_session)

    other_owner_session = _RecordingSession(_service_row(owner=OTHER_AGENT_ID))
    other_owner = await _refusal(other_owner_session, "my-svc")
    assert other_owner.status_code == 403
    assert other_owner.body == NOT_OWNER_BODY
    _assert_refusal_statements(other_owner_session)

    no_owner_session = _RecordingSession(_service_row(owner=None))
    no_owner = await _refusal(no_owner_session, "my-svc")
    assert no_owner.status_code == 403
    assert no_owner.body == NOT_OWNER_BODY
    _assert_refusal_statements(no_owner_session)

    other_tenant_session = _RecordingSession(None)
    other_tenant = await _refusal(other_tenant_session, "my-svc")
    assert other_tenant.status_code == 404
    assert other_tenant.body == NOT_FOUND_BODY
    _assert_refusal_statements(other_tenant_session)

    unknown_session = _RecordingSession(None)
    unknown = await _refusal(unknown_session, "unknown-slug")
    assert unknown.status_code == 404
    assert unknown.body == NOT_FOUND_BODY
    _assert_refusal_statements(unknown_session)

    locked_row = _service_row()
    locked_session = _RecordingSession(locked_row)
    assert (
        await require_owned_service(
            locked_session, _principal(), "my-svc", for_update=True
        )
        is locked_row
    )
    assert _binds_tenant(locked_session)
    assert _has_for_update(locked_session)


# ---------------------------------------------------------------------------
# C-7d79dfe4 — the view
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-7d79dfe4")
def test_C_7d79dfe4_service_view_has_twelve_keys_and_nullable_timestamps() -> None:
    created_at = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc)
    updated_at = created_at.replace(minute=6)
    row = _service_row(credential_set=True)
    row.created_at = created_at
    row.updated_at = updated_at

    view = service_view(row)

    assert set(view) == VIEW_KEYS
    assert view["id"].startswith("svc_")
    assert view["id"] == db_uuid_to_wire(SERVICE_ID, "svc")
    assert view["credential_set"] is True
    assert view["created_at"] == created_at.isoformat()
    assert view["updated_at"] == updated_at.isoformat()

    no_timestamps = _service_row(credential_set=False)
    no_timestamps.created_at = None
    no_timestamps.updated_at = None

    bare = service_view(no_timestamps)

    assert set(bare) == VIEW_KEYS
    assert bare["created_at"] is None
    assert bare["updated_at"] is None
    assert bare["credential_set"] is False
