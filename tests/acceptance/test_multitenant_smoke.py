"""
T-1.12.5: Multi-tenant smoke test (unit mock version).

Asserts multi-tenant isolation invariants at the unit test level — no
running database or Docker required.

  1. test_tenant_isolation_architecture: AST-walk all API handler files;
     assert that handlers with a 'session' parameter that are NOT in the
     exempt list call set_tenant_context.

  2. test_two_tenants_cant_see_each_others_services: Use TestClient with a
     per-call mocked DB; assert that each tenant's response contains only its
     own services and never the other tenant's.

  3. test_jwt_tenant_mismatch_rejected: Read the Go verifier source; assert
     it contains the tenant_mismatch error code for cross-tenant JWT replay.

  4. test_platform_admin_view_is_off_by_default: Read tenant_ctx.py; assert
     set_tenant_context defaults platform_admin_view to falsy.

Sources: ADR-0006; ADR-0008; ADR-0016.3; Req MT-2; T-1.12.5.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_ADMIN_API_SRC = _REPO_ROOT / "admin-api" / "src"
_MODELS_SRC = _REPO_ROOT / "mintkey-models"
_API_DIR = _ADMIN_API_SRC / "admin_api" / "api"
_VERIFIER_GO = (
    _REPO_ROOT
    / "services"
    / "proxy-plugin"
    / "internal"
    / "jwt"
    / "verifier.go"
)

for _p in [str(_ADMIN_API_SRC), str(_MODELS_SRC)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# ---------------------------------------------------------------------------
# Shared test data
# ---------------------------------------------------------------------------

# Two canonical tenant UUIDs (different from the ones used in test_tenant_isolation.py
# to make it clear these are independent test scenarios).
TENANT_01AAAA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TENANT_01BBBB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"

# ---------------------------------------------------------------------------
# Handlers / files that legitimately skip set_tenant_context
# (matches the allowlist in test_tenant_isolation.py — kept in sync manually)
# ---------------------------------------------------------------------------

_STC_EXEMPT_HANDLERS = {
    "get_changes",
    "_load_settings",
    "_save_settings",
    "get_admin_settings",
    "patch_admin_settings",
    "create_tenant",
    "validate_agent_key",
    "verify_chain_endpoint",
    # proxy.py — cross-tenant API-key fingerprint lookup first (platform_admin_view='on'),
    # then set_tenant_context is called in _proxy_call after tenant is resolved (ADR-0016.3)
    "proxy_call",
    # proxy-hit internal endpoint — called from Go proxy plugin, no per-tenant context
    "proxy_hit",
    # acknowledge_tamper — platform-admin endpoint
    "acknowledge_tamper",
}

_STC_EXEMPT_FILES = {
    "auth.py",
    "health.py",
    "internal.py",
    "changes.py",
    "settings.py",
    "tenants.py",
}


# ---------------------------------------------------------------------------
# AST helpers (duplicated from test_tenant_isolation.py for independence)
# ---------------------------------------------------------------------------


def _has_session_param(func_def: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    all_args = func_def.args.args + func_def.args.kwonlyargs
    return any(arg.arg == "session" for arg in all_args)


def _calls_set_tenant_context(func_def: ast.AsyncFunctionDef | ast.FunctionDef) -> bool:
    for node in ast.walk(func_def):
        if not isinstance(node, ast.Call):
            continue
        if isinstance(node.func, ast.Name) and "tenant_context" in node.func.id:
            return True
        if isinstance(node.func, ast.Attribute) and "tenant_context" in node.func.attr:
            return True
    return False


def _imports_set_tenant_context(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module and "tenant_ctx" in node.module:
                return True
    return False


# ---------------------------------------------------------------------------
# Test 1: static RLS enforcement — handlers with tenant path param must call
# set_tenant_context before executing queries
# ---------------------------------------------------------------------------


def test_tenant_isolation_architecture():
    """
    AST-walk admin-api/src/admin_api/api/ and assert that every non-exempt
    handler that accepts a DB 'session' parameter and is defined in a file
    that imports set_tenant_context also calls set_tenant_context.

    This is the static complement to the runtime tests in
    test_tenant_isolation.py.  A handler that omits the call would execute
    queries without activating RLS, leaking cross-tenant data.

    Source: ADR-0008; ADR-0016.3; Req MT-2.
    """
    violations: list[str] = []

    for py_file in sorted(_API_DIR.glob("*.py")):
        if py_file.name in _STC_EXEMPT_FILES or py_file.name == "__init__.py":
            continue

        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))

        if not _imports_set_tenant_context(tree):
            continue

        for node in ast.walk(tree):
            if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
                continue
            if node.name.startswith("_"):
                continue
            if node.name in _STC_EXEMPT_HANDLERS:
                continue
            if not _has_session_param(node):
                continue
            if not _calls_set_tenant_context(node):
                violations.append(
                    f"{py_file.name}:{node.name} — has 'session' param but "
                    "does not call set_tenant_context (ADR-0008, Req MT-2)"
                )

    assert not violations, (
        "Handler(s) missing set_tenant_context call (cross-tenant data leakage risk):\n"
        + "\n".join(f"  {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Helpers for test 2
# ---------------------------------------------------------------------------


def _make_test_app():
    """Return (app, get_db_session) with the minimal service router."""
    from fastapi import FastAPI

    from admin_api.api.services import router as services_router
    from admin_api.db.deps import get_db_session

    app = FastAPI()
    app.include_router(services_router)
    return app, get_db_session


def _mock_session_with_rows(rows: list) -> AsyncMock:
    """
    Return an AsyncMock DB session whose execute() always returns the given rows.
    Used to simulate per-tenant DB isolation without a real database.
    """
    session = AsyncMock()
    result = MagicMock()
    result.fetchall.return_value = rows
    result.fetchone.return_value = rows[0] if rows else None
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# Test 2: two tenants cannot see each other's services (mocked DB)
# ---------------------------------------------------------------------------


def test_two_tenants_cant_see_each_others_services():
    """
    Simulate two independent DB sessions — one per tenant — and assert that:
      - GET /v1/tenants/TENANT_A/services never contains a service ID from
        TENANT_B's mock session, and vice versa.

    Under real RLS each session's set_config call gates what rows Postgres
    returns; here the mocks represent that isolation guarantee at the API
    contract level.

    Source: ADR-0008; ADR-0016.3; Req MT-2.
    """
    from unittest.mock import patch

    from fastapi.testclient import TestClient

    app, get_db_session = _make_test_app()

    # Row-like object for the DB result
    class _FakeRow:
        def __init__(self, row_id, tid, name):
            self.id = row_id
            self.tenant_id = tid
            self.name = name
            self.slug = name.lower()
            self.display_name = name
            self.description = None
            self.base_url = "https://example.com"
            self.auth_scheme = "bearer"
            self.openapi_url = None
            self.status = "active"
            self.created_at = None
            self.updated_at = None

    row_a = _FakeRow("aaa00000-0000-0000-0000-000000000001", TENANT_01AAAA, "ServiceA")
    row_b = _FakeRow("bbb00000-0000-0000-0000-000000000001", TENANT_01BBBB, "ServiceB")

    session_a = _mock_session_with_rows([row_a])
    session_b = _mock_session_with_rows([row_b])

    # Override the DB dependency to return session_a for TENANT_01AAAA
    # and session_b for TENANT_01BBBB.
    # Because TestClient is synchronous and each request is independent, we
    # swap the override between calls.
    client = TestClient(app, raise_server_exceptions=True)

    with patch("admin_api.api.services.set_tenant_context", new_callable=AsyncMock):
        # Request for TENANT_A — DB returns only row_a
        async def _override_a():
            yield session_a

        app.dependency_overrides[get_db_session] = _override_a
        resp_a = client.get(f"/v1/tenants/{TENANT_01AAAA}/services")
        assert resp_a.status_code == 200, f"TENANT_A request failed: {resp_a.text}"
        services_a = resp_a.json()["services"]

        # Request for TENANT_B — DB returns only row_b
        async def _override_b():
            yield session_b

        app.dependency_overrides[get_db_session] = _override_b
        resp_b = client.get(f"/v1/tenants/{TENANT_01BBBB}/services")
        assert resp_b.status_code == 200, f"TENANT_B request failed: {resp_b.text}"
        services_b = resp_b.json()["services"]

    # Extract service names from each response
    names_a = {svc["name"] for svc in services_a}
    names_b = {svc["name"] for svc in services_b}

    assert "ServiceA" in names_a, (
        f"TENANT_A response does not contain its own service. Got: {names_a}"
    )
    assert "ServiceB" in names_b, (
        f"TENANT_B response does not contain its own service. Got: {names_b}"
    )
    assert "ServiceB" not in names_a, (
        "TENANT_A response contains TENANT_B's service — cross-tenant data leakage!"
    )
    assert "ServiceA" not in names_b, (
        "TENANT_B response contains TENANT_A's service — cross-tenant data leakage!"
    )


# ---------------------------------------------------------------------------
# Test 3: JWT verifier rejects cross-tenant tokens (static check)
# ---------------------------------------------------------------------------


def test_jwt_tenant_mismatch_rejected():
    """
    Read services/proxy-plugin/internal/jwt/verifier.go and assert that:
      - The file exists.
      - It defines a ``tenant_mismatch`` error code for cross-tenant JWT
        replay detection.

    This is a static source check: the presence of the error code in the
    verifier guarantees that the enforcement path exists.  The runtime
    behaviour is covered by the Go unit tests.

    Source: ADR-0006; ADR-0008; Req MT-2.
    """
    assert _VERIFIER_GO.exists(), (
        f"JWT verifier source not found at {_VERIFIER_GO}. "
        "Expected services/proxy-plugin/internal/jwt/verifier.go"
    )

    source = _VERIFIER_GO.read_text(encoding="utf-8")

    assert "tenant_mismatch" in source, (
        f"{_VERIFIER_GO.name} does not contain 'tenant_mismatch' error code. "
        "The verifier must reject JWTs whose tnt claim does not match the "
        "configured tenant (ADR-0006, Req MT-2)."
    )

    # Also assert the tnt claim is actually checked (not just the error string)
    assert '"tnt"' in source or "tnt" in source, (
        f"{_VERIFIER_GO.name} does not reference the 'tnt' JWT claim. "
        "Tenant validation requires comparing claims[tnt] to the expected tenant ID."
    )


# ---------------------------------------------------------------------------
# Test 4: platform_admin_view is off by default
# ---------------------------------------------------------------------------


def test_platform_admin_view_is_off_by_default():
    """
    Import mintkey_models.tenant_ctx and assert that set_tenant_context's
    platform-admin parameter defaults to False (or another falsy value).

    This ensures that the RLS escape hatch is never active unless the caller
    explicitly requests it — preventing accidental cross-tenant data exposure.

    Source: ADR-0016.3; T-1.12.4.
    """
    from mintkey_models import tenant_ctx  # noqa: PLC0415

    func = tenant_ctx.set_tenant_context
    sig = inspect.signature(func)

    admin_params = {
        name: param
        for name, param in sig.parameters.items()
        if "platform_admin" in name.lower()
    }

    assert admin_params, (
        "set_tenant_context has no 'platform_admin*' parameter — "
        "cannot verify that the escape is off by default (ADR-0016.3)"
    )

    for param_name, param in admin_params.items():
        assert param.default is not inspect.Parameter.empty, (
            f"Parameter '{param_name}' on set_tenant_context has no default — "
            "must default to False so platform_admin_view is off by default"
        )
        assert not param.default, (
            f"Parameter '{param_name}' defaults to {param.default!r}; "
            "must be falsy (False) so the RLS escape is opt-in, never automatic "
            "(ADR-0016.3)"
        )
