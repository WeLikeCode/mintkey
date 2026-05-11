"""
Mintkey seed job — one-shot bootstrap.

Runs after Liquibase exits 0 and before admin-api starts.
Connects as mintkey_migrate (BYPASSRLS) so RLS policies do not block inserts.

Steps 1-5 are implemented (T-1.0.2 session 1).
Steps 6-8 (Vault Adapter keypairs) are in session 2 after T-1.0.4.
Steps 9-11 (Keycloak + audit chain) are in session 3.
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
    Create bootstrap admin operator with Argon2id-hashed password.
    Returns (operator_id: str, plaintext_password: str).
    Second call returns ("", "") — idempotent per Req 1 AC6.

    Note: argon2-cffi is imported here (session-2 dep); pip install argon2-cffi.
    Source: Req 1 AC5 step 2, design §3 step 5.
    """
    import argon2  # noqa: PLC0415 — deferred so missing dep fails only this step

    ph = argon2.PasswordHasher()

    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM operators WHERE email = %s AND tenant_id = %s::uuid",
            (DEFAULT_ADMIN_EMAIL, tenant_id),
        )
        row = cur.fetchone()
        if row is not None:
            return str(row[0]), ""

        password = secrets.token_urlsafe(32)
        hashed = ph.hash(password)

        cur.execute(
            """
            INSERT INTO operators
              (tenant_id, email, display_name, internal_password_hash, is_platform_admin, status)
            VALUES (%s::uuid, %s, %s, %s, true, 'active')
            RETURNING id
            """,
            (tenant_id, DEFAULT_ADMIN_EMAIL, "Bootstrap Admin", hashed),
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

        if os.getenv("MINTKEY_SEED_DEMO", "").lower() in ("1", "true", "yes"):
            print("Seed: MINTKEY_SEED_DEMO=true — registering mock backend…")
            seed_mock_backend_demo(conn, tenant_id)
            print("Demo seed complete.")
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
