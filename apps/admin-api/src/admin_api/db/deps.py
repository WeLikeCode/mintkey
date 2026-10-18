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
    """Yield an AsyncSession with an open transaction.

    Declare it as ``Depends(get_db_session, scope="function")``. With FastAPI's default
    ``scope="request"`` the exit code below (the COMMIT) runs after the response has been sent,
    so a client that fires its next request right after a 201 can read the old state: a POST
    that creates a service or agent answered 201 and an immediately following GET of that id
    returned 404 in ~7 % of runs (apps/admin-ui e2e: 32-create-api-key, 34-confirm-actions).
    ``scope="function"`` commits before the response is sent.
    """
    async with AsyncSessionLocal() as session:
        async with session.begin():
            yield session
