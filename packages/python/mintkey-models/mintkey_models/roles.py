"""
Shared agent-role vocabulary.

The operator API and the MCP server name an agent's role with the same two
values and the same fallback (design D1, D4).

Source: openspec/changes/agent-roles-and-ownership (D1, D4).
"""

from __future__ import annotations

from typing import Final

ROLE_CONSUMER: Final[str] = "consumer"
ROLE_PUBLISHER: Final[str] = "publisher"
AGENT_ROLES: Final[tuple[str, ...]] = ("consumer", "publisher")


def normalize_role(value: object) -> str:
    """Return a role name in ``AGENT_ROLES`` unchanged, else ``"consumer"``.

    Anything that is not a known role — ``None``, the empty string, an
    unknown name, a non-string — falls back to the less powerful role.
    """
    if isinstance(value, str) and value in AGENT_ROLES:
        return value
    return ROLE_CONSUMER
