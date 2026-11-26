"""
Unit tests: the agent-governance background document has its shape.

Task 2.1 of tenant-session-routes. The document is background only: it must
exist, stay short, carry exactly the six level-two headings in order after its
level-one title, and not read as a second source of requirements (no SHALL or
MUST).

Source: tenant-session-routes › A background document describes the governance model.
"""
from __future__ import annotations

import os

import pytest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
DOC_PATH = os.path.join(REPO_ROOT, "docs/architecture/agent-governance.md")

_EXPECTED_HEADINGS = [
    "## Terms",
    "## Roles and operations",
    "## Ownership and grants",
    "## Access requests",
    "## Agent-supplied targets",
    "## Where it lives",
]

_NORMATIVE_KEYWORDS = ("SHALL", "MUST")


@pytest.mark.l4("C-063b76ce")
def test_document_has_its_shape() -> None:
    assert os.path.isfile(DOC_PATH), f"missing background document: {DOC_PATH}"

    with open(DOC_PATH, encoding="utf-8") as handle:
        text = handle.read()

    assert len(text) <= 6000, (
        f"{DOC_PATH} is {len(text)} characters; the limit is 6000"
    )

    lines = text.splitlines()
    assert lines, f"{DOC_PATH} is empty"
    assert lines[0].startswith("# "), (
        f"{DOC_PATH} must start with a level-one title, got {lines[0]!r}"
    )

    headings = [line for line in lines if line.startswith("## ")]
    assert headings == _EXPECTED_HEADINGS, (
        "unexpected level-two headings:\n"
        f"  expected: {_EXPECTED_HEADINGS}\n"
        f"  found:    {headings}"
    )

    for keyword in _NORMATIVE_KEYWORDS:
        assert keyword not in text, (
            f"{DOC_PATH} contains the normative keyword {keyword}; "
            "the document is background only"
        )
