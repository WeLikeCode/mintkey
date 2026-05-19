# Evidence Ledger — Post-Prealpha Readiness

**Session:** `2026-05-19-post-prealpha-readiness`

Every change in this session traces to a row below. The spec at `.kiro/specs/post-prealpha-readiness/{requirements,design,tasks}.md` is the primary source of truth; this ledger maps each spec requirement to the file/state evidence that justifies the deliverable.

**Schema:**
| EvidenceRef | Source | Requirement | Why the deliverable exists |
|---|---|---|---|

Prefix namespace:
- `EV-SPEC-*` — direct from the kiro spec
- `EV-STATE-*` — current repo state proving a roadmap claim is stale/accurate
- `EV-PRIOR-*` — prior session artifacts that establish ground truth
- `EV-GAP-*` — known gap that this spec closes

## Spec anchors

| EvidenceRef | Source | Requirement | Why the deliverable exists |
|---|---|---|---|
| EV-SPEC-001 | `.kiro/specs/post-prealpha-readiness/requirements.md` | All 21 | Authoritative requirements set |
| EV-SPEC-002 | `.kiro/specs/post-prealpha-readiness/design.md` | All | Workstream layout + per-task design |
| EV-SPEC-003 | `.kiro/specs/post-prealpha-readiness/tasks.md` | All | 17-task implementation plan + dependency graph |

## Prior-session artifacts that ground today's deliverables

| EvidenceRef | Source | Requirement | Why the deliverable exists |
|---|---|---|---|
| EV-PRIOR-001 | `scripts/dev-backup.sh` (PR #72, 2026-05-18) | 1.1, 1.2, 1.3 | Roadmap currently says "No backup/restore procedure" → false. This script is the rebuttal. |
| EV-PRIOR-002 | `scripts/dev-restore.sh` (PR #72) | 1.1, 1.2, 1.3 | Same as above — restore companion script |
| EV-PRIOR-003 | `scripts/dev-backup-cron.example.sh` (PR #75) | 1.1, 1.2, 1.3 | Operator-installable periodic-backup wrapper |
| EV-PRIOR-004 | `team/remediation/HOWTO-backup-before-reset.md` (PR #72 + #75 §11) | 1.1, 1.2, 1.3 | Canonical "back up before reset" doc — what the new roadmap entry will link to |
| EV-PRIOR-005 | `SECURITY.md §Accepted Scorecard Residuals` (PR #64 S11 + PR #77 extend) | 4.1, 4.2 | 8 Scorecard residuals documented; click-paths for GitHub-UI dismissal still missing → tasks 3.1 + 4.1 |
| EV-PRIOR-006 | `team/remediation/2026-05-18-s5-codeql-weak-hashing/` (PR #66) | 6.1, 6.2, 6.3 | 3 weak-hash sites classified BLOCKED pending migration; tasks 3.3 + 4.x consolidate this into a permanent doc |
| EV-PRIOR-007 | `tests/acceptance/test_audit_append_only.py` | 7.1, 7.2 | Audit-chain SHA-256 enforcement test — task 3.4 cites this |
| EV-PRIOR-008 | `docs/architecture/00-vision/07-kiro-readiness.md` | 21.1, 21.2, 21.3 | 3 status-table rows need flip after KIRO.md/patterns/stubs land |
| EV-PRIOR-009 | `docs/DEBUG.md` (existing) | 17.1-17.6 | Current entries are sparse; task 11.1 adds 6 new entries to cover post-2026-05-18 troubleshooting |
| EV-PRIOR-010 | `docs/architecture/00-vision/06-roadmap.md` Section 1 | 1.1, 1.2, 1.3, 2.1 | Contains the stale "No backup/restore" claim (precise location task 2.1 fixes) |
| EV-PRIOR-011 | `docs/architecture/00-vision/06-roadmap.md` Section 3 | 2.1, 3.1, 3.2 | Contains additional status sentences that need EvidenceRef tagging per task 2.2 |
| EV-PRIOR-012 | Mintkey proxy egress via `svc_01KRW0G089YCDPAAQ6G146B3GB` (working since 2026-05-18) | 13.1, 13.2, 13.3, 14.1, 14.2, 14.3, 15.1, 16.1 | All examples in `examples/*` should demonstrate calling backends via this proxy pattern |

## Repo-state anchors (current truth as of `main @ a16aed0`)

| EvidenceRef | Source | Requirement | Why the deliverable exists |
|---|---|---|---|
| EV-STATE-001 | `docker-compose.yml` (9 images all `@sha256:`-pinned post-PRs #70 + #74) | — | Demo target can assume stable digests |
| EV-STATE-002 | `.github/workflows/container-scan.yml` (push trigger + workflow_dispatch post-PR #76) | — | CI rescans on every merge |
| EV-STATE-003 | `.kiro/specs/dev-test-namespace/` (PR #87) | — | Parallel test-stack precedent exists; demo target should NOT conflict with it |
| EV-STATE-004 | No `examples/` dir exists at repo root | 14.1, 14.2, 14.3, 15.1, 16.1, 19.x | Brand-new directories for tasks 8.x, 9.x, 10.x |
| EV-STATE-005 | No `/KIRO.md` exists | 18.x | Brand-new file at repo root |
| EV-STATE-006 | No `docs/patterns/` exists | 19.x | Brand-new directory |
| EV-STATE-007 | No `tests/stubs/` exists | 20.x | Brand-new directory (README only; no implementations) |
| EV-STATE-008 | No `docs/architecture/01-architecture/security-notes/` exists | 6.1, 6.2, 6.3 | Brand-new directory for weak-hash-migration.md |

## Known gaps the spec closes

| EvidenceRef | Source | Requirement | Why the deliverable exists |
|---|---|---|---|
| EV-GAP-001 | Roadmap_Doc "No backup/restore procedure" claim is false post-2026-05-18 | 1.1, 1.2, 1.3 | Task 2.1 |
| EV-GAP-002 | Roadmap_Doc has status sentences without EvidenceRefs | 2.1, 3.1, 3.2 | Task 2.2 |
| EV-GAP-003 | SECURITY.md §Accepted Scorecard Residuals lacks GitHub-UI click-path | 4.1, 4.2 | Task 3.1 |
| EV-GAP-004 | GO-2026-XXXX advisory ID truncated; resolution status unclear | 5.1, 5.2, 5.3 | Task 3.2 |
| EV-GAP-005 | Weak-hash migration strategy is in a S5 99-report but not a permanent design doc | 6.1, 6.2, 6.3 | Task 3.3 |
| EV-GAP-006 | Audit hash-chain SHA-256 ADR-0014.7 not mirrored in SECURITY.md | 7.1, 7.2 | Task 3.4 |
| EV-GAP-007 | No `make demo` target; first-time setup is multi-step | 11.x | Task 6.1 |
| EV-GAP-008 | No `make demo-mock`; mock demo lives only in docs/guides/10min-mock-demo.md | 12.x | Task 6.2 |
| EV-GAP-009 | "Agent never sees secret" claim has no copy-paste walkthrough | 13.x | Task 7.1 |
| EV-GAP-010 | No Python agent example | 14.x | Task 8.1 |
| EV-GAP-011 | No TypeScript agent example | 15.x | Task 9.1 |
| EV-GAP-012 | No OpenAI-compatible example | 16.x | Task 10.1 |
| EV-GAP-013 | DEBUG.md missing 6 new entries | 17.x | Task 11.1 |
| EV-GAP-014 | No /KIRO.md link hub | 18.x | Task 13.1 |
| EV-GAP-015 | No docs/patterns/ — Builder has architecture but no "add a thing" guides | 19.x | Tasks 14.1, 14.2, 14.3 |
| EV-GAP-016 | No tests/stubs/ plan | 20.x | Task 15.1 |
| EV-GAP-017 | kiro-readiness.md status table stale | 21.x | Task 16.1 |

## Coverage check (post-implementation, run before C-7)

For each spec requirement (1.1 through 21.3 — 21 requirements with sub-numbering), confirm a deliverable lands. C-7 will run this audit.
