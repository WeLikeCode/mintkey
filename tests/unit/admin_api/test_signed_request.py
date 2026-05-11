"""
Unit tests: AdminUiSignedRequest middleware (Ed25519 JWT validation).

Sources:
  - design §4; Req SEC-5; ADR-0014.6; ADR-0016.1
  - admin_api/auth/signed_request.py
"""
from __future__ import annotations

import base64
import json
import sys
import os
import time
import uuid

import pytest
from httpx import ASGITransport, AsyncClient

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../../.."))
ADMIN_API_SRC = os.path.join(REPO_ROOT, "admin-api", "src")
if ADMIN_API_SRC not in sys.path:
    sys.path.insert(0, ADMIN_API_SRC)

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey


def make_jwt(private_key: Ed25519PrivateKey, payload: dict) -> str:
    """Build a minimal Ed25519 JWT."""
    header = base64.urlsafe_b64encode(
        json.dumps({"alg": "EdDSA", "typ": "JWT"}).encode()
    ).rstrip(b"=").decode()
    body = base64.urlsafe_b64encode(
        json.dumps(payload).encode()
    ).rstrip(b"=").decode()
    signing_input = f"{header}.{body}".encode()
    sig = private_key.sign(signing_input)
    sig_b64 = base64.urlsafe_b64encode(sig).rstrip(b"=").decode()
    return f"{header}.{body}.{sig_b64}"


def make_test_app(private_key: Ed25519PrivateKey | None = None, public_key=None, jti_store=None):
    from fastapi import FastAPI
    from admin_api.auth.signed_request import AdminUiSignedRequestMiddleware, InMemoryJtiStore

    test_app = FastAPI()

    @test_app.post("/test-endpoint")
    async def test_post():
        return {"status": "ok"}

    @test_app.get("/v1/health")
    async def health():
        return {"status": "ok"}

    # Use provided public_key; if private_key given, derive public key from it
    if public_key is None and private_key is not None:
        public_key = private_key.public_key()

    store = jti_store if jti_store is not None else InMemoryJtiStore()
    test_app.add_middleware(AdminUiSignedRequestMiddleware, public_key=public_key, jti_store=store)
    return test_app


@pytest.mark.asyncio
async def test_get_bypasses_signed_request_check() -> None:
    """
    GET requests (SAFE_METHODS) skip signed-request validation entirely.
    Source: AdminUiSignedRequestMiddleware — SAFE_METHODS bypass.
    """
    private_key = Ed25519PrivateKey.generate()
    app = make_test_app(private_key=private_key)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/v1/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_post_without_header_returns_401() -> None:
    """
    POST without X-Mintkey-Signed-Request header returns 401.
    Source: AdminUiSignedRequestMiddleware — missing header guard.
    """
    private_key = Ed25519PrivateKey.generate()
    app = make_test_app(private_key=private_key)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post("/test-endpoint")

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_post_with_valid_jwt_passes() -> None:
    """
    POST with a valid Ed25519-signed JWT passes through to the handler.
    Source: AdminUiSignedRequestMiddleware — verify_signed_request OK path.
    """
    private_key = Ed25519PrivateKey.generate()
    now = int(time.time())
    payload = {"iat": now, "exp": now + 30, "jti": str(uuid.uuid4())}
    token = make_jwt(private_key, payload)

    app = make_test_app(private_key=private_key)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/test-endpoint",
            headers={"x-mintkey-signed-request": token},
        )

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_post_with_bad_signature_returns_401() -> None:
    """
    POST signed with a different key returns 401.
    Source: AdminUiSignedRequestMiddleware — verify_signed_request bad_signature.
    """
    signing_key = Ed25519PrivateKey.generate()
    verifying_key = Ed25519PrivateKey.generate()  # different key for middleware

    now = int(time.time())
    payload = {"iat": now, "exp": now + 30, "jti": str(uuid.uuid4())}
    token = make_jwt(signing_key, payload)  # signed with signing_key

    app = make_test_app(private_key=verifying_key)  # but middleware has verifying_key's pubkey
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/test-endpoint",
            headers={"x-mintkey-signed-request": token},
        )

    assert response.status_code == 401
    assert "bad_signature" in response.text


@pytest.mark.asyncio
async def test_post_with_expired_jwt_returns_401() -> None:
    """
    POST with iat=0, exp=1 (expired) returns 401.
    Source: AdminUiSignedRequestMiddleware — verify_signed_request expired.
    """
    private_key = Ed25519PrivateKey.generate()
    payload = {"iat": 0, "exp": 1, "jti": str(uuid.uuid4())}
    token = make_jwt(private_key, payload)

    app = make_test_app(private_key=private_key)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/test-endpoint",
            headers={"x-mintkey-signed-request": token},
        )

    assert response.status_code == 401
    assert "expired" in response.text


@pytest.mark.asyncio
async def test_post_with_ttl_over_60s_returns_401() -> None:
    """
    POST with exp - iat > 60 returns 401.
    Source: AdminUiSignedRequestMiddleware — verify_signed_request ttl_too_long.
    """
    private_key = Ed25519PrivateKey.generate()
    now = int(time.time())
    payload = {"iat": now, "exp": now + 120, "jti": str(uuid.uuid4())}  # 120s TTL
    token = make_jwt(private_key, payload)

    app = make_test_app(private_key=private_key)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/test-endpoint",
            headers={"x-mintkey-signed-request": token},
        )

    assert response.status_code == 401
    assert "ttl_too_long" in response.text


@pytest.mark.asyncio
async def test_replay_detected() -> None:
    """
    Same jti sent twice — second attempt returns 401 with mintkey:code=replay_detected.
    Source: AdminUiSignedRequestMiddleware — JtiStore.insert conflict.
    """
    from admin_api.auth.signed_request import InMemoryJtiStore

    private_key = Ed25519PrivateKey.generate()
    now = int(time.time())
    jti = str(uuid.uuid4())
    payload = {"iat": now, "exp": now + 30, "jti": jti}
    token = make_jwt(private_key, payload)

    # Share the same jti_store across both requests so replays are detected
    shared_store = InMemoryJtiStore()
    app = make_test_app(private_key=private_key, jti_store=shared_store)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first = await client.post(
            "/test-endpoint",
            headers={"x-mintkey-signed-request": token},
        )
        second = await client.post(
            "/test-endpoint",
            headers={"x-mintkey-signed-request": token},
        )

    assert first.status_code == 200
    assert second.status_code == 401
    assert "replay_detected" in second.text
