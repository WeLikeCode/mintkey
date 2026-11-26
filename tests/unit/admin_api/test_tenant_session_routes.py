"""
Unit tests: every tenant-scoped admin-api route requires the tenant session.

Task 1.1 of tenant-session-routes. The tests decide three things:

  1. every route whose path matches ``^/v1/tenants/{...}/.+`` (except the two
     OAuth2 consent callbacks, protected by a single-use state token) has
     ``require_tenant_session`` somewhere in its FastAPI dependency tree;
  2. when the session is missing, unknown/expired or belongs to another tenant,
     the dependency answers 401/403 before the handler emits any SQL;
  3. a session of the path's tenant, or a platform admin, reaches the handler
     (which runs ``set_tenant_context`` — a ``SELECT set_config(...)`` — first).

Source: tenant-session-routes › Every tenant-scoped route requires the tenant session.
"""
from __future__ import annotations

import os
import re
import sys
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "apps/admin-api", "src")
MODELS_SRC = os.path.join(REPO_ROOT, "packages/python/mintkey-models")
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# Required before admin_api.main is imported (create_app reads them at import).
os.environ.setdefault("MINTKEY_AUDIT_HMAC_KEY", "0" * 64)
os.environ.setdefault("MINTKEY_VAULT_BACKEND", "sqlite")

TA = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
TB = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
AG = "agent_3C7JAGMBGR9EMRS2AVGXDHQXDX"
PM = "perm_3C7JAGMBGR9EMRS2AVGXDHQXDX"

_TENANT_SCOPED_RE = re.compile(r"^/v1/tenants/\{[^}]+\}/.+")

# OAuth2 consent callbacks: their protection is the single-use state token, not
# a session cookie (the browser hits them straight after the consent screen).
_CALLBACKS = frozenset(
    {
        "/v1/tenants/{tenant_id}/email-services/{service_id}/oauth2/{provider}/callback",
        "/v1/tenants/{tenant_id}/oauth2/{provider}/callback",
    }
)

# The seven handlers of this change, as (method, path) with their registration
# count. POST .../budget/reset is registered twice (permissions and budgets).
_REQUIRED_ROUTES: dict[tuple[str, str], int] = {
    (
        "PATCH",
        "/v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{permission_id}",
    ): 1,
    (
        "POST",
        "/v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{permission_id}/budget/reset",
    ): 2,
    (
        "GET",
        "/v1/tenants/{tenant_id}/agents/{agent_id}/permissions/{permission_id}/budget",
    ): 1,
    ("GET", "/v1/tenants/{tenant_id}/permissions/{permission_id}"): 1,
    ("GET", "/v1/tenants/{tenant_id}/permissions/{permission_id}/budget"): 1,
    ("GET", "/v1/tenants/{tenant_id}/budget-consumers"): 1,
}

_CASES: list[tuple[str, str, str, dict[str, Any] | None]] = [
    (
        "grants",
        "PATCH",
        f"/v1/tenants/{TA}/agents/{AG}/permissions/{PM}",
        {"constraints": {"budget": None}},
    ),
    (
        "grants",
        "POST",
        f"/v1/tenants/{TA}/agents/{AG}/permissions/{PM}/budget/reset",
        None,
    ),
    ("grants", "GET", f"/v1/tenants/{TA}/permissions/{PM}", None),
    ("grants", "GET", f"/v1/tenants/{TA}/permissions/{PM}/budget", None),
    ("grants", "GET", f"/v1/tenants/{TA}/budget-consumers", None),
    (
        "budgets",
        "GET",
        f"/v1/tenants/{TA}/agents/{AG}/permissions/{PM}/budget",
        None,
    ),
    (
        "budgets",
        "POST",
        f"/v1/tenants/{TA}/agents/{AG}/permissions/{PM}/budget/reset",
        None,
    ),
]

_CASE_IDS = [
    "patch-permission",
    "post-permission-budget-reset",
    "get-permission",
    "get-permission-budget",
    "get-budget-consumers",
    "get-budget",
    "post-budget-reset",
]


class RecordingSession:
    """A fake AsyncSession that counts the statements run against it.

    Every ``execute`` records the call and answers with a MagicMock whose
    ``fetchone()`` is ``None`` and ``fetchall()`` is ``[]`` — enough for a
    handler that runs ``set_tenant_context`` first and then finds no row.
    """

    def __init__(self) -> None:
        self.statements: list[tuple[tuple[Any, ...], dict[str, Any]]] = []

    async def execute(self, *args: Any, **kwargs: Any) -> MagicMock:
        self.statements.append((args, kwargs))
        result = MagicMock()
        result.fetchone.return_value = None
        result.fetchall.return_value = []
        return result


def _collect_api_routes(app: Any) -> list[Any]:
    """Flatten every APIRoute, directly or one level under original_router."""
    from fastapi.routing import APIRoute

    routes: list[Any] = []
    for route in app.routes:
        if isinstance(route, APIRoute):
            routes.append(route)
        elif hasattr(route, "original_router"):
            for sub in route.original_router.routes:
                if isinstance(sub, APIRoute):
                    routes.append(sub)
    return routes


def _walk_dependant_calls(dependant: Any, visited: set[int] | None = None) -> set[Any]:
    """Depth-first walk of a FastAPI Dependant tree, collecting its .call values."""
    if visited is None:
        visited = set()
    calls: set[Any] = set()
    key = id(dependant)
    if key in visited:
        return calls
    visited.add(key)
    if dependant.call is not None:
        calls.add(dependant.call)
    for dependency in dependant.dependencies:
        calls |= _walk_dependant_calls(dependency, visited)
    return calls


def build_app(group: str) -> tuple[Any, RecordingSession]:
    """Build a small app from one group of routers, with a recording DB session."""
    from fastapi import FastAPI

    from admin_api.api import budget_consumers, budgets, permissions
    from admin_api.db.deps import get_db_session

    app = FastAPI()
    if group == "grants":
        app.include_router(permissions.router)
        app.include_router(permissions.tenant_permissions_router)
        app.include_router(budget_consumers.router)
    elif group == "budgets":
        app.include_router(budgets.router)
    else:  # pragma: no cover - a bad test table entry is a test bug
        raise AssertionError(f"unknown router group: {group}")

    recording = RecordingSession()

    async def _override_db_session() -> Any:
        yield recording

    app.dependency_overrides[get_db_session] = _override_db_session
    return app, recording


async def _send(
    app: Any,
    method: str,
    path: str,
    json_body: dict[str, Any] | None,
    cookies: dict[str, str] | None = None,
) -> Any:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    kwargs: dict[str, Any] = {"cookies": cookies} if cookies else {}
    async with AsyncClient(
        transport=transport, base_url="http://test", **kwargs
    ) as client:
        return await client.request(method, path, json=json_body)


# ---------------------------------------------------------------------------
# C-f8838ac0 — every tenant-scoped route has the dependency
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.l4("C-f8838ac0")
async def test_every_tenant_scoped_route_has_the_tenant_session() -> None:
    from admin_api.auth.sessions import require_tenant_session
    from admin_api.main import create_app

    app = create_app()
    routes = _collect_api_routes(app)
    tenant_scoped = [route for route in routes if _TENANT_SCOPED_RE.match(route.path)]
    checked = [route for route in tenant_scoped if route.path not in _CALLBACKS]

    # The floor guards against an empty walk (the base registers ~65 such routes).
    assert len(checked) >= 50, (
        f"Only {len(checked)} tenant-scoped routes were walked; "
        "routing may have changed and the walk is no longer meaningful"
    )

    missing: list[str] = []
    for route in checked:
        calls = _walk_dependant_calls(route.dependant)
        if require_tenant_session not in calls:
            methods = ",".join(sorted(route.methods or set()))
            missing.append(f"{methods} {route.path}")

    assert not missing, (
        "Tenant-scoped routes missing require_tenant_session "
        "(add `_authz: None = Depends(require_tenant_session)`):\n"
        + "\n".join(f"  {entry}" for entry in sorted(missing))
    )

    registered = [
        (method, route.path)
        for route in tenant_scoped
        for method in (route.methods or set())
    ]
    for (method, path), expected_count in _REQUIRED_ROUTES.items():
        count = registered.count((method, path))
        assert count >= expected_count, (
            f"Expected at least {expected_count} {method} {path} registration(s), "
            f"found {count}"
        )
        matching = [
            route
            for route in tenant_scoped
            if route.path == path and method in (route.methods or set())
        ]
        for route in matching:
            assert require_tenant_session in _walk_dependant_calls(route.dependant), (
                f"{method} {path} is registered but has no require_tenant_session"
            )


# ---------------------------------------------------------------------------
# C-b77996cc — a request without a session is refused before any statement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("group,method,path,json_body", _CASES, ids=_CASE_IDS)
@pytest.mark.l4("C-b77996cc")
async def test_requests_without_a_session_are_refused_before_any_statement(
    group: str,
    method: str,
    path: str,
    json_body: dict[str, Any] | None,
) -> None:
    app, session = build_app(group)

    response = await _send(app, method, path, json_body)

    assert response.status_code == 401, (
        f"{method} {path} did not refuse a request without a session: "
        f"{response.status_code} {response.text}"
    )
    assert response.json()["detail"]["mintkey:code"] == "unauthenticated"
    assert session.statements == [], (
        f"{method} {path} ran {len(session.statements)} statement(s) before "
        "the session dependency answered"
    )


# ---------------------------------------------------------------------------
# C-f7eab4f7 — an unknown or expired session is refused before any statement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("group,method,path,json_body", _CASES, ids=_CASE_IDS)
@pytest.mark.l4("C-f7eab4f7")
async def test_an_unknown_or_expired_session_is_refused_before_any_statement(
    group: str,
    method: str,
    path: str,
    json_body: dict[str, Any] | None,
) -> None:
    app, session = build_app(group)

    with patch(
        "admin_api.auth.sessions.validate_session", new=AsyncMock(return_value=None)
    ):
        response = await _send(
            app, method, path, json_body, cookies={"mintkey_session": "x"}
        )

    assert response.status_code == 401, (
        f"{method} {path} did not refuse an unknown session: "
        f"{response.status_code} {response.text}"
    )
    assert response.json()["detail"]["mintkey:code"] == "unauthenticated"
    assert session.statements == [], (
        f"{method} {path} ran {len(session.statements)} statement(s) before "
        "the session dependency answered"
    )


# ---------------------------------------------------------------------------
# C-89b1b8a2 — a session of another tenant is refused before any statement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("group,method,path,json_body", _CASES, ids=_CASE_IDS)
@pytest.mark.l4("C-89b1b8a2")
async def test_a_session_of_another_tenant_is_refused_before_any_statement(
    group: str,
    method: str,
    path: str,
    json_body: dict[str, Any] | None,
) -> None:
    app, session = build_app(group)
    other_tenant_session = SimpleNamespace(operator_id="op-1", tenant_id=TB)

    with (
        patch(
            "admin_api.auth.sessions.validate_session",
            new=AsyncMock(return_value=other_tenant_session),
        ),
        patch(
            "admin_api.auth.sessions._is_operator_platform_admin",
            new=AsyncMock(return_value=False),
        ),
    ):
        response = await _send(
            app, method, path, json_body, cookies={"mintkey_session": "x"}
        )

    assert response.status_code == 403, (
        f"{method} {path} did not refuse a session of another tenant: "
        f"{response.status_code} {response.text}"
    )
    assert response.json()["detail"]["mintkey:code"] == "permission_denied"
    assert session.statements == [], (
        f"{method} {path} ran {len(session.statements)} statement(s) before "
        "the session dependency answered"
    )


# ---------------------------------------------------------------------------
# C-8284500b — a session of the tenant, or a platform admin, reaches the handler
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@pytest.mark.parametrize("group,method,path,json_body", _CASES, ids=_CASE_IDS)
@pytest.mark.l4("C-8284500b")
async def test_a_session_of_the_tenant_or_a_platform_admin_reaches_the_handler(
    group: str,
    method: str,
    path: str,
    json_body: dict[str, Any] | None,
) -> None:
    runs = (
        # (session tenant, is platform admin)
        (TA, False),
        (TB, True),
    )
    for session_tenant, is_platform_admin in runs:
        app, session = build_app(group)
        tenant_session = SimpleNamespace(
            operator_id="op-1", tenant_id=session_tenant
        )

        with (
            patch(
                "admin_api.auth.sessions.validate_session",
                new=AsyncMock(return_value=tenant_session),
            ),
            patch(
                "admin_api.auth.sessions._is_operator_platform_admin",
                new=AsyncMock(return_value=is_platform_admin),
            ),
        ):
            response = await _send(
                app, method, path, json_body, cookies={"mintkey_session": "x"}
            )

        assert response.status_code not in (401, 403), (
            f"{method} {path} refused a valid session "
            f"(tenant={session_tenant}, platform_admin={is_platform_admin}): "
            f"{response.status_code} {response.text}"
        )
        assert session.statements, (
            f"{method} {path} reached no statement; the handler should run "
            "set_tenant_context before any lookup"
        )
