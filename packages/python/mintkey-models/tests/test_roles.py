"""
Tests for the shared agent-role vocabulary.

Source: openspec/changes/agent-roles-and-ownership (task 1.1, design D1/D4).
"""
from __future__ import annotations

import pytest

from mintkey_models import roles
from mintkey_models.roles import normalize_role


@pytest.mark.l4("C-0faabce6")
def test_agent_roles_is_the_two_role_vocabulary() -> None:
    """C-0faabce6: AGENT_ROLES is exactly ("consumer", "publisher")."""
    # Stated as a literal: module constants belong to the implementation step.
    assert getattr(roles, "AGENT_ROLES", None) == ("consumer", "publisher")
    # Keep this test exercising the stubbed symbol too.
    assert normalize_role("consumer") == "consumer"


@pytest.mark.l4("C-0faabce6")
@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("publisher", "publisher"),
        ("consumer", "consumer"),
        (None, "consumer"),
        ("", "consumer"),
        ("admin", "consumer"),
        (5, "consumer"),
    ],
)
def test_normalize_role_keeps_known_roles_and_defaults_to_consumer(
    value: object, expected: str
) -> None:
    """C-0faabce6: a name in AGENT_ROLES is unchanged; anything else is consumer."""
    assert normalize_role(value) == expected
