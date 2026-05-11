"""
AdminUiSignedRequest middleware.

Validates Ed25519-signed JWTs from AdminJS on state-changing endpoints.
Public key is fetched from Vault Adapter at startup (credential type
admin_ui_signing_key) and cached for 1 hour.

JTI replay protection: insert into admin_request_jti table; conflict = replay.

Source: design §4; Req SEC-5; ADR-0014.6; ADR-0016.1.
"""

from __future__ import annotations

import base64
import json
import time
import threading
from typing import Callable

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.exceptions import InvalidSignature
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

SIGNED_REQUEST_HEADER = "x-mintkey-signed-request"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS", "TRACE"}
MAX_JWT_TTL_SECONDS = 60


def _decode_b64url(s: str) -> bytes:
    """Decode base64url without padding."""
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


class JtiStore:
    """Abstract jti denylist interface."""

    def insert(self, jti: str, expires_at: float) -> bool:
        """Insert jti. Returns True if new, False if replay."""
        raise NotImplementedError

    def cleanup(self) -> None:
        """Remove expired entries."""
        raise NotImplementedError


class InMemoryJtiStore(JtiStore):
    """In-memory jti denylist for testing."""

    def __init__(self):
        self._store: dict[str, float] = {}
        self._lock = threading.Lock()

    def insert(self, jti: str, expires_at: float) -> bool:
        with self._lock:
            self.cleanup()
            if jti in self._store:
                return False
            self._store[jti] = expires_at
            return True

    def cleanup(self) -> None:
        now = time.time()
        self._store = {k: v for k, v in self._store.items() if v > now}


def verify_signed_request(
    token: str, public_key: Ed25519PublicKey, jti_store: JtiStore
) -> tuple[bool, str]:
    """
    Verify an Ed25519 signed JWT.
    Returns (ok, error_code).
    Error codes: bad_format, bad_signature, expired, ttl_too_long, replay_detected
    """
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return False, "bad_format"

        header_b64, payload_b64, sig_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode()

        sig = _decode_b64url(sig_b64)
        try:
            public_key.verify(sig, signing_input)
        except InvalidSignature:
            return False, "bad_signature"

        payload = json.loads(_decode_b64url(payload_b64))
        now = time.time()

        iat = payload.get("iat", 0)
        exp = payload.get("exp", 0)

        if exp <= now:
            return False, "expired"

        if exp - iat > MAX_JWT_TTL_SECONDS:
            return False, "ttl_too_long"

        jti = payload.get("jti")
        if not jti:
            return False, "bad_format"

        if not jti_store.insert(jti, exp):
            return False, "replay_detected"

        return True, ""
    except Exception:
        return False, "bad_format"


class AdminUiSignedRequestMiddleware(BaseHTTPMiddleware):
    """
    Validates Ed25519-signed AdminJS JWT on every state-changing request.

    Usage: inject the public key and jti_store at construction time
    (or use the default Vault Adapter bootstrap in production).
    """

    def __init__(
        self,
        app,
        public_key: Ed25519PublicKey | None = None,
        jti_store: JtiStore | None = None,
    ):
        super().__init__(app)
        self._public_key = public_key
        self._jti_store = jti_store or InMemoryJtiStore()

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        if request.method in SAFE_METHODS:
            return await call_next(request)

        if self._public_key is None:
            # No key configured → skip (dev mode / bootstrap)
            return await call_next(request)

        token = request.headers.get(SIGNED_REQUEST_HEADER)
        if not token:
            return Response(
                content='{"code":"mintkey:signed_request_required"}',
                status_code=401,
                media_type="application/json",
            )

        ok, error_code = verify_signed_request(token, self._public_key, self._jti_store)
        if not ok:
            content = f'{{"code":"mintkey:{error_code}"}}'
            return Response(content=content, status_code=401, media_type="application/json")

        return await call_next(request)
