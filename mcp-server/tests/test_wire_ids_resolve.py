"""
Unit tests for resolve_service_id — OPS-LL.

Covers:
  1. Raw UUID (form 1) — resolves without a DB call.
  2. svc_ wire form (form 2) — decodes to UUID without a DB call.
  3. Slug (form 3) — looks up in DB and resolves.
  4. Unknown slug → ServiceNotFound (0 rows).
  5. Invalid svc_ wire form → ServiceNotFound.

Source: OPS-LL; ADR-0017.11.
"""
from __future__ import annotations

import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SERVICE_UUID = "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd"
_TENANT_UUID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"


def _make_session_with_slug_result(service_uuid: str | None, *, row_count: int = 1):
    """
    Build a mock AsyncSession whose execute() returns a result set.

    If service_uuid is None, returns zero rows (simulates slug not found).
    row_count > 1 simulates ambiguous slug (should not happen, but guard tested).
    """
    session = AsyncMock()
    result_mock = MagicMock()

    if service_uuid is None or row_count == 0:
        result_mock.fetchall.return_value = []
    else:
        rows = []
        for _ in range(row_count):
            row = MagicMock()
            row.id = service_uuid
            rows.append(row)
        result_mock.fetchall.return_value = rows

    session.execute = AsyncMock(return_value=result_mock)
    return session


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_resolve_raw_uuid_form() -> None:
    """
    Form 1: a raw 36-char UUID with dashes is returned as uuid.UUID without
    touching the DB session.

    Source: OPS-LL resolution order §1.
    """
    from mcp_server.utils.wire_ids import resolve_service_id

    session = AsyncMock()
    result = _run(resolve_service_id(_SERVICE_UUID, _TENANT_UUID, session))

    assert isinstance(result, uuid.UUID)
    assert str(result) == _SERVICE_UUID
    # DB should NOT be called for raw UUID
    session.execute.assert_not_called()


def test_resolve_svc_wire_form() -> None:
    """
    Form 2: a svc_ Crockford wire form decodes to the correct UUID without
    touching the DB session.

    Source: OPS-LL resolution order §2.
    """
    from mcp_server.utils.wire_ids import db_uuid_to_wire, resolve_service_id

    wire_id = db_uuid_to_wire(_SERVICE_UUID, "svc")
    session = AsyncMock()
    result = _run(resolve_service_id(wire_id, _TENANT_UUID, session))

    assert isinstance(result, uuid.UUID)
    assert str(result) == _SERVICE_UUID
    session.execute.assert_not_called()


def test_resolve_slug_form_hits_db() -> None:
    """
    Form 3: a slug string triggers a DB lookup scoped to the tenant and
    returns the matching UUID.

    Source: OPS-LL resolution order §3.
    """
    from mcp_server.utils.wire_ids import resolve_service_id

    session = _make_session_with_slug_result(_SERVICE_UUID)
    result = _run(resolve_service_id("github", _TENANT_UUID, session))

    assert isinstance(result, uuid.UUID)
    assert str(result) == _SERVICE_UUID
    # DB was called once (the slug lookup)
    session.execute.assert_called_once()
    # The SQL call must have passed the tenant_id in the parameters
    call_kwargs = session.execute.call_args
    params = call_kwargs[0][1] if len(call_kwargs[0]) > 1 else call_kwargs[1].get("params", {})
    # params is the second positional arg
    _, bound_params = session.execute.call_args[0]
    assert bound_params["tid"] == str(_TENANT_UUID)
    assert bound_params["slug"] == "github"


def test_resolve_unknown_slug_raises_service_not_found() -> None:
    """
    Form 3: an unknown slug (0 rows) raises ServiceNotFound.

    Source: OPS-LL; error-shape requirement.
    """
    from mcp_server.utils.wire_ids import ServiceNotFound, resolve_service_id

    session = _make_session_with_slug_result(None)
    with pytest.raises(ServiceNotFound) as exc_info:
        _run(resolve_service_id("nonexistent-slug", _TENANT_UUID, session))

    err = exc_info.value
    assert err.service_id_input == "nonexistent-slug"
    assert err.reason == "service_not_found"


def test_resolve_invalid_svc_wire_form_raises_service_not_found() -> None:
    """
    Form 2: a string that starts with 'svc_' but is malformed (not a valid
    Crockford ULID) raises ServiceNotFound, not a bare ValueError.

    Agents should receive a proper 404, not a 500.

    Source: OPS-LL error handling.
    """
    from mcp_server.utils.wire_ids import ServiceNotFound, resolve_service_id

    session = AsyncMock()
    with pytest.raises(ServiceNotFound) as exc_info:
        _run(resolve_service_id("svc_INVALIDBADDATA!!!!!", _TENANT_UUID, session))

    assert exc_info.value.service_id_input == "svc_INVALIDBADDATA!!!!!"
    session.execute.assert_not_called()


def test_resolve_slug_ambiguous_raises_service_not_found() -> None:
    """
    Form 3: >1 row returned (should never happen with DB unique constraint,
    but defensive guard) raises ServiceNotFound with reason 'ambiguous_slug'.

    Source: OPS-LL defensive guard.
    """
    from mcp_server.utils.wire_ids import ServiceNotFound, resolve_service_id

    session = _make_session_with_slug_result(_SERVICE_UUID, row_count=2)
    with pytest.raises(ServiceNotFound) as exc_info:
        _run(resolve_service_id("github", _TENANT_UUID, session))

    assert exc_info.value.reason == "ambiguous_slug"
