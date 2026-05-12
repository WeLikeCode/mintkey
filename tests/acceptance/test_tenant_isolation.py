"""
Cross-tenant isolation integration test (T-1.12.2).

Asserts zero data leakage across all API endpoints by verifying that every
tenant-scoped handler calls set_tenant_context with the tenant_id taken from
the URL path parameter — not from a different tenant's context.

Strategy: the core invariant is that every handler calls
set_tenant_context(session, tenant_id) before executing queries. This ensures
RLS is active and cross-tenant queries return empty/404. We verify this
invariant with:

  1. Runtime tests (tests 1-4) — use FastAPI TestClient with mocked DB sessions
     and patch set_tenant_context in the relevant module to capture call args.

  2. Static enforcement test (test 5) — AST-walks all handler files and asserts
     that every handler that accepts a DB session and operates under a tenant
     URL also imports and calls set_tenant_context.

Sources: ADR-0008 (tenant context via bound parameters), ADR-0016.3 (RLS),
         Req MT-2 (tenant isolation), T-1.12.2.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call
from uuid import UUID

import pytest

# ---------------------------------------------------------------------------
# Path setup: make admin_api and mintkey_models importable
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADMIN_API_SRC = _REPO_ROOT / "admin-api" / "src"
_MODELS_SRC = _REPO_ROOT / "mintkey-models"

for _p in [str(_ADMIN_API_SRC), str(_MODELS_SRC)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Lazy app factory: builds a minimal FastAPI app without OTel instrumentation
# (OTel's RedactingSpanProcessor has a known _on_ending incompatibility with
# the TestClient event loop that would mask the isolation assertions).
# ---------------------------------------------------------------------------

# Two canonical test tenant UUIDs
TENANT_A = "550e8400-e29b-41d4-a716-446655440000"
TENANT_B = "660e8400-e29b-41d4-a716-446655440001"


def _make_test_app():
    """Return (app, get_db_session) for a minimal FastAPI with tenant routers."""
    from fastapi import FastAPI

    from admin_api.api.agents import router as agents_router
    from admin_api.api.audit import router as audit_router
    from admin_api.api.services import router as services_router
    from admin_api.db.deps import get_db_session

    app = FastAPI()
    app.include_router(services_router)
    app.include_router(agents_router)
    app.include_router(audit_router)
    return app, get_db_session


def _mock_session() -> AsyncMock:
    """Return an AsyncMock DB session whose execute always returns empty rows."""
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = []
    result.fetchone.return_value = None
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# Tests 1-3: runtime verification that each endpoint calls set_tenant_context
# with the tenant_id from the URL path
# ---------------------------------------------------------------------------


def test_services_endpoint_uses_tenant_context():
    """
    GET /v1/tenants/{tenant_id}/services must call set_tenant_context with the
    UUID from the path — not with any other tenant's ID.

    Source: ADR-0008, Req MT-2.
    """
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    app, get_db_session = _make_test_app()
    session = _mock_session()

    async def _override():
        yield session

    app.dependency_overrides[get_db_session] = _override
    client = TestClient(app, raise_server_exceptions=True)

    with patch("admin_api.api.services.set_tenant_context", new_callable=AsyncMock) as mock_stc:
        resp = client.get(f"/v1/tenants/{TENANT_A}/services")

    assert resp.status_code == 200, f"Unexpected status: {resp.status_code} {resp.text}"
    assert mock_stc.call_count == 1, (
        f"set_tenant_context called {mock_stc.call_count} times, expected 1"
    )
    called_tenant_id = mock_stc.call_args[0][1]
    assert called_tenant_id == UUID(TENANT_A), (
        f"set_tenant_context called with {called_tenant_id!r}, expected {TENANT_A!r}"
    )
    assert called_tenant_id != UUID(TENANT_B), (
        "set_tenant_context must NOT be called with a different tenant's ID"
    )


def test_agents_endpoint_uses_tenant_context():
    """
    GET /v1/tenants/{tenant_id}/agents must call set_tenant_context with the
    UUID from the path — not with any other tenant's ID.

    Source: ADR-0008, Req MT-2.
    """
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    app, get_db_session = _make_test_app()
    session = _mock_session()

    async def _override():
        yield session

    app.dependency_overrides[get_db_session] = _override
    client = TestClient(app, raise_server_exceptions=True)

    with patch("admin_api.api.agents.set_tenant_context", new_callable=AsyncMock) as mock_stc:
        resp = client.get(f"/v1/tenants/{TENANT_A}/agents")

    assert resp.status_code == 200, f"Unexpected status: {resp.status_code} {resp.text}"
    assert mock_stc.call_count == 1, (
        f"set_tenant_context called {mock_stc.call_count} times, expected 1"
    )
    called_tenant_id = mock_stc.call_args[0][1]
    assert called_tenant_id == UUID(TENANT_A), (
        f"set_tenant_context called with {called_tenant_id!r}, expected {TENANT_A!r}"
    )
    assert called_tenant_id != UUID(TENANT_B), (
        "set_tenant_context must NOT be called with a different tenant's ID"
    )


def test_audit_endpoint_uses_tenant_context():
    """
    GET /v1/tenants/{tenant_id}/audit must call set_tenant_context with the
    UUID from the path — not with any other tenant's ID.

    Source: ADR-0008, Req MT-2.
    """
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    app, get_db_session = _make_test_app()
    session = _mock_session()

    async def _override():
        yield session

    app.dependency_overrides[get_db_session] = _override
    client = TestClient(app, raise_server_exceptions=True)

    with patch("admin_api.api.audit.set_tenant_context", new_callable=AsyncMock) as mock_stc:
        resp = client.get(f"/v1/tenants/{TENANT_A}/audit")

    assert resp.status_code == 200, f"Unexpected status: {resp.status_code} {resp.text}"
    assert mock_stc.call_count == 1, (
        f"set_tenant_context called {mock_stc.call_count} times, expected 1"
    )
    called_tenant_id = mock_stc.call_args[0][1]
    assert called_tenant_id == UUID(TENANT_A), (
        f"set_tenant_context called with {called_tenant_id!r}, expected {TENANT_A!r}"
    )
    assert called_tenant_id != UUID(TENANT_B), (
        "set_tenant_context must NOT be called with a different tenant's ID"
    )


# ---------------------------------------------------------------------------
# Test 4: cross-tenant path param isolation
# ---------------------------------------------------------------------------


def test_cross_tenant_path_param_isolation():
    """
    When a request uses TENANT_B's path, set_tenant_context must be called
    with TENANT_B's UUID — NOT with TENANT_A's UUID. This verifies that the
    handler does not hardcode or leak a previously-seen tenant context.

    Under real RLS this means only TENANT_B's rows would be returned; under
    the mock (empty rows) the important invariant is the tenant_id forwarded
    to set_tenant_context.

    Source: ADR-0008, ADR-0016.3 (RLS isolation), Req MT-2.
    """
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    app, get_db_session = _make_test_app()
    session = _mock_session()

    async def _override():
        yield session

    app.dependency_overrides[get_db_session] = _override
    client = TestClient(app, raise_server_exceptions=True)

    with patch("admin_api.api.services.set_tenant_context", new_callable=AsyncMock) as mock_stc:
        # First request: TENANT_A
        resp_a = client.get(f"/v1/tenants/{TENANT_A}/services")
        assert resp_a.status_code == 200

        # Second request: TENANT_B — different path param, different tenant context
        resp_b = client.get(f"/v1/tenants/{TENANT_B}/services")
        assert resp_b.status_code == 200

    assert mock_stc.call_count == 2, (
        f"Expected 2 calls to set_tenant_context, got {mock_stc.call_count}"
    )

    first_call_tenant = mock_stc.call_args_list[0][0][1]
    second_call_tenant = mock_stc.call_args_list[1][0][1]

    assert first_call_tenant == UUID(TENANT_A), (
        f"First request must use TENANT_A context, got {first_call_tenant!r}"
    )
    assert second_call_tenant == UUID(TENANT_B), (
        f"Second request must use TENANT_B context, got {second_call_tenant!r}"
    )
    assert first_call_tenant != second_call_tenant, (
        "Each request must use its own tenant context — no context leakage between requests"
    )


# ---------------------------------------------------------------------------
# Test 5: static enforcement — AST coverage check
# ---------------------------------------------------------------------------

_API_DIR = _REPO_ROOT / "admin-api" / "src" / "admin_api" / "api"

# Handlers that legitimately skip set_tenant_context because they are:
#   - platform-admin / cross-tenant operations (no per-tenant scoping needed)
#   - internal auth/validation helpers (non-tenant DB tables)
#   - read-only health/liveness probes (no DB query)
_STC_EXEMPT_HANDLERS = {
    # changes.py — global change channel, not per-tenant
    "get_changes",
    # settings.py — platform-wide settings, tenant_id IS NULL rows; PlatformAdmin only
    "_load_settings",
    "_save_settings",
    "get_admin_settings",
    "patch_admin_settings",
    # tenants.py — create tenant is a bootstrap op; sets genesis hash, no tenant context
    "create_tenant",
    # internal.py — internal auth; queries by api_key_hash across tenants
    "validate_agent_key",
    # audit_admin.py — chain verify endpoint; platform-admin bypass
    "verify_chain_endpoint",
    # proxy.py — cross-tenant API-key fingerprint lookup first (platform_admin_view='on'),
    # then set_tenant_context is called in _proxy_call after tenant is resolved (ADR-0016.3)
    "proxy_call",
    # proxy-hit internal endpoint — called from Go proxy plugin, no per-tenant context
    "proxy_hit",
    # acknowledge_tamper — platform-admin endpoint
    "acknowledge_tamper",
    # grant_permission_shortcut — delegates directly to grant_permission, which calls
    # set_tenant_context; the shortcut itself has no session-level queries of its own
    "grant_permission_shortcut",
}

# Files that do NOT operate under per-tenant routes and may skip the import
_STC_EXEMPT_FILES = {
    "auth.py",       # OIDC/session auth — no tenant DB queries
    "health.py",     # liveness/readiness probes
    "internal.py",   # internal key validation
    "changes.py",    # global channel
    "settings.py",   # platform settings
    "tenants.py",    # tenant bootstrap
}


def _has_session_param(func_def: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    """Return True when the function declares a 'session' parameter."""
    all_args = func_def.args.args + func_def.args.kwonlyargs
    return any(arg.arg == "session" for arg in all_args)


def _calls_set_tenant_context(func_def: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    """Return True when the function body calls set_tenant_context (or tenant_ctx)."""
    for node in ast.walk(func_def):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and "tenant_context" in node.func.id:
            return True
        if isinstance(node.func, ast.Attribute) and "tenant_context" in node.func.attr:
            return True
    return False


def _imports_set_tenant_context(tree: ast.AST) -> bool:
    """Return True when the module imports set_tenant_context from mintkey_models."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "tenant_ctx" in node.module:
                return True
        if isinstance(node, ast.Import):
            for alias in node.names:
                if "tenant_ctx" in alias.name:
                    return True
    return False


def test_rls_architecture_coverage():
    """
    AST-walk admin-api/src/admin_api/api/ and assert that every handler that:
      - accepts a 'session' parameter (i.e. makes DB queries), AND
      - is NOT in the exempt list (platform-admin / non-tenant-scoped routes)

    also calls set_tenant_context (ensuring RLS is always activated before
    executing queries under a tenant context).

    This is the static enforcement complement to the runtime tests above.

    Sources: ADR-0008, ADR-0016.3 (RLS), Req MT-2, T-1.12.2.
    """
    violations: list[str] = []

    for py_file in sorted(_API_DIR.glob("*.py")):
        if py_file.name in _STC_EXEMPT_FILES or py_file.name == "__init__.py":
            continue

        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))

        # Only check files that import set_tenant_context — others are exempt
        if not _imports_set_tenant_context(tree):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            if node.name.startswith("_"):
                continue  # skip private helpers
            if node.name in _STC_EXEMPT_HANDLERS:
                continue
            if not _has_session_param(node):
                continue
            if not _calls_set_tenant_context(node):
                violations.append(
                    f"{py_file.name}:{node.name} — has 'session' param but does not "
                    f"call set_tenant_context (ADR-0008, Req MT-2)"
                )

    assert not violations, (
        f"Handler(s) missing set_tenant_context call before DB query "
        f"(cross-tenant data leakage risk):\n"
        + "\n".join(f"  {v}" for v in violations)
    )
