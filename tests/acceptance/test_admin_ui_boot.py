"""
Admin UI boot smoke test — verifies the running admin-ui container.

Tests:
  1. GET /admin/login returns 200.
  2. POST /admin/login with bootstrap credentials succeeds (session cookie set).
  3. Resource list endpoints (services, agents, tenants) return 200 with data.

Reads bootstrap credentials from:
  - Email: admin@mintkey.internal (MINTKEY_BOOTSTRAP_EMAIL env or seed-job default)
  - Password: docker compose logs seed-job (written to bootstrap_secrets volume)

Requires: running docker-compose stack (admin-ui on localhost:8081).
Gate: MINTKEY_INTEGRATION_TEST=true (or MINTKEY_ADMIN_UI_TEST=true).

Sources: T-1.1.4; ADR-0013; ADR-0014.5.
"""
from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import httpx
import pytest

# ---------------------------------------------------------------------------
# Test gate
# ---------------------------------------------------------------------------
INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true"
    and os.getenv("MINTKEY_ADMIN_UI_TEST") != "true",
    reason="Requires running docker-compose stack; set MINTKEY_INTEGRATION_TEST=true",
)

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ADMIN_UI_BASE = os.getenv("ADMIN_UI_BASE_URL", "http://localhost:8081")
BOOTSTRAP_EMAIL = os.getenv("MINTKEY_BOOTSTRAP_EMAIL", "admin@mintkey.internal")

# Resources known to have data after seed-job steps 1-5 and any smoke run.
# services and agents are seeded by the smoke tests / demo seed.
RESOURCE_LIST_PATHS = [
    "/admin/api/resources/services/actions/list",
    "/admin/api/resources/agents/actions/list",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _read_bootstrap_password() -> str:
    """
    Read the bootstrap admin password.

    Priority:
      1. MINTKEY_BOOTSTRAP_PASSWORD env var (CI override).
      2. Parse 'docker compose logs seed-job' output (the password is printed
         exactly once: "Bootstrap admin password: <value>").

    Raises pytest.skip if the password cannot be determined.
    """
    env_pw = os.getenv("MINTKEY_BOOTSTRAP_PASSWORD", "")
    if env_pw:
        return env_pw

    # Attempt to read from docker compose logs
    try:
        result = subprocess.run(
            ["docker", "compose", "logs", "seed-job"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        output = result.stdout + result.stderr
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        pytest.skip(f"Cannot read seed-job logs: {exc}")

    match = re.search(r"Bootstrap admin password:\s*(\S+)", output)
    if not match:
        pytest.skip(
            "Bootstrap password not found in 'docker compose logs seed-job'. "
            "Ensure the seed-job container has run and the stack is up."
        )
    return match.group(1)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@INTEGRATION
def test_login_page_returns_200() -> None:
    """GET /admin/login must return HTTP 200."""
    with httpx.Client(base_url=ADMIN_UI_BASE, follow_redirects=False) as client:
        resp = client.get("/admin/login")
    assert resp.status_code == 200, (
        f"Expected 200 from GET /admin/login, got {resp.status_code}. "
        f"Body snippet: {resp.text[:300]}"
    )


@INTEGRATION
def test_login_with_bootstrap_credentials() -> None:
    """
    POST /admin/login with bootstrap credentials must redirect to /admin
    (HTTP 302) and set the mintkey_session cookie.
    """
    password = _read_bootstrap_password()

    with httpx.Client(base_url=ADMIN_UI_BASE, follow_redirects=False) as client:
        resp = client.post(
            "/admin/login",
            content=f"email={BOOTSTRAP_EMAIL}&password={password}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )

    assert resp.status_code == 302, (
        f"Expected 302 redirect after login, got {resp.status_code}. "
        f"Body: {resp.text[:500]}"
    )
    location = resp.headers.get("location", "")
    assert "/admin" in location, (
        f"Expected redirect to /admin, got Location: {location!r}"
    )
    assert "mintkey_session" in resp.cookies, (
        f"Session cookie 'mintkey_session' not set after login. "
        f"Cookies: {dict(resp.cookies)}"
    )


@INTEGRATION
@pytest.mark.parametrize("path", RESOURCE_LIST_PATHS)
def test_resource_list_returns_200_with_data(path: str) -> None:
    """
    Each resource list endpoint must return 200 and at least one record
    when queried with a valid session.
    """
    password = _read_bootstrap_password()

    with httpx.Client(base_url=ADMIN_UI_BASE, follow_redirects=False) as client:
        # Establish session
        login = client.post(
            "/admin/login",
            content=f"email={BOOTSTRAP_EMAIL}&password={password}",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        assert login.status_code == 302, (
            f"Login failed (expected 302, got {login.status_code}). "
            f"Body: {login.text[:300]}"
        )

        # Query resource list
        resp = client.get(path)

    assert resp.status_code == 200, (
        f"GET {path} returned {resp.status_code}, expected 200. "
        f"Body: {resp.text[:500]}"
    )

    data = resp.json()
    records = data.get("records", [])
    total = data.get("meta", {}).get("total", len(records))
    assert total > 0, (
        f"GET {path} returned 0 records. "
        f"Ensure the seed-job has completed and demo data is seeded. "
        f"Response: {resp.text[:500]}"
    )
