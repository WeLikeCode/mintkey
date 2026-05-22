# <Session Title> — Session Plan

> Copy from SESSION_TEMPLATE — fill in the placeholders.

**Session:** `<YYYY-MM-DD-kebab-slug>`
**Driver:** `remediation-orchestrator` skill
**Status:** Step 0 (issue intake) — fill `ISSUE_INTAKE.md` before anything else.

---

## Mission

<TODO: One paragraph. What is broken or risky, and what does a successful session leave behind?>

---

## Hard rules (every chunk inherits)

- No `Co-Authored-By` trailer on any commit
- No `--no-verify`
- No `docker compose down -v`
- No edits to accepted ADRs
- No product-code changes outside the scope defined in `ISSUE_INTAKE.md`
- Validate via tools: every "done" claim carries command output
- Surgical changes; one logical change per commit

---

## Issue intake

Fill `ISSUE_INTAKE.md` (symlink to `../ISSUE_INTAKE_TEMPLATE.md`) before this session starts.

**Gate:** orchestrator MUST NOT dispatch any chunk until all 9 required fields are answered.

---

## Phase 0 — Baseline + chunk planning

Dispatch a BASELINE-REVIEWER (read-only):

> "Run the verification suite end-to-end, paste output, report which DoD items are red. Do NOT fix anything."

After baseline: write `01-orchestrator-chunks.md` with the chunk plan.

---

## Phase 1+ — Chunk dispatch

<TODO: Describe the chunks or reference `01-orchestrator-chunks.md`.>

Dispatch order: <TODO: serial / parallel per disjoint file ownership>

---

## Closing

When all chunks PASS, spawn a final full-DoD REVIEWER. Write `99-report.md`.
