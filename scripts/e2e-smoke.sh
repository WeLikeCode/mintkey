#!/usr/bin/env bash
# Mintkey end-to-end smoke test — thin shell wrapper that runs the Python test.
# Usage: ./scripts/e2e-smoke.sh [--no-twilio]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "${SCRIPT_DIR}/e2e_smoke.py" "$@"
