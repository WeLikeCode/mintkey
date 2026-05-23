# Issue Intake — Monorepo Structure Cleanup

**Session:** `2026-05-22-monorepo-structure-cleanup`
**Owner:** architect (CiprianSpot)
**Triggered:** 2026-05-22 by direct request to ORCHESTRATOR
**Driver:** remediation-orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → fresh REVIEWERs Opus → final reviewer)
**Branch:** `chore/monorepo-restructure-2026-05-22` (off `main @ 590cb78` / `v0.1.0-preview.1`)

---

## Original brief (verbatim, captured by ORCHESTRATOR)

> Mission: Restructure the monorepo for clarity without changing runtime behavior. Implement only these phases:
>
> 1. Archive completed remediation noise
> 2. Normalize deployable apps under `apps/`
> 3. Normalize shared packages under `packages/`
> 5. Group infra under `infra/`
> 6. Update docs, Kiro, CI, Makefile, and repo maps
>
> Do NOT implement phase 4 yet:
> - Do not promote/move canonical contracts in this pass.
> - Leave `docs/architecture/contracts/` as-is unless path references must be updated because of other moves.
>
> Core requirements:
> - Use Kiro / Spec-Driven Development before moving files.
> - Use the remediation-orchestrator pattern.
> - Every move must have an EvidenceRef.
> - Preserve behavior.
> - Do not edit accepted ADRs.
> - Do not delete history-bearing remediation records; archive/move only.
> - Do not run destructive commands without explicit owner approval.
> - Do not add `Co-Authored-By` trailers.

## Why now

The repo has accumulated layout debt over 6 weeks of rapid pre-alpha work:
- 11 deployable services at root (mixed: 7 at top level + 4 under `services/`)
- 44 dated remediation sessions under `team/remediation/`
- Observability config (prometheus.yml, alert_rules.yml, otel-collector-config.yaml, grafana/) sprawled at root
- Two compose files at root
- ~350 install logs at root (untracked, but visible noise to anyone running `ls`)
- New contributors / builders cannot orient quickly to find apps vs libs vs infra vs history.

## Scope

**In scope (this session):** Phases 1, 2, 3, 5, 6 — structural moves only.
**Out of scope (deferred):** Phase 4 (canonical contracts promotion). `tooling/` consolidation. Code/config refactoring.

## Success criteria

1. Repo root contains apps under `apps/`, packages under `packages/`, infra under `infra/`, sessions under `remediation/`.
2. `docker compose config`, `go test ./...`, `make help` all exit 0.
3. No runtime behavior change. `make demo` produces the same end-state.
4. Single PR with separate atomic commits per chunk.
5. Final reviewer PASS_ALL gate.

## Constraints (hard rules)

- **NO** accepted-ADR edits.
- **NO** real secrets in any committed artifact.
- **NO** `Co-Authored-By:` trailer.
- **NO** destructive volume operations.
- **NO** behavior changes — paths only.
- Every move must be `git mv` (history-preserving).

## Decision authority

- ORCHESTRATOR decides chunk decomposition, dispatch order, parallelism.
- IMPLEMENTERS execute the chunk; they do NOT make architectural decisions.
- Fresh REVIEWERS verify; they do NOT mutate state.
- Owner (architect) decides any item escalated to `03-escalations.md`.

## Reference docs

- `.kiro/specs/monorepo-structure-cleanup/{requirements,design,tasks,evidence}.md` — the spec.
- `00-plan.md` — high-level execution plan.
- `01-orchestrator-chunks.md` — per-chunk file ownership, DoD.
- `02-matrix.md` — live status matrix.
- `03-escalations.md` — open questions for owner.
- `04-progress.md` — running execution log.
- `99-report.md` — final report (filled at session close).
- `EVIDENCE_LEDGER.md` — per-move EvidenceRef.
