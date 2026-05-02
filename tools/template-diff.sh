#!/usr/bin/env bash
# template-diff.sh — compare engagement files to the template version bootstrapped from
# Usage: template-diff.sh [pull <version>]
# Exit 0: no divergence. Exit 1: divergence found.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STATE="$REPO_ROOT/.kiro/setup-state.json"
MODE="${1:-diff}"

if [[ ! -f "$STATE" ]]; then
  echo "✗ .kiro/setup-state.json not found. Run project-setup first."
  exit 1
fi

TEMPLATE_VERSION=$(python3 -c "import json; d=json.load(open('$STATE')); print(d.get('template_version','unknown'))" 2>/dev/null || echo "unknown")

echo "=== Template Diff ==="
echo "Bootstrapped from template version: $TEMPLATE_VERSION"
echo

if [[ "$MODE" == "pull" ]]; then
  TARGET_VERSION="${2:-}"
  if [[ -z "$TARGET_VERSION" ]]; then
    echo "Usage: make template-pull <version>"
    echo "Example: make template-pull 0.2.0"
    exit 1
  fi
  echo "Pulling template version $TARGET_VERSION..."
  echo "This requires the template remote to be configured."
  echo "Add it with: git remote add template <template-repo-url>"
  if git -C "$REPO_ROOT" remote get-url template &>/dev/null; then
    git -C "$REPO_ROOT" fetch template "refs/tags/v${TARGET_VERSION}:refs/remotes/template/v${TARGET_VERSION}" 2>/dev/null || \
    git -C "$REPO_ROOT" fetch template "$TARGET_VERSION" 2>/dev/null
    echo "Fetched. Review with: git diff HEAD template/$TARGET_VERSION -- .kiro/ docs/architecture/"
  else
    echo "✗ 'template' remote not configured. Add it first."
    exit 1
  fi
else
  # Show files that differ from git HEAD (local uncommitted changes to template-owned paths)
  echo "Uncommitted changes to template-owned paths:"
  changed=$(git -C "$REPO_ROOT" status --short -- .kiro/ docs/architecture/ Makefile 2>/dev/null || true)
  if [[ -z "$changed" ]]; then
    echo "  ✓ No uncommitted changes to template-owned paths."
    exit 0
  else
    echo "$changed"
    exit 1
  fi
fi
