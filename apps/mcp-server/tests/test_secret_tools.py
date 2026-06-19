"""
Unit tests for MCP agent secret tools (ADR-0025).

Tests secret_put, secret_get, secret_list, secret_delete — each with mocked
DB, vault gRPC client, and agent context.

Follows the test_email_tools.py pattern: asyncio.run, create_app,
dependency_overrides on get_agent_context + get_db_session, mock vault client.

Key invariants asserted:
  - Anti-enumeration: non-owned == nonexistent response (EQUALITY check).
  - Oversized value rejected (>65536 bytes).
  - Unauthenticated calls return 401.
  - owner/shared distinction in list and get responses.
  - Idempotent delete.
  - Audit payload contains no plaintext value.

Source: ADR-0025; spec agent-secret-storage; design.md D3, D6, D9.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

# ---------------------------------------------------------------------------
# Test constants
# ---------------------------------------------------------------------------

_AGENT_A_ID = str(uuid.uuid4())
_AGENT_B_ID = str(uuid.uuid4())
_TENANT_ID = str(uuid.uuid4())

# A known sec_ wire ID for a "real" secret owned by agent A
_SECRET_UUID = str(uuid.uuid4())
# Build wire form: since we can't run db_uuid_to_wire in test setup easily,
# we use a canonical wire ID format from a fixed UUID.
# We'll mock the DB to return rows with .id = _SECRET_UUID.
_SECRET_WIRE = "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1"  # placeholder — we'll decode in tests

_GRANT_AGENT_UUID = str(uuid.uuid4())

_PLAINTEXT = b"sup3rs3cr3t"


# ---------------------------------------------------------------------------
# Helpers — fake DB session
# ---------------------------------------------------------------------------

def _make_row(**kwargs):
    """Create a MagicMock that has dot-attribute access for columns."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    return row


# ---------------------------------------------------------------------------
# App builder
# ---------------------------------------------------------------------------

def _build_secret_app(
    *,
    agent_id: str = _AGENT_A_ID,
    secret_exists: bool = True,
    secret_owned_by_caller: bool = True,
    grant_exists: bool = False,
    existing_version: int | None = None,
    list_rows: list | None = None,
    vault_plaintext: bytes | None = _PLAINTEXT,
):
    """
    Build a FastAPI app with mocked agent context + DB session for secret tools.

    DB mock rules:
      - params with "stid" + "sagent" + "sname" → owner lookup for secret_put
      - params with "cagent"/"dagent" + "gsecret"/"dsecret" → visibility/ownership for get/delete
      - params with "lagent" → list query
      - all other queries (set_tenant_context) → empty result
    """
    import mcp_server.main as _main_mod
    from mcp_server.db.session import get_db_session
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _fake_agent_context():
        return {"agent_id": agent_id, "tenant_id": _TENANT_ID}

    app.dependency_overrides[get_agent_context] = _fake_agent_context

    async def _fake_db_session() -> AsyncGenerator:
        session = AsyncMock()
        audit_calls: list = []

        async def _execute(stmt, params=None, **kw):
            result = MagicMock()
            result.fetchone = MagicMock(return_value=None)
            result.fetchall = MagicMock(return_value=[])
            p = params or {}

            stmt_str = str(stmt)

            # secret_put: check existing row — has stid + sagent + sname
            if "stid" in p and "sagent" in p and "sname" in p:
                if existing_version is not None and secret_exists:
                    row = _make_row(id=_SECRET_UUID, version=existing_version)
                    result.fetchone.return_value = row
                else:
                    result.fetchone.return_value = None

            # secret_get: visibility query — has cagent + gsecret + gtid
            elif "cagent" in p and "gsecret" in p:
                if secret_exists:
                    if secret_owned_by_caller:
                        row = _make_row(
                            id=_SECRET_UUID,
                            name="db-password",
                            version=1,
                            content_type="text/plain",
                            access="owner",
                        )
                        result.fetchone.return_value = row
                    elif grant_exists:
                        row = _make_row(
                            id=_SECRET_UUID,
                            name="db-password",
                            version=1,
                            content_type=None,
                            access="shared",
                        )
                        result.fetchone.return_value = row
                    else:
                        result.fetchone.return_value = None
                else:
                    result.fetchone.return_value = None

            # secret_delete: ownership check — has dsecret + dtid + dagent
            elif "dsecret" in p and "dagent" in p:
                if secret_exists and secret_owned_by_caller:
                    row = _make_row(id=_SECRET_UUID, name="db-password")
                    result.fetchone.return_value = row
                else:
                    result.fetchone.return_value = None

            # secret_list: union query — has lagent + ltid
            elif "lagent" in p:
                rows = list_rows if list_rows is not None else []
                result.fetchall = MagicMock(return_value=rows)

            # audit_emit: pg_advisory_xact_lock and chain head queries
            elif "lock_id" in p:
                result.fetchone.return_value = None
            elif "tid" in p and "FOR UPDATE" in stmt_str:
                result.fetchone.return_value = None

            return result

        session.execute = _execute
        session.commit = AsyncMock()
        yield session

    app.dependency_overrides[get_db_session] = _fake_db_session
    return app


def _run(coro):
    """Run an async coroutine in a new event loop (test helper)."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Vault client mock helper
# ---------------------------------------------------------------------------

def _mock_vault_put():
    """Patch vault put to return success."""
    return patch(
        "mcp_server.tools.secret_put.get_agent_secrets_vault_client",
        new=AsyncMock(return_value=AsyncMock(
            put_agent_secret=AsyncMock(return_value={"kek_version": 1}),
        )),
    )


def _mock_vault_get(plaintext: bytes | None = _PLAINTEXT):
    """Patch vault get to return plaintext (or None)."""
    return patch(
        "mcp_server.tools.secret_get.get_agent_secrets_vault_client",
        new=AsyncMock(return_value=AsyncMock(
            get_agent_secret=AsyncMock(return_value=plaintext),
        )),
    )


def _mock_vault_delete():
    """Patch vault delete to return True."""
    return patch(
        "mcp_server.tools.secret_delete.get_agent_secrets_vault_client",
        new=AsyncMock(return_value=AsyncMock(
            delete_agent_secret=AsyncMock(return_value=True),
        )),
    )


# ---------------------------------------------------------------------------
# secret_put tests
# ---------------------------------------------------------------------------

def test_secret_put_create_returns_200_version_1():
    """secret_put creates a new secret (first store, version=1)."""
    app = _build_secret_app(secret_exists=False)
    with _mock_vault_put():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/secret_put",
                    json={"name": "db-password", "value": "s3cr3t"},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["name"] == "db-password"
    assert data["version"] == 1
    assert data["secret_id"].startswith("sec_")


def test_secret_put_overwrite_increments_version():
    """secret_put on existing name increments version."""
    app = _build_secret_app(secret_exists=True, existing_version=3)
    with _mock_vault_put():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/secret_put",
                    json={"name": "db-password", "value": "new-value"},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    assert resp.json()["version"] == 4


def test_secret_put_oversized_value_rejected():
    """secret_put rejects value > 65536 bytes."""
    app = _build_secret_app()
    big_value = "x" * 65537
    with _mock_vault_put():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/secret_put",
                    json={"name": "big", "value": big_value},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 422
    assert "invalid_argument" in resp.json()["code"]


def test_secret_put_invalid_name_rejected():
    """secret_put rejects names with invalid characters."""
    app = _build_secret_app()
    with _mock_vault_put():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.post(
                    "/v1/tools/secret_put",
                    json={"name": "bad name with spaces!", "value": "x"},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 422


def test_secret_put_unauthenticated_returns_401():
    """secret_put returns 401 when agent_ctx is None."""
    import mcp_server.main as _main_mod
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _no_ctx():
        return None

    app.dependency_overrides[get_agent_context] = _no_ctx

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.post(
                "/v1/tools/secret_put",
                json={"name": "x", "value": "y"},
            )

    resp = _run(_inner())
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# secret_get tests
# ---------------------------------------------------------------------------

def test_secret_get_owner_success():
    """secret_get returns plaintext for the owning agent."""
    app = _build_secret_app(secret_owned_by_caller=True)
    with _mock_vault_get(_PLAINTEXT):
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    "/v1/tools/secret_get",
                    params={"secret_id": "sec_" + "A" * 26},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["value"] == _PLAINTEXT.decode()
    assert data["access"] == "owner"
    assert data["name"] == "db-password"
    assert data["version"] == 1


def test_secret_get_shared_returns_access_shared():
    """secret_get returns access=shared for a grant holder."""
    app = _build_secret_app(
        agent_id=_AGENT_B_ID,
        secret_owned_by_caller=False,
        grant_exists=True,
    )
    with _mock_vault_get(_PLAINTEXT):
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    "/v1/tools/secret_get",
                    params={"secret_id": "sec_" + "A" * 26},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    assert resp.json()["access"] == "shared"


def test_secret_get_nonexistent_returns_404_secret_not_found():
    """secret_get returns 404 secret_not_found for a nonexistent secret."""
    app = _build_secret_app(secret_exists=False)
    with _mock_vault_get(None):
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    "/v1/tools/secret_get",
                    params={"secret_id": "sec_" + "B" * 26},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 404
    assert resp.json()["code"] == "mintkey:secret_not_found"


def test_secret_get_anti_enumeration_not_owned_equals_nonexistent():
    """
    Anti-enumeration: not-owned secret and nonexistent secret return
    IDENTICAL status code and code field.
    """
    # Case A: secret exists but agent is not owner and has no grant
    app_not_owned = _build_secret_app(
        agent_id=_AGENT_B_ID,
        secret_exists=True,
        secret_owned_by_caller=False,
        grant_exists=False,
    )
    # Case B: secret genuinely does not exist
    app_missing = _build_secret_app(secret_exists=False)

    async def _get(app):
        with patch(
            "mcp_server.tools.secret_get.get_agent_secrets_vault_client",
            new=AsyncMock(return_value=AsyncMock(
                get_agent_secret=AsyncMock(return_value=None),
            )),
        ):
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.get(
                    "/v1/tools/secret_get",
                    params={"secret_id": "sec_" + "C" * 26},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    resp_not_owned = _run(_get(app_not_owned))
    resp_missing = _run(_get(app_missing))

    # EQUALITY assertion — status and code must be identical
    assert resp_not_owned.status_code == resp_missing.status_code, (
        f"Status mismatch: not_owned={resp_not_owned.status_code} "
        f"vs missing={resp_missing.status_code}"
    )
    assert resp_not_owned.json()["code"] == resp_missing.json()["code"], (
        f"Code mismatch: not_owned={resp_not_owned.json()} "
        f"vs missing={resp_missing.json()}"
    )


def test_secret_get_unauthenticated_returns_401():
    """secret_get returns 401 when agent_ctx is None."""
    import mcp_server.main as _main_mod
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _no_ctx():
        return None

    app.dependency_overrides[get_agent_context] = _no_ctx

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(
                "/v1/tools/secret_get",
                params={"secret_id": "sec_" + "A" * 26},
            )

    resp = _run(_inner())
    assert resp.status_code == 401


def test_secret_get_audit_payload_contains_no_value():
    """
    Audit payload from secret_get must not contain the plaintext value.
    We capture the audit_emit call and inspect its payload argument.
    """
    app = _build_secret_app(secret_owned_by_caller=True)
    captured_payloads: list = []

    original_emit = None

    async def _capturing_audit_emit(**kwargs):
        captured_payloads.append(kwargs.get("payload", {}))

    with _mock_vault_get(_PLAINTEXT):
        with patch("mcp_server.tools.secret_get.audit_emit", side_effect=_capturing_audit_emit):
            async def _inner():
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.get(
                        "/v1/tools/secret_get",
                        params={"secret_id": "sec_" + "A" * 26},
                        headers={"Authorization": "Bearer mk_agent_test"},
                    )
            resp = _run(_inner())

    assert resp.status_code == 200
    # Every audit payload emitted must NOT contain the plaintext value
    for p in captured_payloads:
        payload_str = str(p)
        assert _PLAINTEXT.decode() not in payload_str, (
            f"Plaintext leaked into audit payload: {payload_str}"
        )
        assert "value" not in p, f"Audit payload has 'value' key: {p}"


# ---------------------------------------------------------------------------
# secret_list tests
# ---------------------------------------------------------------------------

def test_secret_list_returns_owned_and_shared():
    """secret_list returns owned + shared secrets with correct access markers."""
    import datetime

    owned_row = _make_row(
        id=str(uuid.uuid4()),
        name="owned-secret",
        version=2,
        size_bytes=10,
        content_type="text/plain",
        access="owner",
        created_at=datetime.datetime(2026, 1, 1),
        updated_at=datetime.datetime(2026, 1, 2),
    )
    shared_row = _make_row(
        id=str(uuid.uuid4()),
        name="shared-secret",
        version=1,
        size_bytes=5,
        content_type=None,
        access="shared",
        created_at=datetime.datetime(2026, 1, 3),
        updated_at=datetime.datetime(2026, 1, 3),
    )

    app = _build_secret_app(list_rows=[owned_row, shared_row])

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(
                "/v1/tools/secret_list",
                headers={"Authorization": "Bearer mk_agent_test"},
            )

    resp = _run(_inner())
    assert resp.status_code == 200, resp.text
    data = resp.json()
    secrets = data["secrets"]
    assert len(secrets) == 2
    accesses = {s["access"] for s in secrets}
    assert "owner" in accesses
    assert "shared" in accesses
    # No values in list response
    for s in secrets:
        assert "value" not in s


def test_secret_list_no_values_in_response():
    """secret_list never includes value field."""
    import datetime

    row = _make_row(
        id=str(uuid.uuid4()),
        name="my-secret",
        version=1,
        size_bytes=7,
        content_type=None,
        access="owner",
        created_at=datetime.datetime(2026, 1, 1),
        updated_at=datetime.datetime(2026, 1, 1),
    )
    app = _build_secret_app(list_rows=[row])

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get(
                "/v1/tools/secret_list",
                headers={"Authorization": "Bearer mk_agent_test"},
            )

    resp = _run(_inner())
    assert resp.status_code == 200
    for secret in resp.json()["secrets"]:
        assert "value" not in secret


def test_secret_list_unauthenticated_returns_401():
    """secret_list returns 401 when agent_ctx is None."""
    import mcp_server.main as _main_mod
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _no_ctx():
        return None

    app.dependency_overrides[get_agent_context] = _no_ctx

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.get("/v1/tools/secret_list")

    resp = _run(_inner())
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# secret_delete tests
# ---------------------------------------------------------------------------

def test_secret_delete_owner_success():
    """secret_delete returns 200 for the owning agent."""
    app = _build_secret_app(secret_owned_by_caller=True)
    with _mock_vault_delete():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.delete(
                    "/v1/tools/secret_delete",
                    params={"secret_id": "sec_" + "A" * 26},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 200, resp.text
    assert resp.json() == {}


def test_secret_delete_non_owner_returns_404_secret_not_found():
    """secret_delete returns 404 secret_not_found for a non-owner."""
    app = _build_secret_app(
        agent_id=_AGENT_B_ID,
        secret_exists=True,
        secret_owned_by_caller=False,
    )
    with _mock_vault_delete():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.delete(
                    "/v1/tools/secret_delete",
                    params={"secret_id": "sec_" + "A" * 26},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 404
    assert resp.json()["code"] == "mintkey:secret_not_found"


def test_secret_delete_nonexistent_returns_404_secret_not_found():
    """secret_delete returns 404 secret_not_found for a nonexistent secret."""
    app = _build_secret_app(secret_exists=False)
    with _mock_vault_delete():
        async def _inner():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.delete(
                    "/v1/tools/secret_delete",
                    params={"secret_id": "sec_" + "D" * 26},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )
        resp = _run(_inner())

    assert resp.status_code == 404
    assert resp.json()["code"] == "mintkey:secret_not_found"


def test_secret_delete_anti_enumeration_not_owned_equals_nonexistent():
    """
    Anti-enumeration: deleting a not-owned secret and a nonexistent secret
    return IDENTICAL status code and code field.
    """
    app_not_owned = _build_secret_app(
        agent_id=_AGENT_B_ID,
        secret_exists=True,
        secret_owned_by_caller=False,
    )
    app_missing = _build_secret_app(secret_exists=False)

    async def _delete(app, secret_id_suffix):
        with _mock_vault_delete():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.delete(
                    "/v1/tools/secret_delete",
                    params={"secret_id": f"sec_{secret_id_suffix}"},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    resp_not_owned = _run(_delete(app_not_owned, "A" * 26))
    resp_missing = _run(_delete(app_missing, "E" * 26))

    # EQUALITY assertion
    assert resp_not_owned.status_code == resp_missing.status_code, (
        f"Status mismatch: {resp_not_owned.status_code} vs {resp_missing.status_code}"
    )
    assert resp_not_owned.json()["code"] == resp_missing.json()["code"], (
        f"Code mismatch: {resp_not_owned.json()} vs {resp_missing.json()}"
    )


def test_secret_delete_idempotent():
    """
    Idempotent delete: calling delete twice should not raise.
    (Second call: row already gone → 404, which is the uniform not-found.)
    This asserts only that no exception is raised and the response is valid JSON.
    """
    app_first = _build_secret_app(secret_owned_by_caller=True)
    app_second = _build_secret_app(secret_exists=False)

    async def _delete(app):
        with _mock_vault_delete():
            async with AsyncClient(
                transport=ASGITransport(app=app), base_url="http://test"
            ) as client:
                return await client.delete(
                    "/v1/tools/secret_delete",
                    params={"secret_id": "sec_" + "F" * 26},
                    headers={"Authorization": "Bearer mk_agent_test"},
                )

    resp1 = _run(_delete(app_first))
    resp2 = _run(_delete(app_second))

    assert resp1.status_code == 200
    # Second call: secret already gone → 404 (idempotent — no crash, valid JSON)
    assert resp2.status_code == 404
    assert resp2.json()["code"] == "mintkey:secret_not_found"


def test_secret_delete_unauthenticated_returns_401():
    """secret_delete returns 401 when agent_ctx is None."""
    import mcp_server.main as _main_mod
    from mcp_server.tools.discovery import get_agent_context

    app = _main_mod.create_app()

    async def _no_ctx():
        return None

    app.dependency_overrides[get_agent_context] = _no_ctx

    async def _inner():
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            return await client.delete(
                "/v1/tools/secret_delete",
                params={"secret_id": "sec_" + "A" * 26},
            )

    resp = _run(_inner())
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Audit payload wire-form assertions (G)
# ---------------------------------------------------------------------------

def test_secret_put_audit_payload_agent_id_is_wire_form():
    """secret_put audit payload must carry agent_id in agent_ wire form."""
    app = _build_secret_app(secret_exists=False)
    captured_payloads: list = []

    async def _capturing_audit_emit(**kwargs):
        captured_payloads.append(kwargs.get("payload", {}))

    with _mock_vault_put():
        with patch("mcp_server.tools.secret_put.audit_emit", side_effect=_capturing_audit_emit):
            async def _inner():
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.post(
                        "/v1/tools/secret_put",
                        json={"name": "my-key", "value": "secret"},
                        headers={"Authorization": "Bearer mk_agent_test"},
                    )
            resp = _run(_inner())

    assert resp.status_code == 200
    assert len(captured_payloads) == 1
    p = captured_payloads[0]
    assert p["agent_id"].startswith("agent_"), f"agent_id not wire form: {p['agent_id']}"
    assert p["secret_id"].startswith("sec_"), f"secret_id not wire form: {p['secret_id']}"
    assert p["name"] == "my-key"
    assert p["version"] == 1
    assert "previous_version" not in p  # create has no previous_version
    # Schema conformance: validate captured payload against canonical schema
    _validate_payload("agent_secret.created", p)


def test_secret_put_update_audit_payload_has_previous_version():
    """secret_put audit payload for update must carry previous_version."""
    app = _build_secret_app(secret_exists=True, existing_version=2)
    captured_payloads: list = []

    async def _capturing_audit_emit(**kwargs):
        captured_payloads.append(kwargs.get("payload", {}))

    with _mock_vault_put():
        with patch("mcp_server.tools.secret_put.audit_emit", side_effect=_capturing_audit_emit):
            async def _inner():
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.post(
                        "/v1/tools/secret_put",
                        json={"name": "my-key", "value": "new-value"},
                        headers={"Authorization": "Bearer mk_agent_test"},
                    )
            resp = _run(_inner())

    assert resp.status_code == 200
    p = captured_payloads[0]
    assert p["version"] == 3
    assert p["previous_version"] == 2
    # Schema conformance: validate captured payload against canonical schema
    _validate_payload("agent_secret.updated", p)


def test_secret_get_audit_payload_reader_agent_id_is_wire_form():
    """secret_get audit payload must carry reader_agent_id in agent_ wire form."""
    app = _build_secret_app(secret_owned_by_caller=True)
    captured_payloads: list = []

    async def _capturing_audit_emit(**kwargs):
        captured_payloads.append(kwargs.get("payload", {}))

    with _mock_vault_get(_PLAINTEXT):
        with patch("mcp_server.tools.secret_get.audit_emit", side_effect=_capturing_audit_emit):
            async def _inner():
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.get(
                        "/v1/tools/secret_get",
                        params={"secret_id": "sec_" + "A" * 26},
                        headers={"Authorization": "Bearer mk_agent_test"},
                    )
            resp = _run(_inner())

    assert resp.status_code == 200
    assert len(captured_payloads) == 1
    p = captured_payloads[0]
    assert p["reader_agent_id"].startswith("agent_"), (
        f"reader_agent_id not wire form: {p['reader_agent_id']}"
    )
    # Schema conformance: validate captured payload against canonical schema
    _validate_payload("agent_secret.read", p)


def test_secret_delete_audit_payload_wire_forms_and_name():
    """secret_delete audit payload must carry wire forms for IDs and include name."""
    app = _build_secret_app(secret_owned_by_caller=True)
    captured_payloads: list = []

    async def _capturing_audit_emit(**kwargs):
        captured_payloads.append(kwargs.get("payload", {}))

    with _mock_vault_delete():
        with patch("mcp_server.tools.secret_delete.audit_emit", side_effect=_capturing_audit_emit):
            async def _inner():
                async with AsyncClient(
                    transport=ASGITransport(app=app), base_url="http://test"
                ) as client:
                    return await client.delete(
                        "/v1/tools/secret_delete",
                        params={"secret_id": "sec_" + "A" * 26},
                        headers={"Authorization": "Bearer mk_agent_test"},
                    )
            resp = _run(_inner())

    assert resp.status_code == 200
    assert len(captured_payloads) == 1
    p = captured_payloads[0]
    assert p["secret_id"].startswith("sec_"), f"secret_id not wire form: {p['secret_id']}"
    assert p["agent_id"].startswith("agent_"), f"agent_id not wire form: {p['agent_id']}"
    assert "name" in p, "name missing from delete audit payload"
    # Schema conformance: validate captured payload against canonical schema
    _validate_payload("agent_secret.deleted", p)


# ---------------------------------------------------------------------------
# Schema conformance tests (H)
# ---------------------------------------------------------------------------

def _load_agent_secret_payload_schema(event_type: str) -> dict:
    """
    Load the payload schema for a given agent_secret* event type from the
    canonical audit-event.schema.json.

    Maps event_type dots/underscores to $defs key: e.g.
      "agent_secret.created" -> "ev_agent_secret_created"
      "agent_secret_grant.revoked" -> "ev_agent_secret_grant_revoked"
    """
    import json
    import pathlib

    schema_path = pathlib.Path(__file__).parents[3] / (
        "docs/architecture/contracts/events/audit-event.schema.json"
    )
    schema = json.loads(schema_path.read_text())
    # Convert event_type to $defs key
    def_key = "ev_" + event_type.replace(".", "_")
    ev_def = schema["$defs"][def_key]
    # Extract payload schema from properties.payload
    return ev_def["properties"]["payload"]


def _validate_payload(event_type: str, payload: dict) -> None:
    """
    Validate payload against the schema $defs for the given event_type.

    Loads the canonical schema and checks:
      1. All required fields are present.
      2. String-typed fields with a pattern regex match their pattern.
      3. No additional properties beyond those declared.
    """
    import json
    import pathlib
    import re

    payload_schema = _load_agent_secret_payload_schema(event_type)
    required = payload_schema.get("required", [])
    properties = payload_schema.get("properties", {})

    schema_path = pathlib.Path(__file__).parents[3] / (
        "docs/architecture/contracts/events/audit-event.schema.json"
    )
    full_schema = json.loads(schema_path.read_text())

    # 1. Required fields present
    for field in required:
        assert field in payload, (
            f"[{event_type}] Required field '{field}' missing from payload: {payload}"
        )

    # 2. Pattern checks for string fields
    for field, value in payload.items():
        if field not in properties:
            continue
        prop_schema = properties[field]
        # Resolve $ref if needed (we only need the pattern from $defs)
        if "$ref" in prop_schema:
            ref_key = prop_schema["$ref"].split("/")[-1]
            prop_schema = full_schema["$defs"].get(ref_key, prop_schema)
        pattern = prop_schema.get("pattern")
        if pattern and isinstance(value, str):
            assert re.match(pattern, value), (
                f"[{event_type}] Field '{field}' value {value!r} "
                f"does not match pattern {pattern!r}"
            )

    # 3. No additional properties (schema has additionalProperties: false)
    if payload_schema.get("additionalProperties") is False:
        for field in payload:
            assert field in properties, (
                f"[{event_type}] Unexpected field '{field}' in payload: {payload}"
            )


@pytest.mark.parametrize("event_type,payload", [
    (
        "agent_secret.created",
        {
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "agent_id": "agent_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "name": "my-secret",
            "version": 1,
        },
    ),
    (
        "agent_secret.updated",
        {
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "agent_id": "agent_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "name": "my-secret",
            "version": 2,
            "previous_version": 1,
        },
    ),
    (
        "agent_secret.read",
        {
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "version": 1,
            "reader_agent_id": "agent_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "access": "owner",
        },
    ),
    (
        "agent_secret.deleted",
        {
            "secret_id": "sec_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "agent_id": "agent_AAAAAAAAAAAAAAAAAAAAAAAAA1",
            "name": "my-secret",
        },
    ),
])
def test_mcp_audit_payload_schema_conformance(event_type, payload):
    """Each agent_secret* payload must conform to the canonical schema $defs."""
    _validate_payload(event_type, payload)
