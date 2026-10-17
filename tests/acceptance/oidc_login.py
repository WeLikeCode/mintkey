"""Shared login helper for the stack-based acceptance tests.

Operators are provisioned through Keycloak (OIDC); the bootstrap admin has no internal password
hash, so POST /v1/auth/internal-login answers 404 on a freshly seeded stack. These tests therefore
drive the same headless OIDC flow the browser uses (and apps/admin-ui/e2e/global-setup.ts).
"""

from __future__ import annotations

import os
import re

import httpx


def oidc_login(client: httpx.Client, base_api: str, password: str) -> str:
    """Drive the Keycloak OIDC headless flow and return the csrf_token value.

    Flow (mirrors apps/admin-ui/e2e/global-setup.ts but in Python/httpx):
      1. GET {base_api}/v1/auth/oidc/login        → 302 to Keycloak auth URL
         (admin-api generates PKCE state + stores it in _state_store)
      2. GET Keycloak auth URL                     → 200 HTML login form
         (parse <form action=...> + hidden fields)
      3. POST username + password to Keycloak form → 302 to callback
      4. GET {base_api}/v1/auth/oidc/callback      → 302 to admin-ui
         (admin-api exchanges code, creates session, sets cookies)
      After step 4 the client jar holds:
        mintkey_session  — httponly session cookie
        csrf_token       — non-httponly; read back for X-Mintkey-Csrf header
    Returns the csrf_token string.
    """
    username = os.getenv("MINTKEY_OIDC_USER", "admin@mintkey.internal")

    # Step 1 — trigger OIDC login: admin-api builds auth_url + stores PKCE state
    r1 = client.get(f"{base_api}/v1/auth/oidc/login", follow_redirects=False)
    assert r1.status_code == 302, (
        f"OIDC login redirect: expected 302, got {r1.status_code}"
    )
    kc_auth_url = r1.headers["location"]

    # Step 2 — fetch Keycloak login page (follow any internal Keycloak redirects)
    r2 = client.get(kc_auth_url, follow_redirects=True)
    assert r2.status_code == 200, (
        f"Keycloak login page: expected 200, got {r2.status_code}"
    )
    m = re.search(r'action="([^"]+)"', r2.text)
    assert m, "Keycloak login page: <form action> not found"
    form_action = m.group(1).replace("&amp;", "&")

    # Step 3 — POST credentials to Keycloak
    r3 = client.post(
        form_action,
        data={"username": username, "password": password, "credentialId": ""},
        follow_redirects=False,
    )
    assert r3.status_code in (301, 302, 303, 307, 308), (
        f"Keycloak credentials POST: expected redirect, got {r3.status_code}. "
        "Possible bad password. Body: " + r3.text[:300]
    )
    callback_url = r3.headers["location"]

    # Step 4 — follow callback to admin-api; it sets mintkey_session + csrf_token cookies
    r4 = client.get(callback_url, follow_redirects=False)
    # Callback returns 302 to admin-ui on success; any 4xx/5xx is a failure
    assert r4.status_code in (301, 302, 303, 307, 308), (
        f"OIDC callback: expected redirect, got {r4.status_code} {r4.text[:300]}"
    )

    csrf_token = client.cookies.get("csrf_token")
    assert csrf_token, (
        "OIDC callback: csrf_token cookie not set after successful login"
    )
    assert "mintkey_session" in client.cookies, (
        "OIDC callback: mintkey_session cookie not set"
    )
    return csrf_token


def admin_session(client: httpx.Client, base_api: str, password: str) -> tuple[str, str]:
    """OIDC-login as the bootstrap admin on `client`. Returns (tenant_id, csrf_token)."""
    csrf = oidc_login(client, base_api, password)
    whoami = client.get(f"{base_api}/v1/auth/whoami")
    assert whoami.status_code == 200, f"whoami after OIDC login: {whoami.status_code} {whoami.text}"
    return whoami.json()["operator"]["tenant_id"], csrf
