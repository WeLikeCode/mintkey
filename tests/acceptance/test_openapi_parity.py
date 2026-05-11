"""
CI gate: T-1.11.5 — OpenAPI parity.

Verifies that every router registered in create_app() contributes the expected
route prefixes, and that the canonical openapi.yaml exists, by parsing
admin-api/src/admin_api/main.py and the individual router files as text/AST.

This avoids importing the app (which requires a live DB) while still validating
structural parity.
"""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).parents[2]
MAIN_PY = REPO_ROOT / "admin-api" / "src" / "admin_api" / "main.py"
API_DIR = REPO_ROOT / "admin-api" / "src" / "admin_api" / "api"
CANONICAL_OPENAPI = REPO_ROOT / "docs" / "architecture" / "contracts" / "rest" / "openapi.yaml"
SNAPSHOT_PATH = Path(__file__).parent / "openapi_snapshot.json"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _router_module_names() -> list[str]:
    """Return the module basenames imported as `router as <name>_router` in main.py."""
    src = MAIN_PY.read_text()
    # Match: from admin_api.api.<module> import router as <alias>_router
    return re.findall(r"from admin_api\.api\.(\w+) import router", src)


def _router_prefix(module_name: str) -> str | None:
    """
    Return the `prefix` string from `router = APIRouter(prefix="...")` in the
    given api module, or None if the router has no explicit prefix.
    """
    src = (API_DIR / f"{module_name}.py").read_text()
    # Match: APIRouter(prefix="/v1/...")
    m = re.search(r'APIRouter\s*\([^)]*prefix\s*=\s*["\']([^"\']+)["\']', src, re.DOTALL)
    return m.group(1) if m else None


def _router_inline_paths(module_name: str) -> list[str]:
    """
    For routers with no prefix, extract route paths from @router.<method>("/...") decorators.
    """
    src = (API_DIR / f"{module_name}.py").read_text()
    return re.findall(r'@router\.\w+\s*\(\s*["\']([^"\']+)["\']', src)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestRouterStructure:
    """T-1.11.5 — router structural parity."""

    def test_all_routers_contribute_paths(self):
        """
        Every router imported in main.py must either declare a prefix or
        define at least one @router.<method>("/v1/...") route.
        """
        modules = _router_module_names()
        assert modules, "No router imports found in main.py"

        for module in modules:
            router_file = API_DIR / f"{module}.py"
            assert router_file.exists(), f"Router file missing: {router_file}"

            prefix = _router_prefix(module)
            inline = _router_inline_paths(module)

            assert prefix is not None or inline, (
                f"Router '{module}' has no prefix and no @router.<method>(...) routes"
            )

    def test_expected_route_prefixes_present(self):
        """
        The expected set of route prefixes (or inline paths) must be present
        across all registered routers.
        """
        modules = _router_module_names()
        all_prefixes: set[str] = set()
        all_inline_paths: set[str] = set()

        for module in modules:
            prefix = _router_prefix(module)
            if prefix:
                all_prefixes.add(prefix)
            else:
                all_inline_paths.update(_router_inline_paths(module))

        # Every expected path must be reachable via a prefix or an inline route
        expected = {
            "/v1/health": all_inline_paths,
            "/v1/auth": all_prefixes,
            "/v1/tenants/{tenant_id}/audit": all_prefixes,
            "/v1/admin": all_prefixes,
            "/v1/tenants": all_prefixes,
            "/v1/internal": all_prefixes,
        }

        for path, pool in expected.items():
            assert any(p == path or p.startswith(path) for p in pool), (
                f"Expected route/prefix '{path}' not found among registered routers. "
                f"Pool: {sorted(pool)}"
            )

    def test_main_py_registers_all_imported_routers(self):
        """
        Every router imported in main.py must also appear in an include_router() call.
        """
        src = MAIN_PY.read_text()
        imports = re.findall(r"import router as (\w+)", src)
        includes = re.findall(r"app\.include_router\((\w+)\)", src)

        for alias in imports:
            assert alias in includes, (
                f"Router '{alias}' is imported but never passed to app.include_router()"
            )

    def test_canonical_openapi_yaml_exists(self):
        """
        The canonical OpenAPI YAML (docs/architecture/contracts/rest/openapi.yaml)
        must exist.  This is the source of truth per ADR-0017.1.
        """
        assert CANONICAL_OPENAPI.exists(), (
            f"Canonical OpenAPI spec not found at {CANONICAL_OPENAPI}"
        )

    def test_openapi_parity_snapshot(self):
        """
        Snapshot test for route prefixes: build the expected set of top-level
        path prefixes from the router files and compare against a stored snapshot.

        If the snapshot doesn't exist, create it (first run).
        If it does exist, assert the current prefix set matches it exactly.
        """
        modules = _router_module_names()
        current: dict[str, str | None] = {}
        for module in modules:
            prefix = _router_prefix(module)
            if prefix:
                current[module] = prefix
            else:
                paths = _router_inline_paths(module)
                current[module] = paths[0] if paths else None

        if not SNAPSHOT_PATH.exists():
            SNAPSHOT_PATH.write_text(json.dumps(current, indent=2, sort_keys=True))
            return  # first run: snapshot created, test passes

        stored = json.loads(SNAPSHOT_PATH.read_text())
        assert current == stored, (
            "Router prefix snapshot mismatch.\n"
            f"Current : {json.dumps(current, sort_keys=True)}\n"
            f"Snapshot: {json.dumps(stored, sort_keys=True)}\n"
            f"Update the snapshot at {SNAPSHOT_PATH} if the change is intentional."
        )
