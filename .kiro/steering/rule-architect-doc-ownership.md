# Rule: `docs/architecture/` is architect-owned

**Always-loaded protocol rule.** Auto-applies to every agent in this repository.

## The rule

Files under `docs/architecture/` (architecture vision, ADRs, risk register, assumption register, open questions, decision log) are **architect-owned**. Agents and developers MAY:

- Read these files freely
- Reference them in code, PRs, and other docs
- Suggest diffs as drafts in `team/{handle}/drafts/`

Agents and developers MUST NOT:

- Edit existing files in `docs/architecture/` directly
- Auto-apply suggestions from `adversarial-review` to existing architecture docs
- Move, rename, or delete files in `docs/architecture/`
- Create new ADRs without going through `adr-from-decision` (which drafts in `team/{handle}/drafts/`, not canon)

## Exception: adding new files

The architect — and only the architect — may add new files to `docs/architecture/`. New ADRs land via the architect's manual review of an `adr-from-decision` draft, not via direct agent write.

## Why

Architecture docs are the historical record of decisions. Silent edits destroy the audit trail. The architect's review gate forces every change to be deliberate.

If an agent finds an architecture doc that's stale, contradictory, or wrong, it should:
1. Flag the issue in chat with the specific location.
2. Propose a diff in `team/{handle}/drafts/`.
3. Wait for the architect to apply.

Never silently fix.
