"""
Architecture test: every write handler in admin-api calls audit_emit (T-1.7.3).

Walks the AST of all .py files in admin-api/src/admin_api/api/ and asserts that
every async function decorated with @router.post/put/patch/delete also calls
audit_emit() (directly or via any call whose name contains 'audit').

Sources:
  - ADR-0014.7 (audit chokepoint — every state change emits an audit event)
  - Req AUD-3 (audit coverage)
  - design §4 api/services.py
"""
from __future__ import annotations

import ast
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[2] / "admin-api" / "src" / "admin_api" / "api"

# Handlers that are intentionally exempt from the audit-emit requirement.
# These are either read-only GET handlers or bootstrap/session surfaces where
# audit is handled by the underlying auth layer rather than the handler directly.
AUDIT_EXEMPT = {
    "health",               # GET — liveness probe, no state change
    "ready",                # GET — readiness probe, no state change
    "whoami",               # GET — identity lookup, read-only
    "logout",               # POST — session cookie deletion; no domain state change
    "internal_login",       # POST — bootstrap surface; audit called inside auth.internal
    "list_services",        # GET — read-only list
    "list_agents",          # GET — read-only list
    "list_credential_versions",  # GET — read-only list
    "get_agent",            # GET — read-only
    "validate_agent_key",   # POST — internal validation stub; no state change (read-only Argon2id check)
    "verify_chain_endpoint", # POST — read-only verification; audit emitted via emit_platform_admin_access
    "grant_permission_shortcut",  # POST — shortcut delegating to grant_permission which calls audit_emit
}

_WRITE_DECORATORS = {"post", "put", "patch", "delete"}


def _is_write_decorator(decorator: ast.expr) -> bool:
    """Return True when decorator is @router.post/put/patch/delete."""
    if isinstance(decorator, ast.Call):
        func = decorator.func
    elif isinstance(decorator, ast.Attribute):
        func = decorator
    else:
        return False

    if isinstance(func, ast.Attribute):
        return func.attr in _WRITE_DECORATORS
    return False


def find_write_handlers(tree: ast.AST) -> list[str]:
    """Return names of async functions decorated with @router.{post,put,patch,delete}."""
    handlers: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in node.decorator_list:
            if _is_write_decorator(dec):
                handlers.append(node.name)
                break
    return handlers


def calls_audit_emit(func_def: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    """
    Return True when the function body contains a call to audit_emit or any
    function whose name contains 'audit'.
    """
    for node in ast.walk(func_def):
        if not isinstance(node, ast.Call):
            continue
        # Direct call: audit_emit(...) or audit_something(...)
        if isinstance(node.func, ast.Name) and "audit" in node.func.id:
            return True
        # Attribute call: something.audit_emit(...) or module.audit(...)
        if isinstance(node.func, ast.Attribute) and "audit" in node.func.attr:
            return True
    return False


def test_all_write_handlers_call_audit_emit() -> None:
    """
    AST-walks admin-api/src/admin_api/api/ and asserts that every async
    function decorated with @router.post/put/patch/delete also calls
    audit_emit() (either directly or via a call to a function whose name
    contains 'audit').

    Allowlist (read-only or bootstrap surface):
    - whoami          (GET handler, read-only)
    - internal_login  (bootstrap — audit called by auth layer, not handler)
    - logout          (session deletion, no domain state change)
    - health/ready    (GET liveness/readiness probes)
    - list_services   (GET handler, read-only)

    Sources: ADR-0014.7, Req AUD-3.
    """
    missing: list[str] = []

    for py_file in sorted(API_DIR.glob("*.py")):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))

        write_handlers = find_write_handlers(tree)
        for handler_name in write_handlers:
            if handler_name in AUDIT_EXEMPT:
                continue
            # Find the function definition and check for audit_emit call.
            for node in ast.walk(tree):
                if (
                    isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
                    and node.name == handler_name
                ):
                    if not calls_audit_emit(node):
                        missing.append(f"{py_file.name}:{handler_name}")
                    break

    assert not missing, (
        f"Write handler(s) missing audit_emit call (ADR-0014.7, Req AUD-3): "
        f"{missing}"
    )


def test_audit_coverage_scans_services_api() -> None:
    """Smoke test: confirms the scanner sees the services.py file."""
    assert (API_DIR / "services.py").exists(), (
        f"services.py not found under {API_DIR}"
    )
