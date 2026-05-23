"""
Audit chain verification job — CLI entrypoint.

Connects to the Postgres database, reads audit_events for each tenant
in chain order, and runs verify_chain().  Exits 0 if all chains are intact,
1 if any chain is broken.

Usage:
    python main.py [--tenant-id <id>]

Environment variables:
    DATABASE_URL  — asyncpg-compatible DSN (e.g. postgresql+asyncpg://...)

Source: T-1.13.2; ADR-0014.7; Req AUD-4.
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys

log = logging.getLogger(__name__)


async def _run(tenant_id_filter: str | None) -> int:
    """
    Connect to the DB, load audit events, verify chains.
    Returns exit code: 0 = ok, 1 = broken chain or error.
    """
    # Import here so the module is importable without DB deps installed
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine
    except ImportError:
        log.error("sqlalchemy not installed — cannot connect to DB")
        return 1

    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        log.error("DATABASE_URL environment variable is not set")
        return 1

    from verify import AuditEvent, verify_chain

    engine = create_async_engine(database_url)
    all_ok = True

    async with engine.begin() as conn:
        # Determine which tenants to check
        if tenant_id_filter:
            tenant_ids_result = await conn.execute(
                text("SELECT id FROM tenants WHERE id = :tid"),
                {"tid": tenant_id_filter},
            )
        else:
            tenant_ids_result = await conn.execute(
                text("SELECT id FROM tenants ORDER BY created_at")
            )
        tenant_rows = tenant_ids_result.fetchall()

        for (tenant_id,) in tenant_rows:
            result = await conn.execute(
                text(
                    "SELECT id, event_type, tenant_id, payload, hash, prev_hash"
                    " FROM audit_events"
                    " WHERE tenant_id = :tid"
                    " ORDER BY at ASC"
                ),
                {"tid": str(tenant_id)},
            )
            rows = result.fetchall()

            events = [
                AuditEvent(
                    id=str(row.id),
                    event_type=row.event_type,
                    tenant_id=str(row.tenant_id),
                    payload=row.payload or {},
                    hash=bytes(row.hash),
                    prev_hash=bytes(row.prev_hash),
                )
                for row in rows
            ]

            vr = verify_chain(events)
            if vr.ok:
                log.info(
                    "tenant %s: chain intact (%d events)", tenant_id, vr.chain_length
                )
            else:
                log.error(
                    "tenant %s: chain BROKEN at event %s — %s",
                    tenant_id,
                    vr.first_bad_event_id,
                    vr.message,
                )
                all_ok = False

    await engine.dispose()
    return 0 if all_ok else 1


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Verify Mintkey audit chain integrity")
    parser.add_argument(
        "--tenant-id",
        default=None,
        help="Verify only this tenant (UUID). Omit to verify all tenants.",
    )
    args = parser.parse_args()

    exit_code = asyncio.run(_run(args.tenant_id))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
