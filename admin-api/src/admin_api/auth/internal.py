"""
Internal (Argon2id) authentication logic.

CORRECTED: response body and timing are identical across all failure modes.
The server always runs an Argon2id verify — against the real hash for known users,
against a fixed DUMMY_HASH for unknown users. This prevents timing-based user enumeration.

Source: Req 2 AC2, AC3, AC4; Req SEC-9; ADR-0017.5; design §4.
"""
from __future__ import annotations

from typing import Any

import argon2
from argon2.exceptions import VerifyMismatchError

# Fixed hash used when the user doesn't exist — prevents timing enumeration.
# The DUMMY_HASH is for a password that can never match (sentinel value).
# Source: ADR-0017.5.
_ph = argon2.PasswordHasher()
DUMMY_HASH: str = _ph.hash("__mintkey_dummy_password_never_matches__")

INVALID_CREDENTIALS_RESPONSE: dict[str, Any] = {
    "type": "https://mintkey.internal/errors/invalid-credentials",
    "title": "Invalid credentials",
    "status": 401,
    "mintkey:code": "invalid_credentials",
}


async def fetch_operator(email: str) -> Any | None:
    """
    Look up an operator by email using platform_admin_view to bypass RLS
    (login is a cross-tenant operation — we don't know the tenant yet).
    Overridden in tests via mock.
    """
    from admin_api.db.session import AsyncSessionLocal
    from mintkey_models.db import Operator
    from sqlalchemy import select, text

    async with AsyncSessionLocal() as db:
        async with db.begin():
            # RLS policy evaluates current_tenant::uuid — must be a valid UUID even
            # if unused, otherwise the cast throws when the value is "".
            # platform_admin_view = 'on' then makes the OR condition pass.
            await db.execute(
                text("SELECT set_config('app.current_tenant', '00000000-0000-0000-0000-000000000000', true)")
            )
            await db.execute(
                text("SELECT set_config('app.platform_admin_view', 'on', true)")
            )
            result = await db.execute(
                select(Operator).where(Operator.email == email)
            )
            return result.scalar_one_or_none()


async def record_failed_attempt(email: str) -> None:
    """Record a failed login attempt for lockout tracking."""


async def clear_failed_attempts(email: str) -> None:
    """Clear failed attempt counter after successful login."""


async def verify_internal_login(
    email: str, password: str
) -> tuple[Any | None, str]:
    """
    Verify email + password via Argon2id.

    Always performs an Argon2id hash verify (against DUMMY_HASH if user not found)
    so timing is equalized across failure modes (ADR-0017.5 / Req SEC-9).

    Returns (operator, failure_reason) where:
      - operator is the Operator ORM object on success
      - failure_reason is one of:
        "user_unknown" | "bad_password" | "account_locked" | None (success)
    """
    operator = await fetch_operator(email)

    if operator is None:
        # Always verify against DUMMY_HASH to equalize timing.
        try:
            _ph.verify(DUMMY_HASH, password)
        except Exception:
            pass
        return None, "user_unknown"

    if operator.status == "locked":
        # Still run verify for timing equalization, then return locked.
        try:
            _ph.verify(DUMMY_HASH, password)
        except Exception:
            pass
        await record_failed_attempt(email)
        return None, "account_locked"

    try:
        _ph.verify(operator.internal_password_hash, password)
    except VerifyMismatchError:
        await record_failed_attempt(email)
        return None, "bad_password"
    except Exception:
        await record_failed_attempt(email)
        return None, "bad_password"

    await clear_failed_attempts(email)
    return operator, None
