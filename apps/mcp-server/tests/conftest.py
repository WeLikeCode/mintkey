"""
Pytest configuration for mcp-server tests.

Adds the mcp-server/src path to sys.path so mcp_server is importable without
installing the package (matches the pattern in tests/conftest.py for admin-api).
"""
from __future__ import annotations

import sys
from pathlib import Path

_MCP_SRC = Path(__file__).resolve().parent.parent / "src"
_src_str = str(_MCP_SRC)
if _src_str not in sys.path:
    sys.path.insert(0, _src_str)

# Also add mintkey-models to path since mcp_server imports from it.
# Post-monorepo-restructure (2026-05-22): this conftest sits at
# apps/mcp-server/tests/conftest.py, so parents[3] is the repo root
# (was parents[2] when the file lived at mcp-server/tests/conftest.py).
_REPO_ROOT = Path(__file__).resolve().parents[3]  # mintkey/
for _extra in (
    _REPO_ROOT / "packages" / "python" / "mintkey-models",
    _REPO_ROOT / "apps" / "admin-api" / "src",
):
    s = str(_extra)
    if s not in sys.path:
        sys.path.insert(0, s)
