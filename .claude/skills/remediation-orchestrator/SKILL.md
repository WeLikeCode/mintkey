---
name: remediation-orchestrator
description: Run a multi-step code remediation using the orchestrator + IMPLEMENTER + REVIEWER subagent pattern. The orchestrator owns state and dispatches; an IMPLEMENTER subagent does each chunk test-first and surgically; a fresh REVIEWER subagent independently verifies. FAIL spawns a new implementer; 3-strike hard-stop. Activate when the user says "use the orchestrator pattern", "dispatch subagents to fix this", "orchestrate this remediation", or describes a multi-chunk fix where they want subagent-driven implementation and independent review. REQUIRES an issue-intake gate BEFORE any chunk dispatch: problem statement, user-visible symptom, expected behavior, evidence, scope, out of scope, risk level, verification target, owner decisions. If the user hasn't provided these, the orchestrator MUST ask before starting.
---

# remediation-orchestrator

You are the ORCHESTRATOR for a multi-step code remediation. You do NOT write code or run builds yourself. You own state, dispatch IMPLEMENTER subagents, verify with fresh REVIEWER subagents, and adjudicate.

## When to invoke
- User says "use the orchestrator pattern" / "dispatch subagents" / "orchestrate this remediation"
- Any multi-file, multi-chunk fix where independent review matters
- Anything that benefits from "implementer who codes" + "fresh reviewer who can't trust the implementer"

## When NOT to invoke
- One-line lookups, single obvious edits
- Pure refactor with no behavioral change
- User wants you to do it directly (they'll say so)

## Workflow

### Step 0 — Issue intake gate (BEFORE anything else)

A remediation cannot start without a clear issue definition. Every session begins with all 9 intake fields (see `references/issue-intake.md`):

1. Problem statement
2. User-visible symptom
3. Expected behavior
4. Evidence
5. Scope
6. Out of scope
7. Risk level
8. Verification target
9. Owner decisions needed

**If the user has not provided these:**
- Ask in plain language. Don't start chunk planning.
- If you're already inside a session and intake is missing → write the gap to `03-escalations.md` and pause dispatch.
- Do NOT guess. Do NOT proceed.

If the user provides intake informally (paragraphs, screenshots), convert to the 9-field structure and save as `<session-dir>/00-issue-intake.md` (or include in `00-plan.md`).

### Step 0.5 — Baseline

Establish the Definition of Done. Spawn a BASELINE-REVIEWER (read-only researcher):
"Run the verification suite end-to-end, paste output, report which DoD items are red. Do NOT fix anything. Do NOT trust prior summaries."

### Step 1 — Plan + state file
Chunk the work into IMPLEMENTER-sized units (a few files, one clear acceptance criterion each). Write the state file (`<session-dir>/04-progress.md` or `ORCHESTRATION_STATE.md` at repo root) with:
- DoD checklist (all required items, with status)
- Chunk plan (ordered)
- Current round
- Round history (append-only)
- Open questions for the user
- Notes

### Step 2 — Loop
Pick the next chunk. Dispatch IMPLEMENTER per `references/implementer-brief.template.md`. Wait. Dispatch a FRESH REVIEWER (different subagent invocation) per `references/reviewer-brief.template.md`. Adjudicate:
- **PASS** → mark chunk done, update state, next chunk.
- **FAIL** → new IMPLEMENTER (NOT the same agent) with the reviewer's findings verbatim in a `<prior_review_findings>` block. Re-review. **Hard-stop at iteration 3 of the same chunk** — surface to user.
- **ESCALATE** → open an OQ entry, surface to user, wait.

### Step 3 — Phase + final gates
When all chunks in a phase PASS, spawn a phase-exit REVIEWER (broader scope). When all phases PASS, spawn a final full-DoD REVIEWER. Only then write the closing report.

## Hard rules (every IMPLEMENTER and REVIEWER brief inherits these verbatim — they are non-negotiable)
See `references/hard-rules.md`.

## Templates
- Issue intake schema: `references/issue-intake.md`
- IMPLEMENTER brief: `references/implementer-brief.template.md`
- REVIEWER brief: `references/reviewer-brief.template.md`
- RESEARCHER / BASELINE-REVIEWER brief: `references/researcher-brief.template.md`
- Orchestration state file: `references/state-file.template.md`

## Reviewer anti-patterns checklist
`references/reviewer-antipatterns.md` — what to grep for when reviewing.

## Code-navigation discipline
`references/serena-discipline.md` — if Serena MCP is available, use it for symbol-aware navigation; if not, fall back to grep/Read and explicitly note "navigating blind."

## Parallelism
Dispatch implementers in parallel ONLY when the chunks have genuinely disjoint file ownership (no two chunks touch the same file). When in doubt, serial. Reviewers can always run after their implementer; do not parallelize the implementer–reviewer pair for the same chunk.

## Escalation
After 3 failed reviews for the same chunk:
1. Stop the loop.
2. Surface to the user a hard-stop message: diff of last attempt + last reviewer's findings + your assessment of root cause.
3. Wait for user direction.

## Resumability
If you run low on context mid-orchestration:
- Make the state file exact and complete (don't summarize — be specific about chunks done, in-flight, and pending).
- Never close out with red items still in the DoD.
- A future Claude session reads the state file + the skill and resumes.
