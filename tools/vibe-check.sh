#!/usr/bin/env bash
# vibe-check.sh — pre-PR spec-reference scan
# Scans staged diff for code without spec back-references.
# Exit 0: clean. Exit 1: warnings (never blocks by default).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
WARNINGS=0

echo "=== Vibe Check ==="
echo

# Get staged files
staged=$(git -C "$REPO_ROOT" diff --cached --name-only 2>/dev/null || true)
if [[ -z "$staged" ]]; then
  echo "No staged files. Run after 'git add'."
  exit 0
fi

# Check each staged code file for a spec/ADR/contract back-reference
code_files=$(echo "$staged" | grep -E '\.(py|ts|tsx|js|jsx|go|java|cs|rs)$' || true)
if [[ -z "$code_files" ]]; then
  echo "✓ No code files staged."
  exit 0
fi

echo "Checking staged code files for spec back-references..."
while IFS= read -r f; do
  full="$REPO_ROOT/$f"
  [[ ! -f "$full" ]] && continue
  if ! grep -qiE "(spec:|adr:|contract:|adr-[0-9]+|spec/|contracts/)" "$full" 2>/dev/null; then
    echo "  ⚠ $f — no Spec:/ADR:/Contract: reference found"
    WARNINGS=$((WARNINGS+1))
  else
    echo "  ✓ $f"
  fi
done <<< "$code_files"

echo
if [[ $WARNINGS -gt 0 ]]; then
  echo "⚠ $WARNINGS file(s) lack spec back-references. Add a comment citing the ADR, spec, or contract."
  echo "  (This is a warning — not a block. Architect can promote to blocking.)"
  exit 1
else
  echo "✓ All staged code files have spec back-references."
  exit 0
fi
