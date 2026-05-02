# ADR-{{NNNN}}: {{Title}}

**Status:** Proposed | Accepted | Superseded by ADR-XXX | Deprecated
**Date:** {{YYYY-MM-DD}}
**Author:** {{Architect name}}
**Decision-maker:** {{Architect name}}
**Supersedes:** {{ADR-XXX or none}}
**Refines:** {{ADR-XXX or none}}

---

## Context

What is the situation that requires a decision? What forcing function exists? What constraints frame the decision?

Keep this to 3-6 sentences. Link to companion artifacts (architecture vision, prior ADRs, meeting notes) rather than restate them.

## Decision

State the decision in one sentence in **active voice, present tense**. "We adopt X for Y." NOT "We will adopt", NOT "We should adopt", NOT "We are considering".

## Why

The 2-4 reasons this decision wins. Each reason cites either a constraint, a quality attribute, or evidence (PoC result, benchmark, prior incident).

## Alternatives considered

| Alternative | Why not chosen |
|---|---|
| {{option}} | {{specific reason — perf gap, cost, lock-in, team-skill}} |

At least 2 alternatives. "No alternative considered" is a smell — find one.

## Consequences

What becomes easier? What becomes harder? What new commitments does this create?

- **Positive:** {{specific consequence}}
- **Negative:** {{specific consequence — be honest}}
- **Neutral:** {{trade-off the team accepts}}

## Spec / contract back-references

- {{contracts/openapi/...yaml}}
- {{.kiro/specs/<feature>/}}
- {{any prior ADR this directly affects}}

If no spec or contract back-reference exists, the ADR is decorative. Add one or downgrade to a decision-log entry.

## Tests asserting this decision

- {{tests/acceptance/...}}
- {{tests/contract/...}}

If the decision is testable behavior, list the tests. If it's not testable (e.g., "we adopt monorepo"), say so.

## Open questions

- {{questions the architect deferred}}

Tracked in `.kiro/steering/open-questions.md`.

---

> **House style:**
> - Use active voice, present tense.
> - Cap at 250-500 words excluding tables.
> - One ADR = one decision. If you have two decisions, write two ADRs.
> - Numbers are zero-padded (`ADR-0007`, not `ADR-7`).
> - Slug in filename matches H1 title in kebab-case.
