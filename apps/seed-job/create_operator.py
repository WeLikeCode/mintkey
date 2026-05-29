"""
create_operator.py — idempotent operator-provisioning script for Mintkey.

Creates (or repairs) a human operator who can log in via the Admin UI / Keycloak OIDC.
Three records are required for a working login:
  1. Keycloak user_entity in realm 'mintkey' (with optional platform-admin role)
  2. operators row in the mintkey DB
  3. operator_tenant_memberships row in the mintkey DB

All steps are idempotent: re-running for an existing operator adds missing
pieces without erroring or duplicating.

Usage (inside compose network, e.g. via `make create-operator`):
  python create_operator.py --email foo@mintkey.internal --display-name "Foo Bar"
  python create_operator.py --email foo@mintkey.internal --display-name "Foo Bar" --dry-run
  python create_operator.py --email adminus@mintkey.internal --display-name Adminus \
      --tenant-id ce79c39d-33de-4689-b827-2e926cb5f2c7 --platform-admin

Environment variables (identical to seed-job/main.py):
  PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD — Postgres connection
  KEYCLOAK_ADMIN, KEYCLOAK_ADMIN_PASSWORD — master-realm admin credentials
  MINTKEY_KEYCLOAK_INTERNAL_URL — e.g. http://keycloak:8443 (compose-network URL)
"""
from __future__ import annotations

import argparse
import os
import secrets
import sys
import uuid

import psycopg2
import requests

# ---------------------------------------------------------------------------
# Re-use seed-job primitives verbatim
# ---------------------------------------------------------------------------

_KC_INTERNAL_URL = os.getenv(
    "MINTKEY_KEYCLOAK_INTERNAL_URL", "http://keycloak:8443"
).rstrip("/")
_KC_ADMIN = os.getenv("KEYCLOAK_ADMIN", "admin")
_KC_ADMIN_PASSWORD = os.getenv("KEYCLOAK_ADMIN_PASSWORD", "changeme")

DEFAULT_TENANT_SLUG = "t_default"


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
    return resp.json()["access_token"]


def _kc_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _build_dsn() -> str:
    host = os.getenv("PGHOST", "localhost")
    port = os.getenv("PGPORT", "5432")
    db = os.getenv("PGDATABASE", "postgres")
    user = os.getenv("PGUSER", "mintkey_migrate")
    password = os.getenv("PGPASSWORD", "")
    return f"postgresql://{user}:{password}@{host}:{port}/{db}"


# ---------------------------------------------------------------------------
# Step A: Keycloak user (generalised from _ensure_admin_user)
# ---------------------------------------------------------------------------


def _ensure_kc_user(token: str, email: str, first_name: str, last_name: str, dry_run: bool) -> str:
    """Ensure a Keycloak user exists in realm 'mintkey'; return user UUID.

    If the user already exists, its UUID is returned unchanged (idempotent).
    In dry-run mode no requests are made; returns a placeholder UUID.
    """
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
        print(f"[KC] User '{email}' already exists (id={user_uuid}) — reusing.")
        return user_uuid

    if dry_run:
        print(f"[DRY-RUN][KC] Would CREATE user '{email}' (firstName={first_name}, lastName={last_name}) in realm mintkey.")
        return "dry-run-placeholder-uuid"

    create_resp = requests.post(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/users",
        headers=_kc_headers(token),
        json={
            "username": email,
            "email": email,
            "enabled": True,
            "emailVerified": True,
            "firstName": first_name,
            "lastName": last_name,
        },
        timeout=15,
    )
    create_resp.raise_for_status()

    # Re-fetch to get UUID (Keycloak returns 201 with no body)
    refetch = requests.get(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/users",
        params={"email": email},
        headers=_kc_headers(token),
        timeout=15,
    )
    refetch.raise_for_status()
    user_uuid = refetch.json()[0]["id"]
    print(f"[KC] Created user '{email}' (id={user_uuid}).")
    return user_uuid


# ---------------------------------------------------------------------------
# Step B: Set password (from _sync_admin_password, simplified for plain-text)
# ---------------------------------------------------------------------------


def _set_kc_password(token: str, user_uuid: str, password: str, dry_run: bool) -> None:
    """Set/reset the Keycloak user's password (non-temporary)."""
    if dry_run:
        print(f"[DRY-RUN][KC] Would SET password for user id={user_uuid}.")
        return
    resp = requests.put(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/users/{user_uuid}/reset-password",
        headers=_kc_headers(token),
        json={"type": "password", "value": password, "temporary": False},
        timeout=15,
    )
    resp.raise_for_status()
    print(f"[KC] Password set for user id={user_uuid}.")


# ---------------------------------------------------------------------------
# Step C: Assign platform-admin role (from _assign_platform_admin_role)
# ---------------------------------------------------------------------------


def _ensure_platform_admin_role(token: str, user_uuid: str, dry_run: bool) -> None:
    """Assign mintkey-platform-admin realm role (idempotent set-add)."""
    role_resp = requests.get(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/roles/mintkey-platform-admin",
        headers=_kc_headers(token),
        timeout=15,
    )
    role_resp.raise_for_status()
    role = role_resp.json()

    if dry_run:
        print(f"[DRY-RUN][KC] Would ASSIGN role 'mintkey-platform-admin' to user id={user_uuid}.")
        return

    assign_resp = requests.post(
        f"{_KC_INTERNAL_URL}/admin/realms/mintkey/users/{user_uuid}/role-mappings/realm",
        headers=_kc_headers(token),
        json=[role],
        timeout=15,
    )
    assign_resp.raise_for_status()
    print(f"[KC] Role 'mintkey-platform-admin' assigned to user id={user_uuid}.")


# ---------------------------------------------------------------------------
# Step D: operators row (from seed_bootstrap_operator)
# ---------------------------------------------------------------------------


def _ensure_operator_row(
    conn: psycopg2.extensions.connection,
    tenant_id: str,
    email: str,
    display_name: str,
    is_platform_admin: bool,
    dry_run: bool,
) -> str:
    """INSERT operator row if missing; return operator UUID."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id FROM operators WHERE email = %s",
            (email,),
        )
        row = cur.fetchone()
        if row is not None:
            op_id = str(row[0])
            print(f"[DB] operators row for '{email}' already exists (id={op_id}) — reusing.")
            return op_id

    if dry_run:
        print(
            f"[DRY-RUN][DB] Would INSERT operators row: "
            f"email={email}, display_name={display_name}, "
            f"tenant_id={tenant_id}, is_platform_admin={is_platform_admin}, "
            f"oidc_sub=NULL, internal_password_hash=NULL, status=active."
        )
        return "dry-run-placeholder-operator-id"

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operators
              (tenant_id, email, display_name, internal_password_hash, oidc_sub, is_platform_admin, status)
            VALUES (%s::uuid, %s, %s, NULL, NULL, %s, 'active')
            RETURNING id
            """,
            (tenant_id, email, display_name, is_platform_admin),
        )
        op_id = str(cur.fetchone()[0])
    print(f"[DB] Created operators row for '{email}' (id={op_id}).")
    return op_id


# ---------------------------------------------------------------------------
# Step E: operator_tenant_memberships row
# ---------------------------------------------------------------------------


def _ensure_membership_row(
    conn: psycopg2.extensions.connection,
    operator_id: str,
    tenant_id: str,
    dry_run: bool,
) -> None:
    """INSERT operator_tenant_memberships with role='Admin' (ON CONFLICT DO NOTHING)."""
    if dry_run:
        print(
            f"[DRY-RUN][DB] Would INSERT operator_tenant_memberships: "
            f"operator_id={operator_id}, tenant_id={tenant_id}, role=Admin."
        )
        return

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO operator_tenant_memberships (operator_id, tenant_id, role)
            VALUES (%s::uuid, %s::uuid, 'Admin')
            ON CONFLICT (operator_id, tenant_id) DO NOTHING
            """,
            (operator_id, tenant_id),
        )
        inserted = cur.rowcount
    if inserted:
        print(f"[DB] Created operator_tenant_memberships row for operator_id={operator_id}.")
    else:
        print(f"[DB] operator_tenant_memberships row already exists for operator_id={operator_id} — skipped.")


# ---------------------------------------------------------------------------
# Tenant resolution
# ---------------------------------------------------------------------------


def _resolve_tenant_id(conn: psycopg2.extensions.connection, tenant_id: str | None) -> str:
    """Return provided tenant_id or look up t_default."""
    if tenant_id:
        return tenant_id
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM tenants WHERE slug = %s", (DEFAULT_TENANT_SLUG,))
        row = cur.fetchone()
    if row is None:
        raise RuntimeError(
            f"Default tenant '{DEFAULT_TENANT_SLUG}' not found. "
            "Pass --tenant-id explicitly."
        )
    return str(row[0])


# ---------------------------------------------------------------------------
# Main entrypoint
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Idempotently provision a Mintkey operator (Keycloak + DB rows)."
    )
    parser.add_argument("--email", required=True, help="Operator email (used as KC username)")
    parser.add_argument("--display-name", required=True, dest="display_name",
                        help="Human-readable display name")
    parser.add_argument("--password", default=None,
                        help="Initial Keycloak password. If omitted, a random one is generated and printed.")
    parser.add_argument("--tenant-id", default=None, dest="tenant_id",
                        help="Tenant UUID to join. Defaults to t_default.")
    parser.add_argument("--platform-admin", dest="platform_admin",
                        action="store_true", default=True,
                        help="Grant mintkey-platform-admin realm role (default: true)")
    parser.add_argument("--no-platform-admin", dest="platform_admin",
                        action="store_false",
                        help="Do NOT grant mintkey-platform-admin realm role")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", default=False,
                        help="Print planned actions; write nothing.")
    args = parser.parse_args(argv)

    # Split display_name into first/last for Keycloak
    parts = args.display_name.split(None, 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else ""

    # Generate password if not provided
    generated_password = False
    password = args.password
    if not password:
        password = secrets.token_urlsafe(24)
        generated_password = True

    if args.dry_run:
        print("=== DRY RUN — no writes will be made ===")

    # --- DB connection ---
    dsn = _build_dsn()
    conn = psycopg2.connect(dsn)
    conn.autocommit = True

    try:
        # Resolve tenant
        tenant_id = _resolve_tenant_id(conn, args.tenant_id)
        print(f"Tenant: {tenant_id}")

        # --- Keycloak steps ---
        token = _kc_admin_token()
        user_uuid = _ensure_kc_user(token, args.email, first_name, last_name, args.dry_run)

        # Always set/update the password (non-dry-run); for existing users this
        # resets to the provided/generated value — callers can skip by setting
        # --password to the existing value.
        if not args.dry_run:
            _set_kc_password(token, user_uuid, password, args.dry_run)
        else:
            _set_kc_password(token, user_uuid, password, args.dry_run)

        if args.platform_admin:
            _ensure_platform_admin_role(token, user_uuid, args.dry_run)

        # --- DB steps ---
        operator_id = _ensure_operator_row(
            conn, tenant_id, args.email, args.display_name, args.platform_admin, args.dry_run
        )
        _ensure_membership_row(conn, operator_id, tenant_id, args.dry_run)

    finally:
        conn.close()

    if args.dry_run:
        print("=== DRY RUN complete — nothing written ===")
    else:
        print("\nOperator provisioned successfully.")
        if generated_password:
            print(f"  GENERATED PASSWORD (save this — shown only once): {password}")
        print(f"  email:       {args.email}")
        print(f"  tenant:      {tenant_id}")
        print(f"  platform-admin: {args.platform_admin}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
