"""
Architecture gate: SCOPE-A session-based authorization coverage.

Proves that every admin-api route enforces the correct session-based dependency
and prevents regressions introduced by the SCOPE-A rollout (ADR-0027 §D4).

Rules enforced:
  1. Tenant-scoped data routes (path matches ^/v1/tenants/{...}/.+) MUST have
     `require_tenant_session` anywhere in their FastAPI dependency tree.
  2. Platform-admin routes (/v1/tenants, /v1/tenants/{tid}, /v1/admin/...) MUST
     have `require_platform_admin_session` in their dependency tree.
  3. No route in the relevant source files derives authorization from the
     `X-Platform-Admin` request header (negative/anti-trust assertion).

Allowlisted exceptions (each documented with a clear rationale):

  OAUTH2_CALLBACK_ALLOWLIST — OAuth2 browser-redirect callback routes that are
  protected by a single-use, server-side state token (not a session cookie).
  These are Google/Outlook consent endpoints; the browser hits them directly
  after the OAuth2 consent screen, so no session cookie is present at that
  point. Gated by state-token validation inside the handler.

  AGENT_SECRETS_ALLOWLIST — Routes under …/agent-secrets/… whose
  `require_tenant_session` is added on the operator-provisioned-agent-secrets
  branch (ADR-0026). Remove this allowlist entry after that branch merges.

Sources:
  - ADR-0027 §D4 (authz-coverage architecture gate requirement)
  - ADR-0027 §D2 (require_tenant_session / require_platform_admin_session)
  - SCOPE-A rollout commit on this branch
"""
from __future__ import annotations

import os
import re

import pytest
from fastapi.routing import APIRoute

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api/src/admin_api")

# Source files that previously used X-Platform-Admin header for authz.
# Post-SCOPE-A none of them must derive authz from that header.
PLATFORM_ADMIN_HEADER_SENTINEL = "X-Platform-Admin"
_PLATFORM_ADMIN_AUTHZ_FILES = [
    os.path.join(ADMIN_API_SRC, "api", "tenants.py"),
    os.path.join(ADMIN_API_SRC, "api", "audit_admin.py"),
    os.path.join(ADMIN_API_SRC, "api", "settings.py"),
    os.path.join(ADMIN_API_SRC, "middleware", "platform_admin_audit.py"),
]

# Path pattern for tenant-scoped data routes: /v1/tenants/{any_param}/something_more
_TENANT_SCOPED_RE = re.compile(r"^/v1/tenants/\{[^}]+\}/.+")

# Platform-admin routes: tenants CRUD + /v1/admin/... prefix
_PLATFORM_ADMIN_EXACT: frozenset[str] = frozenset({"/v1/tenants", "/v1/tenants/{tid}"})
_PLATFORM_ADMIN_PREFIX = "/v1/admin"

# ---------------------------------------------------------------------------
# Allowlists (documented, finite, reviewed)
# ---------------------------------------------------------------------------

# OAuth2 callback routes: protected by single-use server-side state token.
# The browser redirects here after Google/Outlook consent — no session cookie
# is present at this point. Authorization is enforced via the `state` parameter
# validated inside the handler (DELETE-after-lookup pattern).
# Source: ADR-0024 §B2; email_services.py oauth2_callback / oauth2_callback_view.
OAUTH2_CALLBACK_ALLOWLIST: frozenset[str] = frozenset(
    {
        "/v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/callback",
        "/v1/tenants/{tenant_id}/oauth2/{provider}/callback",
    }
)

# Agent-secrets routes: require_tenant_session is added on the
# operator-provisioned-agent-secrets branch (ADR-0026). Remove this allowlist
# entry after that branch merges.
AGENT_SECRETS_ALLOWLIST: frozenset[str] = frozenset(
    {
        "/v1/tenants/{tenant_id}/agent-secrets",
        "/v1/tenants/{tenant_id}/agent-secrets/{secret_id}",
        "/v1/tenants/{tenant_id}/agent-secrets/{secret_id}/grants",
        "/v1/tenants/{tenant_id}/agent-secrets/{secret_id}/grants/{grant_id}",
    }
)

# Combined allowlist for tenant-scoped routes that don't need require_tenant_session yet.
TENANT_SCOPED_ALLOWLIST: frozenset[str] = OAUTH2_CALLBACK_ALLOWLIST | AGENT_SECRETS_ALLOWLIST


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _collect_api_routes(app) -> list[APIRoute]:
    """
    Flatten all APIRoute instances from the FastAPI app.

    FastAPI 0.110+ stores included routers as _IncludedRouter objects whose
    routes live under `.original_router.routes`. We collect both direct
    APIRoute children and those nested one level deep.
    """
    routes: list[APIRoute] = []
    for r in app.routes:
        if isinstance(r, APIRoute):
            routes.append(r)
        elif hasattr(r, "original_router"):
            for sub in r.original_router.routes:
                if isinstance(sub, APIRoute):
                    routes.append(sub)
    return routes


def _walk_dependant_calls(dependant, visited: set[int] | None = None) -> set:
    """
    Recursively collect all `.call` values from a FastAPI Dependant tree.

    FastAPI's Dependant.dependencies is a list of child Dependant objects.
    We walk depth-first to find every callable wired into the dependency graph.
    """
    if visited is None:
        visited = set()
    calls: set = set()
    key = id(dependant)
    if key in visited:
        return calls
    visited.add(key)
    if dependant.call is not None:
        calls.add(dependant.call)
    for dep in dependant.dependencies:
        calls |= _walk_dependant_calls(dep, visited)
    return calls


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def app_and_routes():
    """
    Build the real admin-api FastAPI app and collect all APIRoute objects.

    Returns (app, routes_list). Scoped to module so the app is created once.
    """
    import os

    # Required env vars to instantiate the app without a live database.
    os.environ.setdefault(
        "MINTKEY_AUDIT_HMAC_KEY",
        "aa" * 32,  # 64 hex chars = 32 bytes
    )
    os.environ.setdefault("MINTKEY_VAULT_BACKEND", "sqlite")

    # Import here so env vars are set before any module-level code runs.
    from admin_api.main import create_app  # noqa: PLC0415

    app = create_app()
    routes = _collect_api_routes(app)
    return app, routes


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_tenant_scoped_routes_have_require_tenant_session(app_and_routes):
    """
    Every route whose path matches ^/v1/tenants/{...}/.+ (tenant-scoped data)
    MUST have `require_tenant_session` somewhere in its FastAPI dependency tree.

    Allowlisted exceptions: OAuth2 callback routes (state-token gated) and
    agent-secrets routes (covered on the ADR-0026 branch — see TENANT_SCOPED_ALLOWLIST).

    Source: ADR-0027 §D4; SCOPE-A rollout.
    """
    from admin_api.auth.sessions import require_tenant_session  # noqa: PLC0415

    _app, routes = app_and_routes

    tenant_scoped = [r for r in routes if _TENANT_SCOPED_RE.match(r.path)]
    assert tenant_scoped, "No tenant-scoped routes found — routing may have changed"

    missing: list[str] = []
    for route in tenant_scoped:
        if route.path in TENANT_SCOPED_ALLOWLIST:
            continue
        dep_calls = _walk_dependant_calls(route.dependant)
        if require_tenant_session not in dep_calls:
            methods = ",".join(sorted(route.methods or set()))
            missing.append(f"{route.path} [{methods}]")

    covered = [
        r for r in tenant_scoped
        if r.path not in TENANT_SCOPED_ALLOWLIST
    ]

    # Summarise coverage for auditability (visible in -v output).
    print(
        f"\n[authz-coverage] tenant-scoped: "
        f"{len(covered)} verified, "
        f"{len(TENANT_SCOPED_ALLOWLIST)} allowlisted "
        f"(oauth2_callbacks={len(OAUTH2_CALLBACK_ALLOWLIST)}, "
        f"agent_secrets={len(AGENT_SECRETS_ALLOWLIST)})"
    )

    assert not missing, (
        "Tenant-scoped routes missing require_tenant_session "
        "(ADR-0027 §D4 — add the dep or add to TENANT_SCOPED_ALLOWLIST with rationale):\n"
        + "\n".join(f"  {r}" for r in sorted(missing))
    )


def test_platform_admin_routes_have_require_platform_admin_session(app_and_routes):
    """
    Routes in the platform-admin tier — /v1/tenants (tenant CRUD) and /v1/admin/...
    — MUST have `require_platform_admin_session` in their dependency tree.

    Source: ADR-0027 §D2; SCOPE-A rollout.
    """
    from admin_api.auth.sessions import require_platform_admin_session  # noqa: PLC0415

    _app, routes = app_and_routes

    platform_admin = [
        r
        for r in routes
        if r.path in _PLATFORM_ADMIN_EXACT or r.path.startswith(_PLATFORM_ADMIN_PREFIX)
    ]
    assert platform_admin, "No platform-admin routes found — routing may have changed"

    missing: list[str] = []
    for route in platform_admin:
        dep_calls = _walk_dependant_calls(route.dependant)
        if require_platform_admin_session not in dep_calls:
            methods = ",".join(sorted(route.methods or set()))
            missing.append(f"{route.path} [{methods}]")

    print(
        f"\n[authz-coverage] platform-admin: {len(platform_admin)} verified"
    )

    assert not missing, (
        "Platform-admin routes missing require_platform_admin_session "
        "(ADR-0027 §D2 — add the dep):\n"
        + "\n".join(f"  {r}" for r in sorted(missing))
    )


def test_no_x_platform_admin_header_authz(app_and_routes):
    """
    Negative / anti-trust assertion: no admin-api source file in the set that
    previously used X-Platform-Admin for authorization now reads that header
    for an authz decision.

    The header name may still appear in docstrings / comments that document the
    old (removed) behaviour — that is expected and acceptable. What we prohibit
    is *executable code* that actually reads the header value: specifically any
    of the patterns below, which are the only ways to read a named header in
    FastAPI/Starlette:

        headers.get("X-Platform-Admin"...)
        headers["X-Platform-Admin"]
        Header(... alias="X-Platform-Admin"...)

    A simple grep for these patterns across the relevant source files is
    sufficient — if none match, the header is not used for authz decisions.

    Source: ADR-0027 §D2 — header no longer trusted post-SCOPE-A.
    """
    _app, _routes = app_and_routes  # ensure app import has run

    # Patterns that indicate *executable* header reads (not comments or docstrings).
    # We look for the header name inside one of these code constructs.
    _HEADER_READ_RE = re.compile(
        r"""(?x)
        (?:
            headers\s*\.\s*get\s*\(\s*['"]X-Platform-Admin['"]   # .get("X-Platform-Admin"
          | headers\s*\[\s*['"]X-Platform-Admin['"]              # ["X-Platform-Admin"]
          | Header\s*\([^)]*alias\s*=\s*['"]X-Platform-Admin['"] # Header(alias="X-Platform-Admin"
        )
        """,
    )

    violations: list[str] = []
    for filepath in _PLATFORM_ADMIN_AUTHZ_FILES:
        if not os.path.exists(filepath):
            continue
        with open(filepath) as fh:
            source = fh.read()
        for match in _HEADER_READ_RE.finditer(source):
            lineno = source[: match.start()].count("\n") + 1
            line = source.splitlines()[lineno - 1]
            violations.append(f"{filepath}:{lineno}: {line.rstrip()}")

    assert not violations, (
        "X-Platform-Admin header is read in executable code "
        "(ADR-0027 §D2 — must derive authz from session cookie only):\n"
        + "\n".join(violations)
    )


def test_allowlists_are_not_vacuous(app_and_routes):
    """
    Meta-test: every path in TENANT_SCOPED_ALLOWLIST actually exists in the
    app's route table, so the allowlist can't silently grow stale.

    Source: good-test hygiene; Karpathy rule 4 (goal-driven execution).
    """
    _app, routes = app_and_routes
    actual_paths = {r.path for r in routes}

    # Each allowlisted path must appear (at least one method) in the real app.
    for path in TENANT_SCOPED_ALLOWLIST:
        assert path in actual_paths, (
            f"Allowlisted path {path!r} is not present in the app's route table. "
            "Remove it from the allowlist — it may have been renamed or deleted."
        )
