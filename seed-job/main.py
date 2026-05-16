"""
Mintkey seed job — one-shot bootstrap.

Runs after Liquibase exits 0 and before admin-api starts.
Connects as mintkey_migrate (BYPASSRLS) so RLS policies do not block inserts.

Steps 1-5 are implemented (T-1.0.2 session 1).
Steps 6-8 (Vault Adapter keypairs) are in session 2 after T-1.0.4.
Step 9 (Keycloak realm bootstrap) is implemented in SSO-A.
Step 12 (mock backend registration) is behind MINTKEY_SEED_DEMO=true (T-1.11.4).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import secrets
import sys
import time
import uuid
from pathlib import Path

import psycopg2
import requests
from tenacity import retry, stop_after_delay, wait_exponential

DEFAULT_TENANT_SLUG = "t_default"
DEFAULT_ADMIN_EMAIL = os.getenv("MINTKEY_BOOTSTRAP_EMAIL", "admin@mintkey.internal")
BOOTSTRAP_SECRETS_DIR = Path(os.getenv("BOOTSTRAP_SECRETS_DIR", "./data/bootstrap-secrets"))


# ---------------------------------------------------------------------------
# Step 1: Wait for Postgres
# ---------------------------------------------------------------------------


def wait_for_postgres(dsn: str, max_retries: int = 30, delay: float = 2.0) -> None:
    """Wait up to max_retries * delay seconds for Postgres to accept connections."""
    for attempt in range(max_retries):
        try:
            conn = psycopg2.connect(dsn)
            conn.close()
            return
        except psycopg2.OperationalError:
            if attempt < max_retries - 1:
                time.sleep(delay)
    raise RuntimeError(
        f"Postgres not reachable after {max_retries * delay:.0f}s"
    )


# ---------------------------------------------------------------------------
# Step 2: Verify Liquibase
# ---------------------------------------------------------------------------


def verify_liquibase_applied(conn: psycopg2.extensions.connection) -> None:
    """Verify databasechangelog exists and has at least one row."""
    with conn.cursor() as cur:
        try:
            cur.execute(
                "SELECT id FROM databasechangelog ORDER BY orderexecuted DESC LIMIT 1"
            )
            row = cur.fetchone()
        except psycopg2.errors.UndefinedTable:
            conn.rollback()
            raise RuntimeError(
                "databasechangelog table not found — Liquibase has not run yet"
            )
    if row is None:
        raise RuntimeError(
            "databasechangelog is empty — no migrations have been applied"
        )


# ---------------------------------------------------------------------------
# Step 3: Default tenant
# ---------------------------------------------------------------------------


def seed_default_tenant(conn: psycopg2.extensions.connection) -> str:
    """
    Insert t_default tenant if not present (ON CONFLICT DO NOTHING).
    Returns the tenant UUID string.
    Source: Req 1 AC5 step 1, design §3 step 3, ADR-0017.9.
    """
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO tenants (slug, display_name, isolation_mode)
            VALUES (%s, %s, %s)
            ON CONFLICT (slug) DO NOTHING
            """,
            (DEFAULT_TENANT_SLUG, "Default Tenant", "row"),
        )
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (DEFAULT_TENANT_SLUG,))
        row = cur.fetchone()
    return str(row[0])


# ---------------------------------------------------------------------------
# Step 4: Per-tenant audit_chain_state genesis
# ---------------------------------------------------------------------------


def seed_audit_chain_state(conn: psycopg2.extensions.connection, tenant_id: str) -> None:
    """
    Insert genesis audit_chain_state row for a tenant.
    genesis_hash = sha256("mintkey-audit-genesis-v1:" + tenant_id).
    Source: Req 1 AC12, ADR-0014.7, design §3 step 4.
    """
    genesis_input = f"mintkey-audit-genesis-v1:{tenant_id}".encode()
    genesis_hash = hashlib.sha256(genesis_input).digest()
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO audit_chain_state (tenant_id, head_hash)
            VALUES (%s, %s)
            ON CONFLICT (tenant_id) DO NOTHING
            """,
            (tenant_id, genesis_hash),
        )


# ---------------------------------------------------------------------------
# Step 5: Bootstrap admin operator + membership
# ---------------------------------------------------------------------------


def seed_bootstrap_operator(
    conn: psycopg2.extensions.connection, tenant_id: str
) -> tuple:
    """
    Create bootstrap admin operator with internal_password_hash=NULL.
    Returns (operator_id: str, plaintext_password: str).
    Second call returns ("", "") — idempotent per Req 1 AC6.

    SSO-B: internal_password_hash is NULL by default.  The plaintext password
    is still generated and written to bootstrap-secrets/admin_password so that
    Keycloak can be seeded in step 9.  The CLI `mintkey admin reset-password`
    is the only way to set a hash (D2-b).

    Source: Req 1 AC5 step 2, design §3 step 5; SSO-B D2-b.
    """
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM operators WHERE email = %s AND tenant_id = %s::uuid",
            (DEFAULT_ADMIN_EMAIL, tenant_id),
        )
        row = cur.fetchone()
        if row is not None:
            return str(row[0]), ""

        # SSO-B: no password hash stored in the DB — internal_password_hash stays NULL.
        # A plaintext password is still generated so step 9 can seed Keycloak.
        password = secrets.token_urlsafe(32)

        cur.execute(
            """
            INSERT INTO operators
              (tenant_id, email, display_name, internal_password_hash, oidc_sub, is_platform_admin, status)
            VALUES (%s::uuid, %s, %s, NULL, NULL, true, 'active')
            RETURNING id
            """,
            (tenant_id, DEFAULT_ADMIN_EMAIL, "Bootstrap Admin"),
        )
        operator_id = str(cur.fetchone()[0])

        cur.execute(
            """
            INSERT INTO operator_tenant_memberships (operator_id, tenant_id, role)
            VALUES (%s::uuid, %s::uuid, 'Admin')
            ON CONFLICT (operator_id, tenant_id) DO NOTHING
            """,
            (operator_id, tenant_id),
        )

    return operator_id, password


# ---------------------------------------------------------------------------
# Step 12: Mock backend registration (MINTKEY_SEED_DEMO=true only)
# T-1.11.4 — registers mock-backend as a Mintkey service so agents can
# discover and call it via MCP.
# ---------------------------------------------------------------------------

MOCK_BACKEND_SLUG = "mock-backend"
MOCK_BACKEND_URL = os.getenv("MOCK_BACKEND_URL", "http://mock-backend:8070")
MOCK_BACKEND_API_KEY = os.getenv("MOCK_BACKEND_API_KEY", "canary-demo-api-key")
DEMO_AGENT_NAME = "mock-agent"


def seed_mock_backend_demo(conn: psycopg2.extensions.connection, tenant_id: str) -> None:
    """
    Register the mock backend service + demo agent + permission grants so
    the agent can discover and call it via MCP.

    Only runs when MINTKEY_SEED_DEMO=true. Uses ON CONFLICT DO NOTHING for
    full idempotency.

    Source: T-1.11.4; Req 12 AC2; design §12.
    """
    with conn.cursor() as cur:
        # Insert mock-backend service (ON CONFLICT DO NOTHING for idempotency)
        service_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO services
              (id, tenant_id, name, slug, display_name, description,
               base_url, auth_scheme, openapi_url, allow_internal_urls, current_key_version, status)
            VALUES
              (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, %s, false, 1, 'active')
            ON CONFLICT (tenant_id, slug) DO NOTHING
            """,
            (
                service_id,
                tenant_id,
                "Mock Backend",
                MOCK_BACKEND_SLUG,
                "Mock Backend",
                "Demo service exercising all Mintkey auth schemes",
                MOCK_BACKEND_URL,
                "api_key_header",
                f"{MOCK_BACKEND_URL}/openapi.json",
            ),
        )
        # Retrieve actual service_id (may differ if already existed)
        cur.execute(
            "SELECT id FROM services WHERE tenant_id = %s::uuid AND slug = %s",
            (tenant_id, MOCK_BACKEND_SLUG),
        )
        service_id = str(cur.fetchone()[0])

        # Insert demo API key credential (plaintext never stored here; the
        # real seed would call the Vault Adapter. For demo purposes we store
        # a placeholder so the service table has a registered credential.)
        # NOTE: In a real deployment T-1.3.2 handles credential storage via
        # the Vault Adapter gRPC. This is demo-only scaffolding.
        cur.execute(
            """
            INSERT INTO credentials
              (id, tenant_id, service_id, key_version, ciphertext, nonce, wrapped_dek,
               auth_scheme, status)
            VALUES
              (%s::uuid, %s::uuid, %s::uuid, 1, %s, %s, %s, 'api_key_header', 'active')
            ON CONFLICT DO NOTHING
            """,
            (
                str(uuid.uuid4()),
                tenant_id,
                service_id,
                MOCK_BACKEND_API_KEY.encode(),  # demo-only: plaintext stored as bytes
                b"\x00" * 12,                   # placeholder nonce
                b"\x00" * 32,                   # placeholder wrapped DEK
            ),
        )

        # Insert demo agent (ON CONFLICT DO NOTHING)
        agent_id = str(uuid.uuid4())
        demo_key = secrets.token_urlsafe(32)
        import hashlib as _hl
        key_hash = _hl.sha256(demo_key.encode()).hexdigest()
        fingerprint = key_hash[:8]
        cur.execute(
            """
            INSERT INTO agents
              (id, tenant_id, name, description, api_key_hash, api_key_fingerprint, status)
            VALUES
              (%s::uuid, %s::uuid, %s, %s, %s, %s, 'active')
            ON CONFLICT DO NOTHING
            """,
            (
                agent_id,
                tenant_id,
                DEMO_AGENT_NAME,
                "Demo agent for mock-backend smoke tests",
                key_hash,
                fingerprint,
            ),
        )
        # Retrieve actual agent_id
        cur.execute(
            "SELECT id FROM agents WHERE tenant_id = %s::uuid AND name = %s",
            (tenant_id, DEMO_AGENT_NAME),
        )
        agent_id = str(cur.fetchone()[0])

        # Grant demo agent permissions on mock-backend service
        for action in ["read:health", "read:echo", "read:bearer", "read:api-key-header"]:
            cur.execute(
                """
                INSERT INTO permission_grants
                  (id, tenant_id, agent_id, service_id, action, constraints, created_by)
                VALUES
                  (%s::uuid, %s::uuid, %s::uuid, %s::uuid, %s, %s, %s::uuid)
                ON CONFLICT DO NOTHING
                """,
                (
                    str(uuid.uuid4()),
                    tenant_id,
                    agent_id,
                    service_id,
                    action,
                    json.dumps({}),
                    agent_id,  # self-issued for demo
                ),
            )

    print(f"Demo: registered service '{MOCK_BACKEND_SLUG}' (id={service_id})")
    print(f"Demo: registered agent '{DEMO_AGENT_NAME}' (id={agent_id})")
    print(f"Demo: agent API key (shown once): {demo_key}")
    print("Demo: granted read:health, read:echo, read:bearer, read:api-key-header")


# ---------------------------------------------------------------------------
# Step 9: Keycloak realm bootstrap (SSO-A)
# ---------------------------------------------------------------------------

# Keycloak connection settings — read from env with docker-network defaults.
_KC_INTERNAL_URL = os.getenv(
    "MINTKEY_KEYCLOAK_INTERNAL_URL", "http://keycloak:8443"
).rstrip("/")
_KC_ADMIN = os.getenv("KEYCLOAK_ADMIN", "admin")
_KC_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "changeme")

# Maps client ID to the bootstrap-secrets filename for its secret.
_CLIENT_SECRET_FILES: dict[str, str] = {
    "mintkey-admin-api": "oidc_client_secret",
    "mintkey-grafana": "grafana_oidc_client_secret",
    "mintkey-jaeger": "jaeger_oidc_client_secret",
}

# Env vars whose values replace ${...} placeholders in realm.json.
# Defaults match the localhost host-port mappings in docker-compose; operators
# override via .env for cross-machine access (see docs/NETWORK.md).
_REALM_JSON_ENV_DEFAULTS = {
    "MINTKEY_ADMIN_API_PUBLIC_URL": "http://localhost:8080",
    "MINTKEY_GRAFANA_PUBLIC_URL": "http://localhost:3003",
    "MINTKEY_JAEGER_PUBLIC_URL": "http://localhost:16686",
}


def _kc_wait_ready() -> None:
    """Poll Keycloak master realm OIDC discovery until 200 (tenacity, 60 s)."""
    url = f"{_KC_INTERNAL_URL}/realms/master/.well-known/openid-configuration"

    @retry(
        stop=stop_after_delay(60),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _poll() -> None:
        resp = requests.get(url, timeout=5)
        resp.raise_for_status()

    print(f"Keycloak: waiting for readiness at {url} …")
    _poll()
    print("Keycloak: ready.")


def _kc_admin_token() -> str:
    """Obtain a short-lived admin token from the master realm."""
    resp = requests.post(
        f"{_KC_INTERNAL_URL}/realms/master/protocol/openid-connect/token",
        data={
            "client_id": "admin-cli",
            "username": _KC_ADMIN,
            "password": _KC_ADMIN_PASSWORD,
            "grant_type": "password",
        },
        timeout=15,
    )
    resp.raise_for_status()
    token = resp.json()["access_token"]
    return token


def _kc_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _interpolate_realm_json(raw: str) -> dict:
    """Replace ${MINTKEY_*_PUBLIC_URL} placeholders with env values or localhost defaults."""
    for var, default in _REALM_JSON_ENV_DEFAULTS.items():
        value = os.getenv(var, default)
        raw = raw.replace(f"${{{var}}}", value)
    return json.loads(raw)


def _ensure_realm(token: str, realm_json_path: Path) -> None:
    """Import realm if it does not exist yet."""
    resp = requests.get(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey",
        headers=_kc_headers(token),
        timeout=15,
    )
    if resp.status_code == 200:
        print("Keycloak: realm 'mintkey' already exists — skipping import.")
        return
    if resp.status_code != 404:
        resp.raise_for_status()

    raw = realm_json_path.read_text()
    realm_body = _interpolate_realm_json(raw)
    import_resp = requests.post(
        f"{_KC_INTERNAL_URL}/admin/realms",
        headers=_kc_headers(token),
        json=realm_body,
        timeout=30,
    )
    import_resp.raise_for_status()
    print("Keycloak: realm 'mintkey' imported.")


def _write_client_secrets(token: str, secrets_dir: Path) -> None:
    """Retrieve each client's secret from Keycloak and write to bootstrap-secrets."""
    for client_id, secret_filename in _CLIENT_SECRET_FILES.items():
        # Resolve client UUID
        resp = requests.get(
            f"{_KC_INTERNAL_URL}/admin/realms/mintkey/clients",
            params={"clientId": client_id},
            headers=_kc_headers(token),
            timeout=15,
        )
        resp.raise_for_status()
        clients = resp.json()
        if not clients:
            raise RuntimeError(
                f"Keycloak: client '{client_id}' not found in realm 'mintkey'"
            )
        client_uuid = clients[0]["id"]

        # Retrieve secret
        secret_resp = requests.get(
            f"{_KC_INTERNAL_URL}/admin/realms/mintkey/clients/{client_uuid}/client-secret",
            headers=_kc_headers(token),
            timeout=15,
        )
        secret_resp.raise_for_status()
        secret_value = secret_resp.json()["value"]

        secret_file = secrets_dir / secret_filename
        secret_file.write_text(secret_value)
        # Permission policy: all bootstrap secrets are stored in a shared Docker
        # named volume (bootstrap_secrets) mounted :ro into a fixed set of
        # services. Consumer containers run as various non-root UIDs (grafana:
        # 472, jaeger-auth/admin-api: 65532) that differ from seed-job's root
        # UID, so 0o640 (owner-read only) would block them. The Docker volume
        # itself is the security boundary — no untrusted users exist inside any
        # container in the compose stack — so world-read (0o644) is correct for
        # every bootstrap secret written here.
        secret_file.chmod(0o644)
        print(f"Keycloak: wrote {secret_file}")


def _ensure_jaeger_cookie_secret(secrets_dir: Path) -> None:
    """Write jaeger_oauth2_cookie_secret (32 raw bytes) if missing.

    oauth2-proxy v7.6+ requires the cookie secret to be exactly 16, 24, or 32
    bytes so it can construct an AES cipher.  Writing text (hex/base64) produces
    a file that is 44 or 64 bytes — rejected at startup.  Writing raw bytes
    gives exactly 32 bytes (AES-256).
    """
    cookie_secret_file = secrets_dir / "jaeger_oauth2_cookie_secret"
    if cookie_secret_file.exists():
        print("Keycloak: jaeger_oauth2_cookie_secret already exists — skipping.")
        return
    # 32 raw bytes (AES-256 cookie key for oauth2-proxy)
    cookie_secret_file.write_bytes(os.urandom(32))
    # jaeger-auth runs as UID 65532 (non-root); 0o644 lets it read the file.
    # Security boundary is the Docker volume (bootstrap_secrets), not the mode.
    cookie_secret_file.chmod(0o644)
    print(f"Keycloak: wrote {cookie_secret_file}")


def _ensure_admin_user(token: str) -> str:
    """Ensure admin@mintkey.internal exists; return user UUID."""
    email = "admin@mintkey.internal"
    resp = requests.get(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/users",
        params={"email": email},
        headers=_kc_headers(token),
        timeout=15,
    )
    resp.raise_for_status()
    users = resp.json()
    if users:
        user_uuid = users[0]["id"]
        print(f"Keycloak: user '{email}' already exists (id={user_uuid}).")
        return user_uuid

    create_resp = requests.post(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/users",
        headers=_kc_headers(token),
        json={
            "username": email,
            "email": email,
            "enabled": True,
            "emailVerified": True,
            "firstName": "Mintkey",
            "lastName": "Admin",
        },
        timeout=15,
    )
    create_resp.raise_for_status()

    # Re-fetch to get UUID
    refetch = requests.get(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/users",
        params={"email": email},
        headers=_kc_headers(token),
        timeout=15,
    )
    refetch.raise_for_status()
    user_uuid = refetch.json()[0]["id"]
    print(f"Keycloak: created user '{email}' (id={user_uuid}).")
    return user_uuid


def _sync_admin_password(token: str, user_uuid: str, secrets_dir: Path) -> None:
    """Set admin password in Keycloak, gated by mtime sentinel."""
    admin_password_file = secrets_dir / "admin_password"
    sentinel_file = secrets_dir / ".admin_password_synced"

    if not admin_password_file.exists():
        print("Keycloak: admin_password file not found — skipping password sync.")
        return

    if sentinel_file.exists():
        pw_mtime = admin_password_file.stat().st_mtime
        sentinel_mtime = sentinel_file.stat().st_mtime
        if sentinel_mtime >= pw_mtime:
            print("Keycloak: admin password already synced (sentinel up-to-date) — skipping.")
            return

    password = admin_password_file.read_text().strip()
    resp = requests.put(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/users/{user_uuid}/reset-password",
        headers=_kc_headers(token),
        json={"type": "password", "value": password, "temporary": False},
        timeout=15,
    )
    resp.raise_for_status()
    print("Keycloak: admin password set.")


def _assign_platform_admin_role(token: str, user_uuid: str) -> None:
    """Assign mintkey-platform-admin realm role to the admin user (idempotent)."""
    # Get role definition
    role_resp = requests.get(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/roles/mintkey-platform-admin",
        headers=_kc_headers(token),
        timeout=15,
    )
    role_resp.raise_for_status()
    role = role_resp.json()

    # POST is set-add semantics — safe to call repeatedly
    assign_resp = requests.post(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/users/{user_uuid}/role-mappings/realm",
        headers=_kc_headers(token),
        json=[role],
        timeout=15,
    )
    assign_resp.raise_for_status()
    print("Keycloak: role 'mintkey-platform-admin' assigned to admin user.")


def _enforce_pkce_on_clients(token: str) -> None:
    """Idempotent: ensure pkce.code.challenge.method=S256 on all 3 OIDC clients.

    realm-mintkey.json handles fresh installs; this step covers existing installs
    where the realm was already imported before the attribute was added (Keycloak
    skips re-import when the realm already exists).

    Uses GET → merge attributes → PUT (Keycloak client-update uses PUT, not PATCH).

    Source: SSO-REDUX-2 R-02; ADR-0020.
    """
    client_ids = list(_CLIENT_SECRET_FILES.keys())  # ["mintkey-admin-api", "mintkey-grafana", "mintkey-jaeger"]
    for client_id in client_ids:
        # Step 1: GET current client representation + UUID
        resp = requests.get(
            f"{_KC_INTERNAL_URL}/admin/realms/mintkey/clients",
            params={"clientId": client_id},
            headers=_kc_headers(token),
            timeout=15,
        )
        resp.raise_for_status()
        clients = resp.json()
        if not clients:
            print(f"Keycloak: WARNING — client '{client_id}' not found; skipping PKCE enforcement.")
            continue
        client_rep = clients[0]
        client_uuid = client_rep["id"]

        # Step 2: check whether already enforced
        attrs = client_rep.get("attributes") or {}
        if attrs.get("pkce.code.challenge.method") == "S256":
            print(f"Keycloak: PKCE S256 enforced on {client_id} (already enforced — skipping)")
            continue

        # Step 3: merge attribute + PUT full client representation (Keycloak requires PUT)
        attrs["pkce.code.challenge.method"] = "S256"
        client_rep["attributes"] = attrs
        put_resp = requests.put(
            f"{_KC_INTERNAL_URL}/admin/realms/mintkey/clients/{client_uuid}",
            headers=_kc_headers(token),
            json=client_rep,
            timeout=15,
        )
        put_resp.raise_for_status()
        print(f"Keycloak: PKCE S256 enforced on {client_id}")


def _touch_sentinel(secrets_dir: Path) -> None:
    sentinel_file = secrets_dir / ".admin_password_synced"
    sentinel_file.touch()
    sentinel_file.chmod(0o600)


def _pre_link_operator_oidc_sub(
    conn: psycopg2.extensions.connection,
    tenant_id: str,
    kc_user_uuid: str,
) -> None:
    """
    Step 9b: Pre-link the bootstrap operator's oidc_sub to the Keycloak user UUID.

    Eliminates the lazy-first-login race condition (Opus recommendation).
    Tolerant: if the operator row is not found, logs and continues rather than
    blocking bootstrap (hard rule 8 — belt-and-suspenders lazy link remains).

    Source: SSO-B spec §step-9b.
    """
    try:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE operators
                SET oidc_sub = %s
                WHERE email = %s
                  AND oidc_sub IS NULL
                """,
                (kc_user_uuid, DEFAULT_ADMIN_EMAIL),
            )
            rows_updated = cur.rowcount
        if rows_updated > 0:
            print(
                f"Keycloak: pre-linked operator '{DEFAULT_ADMIN_EMAIL}'"
                f" → oidc_sub={kc_user_uuid}"
            )
        else:
            # Either already linked (re-run) or operator not found
            print(
                f"Keycloak: oidc_sub already set or operator not found for"
                f" '{DEFAULT_ADMIN_EMAIL}' — skipping pre-link."
            )
    except Exception as exc:
        print(
            f"Keycloak: WARNING — oidc_sub pre-link failed (non-blocking): {exc}",
            flush=True,
        )


def seed_keycloak_realm_and_admin(
    conn: psycopg2.extensions.connection, tenant_id: str
) -> None:
    """
    Step 9: Bootstrap Keycloak mintkey realm, clients, admin user.

    - Waits for Keycloak readiness (tenacity, 60s).
    - Imports realm from realm-mintkey.json if not present.
    - Writes per-client OIDC secrets to bootstrap-secrets/.
    - Ensures admin@mintkey.internal exists with correct password and role.
    - Step 9b: pre-links oidc_sub on the local operator row (SSO-B).
    - Idempotent: existence checks + mtime sentinel.

    Source: SSO-A spec; ADR-0014 §14.2; Kiro design.md §3 step 9; SSO-B step 9b.
    """
    secrets_dir = BOOTSTRAP_SECRETS_DIR
    secrets_dir.mkdir(parents=True, exist_ok=True)

    realm_json_path = Path(__file__).parent / "realm-mintkey.json"

    _kc_wait_ready()
    token = _kc_admin_token()

    _ensure_realm(token, realm_json_path)

    # Refresh token after realm import (may take a moment)
    token = _kc_admin_token()

    _write_client_secrets(token, secrets_dir)
    _enforce_pkce_on_clients(token)
    _ensure_jaeger_cookie_secret(secrets_dir)

    user_uuid = _ensure_admin_user(token)
    _sync_admin_password(token, user_uuid, secrets_dir)
    _assign_platform_admin_role(token, user_uuid)
    _touch_sentinel(secrets_dir)

    # Step 9b: pre-link oidc_sub so first OIDC login is instant (SSO-B)
    _pre_link_operator_oidc_sub(conn, tenant_id, user_uuid)

    print("Keycloak realm bootstrap complete")


# ---------------------------------------------------------------------------
# Composite helpers
# ---------------------------------------------------------------------------


def run_steps_1_to_5(conn: psycopg2.extensions.connection) -> dict:
    """
    Execute seed steps 2-5 given an open connection.
    Step 1 (pg wait) must be done before calling this.
    Returns {"tenant_id": str, "operator_id": str, "password": str}.
    """
    verify_liquibase_applied(conn)
    tenant_id = seed_default_tenant(conn)
    seed_audit_chain_state(conn, tenant_id)
    operator_id, password = seed_bootstrap_operator(conn, tenant_id)
    return {
        "tenant_id": tenant_id,
        "operator_id": operator_id,
        "password": password,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def _build_dsn() -> str:
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    db = os.getenv("PGDATABASE", "postgres")
    user = os.getenv("PGUSER", "mintkey_migrate")
    password = os.getenv("PGPASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Mintkey bootstrap seed job")
    parser.add_argument(
        "--rotate-bootstrap",
        action="store_true",
        help="Re-run steps 6-9 with new secrets (overlap window applies)",
    )
    args = parser.parse_args(argv)

    dsn = _build_dsn()

    print("Seed: waiting for Postgres…")
    wait_for_postgres(dsn)
    conn = psycopg2.connect(dsn)
    conn.autocommit = True

    try:
        print("Seed: running steps 2-5…")
        result = run_steps_1_to_5(conn)
        tenant_id = result["tenant_id"]
        operator_id = result["operator_id"]
        password = result["password"]

        if password:
            BOOTSTRAP_SECRETS_DIR.mkdir(parents=True, exist_ok=True)
            secret_file = BOOTSTRAP_SECRETS_DIR / "admin_password"
            secret_file.write_text(password)
            secret_file.chmod(0o400)
            print(f"Bootstrap admin password: {password}")
            print(f"Written to {secret_file}")

        print(f"Seed steps 1-5 complete. tenant={tenant_id} operator={operator_id}")
        print("NOTE: Steps 6-8 (Vault Adapter keypairs) pending T-1.0.4.")

        print("Seed: running step 9 — Keycloak realm bootstrap…")
        seed_keycloak_realm_and_admin(conn, tenant_id)

        if os.getenv("MINTKEY_SEED_DEMO", "").lower() in ("1", "true", "yes"):
            print("Seed: MINTKEY_SEED_DEMO=true — registering mock backend…")
            seed_mock_backend_demo(conn, tenant_id)
            print("Demo seed complete.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
