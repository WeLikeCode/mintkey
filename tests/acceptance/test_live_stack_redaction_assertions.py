"""The live-stack acceptance tests pin the proxy's redaction marker.

Requirement: proxy-stored-target › task 4.1: live-stack acceptance tests not
updated (finding F-3e53e4bd).

The proxy replaces exactly the credential value it injected, so the mock
backend's ``received_key`` reaches the caller as ``[REDACTED]``.  The four
live-stack tests read that value back; they must assert the redaction marker
(and say why), never the registered secret.
"""
from __future__ import annotations

import ast
import io
import tokenize
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

LIVE_STACK_TESTS = {
    "test_e2e_smoke.py": ROOT / "tests" / "acceptance" / "test_e2e_smoke.py",
    "test_golden_path.py": ROOT / "tests" / "acceptance" / "test_golden_path.py",
    "test_data_plane_smoke.py": ROOT / "tests" / "acceptance" / "test_data_plane_smoke.py",
    "test_classical_key.py": ROOT / "tests" / "acceptance" / "test_classical_key.py",
}


def _segment(source: str, node: ast.AST) -> str:
    return ast.get_source_segment(source, node) or ""


def _received_key_aliases(tree: ast.AST, source: str) -> set[str]:
    """Names assigned from an expression that reads ``received_key``."""
    aliases: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and "received_key" in _segment(source, node.value):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    aliases.add(target.id)
    return aliases


def _refers_to_received_key(node: ast.AST, source: str, aliases: set[str]) -> bool:
    if isinstance(node, ast.Name) and node.id in aliases:
        return True
    return "received_key" in _segment(source, node)


def _received_key_comparisons(
    tree: ast.AST, source: str
) -> list[tuple[ast.cmpop, ast.AST]]:
    """Every ``assert`` comparison with ``received_key`` on one side."""
    aliases = _received_key_aliases(tree, source)
    comparisons: list[tuple[ast.cmpop, ast.AST]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assert):
            continue
        test = node.test
        if not isinstance(test, ast.Compare):
            continue
        for op, right in zip(test.ops, test.comparators):
            left = test.left
            if _refers_to_received_key(left, source, aliases):
                comparisons.append((op, right))
            elif _refers_to_received_key(right, source, aliases):
                comparisons.append((op, left))
    return comparisons


def _comments(source: str) -> list[str]:
    readline = io.StringIO(source).readline
    return [
        token.string
        for token in tokenize.generate_tokens(readline)
        if token.type == tokenize.COMMENT
    ]


@pytest.mark.l4("C-969b7732")
@pytest.mark.parametrize("name", sorted(LIVE_STACK_TESTS))
def test_C_969b7732_live_stack_test_asserts_the_redaction_marker(name: str) -> None:
    """Each live-stack test reads ``received_key`` back as ``[REDACTED]``."""
    path = LIVE_STACK_TESTS[name]
    source = path.read_text()
    tree = ast.parse(source)

    comparisons = _received_key_comparisons(tree, source)
    assert comparisons, (
        f"{name} never asserts on the mock backend's received_key: the proxy "
        "redacts the credential it injected and the test must pin that"
    )

    for op, expected in comparisons:
        assert isinstance(op, ast.Eq), (
            f"{name} compares received_key with {type(op).__name__}; the test "
            "must assert equality with the redaction marker"
        )
        assert isinstance(expected, ast.Constant) and expected.value == "[REDACTED]", (
            f"{name} compares received_key with {_segment(source, expected)!r}; "
            "expected the redaction marker '[REDACTED]' because the proxy "
            "replaces exactly the value it injected"
        )

    comments = _comments(source)
    assert any(
        "redact" in comment.lower() and "inject" in comment.lower()
        for comment in comments
    ), (
        f"{name} has no comment saying the proxy redacts the credential value "
        "it injected; the redaction marker alone does not explain the assertion"
    )
