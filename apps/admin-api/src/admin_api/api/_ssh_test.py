"""
SSH transient-test helper — OPS-T / ADR-0021.

Extracted into its own module so unit tests can import it without pulling in the
full services.py module (which requires mintkey_models at import time).

Called from services.py::test_service_transient when auth_scheme ∈ {ssh_private_key, ssh_password}.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SSH_SCHEMES = {"ssh_private_key", "ssh_password"}


async def test_ssh_credential(
    scheme: str,
    credential_value: str,
    base_url: str,
    timeout_ms: int = 10000,
) -> dict[str, Any]:
    """
    Dial an SSH server using the inline transient credential and report success/failure.

    This is the back-end for test-transient when auth_scheme is 'ssh_private_key'
    or 'ssh_password'.  It intentionally does NOT check host keys (known_hosts=None)
    because this is a credential-validation step, not a trust-anchoring step.

    NOTE on known_hosts=None:
        At transient-test time the operator is verifying that their credential works
        against the declared target.  Host-key pinning (TOFU) is a separate concern
        handled by the SSH proxy at runtime.  Passing known_hosts=None here suppresses
        asyncssh's host-key check for this one call only and is the correct default for
        a "does my key/password authenticate?" check that the user is performing BEFORE
        the service is saved.  The production SSH proxy (ssh-proxy service) performs
        TOFU host-key pinning independently.  Reference: ADR-0021.

    Security invariants:
        - Private key PEM and password NEVER appear in response body, logs, or audit.
        - Only host:port and username (and a SHA-256[:16] key fingerprint) are logged.
        - asyncssh.import_private_key() loads the key from bytes in memory — no temp file.

    Returns a dict matching the HTTP test result shape so the UI renders it unchanged:
        {ok, status_code, latency_ms, final_url, response_body_truncated, error?}
    """
    import asyncssh  # noqa: PLC0415  — lazy to keep startup fast
    import time as _time  # noqa: PLC0415

    start = _time.monotonic()

    # ------------------------------------------------------------------ parse
    try:
        cred = json.loads(credential_value)
    except (json.JSONDecodeError, ValueError) as exc:
        return {
            "ok": False,
            "status_code": 400,
            "latency_ms": 0,
            "final_url": base_url,
            "response_body_truncated": f"Invalid credential JSON: {exc}",
        }

    # ---------------------------------------------------------------- resolve target
    # Prefer target_address from the inline credential; fall back to base_url.
    raw_target: str = cred.get("target_address", "")
    if not raw_target:
        parsed = urlparse(base_url)
        host = parsed.hostname or ""
        port = parsed.port or 22
        raw_target = f"{host}:{port}"

    target_parts = raw_target.rsplit(":", 1)
    if len(target_parts) != 2 or not target_parts[1].isdigit():
        return {
            "ok": False,
            "status_code": 400,
            "latency_ms": int((_time.monotonic() - start) * 1000),
            "final_url": base_url,
            "response_body_truncated": (
                f"Cannot resolve SSH target — expected 'host:port', got: {raw_target!r}"
            ),
        }

    host = target_parts[0]
    port = int(target_parts[1])
    final_url = f"ssh://{host}:{port}"

    # ---------------------------------------------------------------- build connect kwargs
    connect_kwargs: dict[str, Any] = {
        "host": host,
        "port": port,
        # NOTE: known_hosts=None disables host-key verification for this transient test.
        # The SSH proxy pins host keys via TOFU at runtime (ADR-0021).
        "known_hosts": None,
    }

    username: str = ""

    if scheme == "ssh_private_key":
        pem_str: str = cred.get("private_key_pem", "")
        username = cred.get("ssh_user", "") or cred.get("username", "")
        if not pem_str or not username:
            return {
                "ok": False,
                "status_code": 400,
                "latency_ms": int((_time.monotonic() - start) * 1000),
                "final_url": final_url,
                "response_body_truncated": (
                    "ssh_private_key credential requires 'private_key_pem' and 'ssh_user'"
                ),
            }
        try:
            client_key = asyncssh.import_private_key(pem_str.encode())
        except (asyncssh.KeyImportError, ValueError) as exc:
            return {
                "ok": False,
                "status_code": 400,
                "latency_ms": int((_time.monotonic() - start) * 1000),
                "final_url": final_url,
                "response_body_truncated": f"Cannot import private key: {exc}",
            }
        connect_kwargs["username"] = username
        connect_kwargs["client_keys"] = [client_key]
        # Log only a key fingerprint — never the PEM material (S-SEC-1, ADR-0014.4).
        _key_hint = hashlib.sha256(pem_str.encode()).hexdigest()[:16]
        logger.debug(
            "test_ssh_credential: scheme=ssh_private_key host=%s:%d user=%s key_fp=%s",
            host, port, username, _key_hint,
        )

    else:  # ssh_password
        username = cred.get("username", "") or cred.get("ssh_user", "")
        password: str = cred.get("password", "")
        if not username or not password:
            return {
                "ok": False,
                "status_code": 400,
                "latency_ms": int((_time.monotonic() - start) * 1000),
                "final_url": final_url,
                "response_body_truncated": (
                    "ssh_password credential requires 'username' and 'password'"
                ),
            }
        connect_kwargs["username"] = username
        connect_kwargs["password"] = password
        # Log only host:port and username — never the password (S-SEC-1, ADR-0014.4).
        logger.debug(
            "test_ssh_credential: scheme=ssh_password host=%s:%d user=%s",
            host, port, username,
        )

    # Divide the total budget: connect gets 60 %, session gets remaining 40 %.
    total_s = timeout_ms / 1000.0
    connect_timeout_s = max(1.0, total_s * 0.6)
    session_timeout_s = max(1.0, total_s * 0.4)
    connect_kwargs["login_timeout"] = connect_timeout_s

    # ---------------------------------------------------------------- dial + run
    try:
        async with asyncssh.connect(**connect_kwargs) as conn:
            # Grab the server banner for the success message (may be None).
            banner: str = (getattr(conn, "get_banner", None) or (lambda: ""))() or ""
            banner_line = banner.splitlines()[0].strip() if banner else ""

            # Run a trivial no-op command to verify a session can open.
            await asyncio.wait_for(
                conn.run("true", check=False),
                timeout=session_timeout_s,
            )

        latency_ms = int((_time.monotonic() - start) * 1000)
        body = f"SSH connection succeeded as {username}@{host}:{port}"
        if banner_line:
            body += f" (banner: {banner_line})"
        return {
            "ok": True,
            "status_code": 200,
            "latency_ms": latency_ms,
            "final_url": final_url,
            "response_body_truncated": body,
        }

    except asyncssh.PermissionDenied as exc:
        latency_ms = int((_time.monotonic() - start) * 1000)
        logger.info(
            "test_ssh_credential: auth failed host=%s:%d user=%s reason=%s",
            host, port, username, exc,
        )
        return {
            "ok": False,
            "status_code": 401,
            "latency_ms": latency_ms,
            "final_url": final_url,
            "response_body_truncated": f"SSH authentication failed: {exc}",
        }

    except (TimeoutError, asyncio.TimeoutError) as exc:
        latency_ms = int((_time.monotonic() - start) * 1000)
        logger.info(
            "test_ssh_credential: timeout host=%s:%d user=%s after=%dms",
            host, port, username, latency_ms,
        )
        return {
            "ok": False,
            "status_code": 504,
            "latency_ms": latency_ms,
            "final_url": final_url,
            "response_body_truncated": f"SSH test timed out after {latency_ms}ms",
        }

    except (ConnectionRefusedError, OSError) as exc:
        latency_ms = int((_time.monotonic() - start) * 1000)
        logger.info(
            "test_ssh_credential: connect failed host=%s:%d user=%s error=%s",
            host, port, username, exc,
        )
        return {
            "ok": False,
            "status_code": 502,
            "latency_ms": latency_ms,
            "final_url": final_url,
            "response_body_truncated": f"SSH connect failed: {exc}",
        }

    except Exception as exc:  # noqa: BLE001
        latency_ms = int((_time.monotonic() - start) * 1000)
        logger.warning(
            "test_ssh_credential: unexpected error host=%s:%d user=%s error_type=%s",
            host, port, username, type(exc).__name__,
        )
        return {
            "ok": False,
            "status_code": 502,
            "latency_ms": latency_ms,
            "final_url": final_url,
            "response_body_truncated": f"SSH test error: {type(exc).__name__}: {exc}",
        }
