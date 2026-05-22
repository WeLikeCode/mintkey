# Doc-State Sync — Session Plan

**Session:** `2026-05-17-doc-state-sync`
**Branch:** `fix/doc-state-sync-2026-05-17` (from main @ `5f397b7`)
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)

## Mission

Reconcile public-docs claims with the implementation that actually landed on main between 2026-05-16 and 2026-05-17 (PRs #33 through #53; tag `v0.1.0-prealpha`). Pure documentation remediation; **no claim updated without an `EvidenceRef`**.

## Approach

`EVIDENCE_LEDGER.md` is the bus. Every change in every chunk references at least one `EvidenceRef` row. Reviewer cross-checks the ledger.

## Hard rules (every chunk)

- No `Co-Authored-By` trailer (per `~/.claude/CLAUDE.md`).
- No `--no-verify`.
- No edits to accepted ADRs (`docs/architecture/01-architecture/adr/00*-*.md` files themselves; only the index `adr/README.md` may be touched per scope).
- No product code changes.
- No claim of fresh test runs — always use `last verified by <report/date>`.
- Surgical edits — preserve formatting, headings, link structures wherever possible.
- Atomic commits per chunk; one chunk per commit.
- `EVIDENCE_LEDGER.md` must be updated by EVERY chunk that adds new evidence.
- Pre-existing untracked scaffolding in `team/remediation/2026-05-17-{accept-fakerow,mintkey-models-python-env,seed-job-idempotency-and-sso,jaeger-cookie-size,jaeger-entrypoint-binary,jaeger-secret-perms}/` is out of scope for this PR (4 of these reports ARE in scope; the rest stay untouched).

## Chunks

| # | Wave | Chunk | Owner files |
|---|---|---|---|
| C-1 | 0 (orchestrator) | Implementation status inventory + Evidence Ledger | `EVIDENCE_LEDGER.md`, `02-matrix.md`, `04-progress.md` |
| C-2 | 1 (parallel) | PROGRESS + README sync | `PROGRESS.md`, `README.md` |
| C-3 | 1 (parallel) | Roadmap sync | `docs/architecture/00-vision/06-roadmap.md` |
| C-4 | 1 (parallel) | Kiro readiness rewrite | `docs/architecture/00-vision/07-kiro-readiness.md` |
| C-5 | 1 (parallel) | Remediation session hygiene — 4 placeholder 99-reports | `team/remediation/2026-05-17-jaeger-{cookie-b64,cookie-size,entrypoint-binary,secret-perms}/99-report.md` |
| (also) | 1 | ADR index entry fix | `docs/architecture/01-architecture/adr/README.md` (assigned to C-2 since it's a 1-line index correction adjacent to README work) |

Wave 1: C-2, C-3, C-4, C-5 dispatched in parallel — disjoint file ownership.
Wave 2: REVIEWER (Opus, fresh) per chunk; PASS_ALL gate.
Wave 3: orchestrator commits + opens PR.

## Per-chunk reviewer pass conditions (verbatim from intake)

### C-2 review
- No stale phrase remains for known fixed May 17 issues.
- Status claims cite evidence in the ledger.
- No unsupported "tests pass" language.

### C-3 review
- Fixed items are no longer listed as unresolved.
- Deferred items are still present if not fixed.
- Every changed roadmap claim maps to EvidenceRef.

### C-4 review
- No references to obsolete `docs/contracts` or `docs/specs/<component>` remain unless explicitly historical.
- No "7 accepted ADRs" style stale counts remain.
- Readiness statuses are evidence-backed.

### C-5 review
- No closing report for a merged May 17 fix remains as untouched template text.
- Any remaining template placeholders are either outside scope or explicitly justified.

## 3-strike hard-stop

Per chunk, if 3 successive REVIEWER passes return FAIL, the chunk is hard-stopped; `03-escalations.md` records the blocker and the chunk is left in its current state (no merge).

## Closing acceptance criteria

- All 5 verification commands from intake `Verification target` exit clean (or with intentional, justified residuals documented in `99-report.md`).
- `99-report.md` lists files changed + EvidenceRefs used per chunk.
- Residual risks enumerated.
- Whether any implementation claim is not freshly reverified is called out explicitly.

## Untracked-state acknowledgment (per orchestrator rule)

Worktree at session start contained ?? entries from earlier conversation turns (incomplete scaffolds in 6 sibling 2026-05-17-* dirs). These belong to closed sessions whose merged commits are already on main; the untracked artifacts are abandoned local placeholders, not active user work. Per the orchestrator rule "If there are staged or unstaged changes you did not make, do not overwrite them" — these ARE my own prior artifacts, but to be conservative I will not touch them in this PR. They are recorded in `04-progress.md`.
