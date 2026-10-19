"""
Unit tests for admin_api.middleware.otel._safe_get_route_details.

Guards the monkey-patch applied in configure_otel() against regression.
The root bug: OpenTelemetry's _get_route_details lacked try/except on
the Match.PARTIAL branch, so FastAPI's _IncludedRouter objects (produced
by include_router — they have no .path attribute) caused an AttributeError
that 500'd every instrumented request.

See apps/admin-api/src/admin_api/middleware/otel.py.
"""
from __future__ import annotations

from starlette.routing import Match, Route

from admin_api.middleware.otel import _safe_get_route_details


class _RouterWithoutPath:
    """Simulates FastAPI's _IncludedRouter: has matches() but no .path."""

    def __init__(self, match_result: Match) -> None:
        self._match = match_result

    def matches(self, scope: dict) -> tuple[Match, dict]:
        return self._match, {}


class _FakeApp:
    def __init__(self, routes: list) -> None:
        self.routes = routes


def _scope(path: str = "/test", app: object = None) -> dict:
    return {"type": "http", "path": path, "app": app or _FakeApp([])}


def test_partial_match_router_without_path_falls_back_to_scope_path() -> None:
    """The exact crash scenario: PARTIAL on _IncludedRouter must not raise AttributeError."""
    app = _FakeApp([_RouterWithoutPath(Match.PARTIAL)])
    result = _safe_get_route_details(_scope("/v1/tenants/abc/agent-secrets", app))
    assert result == "/v1/tenants/abc/agent-secrets"


def test_full_match_router_without_path_falls_back_to_scope_path() -> None:
    """FULL match on _IncludedRouter (no .path) must also fall back gracefully."""
    app = _FakeApp([_RouterWithoutPath(Match.FULL)])
    result = _safe_get_route_details(_scope("/v1/tenants/abc/agent-secrets", app))
    assert result == "/v1/tenants/abc/agent-secrets"


def test_none_match_returns_none() -> None:
    """When no route matches the result is None — same as the original upstream."""
    app = _FakeApp([_RouterWithoutPath(Match.NONE)])
    result = _safe_get_route_details(_scope("/v1/unknown", app))
    assert result is None


def test_empty_routes_returns_none() -> None:
    result = _safe_get_route_details(_scope("/v1/test", _FakeApp([])))
    assert result is None
