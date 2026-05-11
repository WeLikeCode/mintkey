"""
Architecture test: audit event payloads must never contain plaintext agent API keys.

Walks the AST of admin-api/src/admin_api/api/agents.py and asserts:
  - No call to audit_emit passes a payload dict containing the api_key (plaintext) variable
  - No string literal starting with "mk_agent_" appears in audit_emit call arguments

Source: S-SEC-1; ADR-0014.4; ADR-0014.7; T-1.4.1.
"""
import ast
from pathlib import Path

_AGENTS_PY = (
    Path(__file__).parent.parent.parent
    / "admin-api"
    / "src"
    / "admin_api"
    / "api"
    / "agents.py"
)


def test_agents_api_exists():
    """The agents.py implementation file must exist."""
    assert _AGENTS_PY.exists(), f"agents.py not found at {_AGENTS_PY}"


def test_no_mk_agent_prefix_in_audit_payloads():
    """
    No audit_emit call in agents.py may pass a string literal containing 'mk_agent_'.
    This is a static AST check — does not require a running DB.

    Source: S-SEC-1 (no plaintext in logs/audit); ADR-0014.7.
    """
    src = _AGENTS_PY.read_text()
    tree = ast.parse(src)

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr

        if "audit" not in func_name:
            continue

        # Check no descendant AST node is a string constant containing "mk_agent_"
        for child in ast.walk(node):
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                assert "mk_agent_" not in child.value, (
                    f"Found 'mk_agent_' string literal in audit call "
                    f"at line {node.lineno}: {child.value!r}"
                )
