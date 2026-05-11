"""
FastAPI dependency: async DB session.

Yields a session with an open transaction. The transaction commits on
success and rolls back on exception.

Source: design §4; ADR-0008; ADR-0015.
"""
from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from admin_api.db.session import AsyncSessionLocal


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession with an open transaction."""
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
