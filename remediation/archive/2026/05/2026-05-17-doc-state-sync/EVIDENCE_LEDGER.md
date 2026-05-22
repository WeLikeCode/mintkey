# Evidence Ledger — 2026-05-17-doc-state-sync

> Every doc change in this session must reference at least one row below. Reviewer cross-checks.

| EvidenceRef | Source | Exact reference | Observed fact | Affected docs | Required update |
|---|---|---|---|---|---|
| `EV-GIT-HEAD` | git | `git log --oneline -1` 2026-05-17 | `5f397b7 (HEAD -> main, tag: v0.1.0-prealpha, origin/main) Merge pull request #53` | PROGRESS.md, README.md | "Last updated" + status freshness; mention v0.1.0-prealpha tag |
| `EV-GIT-LOG-100` | git | `git log --oneline --max-count=100` | 53 PRs visible since 2026-05-12 final; merges #33-#53 between 2026-05-16 and 2026-05-17 | PROGRESS.md, roadmap | Add 2026-05-16/2026-05-17 work summary; remove "WS-8 final" framing as current |
| `EV-TAG-PREALPHA` | git | `git tag -l v0.1.0-prealpha` exists; release `https://github.com/WeLikeCode/mintkey/releases/tag/v0.1.0-prealpha` | First public snapshot released | README.md, PROGRESS.md | Mention pre-alpha release; cite tag for stability claim |
| `EV-PROGRESS-LAST-UPDATED` | repo file | `PROGRESS.md:4` | `Last updated: 2026-05-16. All workstreams WS-7a through WS-8 complete.` | PROGRESS.md | Bump to 2026-05-17 and reflect post-WS-8 remediation work |
| `EV-PROGRESS-WS8-COUNTS` | repo file | `PROGRESS.md:78-94` (WS-8 section) | Test counts dated 2026-05-12: `244 passed, 2 skipped`, `17 architecture`, `23 Go packages`, `139 vitest` | PROGRESS.md, README.md | Reframe as "last verified 2026-05-12 (WS-8)"; do NOT replace with fresh counts (no rerun) |
| `EV-README-ADR-COUNT` | repo file | `README.md:135` | `20 ADRs (18 accepted, ADR-0018 proposed)` | README.md | Replace with current count from `EV-ADR-INDEX-COUNT` |
| `EV-README-TEST-COUNTS` | repo file | `README.md:14-20` | Status table: `Unit tests 244 passing`, `Architecture tests 17 passing`, `Go package tests 23 packages green`, milestones `WS-0 → WS-8 complete (Phase 1)` | README.md | Add `last verified 2026-05-12` annotation OR remove counts and link to PROGRESS.md |
| `EV-README-CONTAINER-COUNT` | repo file | `README.md:84` | `15 long-running containers and 2 one-shot jobs` | README.md, roadmap | Cross-check against `docker-compose.yml`; preserve if accurate, annotate if drifted |
| `EV-COMPOSE-SERVICES` | repo file | `docker-compose.yml` parsed 2026-05-17 | 17 long-running services + 2 one-shot jobs (liquibase, seed-job) = 19 services. Long-running set: postgres, keycloak, vault-adapter, admin-api, admin-ui, mcp-server, broker, kong, kong-syncer, proxy-plugin, mock-backend, otel-collector, jaeger, jaeger-auth, prometheus, cadvisor, grafana. | README.md:84 ("15 long-running + 2 one-shot"), roadmap line ~18 ("17 containers (15 long-running, 2 one-shot)") | Update to "17 long-running + 2 one-shot = 19 total" |
| `EV-ADR-FILE-0018` | repo file | `docs/architecture/01-architecture/adr/0018-classical-service-api-keys.md:3-4` | `## Status\nAccepted — 2026-05-11.` | adr/README.md, README.md | Reconcile index/README to "Accepted" |
| `EV-ADR-INDEX-0018` | repo file | `docs/architecture/01-architecture/adr/README.md:46` | Index entry says `Proposed. ... Awaiting acceptance.` | adr/README.md | Update entry to `Accepted — 2026-05-11`; remove "Awaiting acceptance" |
| `EV-ADR-INDEX-0020` | repo file | `docs/architecture/01-architecture/adr/README.md:48` | ADR-0020 entry: `Accepted — 2026-05-15` | (none — already current) | Cross-reference only |
| `EV-ADR-INDEX-COUNT` | repo file | `ls docs/architecture/01-architecture/adr/00*-*.md \| wc -l` = 20 ADR files; index lines 29-48 list all 20 | README.md | Replace "18 accepted, ADR-0018 proposed" with "20 ADRs (all accepted; ADR-0018 latest from 2026-05-11; ADR-0020 latest from 2026-05-15)" or similar evidence-backed phrasing |
| `EV-KIRO-READINESS-7` | repo file | `docs/architecture/00-vision/07-kiro-readiness.md:56` | `ADRs (7 accepted)` | kiro-readiness | Update count, link to current `adr/README.md` |
| `EV-KIRO-READINESS-STATUS` | repo file | `docs/architecture/00-vision/07-kiro-readiness.md:267-280` | `Status (as of 2026-05-10)` block lists `7 accepted (ADR-0001..0007)` and all other rows ❌/⏳ | kiro-readiness | Reframe status block with current state per `EV-KIRO-*` and `EV-CONTRACTS-PATH` |
| `EV-KIRO-READINESS-PATHS` | repo file | `docs/architecture/00-vision/07-kiro-readiness.md:77-82,95,231-232,253-254` | References `/docs/contracts/...`, `/docs/01-architecture/...`, `docs/specs/<component>/...`, `docs/contracts/...` | kiro-readiness | Replace with `docs/architecture/contracts/...`, `docs/architecture/01-architecture/...`, `.kiro/specs/mintkey-mvp/...` per `EV-CONTRACTS-PATH` + `EV-KIRO-SPECS-PATH` |
| `EV-CONTRACTS-PATH` | repo file | `docs/architecture/contracts/rest/openapi.yaml` exists; `docs/contracts/` does NOT exist | Canonical contract path is under `docs/architecture/` | kiro-readiness | Path correction |
| `EV-KIRO-SPECS-PATH` | repo file | `.kiro/specs/mintkey-mvp/{requirements,design,tasks}.md` exist; `docs/specs/` does NOT exist | Canonical spec path is `.kiro/specs/mintkey-mvp/`, not `docs/specs/<component>/` | kiro-readiness | Path correction |
| `EV-KIRO-TASKS-DONE` | repo file | `.kiro/specs/mintkey-mvp/tasks.md` — `grep -cE "\\[x\\]"` returns 99; `grep -cE "\\[ \\]"` returns 0 | All 14 top-level milestones M1.0 … M1.13 checked; all 99 task/subtask lines checked | kiro-readiness, README/PROGRESS | Support claim that M1.0–M1.13 are checked (note this is checkbox state, not test verification) |
| `EV-OTEL-FIX` | session report | `team/remediation/2026-05-17-otel-collector-config/99-report.md:4` | `Status: CLOSED`; PR #48 merged; commit `4667e91` | roadmap | Remove "otel-collector restart loop pre-existing" line from roadmap Section 3 (or mark Resolved with EvidenceRef) |
| `EV-DOCKERFILE-USER` | git | PR #33 chunk REL-3 in `team/remediation/2026-05-16-public-github-release-readiness/99-report.md`; commit `0fd33bf` and predecessors | `USER 65532:65532` + `HEALTHCHECK` added to 6 Dockerfiles (admin-api, mcp-server, admin-ui, mock-backend, seed-job, jaeger-auth) | roadmap | Update Section 3 "Dockerfile USER directive" + "Dockerfile HEALTHCHECK" rows |
| `EV-DOCKERFILE-PIN` | git | PR #35 commit `373221f` (`fix(ci): SHA-pin all Dockerfile FROM directives`); `team/remediation/2026-05-16-ci-bugs-round2/99-report.md` chunk CB-DOCKERFILE-PIN | 15 FROMs SHA-pinned across 10 Dockerfiles | roadmap | Update "Base image @sha256 digest pinning" from Deferred → Done |
| `EV-SEED-JOB-ROOT` | git | PR #47 commit `c335824`; session `2026-05-17-seed-job-perms` CLOSED | seed-job reverted to root (one-shot init container exception) | (no doc reference) | Cross-reference for any future doc claim about container-user posture |
| `EV-SEED-JOB-IDEMPOTENCY` | session report | `team/remediation/2026-05-17-seed-job-idempotency-and-sso/99-report.md:5-6` | Content-validating `_ensure_secret_file` helper; `_patch_keycloak_client_redirect_uris` after realm import | (no doc reference) | Bootstrap-pipeline behavior; not currently in any in-scope doc |
| `EV-INTEGRATION-TIMEOUT-FIX` | session report + git | `team/remediation/2026-05-17-integration-tests-timeout/99-report.md`; PR #46 commit `e7b5e36` | docker-compose build + start split; wait timeout 120s → 180s | roadmap (if any pre-existing CI claim) | Confirm no roadmap claim still flags this as open |
| `EV-PR53-MERGED` | git | `git log --oneline` 2026-05-17 | `5f397b7 Merge pull request #53` (seed-job idempotency + Keycloak redirectUris patcher) | (cross-reference) | Latest merged work |
| `EV-CI-MAIN-GREEN` | conversation log | Prior conversation turn — CI on `5f397b7` showed 13/13 ✓ at 09:39 UTC 2026-05-17 | All CI checks ✓ on tagged commit | README.md | Optionally cite as evidence for "all gates green on tag" — but DO NOT claim freshly rerun tests |
| `EV-JAEGER-COOKIE-B64-REPORT` | repo file | `team/remediation/2026-05-17-jaeger-cookie-b64/99-report.md` | Template text: `# <Session Title>`, `<TODO: CLOSED ...>`, `<YYYY-MM-DD-kebab-slug>` | this report | Rewrite with real evidence — PR #52 commit `35369d0` merged 2026-05-17 |
| `EV-JAEGER-COOKIE-SIZE-REPORT` | repo file | `team/remediation/2026-05-17-jaeger-cookie-size/99-report.md` | Template text | this report | Rewrite — PR #50 commit `e6c84fc` merged 2026-05-17 |
| `EV-JAEGER-ENTRYPOINT-BINARY-REPORT` | repo file | `team/remediation/2026-05-17-jaeger-entrypoint-binary/99-report.md` | Template text | this report | Rewrite — PR #51 commit `abc80c4` merged 2026-05-17 |
| `EV-JAEGER-SECRET-PERMS-REPORT` | repo file | `team/remediation/2026-05-17-jaeger-secret-perms/99-report.md` | Template text | this report | Rewrite — PR #49 commit `6364923` merged 2026-05-17 |
| `EV-PR52-COMMIT` | git | `git log` | `35369d0 fix(jaeger-auth): use base64-encoded cookie-secret`; PR #52 merged in `54e8f9f` | jaeger-cookie-b64 99-report | Cite as final verification anchor |
| `EV-PR51-COMMIT` | git | `git log` | `abc80c4 fix(jaeger-auth): use --cookie-secret-file`; PR #51 merged in `3c8fd3a`. Note: this fix was superseded by PR #52 because `--cookie-secret-file` flag does not exist in oauth2-proxy v7.6.0 | jaeger-entrypoint-binary 99-report | Document the supersession; mark as "merged but reverted by #52" if applicable, or "intermediate step in cascade" |
| `EV-PR50-COMMIT` | git | `git log` | `e6c84fc fix(seed-job): write jaeger_oauth2_cookie_secret as 32 raw bytes`; PR #50 merged in `a1cf0f3`. Superseded by PR #52 (raw bytes had shell-null-truncation issue) | jaeger-cookie-size 99-report | Document supersession |
| `EV-PR49-COMMIT` | git | `git log` | `6364923 fix(seed-job): write jaeger_oauth2_cookie_secret + make all bootstrap secrets world-readable`; PR #49 merged in `e3f7665` | jaeger-secret-perms 99-report | Standalone — perms fix not superseded |
| `EV-NO-FRESH-RERUN` | this session | No `pytest`, `go test`, `vitest`, or `docker compose` health-check command was run in this doc-state-sync session | All numerical claims | Annotate any update with `last verified by <report/date>` |
| `EV-WORKTREE-DIRTY` | git | `git status --short --branch` at session start | 17 untracked `??` files across 6 prior 2026-05-17-* dirs (incomplete scaffolds from earlier conversation turns) | 04-progress.md | Acknowledged; not modified in this session |
| `EV-MEM-MEGAPROMPT` | repo file | `team/remediation/MEGA_PROMPT.md` referenced from `PROGRESS.md:3` | Companion doc still referenced | PROGRESS.md | Verify file exists; if so, keep reference; otherwise note |

## Residual evidence (cited but not used for changes)

| EvidenceRef | Status |
|---|---|
| `EV-ADR-FILES-COUNT` | 20 ADRs present (0001-0020). Index has 20 entries. |
| `EV-ROADMAP-SECTION-3` | Multiple rows in roadmap Section 3 may also need 🟦 Deferred → ✅ Done; reviewer cross-checks all rows. |

## Notes for implementers

- When updating a public doc, **link or footnote** the EvidenceRef inline ONLY if it improves clarity. Otherwise keep the citation in this ledger and reference it in the commit message.
- The user-facing language should NOT mention "EvidenceRef" labels; those are internal to the session.
- Date stamp for status blocks: `2026-05-17` (today; v0.1.0-prealpha tag day).
