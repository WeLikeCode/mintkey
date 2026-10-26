"""C-9e5600b1: the verify-job chain test sets itself up with the canonical model.

Task 2.1 of audit-chain-verifiable requires
``tests/unit/audit_verify/test_chain_verify.py`` to put
``packages/python/mintkey-models`` on ``sys.path`` itself and to build its
``AuditEvent`` objects with ``at=datetime(2026, 1, 1, tzinfo=timezone.utc)``,
leaving the test bodies as they are.  The rewritten ``verify.py`` refuses an
event whose ``at`` is ``None``, so the file's own set-up is observable: it can
only import ``verify`` when it adds the model path, and ``_build_chain`` can
only return an event when it passes ``at``.

The check runs the file in a fresh interpreter with every ``mintkey-models``
entry removed from ``sys.path``, so the shared ``tests/conftest.py`` cannot
hide a missing entry in the file itself.

Source: specs/audit-chain/spec.md — task 2.1; proposal.md (F-0b7e7198, Q-005).
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
TARGET = REPO_ROOT / "tests" / "unit" / "audit_verify" / "test_chain_verify.py"
EXPECTED_AT = "2026-01-01T00:00:00+00:00"

_PROBE = r"""
import importlib.util
import json
import sys

path = sys.argv[1]
sys.dont_write_bytecode = True
sys.path = [
    entry
    for entry in sys.path
    if not entry.replace("\\", "/").rstrip("/").endswith("packages/python/mintkey-models")
]
spec = importlib.util.spec_from_file_location("_chain_verify_setup_probe", path)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
events = module._build_chain(1)
event = events[0]
has_path = any(
    entry.replace("\\", "/").rstrip("/").endswith("packages/python/mintkey-models")
    for entry in sys.path
)
print(json.dumps({
    "at": event.at.isoformat() if event.at is not None else None,
    "has_path": has_path,
}))
"""


def test_C_9e5600b1_chain_verify_setup_adds_model_path_and_builds_events_with_at() -> None:
    assert TARGET.is_file()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, str(TARGET)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    payload = json.loads(result.stdout)
    assert payload["has_path"] is True
    assert payload["at"] == EXPECTED_AT
