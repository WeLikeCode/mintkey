# Chunk Status Matrix

**Session:** `2026-05-22-monorepo-structure-cleanup`
**Branch:** `chore/monorepo-restructure-2026-05-22`

| ID | Wave | Owner | Files | Tasks (kiro) | Impl | Reviewer | Commit |
|---|---|---|---|---|---|---|---|
| C-0 | 0 | ORCHESTRATOR | spec + session folder + branch | 0.1..0.6 | ✅ | n/a | e477369 |
| C-1 | 1 | IMPLEMENTER (Sonnet) | `team/remediation/`, `remediation/`, non-historical refs | 1.1..1.8, 5 | ✅ | ✅ | b9b3733 |
| C-2 | 1 | IMPLEMENTER (Sonnet) | 11 service dirs, `apps/`, `services/`, compose, Makefile, workflows, go.work | 2.1..2.12, 12 | ✅ | ✅ | ce3870d + 188c870 |
| C-3 | 2 | IMPLEMENTER (Sonnet) | `mintkey-models/`, `internal/`, `packages/`, Go imports, pyproject | 3.1..3.12 | ✅ | ⬜ pending | _pending_ |
| C-4 | 2 | IMPLEMENTER (Sonnet) | `docker-compose*`, observability files, `grafana/`, `infra/`, scripts | 4.1..4.11 | ⬜ pending (gated on C-2) | ⬜ pending | _pending_ |
| C-5 | 3 | IMPLEMENTER (Sonnet) | README/KIRO/AGENTS/CLAUDE/docs/.kiro/.github/CODEOWNERS/Makefile | 6.1..6.12 | ⬜ pending (gated on C-2/C-3/C-4) | ⬜ pending | _pending_ |
| C-6 | 4 | REVIEWER (Opus, fresh) | full session audit | 17 | n/a | ⬜ pending | _no commits_ |

## Legend
| Symbol | Meaning |
|---|---|
| ⬜ | Pending |
| 🔵 | In flight |
| ✅ | PASS |
| ❌ | FAIL — re-dispatched |
| 🛑 | Hard-stop |
| ↻ | Strike-N retry |

## Strike counter (per chunk)

| Chunk | Strikes used | Max | Status |
|---|---|---|---|
| C-1 | 0 | 3 | ok |
| C-2 | 0 | 3 | ok |
| C-3 | 0 | 3 | ok |
| C-4 | 0 | 3 | ok |
| C-5 | 0 | 3 | ok |
| C-6 | 0 | 3 | ok (review-only) |
