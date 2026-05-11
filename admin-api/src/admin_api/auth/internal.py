"""
Internal (Argon2id) authentication logic.

CORRECTED: response body and timing are identical across all failure modes.
The server always runs an Argon2id verify — against the real hash for known users,
against a fixed DUMMY_HASH for unknown users. This prevents timing-based user enumeration.

Source: Req 2 AC2, AC3, AC4; Req SEC-9; ADR-0017.5; design §4.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

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
    Look up an operator by email. Returns None if not found.
    Overridden in tests via mock.
    Full implementation wired in T-1.1.2 (requires DB session injection).
    """
    return None


async def record_failed_attempt(email: str) -> None:
    """Record a failed login attempt for lockout tracking. Stub: wired in T-1.1.2."""


async def clear_failed_attempts(email: str) -> None:
    """Clear failed attempt counter after successful login. Stub: wired in T-1.1.2."""


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
