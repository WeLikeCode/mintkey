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
import re
from pathlib import Path
from typing import Generator

REPO_ROOT = Path(__file__).resolve().parents[2]

# Scan these directories for Python source files.
SCAN_DIRS = [
    REPO_ROOT / "apps/admin-api" / "src",
    REPO_ROOT / "apps/mcp-server" / "src",
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

# Pre-compiled word-boundary patterns for each SQL keyword.
# Multi-word keywords (e.g. "SET LOCAL") allow flexible internal whitespace.
#
# We use a negative lookbehind (?<!\.) so that Python method calls like
# ''.join(...) are NOT matched even though '\bjoin\b' would otherwise fire
# (because '.' and '(' are both non-word characters and create word boundaries
# around 'join').  A genuine SQL JOIN keyword always follows whitespace or a
# parenthesis that is NOT preceded by a method-call dot.
_SQL_KW_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        kw,
        re.compile(
            r"(?<!\.)\b" + re.escape(kw).replace(r"\ ", r"\s+") + r"\b",
            re.IGNORECASE,
        ),
    )
    for kw in SQL_KEYWORDS
]


def _has_sql_keyword(src: str) -> str | None:
    """Return the first SQL keyword matched as a whole word in *src*, or None."""
    for kw, pattern in _SQL_KW_PATTERNS:
        if pattern.search(src):
            return kw
    return None


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


class LiteralVarTracker(ast.NodeVisitor):
    """
    Two-pass helper: walk a function/module body and track which local variables
    are provably built from literal-only expressions throughout their entire
    lifetime in that scope.

    A variable is "literal-only" iff every assignment and augmented-assignment
    in its enclosing scope has a RHS that is:
      - a string constant, OR
      - a BinOp(+) whose both sides are literal-only, OR
      - a Name that itself is literal-only in the current scope.

    Any f-string, call result, or reference to an unknown variable taints the
    variable and marks it NOT literal-only.  We are intentionally conservative.
    """

    def __init__(self) -> None:
        # Stack of scope dicts: {varname: is_literal_only}.
        # Index 0 = module scope; deeper indices = function scopes.
        self.scopes: list[dict[str, bool]] = [{}]

    def _current_scope(self) -> dict[str, bool]:
        return self.scopes[-1]

    def _expr_is_literal_only(self, node: ast.expr) -> bool:
        """True if *node* evaluates to a string built solely from constants + literal-only vars."""
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            return True
        if isinstance(node, ast.JoinedStr):
            return False  # f-string — never literal-only
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return (
                self._expr_is_literal_only(node.left)
                and self._expr_is_literal_only(node.right)
            )
        if isinstance(node, ast.Name):
            return self._current_scope().get(node.id, False)
        return False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        self.scopes.append({})
        self.generic_visit(node)
        self.scopes.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        is_lit = self._expr_is_literal_only(node.value)
        for target in node.targets:
            if isinstance(target, ast.Name):
                # Regular assignment replaces previous value entirely.
                self._current_scope()[target.id] = is_lit
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802
        # x += expr: literal-only only if x was already literal-only AND rhs is literal-only.
        if isinstance(node.target, ast.Name):
            cur = self._current_scope().get(node.target.id, False)
            rhs_lit = self._expr_is_literal_only(node.value)
            self._current_scope()[node.target.id] = cur and rhs_lit
        self.generic_visit(node)

    def is_literal_only(self, varname: str) -> bool:
        """Query whether *varname* is literal-only in the current (innermost) scope."""
        return self._current_scope().get(varname, False)


class SqlInjectionVisitor(ast.NodeVisitor):
    """Collects violations."""

    def __init__(self, filepath: Path) -> None:
        self.filepath = filepath
        self.violations: list[str] = []
        # Run a full pre-pass to build literal-variable maps for every scope.
        self._lit_tracker = LiteralVarTracker()

    def _arg_is_safe(self, arg: ast.expr) -> bool:
        """
        Return True if *arg* is provably safe for text():
          - a string literal / pure-literal BinOp, OR
          - a Name that the LiteralVarTracker has classified as literal-only.
        """
        if _is_string_literal(arg):
            return True
        if isinstance(arg, ast.Name):
            return self._lit_tracker.is_literal_only(arg.id)
        return False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:  # noqa: N802
        # Keep LiteralVarTracker in sync as we descend into functions.
        self._lit_tracker.scopes.append({})
        self.generic_visit(node)
        self._lit_tracker.scopes.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:  # noqa: N802
        self.visit_FunctionDef(node)  # type: ignore[arg-type]

    def visit_Assign(self, node: ast.Assign) -> None:  # noqa: N802
        # Forward assignments to the tracker before visiting children.
        self._lit_tracker.visit_Assign(node)
        self.generic_visit(node)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:  # noqa: N802
        self._lit_tracker.visit_AugAssign(node)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # Check text(...) calls from SQLAlchemy.
        if isinstance(node.func, ast.Name) and node.func.id == "text":
            if node.args:
                arg = node.args[0]
                if not self._arg_is_safe(arg):
                    self.violations.append(
                        f"{self.filepath}:{node.lineno}: "
                        f"text() called with non-literal argument (f-string or concatenation) "
                        f"— use bound parameters instead (ADR-0014)"
                    )
        self.generic_visit(node)

    def visit_JoinedStr(self, node: ast.JoinedStr) -> None:  # noqa: N802
        # Detect f-strings containing SQL keywords (word-boundary match only).
        src = ast.unparse(node)
        kw = _has_sql_keyword(src)
        if kw is not None:
            self.violations.append(
                f"{self.filepath}:{node.lineno}: "
                f"f-string contains SQL keyword '{kw}' — "
                f"use bound parameters instead (ADR-0014, Req SEC-1)"
            )
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
    scanned = list(_collect_py_files([REPO_ROOT / "apps/admin-api" / "src"]))
    # We know health.py and tenant.py exist from T-1.0.3.
    names = {f.name for f in scanned}
    assert "health.py" in names, f"health.py not found in scan. Scanned: {names}"
    assert "tenant.py" in names, f"tenant.py not found in scan. Scanned: {names}"


# ---------------------------------------------------------------------------
# Scanner self-tests
#
# These drive the detection logic directly on inline code snippets (no live
# files needed) so regressions in keyword matching or literal-variable
# tracking are caught immediately.
# ---------------------------------------------------------------------------

_SELF_TEST_FAKE_PATH = Path("<test-snippet>")


def _scan_snippet(code: str) -> list[str]:
    """Parse *code* and return all SQL injection violations found by the scanner."""
    tree = ast.parse(code)
    visitor = SqlInjectionVisitor(_SELF_TEST_FAKE_PATH)
    visitor.visit(tree)
    return visitor.violations


# -- Keyword matching helpers ------------------------------------------------


def test_scanner_kw_join_matches_in_sql_context() -> None:
    """JOIN as a standalone SQL keyword must be detected (any keyword in the string triggers)."""
    assert _has_sql_keyword("SELECT x FROM y JOIN z ON z.id = y.id") is not None


def test_scanner_kw_join_not_matched_in_python_join_method() -> None:
    """''.join(...) must NOT be flagged — dot before 'join' excludes it via lookbehind."""
    assert _has_sql_keyword("''.join(chars)") is None


def test_scanner_kw_join_not_matched_in_wire_ids_fstring_repr() -> None:
    """The exact ast.unparse() output from wire_ids.py must not be flagged."""
    # ast.unparse produces: f"{prefix}_{chars[0]}{''.join(chars[1:])}"
    # Build with repr-safe escaping to avoid f-string syntax confusion.
    src = "f\"{prefix}_{chars[0]}{''." + "join(chars[1:])}\""
    assert _has_sql_keyword(src) is None


def test_scanner_kw_from_matches_as_word() -> None:
    """FROM keyword must be detected (any keyword in the string triggers)."""
    assert _has_sql_keyword("SELECT * FROM users") is not None


def test_scanner_kw_from_not_matched_in_identifier_substring() -> None:
    """'platform' contains 'from' but must NOT be matched (no word boundary)."""
    assert _has_sql_keyword("platform = 'linux'") is None


def test_scanner_kw_set_local_multiword_flexible_whitespace() -> None:
    """SET LOCAL (multi-word keyword) must match with one or more spaces."""
    assert _has_sql_keyword("SET LOCAL mintkey.tenant_id = '123'") == "SET LOCAL"


# -- Positive cases: scanner MUST flag ---------------------------------------


def test_scanner_positive_fstring_with_sql_where() -> None:
    """f-string containing WHERE with interpolated value must be flagged."""
    code = 'x = f"WHERE id={user_input}"'
    assert _scan_snippet(code), "Expected violation for f-string containing WHERE"


def test_scanner_positive_text_with_fstring_arg() -> None:
    """text(f"...{user_input}...") must be flagged."""
    code = 'result = session.execute(text(f"WHERE x={user_input}"))'
    assert _scan_snippet(code), "Expected violation for text(f-string)"


def test_scanner_positive_text_with_string_plus_variable() -> None:
    """text('WHERE x=' + user_input) must be flagged."""
    code = 'result = session.execute(text("WHERE x=" + user_input))'
    assert _scan_snippet(code), "Expected violation for text() with + variable"


def test_scanner_positive_text_with_var_tainted_by_user_input() -> None:
    """Variable tainted via augmented assignment with non-literal must be flagged."""
    code = (
        's = "WHERE x="\n'
        "s += user_input\n"  # tainted
        "result = session.execute(text(s))"
    )
    assert _scan_snippet(code), "Expected violation: s tainted by user_input"


def test_scanner_positive_fstring_sql_join_keyword() -> None:
    """f-string with genuine SQL JOIN keyword must be flagged."""
    code = 'q = f"SELECT * FROM a JOIN b ON a.id = b.a_id WHERE b.x = {val}"'
    assert _scan_snippet(code), "Expected violation for f-string with JOIN"


def test_scanner_positive_text_var_reassigned_from_noliteral() -> None:
    """Variable reassigned from non-literal expression must be flagged."""
    code = (
        'base = "SELECT * FROM t WHERE x = :p"\n'
        "base = base + extra_filter\n"  # taints base
        "result = session.execute(text(base))"
    )
    assert _scan_snippet(code), "Expected violation: base reassigned from non-literal"


# -- Negative cases: scanner MUST NOT flag -----------------------------------


def test_scanner_negative_text_pure_literal() -> None:
    """text('WHERE x=:p') must be accepted."""
    code = 'result = session.execute(text("WHERE x=:p"))'
    violations = _scan_snippet(code)
    assert not violations, f"Unexpected violations: {violations}"


def test_scanner_negative_text_var_built_from_literals_only() -> None:
    """Variable built exclusively from literals, then passed to text(), must be accepted."""
    code = (
        's = "WHERE x="\n'
        's += " AND y=:p"\n'
        "result = session.execute(text(s))"
    )
    violations = _scan_snippet(code)
    assert not violations, f"Unexpected violations for literal-only var: {violations}"


def test_scanner_negative_production_base_sql_pattern() -> None:
    """Multi-line literal-only construction (production base_sql pattern) must be accepted."""
    code = (
        'base_sql = (\n'
        '    "SELECT id FROM service_api_keys"\n'
        '    " WHERE tenant_id = :tid"\n'
        ')\n'
        'base_sql += " AND service_id = :svc_id"\n'
        'base_sql += " ORDER BY created_at DESC"\n'
        "rows = session.execute(text(base_sql), params)"
    )
    violations = _scan_snippet(code)
    assert not violations, f"Unexpected violations for production-style base_sql: {violations}"


def test_scanner_negative_python_join_in_fstring_not_flagged() -> None:
    """f-string containing ''.join() must NOT be flagged (no SQL keyword at word boundary)."""
    code = "result = f\"{prefix}_{''.join(chars[1:])}\""
    violations = _scan_snippet(code)
    assert not violations, f"Unexpected violations for wire_ids-style join: {violations}"


def test_scanner_negative_fstring_no_sql_keywords() -> None:
    """f-strings with no SQL keywords must not be flagged."""
    code = (
        'name = f"service_{service_id}"\n'
        'url = f"https://example.com/{path}"'
    )
    violations = _scan_snippet(code)
    assert not violations, f"Unexpected violations for non-SQL f-string: {violations}"


def test_scanner_negative_text_literal_binop() -> None:
    """text('base ' + ' AND x=:p') — two string constants concatenated is safe."""
    code = 'result = session.execute(text("SELECT * FROM t" + " WHERE x=:p"))'
    violations = _scan_snippet(code)
    assert not violations, f"Unexpected violations for literal BinOp in text(): {violations}"


# -- LiteralVarTracker unit tests --------------------------------------------


def test_literal_var_tracker_simple_literal() -> None:
    """Tracker marks a plain string assignment as literal-only."""
    code = "x = 'hello'"
    tree = ast.parse(code)
    tracker = LiteralVarTracker()
    tracker.visit(tree)
    assert tracker.is_literal_only("x") is True


def test_literal_var_tracker_tainted_by_unknown_name() -> None:
    """Tracker marks a variable assigned from an unknown name as NOT literal-only."""
    code = "x = some_var"
    tree = ast.parse(code)
    tracker = LiteralVarTracker()
    tracker.visit(tree)
    assert tracker.is_literal_only("x") is False


def test_literal_var_tracker_augassign_stays_pure() -> None:
    """x = 'a'; x += 'b' — both literal, x stays literal-only."""
    code = "x = 'a'\nx += 'b'"
    tree = ast.parse(code)
    tracker = LiteralVarTracker()
    tracker.visit(tree)
    assert tracker.is_literal_only("x") is True


def test_literal_var_tracker_augassign_taints() -> None:
    """x = 'a'; x += user_input — x must be tainted."""
    code = "x = 'a'\nx += user_input"
    tree = ast.parse(code)
    tracker = LiteralVarTracker()
    tracker.visit(tree)
    assert tracker.is_literal_only("x") is False
