---
inclusion: manual
---

# {{ENGAGEMENT_NAME}} — Repo governance

> Branching, PR, review, release, and CI-gate rules. Loaded on demand for PR / review skills.

## Branching model

Selected at bootstrap (Q15): **(populated by wizard)**

[REQUIRES-UPDATE: if Trunk-based, document branch lifetime cap, feature-flag rules. If GitFlow, document `develop`/`main` flow. If GitHub Flow, document branch-protection.]

## Commit conventions

[REQUIRES-UPDATE: e.g., Conventional Commits, custom prefixes, ticket-ID requirements.]

## PR rules

- **Description template** required, including:
  - `Spec:` / `ADR:` / `Contract:` reference (per the spec-first-check rule)
  - Brief test plan
  - Linked issue / ticket
- **Reviewers**: per `CODEOWNERS`. Architect-only on `docs/architecture/` and `.kiro/steering/`.
- **CI must be green** before merge.
- **Squash-merge** by default; document any exceptions.

## CI gates

| Gate | When | Action |
|---|---|---|
| `lint` | Every PR | Block on error |
| `unit-tests` | Every PR | Block on failure |
| `contract-lint` | PR touching `contracts/` | Block on error |
| `vibe-check` | Every PR | Comment, do not block (initially) |
| `spec-trace` | Nightly | Comment-only |
| `coverage-vs-spec` | Every PR | Comment-only |
| `audit-steering` | PR touching `.kiro/steering/` | Block on error-level issues |

[REQUIRES-UPDATE: gate promotion to "block" can ratchet over time. The architect controls promotion.]

## Release process

[REQUIRES-UPDATE: e.g., release branches per release-branch-process.md, semver, calendar versioning.]

## Hotfix process

[REQUIRES-UPDATE: cherry-pick from main, never direct-to-release-branch.]

## Codeowners

See [`CODEOWNERS`](../../CODEOWNERS) for the current routing. Initially architect-only on architecture canon and steering. Expand as squads form (Q24).

## What does NOT belong here

- Specific CI provider syntax (those are in `.gitlab-ci.yml` / `.github/workflows/`)
- ADR rationale for branching choice (that's an ADR)
- Per-team ceremonies (those are in `docs/onboarding/lead.md` or equivalent)

## Cross-references

- ADR-NNN — branching model decision
- [`docs/onboarding/lead.md`](../../docs/onboarding/lead.md) — TL responsibilities
- [`tools/README.md`](../../tools/README.md) — audit / lint / vibe-check tooling
