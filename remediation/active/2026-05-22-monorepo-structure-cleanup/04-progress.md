# Progress Log — Monorepo Structure Cleanup

**Session:** `2026-05-22-monorepo-structure-cleanup`
**Branch:** `chore/monorepo-restructure-2026-05-22`

Running execution log. Newest entries at the top.

---

## 2026-05-22 — C-1 IMPLEMENTER (Sonnet)

### Chunk C-1: Remediation archive executed

**Tasks completed:** 1.1, 1.2, 1.3, 1.4 (verify), 1.5, 1.6, 1.7, 1.8

**Moves performed:**
- Created `remediation/SESSION_TEMPLATE/`, `remediation/archive/2026/05/` (tree)
- `git mv` of 44 dated sessions from `team/remediation/` → `remediation/archive/2026/05/` (spec said 43; actual count was 44 including `2026-05-19-post-prealpha-readiness` which was not listed in EVIDENCE_LEDGER but was present in the directory)
- `git mv team/remediation/SESSION_TEMPLATE/ remediation/SESSION_TEMPLATE/` — done
- `git mv team/remediation/README.md remediation/README.md` — done; content updated to reflect new paths
- `git mv team/remediation/HOWTO-backup-before-reset.md docs/operations/backup-before-reset.md` — done (E-5.B default)
- `git mv team/remediation/ISSUE_INTAKE_TEMPLATE.md remediation/ISSUE_INTAKE_TEMPLATE.md` — done (additional file not in spec, but in team/remediation root)
- `git mv team/remediation/_archive/2026-05-12-mintkey-mvp remediation/archive/2026/05/` — done
- `git mv team/remediation/_archive/2026-05-13-playwright-extension remediation/archive/2026/05/` — done
- `git rm team/.gitkeep` + removed empty `team/` directory — done

**Path-reference updates (18 non-session files modified):**
- README.md — HOWTO link updated
- AGENTS.md — 4 refs updated (ISSUE_INTAKE_TEMPLATE, HOWTO, routing table, README)
- CLAUDE.md — 4 refs updated (same pattern)
- CONTRIBUTING.md — 3 refs updated
- GOVERNANCE.md — 1 ref updated
- PROGRESS.md — 3 refs updated (MEGA_PROMPT companion line removed as untracked; historical cascade refs updated)
- SECURITY.md — 1 ref updated
- .github/pull_request_template.md — 3 refs updated
- docs/AUTH.md — 1 HOWTO ref updated
- docs/NETWORK.md — 1 HOWTO ref updated
- docs/DEBUG.md — 2 HOWTO refs updated
- docs/RELEASE.md — 2 session archive refs updated
- docs/guides/10min-mock-demo.md — 1 HOWTO ref updated
- docs/architecture/00-vision/06-roadmap.md — 5 session refs updated
- docs/architecture/00-vision/07-kiro-readiness.md — 1 session ref updated
- docs/architecture/01-architecture/security-notes/weak-hash-migration.md — 2 refs updated
- .kiro/specs/post-prealpha-readiness/evidence.md — 3 refs updated
- .kiro/specs/post-prealpha-readiness/tasks.md — 1 ref updated
- .serena/memories/suggested_commands.md — 1 HOWTO ref updated
- docs/operations/backup-before-reset.md — 2 internal refs updated (the moved file itself)
- remediation/README.md — full content rewrite to reflect new paths

**Intentionally NOT modified (documented justification):**
- `docs/architecture/01-architecture/adr/0019-admin-ui-bff-and-write-auth.md` — accepted ADR, read-only per R-0.2
- `docs/architecture/adrs/0019-admin-ui-bff-and-write-auth.md` — accepted ADR, read-only per R-0.2
- `admin-ui/e2e/tests/26-smoke-regression.spec.ts` — outside C-1 owner-file scope (source code in admin-ui); references untracked design artifact `team/remediation/ADMIN_UI_SPEC.md`
- `.kiro/specs/monorepo-structure-cleanup/*` — own spec files; instructed to leave alone
- `remediation/active/2026-05-22-monorepo-structure-cleanup/*` — current active session meta-docs describing this operation

**Verification:**
- 44 sessions moved (spec expected 43; one extra `2026-05-19-post-prealpha-readiness` present on disk)
- SESSION_TEMPLATE moved: yes
- README moved: yes (content updated)
- HOWTO moved: yes → `docs/operations/backup-before-reset.md`
- ISSUE_INTAKE_TEMPLATE.md moved: yes → `remediation/ISSUE_INTAKE_TEMPLATE.md`
- `team/` deleted: yes (empty after `.gitkeep` removal)
- Remaining `team/remediation` refs outside archive: 2 accepted ADRs (read-only) + 1 e2e test comment (outside C-1 scope) + active session self-references

### Next
- Dispatch fresh REVIEWER (Opus) for C-1.
- C-2 IMPLEMENTER can run in parallel (no shared files).

---

## 2026-05-22 — C-0 ORCHESTRATOR

### Bootstrap
- Synced `main` (HEAD `590cb78`, tag `v0.1.0-preview.1`); worktree clean.
- Created branch `chore/monorepo-restructure-2026-05-22`.
- Baseline inventory captured:
  - 11 deployable services (7 at root + 4 under `services/`).
  - 1 Python shared pkg (`mintkey-models/`).
  - 9 Go internal pkgs under `internal/` (7 with code + 2 empty: `cfg/`, `models/`).
  - 44 dated remediation sessions under `team/remediation/`.
  - 3 observability files + `grafana/` at root.
  - 2 compose files at root.
  - ~350 untracked install-logs at root (already gitignored).
- Path-reference scan: 1700+ occurrences across the move-target paths (admin-api 313, admin-ui 313, docker-compose 163, team/remediation 285, mintkey-models 111, etc.).
- Wrote 4 spec files: `.kiro/specs/monorepo-structure-cleanup/{requirements,design,tasks,evidence}.md`.
- Wrote 8 session files: this folder.
- Identified 5 escalations (E-1..E-5) with defaults for implementers to proceed on.

### Decisions made by ORCHESTRATOR
- Wave structure: C-1 ∥ C-2 (independent files), then C-3 ∥ C-4 (gated on C-2), then C-5, then C-6.
- Implementer strike budget: 3 per chunk.
- Compatibility decisions CD-1..CD-6 documented in `design.md`.

### Next
- Commit Phase 0 (this turn).
- Dispatch C-1 IMPLEMENTER (Sonnet) + C-2 IMPLEMENTER (Sonnet) in parallel.
