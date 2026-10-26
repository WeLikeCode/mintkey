"""
Unit tests: admin-api's change notifications carry event_type.

Requirement: proxy-token-revocation › admin-api's change notifications carry
event_type.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for p in (ADMIN_API_SRC, MODELS_SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

from admin_api.api import agents, api_keys
from admin_api.api.api_keys import RevokeRequest
from admin_api.changes import publisher

T = "11111111-2222-3333-4444-555555555555"
A = "agent_3C7JAGMBGR9EMRS2AVGXDHQXDX"


class RecordingSession:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object] | None]] = []
        self._result = MagicMock()
        self._result.fetchone.return_value = SimpleNamespace(
            id="00000000-0000-0000-0000-0000000000aa",
            cnt=0,
            key_fingerprint="abcd1234",
            service_id=None,
            revoked_at=None,
        )

    async def execute(self, stmt: object, params: dict[str, object] | None = None) -> MagicMock:
        self.calls.append((str(stmt), params))
        return self._result


def published(session: RecordingSession) -> list[tuple[str, object]]:
    out: list[tuple[str, object]] = []
    for _stmt, params in session.calls:
        if params is not None and "channel" in params:
            out.append((params["channel"], json.loads(params["payload"])))
    return out


@pytest.mark.l4("C-668cad91")
def test_C_668cad91_notify_change_adds_event_type_and_keeps_the_rest() -> None:
    first = {"event": "token.revoked", "tenant_id": T, "jti": "jti_01REVOKED"}
    second = {
        "event": "credential.rotated",
        "tenant_id": T,
        "service_id": "svc_5ANANANANANANANANANANANANA",
        "credential_id": "cred_x",
    }
    third = {"event_type": "budget.config_updated", "target_id": "perm_x"}
    copies = [dict(first), dict(second), dict(third)]

    session = RecordingSession()
    asyncio.run(publisher.notify_change(session, "mintkey:agent", first))
    asyncio.run(publisher.notify_change(session, "mintkey:credential", second))
    asyncio.run(publisher.notify_change(session, "mintkey:agent", third))

    assert published(session) == [
        (
            "mintkey:agent",
            {
                "event": "token.revoked",
                "event_type": "token.revoked",
                "tenant_id": T,
                "jti": "jti_01REVOKED",
            },
        ),
        (
            "mintkey:credential",
            {
                "event": "credential.rotated",
                "event_type": "credential.rotated",
                "tenant_id": T,
                "service_id": "svc_5ANANANANANANANANANANANANA",
                "credential_id": "cred_x",
            },
        ),
        ("mintkey:agent", {"event_type": "budget.config_updated", "target_id": "perm_x"}),
    ]
    assert [first, second, third] == copies


@pytest.mark.l4("C-dd48286f")
def test_C_dd48286f_agent_revocation_publishers_carry_event_type() -> None:
    expected = (
        "mintkey:agent",
        {
            "event": "agent.revoked",
            "event_type": "agent.revoked",
            "tenant_id": T,
            "agent_id": A,
        },
    )
    for revoke in (agents.revoke_agent, agents.delete_agent):
        session = RecordingSession()
        with (
            patch("admin_api.api.agents.set_tenant_context", new=AsyncMock()),
            patch("admin_api.api.agents.audit_emit", new=AsyncMock()),
        ):
            asyncio.run(revoke(tenant_id=UUID(T), agent_id=A, session=session, _authz=None))
        assert published(session) == [expected]


@pytest.mark.l4("C-af7468de")
def test_C_af7468de_api_key_revocation_publisher_carries_event_type() -> None:
    session = RecordingSession()
    with (
        patch("admin_api.api.api_keys.set_tenant_context", new=AsyncMock()),
        patch("admin_api.api.api_keys.audit_emit", new=AsyncMock()),
    ):
        asyncio.run(
            api_keys.revoke_api_key(
                tenant_id=UUID(T),
                agent_id=A,
                api_key_id="svckey_x",
                body=RevokeRequest(reason="test"),
                session=session,
                _authz=None,
            )
        )
    assert published(session) == [
        (
            "mintkey:agent",
            {
                "event": "api_key.revoked",
                "event_type": "api_key.revoked",
                "tenant_id": T,
                "api_key_id": "svckey_x",
                "key_fingerprint": "abcd1234",
                "reason": "test",
            },
        )
    ]
