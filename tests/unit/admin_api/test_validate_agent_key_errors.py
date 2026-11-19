"""
Unit tests for admin_api.api.internal.validate_agent_key error handling.

Requirement: agent-key-auth › admin-api answers 503 when the verify fails for
a reason other than the key.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import argon2.exceptions
import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi.responses import JSONResponse

from admin_api.api import internal

# Built at run time so no test file holds a token-shaped value whole.
API_KEY = "mk_" + "agent_" + "A" * 24
LOGGER_NAME = "admin_api.api.internal"


def _active_agent_row() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.UUID("00000000-0000-0000-0000-000000000022"),
        tenant_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        api_key_hash="$argon2id$v=19$m=65536,t=3,p=4$c2FsdA$aGFzaA",
        status="active",
        api_key_expires_at=None,
        api_key_fingerprint="deadbeefdeadbeef",
    )


def _fake_session(row: SimpleNamespace | None) -> MagicMock:
    session = MagicMock()
    result = MagicMock()
    result.fetchone.return_value = row
    session.execute = AsyncMock(side_effect=[MagicMock(), result])
    return session


def _raise_with(exc: BaseException):
    async def _raiser(_stored_hash: str, _secret: str) -> None:
        raise exc

    return _raiser


@pytest.mark.asyncio
@pytest.mark.l4("C-b6439852")
async def test_C_b6439852_unexpected_verify_error_answers_503(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = _fake_session(_active_agent_row())
    monkeypatch.setattr(internal, "_verify_argon2", _raise_with(MemoryError()))
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)

    response = await internal.validate_agent_key(
        internal.ValidateAgentKeyRequest(api_key=API_KEY), session
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    assert response.body == b'{"mintkey:code":"mintkey:verify_unavailable"}'
    warnings = [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and record.levelno == logging.WARNING
    ]
    assert len(warnings) == 1
    assert warnings[0].getMessage() == "validate-agent-key: verify failed (MemoryError)"
    assert API_KEY not in warnings[0].getMessage()


@pytest.mark.asyncio
@pytest.mark.l4("C-51ef8acf")
async def test_C_51ef8acf_verify_mismatch_is_still_401(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = _fake_session(_active_agent_row())
    exc = argon2.exceptions.VerifyMismatchError()
    monkeypatch.setattr(internal, "_verify_argon2", _raise_with(exc))
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)

    response = await internal.validate_agent_key(
        internal.ValidateAgentKeyRequest(api_key=API_KEY), session
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 401
    assert response.body == JSONResponse(
        status_code=401, content=internal.INVALID_KEY_RESPONSE
    ).body
    assert not [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and record.levelno == logging.WARNING
    ]


@pytest.mark.asyncio
@pytest.mark.l4("C-60c778ab")
async def test_C_60c778ab_invalid_stored_hash_is_still_401(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = _fake_session(_active_agent_row())
    exc = argon2.exceptions.InvalidHashError()
    monkeypatch.setattr(internal, "_verify_argon2", _raise_with(exc))
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)

    response = await internal.validate_agent_key(
        internal.ValidateAgentKeyRequest(api_key=API_KEY), session
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 401
    assert response.body == JSONResponse(
        status_code=401, content=internal.INVALID_KEY_RESPONSE
    ).body
    assert not [
        record
        for record in caplog.records
        if record.name == LOGGER_NAME and record.levelno == logging.WARNING
    ]


@pytest.mark.asyncio
@pytest.mark.l4("C-f73110db")
async def test_C_f73110db_unknown_key_stays_401_when_dummy_verify_raises(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    session = _fake_session(None)
    monkeypatch.setattr(internal, "_verify_argon2", _raise_with(MemoryError()))
    caplog.set_level(logging.WARNING, logger=LOGGER_NAME)

    response = await internal.validate_agent_key(
        internal.ValidateAgentKeyRequest(api_key=API_KEY), session
    )

    assert isinstance(response, JSONResponse)
    assert response.status_code == 401
    assert response.body == JSONResponse(
        status_code=401, content=internal.INVALID_KEY_RESPONSE
    ).body


@pytest.mark.asyncio
@pytest.mark.l4("C-55531051")
async def test_C_55531051_cancelled_verify_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = _fake_session(_active_agent_row())
    monkeypatch.setattr(internal, "_verify_argon2", _raise_with(asyncio.CancelledError()))

    with pytest.raises(asyncio.CancelledError):
        await internal.validate_agent_key(
            internal.ValidateAgentKeyRequest(api_key=API_KEY), session
        )
