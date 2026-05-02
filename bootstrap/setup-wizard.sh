#!/usr/bin/env bash
# Kiro Project Template — Bootstrap Wizard
# Usage:
#   ./bootstrap/setup-wizard.sh                # interactive mode
#   ./bootstrap/setup-wizard.sh --re-run       # re-run, preserving prior answers as defaults
#   ./bootstrap/setup-wizard.sh --save-and-exit  # save partial progress
#   ./bootstrap/setup-wizard.sh --from-yaml answers.yml  # non-interactive

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANSWERS_JSON="$REPO_ROOT/.kiro/wizard-answers.json"
MANIFEST="$REPO_ROOT/.kiro/template-manifest.yml"
TEMPLATE_VERSION="0.1.0"

# Load helpers
# shellcheck source=lib/wizard-helpers.sh
. "$REPO_ROOT/bootstrap/lib/wizard-helpers.sh"

declare -A ANSWERS=()
RE_RUN=0
SAVE_AND_EXIT=0
NON_INTERACTIVE=""

# Parse flags
for arg in "$@"; do
  case "$arg" in
    --re-run)              RE_RUN=1 ;;
    --save-and-exit)       SAVE_AND_EXIT=1 ;;
    --from-yaml=*)         NON_INTERACTIVE="${arg#*=}" ;;
    --help|-h)             cat "$REPO_ROOT/bootstrap/questionnaire.md"; exit 0 ;;
    *) echo "Unknown flag: $arg" >&2; exit 2 ;;
  esac
done

# Load prior answers if re-running
if [ "$RE_RUN" -eq 1 ] && [ -f "$ANSWERS_JSON" ]; then
  echo "→ Re-running wizard. Prior answers will be shown as defaults; press Enter to keep, type to change."
  load_prior_answers "$ANSWERS_JSON"
fi

# Non-interactive: load from yaml
if [ -n "$NON_INTERACTIVE" ]; then
  load_yaml_answers "$NON_INTERACTIVE"
fi

# Banner
cat <<'BANNER'
==============================================================
  Kiro Project Template — Bootstrap Wizard v0.1.0
==============================================================

This wizard asks 16 mandatory + 9 optional questions to populate
your engagement's steering files and registers.

It will refuse to proceed if mandatory questions are blank, if
Q25 (top three risks) is padded with platitudes, or if conflicting
answers are detected.

You can save partial progress with --save-and-exit and resume later.
See bootstrap/questionnaire.md for the full question catalog.

==============================================================
BANNER

# ──────────────────────────────────────────────────────────────
# MANDATORY QUESTIONS
# ──────────────────────────────────────────────────────────────

ask_freetext         "Q1"  "Project codename (kebab-case, no client name)"  required validate_kebab_no_client
ask_freetext         "Q2"  "Client / sponsoring organisation"               required
ask_paragraph        "Q3"  "Business goal — one paragraph (>=120 chars, no platitudes)"  required validate_business_goal
ask_freetext         "Q4"  "Architect of record (Full Name <email>)"        required validate_architect
ask_choice           "Q5"  "Engagement phase at start"                      required "Discovery|PoC|MVP|Scale-up|Sustain"
ask_choice           "Q6"  "Regulated industry"                             required "No|Light (privacy only)|Heavy (sector regs)"
ask_choice           "Q7"  "Tenancy model"                                  required "Single-tenant|Multi-tenant shared|Multi-tenant isolated|Customer-deployed"
ask_multichoice      "Q8"  "Target deployment (multi-select, comma-sep)"    required "Public cloud|Private cloud|On-prem customer|Air-gapped|Hybrid"
ask_multichoice      "Q9"  "Primary backend language(s)"                    required "Python|TypeScript-Node|Java|Go|.NET|Rust|Other"
ask_choice           "Q10" "Frontend present"                               required "None|SPA|SSR|Mobile|Multiple"
ask_multichoice      "Q11" "Persistence primaries"                          required "Relational|Document|Object store|Time-series|Graph|Vector|None-yet"
ask_multichoice      "Q12" "API contract format"                            required "OpenAPI|gRPC|GraphQL|Async-only|Internal-only"
ask_choice           "Q13" "AI / ML in critical path"                       required "No|Sync inference|Async/batch inference|Both"
ask_choice           "Q14" "Eventing / async needed"                        required "No|Yes - broker not chosen|Yes - broker chosen"
ask_choice           "Q15" "Source control + branching model"               required "Trunk-based|GitFlow|GitHub Flow|Custom"
ask_choice           "Q16" "Architect first-cut horizon"                    required "Skeleton (Discovery)|Working set (PoC)|Full (pre-MVP)"

# Q25 — three real risks (mandatory, refusal-strict)
ask_three_real_risks "Q25" "Three top business risks (each: 'what breaks' + 'evidence')"

# ──────────────────────────────────────────────────────────────
# OPTIONAL QUESTIONS (Q17-Q24)
# ──────────────────────────────────────────────────────────────

ask_choice           "Q17" "Observability stack preference (optional)"      optional "OpenTelemetry default|Vendor-specified|Defer"
ask_choice           "Q18" "Identity provider / auth pattern (optional)"    optional "OIDC external|Internal|API-key only|Defer"
ask_yesno            "Q19" "Schema-driven UI (forms generated from schemas)? (optional)"  optional
ask_yesno            "Q20" "Geospatial / heavy-data plane? (optional)"      optional
ask_choice           "Q21" "CODEOWNERS model (optional)"                    optional "Squad-aligned|Domain-aligned|Architect-only initial"
ask_choice           "Q22" "Test-data strategy known? (optional)"           optional "Synthetic|Anonymized prod|Customer-supplied|Defer"
if [ "${ANSWERS[Q6]}" != "No" ]; then
  ask_multichoice    "Q23" "Known compliance frameworks (optional, multi-select, conditional)" optional "SOC2|ISO27001|HIPAA|GDPR|PCI-DSS|sector-specific|None"
fi
ask_freetext         "Q24" "Initial squad count + names (or unknown) (optional)"  optional

# ──────────────────────────────────────────────────────────────
# CONFLICT DETECTION
# ──────────────────────────────────────────────────────────────

detect_conflicts || {
  echo "✘ Conflict(s) detected. Re-run with corrections." >&2
  exit 1
}

# Save & exit if requested
if [ "$SAVE_AND_EXIT" -eq 1 ]; then
  save_answers "$ANSWERS_JSON"
  echo "✓ Saved partial answers to $ANSWERS_JSON. Resume with --re-run."
  exit 0
fi

# ──────────────────────────────────────────────────────────────
# RENDER PHASE — generate files based on answers
# ──────────────────────────────────────────────────────────────

echo
echo "=============================================================="
echo "  Generating engagement files…"
echo "=============================================================="

mkdir -p "$REPO_ROOT/.kiro/steering" "$REPO_ROOT/docs/architecture/adrs" "$REPO_ROOT/team/_template"

# Always-generated files
render_template "product"                "always"
render_template "structure"              "always"
render_template "architecture-principles" "always"
render_template "tech"                   "always"
render_template "repo-governance"        "always"
render_template "ownership-and-codeowners-strategy" "always"
render_template "open-questions"         "always"

# Conditional steering files
[[ "${ANSWERS[Q9]}"  == *"Python"*         ]] && render_template "python-conventions" "fileMatch"
[[ "${ANSWERS[Q9]}"  == *"TypeScript"*     ]] && render_template "typescript-conventions" "fileMatch"
[[ "${ANSWERS[Q10]}" != "None"             ]] && { render_template "frontend-conventions" "fileMatch"; render_template "web-app-structure" "always"; }
[[ "${ANSWERS[Q11]}" == *"Relational"* || "${ANSWERS[Q11]}" == *"Document"* ]] && render_template "database-conventions" "fileMatch"
[[ "${ANSWERS[Q11]}" == *"Object store"*   ]] && render_template "object-storage-conventions" "on-demand"
[[ "${ANSWERS[Q12]}" != "Internal-only"    ]] && render_template "api-contracts-and-schemas" "fileMatch"
[[ "${ANSWERS[Q13]}" != "No"               ]] && { render_template "ai-engine-integration-flow" "on-demand"; render_template "data-lifecycle-and-idempotency" "on-demand"; }
[[ "${ANSWERS[Q6]}"  != "No" || "${ANSWERS[Q7]}" != "Single-tenant" ]] && render_template "security-and-tenancy" "on-demand"
[[ "${ANSWERS[Q17]:-Defer}" != "Defer"     ]] && render_template "observability-and-operations" "on-demand"
[[ "${ANSWERS[Q20]:-No}" == "Yes"          ]] && render_template "geospatial-conventions" "on-demand"
[[ "${ANSWERS[Q22]:-Defer}" != "Defer"     ]] && render_template "fixtures-and-test-data-strategy" "on-demand"
[[ "${ANSWERS[Q16]}" != "Skeleton"*        ]] && { render_template "developer-workflows" "on-demand"; render_template "testing-strategy" "on-demand"; }

render_template "branching-and-release" "on-demand"

# Architecture canon
render_template_doc  "architecture-vision"   "docs/architecture/architecture-vision.md"
render_template_doc  "risk-register"         "docs/architecture/risk-register.md"
render_template_doc  "assumption-register"   "docs/architecture/assumption-register.md"
render_template_doc  "decision-log"          "docs/architecture/decision-log.md"

# Team scaffolding
render_team_template "team/_template/onboarded.md"

# Generate ADR-0001-bootstrap recording the wizard's choices
render_bootstrap_adr "docs/architecture/adrs/ADR-0001-bootstrap.md"


# CODEOWNERS — architect-only on architecture + steering
render_codeowners "$REPO_ROOT/CODEOWNERS"

# Save manifest + answers
save_answers "$ANSWERS_JSON"
write_manifest "$MANIFEST" "$TEMPLATE_VERSION"

# ──────────────────────────────────────────────────────────────
# SUMMARY
# ──────────────────────────────────────────────────────────────

print_summary

echo
echo "✓ Bootstrap complete."
echo
echo "Next: run 'make doctor' to verify, then open docs/onboarding/README.md."
