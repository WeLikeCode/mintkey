#!/usr/bin/env bash
# Wizard helpers — sourced by setup-wizard.sh
# Provides: ask_*, validate_*, render_*, detect_conflicts, save_answers, print_summary

# ─── PROMPT HELPERS ──────────────────────────────────────────────

# ANSWERS map is declared in the calling script

_print_question() {
  local id="$1"; local prompt="$2"; local req="$3"; local opts="${4:-}"
  echo
  echo "── $id ──────────────────────────────────────────────"
  echo "$prompt"
  [ -n "$opts" ] && echo "  Options: $opts"
  if [ "$req" = "required" ]; then echo "  (mandatory)"; else echo "  (optional — press Enter to defer)"; fi
  if [ -n "${ANSWERS[$id]:-}" ]; then echo "  Current: ${ANSWERS[$id]}"; fi
  echo -n "→ "
}

ask_freetext() {
  local id="$1" prompt="$2" req="$3"; local validator="${4:-}"
  while :; do
    _print_question "$id" "$prompt" "$req"
    local input; read -r input
    [ -z "$input" ] && [ "$req" = "optional" ] && { ANSWERS[$id]="${ANSWERS[$id]:-Defer}"; return; }
    [ -z "$input" ] && [ "$req" = "required" ] && { echo "✘ Mandatory. Cannot be blank."; continue; }
    if [ -n "$validator" ] && ! "$validator" "$input"; then continue; fi
    ANSWERS[$id]="$input"; return
  done
}

ask_paragraph() {
  local id="$1" prompt="$2" req="$3"; local validator="${4:-}"
  while :; do
    _print_question "$id" "$prompt" "$req"
    local input; read -r input
    [ -z "$input" ] && [ "$req" = "optional" ] && { ANSWERS[$id]="${ANSWERS[$id]:-Defer}"; return; }
    [ -z "$input" ] && [ "$req" = "required" ] && { echo "✘ Mandatory."; continue; }
    if [ -n "$validator" ] && ! "$validator" "$input"; then continue; fi
    ANSWERS[$id]="$input"; return
  done
}

ask_choice() {
  local id="$1" prompt="$2" req="$3" opts="$4"
  while :; do
    _print_question "$id" "$prompt" "$req" "$opts"
    local input; read -r input
    [ -z "$input" ] && [ "$req" = "optional" ] && { ANSWERS[$id]="${ANSWERS[$id]:-Defer}"; return; }
    [ -z "$input" ] && { echo "✘ Mandatory."; continue; }
    if echo "$opts" | tr '|' '\n' | grep -Fxq "$input"; then
      ANSWERS[$id]="$input"; return
    fi
    echo "✘ Must be one of: $opts"
  done
}

ask_multichoice() {
  local id="$1" prompt="$2" req="$3" opts="$4"
  while :; do
    _print_question "$id" "$prompt" "$req" "$opts"
    local input; read -r input
    [ -z "$input" ] && [ "$req" = "optional" ] && { ANSWERS[$id]="${ANSWERS[$id]:-Defer}"; return; }
    [ -z "$input" ] && { echo "✘ Mandatory."; continue; }
    local valid=1
    IFS=',' read -ra picks <<< "$input"
    for pick in "${picks[@]}"; do
      pick="$(echo "$pick" | sed 's/^ *//;s/ *$//')"
      if ! echo "$opts" | tr '|' '\n' | grep -Fxq "$pick"; then
        echo "✘ '$pick' not in: $opts"; valid=0; break
      fi
    done
    [ "$valid" -eq 1 ] && { ANSWERS[$id]="$input"; return; }
  done
}

ask_yesno() {
  local id="$1" prompt="$2" req="$3"
  ask_choice "$id" "$prompt" "$req" "Yes|No"
}

ask_three_real_risks() {
  local id="$1" prompt="$2"
  echo
  echo "── $id ──────────────────────────────────────────────"
  echo "$prompt"
  echo
  echo "  Format: enter 3 risks. For each: 'Risk title — what breaks — evidence'"
  echo "  Example: 'Source data quality variance — primary keys non-unique in ~3% of rows — 2026-04-02 workshop with client'"
  echo "  The wizard refuses platitudes. Be specific."
  echo
  local count=0
  local risks=""
  while [ "$count" -lt 3 ]; do
    echo -n "Risk $((count+1))/3 → "
    local r; read -r r
    if validate_risk_entry "$r"; then
      risks+="${r}\n"
      count=$((count+1))
    fi
  done
  ANSWERS[$id]="$(echo -e "$risks")"
}

# ─── VALIDATORS ──────────────────────────────────────────────────

validate_kebab_no_client() {
  local v="$1"
  if ! [[ "$v" =~ ^[a-z][a-z0-9-]*$ ]]; then
    echo "✘ Must be kebab-case (lowercase letters, digits, hyphens; start with letter)."
    return 1
  fi
  if [ -n "${ANSWERS[Q2]:-}" ] && echo "$v" | grep -qiF "${ANSWERS[Q2]}"; then
    echo "✘ Codename must NOT contain the client name."
    return 1
  fi
  return 0
}

validate_business_goal() {
  local v="$1"
  if [ ${#v} -lt 120 ]; then
    echo "✘ Too short. Goal must be at least 120 characters and describe what changes for the customer."
    return 1
  fi
  local denylist="transform the business|leverage AI|drive value|synergy|next generation|digital transformation|unlock potential|enable scale"
  if echo "$v" | grep -qiE "$denylist"; then
    if ! echo "$v" | grep -qiE "(reduce|increase|decrease|eliminate|measure|customer|user|operator|technician|engineer|inspector|reviewer|manager|in [0-9]+ (hour|day|week|month))"; then
      echo "✘ Detected platitude language with no concrete object. Rewrite to say what changes for whom."
      return 1
    fi
  fi
  return 0
}

validate_architect() {
  local v="$1"
  if ! echo "$v" | grep -qE '<[^@]+@[^>]+>'; then
    echo "✘ Must include an email in angle brackets, e.g. 'Jane Doe <jane@example.com>'."
    return 1
  fi
  if echo "$v" | grep -qiE "(TBD|To be|Pending|John Doe|example@example.com)"; then
    echo "✘ Architect must be named on Day 0, not deferred."
    return 1
  fi
  return 0
}

validate_risk_entry() {
  local r="$1"
  if [ -z "$r" ]; then echo "✘ Risk cannot be blank."; return 1; fi
  if ! echo "$r" | grep -qF "—"; then
    echo "✘ Format: 'Title — what breaks — evidence'. Use em-dash separators."
    return 1
  fi
  local parts; parts="$(echo "$r" | awk -F'—' '{print NF}')"
  if [ "$parts" -lt 3 ]; then
    echo "✘ Need 3 parts: title, what breaks, evidence. Got $parts."
    return 1
  fi
  local denylist="data sovereignty|terminology drift|generic concern|could potentially|might happen|in some configurations"
  if echo "$r" | grep -qiE "$denylist"; then
    echo "✘ Padding language detected. Real risks have specific evidence, not speculation."
    return 1
  fi
  return 0
}

# ─── CONFLICT DETECTION ──────────────────────────────────────────

detect_conflicts() {
  local conflicts=0
  if [[ "${ANSWERS[Q8]}" == *"Air-gapped"* && "${ANSWERS[Q17]:-Defer}" == "Vendor-specified" ]]; then
    echo "✘ Conflict: Q8=Air-gapped + Q17=Vendor-specified telemetry. Vendor SaaS often unreachable from air-gapped."
    conflicts=$((conflicts+1))
  fi
  if [[ "${ANSWERS[Q13]}" == "No" && "${ANSWERS[Q14]}" == "Yes - broker chosen" ]]; then
    echo "ℹ Note: Q13=No AI but Q14=eventing broker chosen. Confirm eventing is for non-AI use case."
  fi
  if [[ "${ANSWERS[Q16]}" == "Full"* && "${ANSWERS[Q5]}" == "Discovery" ]]; then
    echo "ℹ Warning: Q16=Full depth but Q5=Discovery. Mismatch — Discovery typically warrants Skeleton or Working set."
  fi
  return $conflicts
}

# ─── PERSISTENCE ─────────────────────────────────────────────────

save_answers() {
  local path="$1"
  mkdir -p "$(dirname "$path")"
  {
    echo "{"
    local first=1
    for k in "${!ANSWERS[@]}"; do
      [ $first -eq 0 ] && echo ","
      printf '  "%s": %s' "$k" "$(echo "${ANSWERS[$k]}" | python3 -c 'import sys, json; print(json.dumps(sys.stdin.read().rstrip()))' 2>/dev/null || echo "\"${ANSWERS[$k]//\"/\\\"}\"")"
      first=0
    done
    echo
    echo "}"
  } > "$path"
}

load_prior_answers() {
  local path="$1"
  if [ ! -f "$path" ]; then return; fi
  while IFS= read -r line; do
    if [[ "$line" =~ \"([^\"]+)\":\ *(.*) ]]; then
      local k="${BASH_REMATCH[1]}"
      local v="${BASH_REMATCH[2]}"
      v="${v%,}"; v="${v%\"}"; v="${v#\"}"
      ANSWERS[$k]="$v"
    fi
  done < "$path"
}

load_yaml_answers() {
  local path="$1"
  if [ ! -f "$path" ]; then echo "✘ YAML file not found: $path"; exit 2; fi
  while IFS=': ' read -r k v; do
    [ -z "$k" ] || [[ "$k" =~ ^# ]] && continue
    ANSWERS[$k]="${v//\"/}"
  done < "$path"
}

# ─── RENDERING ───────────────────────────────────────────────────

render_template() {
  local name="$1" inclusion="$2"
  local src="$REPO_ROOT/bootstrap/templates/${name}.template.md"
  local dst="$REPO_ROOT/.kiro/steering/${name}.md"
  if [ ! -f "$src" ]; then
    # Generic placeholder
    write_generic_steering "$dst" "$name" "$inclusion"
  else
    substitute_vars < "$src" > "$dst"
  fi
  echo "  ✓ .kiro/steering/${name}.md ($inclusion)"
}

render_template_doc() {
  local name="$1" dst="$2"
  # Templates moved to skill references (Kiro convention).
  local src=""
  case "$name" in
    risk-register)         src="$REPO_ROOT/.kiro/skills/risk-register-update/references/risk-register-template.md" ;;
    assumption-register)   src="$REPO_ROOT/.kiro/skills/assumption-validate/references/assumption-register-template.md" ;;
    architecture-vision|decision-log)
      # No skill-bundled template for these; use bootstrap/templates/ if present
      src="$REPO_ROOT/bootstrap/templates/${name}.template.md"
      ;;
    *) src="$REPO_ROOT/bootstrap/templates/${name}.template.md" ;;
  esac
  if [ ! -f "$src" ]; then
    echo "  ⚠ Template missing: $src — skipping $dst"
    return
  fi
  substitute_vars < "$src" > "$REPO_ROOT/$dst"
  echo "  ✓ $dst"
}

write_generic_steering() {
  local dst="$1" name="$2" inclusion="$3"
  local title="${name//-/ }"
  title="$(echo "$title" | sed 's/\b\(.\)/\u\1/g')"
  cat > "$dst" <<EOF
---
inclusion: $inclusion
owner: "@${ANSWERS[Q4]%% *}"
last_reviewed: $(date +%Y-%m-%d)
status: draft
max_words: 1500
---

# $title

> [REQUIRES-UPDATE: This file is a generic skeleton. The architect must populate engagement-specific content. See bootstrap/questionnaire.md for the answers that should drive this content.]

## Purpose

[REQUIRES-UPDATE: One paragraph — what this steering file governs and why.]

## Conventions

[REQUIRES-UPDATE: The actual conventions — bullets, tables, or short prose. ≤ 1500 words.]

## What does NOT belong here

[REQUIRES-UPDATE: List the things that look like they belong here but don't (e.g., implementation detail, ADR rationale).]

## Cross-references

- ADRs that established these conventions: [REQUIRES-UPDATE]
- Companion steering files: [REQUIRES-UPDATE]

---

*[REQUIRES-UPDATE: Replace this skeleton with engagement-specific content, then remove this banner.]*
EOF
}

substitute_vars() {
  sed \
    -e "s|{{ENGAGEMENT_NAME}}|${ANSWERS[Q1]}|g" \
    -e "s|{{CLIENT}}|${ANSWERS[Q2]}|g" \
    -e "s|{{ARCHITECT}}|${ANSWERS[Q4]}|g" \
    -e "s|{{ARCHITECT_NAME}}|${ANSWERS[Q4]%% <*}|g" \
    -e "s|{{ARCHITECT_EMAIL}}|$(echo "${ANSWERS[Q4]}" | grep -oE '<[^>]+>' | tr -d '<>')|g" \
    -e "s|{{PHASE}}|${ANSWERS[Q5]}|g" \
    -e "s|{{ISO_DATE}}|$(date +%Y-%m-%d)|g" \
    -e "s|{{NNNN}}|0001|g" \
    -e "s|{{Title}}|Bootstrap baseline|g" \
    -e "s|{{YYYY-MM-DD}}|$(date +%Y-%m-%d)|g" \
    -e "s|{{vN}}|v1|g"
}

render_team_template() {
  local dst="$1"
  cat > "$REPO_ROOT/$dst" <<EOF
# Onboarding — {{handle}}

Started: $(date +%Y-%m-%d) | Track: {{role}} | Buddy: {{buddy_handle}}

## Required reading
- [ ] README.md
- [ ] BOOTSTRAP.md
- [ ] (role-specific list — see docs/onboarding/{role}.md)

## Hands-on gates
- [ ] \`make doctor\` is green
- [ ] I read the closest 1-2 ADRs
- [ ] I opened one PR (link: ___) — even a typo fix counts
- [ ] I left one comment on an open ADR or open-question

## First impressions (one paragraph)
What surprised me, what was unclear, what I'd improve in onboarding.

## Sign-off
Signed: {{handle}}    Date: ____
Reviewed by buddy: {{buddy_handle}}    Date: ____
EOF
  echo "  ✓ $dst"
}

render_bootstrap_adr() {
  local dst="$1"
  cat > "$REPO_ROOT/$dst" <<EOF
# ADR-0001: Bootstrap baseline

**Status:** Accepted
**Date:** $(date +%Y-%m-%d)
**Author:** ${ANSWERS[Q4]}
**Decision-maker:** ${ANSWERS[Q4]}

## Context

Engagement \`${ANSWERS[Q1]}\` for client \`${ANSWERS[Q2]}\` is bootstrapped from kiro-project-template v$TEMPLATE_VERSION on $(date +%Y-%m-%d). This ADR records the load-bearing answers to the wizard so that future re-architecture has a single artifact to point at.

## Decision

We adopt the following baseline:

| Concern | Choice |
|---|---|
| Project codename | \`${ANSWERS[Q1]}\` |
| Phase | ${ANSWERS[Q5]} |
| Regulated industry | ${ANSWERS[Q6]} |
| Tenancy | ${ANSWERS[Q7]} |
| Deployment | ${ANSWERS[Q8]} |
| Backend language(s) | ${ANSWERS[Q9]} |
| Frontend | ${ANSWERS[Q10]} |
| Persistence | ${ANSWERS[Q11]} |
| API contract format | ${ANSWERS[Q12]} |
| AI / ML | ${ANSWERS[Q13]} |
| Eventing | ${ANSWERS[Q14]} |
| Branching | ${ANSWERS[Q15]} |

## Why

Each choice is documented with rationale in the steering files generated alongside this ADR.

## Consequences

- **Positive:** explicit baseline; no implicit decisions.
- **Negative:** changing any of the above requires a superseding ADR.
- **Neutral:** open questions logged in \`docs/architecture/open-questions.md\`.

## Spec / contract back-references

- [README.md](../../README.md)
- [BOOTSTRAP.md](../../BOOTSTRAP.md)
- [.kiro/setup-state.json](../../.kiro/setup-state.json)

## Tests asserting this decision

- N/A (configuration ADR; assertion is the manifest itself)
EOF
  echo "  ✓ $dst"
}

render_claude_md() {
  local dst="$1"
  # Already exists from template; substitute the engagement: block
  python3 - <<PYEOF
import re, sys, datetime
path = "$dst"
with open(path) as f: content = f.read()
yml = '''engagement:
  name: "${ANSWERS[Q1]}"
  client: "${ANSWERS[Q2]}"
  architect: "${ANSWERS[Q4]}"
  phase: "${ANSWERS[Q5]}"
  bootstrapped_at: "$(date +%Y-%m-%d)"
  template_version: "$TEMPLATE_VERSION"
languages: [${ANSWERS[Q9]}]
planes: []'''
content = re.sub(r"engagement:\\s*\\n  name:.*?planes:.*?\\n", yml + "\\n", content, flags=re.DOTALL)
with open(path, "w") as f: f.write(content)
PYEOF
}

render_codeowners() {
  local dst="$1"
  local handle="${ANSWERS[Q4]%% *}"
  cat > "$dst" <<EOF
# CODEOWNERS — generated by bootstrap wizard
# Architect-only on architecture canon and steering. Expand once squads are named (Q24).

docs/architecture/   @${handle}
.kiro/steering/      @${handle}
.kiro/skills/        @${handle}
.kiro/specs/         @${handle}
EOF
  echo "  ✓ CODEOWNERS"
}

write_manifest() {
  local path="$1" version="$2"
  cat > "$path" <<EOF
template_version: $version
template_commit: \$(git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "unknown")
bootstrapped_at: $(date -Iseconds)
overrides: {}
EOF
}

print_summary() {
  echo
  echo "── Summary ──────────────────────────────────────────"
  echo "Files generated:"
  find "$REPO_ROOT/.kiro/steering" "$REPO_ROOT/docs/architecture" -type f -newer "$REPO_ROOT/bootstrap/setup-wizard.sh" 2>/dev/null | sed "s|$REPO_ROOT/|  |"
  echo
  local deferred=0
  for k in "${!ANSWERS[@]}"; do
    [ "${ANSWERS[$k]}" = "Defer" ] && deferred=$((deferred+1))
  done
  echo "Deferred answers logged to open-questions.md: $deferred"
  if [ $deferred -gt 8 ]; then
    echo "⚠ Warning: more than 8 Defer/TBD — consider answering more before closing this phase."
  fi
}
