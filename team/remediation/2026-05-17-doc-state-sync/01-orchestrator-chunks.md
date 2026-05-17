# Doc-State Sync — Chunk Catalog

**Session:** `2026-05-17-doc-state-sync`
**Driver:** orchestrator pattern
**Phase 0:** ✅ baseline + Evidence Ledger built by ORCHESTRATOR (see `EVIDENCE_LEDGER.md`)

---

## Locked decisions

| Decision | Value | Source |
|---|---|---|
| Test-count language | Always "last verified by <report/date>" — never fresh-rerun claim | Owner intake + `EV-NO-FRESH-RERUN` |
| ADR file edits | Forbidden (immutable per ADR-0001). Only `adr/README.md` index is editable. | Intake + ADR-0001 |
| Untracked scaffolds | Acknowledge in `04-progress.md`; do not touch | `EV-WORKTREE-DIRTY` |
| Date stamp | `2026-05-17` (today; tag day) | Owner intake |
| Co-Authored-By | NONE on any commit | `~/.claude/CLAUDE.md` |

---

## Universal hard rules

- No `Co-Authored-By` trailer on any commit
- No `--no-verify`
- No edits to accepted ADRs (files `0001`–`0020`)
- No product code changes
- No claim of fresh test runs
- Atomic commits — one chunk per commit
- Validate via tools (`rg`, `python3 -c "yaml.safe_load(...)"`, `git diff --check`)
- Update `EVIDENCE_LEDGER.md` if a chunk adds new evidence
- Update `02-matrix.md` row(s) before commit

---

## Wave 0 — Orchestrator (this file + `EVIDENCE_LEDGER.md` + `02-matrix.md`)

C-1: **Implementation status inventory + Evidence Ledger**

- Owner: ORCHESTRATOR
- Status: ✅ done before Wave 1 dispatch
- Output: `ISSUE_INTAKE.md`, `00-plan.md`, `01-orchestrator-chunks.md`, `EVIDENCE_LEDGER.md`, `02-matrix.md`, `04-progress.md` scaffolded

Reviewer pass condition (per intake):
- Every planned update has an EvidenceRef.
- No implementation claim relies only on memory or interpretation.
- Verified: ledger covers all known stale claims across 5 in-scope docs.

---

## Wave 1 — parallel implementer chunks (disjoint files)

### C-2: PROGRESS + README sync + adr/README.md index entry for ADR-0018

| Field | Value |
|---|---|
| Owner files | `PROGRESS.md`, `README.md`, `docs/architecture/01-architecture/adr/README.md` |
| EvidenceRefs (primary) | `EV-PROGRESS-LAST-UPDATED`, `EV-PROGRESS-WS8-COUNTS`, `EV-README-ADR-COUNT`, `EV-README-TEST-COUNTS`, `EV-ADR-FILE-0018`, `EV-ADR-INDEX-0018`, `EV-TAG-PREALPHA`, `EV-GIT-LOG-100`, `EV-NO-FRESH-RERUN` |
| Reviewer pass | No stale phrase for May-17-fixed issues; status claims cite ledger; no unsupported "tests pass" |

Specific updates required (each must trace to an EvidenceRef):

- `PROGRESS.md:4` — bump `Last updated` to `2026-05-17`; reframe `All workstreams WS-7a through WS-8 complete` as the milestone snapshot at `WS-8 (2026-05-12)`; add a brief 2026-05-16 / 2026-05-17 remediation overview referencing 99-reports (no fresh test counts).
- `PROGRESS.md:8-19` — table `Last verified` column: leave dates as-is (they're already historical); ensure no row falsely implies present-tense freshness.
- `PROGRESS.md:78-94` — WS-8 verification block: annotate as "Final WS-8 verification snapshot (2026-05-12)" so reader doesn't read it as "current".
- `README.md:14-20` — status table: add a brief note that test counts reflect the WS-8 (2026-05-12) snapshot; OR replace counts with link to PROGRESS.md.
- `README.md:135` — `20 ADRs (18 accepted, ADR-0018 proposed)` → reconcile per `EV-ADR-INDEX-COUNT`. Cite ADR file dates if helpful.
- `README.md:7,170-172` — pre-alpha stability section: cross-reference `v0.1.0-prealpha` tag (`EV-TAG-PREALPHA`) if appropriate.
- `docs/architecture/01-architecture/adr/README.md:46` — ADR-0018 index entry: change `Proposed. ... Awaiting acceptance.` → `Accepted — 2026-05-11.` (cite `EV-ADR-FILE-0018`).
- `README.md:84` — container count claim — cross-check `EV-COMPOSE-SERVICES`; preserve if accurate.

### C-3: Roadmap sync

| Field | Value |
|---|---|
| Owner files | `docs/architecture/00-vision/06-roadmap.md` |
| EvidenceRefs | `EV-OTEL-FIX`, `EV-DOCKERFILE-USER`, `EV-DOCKERFILE-PIN`, `EV-INTEGRATION-TIMEOUT-FIX`, `EV-TAG-PREALPHA`, `EV-GIT-LOG-100` |
| Reviewer pass | Fixed items no longer listed as unresolved; genuine deferred items still present; every change maps to EvidenceRef |

Specific updates required:

- `06-roadmap.md` Section 3 row "otel-collector restart loop" — move from ⬜ Pre-existing → ✅ Fixed (cite `EV-OTEL-FIX`).
- Section 3 rows for Dockerfile USER (line ~89), HEALTHCHECK (~90), digest pinning (~91) — move from 🟦 Deferred → ✅ Done (cite `EV-DOCKERFILE-USER`, `EV-DOCKERFILE-PIN`).
- Section 1 / Section 7 "What is not yet in place" `10 Dockerfiles run as root; no HEALTHCHECK; base images pinned by tag not digest` (around line 32) — update per `EV-DOCKERFILE-USER` + `EV-DOCKERFILE-PIN`. Note: this is the public roadmap caveat, so be precise about the residual (e.g., long-running services were hardened; seed-job runs root by design for one-shot init per `EV-SEED-JOB-ROOT`).
- Section 8 Launch Milestones: if any milestone references these as gates, sync.
- Optionally annotate Section 1 "What is working today" with the v0.1.0-prealpha tag and the 22-PR cascade.

### C-4: Kiro readiness rewrite

| Field | Value |
|---|---|
| Owner files | `docs/architecture/00-vision/07-kiro-readiness.md` |
| EvidenceRefs | `EV-KIRO-READINESS-7`, `EV-KIRO-READINESS-STATUS`, `EV-KIRO-READINESS-PATHS`, `EV-CONTRACTS-PATH`, `EV-KIRO-SPECS-PATH`, `EV-KIRO-TASKS-DONE`, `EV-ADR-INDEX-COUNT` |
| Reviewer pass | No references to obsolete `docs/contracts` or `docs/specs/<component>` remain unless explicitly historical; no "7 accepted ADRs" stale counts; readiness statuses evidence-backed |

Specific updates required:

- Line 56: `ADRs (7 accepted)` → current count from `EV-ADR-INDEX-COUNT`; link to current `adr/README.md`.
- Lines 77-82 (Contract table): paths `/docs/contracts/rest/`, `/docs/contracts/mcp/`, `/docs/contracts/events/`, `/docs/contracts/` → `docs/architecture/contracts/{rest,mcp,events,...}` per `EV-CONTRACTS-PATH`. Status `⏳ Iteration 4` should reflect that OpenAPI etc. are CHECKED IN (per `EV-CONTRACTS-PATH` + the openapi.yaml file existing).
- Line 95: `docs/specs/<component>/` → `.kiro/specs/mintkey-mvp/` per `EV-KIRO-SPECS-PATH`.
- Lines 99-107 (per-component spec table): per `EV-KIRO-TASKS-DONE`, M1.0–M1.13 are all checked in `tasks.md`. Update statuses accordingly — but DO NOT claim "tests pass"; cite "tasks marked [x] in `.kiro/specs/mintkey-mvp/tasks.md` per `EV-KIRO-TASKS-DONE`".
- Lines 231-232 (Quality gates table): "Contract round-trip: Diff between OpenAPI emitted by FastAPI and `docs/contracts/rest/openapi.yaml`" → update path.
- Line 253-254 ("Kiro-specific scaffolding" template output): `docs/proposal/`, `docs/specs/<component>/`, `docs/contracts/` → current paths.
- Lines 267-280 ("Status as of 2026-05-10"): replace with `Status as of 2026-05-17` block; rewrite each row with `EV-*` backed status. Do NOT make up tool-CI evidence — for items like "linters in CI", cite `EV-CI-MAIN-GREEN` only if applicable.
- Line 274 fastest-path: similar reframing — what's actually shipped vs still gating.

### C-5: Remediation session hygiene

| Field | Value |
|---|---|
| Owner files | `team/remediation/2026-05-17-jaeger-cookie-b64/99-report.md`, `team/remediation/2026-05-17-jaeger-cookie-size/99-report.md`, `team/remediation/2026-05-17-jaeger-entrypoint-binary/99-report.md`, `team/remediation/2026-05-17-jaeger-secret-perms/99-report.md` |
| EvidenceRefs | `EV-PR52-COMMIT`, `EV-PR51-COMMIT`, `EV-PR50-COMMIT`, `EV-PR49-COMMIT`, `EV-JAEGER-*-REPORT`, `EV-GIT-LOG-100`, `EV-NO-FRESH-RERUN` |
| Reviewer pass | No template `<TODO>` / `<Session Title>` text in any of the 4 reports; cite PR/commit; mark verification as "not rerun in this session" where applicable |

Specific updates required, per file:

- `jaeger-cookie-b64/99-report.md` — rewrite with: session title `Jaeger Cookie Secret Base64`, status `CLOSED (merged via PR #52)`, summary referencing PR #52 commit `35369d0`, merge commit `54e8f9f`. Verification: cite the on-PR CI green check and the live integration in PR #53's session report; mark as "not freshly rerun in this doc-sync session" per `EV-NO-FRESH-RERUN`.
- `jaeger-cookie-size/99-report.md` — same pattern. Note PR #50 commit `e6c84fc` was an intermediate step in the cascade and was superseded by PR #51 (`--cookie-secret-file` attempt) then PR #52 (final base64 fix). Document the cascade history; status `CLOSED (superseded; see PRs #51 + #52 for final fix)`.
- `jaeger-entrypoint-binary/99-report.md` — PR #51 commit `abc80c4` introduced `--cookie-secret-file` flag (binary-safe attempt). oauth2-proxy v7.6.0 does NOT support that flag; superseded by PR #52. Status `CLOSED (superseded by PR #52)`.
- `jaeger-secret-perms/99-report.md` — PR #49 commit `6364923` — standalone fix (perms 0o600/0o640 → 0o644). Not superseded. Status `CLOSED`.

For each report:
- Start from the existing template skeleton; replace `<...>` placeholders with EvidenceRef-backed content.
- Use the same closing-report shape as `2026-05-17-otel-collector-config/99-report.md` (reference shape).
- Verification section MUST explicitly say "not rerun in this doc-sync session; relying on PR #N CI on commit <sha>" rather than copying verification text from elsewhere.

---

## Wave 2 — REVIEWER (Opus, fresh)

| # | Chunk | Reviewer task |
|---|---|---|
| REV-2 | C-2 | Run `rg` for stale phrases in PROGRESS.md + README.md + adr/README.md; confirm every diff line maps to an EvidenceRef row; assert no fresh-rerun claim added |
| REV-3 | C-3 | Same in 06-roadmap.md; specifically check otel-collector + 3 Dockerfile rows transitioned; deferred items still present |
| REV-4 | C-4 | Same in 07-kiro-readiness.md; specifically check no obsolete `docs/contracts` / `docs/specs/<component>` paths remain; ADR count current |
| REV-5 | C-5 | Confirm zero `<TODO>` / `<Session Title>` / `<YYYY-MM-DD-kebab-slug>` placeholders in the 4 in-scope reports; each report cites PR + commit |

PASS_ALL gate: only after all 4 sub-reviews pass does ORCHESTRATOR commit final 99-report and open PR.

---

## Status legend (`02-matrix.md`)

| Symbol | Meaning |
|---|---|
| ⬜ | Pending |
| 🔵 | Dispatched (in-flight) |
| ✅ | Reviewer PASS |
| ❌ | Reviewer FAIL — new implementer dispatched |
| 🛑 | Hard-stop — 3 failures; awaiting user |
| ⚠️ | Escalated — awaiting owner decision |
