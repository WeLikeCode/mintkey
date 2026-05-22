"""
Shared pytest configuration.

Detects the Docker socket path (Docker Desktop on macOS uses a non-standard
location) and sets DOCKER_HOST so testcontainers finds it automatically.

Also ensures the local source trees are importable without installation:
  - admin-api/src   (admin_api package)
  - mintkey-models  (mintkey_models package)
"""
import os
import sys
from pathlib import Path

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
