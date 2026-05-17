# Issue Intake — 2026-05-17-doc-state-sync

**Session:** `team/remediation/2026-05-17-doc-state-sync/`
**Branch:** `fix/doc-state-sync-2026-05-17` (from main @ `5f397b7`)
**Reported:** 2026-05-17
**Reporter:** Owner — "Reconcile Mintkey's implementation-state and public documentation so README, PROGRESS, roadmap, Kiro readiness, and remediation session records accurately reflect the current implementation on main."

## Problem statement (required)

Documentation on `main` has drifted away from the actual implementation after the 22-PR cascade landed between 2026-05-16 and 2026-05-17. Specifically:

- `PROGRESS.md` `Last updated: 2026-05-16` and all test counts/headers are from 2026-05-12 (`WS-7a` … `WS-8`); no mention of any work after the OSS-readiness session.
- `README.md` status table claims `Unit tests 244 passing`, `Architecture tests 17 passing`, `Go package tests 23 packages green`, all dated 2026-05-12. The repo map says `20 ADRs (18 accepted, ADR-0018 proposed)` even though ADR-0018 itself says `Accepted — 2026-05-11`. The Run-it-locally section claims `15 long-running containers and 2 one-shot jobs`.
- `docs/architecture/00-vision/06-roadmap.md` Section 3 still flags `otel-collector restart loop` as pre-existing/unresolved and Dockerfile USER/HEALTHCHECK/digest-pinning as Deferred — all three classes were closed in PRs #33/#35/#47/#48.
- `docs/architecture/00-vision/07-kiro-readiness.md` says `ADRs (7 accepted)` and references obsolete `docs/contracts/...` / `docs/specs/<component>/` paths; the canonical paths are `docs/architecture/contracts/...` and `.kiro/specs/mintkey-mvp/...`. Status block is dated 2026-05-10.
- `docs/architecture/01-architecture/adr/README.md` Index line 46 still says `0018-classical-service-api-keys.md — Proposed`. The ADR file itself reads `Accepted — 2026-05-11`.
- 4 closed-on-main 2026-05-17 sessions still have placeholder `99-report.md` (template `<TODO>` / `<Session Title>` text): `jaeger-cookie-b64`, `jaeger-cookie-size`, `jaeger-entrypoint-binary`, `jaeger-secret-perms`.

## User-visible symptom (required)

- A new contributor reading `README.md` + `PROGRESS.md` cannot tell what's actually merged or running. The status table claims test counts from a build that was 5+ days old at the time of the v0.1.0-prealpha tag.
- A reader of `kiro-readiness.md` is sent to non-existent paths (`/docs/contracts/...`, `docs/specs/<component>/...`).
- A reader of the public roadmap thinks the otel-collector restart loop is still open.
- The `adr/README.md` index contradicts ADR-0018's own header.

## Expected behavior (required)

- Every claim in the four public docs (`README.md`, `PROGRESS.md`, roadmap, kiro-readiness) is either current, or explicitly labelled `last verified by <report/date>` when not freshly re-run.
- The ADR index agrees with the ADR file headers.
- Closed remediation reports for merged PRs (#43–#52) carry real verification evidence (commit SHA + PR # + the verification commands that the session actually ran), not template placeholders.
- Every doc change is traceable via an `EvidenceRef` in `EVIDENCE_LEDGER.md`.

## Evidence (required)

Baseline survey 2026-05-17 (this session's worktree):

- `EV-GIT-HEAD`: `git log --oneline -1` → `5f397b7 (HEAD -> main, tag: v0.1.0-prealpha, origin/main) Merge pull request #53` — 60+ commits past PROGRESS's last-mentioned 2026-05-12 state.
- `EV-README-ADR-0018`: `README.md:135` — `20 ADRs (18 accepted, ADR-0018 proposed)`.
- `EV-ADR-FILE-0018`: `docs/architecture/01-architecture/adr/0018-classical-service-api-keys.md:3-4` — `Accepted — 2026-05-11`.
- `EV-ADR-INDEX-0018`: `docs/architecture/01-architecture/adr/README.md:46` — `0018-classical-service-api-keys.md — Proposed. ... Awaiting acceptance.`
- `EV-ADR-INDEX-0020`: `docs/architecture/01-architecture/adr/README.md:48` — ADR-0020 entry already shows `Accepted — 2026-05-15`. Index counts ADRs 0001–0020 (20 entries).
- `EV-KIRO-READINESS-7`: `docs/architecture/00-vision/07-kiro-readiness.md:56` — `ADRs (7 accepted)`.
- `EV-KIRO-READINESS-STATUS`: `docs/architecture/00-vision/07-kiro-readiness.md:267-280` — `Status (as of 2026-05-10)` block lists `7 accepted (ADR-0001..0007)`.
- `EV-KIRO-READINESS-PATHS`: `docs/architecture/00-vision/07-kiro-readiness.md:77-82,95,231` — references `docs/contracts/rest/`, `docs/specs/<component>/`, `docs/contracts/...`.
- `EV-KIRO-TASKS-DONE`: `.kiro/specs/mintkey-mvp/tasks.md` — 14 top-level milestones M1.0 … M1.13 ALL marked `[x]`; 0 unchecked items across 99 task lines.
- `EV-ROADMAP-OTEL`: `docs/architecture/00-vision/06-roadmap.md:96` — `otel-collector restart loop | Observability reliability | ⬜ Pre-existing; unrelated to OSS work`.
- `EV-ROADMAP-DOCKER`: `docs/architecture/00-vision/06-roadmap.md:89-91` — `Dockerfile USER directive`, `Dockerfile HEALTHCHECK`, `Base image @sha256 digest pinning` all marked `🟦 Deferred`.
- `EV-OTEL-FIX`: `team/remediation/2026-05-17-otel-collector-config/99-report.md` — status `CLOSED`, PR #48 merged 2026-05-17.
- `EV-DOCKERFILE-PIN`: PR #35 commit `373221f` (`fix(ci): SHA-pin all Dockerfile FROM directives`) — 15 FROMs SHA-pinned across 10 Dockerfiles; PR #33 (REL-3) added `USER` + `HEALTHCHECK` to 6 Dockerfiles.
- `EV-SEED-JOB-PERMS`: PR #47 + PR #49 + PR #53 closed seed-job + jaeger-auth bootstrap-volume permissions; sessions `2026-05-17-seed-job-perms`, `2026-05-17-jaeger-secret-perms`, `2026-05-17-seed-job-idempotency-and-sso` all CLOSED.
- `EV-INTEGRATION-TIMEOUT`: PR #46 commit `e7b5e36` split docker-compose build/start; session `2026-05-17-integration-tests-timeout/99-report.md` status `CLOSED`.
- `EV-JAEGER-COOKIE-B64-PLACEHOLDER`: `team/remediation/2026-05-17-jaeger-cookie-b64/99-report.md` — `# <Session Title> — Closing Report` + `<TODO: CLOSED | CLOSED-WITH-RESIDUALS | HARD-STOP>` template text.
- `EV-JAEGER-COOKIE-SIZE-PLACEHOLDER`, `EV-JAEGER-ENTRYPOINT-BINARY-PLACEHOLDER`, `EV-JAEGER-SECRET-PERMS-PLACEHOLDER`: same template text in those 3 sibling sessions.
- `EV-PROGRESS-WS8`: `PROGRESS.md:78-94` — final verification dated 2026-05-12; numbers (244, 17, 23, 139) reflect the WS-8 commit, not main HEAD.
- `EV-PROGRESS-LAST-UPDATED`: `PROGRESS.md:4` — `Last updated: 2026-05-16` while git log shows merges through 2026-05-17.

## Scope (required)

May be changed:
- `PROGRESS.md`
- `README.md`
- `docs/architecture/00-vision/06-roadmap.md`
- `docs/architecture/00-vision/07-kiro-readiness.md`
- `docs/architecture/01-architecture/adr/README.md` (index entries only — NOT the ADR files themselves)
- `team/remediation/2026-05-17-jaeger-cookie-b64/99-report.md` and the 3 sibling placeholder reports (`jaeger-cookie-size`, `jaeger-entrypoint-binary`, `jaeger-secret-perms`) only as required to remove template `<TODO>` text per closing-report standard.
- Session folder + `EVIDENCE_LEDGER.md` (this session's own files).

## Out of scope (required)

- Accepted ADR files (`0001`–`0020`) — immutable per ADR-0001. If an ADR inconsistency is found, document it as escalation.
- Product code (`admin-api/`, `mcp-server/`, `services/`, etc.). No code change unless a doc-validation script is broken.
- Other docs (`CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `docs/architecture/01-architecture/` body, etc.) — out of stated chunk scope.
- Pre-existing untracked files in `team/remediation/2026-05-17-*/` from earlier conversation turns. These are template placeholders that I left behind in earlier sessions but never committed; I will not absorb them or modify them in this PR unless a chunk explicitly targets them (the 4 jaeger sessions are the only ones in scope).
- Re-running the full test suite. No claim of fresh test runs will be added; we cite the source-of-truth (commit SHA + 99-report).

## Risk level (required)

- **Doc correctness**: high positive — closes the trust gap between public docs and the v0.1.0-prealpha tag.
- **Behavior regression**: 0 — pure doc edits.
- **Information disclosure**: low — every claim added is already in `team/remediation/*/99-report.md` (already on main) or in commit messages (public on github.com).

## Verification target (required)

After each chunk + at session close:

1. `git status --short --branch` — clean except this session's intended changes.
2. `git diff --check` — no whitespace errors.
3. `rg -n "7 accepted|docs/contracts|docs/specs/<component>|docs/specs/<container>|ADR-0018 proposed|otel-collector.*Pre-existing|<TODO>|<Session Title>|<YYYY-MM-DD|244 passing|17 passing|23 packages|139 admin-ui" PROGRESS.md README.md docs/architecture/00-vision/06-roadmap.md docs/architecture/00-vision/07-kiro-readiness.md docs/architecture/01-architecture/adr/README.md team/remediation/2026-05-17-jaeger-{cookie-b64,cookie-size,entrypoint-binary,secret-perms}/99-report.md` — every remaining hit must be either:
   - Inside a code-fence and clearly historical, OR
   - Annotated with `last verified by <report/date>` or similar evidence-trace.
4. Every line changed in the 5 in-scope public docs traces to at least one `EvidenceRef` in `EVIDENCE_LEDGER.md`.

## Owner decisions

- ✅ **Approach**: orchestrator pattern per intake. Each chunk has disjoint file ownership.
- ✅ **Test-count language**: NEVER claim a freshly rerun count. Always cite `last verified by <session>/<commit>/<date>`.
- ✅ **ADR-0018 index fix**: update `adr/README.md` index entry only (it currently contradicts the ADR file). Do not edit the ADR itself.
- ✅ **Untracked scaffolding artifacts** (`team/remediation/2026-05-17-*/` minus the 4 jaeger ones): leave them untouched. They are scaffolding placeholders from earlier sessions that were never committed; out of scope. Record their existence in `04-progress.md`.
- ✅ **Date stamp on changed status blocks**: use `2026-05-17` (today; the v0.1.0-prealpha tag day).

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with EvidenceRef stubs)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions
