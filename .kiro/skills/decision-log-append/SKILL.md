---
name: decision-log-append
description: Append a lightweight decision entry (≤80 words) to the project decision log. Use when a full ADR is overkill but the decision should not be lost. Activate when the user says "log this decision", "note this for later", or "add to the decision log".
compatibility: Requires read/write access to docs/architecture/decision-log.md. Promotes to adr-from-decision when the entry has architectural cascade.
metadata:
  author: kiro-project-template
  version: 0.2
---

## Instructions

You append a lightweight decision entry (≤ 80 words) to `docs/architecture/decision-log.md`. You do NOT write ADRs (use `adr-from-decision` for those).

## When to invoke

- "Log this decision"
- "Note this for later"
- "Add to the decision log"
- Quick decisions in chat that have downstream effects but don't warrant 500 words

## When NOT to invoke

- Decision has architectural consequences → use `adr-from-decision`
- It's actually a risk or assumption → use those skills
- It's a meeting note → use `meeting-notes-distill` (if present)

## Inputs

- `decision-statement` (required)
- `context` — one sentence — why this came up
- `source` — chat / meeting / commit / ticket

## Workflow

1. Append entry: date / decision (one sentence) / context / source / decision-maker (default: architect).
2. Cross-check existing entries — if it contradicts a prior entry, flag and link.
3. If the decision touches a known ADR topic, surface: "this looks promotable to ADR-NNN — want me to draft it?"
4. Default decision-maker to **architect** (per the architect-owns-governance steering rule).

## Output

- One-line append to `docs/architecture/decision-log.md`.
- Optional ADR-promotion offer.

## Anti-patterns

- Letting the entry bloat into a mini-ADR.
- Silent contradiction with prior entries.
- Assigning decision-maker to a developer for an architectural call.
