"""
Server-side session storage in the `sessions` table.

Source: design §4 auth/sessions.py; Req 2 AC2.
"""
from __future__ import annotations

import secrets
from typing import Any
from uuid import UUID


async def create_session(operator_id: UUID, tenant_id: UUID) -> str:
    """
    Create a session and return an opaque session token.
    Stub: full DB insert wired in T-1.1.2.
    """
    return secrets.token_urlsafe(32)


async def validate_session(token: str) -> Any | None:
    """
    Look up a session by token. Returns operator context or None if invalid/expired.
    Stub: wired in T-1.1.2.
    """
    return None
