"""
CSRF middleware — double-submit cookie pattern.

Validates X-Mintkey-Csrf header against the csrf_token cookie on
state-changing requests. Skips GET/HEAD. Skips routes decorated @no_csrf.

Source: design §4; ADR-0013; ADR-0017.3 (CsrfHeader security scheme).
"""
from __future__ import annotations

import hmac
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

NO_CSRF_ATTR = "_no_csrf"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
CSRF_COOKIE = "csrf_token"
CSRF_HEADER = "x-mintkey-csrf"

# Paths registered as CSRF-exempt via @no_csrf decorator.
_CSRF_EXEMPT_PATHS: set[str] = set()


def no_csrf(func: Callable) -> Callable:
    """
    Decorator: mark a route handler to skip CSRF validation.
    Also registers the route path in _CSRF_EXEMPT_PATHS so middleware can check it.
    """
    setattr(func, NO_CSRF_ATTR, True)
    # Register by name for path-based lookup in middleware.
    _CSRF_EXEMPT_PATHS.add(f"/{func.__module__.split('.')[-1]}/{func.__name__}")
    return func


def csrf_exempt(path: str) -> None:
    """Explicitly register a path as CSRF-exempt (used in app factory)."""
    _CSRF_EXEMPT_PATHS.add(path)


class CsrfMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in SAFE_METHODS:
            return await call_next(request)

        # Routing hasn't happened yet at middleware time, so check path directly.
        # Use startswith so that prefix registrations like /v1/proxy/call match
        # dynamic segments such as /v1/proxy/call/svc_abc/messages.json.
        if any(request.url.path == p or request.url.path.startswith(p + "/") for p in _CSRF_EXEMPT_PATHS):
            return await call_next(request)

        cookie_token = request.cookies.get(CSRF_COOKIE)
        header_token = request.headers.get(CSRF_HEADER)

        if not cookie_token or not header_token:
            return Response(
                content='{"code":"mintkey:csrf_missing"}',
                status_code=403,
                media_type="application/json",
            )

        if not hmac.compare_digest(cookie_token, header_token):
            return Response(
                content='{"code":"mintkey:csrf_invalid"}',
                status_code=403,
                media_type="application/json",
            )

        return await call_next(request)
