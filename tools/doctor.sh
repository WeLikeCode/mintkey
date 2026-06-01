#!/usr/bin/env bash
# doctor.sh — local environment health check
# Exit 0: clean. Exit 1: warnings. Exit 2: errors.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0
WARNINGS=0

pass() { echo "  ✓ $1"; }
warn() { echo "  ⚠ $1"; WARNINGS=$((WARNINGS+1)); }
fail() { echo "  ✗ $1"; ERRORS=$((ERRORS+1)); }

echo "=== Kiro Project Template — Doctor ==="
echo

# 1. Setup state
echo "[1/5] Setup state"
STATE="$REPO_ROOT/.kiro/setup-state.json"
if [[ ! -f "$STATE" ]]; then
  fail "Project not bootstrapped — .kiro/setup-state.json missing. Run the project-setup skill in Kiro."
elif ! python3 -c "import json,sys; d=json.load(open('$STATE')); sys.exit(0 if d.get('completed') else 1)" 2>/dev/null; then
  warn "Setup incomplete — .kiro/setup-state.json exists but completed != true. Re-invoke project-setup."
else
  pass ".kiro/setup-state.json present and completed"
fi

# 2. Mandatory steering files
echo
echo "[2/5] Mandatory steering files"
for f in product.md structure.md architecture-principles.md; do
  if [[ -f "$REPO_ROOT/.kiro/steering/$f" ]]; then
    pass ".kiro/steering/$f"
  else
    fail ".kiro/steering/$f missing — run project-setup skill"
  fi
done

# 3. docs/architecture/ structure
echo
echo "[3/5] Architecture directory"
for f in risk-register.md open-questions.md; do
  if [[ -f "$REPO_ROOT/docs/architecture/$f" ]]; then
    pass "docs/architecture/$f"
  else
    warn "docs/architecture/$f missing — expected after bootstrap"
  fi
done
if [[ -f "$REPO_ROOT/CODEOWNERS" ]]; then
  pass "CODEOWNERS present"
else
  warn "CODEOWNERS missing — architect should create it"
fi

# 4. Steering frontmatter check (default-load files must have no inclusion: line, or valid one)
# Only inspect the YAML frontmatter block (between the first pair of --- delimiters).
# Lines starting with `inclusion:` inside fenced code blocks in the body are not frontmatter.
echo
echo "[4/5] Steering frontmatter"
STEERING_DIR="$REPO_ROOT/.kiro/steering"
for f in "$STEERING_DIR"/*.md; do
  name="$(basename "$f")"
  # Extract only the frontmatter block: lines between the first --- and the closing ---
  # If no frontmatter block exists, frontmatter is empty.
  frontmatter=$(awk '/^---$/{if(fm==0){fm=1;next}else{exit}} fm{print}' "$f" 2>/dev/null)
  if echo "$frontmatter" | grep -q "^inclusion:"; then
    mode=$(echo "$frontmatter" | grep "^inclusion:" | awk '{print $2}')
    if [[ "$mode" != "fileMatch" && "$mode" != "manual" ]]; then
      fail "$name: unknown inclusion mode '$mode' (valid: fileMatch, manual, or omit for default)"
    else
      pass "$name: inclusion=$mode"
    fi
  else
    pass "$name: default-load"
  fi
done

# 5. Kiro CLI present
echo
echo "[5/5] Tooling"
if command -v kiro &>/dev/null; then
  pass "kiro CLI found: $(kiro --version 2>/dev/null || echo 'version unknown')"
else
  warn "kiro CLI not found — install from https://kiro.dev"
fi
if command -v git &>/dev/null; then
  pass "git found: $(git --version)"
else
  fail "git not found"
fi

# 6. Mintkey stack consistency (live-stack checks — skipped gracefully if Docker is absent)
echo
echo "[6/6] Mintkey stack"
MINTKEY_DOCTOR="$REPO_ROOT/scripts/mintkey-doctor.sh"
if [[ -f "$MINTKEY_DOCTOR" ]]; then
  bash "$MINTKEY_DOCTOR" || true  # errors/warnings already printed; we tally below via its exit
  STACK_EXIT=$?
  if [[ $STACK_EXIT -ne 0 ]]; then
    ERRORS=$((ERRORS+1))
  fi
else
  warn "scripts/mintkey-doctor.sh not found — skipping stack checks"
fi

# Summary
echo
if [[ $ERRORS -gt 0 ]]; then
  echo "✗ $ERRORS error(s), $WARNINGS warning(s). Fix errors before proceeding."
  exit 2
elif [[ $WARNINGS -gt 0 ]]; then
  echo "⚠ $WARNINGS warning(s). Review above."
  exit 1
else
  echo "✓ All checks passed."
  exit 0
fi
