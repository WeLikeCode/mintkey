"""
Access-request expiry sweep — CLI entrypoint.

Connects to the Postgres database and, for each tenant, flips that tenant's
elapsed ``pending`` access requests to ``expired`` and emits one
``access_request.expired`` audit event per row (``actor_type: system``) through
the single ``audit.emit()`` chokepoint. Exits 0 on success, 1 on error.

This is the scheduled half of the expiration mechanism (design §Expiration
Mechanism): the lazy-on-read guard in ``admin_api.services.access_requests``
prevents any expired row from being actioned, and this sweep persists the flip
and emits the system-actor audit event that Req 10.1 requires.

It follows the ``apps/audit-verify-job/`` precedent for cross-tenant iteration:
enumerate the tenants, then work each one. Unlike the read-only verify job, the
sweep MUTATES state, so it uses one transaction per tenant — the actual sweep
logic (RLS tenant GUC + status flip + per-row audit emit) lives in
``admin_api.services.access_requests.sweep_tenant_expired`` and runs inside that
transaction so the flip and its audit event are atomic (Req 10.1, 10.6).

Usage:
    python main.py [--tenant-id <uuid>]

Environment variables:
    DATABASE_URL  — asyncpg-compatible DSN (e.g. postgresql+asyncpg://...)

Source: T-5.7; design §Expiration Mechanism; Req 9.2, 9.4, 10.1, 10.5;
        ADR-0008 (tenant GUC), ADR-0014.7 (audit chokepoint);
        apps/audit-verify-job/main.py (cross-tenant job precedent).
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import uuid

log = logging.getLogger(__name__)


async def _run(tenant_id_filter: str | None) -> int:
    """
    Connect to the DB, enumerate tenants, sweep each tenant's elapsed rows.
    Returns exit code: 0 = ok, 1 = error.
    """
    # Import here so the module is importable without DB deps installed
    # (mirrors apps/audit-verify-job/main.py).
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import (
            AsyncSession,
            async_sessionmaker,
            create_async_engine,
        )
    except ImportError:
        log.error("sqlalchemy not installed — cannot connect to DB")
        return 1

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL environment variable is not set")
        return 1

    from admin_api.services.access_requests import sweep_tenant_expired

    engine = create_async_engine(database_url)
    sessionmaker = async_sessionmaker(
        bind=engine, class_=AsyncSession, expire_on_commit=False
    )
    total_expired = 0
    all_ok = True

    try:
        # Enumerate the tenants to sweep. Reading the tenant list needs no
        # tenant GUC (the tenants table is not RLS-scoped per tenant); the
        # sweep itself sets app.current_tenant per tenant inside its own
        # transaction (P-3, ADR-0008).
        async with engine.connect() as conn:
            if tenant_id_filter:
                result = await conn.execute(
                    text("SELECT id FROM tenants WHERE id = :tid"),
                    {"tid": tenant_id_filter},
                )
            else:
                result = await conn.execute(
                    text("SELECT id FROM tenants ORDER BY created_at")
                )
            tenant_ids = [row[0] for row in result.fetchall()]

        for tenant_id in tenant_ids:
            # One transaction per tenant so the status flip + per-row audit
            # emit are atomic; a failure on one tenant does not roll back
            # tenants already swept (Req 10.6).
            try:
                async with sessionmaker() as session:
                    async with session.begin():
                        count = await sweep_tenant_expired(
                            session, tenant_id=uuid.UUID(str(tenant_id))
                        )
                total_expired += count
                if count:
                    log.info("tenant %s: expired %d request(s)", tenant_id, count)
            except Exception:  # noqa: BLE001 — one tenant's failure must not abort the rest
                log.exception("tenant %s: expiry sweep failed", tenant_id)
                all_ok = False
    finally:
        await engine.dispose()

    log.info("expiry sweep complete: %d request(s) expired total", total_expired)
    return 0 if all_ok else 1


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(
        description="Expire elapsed pending Mintkey access requests"
    )
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="Sweep only this tenant (UUID). Omit to sweep all tenants.",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(_run(args.tenant_id))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
