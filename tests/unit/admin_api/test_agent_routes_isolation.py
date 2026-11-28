"""Unit tests: the agent route table is separate from the operator routes.

Task 6.1 of agent-service-routes. The three scenarios of "The agent routes are
separate from the operator routes" decide:

  1. every ``/v1/agent`` route has ``require_agent_principal`` (and neither
     operator session dependency) in its tree, no other route has it, the four
     routes have exactly the documented methods, and the parity snapshot maps
     ``agent`` to ``/v1/agent``;
  2. a cookie-less, Authorization-less POST reaches authentication (401
     ``mintkey:auth_required``), not the CSRF refusal;
  3. a consumer principal is refused 403 ``mintkey:role_forbidden`` on each of
     the four routes, with one ``agent.operation.denied`` event per call and no
     service statement.

Sources:
  - `openspec/changes/agent-service-routes/spec.md` — The agent routes are
    separate from the operator routes
  - `openspec/changes/agent-service-routes/design.md` — D1, D10
"""

# ruff: noqa: E402 — admin-api and mintkey-models are imported after sys.path setup.
from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock
from uuid import UUID

import pytest
from fastapi.routing import APIRoute
from httpx import ASGITransport, AsyncClient

REPO_ROOT = Path(__file__).resolve().parents[3]
ADMIN_API_SRC = REPO_ROOT / "apps" / "admin-api" / "src"
MODELS_SRC = REPO_ROOT / "packages" / "python" / "mintkey-models"
for _path in (ADMIN_API_SRC, MODELS_SRC):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from admin_api.auth import agent_principal
from admin_api.auth.agent_principal import (
    AgentApiError,
    AgentPrincipal,
    agent_api_error_handler,
    require_agent_principal,
)
from admin_api.auth.sessions import (
    require_platform_admin_session,
    require_tenant_session,
)
from admin_api.db.deps import get_db_session

TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
AGENT_ID = UUID("00000000-0000-0000-0000-000000000022")

CONSUMER = AgentPrincipal(tenant_id=TENANT_ID, agent_id=AGENT_ID, role="consumer")

AGENT_PREFIX = "/v1/agent"
SERVICES_PATH = "/v1/agent/services"
SERVICE_PATH = "/v1/agent/services/{service_ref}"
CREDENTIAL_PATH = "/v1/agent/services/{service_ref}/credential"

SNAPSHOT_PATH = REPO_ROOT / "tests" / "acceptance" / "openapi_snapshot.json"
MAIN_PY = ADMIN_API_SRC / "admin_api" / "main.py"


# ---------------------------------------------------------------------------
# App and route helpers
# ---------------------------------------------------------------------------


def _build_app() -> Any:
    """Build the real app with the same env the authz architecture test uses."""
    os.environ.setdefault("MINTKEY_AUDIT_HMAC_KEY", "aa" * 32)
    os.environ.setdefault("MINTKEY_VAULT_BACKEND", "sqlite")

    from admin_api.main import create_app

    return create_app()


def _walk_dependency_calls(dependant: Any, visited: set[int] | None = None) -> set[Any]:
    """Collect every callable of a FastAPI dependency tree (see authz test)."""
    if visited is None:
        visited = set()
    calls: set[Any] = set()
    key = id(dependant)
    if key in visited:
        return calls
    visited.add(key)
    if dependant.call is not None:
        calls.add(dependant.call)
    for child in dependant.dependencies:
        calls |= _walk_dependency_calls(child, visited)
    return calls


def _effective_routes(app: Any) -> list[tuple[str, set[str], Any]]:
    """Return ``(full path, methods, dependant)`` for every real APIRoute.

    FastAPI 0.163 stores included routers as ``_IncludedRouter`` objects and
    exposes the flattened path through ``effective_route_contexts()``; nested
    includes (the agent router includes the services sub-router) flatten too.
    """
    routes: list[tuple[str, set[str], Any]] = []
    for route in app.routes:
        original = getattr(route, "original_router", None)
        if original is not None:
            for context in route.effective_route_contexts():
                api_route = context.original_route
                if isinstance(api_route, APIRoute):
                    routes.append(
                        (
                            context.path,
                            set(api_route.methods or set()),
                            api_route.dependant,
                        )
                    )
            continue
        if isinstance(route, APIRoute):
            routes.append(
                (route.path, set(route.methods or set()), route.dependant)
            )
    return routes


def _is_agent_path(path: str) -> bool:
    return path == AGENT_PREFIX or path.startswith(AGENT_PREFIX + "/")


def _imports_agent_router_once(main_source: str) -> bool:
    """True when main.py imports ``router as agent_router`` from the agent module."""
    tree = ast.parse(main_source)
    aliases = [
        (alias.name, alias.asname)
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
        and node.module == "admin_api.api.agent"
        for alias in node.names
    ]
    return aliases.count(("router", "agent_router")) == 1


def _includes_agent_router_once(main_source: str) -> bool:
    tree = ast.parse(main_source)
    includes = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "include_router"
        and node.args
        and isinstance(node.args[0], ast.Name)
        and node.args[0].id == "agent_router"
    ]
    return len(includes) == 1


# ---------------------------------------------------------------------------
# Recording fakes for the consumer scenario
# ---------------------------------------------------------------------------


class _Result:
    """The slice of a SQLAlchemy result a context statement returns."""

    def fetchone(self) -> Any:
        return None


class _RecordingSession:
    """An async-context-manager session recording statements and commits."""

    def __init__(self) -> None:
        self.statements: list[tuple[str, dict[str, Any]]] = []
        self.commits = 0

    async def __aenter__(self) -> "_RecordingSession":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        return None

    async def commit(self) -> None:
        self.commits += 1

    async def execute(
        self,
        statement: Any,
        params: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> _Result:
        self.statements.append((" ".join(str(statement).split()), dict(params or {})))
        return _Result()


class _RecordingFactory:
    """Stand-in for ``AsyncSessionLocal`` that hands out one session."""

    def __init__(self, session: _RecordingSession) -> None:
        self.session = session
        self.calls = 0

    def __call__(self) -> _RecordingSession:
        self.calls += 1
        return self.session


def _consumer_app(route_session: _RecordingSession) -> Any:
    """The real app with the agent key resolved to a consumer principal."""

    app = _build_app()
    app.dependency_overrides[require_agent_principal] = lambda: CONSUMER

    async def _route_session() -> _RecordingSession:
        return route_session

    app.dependency_overrides[get_db_session] = _route_session
    return app


async def _send(app: Any, method: str, path: str) -> Any:
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.request(method, path)


# ---------------------------------------------------------------------------
# C-48021709 — the route table
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-48021709")
def test_C_48021709_agent_route_table_and_snapshot() -> None:
    app = _build_app()
    routes = _effective_routes(app)

    agent_routes = [
        (path, methods, dependant)
        for path, methods, dependant in routes
        if _is_agent_path(path)
    ]
    assert agent_routes, "create_app() exposes no /v1/agent routes"

    for path, methods, dependant in agent_routes:
        calls = _walk_dependency_calls(dependant)
        assert require_agent_principal in calls, (
            f"{path} lacks require_agent_principal in its dependency tree"
        )
        assert require_tenant_session not in calls, (
            f"{path} uses the operator tenant session"
        )
        assert require_platform_admin_session not in calls, (
            f"{path} uses the operator platform-admin session"
        )
        assert "DELETE" not in methods, f"{path} accepts DELETE"
        assert "transfer" not in path, f"{path} contains 'transfer'"
        assert "role" not in path, f"{path} contains 'role'"
        assert not ("GET" in methods and "credential" in path), (
            f"{path} answers GET on a credential path"
        )

    operator_routes = [
        (path, dependant)
        for path, _methods, dependant in routes
        if not _is_agent_path(path)
    ]
    leaked = [
        path
        for path, dependant in operator_routes
        if require_agent_principal in _walk_dependency_calls(dependant)
    ]
    assert leaked == [], (
        "operator routes accept the agent principal dependency: " + repr(leaked)
    )

    methods_by_path = {
        path: methods for path, methods, _dependant in agent_routes
    }
    assert methods_by_path.get(SERVICES_PATH) == {"POST", "GET"}, methods_by_path
    assert methods_by_path.get(SERVICE_PATH) == {"PATCH"}, methods_by_path
    assert methods_by_path.get(CREDENTIAL_PATH) == {"PUT"}, methods_by_path

    assert app.exception_handlers.get(AgentApiError) is agent_api_error_handler
    main_source = MAIN_PY.read_text()
    assert _imports_agent_router_once(main_source)
    assert _includes_agent_router_once(main_source)

    snapshot = json.loads(SNAPSHOT_PATH.read_text())
    assert snapshot.get("agent") == AGENT_PREFIX, snapshot


# ---------------------------------------------------------------------------
# C-96185b5c — a cookie-less POST reaches authentication
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-96185b5c")
@pytest.mark.asyncio
async def test_C_96185b5c_cookieless_post_reaches_agent_authentication() -> None:
    app = _build_app()

    response = await _send(app, "POST", SERVICES_PATH)

    assert response.status_code == 401, response.text
    assert response.json() == {
        "code": "mintkey:auth_required",
        "title": "Agent key required",
    }
    assert response.json()["code"] != "mintkey:csrf_missing"


# ---------------------------------------------------------------------------
# C-25c5b05b — a consumer key is refused on every route
# ---------------------------------------------------------------------------


@pytest.mark.l4("C-25c5b05b")
@pytest.mark.asyncio
async def test_C_25c5b05b_consumer_is_refused_on_each_route(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    denial_session = _RecordingSession()
    factory = _RecordingFactory(denial_session)
    audit = AsyncMock()
    monkeypatch.setattr(agent_principal, "AsyncSessionLocal", factory)
    monkeypatch.setattr(agent_principal, "audit_emit", audit, raising=False)

    route_session = _RecordingSession()
    app = _consumer_app(route_session)

    requests = [
        ("POST", SERVICES_PATH),
        ("GET", SERVICES_PATH),
        ("PATCH", "/v1/agent/services/x"),
        ("PUT", "/v1/agent/services/x/credential"),
    ]
    operations = [
        "POST /v1/agent/services",
        "GET /v1/agent/services",
        "PATCH /v1/agent/services/x",
        "PUT /v1/agent/services/x/credential",
    ]

    for method, path in requests:
        response = await _send(app, method, path)
        assert response.status_code == 403, (method, path, response.text)
        body = response.json()
        assert body["code"] == "mintkey:role_forbidden", (method, path, body)
        assert body["title"] == "Role not allowed", (method, path, body)
        assert body["role"] == "consumer", (method, path, body)

    assert audit.await_count == len(requests)
    recorded = [call.kwargs["payload"]["operation"] for call in audit.await_args_list]
    assert recorded == operations

    for call in audit.await_args_list:
        assert call.kwargs["event_type"] == "agent.operation.denied"
        assert call.kwargs["actor_type"] == "agent"
        assert call.kwargs["actor_id"] == AGENT_ID

    assert factory.calls == len(requests)
    for sql, _params in denial_session.statements:
        assert "set_config" in sql.lower()
        assert "services" not in sql.lower()

    assert route_session.statements == []
