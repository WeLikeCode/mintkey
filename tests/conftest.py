"""
Shared pytest configuration.

Detects the Docker socket path (Docker Desktop on macOS uses a non-standard
location) and sets DOCKER_HOST so testcontainers finds it automatically.

Also ensures the local source trees are importable without installation:
  - admin-api/src   (admin_api package)
  - mintkey-models  (mintkey_models package)

Sets MINTKEY_AUDIT_HMAC_KEY to a deterministic dev-only placeholder if the
variable is not already present in the environment.  This prevents the
RuntimeError that audit_fingerprint raises at import time when running tests
without a full .env loaded.  Production containers supply the real key via
.env / docker-compose (see infra/compose/docker-compose.yml and .env.example).
"""
import os
import sys
from pathlib import Path

# 64-char hex = 32 bytes = minimum accepted by audit_fingerprint._load_hmac_key.
# All-zeros is a test-only placeholder — NOT a production secret.
os.environ.setdefault("MINTKEY_AUDIT_HMAC_KEY", "0" * 64)

_REPO_ROOT = Path(__file__).parent.parent
for _src in (
    _REPO_ROOT / "apps/admin-api" / "src",
    _REPO_ROOT / "packages/python/mintkey-models",
):
    _src_str = str(_src)
    if _src_str not in sys.path:
        sys.path.insert(0, _src_str)

_SOCKET_CANDIDATES = [
    "/var/run/docker.sock",
    Path.home() / ".docker" / "run" / "docker.sock",
    Path.home() / ".colima" / "default" / "docker.sock",
]


def _find_docker_socket():
    for candidate in _SOCKET_CANDIDATES:
        if Path(candidate).exists():
            return f"unix://{candidate}"
    return None


# Set before any testcontainers import resolves the Docker client.
if not os.environ.get("DOCKER_HOST"):
    sock = _find_docker_socket()
    if sock:
        os.environ["DOCKER_HOST"] = sock
