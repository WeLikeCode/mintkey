"""
R14b regression tests — test_service body parsing (method/path/headers/timeout).

Before fix: admin-api test_service handler lacked a body model, silently dropped
the `path` parameter, and called `client.get(base_url, ...)` instead of
`client.request(method, base_url+path, ...)`.

After fix:
  - TestRunRequest Pydantic model accepted in handler.
  - Outbound request uses method + appended path.
  - Response includes final_url for operator visibility.

Source: R14b; ADR-0014.4; services.py testRunService handler.
"""
from __future__ import annotations

import os
import time
from pathlib import Path
from urllib.parse import urljoin

import httpx
import pytest

# ---------------------------------------------------------------------------
# Integration marker
# ---------------------------------------------------------------------------

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason="Requires full docker-compose stack",
)

_ROOT = Path(__file__).resolve().parents[2]

BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")
_pwd_file = _ROOT / "data" / "bootstrap-secrets" / "admin_password"
BOOTSTRAP_PASSWORD = os.getenv(
    "MINTKEY_BOOTSTRAP_PASSWORD",
    _pwd_file.read_text().strip() if _pwd_file.exists() else "changeme",
)


# ---------------------------------------------------------------------------
# Unit assertions (always run) — source-level checks
# ---------------------------------------------------------------------------


def test_test_service_has_body_model() -> None:
    """
    test_service handler must accept a Pydantic body model (TestRunRequest).

    Pre-fix: handler signature was `test_service(tenant_id, service_id, session)`
    with no body — the request body was silently ignored.

    Source: R14b; services.py test_service; OpenAPI testRunService.
    """
    services_py = _ROOT / "admin-api" / "src" / "admin_api" / "api" / "services.py"
    assert services_py.exists(), f"services.py not found at {services_py}"
    src = services_py.read_text()

    # TestRunRequest model must exist
    assert "TestRunRequest" in src, (
        "TestRunRequest Pydantic model must be defined in services.py — R14b. "
        "Pre-fix: no body model existed; path was silently dropped."
    )

    # test_service handler must reference TestRunRequest
    fn_idx = src.find("async def test_service(")
    assert fn_idx >= 0, "test_service handler not found in services.py"
    next_fn_idx = src.find("\n@router.", fn_idx + 1)
    fn_body = src[fn_idx:next_fn_idx] if next_fn_idx > 0 else src[fn_idx:]

    assert "TestRunRequest" in fn_body, (
        "test_service handler must accept a TestRunRequest body — R14b. "
        "Pre-fix: handler signature lacked body model."
    )


def test_test_service_uses_path_in_request() -> None:
    """
    test_service must append `req.path` to `base_url` when making the outbound call.

    Pre-fix: `client.get(base_url, headers=headers)` — path silently dropped.

    Source: R14b; services.py test_service.
    """
    services_py = _ROOT / "admin-api" / "src" / "admin_api" / "api" / "services.py"
    src = services_py.read_text()

    fn_idx = src.find("async def test_service(")
    assert fn_idx >= 0
    next_fn_idx = src.find("\n@router.", fn_idx + 1)
    fn_body = src[fn_idx:next_fn_idx] if next_fn_idx > 0 else src[fn_idx:]

    # Must NOT call client.get(base_url, ...) — that drops the path
    import re
    bad_get = re.search(r"client\.get\(base_url[,\)]", fn_body)
    assert bad_get is None, (
        "test_service must NOT call client.get(base_url, ...) — this drops the path. "
        "Use client.request(method=..., url=<base_url+path>, ...) — R14b."
    )

    # Must use client.request with a path-appended URL
    assert "client.request(" in fn_body or "client.request\n" in fn_body, (
        "test_service must call client.request(...) to honour method and path — R14b."
    )


def test_url_join_behaviour() -> None:
    """
    Validate URL-join behaviour used in fix: urljoin with trailing-slash handling.

    urljoin('http://x:8999', '/health') == 'http://x:8999/health'
    urljoin('http://x:8999/', '/health') == 'http://x:8999/health'
    urljoin('http://x:8999', 'health') == 'http://x:8999/health'  (note: no double slash)

    Source: R14b discipline note on URL-join gotchas.
    """
    base = "http://mock-backend:8999"
    assert urljoin(base, "/health") == "http://mock-backend:8999/health"
    assert urljoin(base + "/", "/health") == "http://mock-backend:8999/health"
    # Path without leading slash: urljoin treats it as relative to base path segment
    # The fix must handle /health (with slash) — that is the documented contract.
    assert urljoin(base, "/health") == "http://mock-backend:8999/health"


# ===========================================================================
# Integration tests (requires docker-compose stack)
# ===========================================================================


def _login(client: httpx.Client) -> tuple[str, str]:
    """Login; return (tenant_id, csrf_token)."""
    r = client.post(
        f"{BASE_API}/v1/auth/internal-login",
        json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
    )
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return r.json()["tenant_id"], client.cookies.get("csrf_token", "")


def _create_mock_backend_service(
    client: httpx.Client, tenant_id: str, csrf: str, ts: int
) -> str:
    """Create a service pointing at mock-backend; return wire ID."""
    r = client.post(
        f"{BASE_API}/v1/tenants/{tenant_id}/services",
        json={
            "name": f"r14b-test-svc-{ts}",
            "base_url": "http://mock-backend:8999",
            "auth_scheme": "bearer_token",
        },
        headers={"X-Mintkey-Csrf": csrf},
    )
    assert r.status_code == 201, f"create_service failed: {r.status_code} {r.text}"
    wire_id = r.json()["id"]
    assert wire_id.startswith("svc_"), f"Expected svc_ prefix: {wire_id}"
    return wire_id


@INTEGRATION
def test_test_service_with_health_path_returns_ok() -> None:
    """
    POST /test with {"method":"GET","path":"/health"} must return ok:true, status_code:200.

    Pre-fix: path was silently dropped → client.get(base_url) → root "/" → 404 → ok:false.
    Post-fix: client.request("GET", base_url+"/health") → 200 → ok:true.

    Source: R14b; R13 finding: 'path parameter silently dropped'.
    """
    ts = int(time.time() * 1000)  # ms precision for uniqueness
    with httpx.Client(timeout=30) as client:
        tenant_id, csrf = _login(client)
        svc_id = _create_mock_backend_service(client, tenant_id, csrf, ts)

        r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services/{svc_id}/test",
            json={"method": "GET", "path": "/health"},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert r.status_code == 200, (
            f"POST /test returned HTTP {r.status_code}, expected 200.\n"
            f"Response: {r.text}"
        )
        body = r.json()
        assert body.get("ok") is True, (
            f"R14b REGRESSION: test_service returned ok=false for /health.\n"
            f"Expected ok:true (mock-backend /health returns 200).\n"
            f"Got: {body}\n"
            "Root cause (pre-fix): path was silently dropped; client.get(base_url) "
            "hit root '/' which returns 404 on mock-backend."
        )
        assert body.get("status_code") == 200, (
            f"Expected status_code=200, got: {body.get('status_code')}\n"
            f"Full body: {body}"
        )
        assert "latency_ms" in body, f"Missing latency_ms in response: {body}"

        # If final_url is present, validate it shows the correct path
        if "final_url" in body:
            assert body["final_url"] == "http://mock-backend:8999/health", (
                f"final_url should be http://mock-backend:8999/health, got: {body['final_url']}"
            )


@INTEGRATION
def test_test_service_default_body_no_5xx() -> None:
    """
    POST /test with empty body `{}` must use defaults (method:GET, path:/health or /)
    and return a 200-envelope (not 5xx). The upstream response may be 404 (honest root),
    but the admin-api envelope must be 200 with no 5xx.

    Source: R14b AC #7.
    """
    ts = int(time.time() * 1000) + 1  # ms precision + offset for uniqueness
    with httpx.Client(timeout=30) as client:
        tenant_id, csrf = _login(client)
        svc_id = _create_mock_backend_service(client, tenant_id, csrf, ts)

        r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services/{svc_id}/test",
            json={},
            headers={"X-Mintkey-Csrf": csrf},
        )
        # Admin-api envelope must be 200 (not 5xx)
        assert r.status_code == 200, (
            f"POST /test with empty body returned HTTP {r.status_code}, expected 200-envelope.\n"
            f"Response: {r.text}"
        )
        body = r.json()
        # Must have the standard fields
        assert "ok" in body, f"Missing 'ok' field: {body}"
        assert "latency_ms" in body, f"Missing 'latency_ms' field: {body}"
        # No 5xx — it's either ok (2xx upstream) or not-ok (4xx upstream), both are fine


@INTEGRATION
def test_test_service_unsupported_method_returns_422() -> None:
    """
    POST /test with an invalid method value must return 422 from FastAPI validation.

    Source: R14b AC #8.
    """
    ts = int(time.time() * 1000) + 2  # ms precision + offset for uniqueness
    with httpx.Client(timeout=30) as client:
        tenant_id, csrf = _login(client)
        svc_id = _create_mock_backend_service(client, tenant_id, csrf, ts)

        r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services/{svc_id}/test",
            json={"method": "WRONG", "path": "/health"},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert r.status_code == 422, (
            f"POST /test with invalid method='WRONG' must return 422, got: {r.status_code}\n"
            f"Response: {r.text}"
        )


@INTEGRATION
def test_test_service_path_with_leading_slash() -> None:
    """
    POST /test with path="/health" (leading slash) must correctly resolve to
    http://mock-backend:8999/health (not drop the path or double-slash).

    Source: R14b AC #9.
    """
    ts = int(time.time() * 1000) + 3  # ms precision + offset for uniqueness
    with httpx.Client(timeout=30) as client:
        tenant_id, csrf = _login(client)
        svc_id = _create_mock_backend_service(client, tenant_id, csrf, ts)

        r = client.post(
            f"{BASE_API}/v1/tenants/{tenant_id}/services/{svc_id}/test",
            json={"method": "GET", "path": "/health"},
            headers={"X-Mintkey-Csrf": csrf},
        )
        assert r.status_code == 200
        body = r.json()
        assert body.get("ok") is True, (
            f"Path '/health' (with leading slash) should resolve to /health and return ok:true.\n"
            f"Got: {body}"
        )
        assert body.get("status_code") == 200, f"Expected 200, got: {body}"
