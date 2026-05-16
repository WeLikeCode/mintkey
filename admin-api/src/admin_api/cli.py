"""
Mintkey Admin CLI — break-glass and operator management.

Entry point: python -m admin_api.cli

Commands:
  mintkey admin reset-password --email <e>
      Generate a random 32-char password, Argon2id-hash it, store in operators,
      print plaintext once. (D2-b break-glass)

  mintkey admin clear-password --email <e>
      Set internal_password_hash = NULL. Disables internal-login for that operator.

Source: D2-b (CLI break-glass); ADR-0014.7 (audit events).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import secrets
import sys
import uuid
from typing import Any

_logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


async def _fetch_operator_by_email(email: str) -> Any | None:
    """Return operator row or None using platform_admin_view bypass."""
    from admin_api.db.session import AsyncSessionLocal
    from sqlalchemy import text

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await db.execute(
                text(
                    "SELECT set_config('app.current_tenant',"
                    " '00000000-0000-0000-0000-000000000000', true),"
                    " set_config('app.platform_admin_view', 'on', true)"
                )
            )
            result = await db.execute(
                text(
                    "SELECT id, tenant_id, email, internal_password_hash"
                    " FROM operators WHERE email = :email"
                ),
                {"email": email},
            )
            return result.fetchone()


async def _cmd_reset_password(email: str) -> int:
    """Set a fresh Argon2id hash; print plaintext once."""
    import argon2 as _argon2

    ph = _argon2.PasswordHasher()

    row = await _fetch_operator_by_email(email)
    if row is None:
        print(f"ERROR: operator not found for email '{email}'", file=sys.stderr)
        return 1

    operator_id = row[0]
    tenant_id = row[1]

    plaintext = secrets.token_urlsafe(32)
    hashed = ph.hash(plaintext)

    from admin_api.db.session import AsyncSessionLocal
    from sqlalchemy import text
    from mintkey_models.audit import audit_emit
    from mintkey_models.tenant_ctx import set_tenant_context

    tid = uuid.UUID(str(tenant_id))
    oid = uuid.UUID(str(operator_id))

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await set_tenant_context(db, tid)

            await db.execute(
                text(
                    "UPDATE operators SET internal_password_hash = :hashed WHERE id = :oid"
                ),
                {"hashed": hashed, "oid": str(oid)},
            )

            await audit_emit(
                session=db,
                tenant_id=tid,
                event_type="operator.password.reset",
                actor_id=oid,
                actor_type="operator",
                target_id=oid,
                target_type="operator",
                payload={
                    "email": email,
                    "method": "cli_break_glass",
                },
            )

    print(
        f"Temporary password for {email} (Argon2id hash stored): {plaintext}\n"
        f"\n"
        f"Log in via /v1/auth/internal-login. After Keycloak is back, run:\n"
        f"  mintkey admin clear-password --email {email}\n"
        f"to remove the hash."
    )
    return 0


async def _cmd_clear_password(email: str) -> int:
    """Set internal_password_hash = NULL, disabling internal login."""
    row = await _fetch_operator_by_email(email)
    if row is None:
        print(f"ERROR: operator not found for email '{email}'", file=sys.stderr)
        return 1

    operator_id = row[0]
    tenant_id = row[1]

    from admin_api.db.session import AsyncSessionLocal
    from sqlalchemy import text
    from mintkey_models.audit import audit_emit
    from mintkey_models.tenant_ctx import set_tenant_context

    tid = uuid.UUID(str(tenant_id))
    oid = uuid.UUID(str(operator_id))

    async with AsyncSessionLocal() as db:
        async with db.begin():
            await set_tenant_context(db, tid)

            await db.execute(
                text(
                    "UPDATE operators SET internal_password_hash = NULL WHERE id = :oid"
                ),
                {"oid": str(oid)},
            )

            await audit_emit(
                session=db,
                tenant_id=tid,
                event_type="operator.password.cleared",
                actor_id=oid,
                actor_type="operator",
                target_id=oid,
                target_type="operator",
                payload={
                    "email": email,
                    "method": "cli_break_glass",
                },
            )

    print(f"Cleared internal password hash for {email}.")
    return 0


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mintkey",
        description="Mintkey Admin CLI",
    )
    subparsers = parser.add_subparsers(dest="group", required=True)

    # mintkey admin <subcommand>
    admin_parser = subparsers.add_parser("admin", help="Operator administration commands")
    admin_sub = admin_parser.add_subparsers(dest="command", required=True)

    # mintkey admin reset-password --email <e>
    rp = admin_sub.add_parser(
        "reset-password",
        help="Generate a break-glass Argon2id password hash for the operator",
    )
    rp.add_argument("--email", required=True, help="Operator email address")

    # mintkey admin clear-password --email <e>
    cp = admin_sub.add_parser(
        "clear-password",
        help="Clear the internal password hash (re-disables internal login)",
    )
    cp.add_argument("--email", required=True, help="Operator email address")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.group == "admin":
        if args.command == "reset-password":
            return asyncio.run(_cmd_reset_password(args.email))
        elif args.command == "clear-password":
            return asyncio.run(_cmd_clear_password(args.email))

    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
