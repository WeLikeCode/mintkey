#!/usr/bin/env bash
# deps.sh — Ensure required dependencies are installed.
# Installs missing tools non-destructively. Safe to re-run.
set -euo pipefail

INSTALLED=0
SKIPPED=0

info()  { echo "  → $1"; }
ok()    { echo "  ✓ $1"; SKIPPED=$((SKIPPED+1)); }
added() { echo "  + $1"; INSTALLED=$((INSTALLED+1)); }

echo "=== Dependency Check & Install ==="
echo

# --- Python 3 ---
echo "[python3]"
if command -v python3 &>/dev/null; then
  ok "python3 found: $(python3 --version 2>&1)"
else
  info "python3 not found — installing via Homebrew..."
  if command -v brew &>/dev/null; then
    brew install python3
    added "python3 installed via Homebrew"
  else
    echo "  ✗ Homebrew not found. Install Python manually: https://www.python.org/downloads/"
    echo "    Or install Homebrew first: /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
    exit 2
  fi
fi

# --- uv (Python package manager, needed for MCP servers) ---
echo "[uv]"
if command -v uv &>/dev/null; then
  ok "uv found: $(uv --version 2>&1)"
else
  info "uv not found — installing..."
  if command -v brew &>/dev/null; then
    brew install uv
    added "uv installed via Homebrew"
  elif command -v pip3 &>/dev/null; then
    pip3 install uv
    added "uv installed via pip3"
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
    added "uv installed via installer script"
  fi
fi

# --- jq (JSON processing) ---
echo "[jq]"
if command -v jq &>/dev/null; then
  ok "jq found: $(jq --version 2>&1)"
else
  info "jq not found — installing..."
  if command -v brew &>/dev/null; then
    brew install jq
    added "jq installed via Homebrew"
  else
    echo "  ✗ Install jq manually: https://jqlang.github.io/jq/download/"
    exit 2
  fi
fi

# --- git (should always be present, but check) ---
echo "[git]"
if command -v git &>/dev/null; then
  ok "git found: $(git --version)"
else
  info "git not found — installing..."
  if command -v brew &>/dev/null; then
    brew install git
    added "git installed via Homebrew"
  else
    echo "  ✗ Install git: https://git-scm.com/downloads"
    exit 2
  fi
fi

# --- csvkit (CSV processing for requirements tracking) ---
echo "[csvkit]"
if python3 -c "import csvkit" 2>/dev/null || command -v csvlook &>/dev/null; then
  ok "csvkit available"
else
  info "csvkit not found — installing..."
  if command -v uv &>/dev/null; then
    uv pip install --system csvkit 2>/dev/null || pip3 install csvkit
    added "csvkit installed"
  elif command -v pip3 &>/dev/null; then
    pip3 install csvkit
    added "csvkit installed via pip3"
  else
    echo "  ⚠ csvkit not installed (optional — needed for requirements CSV validation)"
  fi
fi

# --- Summary ---
echo
echo "Done. $INSTALLED installed, $SKIPPED already present."
[[ $INSTALLED -gt 0 ]] && echo "Restart your shell if PATH changes aren't picked up."
exit 0
