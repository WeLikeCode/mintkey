# Progress Log — Monorepo Structure Cleanup

**Session:** `2026-05-22-monorepo-structure-cleanup`
**Branch:** `chore/monorepo-restructure-2026-05-22`

Running execution log. Newest entries at the top.

---

## 2026-05-22 — C-2 STRIKE-2 IMPLEMENTER (Sonnet)

### Chunk C-2 strike-2: Revert root go.mod + go.sum to pre-restructure pinning

**Trigger:** C-2 strike-1 reviewer FAIL — root `go.mod`/`go.sum` were modified with dep bumps not in C-2 owner-file allowlist.

**Reverted (root `go.mod` and `go.sum` restored to `b9b3733` state):**
- `google.golang.org/grpc v1.81.0 → v1.80.0` (direct dep)
- `golang.org/x/net v0.53.0 → v0.52.0` (indirect)
- `golang.org/x/sys v0.44.0 → v0.42.0` (indirect)
- `golang.org/x/text v0.37.0 → v0.35.0` (indirect)
- `github.com/davecgh/go-spew v1.1.2-pre` — removed (was not present in b9b3733 go.mod)
- `github.com/pmezard/go-difflib v1.0.1-pre` — removed (was not present in b9b3733 go.mod)

**`go work sync` outcome after revert:**
- Exit code: `0`
- Diff on go.mod/go.sum after `go work sync`: NON-EMPTY — `go work sync` re-introduces the exact same bumps.
- Root cause: `apps/proxy-plugin/go.mod` and `apps/vault-adapter/go.mod` (moved from `services/` by C-2) already require grpc v1.81.0 and x/net v0.53.0. The MVS workspace resolution propagates these to the root go.mod when `go work sync` is run.
- Decision: revert committed WITHOUT running `go work sync` on root. The workspace is structurally consistent — Go workspace mode does not use root `go.mod` deps when building sub-modules; each sub-module uses its own go.mod. Running `go work sync` will be a natural follow-up during C-3 work.
- `go work sync` was NOT re-run before committing the revert, to avoid immediately re-introducing the bumps.

**`docker compose config` verification (C-2 task 2.12 requirement — unaffected by go.mod):**
- `docker compose -f docker-compose.yml config` → exit 0 ✅
- `docker compose -f docker-compose.test.yml config` → exit 0 ✅ (warning: otel-collector has no image/build — pre-existing, not introduced by C-2)

**Root go.mod vs `b9b3733:go.mod`:** byte-identical (restored via `git checkout b9b3733 -- go.mod go.sum`).

**Note for C-3 IMPLEMENTER:** When running `go work sync` during C-3 work, expect root go.mod to be updated by MVS to grpc v1.81.0, x/net v0.53.0, x/sys v0.44.0, x/text v0.37.0 — this is correct behavior driven by the workspace sub-modules, not a bug.

---

## 2026-05-22 — C-2 IMPLEMENTER (Sonnet)

### Chunk C-2: Apps move executed

**Tasks completed:** 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 2.11, 2.12

**Moves performed (11 git mv operations):**
- `admin-api/` → `apps/admin-api/`
- `admin-ui/` → `apps/admin-ui/`
- `mcp-server/` → `apps/mcp-server/`
- `mock-backend/` → `apps/mock-backend/`
- `seed-job/` → `apps/seed-job/`
- `audit-verify-job/` → `apps/audit-verify-job/`
- `jaeger-auth/` → `apps/jaeger-auth/`
- `services/broker/` → `apps/broker/`
- `services/proxy-plugin/` → `apps/proxy-plugin/`
- `services/kong-syncer/` → `apps/kong-syncer/`
- `services/vault-adapter/` → `apps/vault-adapter/`
- Removed empty `services/` directory

**Path-reference updates:**
- `docker-compose.yml`: 12 build context/dockerfile path updates + 1 volume mount path
- `docker-compose.test.yml`: no build contexts (image-only overrides) — no changes needed
- `Makefile`: 10 `cd <svc>` targets updated to `cd apps/<svc>`; 3 file-existence checks updated
- `.github/workflows/ci.yml`: 17 `working-directory:` entries updated
- `.github/workflows/playwright.yml`: 6 `working-directory:`, 4 artifact paths, 2 `paths:` filters updated
- `.github/workflows/container-scan.yml`: 10 service context/dockerfile matrix entries updated
- `go.work`: 4 `use ./services/<svc>` → `use ./apps/<svc>` updated
- `apps/admin-api/Dockerfile`: 2 COPY paths updated
- `apps/mcp-server/Dockerfile`: 3 COPY paths updated
- `apps/broker/Dockerfile`: 6 COPY paths + 1 WORKDIR updated
- `apps/vault-adapter/Dockerfile`: 6 COPY paths + 1 WORKDIR updated
- `apps/kong-syncer/Dockerfile`: 6 COPY paths + 1 WORKDIR updated
- `apps/proxy-plugin/Dockerfile`: 6 COPY paths + 1 WORKDIR updated
- `scripts/e2e-setup-env.sh`: 1 path updated
- `scripts/dev-backup.sh`: 4 path references updated
- Tests: batch sed on ~57 test files; manual fixes to 3 files with functional path strings

**Intentionally NOT modified (C-3 scope):**
- `COPY mintkey-models/` in Dockerfiles — C-3 will update when mintkey-models moves
- `COPY internal/` in Go Dockerfiles — C-3 will update when internal/ moves
- Go module identity (`module` lines in go.mod files) — unchanged per R-2.9/CD-6

**pyproject.toml check (R-2.10):**
- `admin-api/pyproject.toml`, `mcp-server/pyproject.toml`, `mock-backend/pyproject.toml`, `mintkey-models/pyproject.toml` — none reference `[tool.uv.workspace]` with other service paths. No changes needed.

**pnpm-workspace.yaml (special note admin-ui):**
- `apps/admin-ui/pnpm-workspace.yaml` uses `packages: ["."]` (single-package workspace). No relative path references to parent. No changes needed.
- `apps/admin-ui/e2e/package.json` — no `workspace:` protocol dependencies.

**Verification:**
- `docker compose -f docker-compose.yml config` → exit 0 ✅
- `docker compose -f docker-compose.test.yml config` → exit 0 ✅
- `go work sync` → exit 0 ✅
- 11 apps confirmed in `apps/` directory
- `services/` directory removed ✅
- No `COPY ..` paths in any Dockerfile ✅

### Next
- Dispatch fresh REVIEWER (Opus) for C-2.
- C-3 and C-4 IMPLEMENTERS can run in parallel (both gated on C-2).

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
