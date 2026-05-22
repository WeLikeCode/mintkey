"""
Architecture test: no plaintext credentials in OTel span attribute calls.

AST-walks all Python files in admin-api, mcp-server, and mintkey-models to assert:
  1. No set_attribute / set_attributes call passes a string literal matching
     credential patterns (mk_agent_, sk_, pk_, eyJ).
  2. No set_attribute / set_attributes call uses a keyword argument whose name
     is one of the forbidden keys (token, secret, password, api_key, passphrase).
  3. The RedactingSpanProcessor from otel_redaction is referenced in the OTel
     middleware (admin-api/src/admin_api/middleware/otel.py).

Source: S-SEC-1; ADR-0017.6; T-1.3.3.
"""
import ast
from pathlib import Path

_REPO_ROOT = Path(__file__).parent.parent.parent

_SCAN_ROOTS = [
    _REPO_ROOT / "apps/admin-api" / "src" / "admin_api",
    _REPO_ROOT / "apps/mcp-server" / "src" / "mcp_server",
    _REPO_ROOT / "mintkey-models" / "mintkey_models",
]

# String literal prefixes that signal a plaintext credential value.
_CREDENTIAL_PREFIXES = ("mk_agent_", "sk_", "pk_", "eyJ")

# Keyword argument names that must never appear on span attribute calls.
_FORBIDDEN_KWARG_NAMES = frozenset({"token", "secret", "password", "api_key", "passphrase"})


def _collect_python_files(roots: list[Path]) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if root.exists():
            files.extend(root.rglob("*.py"))
    return sorted(files)


def _is_span_attribute_call(node: ast.Call) -> bool:
    """Return True if the call's function name contains set_attribute(s)."""
    func = node.func
    if isinstance(func, ast.Name):
        return "set_attribute" in func.id
    if isinstance(func, ast.Attribute):
        return "set_attribute" in func.attr
    return False


def test_no_plaintext_literal_in_span_attribute_calls() -> None:
    """
    No set_attribute / set_attributes call in any scanned Python source may:
      - pass a positional string literal that starts with a credential prefix, or
      - use a keyword argument named after a sensitive field.

    Source: S-SEC-1; ADR-0017.6; T-1.3.3.
    """
    files = _collect_python_files(_SCAN_ROOTS)
    assert files, "No Python files found under scan roots — check repo layout"

    violations: list[str] = []

    for path in files:
        src = path.read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=str(path))
        except SyntaxError:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not _is_span_attribute_call(node):
                continue

            # Check positional arguments for plaintext credential literals.
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    for prefix in _CREDENTIAL_PREFIXES:
                        if arg.value.startswith(prefix):
                            violations.append(
                                f"{path}:{node.lineno}: "
                                f"span attribute call contains credential literal "
                                f"matching prefix {prefix!r}: {arg.value!r}"
                            )

            # Check keyword arguments for forbidden names.
            for kw in node.keywords:
                if kw.arg in _FORBIDDEN_KWARG_NAMES:
                    violations.append(
                        f"{path}:{node.lineno}: "
                        f"span attribute call uses forbidden keyword argument name "
                        f"{kw.arg!r}"
                    )

    assert not violations, (
        "Plaintext credential patterns found in span attribute calls:\n"
        + "\n".join(violations)
    )


def test_otel_redacting_processor_referenced_in_middleware() -> None:
    """
    The RedactingSpanProcessor (from otel_redaction) must be imported or
    referenced somewhere in the admin-api OTel middleware, confirming it is
    wired into the SDK pipeline per ADR-0017.6.

    NOTE: The current middleware (T-1.0.14 step) wires configure_otel() but
    the RedactingSpanProcessor integration is the next wiring step (T-1.3.3).
    This test checks the *module* (otel_redaction) is at minimum imported in
    at least one of: middleware/otel.py, main.py of admin-api, or main.py of
    mcp-server — and that the class symbol RedactingSpanProcessor exists in
    the mintkey_models package.

    Source: ADR-0017.6; T-1.3.3.
    """
    # Confirm the class exists in the package — the file was already read above.
    otel_redaction_py = (
        _REPO_ROOT / "mintkey-models" / "mintkey_models" / "otel_redaction.py"
    )
    assert otel_redaction_py.exists(), (
        f"otel_redaction.py not found at {otel_redaction_py}"
    )

    src = otel_redaction_py.read_text(encoding="utf-8")
    assert "class RedactingSpanProcessor" in src, (
        "RedactingSpanProcessor class definition missing from otel_redaction.py"
    )

    # Check that at least one primary entry-point module references otel_redaction.
    candidate_files = [
        _REPO_ROOT / "apps/admin-api" / "src" / "admin_api" / "middleware" / "otel.py",
        _REPO_ROOT / "apps/admin-api" / "src" / "admin_api" / "main.py",
        _REPO_ROOT / "apps/mcp-server" / "src" / "mcp_server" / "main.py",
    ]

    # Build the set of files that actually import otel_redaction.
    referencing: list[Path] = []
    for candidate in candidate_files:
        if not candidate.exists():
            continue
        candidate_src = candidate.read_text(encoding="utf-8")
        if "otel_redaction" in candidate_src or "RedactingSpanProcessor" in candidate_src:
            referencing.append(candidate)

    # The test documents intent: RedactingSpanProcessor should be wired.
    # We assert the class exists and is ready; wiring verification is a
    # separate integration task (T-1.0.14).  If already wired, referencing
    # will be non-empty and the assert passes with an informative message.
    # If not yet wired, we emit a clear failure rather than a silent pass.
    assert referencing, (
        "RedactingSpanProcessor / otel_redaction is not imported in any of "
        "admin-api middleware/otel.py, admin-api main.py, or mcp-server main.py. "
        "Wire it per ADR-0017.6 (T-1.0.14)."
    )
