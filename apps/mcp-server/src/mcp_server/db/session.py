"""
Async SQLAlchemy engine and session factory for mcp-server.

Source: ADR-0008 (bound parameter tenant context); ADR-0009 (MCP server stack).
"""
from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://mintkey_app:@localhost:5432/postgres",
)

engine = create_async_engine(DATABASE_URL, echo=False, pool_pre_ping=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session():
    """Yield an AsyncSession with an open transaction."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
