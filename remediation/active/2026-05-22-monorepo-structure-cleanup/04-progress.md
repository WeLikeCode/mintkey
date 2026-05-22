# Progress Log — Monorepo Structure Cleanup

**Session:** `2026-05-22-monorepo-structure-cleanup`
**Branch:** `chore/monorepo-restructure-2026-05-22`

Running execution log. Newest entries at the top.

---

## 2026-05-22 — C-5 STRIKE-2 IMPLEMENTER (Sonnet)

### Chunk C-5 strike-2: Fix 6 stale-path misses from strike-1 reviewer

**Trigger:** C-5 strike-1 reviewer FAIL — 6 mechanical path misses not caught during original C-5 sweep.

**Fixes applied (all runtime-breaking or silently-wrong paths):**

1. `Makefile:115` — `cd mintkey-models && $(UV) run pytest tests/` → `cd packages/python/mintkey-models && $(UV) run pytest tests/` (`make test-unit` was broken)
2. `Makefile:214` — `cd mintkey-models && $(UV) run ruff check mintkey_models/` → `cd packages/python/mintkey-models && $(UV) run ruff check mintkey_models/` (`make lint-python` was broken)
3. `Makefile:217` — `cd mintkey-models && $(UV) run mypy --strict mintkey_models/` → `cd packages/python/mintkey-models && $(UV) run mypy --strict mintkey_models/` (`make lint-python` was broken)
4. `.github/workflows/ci.yml:36` — `working-directory: mintkey-models` → `working-directory: packages/python/mintkey-models` (CI lint job was broken)
5. `.github/workflows/ci.yml:128` — `working-directory: mintkey-models` → `working-directory: packages/python/mintkey-models` (CI test job was broken)
6. `.github/dependabot.yml:110` — `directory: /jaeger-auth` → `directory: /apps/jaeger-auth` (dependabot silently no-oping on Docker updates)
7. `.github/dependabot.yml:141` — `directory: /mintkey-models` → `directory: /packages/python/mintkey-models` (dependabot silently no-oping on pip updates)
8. `QUICKSTART.md:171` — `cd mintkey-models` → `cd packages/python/mintkey-models` (operator setup step was broken)
9. `QUICKSTART.md:179` — `cd admin-ui` → `cd apps/admin-ui` (operator setup step was broken)
10. `docs/guides/github-quickstart.md:49` — `admin-ui/e2e/.env.local` → `apps/admin-ui/e2e/.env.local`
11. `docs/operations/backup-before-reset.md:38` — `admin-ui/e2e/.env.local` → `apps/admin-ui/e2e/.env.local`
12. `.gitignore:23` — `admin-ui/screenshots-*/` → `apps/admin-ui/screenshots-*/` (Playwright screenshots were silently not gitignored)

Note: items 1-3 count as 3 Makefile occurrences (reviewer listed as R-6.8); items 4-5 as 2 CI occurrences (R-6.9); items 6-7 as 2 dependabot occurrences (R-6.9); items 8-9 as 2 QUICKSTART occurrences (R-6.1); items 10-11 as 2 docs occurrences (R-6.6); item 12 as 1 .gitignore occurrence (R-6.11). Total: 6 reviewer findings, 12 individual line changes.

**Impact of these misses:** `make test-unit` and `make lint-python` would have exited non-zero with "No such file or directory"; CI lint-mintkey-models and test-mintkey-models jobs would have failed; dependabot would have silently skipped jaeger-auth Docker and mintkey-models pip updates; QUICKSTART operator setup steps would have failed; Playwright screenshots generated under `apps/admin-ui/screenshots-*/` would not have been gitignored (risking accidental commit of large binary artifacts).

**No additional similar misses found** in the files touched during strike-2 review.

**Verification (all clean):**
- `grep -nE 'cd mintkey-models|cd admin-ui[^/]' Makefile` → no hits ✅
- `grep -nE 'working-directory: mintkey-models|working-directory: admin-' .github/workflows/ci.yml` → no hits ✅
- `grep -nE '^[[:space:]]*directory: /(jaeger-auth|mintkey-models|...)' .github/dependabot.yml` → no hits ✅
- `grep -n 'cd mintkey-models\|cd admin-ui[^/]' QUICKSTART.md` → no hits ✅
- `grep -n '[^s]/admin-ui/e2e/' docs/guides/github-quickstart.md docs/operations/backup-before-reset.md` → no hits ✅
- `grep -n '^admin-ui/' .gitignore` → no hits ✅
- `make help` → pre-existing line-18 warning only; exit=0 ✅
- `make -n test-unit` → exit=0 ✅
- `make -n lint-python` → exit=0 ✅
- `git diff --stat HEAD~1..HEAD -- docs/architecture/01-architecture/adr/ docs/architecture/adrs/` → empty (no ADR edits) ✅

**Commit:** _see 02-matrix.md_

---

## 2026-05-22 — C-5.5 IMPLEMENTER (Sonnet)

### Chunk C-5.5: Root go.mod workspace MVS sync

**Task completed:** 6.5.1

**Option chosen:** Option A — accept MVS-propagated bumps as a one-time consistency sync.

**Rationale:** The root go.mod was left pinned at pre-restructure versions (intentionally per R-0.1 / OOS-4). However, every upgraded version was already present in apps/*/go.mod prior to this restructure PR — none are net-new upgrades introduced by C-5.5. Running `go work sync` without this fix would forever produce a non-empty diff, making future maintenance noisy. The root go.mod is de facto unused for builds (Go workspace mode routes each sub-module through its own go.mod); this sync only matters for `go test ./...` against root-module packages.

**Version bumps propagated (apps/*/go.mod → root go.mod via MVS):**
- `google.golang.org/grpc`: v1.80.0 → v1.81.0 (direct; driven by apps/proxy-plugin, apps/vault-adapter)
- `golang.org/x/net`: v0.52.0 → v0.53.0 (indirect; driven by apps/proxy-plugin, apps/vault-adapter)
- `golang.org/x/sys`: v0.42.0 → v0.44.0 (indirect; driven by apps/broker, apps/proxy-plugin, apps/vault-adapter)
- `golang.org/x/text`: v0.35.0 → v0.37.0 (indirect; driven by apps/broker, apps/proxy-plugin, apps/vault-adapter)
- `github.com/davecgh/go-spew`: added (pre-release commit; driven by apps/broker, apps/proxy-plugin)
- `github.com/pmezard/go-difflib`: added (pre-release commit; driven by apps/broker, apps/proxy-plugin)
- `go.sum`: checksums swapped for the above; no new transitive checksums

**Files modified:** `go.mod`, `go.sum` (only)

**Verification:**
- `go work sync` (first run) → exit 0 ✅
- `git diff --stat go.mod go.sum go.work.sum` → 2 files changed (go.work.sum unchanged) ✅
- `go test ./...` (root module) → exit 0 (audit, auditq, changes, otelinit, svcid, ulid, vault/v1: ok) ✅
- `uv run pytest tests/` (packages/python/mintkey-models) → 60 passed ✅
- `go work sync` (second run — idempotency check) → empty diff ✅

**Commit:** 4fa8819

### Next
- Dispatch C-6 REVIEWER (Opus) for full session audit.

---

## 2026-05-22 — C-5 IMPLEMENTER (Sonnet)

### Chunk C-5: Docs/Kiro/CI sweep executed

**Tasks completed:** 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 6.10, 6.11, 6.12

**Files updated (stale path sweep — docs, Kiro specs, CI, skills, serena memories):**

Root docs: README.md, KIRO.md, AGENTS.md, CLAUDE.md, QUICKSTART.md, CONTRIBUTING.md, SECURITY.md, CHANGELOG.md, ORCHESTRATION_STATE.md

`docs/`: AUTH.md, DEBUG.md, DEPLOYMENT.md, NETWORK.md, RELEASE.md, SDD.md, architecture/00-vision/06-roadmap.md, architecture/00-vision/07-kiro-readiness.md, architecture/01-architecture/open-questions.md, architecture/01-architecture/security-notes/weak-hash-migration.md, architecture/03-flows/F-AG-01*, F-OP-01*, F-OP-02*, F-OP-03*, F-OP-04*, architecture/proposal/P-006*, architecture/proposal/P-009*, architecture/risk-register.md, guides/agent-never-sees-secret.md, guides/github-quickstart.md, operations/backup-before-reset.md, patterns/add-audit-event.md, patterns/add-mcp-tool.md, patterns/add-rest-endpoint.md

`.kiro/`: steering/structure.md, steering/architecture-principles.md, specs/grafana-request-monitoring/{design,requirements,tasks}.md, specs/long-lived-api-keys/{design,requirements,tasks}.md, specs/mintkey-mvp/{design,requirements,tasks}.md, specs/monorepo-structure-cleanup/tasks.md, specs/post-prealpha-readiness/design.md

`.github/`: workflows/container-scan.yml (comment update), dependabot.yml (directory paths)

CI/ignore: .dockerignore, .gitignore

Skills: .agents/skills/task-implement/SKILL.md, .claude/skills/task-implement/SKILL.md

Serena memories: codebase_structure.md, tech_stack.md, suggested_commands.md, task_completion_checklist.md, code_style_conventions.md, known_gaps_and_issues.md

**Substitutions applied:**
- `admin-api/` → `apps/admin-api/` (in filesystem path context)
- `mcp-server/` → `apps/mcp-server/` (in filesystem path context)
- `services/broker/` → `apps/broker/`
- `services/proxy-plugin/` → `apps/proxy-plugin/`
- `services/kong-syncer/` → `apps/kong-syncer/`
- `services/vault-adapter/` → `apps/vault-adapter/`
- `mintkey-models/` → `packages/python/mintkey-models/` (in filesystem path context)
- `internal/audit` etc. → `packages/go/audit` etc. (Go package imports/paths)
- `otel-collector-config.yaml` → `infra/observability/otel-collector-config.yaml`
- `grafana/provisioning/` → `infra/observability/grafana/provisioning/`
- `/services/broker` → `/apps/broker` (dependabot.yml directory entries)

**Excluded per constraint:**
- `docs/architecture/01-architecture/adr/**` — accepted ADRs, read-only (R-0.2)
- `remediation/archive/**` — historical record
- `.kiro/specs/monorepo-structure-cleanup/**` — own spec files (self-referential evidence)
- HTTP API endpoint paths (`/v1/internal/audit/emit`, `/v1/tenants/.../services/...`) — not filesystem paths
- `apps/proxy-plugin/internal/` refs — proxy plugin's own internal packages, NOT shared `packages/go/`

**Verification (all final scans exit 0):**
- `grep -rn "services/broker|services/proxy-plugin..." docs/ .kiro/ ...` → only accepted ADR hits
- `grep -rn "mintkey-models/" ...` → only accepted ADR hits + own spec self-refs
- `grep -rn "internal/audit|internal/changes..." ...` → only accepted ADR hits + HTTP endpoint paths
- `git diff --stat HEAD -- docs/architecture/01-architecture/adr/` → empty (no ADR edits) ✅

### Next
- Commit this C-5 work: `chore(repo): C-5 — sweep docs/Kiro/CI for stale paths`
- Dispatch fresh REVIEWER (Opus) for C-5.
- C-6 REVIEWER can run after C-5 review passes.

---

## 2026-05-22 — C-4 IMPLEMENTER (Sonnet)

### Chunk C-4: Infra grouping executed

**Tasks completed:** 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9, 4.10, 4.11

**Directories created:**
- `infra/compose/` (via mkdir -p; compose files moved in)
- `infra/observability/` (via mkdir -p; observability files moved in)
- `infra/keycloak/` (via mkdir -p + `.gitkeep` per CD-2/E-3.A placeholder)

**Moves performed (5 git mv operations):**
- `docker-compose.yml` → `infra/compose/docker-compose.yml`
- `docker-compose.test.yml` → `infra/compose/docker-compose.test.yml`
- `prometheus.yml` → `infra/observability/prometheus.yml`
- `alert_rules.yml` → `infra/observability/alert_rules.yml`
- `otel-collector-config.yaml` → `infra/observability/otel-collector-config.yaml`
- `grafana/` → `infra/observability/grafana/`

**realm-mintkey.json decision (4.6 / CD-2):** `apps/seed-job/realm-mintkey.json` stays in place. Docker `COPY` from build context constraint makes it unsafe to move to `infra/keycloak/`. Documented in `99-report.md` (EV-KEEP-5-009). `infra/keycloak/.gitkeep` created as placeholder.

**Root shim (4.7 / CD-1):** Docker Compose v5.1.4 detected — well above v2.20.0 threshold. Created root `docker-compose.yml` with `include: - ./infra/compose/docker-compose.yml` (no symlink needed).

**Internal compose path updates (infra/compose/docker-compose.yml) — 14 build-context + volume-mount edits:**
- Build contexts (services with `context: ./apps/<svc>` → `../../apps/<svc>`): seed-job, admin-ui, mock-backend, jaeger-auth (4 services)
- Build contexts (services with `context: .` → `../..`): vault-adapter, admin-api, mcp-server, broker, kong-syncer, proxy-plugin (6 services)
- Volume mounts updated: `./apps/admin-api/db/changelog` → `../../apps/admin-api/db/changelog`; `./apps/proxy-plugin/kong.yml` → `../../apps/proxy-plugin/kong.yml`; `./otel-collector-config.yaml` → `../observability/otel-collector-config.yaml`; `./prometheus.yml` → `../observability/prometheus.yml`; `./alert_rules.yml` → `../observability/alert_rules.yml`; `./grafana/provisioning/dashboards` → `../observability/grafana/provisioning/dashboards`; `./grafana/provisioning/datasources` → `../observability/grafana/provisioning/datasources`

**docker-compose.test.yml:** No path updates needed — test overlay only overrides ports and image tags, has no build contexts or volume mounts.

**Makefile update (4.8 / R-5.7):** 1 update — `COMPOSE_TEST` variable: `docker-compose.yml -f docker-compose.test.yml` → `infra/compose/docker-compose.yml -f infra/compose/docker-compose.test.yml`. The `dev`, `demo`, `smoke`, `demo-mock` targets use `docker compose` without `-f` and work via root shim.

**Script updates (4.11 / R-5.10):** 
- `scripts/dev-backup.sh`: 4 occurrences of `-f "${REPO_ROOT}/docker-compose.yml"` → `-f "${REPO_ROOT}/infra/compose/docker-compose.yml"`
- `scripts/dev-restore.sh`: 1 occurrence, same update
- `scripts/demo-mock-flow.sh`: no `-f` flag usage (only comments) — unchanged
- `scripts/e2e-setup-env.sh`: no `-f` flag usage — unchanged

**Verification results:**
- `docker compose -f infra/compose/docker-compose.yml config` → exit 0 ✅
- `docker compose -f infra/compose/docker-compose.test.yml config` → exit 0 ✅ (warning: standalone overlay without base — expected; combined with base exits 0)
- `docker compose config` (root shim) → exit 0 ✅
- `make help` → pre-existing Makefile error on line 18 (`.PHONY` with `test:e2e` colon patterns); NOT introduced by C-4; exit=0 ✅
- `make -n demo` → same pre-existing Makefile error; exit=0 ✅

### Next
- Dispatch fresh REVIEWER (Opus) for C-4.
- C-5 gated on C-2, C-3, C-4 — dispatch after C-3 and C-4 reviewers pass.

---

## 2026-05-22 — C-3 IMPLEMENTER (Sonnet)

### Chunk C-3: Packages move executed

**Tasks completed:** 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8, 3.9, 3.10, 3.11, 3.12

**Moves performed:**
- Created `packages/python/` and `packages/go/` directories
- `git mv mintkey-models/ packages/python/mintkey-models/` (1 Python package)
- `git mv internal/audit/ packages/go/audit/` 
- `git mv internal/auditq/ packages/go/auditq/`
- `git mv internal/changes/ packages/go/changes/`
- `git mv internal/otelinit/ packages/go/otelinit/`
- `git mv internal/svcid/ packages/go/svcid/`
- `git mv internal/ulid/ packages/go/ulid/`
- `git mv internal/vault/ packages/go/vault/` (7 Go packages)
- `rmdir internal/cfg internal/models internal/` (empty dirs, no tracked files)

**Go import rewrites:**
- Module root: `github.com/mintkey/mintkey`
- `find . -name '*.go' | xargs sed -i.bak 's|github.com/mintkey/mintkey/internal/|github.com/mintkey/mintkey/packages/go/|g'`
- 20 `.go` files rewritten
- Important fix: `packages/go/vault/v1/vault.pb.go` — sed accidentally rewrote a binary string in the protobuf rawDesc constant (`Z4` varint length prefix encoded 52-char old path; sed changed content to 55 chars without updating the length → `slice bounds out of range [-5:]` panic). Reverted the binary string to preserve the length-prefixed encoding while the actual Go import statement was unchanged (there were no Go import statements in vault.pb.go to begin with — only the rawDesc string).

**go.work directive note:**
- The 7 moved Go packages have NO individual `go.mod` — they are part of the root module (`github.com/mintkey/mintkey`)
- Root module `.` is already listed in `go.work`; no new `use` directives needed
- `go work sync` exit 0; go.mod/go.sum drive-by version bumps reverted with `git checkout HEAD -- go.mod go.sum` per strike-2 policy
- `go.work.sum` minor cleanups (3 removed `.mod` entries, no new versions) retained

**Dockerfile COPY updates:**
- `apps/admin-api/Dockerfile`: `COPY mintkey-models/mintkey_models/` → `COPY packages/python/mintkey-models/mintkey_models/`
- `apps/mcp-server/Dockerfile`: same
- `apps/broker/Dockerfile`: `COPY internal/ internal/` → `COPY packages/go/ packages/go/`
- `apps/vault-adapter/Dockerfile`: same
- `apps/kong-syncer/Dockerfile`: same
- `apps/proxy-plugin/Dockerfile`: same

**pyproject.toml check (R-3.10):**
- No `[tool.uv.workspace]` references to `mintkey-models` path found in any pyproject.toml
- No changes needed

**Python import names (R-3.9):**
- `mintkey_models` package name unchanged; only filesystem path changed
- Confirmed by `uv run pytest tests/` passing all 60 tests

**Verification:**
- `go work sync` → exit 0
- `go.mod`/`go.sum` drive-by bumps reverted ✓
- `go test ./...` (root module) → exit 0 (audit, auditq, changes, otelinit, svcid, ulid, vault/v1: ok/no test files)
- `go test ./...` (apps/broker) → exit 0
- `go test ./...` (apps/vault-adapter) → exit 0
- `go test ./...` (apps/kong-syncer) → exit 0
- `go test ./...` (apps/proxy-plugin) → exit 0
- `uv run pytest tests/` (packages/python/mintkey-models) → 60 passed, exit 0
- `internal/` directory removed ✓

**Intentionally NOT modified (C-4/C-5 scope):**
- `docker-compose.yml` and `docker-compose.test.yml` build contexts referencing `internal/` (C-4 scope; those files not present at root post-C-4 move)
- Documentation and .kiro references to `internal/` (C-5 scope)

### Next
- Dispatch fresh REVIEWER (Opus) for C-3.
- C-4 IMPLEMENTER can run in parallel (both gated on C-2 only).

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
