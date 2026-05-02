# Architecture documentation

> **⚠️ Architect-owned. ADD-only for non-architects.** See [`.kiro/steering/rule-architect-doc-ownership.md`](../../.kiro/steering/rule-architect-doc-ownership.md).

This directory holds:

| File / Dir | Purpose | How to update |
|---|---|---|
| [`architecture-vision.md`](architecture-vision.md) | System-level intent — what we're building and why | Architect edits directly |
| [`adrs/`](adrs/) | Architecture Decision Records (ADR-NNNN) | `/adr-from-decision` drafts; architect applies |
| [`risk-register.md`](risk-register.md) | Active risks, evidence-based | `/risk-register-update` |
| [`assumption-register.md`](assumption-register.md) | Open / partially / validated assumptions | `/assumption-validate` |
| [`open-questions.md`](open-questions.md) | Unresolved decisions, owner + due date | Architect edits |
| [`decision-log.md`](decision-log.md) | Lighter-weight running log | `/decision-log-append` |
| [`diagrams/`](diagrams/) | Mermaid sources + rendered PNGs | Architect maintains |

## Rules

1. **Read freely.** Anyone on the team can read these docs.
2. **Reference freely.** PRs, code, and other docs SHOULD cite ADRs by number.
3. **Edit only via architect.** Non-architects suggest diffs in `team/{handle}/drafts/` and ping the architect.
4. **No silent fixes.** If you find a stale or wrong doc, flag the location to the architect — don't auto-fix.
5. **ADRs are immutable once Accepted.** Reverse a decision by writing a new ADR with `Supersedes: ADR-NNN`.
6. **Decision-log is lighter than ADR.** ≤ 80 words per entry. Promote to ADR if architectural cascade emerges.

## Cadence guidance

- **ADR rate target**: 1-3 per sprint in early phases, 0-1 per sprint at steady state. > 5 per sprint = ADR overload — fold smaller ones into the decision log.
- **Risk register review**: end of each sprint, or whenever new evidence lands.
- **Assumption register review**: end of each sprint; before any major milestone.
- **Open questions review**: weekly, by the architect.

## What does NOT belong here

- Implementation details (those live in code or `.kiro/specs/`)
- Conventions / coding rules (those are steering files)
- Sprint plans or task lists (those live in your project management tool)
- Meeting notes (those live in `.claude/memory/meetings/` or equivalent — distill into ADR / risk / assumption / open-question if architectural)

---

*This directory is loaded `manual` mode for agents — never auto-read. Cite specific files when needed.*
