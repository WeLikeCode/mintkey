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

API_DIR = Path(__file__).resolve().parents[2] / "apps/admin-api" / "src" / "admin_api" / "api"

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
    # agent-access-requests (T-6.1): these router handlers deliberately delegate
    # audit emission to the service layer (services/access_requests.py), which
    # emits access_request.* through the single audit chokepoint inside the SAME
    # transaction (documented in the router module docstring; ADR-0014.7). The
    # service-layer emission is asserted explicitly by
    # test_access_request_service_handlers_emit_audit (T-11.1), so audit coverage
    # is verified — just not inside the handler body this scanner walks.
    "approve_access_request",          # POST — audit emitted in svc.approve()
    "reject_access_request",           # POST — audit emitted in svc.reject()
    "test_access_request_connection",  # POST — Connection_Test; secret-free diagnostic, no state change
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


# ---------------------------------------------------------------------------
# Feature: agent-access-requests — service-layer + MCP audit coverage (T-11.1)
#
# The scanner above walks only the admin-api @router write handlers. The
# access-request state-change handlers live in the SERVICE layer
# (services/access_requests.py) and in the MCP create funnel
# (_access_requests_common.py), which are not @router-decorated and so are not
# covered above. This add-only section asserts, via the same AST mechanism
# (calls_audit_emit — a call whose name contains 'audit' in the function body),
# that each new state-change handler routes through the single audit chokepoint.
#
# Add-only: the existing scanner and its tests are unchanged.
#
# Sources:
#   - ADR-0014.7 (audit chokepoint — every state change emits an audit event)
#   - agent-access-requests Req 10.1; design §Sequence (create/approve/reject/expire)
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[2]

# admin-api service-layer state-change handlers (each must emit access_request.*
# through the single audit chokepoint — directly or via an 'audit'-named helper).
_ACCESS_REQUEST_SERVICE = (
    _ROOT / "apps/admin-api" / "src" / "admin_api" / "services" / "access_requests.py"
)
_ACCESS_REQUEST_SERVICE_HANDLERS = {
    "create_access_request",
    "create_integration_proposal",
    "create_share_request",
    "approve",
    "reject",
    "sweep_tenant_expired",
}

# MCP create funnel — the single shared emit path for the 3 create tools.
_MCP_ACCESS_REQUEST_COMMON = (
    _ROOT / "apps/mcp-server" / "src" / "mcp_server" / "tools" / "_access_requests_common.py"
)
_MCP_ACCESS_REQUEST_HANDLERS = {
    "emit_created_audit",
}


def _find_func(tree: ast.AST, name: str) -> ast.AsyncFunctionDef | ast.FunctionDef | None:
    """Return the top-level-or-nested function def matching *name*, else None."""
    for node in ast.walk(tree):
        if (
            isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef))
            and node.name == name
        ):
            return node
    return None


def _assert_handlers_emit_audit(
    py_file: Path, handler_names: set[str]
) -> None:
    """Assert every named handler in *py_file* calls an 'audit'-named function."""
    assert py_file.exists(), f"Expected file not found: {py_file}"
    tree = ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))

    missing: list[str] = []
    for name in sorted(handler_names):
        func = _find_func(tree, name)
        if func is None:
            missing.append(f"{py_file.name}:{name} (function not found)")
            continue
        if not calls_audit_emit(func):
            missing.append(f"{py_file.name}:{name} (no audit_emit call)")

    assert not missing, (
        f"access-request state-change handler(s) missing audit_emit call "
        f"(ADR-0014.7, agent-access-requests Req 10.1): {missing}"
    )


def test_access_request_service_handlers_emit_audit() -> None:
    """
    Every admin-api access-request state-change handler
    (create_access_request / create_integration_proposal / create_share_request /
    approve / reject / sweep_tenant_expired) routes through the single audit
    chokepoint — asserted via the same AST mechanism as the router scanner.

    Sources: ADR-0014.7; agent-access-requests Req 10.1.
    """
    _assert_handlers_emit_audit(
        _ACCESS_REQUEST_SERVICE, _ACCESS_REQUEST_SERVICE_HANDLERS
    )


def test_mcp_access_request_create_funnel_emits_audit() -> None:
    """
    The MCP create funnel (emit_created_audit in _access_requests_common.py) —
    the single shared emit path for request_access / propose_integration /
    request_share — routes through the audit chokepoint.

    Sources: ADR-0014.7; agent-access-requests Req 10.1; ADR-0009.
    """
    _assert_handlers_emit_audit(
        _MCP_ACCESS_REQUEST_COMMON, _MCP_ACCESS_REQUEST_HANDLERS
    )
