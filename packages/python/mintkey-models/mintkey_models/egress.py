"""
Agent egress policy: the rule for URLs an agent supplies as service targets.

Signature-only stubs for the red step; the behaviour is added in the green
step.

Source: openspec/changes/agent-principal-and-egress (task 1.1; spec
agent-egress-policy, requirement "Agent-supplied URLs must be public https
targets").
"""

from __future__ import annotations


class TargetNotAllowed(Exception):
    pass


async def resolve_host(host: str) -> list[str]:
    raise NotImplementedError


def egress_deny_names() -> tuple[str, ...]:
    raise NotImplementedError


def address_is_public(address: str) -> bool:
    raise NotImplementedError


async def check_agent_target_url(url: str) -> None:
    raise NotImplementedError
