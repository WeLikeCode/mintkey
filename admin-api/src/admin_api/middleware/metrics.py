"""
Prometheus metrics middleware.

Records mintkey_requests_total and mintkey_request_duration_seconds for every
HTTP request handled by admin-api.

Key design decisions:
- Skip /metrics itself to avoid self-counting noise.
- Use the route template (e.g. /v1/tenants/{tenant_id}/services) rather than
  the raw request path — avoids cardinality explosion from UUID path segments.
- Wrap all metric calls in try/except — metrics export must never break a
  real request (graceful degradation per T-1.10.2).
- Added LAST in main.py so Starlette's reverse-add order makes it the
  outermost timer (measures full round-trip including other middleware).

Source: OPS-N; T-1.10.2; design §4.
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware

from admin_api.api.health import _REQUESTS_TOTAL, _REQUEST_DURATION, _PROMETHEUS_AVAILABLE


class MetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        if not _PROMETHEUS_AVAILABLE or request.url.path == "/metrics":
            return await call_next(request)
        start = time.monotonic()
        response = await call_next(request)
        elapsed = time.monotonic() - start
        # Use the route template (low cardinality), not the raw path.
        # request.scope["route"] is set by Starlette's Router after routing.
        route = request.scope.get("route")
        path_label = getattr(route, "path", request.url.path) if route else request.url.path
        try:
            _REQUESTS_TOTAL.labels(
                method=request.method,
                path=path_label,
                status=str(response.status_code),
            ).inc()
            _REQUEST_DURATION.labels(method=request.method, path=path_label).observe(elapsed)
        except Exception:
            pass  # Never break a request because metrics export failed
        return response
