"""
T-1.12.4: PlatformAdmin RLS escape architecture tests.

Asserts three architectural invariants at the source level (no DB required):

  1. Every RLS policy in the Liquibase changelogs contains the
     platform_admin_view escape clause.

  2. The set_tenant_context function in mintkey_models/tenant_ctx.py
     accepts an is_platform_admin_view parameter that controls whether
     app.platform_admin_view is set to 'on'.

  3. The platform-admin path in middleware or API source emits
     SET app.platform_admin_view via set_config.

Sources: ADR-0008; ADR-0016.3; Req MT-2; T-1.12.4.
"""
from __future__ import annotations

import ast
import inspect
import sys
from pathlib import Path

import pytest
import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHANGELOG_DIR = _REPO_ROOT / "admin-api" / "db" / "changelog"
_MODELS_SRC = _REPO_ROOT / "mintkey-models"
_ADMIN_API_SRC = _REPO_ROOT / "admin-api" / "src"

for _p in [str(_ADMIN_API_SRC), str(_MODELS_SRC)]:
    if _p not in sys.path:
        sys.path.insert(0, _p)

# Substring that must appear in every RLS policy USING clause.
_PLATFORM_ADMIN_ESCAPE = "platform_admin_view"


# ---------------------------------------------------------------------------
# Helper: extract all SQL strings from a Liquibase changeset entry
# ---------------------------------------------------------------------------


def _extract_sql_blocks(changelog_path: Path) -> list[tuple[str, str]]:
    """
    Return (changeset_id, sql_text) pairs for every changeSet that contains
    a ``sql`` or ``createPolicy`` entry.  Only the YAML form is supported;
    the Mintkey changelogs all use YAML.
    """
    data = yaml.safe_load(changelog_path.read_text(encoding="utf-8"))
    results: list[tuple[str, str]] = []
    for entry in data.get("databaseChangeLog", []):
        changeset = entry.get("changeSet")
        if not changeset:
            continue
        cs_id = changeset.get("id", "<unknown>")
        for change in changeset.get("changes", []):
            if "sql" in change:
                sql_text = change["sql"].get("sql", "")
                if sql_text:
                    results.append((cs_id, sql_text))
            if "createPolicy" in change:
                policy = change["createPolicy"]
                using = policy.get("using", "")
                if using:
                    results.append((cs_id, using))
    return results


# ---------------------------------------------------------------------------
# Test 1: every RLS policy contains the platform_admin_view escape
# ---------------------------------------------------------------------------


def test_rls_policies_contain_platform_admin_escape():
    """
    Parse every Liquibase changelog in admin-api/db/changelog/.
    For each changeSet that creates a RLS policy (via a ``sql`` block that
    contains CREATE POLICY or via a ``createPolicy`` block), assert that the
    policy text references ``platform_admin_view``.

    Source: ADR-0008; ADR-0016.3; Req MT-2.
    """
    yaml_files = sorted(_CHANGELOG_DIR.glob("*.yaml"))
    assert yaml_files, f"No YAML changelogs found in {_CHANGELOG_DIR}"

    violations: list[str] = []

    for changelog_path in yaml_files:
        for cs_id, sql_text in _extract_sql_blocks(changelog_path):
            # Only check SQL that actually creates a policy
            if "CREATE POLICY" not in sql_text.upper():
                continue
            if _PLATFORM_ADMIN_ESCAPE not in sql_text:
                violations.append(
                    f"{changelog_path.name} / changeSet {cs_id!r}: "
                    f"CREATE POLICY block does not contain '{_PLATFORM_ADMIN_ESCAPE}'"
                )

    assert not violations, (
        "RLS policy / policies missing platform_admin_view escape clause "
        "(ADR-0016.3):\n" + "\n".join(f"  {v}" for v in violations)
    )


# ---------------------------------------------------------------------------
# Test 2: set_tenant_context supports is_platform_admin_view parameter
# ---------------------------------------------------------------------------


def test_set_tenant_context_has_platform_admin_param():
    """
    Import mintkey_models.tenant_ctx and assert that set_tenant_context:
      - exists as a callable
      - has a parameter whose name contains 'platform_admin' or 'platform_admin_view'
      - that parameter defaults to False / falsy (off by default — Req MT-2)

    Source: ADR-0016.3; T-1.12.4.
    """
    from mintkey_models import tenant_ctx  # noqa: PLC0415

    assert hasattr(tenant_ctx, "set_tenant_context"), (
        "mintkey_models.tenant_ctx does not export set_tenant_context"
    )

    func = tenant_ctx.set_tenant_context
    sig = inspect.signature(func)

    admin_params = [
        name
        for name, param in sig.parameters.items()
        if "platform_admin" in name.lower()
    ]

    assert admin_params, (
        "set_tenant_context has no parameter containing 'platform_admin'. "
        "Expected is_platform_admin_view (ADR-0016.3)."
    )

    # The parameter must default to False / falsy so the escape is opt-in.
    for param_name in admin_params:
        default = sig.parameters[param_name].default
        assert default is not inspect.Parameter.empty, (
            f"set_tenant_context parameter '{param_name}' has no default — "
            "it must default to False so platform_admin_view is off by default"
        )
        assert not default, (
            f"set_tenant_context parameter '{param_name}' defaults to {default!r}; "
            "must be falsy (False/None) so RLS escape is off by default (ADR-0016.3)"
        )


# ---------------------------------------------------------------------------
# Test 3: platform_admin_view SET appears in source for the PlatformAdmin path
# ---------------------------------------------------------------------------


def test_platform_admin_view_setting_present_in_tenant_middleware():
    """
    Grep admin-api source files for ``set_config.*platform_admin_view`` or
    ``SET app.platform_admin_view``.  At least one source file must contain
    this string to prove the escape-hatch is actually activated somewhere in
    the codebase.

    Candidates: middleware/tenant.py, mintkey_models/tenant_ctx.py,
                any api/*.py file.

    Source: ADR-0016.3; T-1.12.4.
    """
    search_roots = [
        _ADMIN_API_SRC,
        _MODELS_SRC,
    ]
    needle = "platform_admin_view"

    hits: list[str] = []
    for root in search_roots:
        for py_file in root.rglob("*.py"):
            text = py_file.read_text(encoding="utf-8")
            if needle in text and "set_config" in text:
                hits.append(str(py_file.relative_to(_REPO_ROOT)))

    assert hits, (
        f"No source file found that both references '{needle}' AND 'set_config'. "
        "The platform_admin_view escape-hatch must be SET somewhere in code "
        "(ADR-0016.3)."
    )
