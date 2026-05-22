# Plan — Monorepo Structure Cleanup

**Session:** `2026-05-22-monorepo-structure-cleanup`
**Branch:** `chore/monorepo-restructure-2026-05-22`

---

## Execution waves

```
Wave 0 (ORCHESTRATOR, this turn):
  C-0  Kiro spec + session + branch + baseline + commit

Wave 1 (parallel — disjoint files):
  C-1  Remediation archive          [IMPLEMENTER Sonnet]
  C-2  Apps move                    [IMPLEMENTER Sonnet]

Wave 1 review (parallel):
  C-1 fresh REVIEWER (Opus)
  C-2 fresh REVIEWER (Opus)

Wave 2 (parallel — gated on C-2):
  C-3  Packages move                [IMPLEMENTER Sonnet]
  C-4  Infra grouping               [IMPLEMENTER Sonnet]

Wave 2 review (parallel):
  C-3 fresh REVIEWER
  C-4 fresh REVIEWER

Wave 3 (serial — gated on C-2/C-3/C-4):
  C-5  Docs/Kiro/CI sweep           [IMPLEMENTER Sonnet]

Wave 3 review:
  C-5 fresh REVIEWER

Wave 4 (serial):
  C-6  Final fresh REVIEWER (full session audit, all chunks)
```

## Why this wave layout

- **C-1 and C-2 in parallel:** zero overlapping files. C-1 touches `team/remediation/` + `remediation/` + non-session refs to them. C-2 touches `apps/`, `services/`, `docker-compose*`, `Makefile`, `.github/workflows/`, `go.work`. No mutual writes.
- **C-3 and C-4 gated on C-2:** both need to know the new `apps/` paths (C-3 for Dockerfile COPY, C-4 for compose build contexts). C-3 and C-4 are otherwise independent — C-3 touches `packages/`, `mintkey-models/`, `internal/`, Go imports; C-4 touches `infra/`, compose, observability.
- **C-5 last:** needs all preceding paths settled to do the doc-sweep with high accuracy.
- **C-6 final:** full-session audit with stale-path scan, behavior preservation evidence.

## Per-chunk Definition of Done (summary; full DoD in `01-orchestrator-chunks.md`)

- **C-1:** 43 sessions moved to `remediation/archive/2026/05/`; `team/` empty or removed; non-historical refs updated.
- **C-2:** 11 apps moved to `apps/`; `services/` removed; `docker compose config` exits 0; `go.work` valid.
- **C-3:** 8 packages moved to `packages/{python,go}/`; `internal/` removed; `go test ./...` exits 0; `uv run pytest` exits 0 for mintkey-models.
- **C-4:** compose + observability moved to `infra/`; root compose shim works; `make demo` dry-run unchanged.
- **C-5:** docs + Kiro + CI + Makefile reflect new paths; stale-path scan returns only intentional/historical hits.
- **C-6:** PASS_ALL on all chunks; final report written; PR ready for owner merge.

## Failure handling

- If an IMPLEMENTER cannot complete the chunk, it MUST commit partial progress + write a "blocker" entry in `03-escalations.md` and tag ORCHESTRATOR.
- Per chunk: max 3 strikes. After strike-3 failure: hard stop, escalate to owner.
- If a fresh REVIEWER finds a FAIL: ORCHESTRATOR dispatches a strike-2 IMPLEMENTER with the specific issues. The strike-2 implementer SHALL only fix the flagged items, not re-do the entire chunk.
- If the strike-2 also FAILS: ORCHESTRATOR is in strike-3 territory and SHOULD escalate before strike-4.

## Branch + commit strategy

- One branch: `chore/monorepo-restructure-2026-05-22`.
- One commit per chunk (atomic, self-contained).
- Commit messages follow conventional commits:
  - `chore(repo): C-0 — Kiro spec + remediation session scaffold for monorepo-structure-cleanup`
  - `chore(repo): C-1 — archive 43 remediation sessions to remediation/archive/2026/05/`
  - `chore(repo): C-2 — move 11 deployable apps to apps/`
  - `chore(repo): C-3 — move shared packages to packages/{python,go}/`
  - `chore(repo): C-4 — group compose + observability under infra/`
  - `chore(repo): C-5 — sweep docs/Kiro/CI for stale paths`
  - `chore(repo): C-6 — final reviewer notes + 99-report close`
- No `Co-Authored-By` trailers.
- No `--no-verify`.

## Open dependencies

- Owner decision on `03-escalations.md` items before C-3 / C-4 commit:
  - E-1: `internal/cfg/` and `internal/models/` empty-dir disposition (default: delete; alternative: leave + keep aspirational).
  - E-2: `tooling/{scripts,ci,bootstrap,dev}/` consolidation: in scope or follow-up?
  - E-3: `realm-mintkey.json` location decision (CD-2 default: stay in `apps/seed-job/`).
  - E-4: Compose `include:` vs symlink for root shim (CD-1 default: `include:` if Compose ≥ v2.20, else symlink).
- Owner decision before C-1 commit:
  - E-5: `team/remediation/HOWTO-backup-before-reset.md` destination — `remediation/HOWTO-...` or `docs/operations/backup-before-reset.md`?
