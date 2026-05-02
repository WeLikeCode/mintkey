#!/usr/bin/env bash
# kiro-steering-audit.sh — audit .kiro/steering/ files
# Usage: kiro-steering-audit.sh [--json]
# Exit 0: clean. Exit 1: warnings. Exit 2: errors.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
STEERING="$REPO_ROOT/.kiro/steering"
JSON_MODE=0
[[ "${1:-}" == "--json" ]] && JSON_MODE=1

DEFAULT_WORD_CAP=1500
DEFAULT_BUDGET_CAP=5000
STALE_DAYS=90
ERRORS=0
WARNINGS=0

declare -A MODE_MAP
declare -A WORD_MAP
DEFAULT_TOTAL=0

for f in "$STEERING"/*.md; do
  name="$(basename "$f")"
  words=$(wc -w < "$f")
  WORD_MAP[$name]=$words

  if grep -q "^inclusion:" "$f" 2>/dev/null; then
    mode=$(grep "^inclusion:" "$f" | awk '{print $2}')
    MODE_MAP[$name]=$mode
  else
    MODE_MAP[$name]="default"
    DEFAULT_TOTAL=$((DEFAULT_TOTAL + words))
  fi
done

if [[ $JSON_MODE -eq 1 ]]; then
  echo "{"
  echo "  \"files\": ["
  first=1
  for name in "${!MODE_MAP[@]}"; do
    [[ $first -eq 0 ]] && echo ","
    printf '    {"name":"%s","mode":"%s","words":%d}' "$name" "${MODE_MAP[$name]}" "${WORD_MAP[$name]}"
    first=0
  done
  echo ""
  echo "  ],"
  echo "  \"default_total_words\": $DEFAULT_TOTAL,"
  echo "  \"default_budget_cap\": $DEFAULT_BUDGET_CAP"
  echo "}"
  exit 0
fi

echo "=== Kiro Steering Audit ==="
echo

echo "Inclusion modes:"
for name in $(echo "${!MODE_MAP[@]}" | tr ' ' '\n' | sort); do
  mode="${MODE_MAP[$name]}"
  words="${WORD_MAP[$name]}"
  flag=""
  if [[ "$mode" == "default" && $words -gt $DEFAULT_WORD_CAP ]]; then
    flag=" ⚠ over ${DEFAULT_WORD_CAP}w cap"
    WARNINGS=$((WARNINGS+1))
  fi
  printf "  %-50s  %-12s  %4d words%s\n" "$name" "$mode" "$words" "$flag"
done

echo
echo "Default-load budget: $DEFAULT_TOTAL / $DEFAULT_BUDGET_CAP words"
if [[ $DEFAULT_TOTAL -gt $DEFAULT_BUDGET_CAP ]]; then
  echo "  ✗ Over budget by $((DEFAULT_TOTAL - DEFAULT_BUDGET_CAP)) words"
  ERRORS=$((ERRORS+1))
else
  echo "  ✓ Within budget"
fi

echo
echo "Stale files (not modified in ${STALE_DAYS}+ days):"
found_stale=0
while IFS= read -r f; do
  name="$(basename "$f")"
  echo "  ⚠ $name"
  WARNINGS=$((WARNINGS+1))
  found_stale=1
done < <(find "$STEERING" -name "*.md" -mtime +${STALE_DAYS} 2>/dev/null)
[[ $found_stale -eq 0 ]] && echo "  ✓ None"

echo
if [[ $ERRORS -gt 0 ]]; then
  echo "✗ $ERRORS error(s), $WARNINGS warning(s)."
  exit 2
elif [[ $WARNINGS -gt 0 ]]; then
  echo "⚠ $WARNINGS warning(s)."
  exit 1
else
  echo "✓ Steering audit clean."
  exit 0
fi
