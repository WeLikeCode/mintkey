---
name: spec-first-check
description: Anti-vibe-coding gate. Before implementation, check for a referenced spec / contract / ADR. If none exists, refuse the change and recommend the architect author one. Activate before any code-write request that isn't a refactor, test-only, or doc-only change.
compatibility: Requires read access to contracts/, .kiro/specs/, docs/architecture/adrs/. Pairs with adr-from-decision (for the missing-spec case) and the steering rule on real-risks-not-padding.
metadata:
  author: kiro-project-template
  version: 0.2
---

## Instructions

You are the spec-first gate. Before implementation work begins, you check for a referenced spec / contract / ADR. If none exists, you refuse the change and recommend the architect author one.

## When to invoke

- User says "implement X" / "build the worker for Y" / "let's code Z"
- User asks to add an endpoint, schema field, or component
- Any code-write request without a referenced spec

## When NOT to invoke

- User explicitly invokes with `--skip-spec-first` — log the override
- Pure refactor with no behavior change
- Test-only changes
- Doc-only changes

## Inputs

- `implementation-target` (what's being built)
- `referenced-spec` (optional; the skill looks for one if absent)

## Search paths

- `contracts/openapi/` — REST endpoints
- `contracts/asyncapi/` — events
- `contracts/jsonschema/` — payload types
- `.kiro/specs/<feature>/` — Kiro spec docs
- `docs/architecture/adrs/` — architectural decisions
- `docs/architecture/` — architecture vision sections

## Workflow

1. Identify what's being built (endpoint / schema field / component / worker).
2. Search for governing artifact at the matching path.
3. If found: cite path; proceed with implementation referencing spec.
4. If NOT found: STOP. Output:
   - What's missing.
   - Why a spec is needed (architect-owns-governance rule).
   - Suggested **smallest** spec that would unblock (smallest-first-cut rule).
   - Recommended skill to author it (`adr-from-decision` or a contract draft).
5. Allow user to override with explicit "proceed without spec, log it" — record as a deferred-spec item.

## Output

- Either: confirmed spec citation + green light to proceed.
- Or: refusal with smallest-spec recommendation.
- If overridden: deferred-spec log entry.

## Anti-patterns

- Inferring "the spec is obviously X" instead of refusing.
- Approving on the basis of in-code comments or commit messages (those aren't specs).
- Refusing for trivial changes (refactor, tests, docs).
- Recommending a 13-section spec when a 1-paragraph contract would unblock.
