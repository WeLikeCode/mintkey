"""
Architecture test: zero SQL injection patterns (T-1.0.15).

Walks the AST of every .py file in admin-api/src/ and mcp-server/src/.
Asserts:
  (a) every text(...) call argument is a string literal (not an f-string,
      not a .format(), not a + concatenation with a non-constant)
  (b) no f-string in production code contains SQL keywords

Allowlist: files under tests/ are excluded (DDL fixtures may use f-strings).

Sources:
  - Req SEC-1, SEC-2 (no SQL injection)
  - design §4 (corrected — bound parameters via set_config + pg_notify(:channel,:payload))
  - ADR-0014 (no f-string interpolation into SQL)
"""
from __future__ import annotations

import ast
import os
from pathlib import Path
from typing import Generator

REPO_ROOT = Path(__file__).resolve().parents[2]

# Scan these directories for Python source files.
SCAN_DIRS = [
    REPO_ROOT / "admin-api" / "src",
    REPO_ROOT / "mcp-server" / "src",
]

# SQL keywords that must not appear inside f-strings in production code.
SQL_KEYWORDS = {
    "SELECT", "INSERT", "UPDATE", "DELETE",
    "SET LOCAL", "pg_notify", "set_config",
    "FROM", "WHERE", "JOIN",
}

# Skip test fixtures — they may use dynamic DDL.
ALLOWLIST_DIRS = {
    REPO_ROOT / "tests",
}


def _collect_py_files(dirs: list[Path]) -> Generator[Path, None, None]:
    for d in dirs:
        if not d.exists():
            continue
        for f in d.rglob("*.py"):
            if any(f.is_relative_to(a) for a in ALLOWLIST_DIRS):
                continue
            yield f


def _is_string_literal(node: ast.expr) -> bool:
    """Return True if the node is a safe string constant (not f-string, not concat with var)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return True
    if isinstance(node, ast.JoinedStr):
        return False  # f-string
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        # Allow only constant + constant; reject any var concatenation.
        return _is_string_literal(node.left) and _is_string_literal(node.right)
    return False


class SqlInjectionVisitor(ast.NodeVisitor):
    """Collects violations."""

    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self.violations: list[str] = []

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # Check text(...) calls from SQLAlchemy.
        if isinstance(node.func, ast.Name) and node.func.id == "text":
            if node.args:
                arg = node.args[0]
                if not _is_string_literal(arg):
                    self.violations.append(
                        f"{self.filepath}:{node.lineno}: "
                        f"text() called with non-literal argument (f-string or concatenation) "
                        f"— use bound parameters instead (ADR-0014)"
                    )
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:  # noqa: N802
        # Detect f-strings containing SQL keywords.
        src = ast.unparse(node)
        for kw in SQL_KEYWORDS:
            if kw.lower() in src.lower():
                self.violations.append(
                    f"{self.filepath}:{node.lineno}: "
                    f"f-string contains SQL keyword '{kw}' — "
                    f"use bound parameters instead (ADR-0014, Req SEC-1)"
                )
                break
        self.generic_visit(node)


def _scan_file(filepath: Path) -> list[str]:
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except SyntaxError as e:
        return [f"{filepath}: SyntaxError: {e}"]
    visitor = SqlInjectionVisitor(filepath)
    visitor.visit(tree)
    return visitor.violations


def test_no_sql_injection_in_admin_api_and_mcp_server() -> None:
    """
    Zero SQL injection patterns (f-string SQL, text() with dynamic arg).
    Source: T-1.0.15; Req SEC-1, SEC-2; ADR-0014.
    """
    files = list(_collect_py_files(SCAN_DIRS))
    all_violations: list[str] = []

    for f in files:
        all_violations.extend(_scan_file(f))

    assert not all_violations, (
        f"SQL injection patterns found in {len(all_violations)} location(s):\n"
        + "\n".join(f"  {v}" for v in all_violations)
    )


def test_scan_covers_admin_api_health_and_middleware() -> None:
    """Smoke test: the scanner actually reads admin-api/src/ files."""
    scanned = list(_collect_py_files([REPO_ROOT / "admin-api" / "src"]))
    # We know health.py and tenant.py exist from T-1.0.3.
    names = {f.name for f in scanned}
    assert "health.py" in names, f"health.py not found in scan. Scanned: {names}"
    assert "tenant.py" in names, f"tenant.py not found in scan. Scanned: {names}"
