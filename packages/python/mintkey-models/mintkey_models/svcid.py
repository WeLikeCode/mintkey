"""
Service identity client — reads service token from a file.

Re-reads on every token() call to support rotation without restart.
Raises FileNotFoundError at construction time if the token file is absent.

Source: design §1; ADR-0014.6 (service identity tokens);
        ADR-0017.1 (X-Mintkey-Service-Token header).
"""
from __future__ import annotations

from pathlib import Path


class ServiceIdentityClient:
    """
    Reads a Mintkey service identity token from a file on disk.

    The file is checked for existence at construction time. token() re-reads
    the file on every call so that token rotation (writing a new file) takes
    effect without a service restart — ADR-0014.6.
    """

    def __init__(self, token_path: str = "/run/secrets/mintkey_service_token") -> None:
        self._path = Path(token_path)
        # Fail fast at construction time if the file is missing.
        if not self._path.exists():
            raise FileNotFoundError(
                f"Service identity token file not found: {token_path}"
            )

    def token(self) -> str:
        """Read and return the current token from file (re-reads for rotation)."""
        return self._path.read_text().strip()

    def http_header(self) -> dict[str, str]:
        """Return the X-Mintkey-Service-Token header — ADR-0017.1."""
        return {"X-Mintkey-Service-Token": self.token()}
