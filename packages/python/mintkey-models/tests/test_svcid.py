"""
Tests for svcid.py — service identity client.

TDD: written before implementation per T-1.0.9 (session 2) test-first discipline.
Source: T-1.0.9; design §1; ADR-0014.6 (service identity tokens);
        ADR-0017.1 (X-Mintkey-Service-Token header).

Requirements verified:
- Token is read from file (not env var) for per-rotation support.
- Token re-read on every call to support rotation without restart.
- Missing file raises FileNotFoundError at construction time.
- http_header() returns the correct header dict.
"""
from __future__ import annotations

import pathlib
import tempfile


class TestClientReadsToken:
    """token() returns the content of the token file."""

    def test_client_reads_token(self, tmp_path) -> None:
        from mintkey_models.svcid import ServiceIdentityClient

        token_file = tmp_path / "mintkey_service_token"
        token_file.write_text("my-secret-token-abc123")

        client = ServiceIdentityClient(token_path=str(token_file))
        assert client.token() == "my-secret-token-abc123"


class TestClientRotates:
    """token() re-reads file on every call to support rotation — ADR-0014.6."""

    def test_client_rotates(self, tmp_path) -> None:
        from mintkey_models.svcid import ServiceIdentityClient

        token_file = tmp_path / "mintkey_service_token"
        token_file.write_text("token-A")

        client = ServiceIdentityClient(token_path=str(token_file))
        assert client.token() == "token-A"

        # Simulate rotation: overwrite the file
        token_file.write_text("token-B")
        assert client.token() == "token-B", (
            "token() must re-read the file each call to support rotation"
        )


class TestClientMissingFile:
    """ServiceIdentityClient raises FileNotFoundError if token file is absent."""

    def test_client_missing_file(self) -> None:
        from mintkey_models.svcid import ServiceIdentityClient

        try:
            ServiceIdentityClient(token_path="/nonexistent/path/mintkey_token")
            assert False, "Expected FileNotFoundError not raised"
        except FileNotFoundError:
            pass  # correct


class TestHttpHeader:
    """http_header() returns {"X-Mintkey-Service-Token": <token>} — ADR-0017.1."""

    def test_http_header(self, tmp_path) -> None:
        from mintkey_models.svcid import ServiceIdentityClient

        token_file = tmp_path / "mintkey_service_token"
        token_file.write_text("bearer-xyz-987")

        client = ServiceIdentityClient(token_path=str(token_file))
        header = client.http_header()

        assert header == {"X-Mintkey-Service-Token": "bearer-xyz-987"}, (
            f"Unexpected header dict: {header}"
        )
