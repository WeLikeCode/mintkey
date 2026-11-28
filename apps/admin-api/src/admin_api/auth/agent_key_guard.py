"""Guard for agent-route key checks: key shape and a bounded capacity of its own.

A request to ``/v1/agent/`` may carry millions of well-formed but unknown
``mk_agent_`` keys.  Those requests must not reach a password-hash verify
through the capacity that ``/v1/internal/validate-agent-key`` uses, and a
bearer that is not ``mk_agent_`` followed by the exact length and alphabet of
a real key must be answered ``401 mintkey:auth_required`` without any verify.

Source: openspec/changes/agent-service-routes-fix-1 — Feedback FB-001
(requirement "Unknown agent keys on the agent routes cannot slow the MCP
server's key checks").
"""

from __future__ import annotations

import asyncio
import os

#: The prefix of every agent API key (see ``agents._generate_agent_api_key``).
_AGENT_KEY_PREFIX = "mk_agent_"

#: The Crockford base32 alphabet an agent key's payload uses.
_CROCKFORD = frozenset("0123456789ABCDEFGHJKMNPQRSTVWXYZ")

#: A real agent key carries 52 payload characters (32 random bytes, base32).
_AGENT_KEY_PAYLOAD_LENGTH = 52

#: Bound the agent routes' own Argon2id verifies independently of the
#: ``/v1/internal/validate-agent-key`` capacity.  A request that finds this
#: capacity full is refused at once (503) rather than queued behind it.
_AGENT_VERIFY_CONCURRENCY = max(
    1, int(os.getenv("MINTKEY_AGENT_ROUTE_VERIFY_CONCURRENCY", "4"))
)
_agent_verify_capacity = asyncio.Semaphore(_AGENT_VERIFY_CONCURRENCY)


def agent_key_shape_is_valid(api_key: str) -> bool:
    """Return True when ``api_key`` is ``mk_agent_`` plus 52 Crockford chars.

    A real agent key is ``mk_agent_`` followed by 52 characters of the
    Crockford base32 alphabet (uppercase, no ``I``, ``L``, ``O`` or ``U``).
    """
    if not api_key.startswith(_AGENT_KEY_PREFIX):
        return False
    payload = api_key[len(_AGENT_KEY_PREFIX):]
    if len(payload) != _AGENT_KEY_PAYLOAD_LENGTH:
        return False
    return all(char in _CROCKFORD for char in payload)


def agent_verify_capacity() -> asyncio.Semaphore:
    """Return the agent routes' own bounded verify capacity.

    The semaphore is the one the ``/v1/agent/`` routes use for their key
    checks; it is separate from the semaphore behind
    ``/v1/internal/validate-agent-key``.
    """
    return _agent_verify_capacity
