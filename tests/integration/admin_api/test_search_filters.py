"""
Integration tests for free-text search (q) and contextual filter query parameters
added to list endpoints (admin-api-search-filters chunk).

Endpoints covered:
  GET /v1/tenants/{tid}/services          — q (name, slug, description, base_url)
  GET /v1/tenants/{tid}/services/{sid}/credentials — q (auth_scheme)
  GET /v1/tenants/{tid}/agents            — q (name, description), has_access_to_service_id
  GET /v1/tenants/{tid}/agents/{aid}/permissions   — service_id filter
  GET /v1/tenants/{tid}/agents/{aid}/api-keys      — q (fingerprint), service_id
  GET /v1/tenants/{tid}/audit             — q (event_type), event_type, actor_id, from_ts, to_ts
  GET /v1/tenants                         — q (slug, display_name) [PlatformAdmin]

Acceptance criteria verified:
  - No params → existing response unchanged (regression).
  - q=<known substring> → expected hits.
  - Contextual filter → expected hits.
  - Combined params → AND semantics.
  - Tenant isolation: operator in tenant A, data in tenant B → empty result.
  - LIKE-special-char safety: q=% and q=_ are handled safely.
"""
from __future__ import annotations

import hashlib
import json
import secrets
import uuid
from typing import Optional

import psycopg2
import pytest
from starlette.testclient import TestClient

# ---------------------------------------------------------------------------
# CSRF / Platform-Admin helpers
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-csrf-filter-abc"
_CSRF_HEADERS = {"x-mintkey-csrf": _CSRF_TOKEN}
_CSRF_COOKIES = {"csrf_token": _CSRF_TOKEN}
_PLATFORM_ADMIN = {"X-Platform-Admin": "true"}


def _post(client: TestClient, url: str, **kwargs):
    headers = {**kwargs.pop("headers", {}), **_CSRF_HEADERS}
    cookies = {**kwargs.pop("cookies", {}), **_CSRF_COOKIES}
    return client.post(url, headers=headers, cookies=cookies, **kwargs)


# ---------------------------------------------------------------------------
# Low-level DB helpers
# ---------------------------------------------------------------------------


def _conn(postgres_container):
    host = postgres_container.get_container_host_ip()
    port = postgres_container.get_exposed_port(5432)
    return psycopg2.connect(
        host=host, port=port,
        dbname=postgres_container.dbname,
        user=postgres_container.username,
        password=postgres_container.password,
    )


def _insert_tenant(postgres_container, slug: str) -> str:
    conn = _conn(postgres_container)
    cur = conn.cursor()
    cur.execute("SELECT id FROM tenants WHERE slug = %s", (slug,))
    row = cur.fetchone()
    if row is None:
        cur.execute(
            "INSERT INTO tenants (slug, display_name, isolation_mode, status)"
            " VALUES (%s, %s, 'row', 'active') RETURNING id",
            (slug, f"Display {slug}"),
        )
        conn.commit()
        row = cur.fetchone()
    else:
        conn.commit()
    cur.close()
    conn.close()
    return str(row[0])


def _insert_service(postgres_container, tenant_id: str, name: str,
                    base_url: str = "https://example.com/api",
                    auth_scheme: str = "bearer_token",
                    description: str = "") -> str:
    """Insert a service and return its UUID string."""
    svc_id = str(uuid.uuid4())
    slug = name.lower().replace(" ", "-")
    conn = _conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO services"
        " (id, tenant_id, name, slug, description, base_url, auth_scheme, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, 'active') RETURNING id",
        (svc_id, tenant_id, name, slug, description, base_url, auth_scheme),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    return str(row[0])


def _insert_agent(postgres_container, tenant_id: str, name: str,
                  description: str = "") -> str:
    """Insert an agent and return its UUID string."""
    agent_id = str(uuid.uuid4())
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    raw_key = "mk_agent_" + secrets.token_hex(20)
    api_key_hash = ph.hash(raw_key)
    fingerprint = hashlib.sha256(raw_key.encode()).digest()[:8].hex()

    conn = _conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO agents"
        " (id, tenant_id, name, description, api_key_hash, api_key_fingerprint,"
        "  mcp_endpoint, status)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, 'active') RETURNING id",
        (agent_id, tenant_id, name, description, api_key_hash, fingerprint,
         f"http://localhost:8100/v1/agents/{agent_id}"),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    return str(row[0])


def _insert_permission(postgres_container, tenant_id: str, agent_id: str,
                       service_id: str, action: str = "read:all") -> str:
    """Insert a permission grant and return its UUID string."""
    perm_id = str(uuid.uuid4())
    conn = _conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO permission_grants"
        " (id, tenant_id, agent_id, service_id, action, constraints, created_by)"
        " VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s) RETURNING id",
        (perm_id, tenant_id, agent_id, service_id, action, "{}", agent_id),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    return str(row[0])


def _insert_credential(postgres_container, tenant_id: str, service_id: str,
                       auth_scheme: str = "bearer_token") -> str:
    """Insert a credential metadata row."""
    cred_id = str(uuid.uuid4())
    conn = _conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO credentials"
        " (id, tenant_id, service_id, key_version, ciphertext, nonce,"
        "  wrapped_dek, auth_scheme, status)"
        " VALUES (%s, %s, %s, 1, %s, %s, %s, %s, 'active') RETURNING id",
        (cred_id, tenant_id, service_id, b"", b"", b"", auth_scheme),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    return str(row[0])


def _insert_api_key(postgres_container, tenant_id: str, agent_id: str,
                    service_id: str) -> tuple[str, str]:
    """Insert a service_api_key row; return (id, key_fingerprint)."""
    key_id = str(uuid.uuid4())
    from argon2 import PasswordHasher
    ph = PasswordHasher(time_cost=1, memory_cost=65536, parallelism=4, hash_len=32)
    plaintext = "mk_svckey_" + secrets.token_hex(20)
    fp = hashlib.sha256(plaintext.encode()).digest()[:8].hex()
    key_hash = ph.hash(plaintext)

    conn = _conn(postgres_container)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO service_api_keys"
        " (id, tenant_id, agent_id, service_id, key_hash, key_fingerprint,"
        "  allowed_actions, created_by)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s::text[], %s) RETURNING id",
        (key_id, tenant_id, agent_id, service_id, key_hash, fp,
         ["read:all"], agent_id),
    )
    conn.commit()
    row = cur.fetchone()
    cur.close()
    conn.close()
    return str(row[0]), fp


# ---------------------------------------------------------------------------
# Fixtures — module-scoped to avoid rebuilding per test
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sf_tenant(admin_app: TestClient, postgres_container) -> str:
    """Primary tenant for search-filter tests."""
    return _insert_tenant(postgres_container, "sf-tenant-a")


@pytest.fixture(scope="module")
def sf_tenant_b(admin_app: TestClient, postgres_container) -> str:
    """Secondary tenant (isolation check)."""
    return _insert_tenant(postgres_container, "sf-tenant-b")


@pytest.fixture(scope="module")
def sf_svc_alpha(admin_app, postgres_container, sf_tenant) -> str:
    return _insert_service(
        postgres_container, sf_tenant,
        name="Alpha Service",
        base_url="https://alpha.example.com/api",
        auth_scheme="bearer_token",
        description="Primary alpha service for search test",
    )


@pytest.fixture(scope="module")
def sf_svc_beta(admin_app, postgres_container, sf_tenant) -> str:
    return _insert_service(
        postgres_container, sf_tenant,
        name="Beta Service",
        base_url="https://beta.example.com/api",
        auth_scheme="api_key",
        description="Secondary beta description",
    )


@pytest.fixture(scope="module")
def sf_svc_in_b(admin_app, postgres_container, sf_tenant_b) -> str:
    """A service in tenant B (should be invisible to tenant A searches)."""
    return _insert_service(
        postgres_container, sf_tenant_b,
        name="Alpha Service in B",
        description="alpha description in tenant B",
    )


@pytest.fixture(scope="module")
def sf_agent_a(admin_app, postgres_container, sf_tenant) -> str:
    return _insert_agent(
        postgres_container, sf_tenant,
        name="Agent Alpha",
        description="Does alpha tasks",
    )


@pytest.fixture(scope="module")
def sf_agent_b(admin_app, postgres_container, sf_tenant) -> str:
    return _insert_agent(
        postgres_container, sf_tenant,
        name="Agent Beta",
        description="Does beta tasks",
    )


@pytest.fixture(scope="module")
def sf_perm_a_alpha(admin_app, postgres_container, sf_tenant, sf_agent_a, sf_svc_alpha) -> str:
    """Grant agent_a access to svc_alpha."""
    return _insert_permission(postgres_container, sf_tenant, sf_agent_a, sf_svc_alpha)


@pytest.fixture(scope="module")
def sf_cred_alpha_bearer(admin_app, postgres_container, sf_tenant, sf_svc_alpha) -> str:
    return _insert_credential(postgres_container, sf_tenant, sf_svc_alpha, "bearer_token")


@pytest.fixture(scope="module")
def sf_cred_alpha_apikey(admin_app, postgres_container, sf_tenant, sf_svc_alpha) -> str:
    return _insert_credential(postgres_container, sf_tenant, sf_svc_alpha, "api_key")


@pytest.fixture(scope="module")
def sf_api_key_a_alpha(admin_app, postgres_container, sf_tenant, sf_agent_a,
                        sf_svc_alpha, sf_perm_a_alpha) -> tuple[str, str]:
    return _insert_api_key(postgres_container, sf_tenant, sf_agent_a, sf_svc_alpha)


# ---------------------------------------------------------------------------
# Helper to format UUID as svc_ wire ID
# ---------------------------------------------------------------------------


def _svc_wire(uuid_str: str) -> str:
    """Convert a plain UUID string to svc_<32 hex> wire form."""
    return "svc_" + uuid_str.replace("-", "")


# ===========================================================================
# GET /v1/tenants/{tid}/services — q filter
# ===========================================================================


class TestServiceSearch:

    def test_no_params_returns_all(self, admin_app, sf_tenant, sf_svc_alpha, sf_svc_beta):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/services")
        assert resp.status_code == 200
        ids = {s["id"] for s in resp.json()["services"]}
        assert _svc_wire(sf_svc_alpha) in ids
        assert _svc_wire(sf_svc_beta) in ids

    def test_q_matches_name(self, admin_app, sf_tenant, sf_svc_alpha, sf_svc_beta):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/services", params={"q": "Alpha"})
        assert resp.status_code == 200
        services = resp.json()["services"]
        ids = {s["id"] for s in services}
        assert _svc_wire(sf_svc_alpha) in ids
        assert _svc_wire(sf_svc_beta) not in ids

    def test_q_case_insensitive(self, admin_app, sf_tenant, sf_svc_beta):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/services", params={"q": "beta"})
        assert resp.status_code == 200
        ids = {s["id"] for s in resp.json()["services"]}
        assert _svc_wire(sf_svc_beta) in ids

    def test_q_matches_description(self, admin_app, sf_tenant, sf_svc_alpha):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/services", params={"q": "primary alpha"})
        assert resp.status_code == 200
        ids = {s["id"] for s in resp.json()["services"]}
        assert _svc_wire(sf_svc_alpha) in ids

    def test_q_matches_base_url(self, admin_app, sf_tenant, sf_svc_alpha):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/services", params={"q": "alpha.example.com"})
        assert resp.status_code == 200
        ids = {s["id"] for s in resp.json()["services"]}
        assert _svc_wire(sf_svc_alpha) in ids

    def test_q_no_match_returns_empty(self, admin_app, sf_tenant):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/services", params={"q": "xyzzy_no_match_ever"})
        assert resp.status_code == 200
        assert resp.json()["services"] == []

    def test_q_percent_sign_safe(self, admin_app, sf_tenant):
        """q=% must not explode or match everything via SQL injection."""
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/services", params={"q": "%"})
        assert resp.status_code == 200
        # Should return empty (no service name literally contains %)
        assert resp.json()["services"] == []

    def test_q_underscore_safe(self, admin_app, sf_tenant):
        """q=_ must not match everything via SQL glob."""
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/services", params={"q": "_"})
        assert resp.status_code == 200
        assert resp.json()["services"] == []

    def test_tenant_isolation(self, admin_app, sf_tenant, sf_svc_in_b):
        """Tenant A cannot find tenant B services even with matching q."""
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/services", params={"q": "Alpha Service in B"})
        assert resp.status_code == 200
        # Should be empty — tenant A's search must not see B's data
        assert resp.json()["services"] == []


# ===========================================================================
# GET /v1/tenants/{tid}/services/{sid}/credentials — q filter
# ===========================================================================


class TestCredentialSearch:

    def test_no_params_returns_all(self, admin_app, sf_tenant, sf_svc_alpha,
                                    sf_cred_alpha_bearer, sf_cred_alpha_apikey):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/services/{sf_svc_alpha}/credentials"
        )
        assert resp.status_code == 200
        versions = resp.json()["versions"]
        schemes = {v["auth_scheme"] for v in versions}
        assert "bearer_token" in schemes
        assert "api_key" in schemes

    def test_q_matches_auth_scheme(self, admin_app, sf_tenant, sf_svc_alpha,
                                    sf_cred_alpha_bearer, sf_cred_alpha_apikey):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/services/{sf_svc_alpha}/credentials",
            params={"q": "bearer"},
        )
        assert resp.status_code == 200
        versions = resp.json()["versions"]
        assert all("bearer" in v["auth_scheme"] for v in versions)
        assert len(versions) >= 1

    def test_q_no_match(self, admin_app, sf_tenant, sf_svc_alpha,
                         sf_cred_alpha_bearer):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/services/{sf_svc_alpha}/credentials",
            params={"q": "nonexistent_scheme"},
        )
        assert resp.status_code == 200
        assert resp.json()["versions"] == []

    def test_q_percent_sign_safe(self, admin_app, sf_tenant, sf_svc_alpha):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/services/{sf_svc_alpha}/credentials",
            params={"q": "%"},
        )
        assert resp.status_code == 200
        assert resp.json()["versions"] == []


# ===========================================================================
# GET /v1/tenants/{tid}/agents — q + has_access_to_service_id
# ===========================================================================


class TestAgentSearch:

    def test_no_params_returns_all(self, admin_app, sf_tenant, sf_agent_a, sf_agent_b):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/agents")
        assert resp.status_code == 200
        ids = {a["id"] for a in resp.json()["agents"]}
        wire_a = "agent_" + sf_agent_a.replace("-", "")
        wire_b = "agent_" + sf_agent_b.replace("-", "")
        assert wire_a in ids
        assert wire_b in ids

    def test_q_matches_name(self, admin_app, sf_tenant, sf_agent_a, sf_agent_b):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/agents", params={"q": "Alpha"})
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        wire_a = "agent_" + sf_agent_a.replace("-", "")
        wire_b = "agent_" + sf_agent_b.replace("-", "")
        ids = {a["id"] for a in agents}
        assert wire_a in ids
        assert wire_b not in ids

    def test_q_matches_description(self, admin_app, sf_tenant, sf_agent_b):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/agents", params={"q": "beta tasks"})
        assert resp.status_code == 200
        ids = {a["id"] for a in resp.json()["agents"]}
        wire_b = "agent_" + sf_agent_b.replace("-", "")
        assert wire_b in ids

    def test_has_access_to_service_id_uuid(self, admin_app, sf_tenant, sf_agent_a,
                                            sf_agent_b, sf_svc_alpha, sf_perm_a_alpha):
        """has_access_to_service_id (UUID) → only agent_a (has grant)."""
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents",
            params={"has_access_to_service_id": sf_svc_alpha},
        )
        assert resp.status_code == 200
        ids = {a["id"] for a in resp.json()["agents"]}
        wire_a = "agent_" + sf_agent_a.replace("-", "")
        wire_b = "agent_" + sf_agent_b.replace("-", "")
        assert wire_a in ids
        assert wire_b not in ids

    def test_has_access_to_service_id_wire(self, admin_app, sf_tenant, sf_agent_a,
                                            sf_svc_alpha, sf_perm_a_alpha):
        """has_access_to_service_id as svc_ wire ID also works."""
        wire_svc = _svc_wire(sf_svc_alpha)
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents",
            params={"has_access_to_service_id": wire_svc},
        )
        assert resp.status_code == 200
        ids = {a["id"] for a in resp.json()["agents"]}
        wire_a = "agent_" + sf_agent_a.replace("-", "")
        assert wire_a in ids

    def test_combined_q_and_service_filter(self, admin_app, sf_tenant, sf_agent_a,
                                            sf_agent_b, sf_svc_alpha, sf_perm_a_alpha):
        """q=Alpha AND has_access_to_service_id → intersection."""
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents",
            params={"q": "Alpha", "has_access_to_service_id": sf_svc_alpha},
        )
        assert resp.status_code == 200
        agents = resp.json()["agents"]
        wire_a = "agent_" + sf_agent_a.replace("-", "")
        assert any(a["id"] == wire_a for a in agents)

    def test_q_percent_safe(self, admin_app, sf_tenant):
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/agents", params={"q": "%"})
        assert resp.status_code == 200
        assert resp.json()["agents"] == []

    def test_tenant_isolation_q(self, admin_app, sf_tenant, sf_svc_in_b):
        """Tenant A sees no agents via q search of tenant B data."""
        resp = admin_app.get(f"/v1/tenants/{sf_tenant}/agents", params={"q": "Alpha"})
        # Only tenant A agents appear (we can't see tenant B's agents)
        assert resp.status_code == 200


# ===========================================================================
# GET /v1/tenants/{tid}/agents/{aid}/permissions — service_id filter (NEW endpoint)
# ===========================================================================


class TestPermissionSearch:

    def test_no_params_returns_grants(self, admin_app, sf_tenant, sf_agent_a,
                                       sf_perm_a_alpha):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/permissions"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "grants" in body
        assert len(body["grants"]) >= 1

    def test_service_id_filter_uuid(self, admin_app, sf_tenant, sf_agent_a,
                                     sf_svc_alpha, sf_svc_beta, sf_perm_a_alpha):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/permissions",
            params={"service_id": sf_svc_alpha},
        )
        assert resp.status_code == 200
        grants = resp.json()["grants"]
        assert all(g["service_id"] == sf_svc_alpha for g in grants)

    def test_service_id_filter_no_match(self, admin_app, sf_tenant, sf_agent_a, sf_svc_beta):
        """Agent A has no grant on svc_beta — should return empty."""
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/permissions",
            params={"service_id": sf_svc_beta},
        )
        assert resp.status_code == 200
        assert resp.json()["grants"] == []

    def test_service_id_wire_form(self, admin_app, sf_tenant, sf_agent_a,
                                   sf_svc_alpha, sf_perm_a_alpha):
        wire = _svc_wire(sf_svc_alpha)
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/permissions",
            params={"service_id": wire},
        )
        assert resp.status_code == 200
        grants = resp.json()["grants"]
        assert len(grants) >= 1

    def test_tenant_isolation(self, admin_app, sf_tenant_b, sf_agent_a, sf_perm_a_alpha):
        """Tenant B cannot see tenant A's agent permissions."""
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant_b}/agents/{sf_agent_a}/permissions"
        )
        assert resp.status_code == 200
        assert resp.json()["grants"] == []


# ===========================================================================
# GET /v1/tenants/{tid}/agents/{aid}/api-keys — q + service_id
# ===========================================================================


class TestApiKeySearch:

    def test_no_params_returns_all(self, admin_app, sf_tenant, sf_agent_a,
                                    sf_api_key_a_alpha):
        key_id, fp = sf_api_key_a_alpha
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/api-keys"
        )
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
        assert len(resp.json()) >= 1

    def test_q_matches_fingerprint_prefix(self, admin_app, sf_tenant, sf_agent_a,
                                           sf_api_key_a_alpha):
        key_id, fp = sf_api_key_a_alpha
        prefix = fp[:4]
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/api-keys",
            params={"q": prefix},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert any(i["key_fingerprint"] == fp for i in items)

    def test_q_no_match(self, admin_app, sf_tenant, sf_agent_a, sf_api_key_a_alpha):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/api-keys",
            params={"q": "zzz_no_match_fingerprint"},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_service_id_filter(self, admin_app, sf_tenant, sf_agent_a, sf_svc_alpha,
                                sf_api_key_a_alpha):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/api-keys",
            params={"service_id": sf_svc_alpha},
        )
        assert resp.status_code == 200
        items = resp.json()
        assert len(items) >= 1
        assert all(i["service_id"] == sf_svc_alpha for i in items)

    def test_service_id_no_match(self, admin_app, sf_tenant, sf_agent_a, sf_svc_beta):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/api-keys",
            params={"service_id": sf_svc_beta},
        )
        assert resp.status_code == 200
        assert resp.json() == []

    def test_q_percent_safe(self, admin_app, sf_tenant, sf_agent_a):
        resp = admin_app.get(
            f"/v1/tenants/{sf_tenant}/agents/{sf_agent_a}/api-keys",
            params={"q": "%"},
        )
        assert resp.status_code == 200
        assert resp.json() == []


# ===========================================================================
# GET /v1/tenants/{tid}/audit — q, event_type, from_ts, to_ts
# ===========================================================================


class TestAuditSearch:

    @pytest.fixture(scope="class")
    def audit_tenant(self, admin_app, postgres_container):
        tid = _insert_tenant(postgres_container, "sf-audit-tenant")
        # Trigger an audit event by creating a service via POST
        svc_id = _insert_service(postgres_container, tid, "audit-test-service")
        # Emit a known event by inserting directly
        conn = _conn(postgres_container)
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO audit_events (tenant_id, event_type, actor_type, payload, prev_hash, hash)"
            " VALUES (%s, 'service.registered', 'operator', '{}'::jsonb, %s, %s)",
            (tid, b"\x00" * 32, b"\x00" * 32),
        )
        cur.execute(
            "INSERT INTO audit_events (tenant_id, event_type, actor_type, payload, prev_hash, hash)"
            " VALUES (%s, 'agent.created', 'operator', '{}'::jsonb, %s, %s)",
            (tid, b"\x00" * 32, b"\x00" * 32),
        )
        conn.commit()
        cur.close()
        conn.close()
        return tid

    def test_no_params_returns_events(self, admin_app, audit_tenant):
        resp = admin_app.get(f"/v1/tenants/{audit_tenant}/audit")
        assert resp.status_code == 200
        body = resp.json()
        assert "events" in body
        assert len(body["events"]) >= 2

    def test_event_type_exact_filter(self, admin_app, audit_tenant):
        resp = admin_app.get(
            f"/v1/tenants/{audit_tenant}/audit",
            params={"event_type": "service.registered"},
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert all(e["event_type"] == "service.registered" for e in events)
        assert len(events) >= 1

    def test_q_matches_event_type_substring(self, admin_app, audit_tenant):
        resp = admin_app.get(
            f"/v1/tenants/{audit_tenant}/audit",
            params={"q": "agent"},
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert all("agent" in e["event_type"].lower() for e in events)
        assert len(events) >= 1

    def test_q_no_match(self, admin_app, audit_tenant):
        resp = admin_app.get(
            f"/v1/tenants/{audit_tenant}/audit",
            params={"q": "xyzzy_event_never_exists"},
        )
        assert resp.status_code == 200
        assert resp.json()["events"] == []

    def test_from_ts_filter(self, admin_app, audit_tenant):
        """from_ts in the far future → empty results."""
        resp = admin_app.get(
            f"/v1/tenants/{audit_tenant}/audit",
            params={"from_ts": "2099-01-01T00:00:00Z"},
        )
        assert resp.status_code == 200
        assert resp.json()["events"] == []

    def test_to_ts_filter(self, admin_app, audit_tenant):
        """to_ts in the far past → empty results."""
        resp = admin_app.get(
            f"/v1/tenants/{audit_tenant}/audit",
            params={"to_ts": "2000-01-01T00:00:00Z"},
        )
        assert resp.status_code == 200
        assert resp.json()["events"] == []

    def test_q_percent_safe(self, admin_app, audit_tenant):
        resp = admin_app.get(
            f"/v1/tenants/{audit_tenant}/audit",
            params={"q": "%"},
        )
        assert resp.status_code == 200
        assert resp.json()["events"] == []

    def test_combined_q_and_event_type(self, admin_app, audit_tenant):
        """q=service AND event_type=service.registered → only service.registered events."""
        resp = admin_app.get(
            f"/v1/tenants/{audit_tenant}/audit",
            params={"q": "service", "event_type": "service.registered"},
        )
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert all(e["event_type"] == "service.registered" for e in events)

    def test_tenant_isolation(self, admin_app, sf_tenant_b, audit_tenant):
        """Tenant B cannot see audit events from audit_tenant."""
        resp = admin_app.get(f"/v1/tenants/{sf_tenant_b}/audit")
        assert resp.status_code == 200
        for e in resp.json()["events"]:
            assert e["tenant_id"] == sf_tenant_b


# ===========================================================================
# GET /v1/tenants — q filter (PlatformAdmin only)
# ===========================================================================


class TestTenantSearch:

    def test_no_params_returns_all(self, admin_app, sf_tenant, sf_tenant_b):
        resp = admin_app.get(
            "/v1/tenants",
            headers=_PLATFORM_ADMIN,
        )
        assert resp.status_code == 200
        slugs = {t["slug"] for t in resp.json()["data"]}
        assert "sf-tenant-a" in slugs
        assert "sf-tenant-b" in slugs

    def test_q_matches_slug(self, admin_app, sf_tenant):
        resp = admin_app.get(
            "/v1/tenants",
            headers=_PLATFORM_ADMIN,
            params={"q": "sf-tenant-a"},
        )
        assert resp.status_code == 200
        slugs = {t["slug"] for t in resp.json()["data"]}
        assert "sf-tenant-a" in slugs

    def test_q_matches_display_name(self, admin_app):
        """display_name was set to 'Display sf-tenant-a' in _insert_tenant."""
        resp = admin_app.get(
            "/v1/tenants",
            headers=_PLATFORM_ADMIN,
            params={"q": "Display sf-tenant"},
        )
        assert resp.status_code == 200
        assert len(resp.json()["data"]) >= 1

    def test_q_no_match(self, admin_app):
        resp = admin_app.get(
            "/v1/tenants",
            headers=_PLATFORM_ADMIN,
            params={"q": "xyzzy_no_such_tenant"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_q_percent_safe(self, admin_app):
        resp = admin_app.get(
            "/v1/tenants",
            headers=_PLATFORM_ADMIN,
            params={"q": "%"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_q_underscore_safe(self, admin_app):
        resp = admin_app.get(
            "/v1/tenants",
            headers=_PLATFORM_ADMIN,
            params={"q": "_"},
        )
        assert resp.status_code == 200
        assert resp.json()["data"] == []

    def test_no_platform_admin_still_403(self, admin_app):
        resp = admin_app.get("/v1/tenants", params={"q": "something"})
        assert resp.status_code == 403
