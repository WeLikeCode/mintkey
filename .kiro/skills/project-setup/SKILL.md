---
name: project-setup
description: Reentrant onboarding wizard for new projects. Walks the architect through the 25 bootstrap questions in phases, writes the three mandatory steering files (product.md, structure.md, architecture-principles.md), and tracks progress in .kiro/setup-state.json. Safe to re-invoke — resumes from last completed phase or exits if already done.
compatibility: Requires write access to .kiro/steering/ and docs/architecture/. Reads bootstrap/questionnaire.md as the canonical question source.
metadata:
  author: kiro-project-template
  version: 0.1
---

## When to invoke

- A new contributor opens the repo and no `.kiro/setup-state.json` exists
- The architect says "set up this project", "run the onboarding wizard", "bootstrap the project"
- Re-invoked mid-setup to resume from where it stopped

## When NOT to invoke

- `.kiro/setup-state.json` exists with `completed: true` → tell the architect the project is already set up and show a summary of what was generated. Offer `--force` to re-run.
- The user is not the architect → redirect: "This skill is for the architect of record. If you are a developer, read docs/onboarding/ for your role track."

## Reentrant guard (ALWAYS check first)

```
1. Read .kiro/setup-state.json (if it exists).
2. If completed == true → print summary, exit. Do NOT re-run unless --force is passed.
3. If file exists but completed == false → resume from the first phase where done == false.
4. If file does not exist → start from phase: identity.
```

## Question source

The canonical questions live in `bootstrap/questionnaire.md`. Load that file at skill start. Do NOT paraphrase or reorder questions. Q1-Q16 and Q25 are mandatory. Q17-Q24 are optional (ask them after mandatory phases complete).

#[[file:bootstrap/questionnaire.md]]

## Phases

Run phases in order. After each phase completes, write the updated state to `.kiro/setup-state.json` before proceeding. This makes every phase checkpoint resumable.

### Phase 1 — Identity (Q1, Q2, Q4)
Questions: project codename, client/sponsoring org, architect of record.

Refusals (per questionnaire.md):
- Q1 blank or contains the client name from Q2 → refuse, re-ask
- Q4 missing recognisable email or answered "TBD" → refuse, re-ask

### Phase 2 — Product (Q3, Q5, Q6)
Questions: business goal, engagement phase, regulated industry.

Refusals:
- Q3 shorter than 120 characters → refuse, re-ask
- Q3 matches platitude denylist (`transform the business`, `leverage AI`, `drive value`, `synergy`, `next generation`, `digital transformation`, `unlock potential`, `enable scale`) → refuse, re-ask with explanation

### Phase 3 — Architecture (Q7–Q14, Q16)
Questions: tenancy model, deployment target, backend language(s), frontend, persistence, API contract format, AI/ML, eventing, steering depth.

Handling deferrals:
- Q14 "broker not chosen" → log as open question, do not bake a tech choice
- Q16 = Skeleton → generate only the three mandatory steering files; skip optional ones

### Phase 4 — Governance (Q15, Q25)
Questions: branching model, top three business risks.

Refusals:
- Q25 fewer than 3 entries → refuse, re-ask
- Any Q25 entry missing `what breaks` or `evidence` → refuse that entry, re-ask for it specifically

### Phase 5 — Team / optional (Q17–Q24)
Ask each optional question. Accept "skip" or "defer" as valid answers — log deferred answers to `open-questions.md`.

## Output — what the skill writes

After all mandatory phases complete, write these files. Only write files justified by the answers (per Q16 steering depth and Q10/Q11/Q13 flags):

| File | Condition |
|---|---|
| `.kiro/steering/product.md` | Always |
| `.kiro/steering/structure.md` | Always |
| `.kiro/steering/architecture-principles.md` | Always |
| `.kiro/steering/tech.md` | Q16 ≠ Skeleton |
| `.kiro/steering/security-and-tenancy.md` stub | Q6 ≠ No OR Q7 ≠ Single-tenant |
| `.kiro/steering/data-lifecycle-and-idempotency.md` stub | Q13 ≠ No |
| `.kiro/steering/frontend-conventions.md` stub | Q10 ≠ None |
| `docs/architecture/risk-register.md` | Always (seeded from Q25) |
| `docs/architecture/open-questions.md` | Always (seeded from deferred answers) |
| `.kiro/setup-state.json` | Always (final state, completed: true) |

Templates for the three mandatory steering files:

#[[file:.kiro/skills/project-setup/references/product-template.md]]
#[[file:.kiro/skills/project-setup/references/structure-template.md]]
#[[file:.kiro/skills/project-setup/references/principles-template.md]]

State schema:

#[[file:.kiro/skills/project-setup/references/setup-state-schema.json]]

## Workflow

1. **Reentrant check** — read `.kiro/setup-state.json`; exit if `completed: true` (unless `--force`).
2. **Load questionnaire** — read `bootstrap/questionnaire.md`.
3. **Run phases 1–4** in order, one question at a time. After each phase, checkpoint state.
4. **Run phase 5** (optional questions). Accept skips.
5. **Validate all mandatory answers** against refusal rules before writing any file.
6. **Write output files** — only those justified by answers. Fill templates from answers; no placeholder values left in written files.
7. **Write `.kiro/setup-state.json`** with `completed: true`.
8. **Print summary**: files written (with paths), files skipped (with reason), open questions logged, next recommended action.

## Conversation style

- Ask one phase at a time, not all 25 questions at once.
- Show the architect which phase they are in: `[Phase 2/5 — Product]`.
- On refusal, explain exactly which rule was violated and what a valid answer looks like.
- After each phase, confirm answers before proceeding: "Here's what I captured for Phase 2 — confirm or correct."
- Never invent answers. Never pre-fill with placeholder names (no "Acme Corp", "John Doe", "example@example.com").
- If the architect is unsure, offer `architecture-advisor` for trade-off questions or `think-tiger` to stress-test a direction.

## Anti-patterns

- Writing all 22+ steering files regardless of answers.
- Leaving `{{PLACEHOLDER}}` tokens in any written file.
- Baking a tech choice that was answered "defer" or "not chosen".
- Assigning governance ownership to a developer or TL.
- Generating risks beyond Q25 answers.
- Writing directly to `docs/architecture/` for anything other than the seeded registers (those are the architect's initial act, not a draft).
- Skipping the reentrant check.
