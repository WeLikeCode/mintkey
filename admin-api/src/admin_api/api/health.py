"""
Health and readiness endpoints.

GET /v1/health  → liveness (no dependency checks, always 200)
GET /v1/ready   → readiness (checks DB, Liquibase, Vault Adapter, change-channel)

Source: Req 1 AC7, AC8; design §4.
"""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


async def check_db() -> bool:
    """Return True when DB is reachable. Overridden in tests via mock."""
    from admin_api.db.session import engine
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


async def check_liquibase() -> bool:
    """Return True when databasechangelog has at least one row."""
    from admin_api.db.session import engine
    from sqlalchemy import text

    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text("SELECT COUNT(*) FROM databasechangelog")
            )
            return (result.scalar() or 0) > 0
    except Exception:
        return False


async def check_vault_adapter() -> bool:
    """Return True when Vault Adapter gRPC ping succeeds. Overridden in tests via mock."""
    return False  # stub: implemented fully in T-1.0.4


async def check_change_channel() -> bool:
    """Return True when the LISTEN change-channel is attached. Overridden in tests via mock."""
    return False  # stub: implemented fully in T-1.0.8


@router.get("/v1/health")
async def health() -> JSONResponse:
    """Liveness probe — always 200. Source: Req 1 AC7."""
    return JSONResponse({"status": "ok"})


@router.get("/v1/ready")
async def ready() -> JSONResponse:
    """
    Readiness probe — 200 only when all four checks pass.
    Source: Req 1 AC8, design §4.
    """
    checks = {
        "db": await check_db(),
        "liquibase": await check_liquibase(),
        "vault_adapter": await check_vault_adapter(),
        "change_channel": await check_change_channel(),
    }
    failing = [name for name, ok in checks.items() if not ok]
    if failing:
        return JSONResponse(
            status_code=503,
            content={"code": "mintkey:not_ready", "failing": failing},
        )
    return JSONResponse({"status": "ready"})
