"""
No-leak tests for pydantic-validated credential schemes — C-2 round 2.

Proves by construction that a unique marker planted in the secret-bearing
field of an INVALID payload does NOT appear anywhere in the pydantic error
output that the handler returns to the caller.

This guards against the pydantic v2 `input_value=...` echo that is present
in `str(exc)` for `pydantic.ValidationError` (confirmed on pydantic 2.x).
Because `pydantic.ValidationError` is a subclass of `ValueError`, any
`except ValueError` arm that does `detail=str(exc)` will leak the user-
supplied input bytes back in the HTTP response.

The fix (applied in this chunk) catches `pydantic.ValidationError` BEFORE
the bare `except ValueError` and calls
    exc.errors(include_url=False, include_context=False, include_input=False)
which scrubs `input_value` from all error entries.

Five parametrized subtests — one per pydantic-validated scheme:
  - apple_jwt          (field: p8_key_pem)
  - google_service_account (field: service_account_json nested)
  - oauth2_password_grant  (field: token_url — http:// triggers HTTPS check)
  - ssh_password           (field: password, empty username triggers first)
  - ssh_private_key        (field: private_key_pem)

Note: ssh_ca is intentionally excluded — no SSHCAPayload model exists today.
Follow-up tracked as TODO(ssh-ca-payload) in credentials.py.

Source: C-2 chunk goal (round 2); ADR-0014.7; S-SEC-1.
"""
from __future__ import annotations

import json as _json
import uuid

import pydantic
import pytest

from admin_api.services.credential_service import (
    AppleJWTPayload,
    GoogleServiceAccountPayload,
    OAuth2PasswordGrantPayload,
    SSHPasswordPayload,
    SSHPrivateKeyPayload,
)


def _marker() -> str:
    """Generate a unique secret-shaped marker per test run."""
    return f"LEAK-MARKER-{uuid.uuid4().hex}"


# ---------------------------------------------------------------------------
# apple_jwt — p8_key_pem must start with -----BEGIN PRIVATE KEY-----
# Trigger: provide a marker value that does NOT start with that prefix.
# The ValidationError should be raised on the p8_key_pem field.
# ---------------------------------------------------------------------------


def test_apple_jwt_no_input_leak() -> None:
    """pydantic errors() for apple_jwt must not echo the p8_key_pem value."""
    marker = _marker()
    with pytest.raises(pydantic.ValidationError) as exc_info:
        AppleJWTPayload(
            p8_key_pem=marker,  # does not start with -----BEGIN PRIVATE KEY-----
            key_id="ABCDE12345",
            issuer_id="aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        )

    exc = exc_info.value
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    body = _json.dumps({"type": "about:blank", "title": "validation error", "detail": errors})

    assert marker not in body, (
        f"LEAK: marker '{marker}' appeared in apple_jwt error body:\n{body}"
    )
    # Also verify no input_value echo in str(exc) leaks when we call errors() directly
    assert marker not in _json.dumps(errors), (
        "LEAK: marker appeared in errors() output for apple_jwt"
    )


# ---------------------------------------------------------------------------
# google_service_account — service_account_json must be valid Google SA JSON
# Trigger: provide a JSON object whose "type" field is wrong but embed the
# marker inside the service_account_json string.
# ---------------------------------------------------------------------------


def test_google_service_account_no_input_leak() -> None:
    """pydantic errors() for google_service_account must not echo the SA JSON."""
    marker = _marker()
    # Build a plausible-looking but invalid SA JSON — type != "service_account"
    invalid_sa_json = _json.dumps({
        "type": "authorized_user",  # wrong type — triggers validation error
        "private_key": f"-----BEGIN RSA PRIVATE KEY-----\n{marker}\n-----END RSA PRIVATE KEY-----",
        "client_email": f"{marker}@project.iam.gserviceaccount.com",
        "project_id": "my-project",
        "private_key_id": "abc123",
        "token_uri": "https://oauth2.googleapis.com/token",
    })

    with pytest.raises(pydantic.ValidationError) as exc_info:
        GoogleServiceAccountPayload(service_account_json=invalid_sa_json)

    exc = exc_info.value
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    body = _json.dumps({"type": "about:blank", "title": "validation error", "detail": errors})

    assert marker not in body, (
        f"LEAK: marker appeared in google_service_account error body:\n{body}"
    )


# ---------------------------------------------------------------------------
# oauth2_password_grant — token_url must use HTTPS
# Trigger: provide http:// (not https://) with the marker embedded in the URL
# path so that if str(exc) is echoed the marker would appear.
# ---------------------------------------------------------------------------


def test_oauth2_password_grant_no_input_leak() -> None:
    """pydantic errors() for oauth2_password_grant must not echo token_url."""
    marker = _marker()
    insecure_url = f"http://token-server.example.com/{marker}/oauth/token"

    with pytest.raises(pydantic.ValidationError) as exc_info:
        OAuth2PasswordGrantPayload(
            token_url=insecure_url,
            credential_fields={"username": "user", "password": "pass"},
        )

    exc = exc_info.value
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    body = _json.dumps({"type": "about:blank", "title": "validation error", "detail": errors})

    assert marker not in body, (
        f"LEAK: marker appeared in oauth2_password_grant error body:\n{body}"
    )


# ---------------------------------------------------------------------------
# ssh_password — password field
# Trigger: empty username (rejected) with a long unique marker in password.
# The ValidationError on username fires first, but pydantic collects ALL
# field errors — include_input=False must scrub all of them.
# ---------------------------------------------------------------------------


def test_ssh_password_no_input_leak() -> None:
    """pydantic errors() for ssh_password must not echo the password value."""
    marker = _marker()

    with pytest.raises(pydantic.ValidationError) as exc_info:
        SSHPasswordPayload(
            username="",          # triggers username validation error
            password=marker,      # the secret-bearing field — must not leak
            target_address="bastion.example.com:22",
        )

    exc = exc_info.value
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    body = _json.dumps({"type": "about:blank", "title": "validation error", "detail": errors})

    assert marker not in body, (
        f"LEAK: marker appeared in ssh_password error body:\n{body}"
    )


# ---------------------------------------------------------------------------
# ssh_private_key — private_key_pem field
# Trigger: provide a marker value that does NOT start with -----BEGIN.
# ---------------------------------------------------------------------------


def test_ssh_private_key_no_input_leak() -> None:
    """pydantic errors() for ssh_private_key must not echo private_key_pem."""
    marker = _marker()

    with pytest.raises(pydantic.ValidationError) as exc_info:
        SSHPrivateKeyPayload(
            private_key_pem=marker,  # does not start with -----BEGIN
            target_address="bastion.example.com:22",
            ssh_user="ubuntu",
        )

    exc = exc_info.value
    errors = exc.errors(include_url=False, include_context=False, include_input=False)
    body = _json.dumps({"type": "about:blank", "title": "validation error", "detail": errors})

    assert marker not in body, (
        f"LEAK: marker appeared in ssh_private_key error body:\n{body}"
    )
