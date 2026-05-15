"""
Wire-form consistency test — #13 / ADR-0017.11.

Verifies that every list/create/get response emits Crockford ULID wire-form IDs
(not the legacy 32-hex form) for all resources:
  - agents      — id field (agent_<26Crockford>)
  - services    — id field (svc_<26Crockford>)
  - permissions — id, agent_id, service_id fields (perm_/agent_/svc_ + Crockford)
  - api_keys    — api_key_id, service_id fields (svckey_/svc_ + Crockford)

The 32-hex form (e.g. agent_6c3c950a2e184ba98c895b875b1bf5bd, 32 hex chars after prefix)
must NOT appear in any list/get response after this fix.

Pattern rules:
  Crockford suffix:  26 chars drawn from [0-9A-HJKMNP-TV-Z] (no I, L, O, U)
  32-hex suffix:     32 chars drawn from [0-9a-f]

Source: ADR-0017.11; #13.
"""
from __future__ import annotations

import re
import secrets
import hashlib
from typing import Any

import psycopg2
import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# Wire-form validation patterns — ADR-0017.11
# ---------------------------------------------------------------------------

# Crockford base32 suffix: exactly 26 chars from the Crockford alphabet (no I/L/O/U)
_CROCKFORD_PATTERN = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")
# Legacy 32-hex suffix (must NOT appear in post-#13 responses)
_HEX32_PATTERN = re.compile(r"^[0-9a-f]{32}$")

_CSRF_TOKEN = "test-csrf-token-wire-consistency"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}


def _post(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


def _delete(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.delete(url, headers=headers, cookies=cookies, **kwargs)


def _assert_crockford_wire_id(value: str, prefix: str, field_name: str) -> None:
    """Assert that `value` is <prefix>_<26-char Crockford> and NOT <prefix>_<32hex>."""
    assert isinstance(value, str), f"{field_name}: expected str, got {type(value)}"
    assert value.startswith(f"{prefix}_"), (
        f"{field_name}: expected prefix '{prefix}_', got: {value!r}"
    )
    suffix = value[len(prefix) + 1:]
    assert len(suffix) == 26, (
        f"{field_name}: expected 26-char Crockford suffix, got {len(suffix)} chars: {value!r}"
    )
    assert _CROCKFORD_PATTERN.match(suffix.upper()), (
        f"{field_name}: suffix is not valid Crockford base32: {value!r}"
    )
    assert not _HEX32_PATTERN.match(suffix), (
        f"{field_name}: suffix looks like 32-hex (legacy form MUST NOT be emitted): {value!r}"
    )


def _insert_tenant(postgres_container, slug: str) -> str:
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    conn = psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )
    cur = conn.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO tenants (slug, display_name, isolation_mode, status)"
            " VALUES (%s, %s, 'row', 'active') RETURNING id",
            (slug, slug),
        )
        conn.commit()
        row = cur.fetchone()
    else:
        conn.commit()
    cur.close()
    conn.close()
    assert row is not None
    return str(row[0])


@pytest.fixture(scope="module")
def wf_tenant(admin_app: TestClient, postgres_container) -> str:
    return _insert_tenant(postgres_container, "wire-form-consistency-tenant")


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------

def test_agent_create_emits_crockford(admin_app: TestClient, wf_tenant: str) -> None:
    """POST /agents → 201 with agent_<26Crockford> id."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/agents",
        json={"name": "wf-create-agent"},
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    _assert_crockford_wire_id(body["id"], "agent", "create response id")


def test_agent_list_emits_crockford(admin_app: TestClient, wf_tenant: str) -> None:
    """GET /agents → list items have agent_<26Crockford> ids (not 32-hex)."""
    # Ensure at least one agent exists
    _post(admin_app, f"/v1/tenants/{wf_tenant}/agents", json={"name": "wf-list-agent"})

    resp = admin_app.get(f"/v1/tenants/{wf_tenant}/agents")
    assert resp.status_code == 200, resp.text
    agents = resp.json()["agents"]
    assert len(agents) >= 1, "Expected at least one agent in list"
    for agent in agents:
        _assert_crockford_wire_id(agent["id"], "agent", "list agent id")


def test_agent_create_and_list_id_consistent(admin_app: TestClient, wf_tenant: str) -> None:
    """Create response id matches the id returned in list."""
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/agents",
        json={"name": "wf-consistency-agent"},
    )
    assert create_resp.status_code == 201
    create_id = create_resp.json()["id"]
    _assert_crockford_wire_id(create_id, "agent", "create id")

    list_resp = admin_app.get(f"/v1/tenants/{wf_tenant}/agents")
    list_ids = [a["id"] for a in list_resp.json()["agents"]]
    assert create_id in list_ids, (
        f"Create id {create_id!r} not found in list ids: {list_ids}"
    )


def test_agent_get_emits_crockford(admin_app: TestClient, wf_tenant: str) -> None:
    """GET /agents/{id} with Crockford ID → 200 with Crockford id."""
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/agents",
        json={"name": "wf-get-agent"},
    )
    assert create_resp.status_code == 201
    agent_id = create_resp.json()["id"]

    get_resp = admin_app.get(f"/v1/tenants/{wf_tenant}/agents/{agent_id}")
    assert get_resp.status_code == 200, get_resp.text
    _assert_crockford_wire_id(get_resp.json()["id"], "agent", "get response id")


# ---------------------------------------------------------------------------
# Services
# ---------------------------------------------------------------------------

def test_service_create_emits_crockford(admin_app: TestClient, wf_tenant: str) -> None:
    """POST /services → 201 with svc_<26Crockford> id."""
    resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/services",
        json={
            "name": "wf-create-svc",
            "base_url": "https://wf-create.example.com/api",
            "auth_scheme": "bearer_token",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    _assert_crockford_wire_id(body["id"], "svc", "create response id")


def test_service_list_emits_crockford(admin_app: TestClient, wf_tenant: str) -> None:
    """GET /services → list items have svc_<26Crockford> ids."""
    _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/services",
        json={
            "name": "wf-list-svc",
            "base_url": "https://wf-list.example.com/api",
            "auth_scheme": "api_key",
        },
    )
    resp = admin_app.get(f"/v1/tenants/{wf_tenant}/services")
    assert resp.status_code == 200
    services = resp.json()["services"]
    assert len(services) >= 1
    for svc in services:
        _assert_crockford_wire_id(svc["id"], "svc", "list service id")


def test_service_create_and_list_id_consistent(admin_app: TestClient, wf_tenant: str) -> None:
    """Create response id matches the id returned in list (no hex/Crockford mismatch)."""
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/services",
        json={
            "name": "wf-consistency-svc",
            "base_url": "https://wf-consistency.example.com/api",
            "auth_scheme": "bearer_token",
        },
    )
    assert create_resp.status_code == 201
    create_id = create_resp.json()["id"]
    _assert_crockford_wire_id(create_id, "svc", "create id")

    list_resp = admin_app.get(f"/v1/tenants/{wf_tenant}/services")
    list_ids = [s["id"] for s in list_resp.json()["services"]]
    assert create_id in list_ids, (
        f"Create id {create_id!r} not found in list ids: {list_ids}"
    )


def test_service_get_by_crockford_id_works(admin_app: TestClient, wf_tenant: str) -> None:
    """GET /services/{crockford_id} → 200 (create→list→get round-trip)."""
    create_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/services",
        json={
            "name": "wf-get-svc",
            "base_url": "https://wf-get.example.com/api",
            "auth_scheme": "bearer_token",
        },
    )
    assert create_resp.status_code == 201
    svc_id = create_resp.json()["id"]
    _assert_crockford_wire_id(svc_id, "svc", "create id")

    get_resp = admin_app.get(f"/v1/tenants/{wf_tenant}/services/{svc_id}")
    assert get_resp.status_code == 200, get_resp.text
    _assert_crockford_wire_id(get_resp.json()["id"], "svc", "get response id")


# ---------------------------------------------------------------------------
# Permissions
# ---------------------------------------------------------------------------

def test_permission_list_emits_crockford(admin_app: TestClient, wf_tenant: str) -> None:
    """Permission grant list emits Crockford wire IDs for id, agent_id, service_id."""
    # Create agent and service
    agent_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/agents",
        json={"name": "wf-perm-agent"},
    )
    assert agent_resp.status_code == 201
    agent_id = agent_resp.json()["id"]

    svc_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/services",
        json={
            "name": "wf-perm-svc",
            "base_url": "https://wf-perm.example.com/api",
            "auth_scheme": "bearer_token",
        },
    )
    assert svc_resp.status_code == 201
    svc_id = svc_resp.json()["id"]

    # Grant permission
    grant_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/agents/{agent_id}/permissions",
        json={"service_id": svc_id, "action": "read"},
    )
    assert grant_resp.status_code in (200, 201), grant_resp.text
    grant_body = grant_resp.json()
    _assert_crockford_wire_id(grant_body["id"], "perm", "grant response id")

    # List permissions
    list_resp = admin_app.get(f"/v1/tenants/{wf_tenant}/agents/{agent_id}/permissions")
    assert list_resp.status_code == 200
    grants = list_resp.json()["grants"]
    assert len(grants) >= 1
    for g in grants:
        _assert_crockford_wire_id(g["id"], "perm", "list perm id")
        _assert_crockford_wire_id(g["agent_id"], "agent", "list perm agent_id")
        _assert_crockford_wire_id(g["service_id"], "svc", "list perm service_id")


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

def test_api_key_create_and_list_emit_crockford(admin_app: TestClient, wf_tenant: str) -> None:
    """API key create and list both emit svckey_<26Crockford> api_key_id."""
    # Create agent
    agent_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/agents",
        json={"name": "wf-apikey-agent"},
    )
    assert agent_resp.status_code == 201
    agent_id = agent_resp.json()["id"]

    # Create service
    svc_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/services",
        json={
            "name": "wf-apikey-svc",
            "base_url": "https://wf-apikey.example.com/api",
            "auth_scheme": "bearer_token",
        },
    )
    assert svc_resp.status_code == 201
    svc_id = svc_resp.json()["id"]

    # Grant permission
    grant_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/agents/{agent_id}/permissions",
        json={"service_id": svc_id, "action": "invoke"},
    )
    assert grant_resp.status_code in (200, 201)

    # Create API key
    key_resp = _post(
        admin_app,
        f"/v1/tenants/{wf_tenant}/agents/{agent_id}/api-keys",
        json={
            "service_id": svc_id,
            "allowed_actions": ["invoke"],
        },
    )
    assert key_resp.status_code == 201, key_resp.text
    key_body = key_resp.json()
    _assert_crockford_wire_id(key_body["api_key_id"], "svckey", "create api_key_id")

    create_key_id = key_body["api_key_id"]

    # List API keys
    list_resp = admin_app.get(f"/v1/tenants/{wf_tenant}/agents/{agent_id}/api-keys")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) >= 1
    for item in items:
        _assert_crockford_wire_id(item["api_key_id"], "svckey", "list api_key_id")
        if item.get("service_id"):
            _assert_crockford_wire_id(item["service_id"], "svc", "list api_key service_id")

    # Create ID must appear in list
    list_key_ids = [i["api_key_id"] for i in items]
    assert create_key_id in list_key_ids, (
        f"Create api_key_id {create_key_id!r} not found in list: {list_key_ids}"
    )
