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


def agent_key_shape_is_valid(api_key: str) -> bool:
    """Return True when ``api_key`` is ``mk_agent_`` plus 52 Crockford chars.

    A real agent key is ``mk_agent_`` followed by 52 characters of the
    Crockford base32 alphabet (uppercase, no ``I``, ``L``, ``O`` or ``U``).
    """
    raise NotImplementedError


def agent_verify_capacity() -> asyncio.Semaphore:
    """Return the agent routes' own bounded verify capacity.

    The semaphore is the one the ``/v1/agent/`` routes use for their key
    checks; it is separate from the semaphore behind
    ``/v1/internal/validate-agent-key``.
    """
    raise NotImplementedError
