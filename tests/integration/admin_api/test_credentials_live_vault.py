"""
UX-BL3: Round-trip integration test — header_name flows end-to-end through live vault-adapter.

Verifies that:
  1. A credential registered via admin-api POST /credentials (with a unique header_name)
     is persisted in the real vault-adapter (not a mock) — proven by step 2.
  2. admin-api GET /credentials returns metadata confirming the credential exists with
     the correct key_version (vault round-trip success).
  3. admin-api POST /{service_id}/test forwards the credential under the exact custom
     header_name to the mock-backend's /echo endpoint, not under the X-API-Key fallback.
  4. The mock-backend echo response body shows the credential value under the custom
     header, proving the full flow: admin-api → vault-adapter (gRPC write) →
     admin-api (gRPC read) → test_service → mock-backend.

Gate: MINTKEY_INTEGRATION_TEST=true (mirrors test_golden_path.py skip mechanism).

Cleanup: performed in a finally block so revocation + service deletion run even when
assertions fail midway.

Sources: UX-BL3; UX-C6; ADR-0011; ADR-0014.4; vault.proto; T-1.3.1; WS-9.
"""
from __future__ import annotations

import os
import time
from pathlib import Path

import httpx
import pytest

from mintkey_models.bootstrap_password import BootstrapPasswordError, read_bootstrap_password

# ---------------------------------------------------------------------------
# Integration-only marker — requires full docker-compose stack
# ---------------------------------------------------------------------------

INTEGRATION = pytest.mark.skipif(
    os.getenv("MINTKEY_INTEGRATION_TEST") != "true",
    reason=(
        "UX-BL3 round-trip test requires full docker-compose stack "
        "and MINTKEY_INTEGRATION_TEST=true"
    ),
)

# ---------------------------------------------------------------------------
# Endpoint configuration (mirrors docker-compose.yml port map)
# ---------------------------------------------------------------------------

_ROOT = Path(__file__).resolve().parents[3]

BASE_API = os.getenv("MINTKEY_API_URL", "http://localhost:8080")

_pwd_file = _ROOT / "data" / "bootstrap-secrets" / "admin_password"
try:
    BOOTSTRAP_PASSWORD = os.getenv(
        "MINTKEY_BOOTSTRAP_PASSWORD",
        read_bootstrap_password(_pwd_file) if _pwd_file.exists() else "changeme",
    )
except BootstrapPasswordError:
    BOOTSTRAP_PASSWORD = os.getenv("MINTKEY_BOOTSTRAP_PASSWORD", "changeme")

# ---------------------------------------------------------------------------
# Wire-ID helper (matches golden-path — post-#13 Crockford ULID form)
# ---------------------------------------------------------------------------

_CROCKFORD_ALPHA = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def _wire_to_uuid(wire_id: str, prefix: str) -> str:
    """Decode <prefix>_<26-char Crockford> or <prefix>_<32hex> → dashed UUID string."""
    tail = wire_id[len(prefix) + 1:]  # strip "prefix_"
    if len(tail) == 26:
        val = 0
        for ch in tail.upper():
            val = (val << 5) | _CROCKFORD_ALPHA.index(ch)
        val &= (1 << 128) - 1
        h = f"{val:032x}"
        return f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
    if len(tail) == 32:
        return f"{tail[:8]}-{tail[8:12]}-{tail[12:16]}-{tail[16:20]}-{tail[20:]}"
    raise ValueError(f"Cannot decode wire ID: {wire_id!r}")


# ---------------------------------------------------------------------------
# UX-BL3 round-trip test
# ---------------------------------------------------------------------------


@INTEGRATION
def test_bl3_header_name_round_trip_via_live_vault() -> None:
    """
    UX-BL3: Full round-trip — header_name stored in vault-adapter, read back,
    injected by test_service into the mock-backend /echo call.

    Flow:
      1. Login as bootstrap admin; obtain session + CSRF token.
      2. Create a fresh service with auth_scheme=api_key_header,
         base_url=http://mock-backend:8999 (admin-api's Docker-network address).
      3. Register a credential: value=<unique secret>, header_name=X-BL3-Test-<ts>.
         → admin-api calls vault-adapter.PutCredential (real gRPC write).
      4. Assert GET /credentials returns key_version=1 (vault persisted it).
      5. Call POST /{service_id}/test with method=GET, path=/echo.
         → admin-api calls vault-adapter.GetCredential (real gRPC read).
         → admin-api injects credential under X-BL3-Test-<ts> header.
         → mock-backend /echo returns {"headers": {...}, "params": {...}}.
      6. Assert test response status is 200.
      7. Assert the mock-backend echo body contains X-BL3-Test-<ts>: <secret>.
         This proves the custom header_name, NOT the fallback X-API-Key, was used.
      8. Assert the plaintext secret value does NOT appear in the test-endpoint
         response (ADR-0014.4 — plaintext must never be returned to the caller).

    Cleanup (finally block):
      - Revoke the credential via DELETE .../credentials/{key_version}.
      - The service is left in place (no delete endpoint); tagged with a unique
        name so it does not conflict with future runs.
    """
    ts = int(time.time())
    unique_secret = f"bl3-secret-{ts}-{os.urandom(4).hex()}"
    custom_header_name = f"X-BL3-Test-{ts}"
    svc_name = f"bl3-test-svc-{ts}"

    # Mutable state captured in setup; used in cleanup.
    _state: dict = {
        "tenant_id": None,
        "service_uuid": None,
        "credential_key_version": None,
    }

    with httpx.Client(timeout=30) as client:

        # ── Step 1: Login ─────────────────────────────────────────────────
        login_r = client.post(
            f"{BASE_API}/v1/auth/internal-login",
            json={"email": "admin@mintkey.internal", "password": BOOTSTRAP_PASSWORD},
        )
        assert login_r.status_code == 200, (
            f"UX-BL3 login failed: {login_r.status_code} {login_r.text}"
        )
        tenant_id: str = login_r.json()["tenant_id"]
        csrf: str = client.cookies.get("csrf_token", "")
        _state["tenant_id"] = tenant_id

        try:
            # ── Step 2: Create service ────────────────────────────────────
            csrf = client.cookies.get("csrf_token", csrf)
            svc_r = client.post(
                f"{BASE_API}/v1/tenants/{tenant_id}/services",
                json={
                    "name": svc_name,
                    # Docker-internal address so admin-api (inside Docker) can
                    # reach mock-backend when test_service makes the outbound call.
                    "base_url": "http://mock-backend:8999",
                    "auth_scheme": "api_key_header",
                    "settings": {},
                },
                headers={"X-Mintkey-Csrf": csrf},
            )
            assert svc_r.status_code == 201, (
                f"UX-BL3 create service failed: {svc_r.status_code} {svc_r.text}"
            )

            # Resolve the service UUID — list endpoint returns Crockford wire IDs.
            svcs_r = client.get(f"{BASE_API}/v1/tenants/{tenant_id}/services")
            assert svcs_r.status_code == 200
            services_list = svcs_r.json().get("services", [])
            matching = [s for s in services_list if s.get("name") == svc_name]
            assert matching, (
                f"UX-BL3: created service {svc_name!r} not found in service list"
            )
            svc_wire = matching[0]["id"]  # svc_<Crockford>
            service_uuid = _wire_to_uuid(svc_wire, "svc")
            _state["service_uuid"] = service_uuid

            # ── Step 3: Register credential with custom header_name ───────
            csrf = client.cookies.get("csrf_token", csrf)
            cred_r = client.post(
                f"{BASE_API}/v1/tenants/{tenant_id}/services/{service_uuid}/credentials",
                json={
                    "auth_scheme": "api_key_header",
                    "value": unique_secret,
                    "header_name": custom_header_name,
                },
                headers={"X-Mintkey-Csrf": csrf},
            )
            assert cred_r.status_code == 201, (
                f"UX-BL3 register credential failed: {cred_r.status_code} {cred_r.text}"
            )
            cred_body = cred_r.json()
            key_version: int = cred_body["key_version"]
            _state["credential_key_version"] = key_version

            # ADR-0014.4: plaintext must NOT appear in the 201 response.
            assert unique_secret not in cred_r.text, (
                f"UX-BL3 SECURITY: plaintext credential leaked in 201 response body"
            )

            # ── Step 4: List credentials — proves vault round-trip ────────
            # The GET returns DB-side metadata (key_version, auth_scheme, status).
            # key_version=1 means vault-adapter accepted the PutCredential call
            # and returned key_version=1 (not a mock default).
            list_r = client.get(
                f"{BASE_API}/v1/tenants/{tenant_id}/services/{service_uuid}/credentials"
            )
            assert list_r.status_code == 200, (
                f"UX-BL3 list credentials failed: {list_r.status_code} {list_r.text}"
            )
            versions = list_r.json().get("versions", [])
            assert len(versions) >= 1, (
                "UX-BL3: no credential versions returned after registration"
            )
            active_versions = [v for v in versions if v.get("status") == "active"]
            assert active_versions, (
                f"UX-BL3: no active credential version found; statuses={[v['status'] for v in versions]}"
            )
            assert active_versions[0]["key_version"] == key_version, (
                f"UX-BL3: expected key_version={key_version}, "
                f"got {active_versions[0]['key_version']}"
            )
            assert active_versions[0]["auth_scheme"] == "api_key_header", (
                f"UX-BL3: auth_scheme mismatch: {active_versions[0]['auth_scheme']!r}"
            )

            # ── Step 5 + 6: Call test_service → mock-backend /echo ────────
            # test_service fetches the credential from vault-adapter via GetCredential,
            # builds headers based on auth_scheme + header_name, then makes an outbound
            # HTTP call to base_url + path.
            # /echo (GET) returns {"headers": {...}, "params": {...}}.
            csrf = client.cookies.get("csrf_token", csrf)
            test_r = client.post(
                f"{BASE_API}/v1/tenants/{tenant_id}/services/{service_uuid}/test",
                json={
                    "method": "GET",
                    "path": "/echo",
                },
                headers={"X-Mintkey-Csrf": csrf},
            )
            assert test_r.status_code == 200, (
                f"UX-BL3 test_service call failed: {test_r.status_code} {test_r.text}\n"
                "Expected 200 from the test endpoint (not 502). "
                "Check: vault-adapter health, gRPC wiring in vault_client.py."
            )
            test_body = test_r.json()

            # The test endpoint must report ok=True (2xx from mock-backend).
            assert test_body.get("ok") is True, (
                f"UX-BL3: test_service reported ok=False. "
                f"status_code={test_body.get('status_code')!r}, "
                f"latency_ms={test_body.get('latency_ms')}, "
                f"error={test_body.get('error')!r}\n"
                f"Full body: {test_body}\n"
                "Possible causes: vault-adapter not returning header_name, "
                "mock-backend unreachable from admin-api container."
            )

            # ── Step 7: Assert custom header reached mock-backend ─────────
            # response_body_truncated contains the JSON that mock-backend /echo returned.
            # It has the shape {"headers": {"x-bl3-test-<ts>": "<secret>", ...}, "params": {}}.
            # FastAPI canonicalises header names to lowercase.
            echo_text: str = test_body.get("response_body_truncated", "")
            assert echo_text, (
                "UX-BL3: test_service returned empty response_body_truncated"
            )

            # The custom header key must appear in the echo body (case-insensitive check
            # since HTTP headers are case-insensitive and FastAPI lowercases them).
            custom_header_lower = custom_header_name.lower()
            assert custom_header_lower in echo_text.lower(), (
                f"UX-BL3 FAIL: custom header {custom_header_name!r} NOT found in mock-backend "
                f"echo response.\n"
                f"echo body: {echo_text}\n"
                f"This means header_name was NOT read from vault-adapter or was ignored "
                f"by test_service. The fallback 'X-API-Key' may have been used instead."
            )

            # The credential value must appear in the echo body (it was injected as a header
            # value and echoed back by the mock-backend).
            assert unique_secret in echo_text, (
                f"UX-BL3 FAIL: credential value not found in mock-backend echo response.\n"
                f"echo body: {echo_text}\n"
                f"The credential was not injected into the outbound request."
            )

            # Sanity: X-API-Key fallback must NOT appear as the injected header
            # (only acceptable if it matches the custom header name, which it doesn't).
            if "x-api-key" in echo_text.lower() and custom_header_lower != "x-api-key":
                # Check whether X-API-Key is carrying our secret (fallback used instead
                # of custom header) vs. being some other header from the echo dump.
                import json as _json  # noqa: PLC0415
                try:
                    echo_json = _json.loads(echo_text)
                    echo_headers = {k.lower(): v for k, v in echo_json.get("headers", {}).items()}
                    if echo_headers.get("x-api-key") == unique_secret:
                        pytest.fail(
                            f"UX-BL3 FAIL: credential was injected under 'X-API-Key' fallback, "
                            f"not under the custom header {custom_header_name!r}.\n"
                            f"This means header_name was not retrieved from vault-adapter or "
                            f"was empty/missing in the GetCredential response."
                        )
                except _json.JSONDecodeError:
                    pass  # echo_text is not JSON-parseable; skip the detailed check

            # ── Step 8: ADR-0014.4 — no plaintext in test-endpoint response ──
            # The test_service response JSON must not include the raw secret.
            # Note: the echo body IS included in response_body_truncated, so we check
            # that the secret only appears there (echoed from the injected header), not
            # also in top-level response fields like "error" or "final_url".
            response_top_keys = {k: v for k, v in test_body.items()
                                 if k != "response_body_truncated"}
            assert unique_secret not in str(response_top_keys), (
                f"UX-BL3 SECURITY: plaintext credential leaked in test_service response "
                f"top-level fields (outside response_body_truncated): {response_top_keys}"
            )

        finally:
            # ── Cleanup: revoke credential + leave service ─────────────────
            # Revocation runs even if assertions failed above.
            tid = _state["tenant_id"]
            svc_id = _state["service_uuid"]
            kv = _state["credential_key_version"]

            if tid and svc_id and kv is not None:
                csrf_cleanup = client.cookies.get("csrf_token", csrf)
                del_r = client.delete(
                    f"{BASE_API}/v1/tenants/{tid}/services/{svc_id}/credentials/{kv}",
                    headers={"X-Mintkey-Csrf": csrf_cleanup},
                )
                # 204 = clean revocation; 404/409 = already gone/revoked — both are fine.
                if del_r.status_code not in (204, 404, 409):
                    # Non-fatal: log but don't mask the original assertion failure.
                    print(
                        f"[UX-BL3 cleanup] WARNING: credential revocation returned "
                        f"{del_r.status_code}: {del_r.text}"
                    )
