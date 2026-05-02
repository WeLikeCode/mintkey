#!/usr/bin/env bash
# contract-lint.sh — lint OpenAPI / AsyncAPI / JSON Schema contracts
# Exit 0: clean. Exit 2: lint errors (CI-blocking).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0

echo "=== Contract Lint ==="
echo

# OpenAPI — spectral
openapi_files=$(find "$REPO_ROOT/contracts/openapi" -name "*.yaml" -o -name "*.yml" 2>/dev/null | grep -v .gitkeep || true)
if [[ -n "$openapi_files" ]]; then
  if command -v spectral &>/dev/null; then
    echo "[OpenAPI] Running spectral..."
    while IFS= read -r f; do
      spectral lint "$f" && echo "  ✓ $f" || { echo "  ✗ $f"; ERRORS=$((ERRORS+1)); }
    done <<< "$openapi_files"
  else
    echo "[OpenAPI] spectral not installed — skipping (install: npm i -g @stoplight/spectral-cli)"
  fi
else
  echo "[OpenAPI] No contracts found — skipping"
fi

# AsyncAPI — asyncapi-cli
asyncapi_files=$(find "$REPO_ROOT/contracts/asyncapi" -name "*.yaml" -o -name "*.yml" 2>/dev/null | grep -v .gitkeep || true)
if [[ -n "$asyncapi_files" ]]; then
  if command -v asyncapi &>/dev/null; then
    echo "[AsyncAPI] Running asyncapi validate..."
    while IFS= read -r f; do
      asyncapi validate "$f" && echo "  ✓ $f" || { echo "  ✗ $f"; ERRORS=$((ERRORS+1)); }
    done <<< "$asyncapi_files"
  else
    echo "[AsyncAPI] asyncapi CLI not installed — skipping (install: npm i -g @asyncapi/cli)"
  fi
else
  echo "[AsyncAPI] No contracts found — skipping"
fi

# JSON Schema — ajv
schema_files=$(find "$REPO_ROOT/contracts/jsonschema" -name "*.json" 2>/dev/null | grep -v .gitkeep || true)
fixture_files=$(find "$REPO_ROOT/contracts/fixtures" -name "*.json" 2>/dev/null | grep -v .gitkeep || true)
if [[ -n "$schema_files" ]]; then
  if command -v ajv &>/dev/null; then
    echo "[JSON Schema] Running ajv..."
    while IFS= read -r s; do
      ajv compile -s "$s" && echo "  ✓ $s" || { echo "  ✗ $s"; ERRORS=$((ERRORS+1)); }
    done <<< "$schema_files"
  else
    echo "[JSON Schema] ajv not installed — skipping (install: npm i -g ajv-cli)"
  fi
else
  echo "[JSON Schema] No schemas found — skipping"
fi

echo
if [[ $ERRORS -gt 0 ]]; then
  echo "✗ $ERRORS lint error(s). Fix before merging."
  exit 2
else
  echo "✓ Contract lint clean."
  exit 0
fi
