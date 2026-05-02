---
name: assumption-validate
description: Drive an assumption from Open → Validated / Partially Validated / Invalidated. Forces evidence citation on every status change. Activate when the user says "validate assumption A-N", "is this still open", or "update the assumption register based on {meeting / decision / code}".
compatibility: Requires read/write access to the project's assumption-register.md. Pairs with risk-register-update (invalidated assumptions can cascade into risks).
metadata:
  author: kiro-project-template
  version: 0.2
---

## Instructions

You drive an assumption's status forward based on new evidence. You force the user to cite the evidence source on every status change. You refuse status updates that lack a citation.

## When to invoke

- "Validate assumption A-N"
- "Is A-N still open?"
- "Update the assumption register based on {meeting / decision / code}"

## When NOT to invoke

- It's actually a risk, not an assumption → use `risk-register-update`
- It's a decision now → use `adr-from-decision` or `decision-log-append`

## Inputs

- `register-path` (required)
- `assumption-id` (required)
- `evidence-source` (required: meeting date, commit, ticket, file)
- `new-status` — validated / partial / invalidated

## Template

The assumption register template lives in this skill's references directory:

#[[file:.kiro/skills/assumption-validate/references/assumption-register-template.md]]

## Workflow

1. Read assumption-id from register.
2. Require `evidence-source` — refuse to update without one.
3. For "validated": require source that confirms the assumption holds in the **production design**, not just a PoC.
4. For "invalidated": require source showing the assumption was wrong; trigger a flag if a downstream decision depended on it.
5. For "partial": specify which sub-claim validated and which is still open.
6. Update entry with: new-status / evidence / date / who-confirmed.
7. If invalidation cascades into ADR or risk implications, surface those — don't silently update.

## Output

- Diff of assumption register.
- Cascade-warning section if downstream ADRs / risks affected.

## Anti-patterns

- Marking validated without a citation.
- Validating against PoC code instead of production design.
- Hiding cascade impact when an assumption fails.
- Letting "feels validated" creep in without an artifact.
