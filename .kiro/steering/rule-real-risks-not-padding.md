# Rule: Real risks, no padding

**Always-loaded protocol rule.**

## The rule

Every entry in `docs/architecture/risk-register.md` MUST answer three questions:

1. **What specifically breaks?** — A concrete failure mode, not a category.
2. **What evidence shows it's real?** — A citation to a meeting, commit, ticket, code line, or operational incident.
3. **Which decision or component depends on this?** — A named architectural choice or component the risk threatens.

If any answer is missing, the entry is padding. Reject.

## Reject these as padding

- Generic platform concerns (data sovereignty, container access, terminology drift) — these are operational considerations, not risks.
- Speculative "could potentially happen in some configuration" entries.
- Citations of prototype / PoC code as evidence the production architecture has the same flaw.
- Stakeholder clarification questions — those go to Open Decisions, not Risks.
- Risks invented by `adversarial-review` subagents to look thorough.

## Why

A 50-entry risk register that's 80% padding is invisible. A 12-entry register that's 100% real is actionable. Stakeholders read short, evidenced lists.

When the user is reviewing a risk register, surface this rule explicitly. Reject additions that fail the three-question test even if the user appears to want them. The user has explicitly opted into this discipline at template bootstrap.

## Application

The `risk-register-update` skill enforces this rule programmatically. The `adversarial-review` skill discards padding findings during synthesis. When in doubt, ask the architect: "Does this risk pass the three-question test?"
