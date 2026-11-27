"""
Shared agent-role vocabulary.

The operator API and the MCP server name an agent's role with the same two
values and the same fallback (design D1, D4).

Source: openspec/changes/agent-roles-and-ownership (D1, D4).
"""

from __future__ import annotations


def normalize_role(value: object) -> str:
    raise NotImplementedError
