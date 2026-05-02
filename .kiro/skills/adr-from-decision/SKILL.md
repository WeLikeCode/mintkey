---
name: adr-from-decision
description: Author an ADR draft from a decision source (memory note, meeting, commit, ticket). Drafts only; never syncs to canon. Activate when the user says "write ADR for X", "promote {memory-path} to an ADR", or "capture {decision} as ADR-NNN".
compatibility: Requires read access to docs/architecture/adrs/ for next-number resolution. Drafts land in team/{handle}/drafts/, never in the canon directory directly.
metadata:
  author: kiro-project-template
  version: 0.2
---

## Instructions

You author an ADR draft from a decision source. **Draft only — never sync to canon.** Place the draft in `team/{handle}/drafts/`. The architect reviews and `git mv`s to canon.

## When to invoke

- "Write ADR for {decision}"
- "Promote {memory-path} to an ADR"
- "Capture {decision} as ADR-NNN"

## When NOT to invoke

- Decision not yet made → use `architecture-advisor` or `think-tiger` first
- Light note, no consequences yet → use `decision-log-append`
- Reversing an existing ADR → use this skill, but specify "supersedes ADR-X"

## Inputs

- `decision-topic` OR `source-memory-path` (required)
- `adr-number` (optional; auto-pick next sequential)
- `relationship` — refines / supersedes / standalone

## Template

The ADR template lives in this skill's references directory and is loaded inline when this skill activates:

#[[file:.kiro/skills/adr-from-decision/references/adr-template.md]]

## Workflow

1. Resolve next ADR number from `docs/architecture/adrs/` listing.
2. Read source material (memory, meeting note, commit, ticket).
3. Cross-reference existing ADRs; identify refines / supersedes relationships.
4. Draft in **active voice, present tense** — "we adopt" not "we should".
5. Place draft ONLY in `team/{handle}/drafts/` (never canon).
6. Surface suggested-diffs for canon placement, README updates, mirror locations — do not apply.
7. Default decision-maker / owner to the **project architect** (per the architect-owns-governance steering rule).

## Output

- Draft `adr-NNNN-slug.md` in `team/{handle}/drafts/`.
- Chat: suggested `cp` / `git mv` commands for the architect to apply manually.

## Anti-patterns

- Writing directly to `docs/architecture/adrs/` or any client-facing location.
- Hedging language ("we should consider", "we might").
- More than 500 words (loses signal).
- Number collision with existing ADRs.
- Assigning decision-maker to a developer or TL when the decision is architectural.
