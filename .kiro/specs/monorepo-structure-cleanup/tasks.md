# Tasks — Monorepo Structure Cleanup

**Spec name:** `monorepo-structure-cleanup`
**Created:** 2026-05-22
**Convention:** `[ ]` open, `[x]` done. Each task is one atomic deliverable. Checkpoint/verification tasks (5, 12, 17) flip after their chunk's implementer commits AND the chunk reviewer passes.

---

## Wave 0 — Orchestrator bootstrap (C-0)

- [x] 0.1 — Sync `main` and confirm clean worktree (R-0.1, R-0.7)
- [x] 0.2 — Create branch `chore/monorepo-restructure-2026-05-22`
- [x] 0.3 — Run baseline inventory (`find`, `git ls-files`, path-reference scan)
- [x] 0.4 — Author Kiro spec — `requirements.md`, `design.md`, `tasks.md`, `evidence.md`
- [x] 0.5 — Scaffold remediation session — `ISSUE_INTAKE.md`, `00-plan.md`, `01-orchestrator-chunks.md`, `02-matrix.md`, `03-escalations.md`, `04-progress.md`, `99-report.md`, `EVIDENCE_LEDGER.md`
- [x] 0.6 — Commit Phase 0 (spec + session scaffold + branch baseline)

## Wave 1 — Remediation archive (C-1)

- [x] 1.1 — Create `remediation/{SESSION_TEMPLATE,active,archive/2026/05}` directory tree (R-1.1)
- [x] 1.2 — `git mv team/remediation/SESSION_TEMPLATE/ remediation/SESSION_TEMPLATE/` (R-1.2; skip if not present)
- [x] 1.3 — `git mv team/remediation/<each-dated-session>/ remediation/archive/2026/05/<session>/` for all 43 archived sessions (R-1.3)
- [x] 1.4 — Active session at `remediation/active/2026-05-22-monorepo-structure-cleanup/` already in place from C-0 (R-1.4) — verify only
- [x] 1.5 — `git mv team/remediation/README.md remediation/README.md` if present; move any `HOWTO-backup-before-reset.md` to `docs/operations/backup-before-reset.md` if operator-facing (R-1.5)
- [x] 1.6 — Remove `team/.gitkeep` and `team/` directory if empty post-move (R-1.6)
- [x] 1.7 — Sweep references to `team/remediation/` in non-session tracked files (README, KIRO, AGENTS, CLAUDE, Makefile, docs, .kiro, .github/workflows) → update to `remediation/{archive/2026/05,active,…}/` paths (R-1.7)
- [x] 1.8 — Path-reference verification: `git ls-files | xargs grep -l "team/remediation" | grep -v archive/2026/05/` must be empty (or each remaining hit documented as historical) (R-1.8, R-7.1)
- [ ] **5 — CHECKPOINT C-1 reviewer PASS** (R-7.1)

## Wave 1 (parallel) — Apps move (C-2)

- [x] 2.1 — Create `apps/` directory (R-2.1)
- [x] 2.2 — `git mv <each-service>/ apps/<service>/` for all 11 services (R-2.2)
- [x] 2.3 — `git rm` empty `services/` directory after the 4 services move out (R-2.3)
- [x] 2.4 — Update `docker-compose.yml` and `docker-compose.test.yml` build contexts to `./apps/<service>` (R-2.4)
- [x] 2.5 — Audit Dockerfiles for paths above build context (typically none — verify) (R-2.5)
- [x] 2.6 — Update `Makefile` targets referencing old paths (R-2.6)
- [x] 2.7 — Update `.github/workflows/*` `paths:` filters and `working-directory:` (R-2.7)
- [x] 2.8 — Update `go.work` `use` directives for broker/proxy-plugin/kong-syncer/vault-adapter (R-2.8)
- [x] 2.9 — Verify Go module identity unchanged (no go.mod path renames required) (R-2.9)
- [x] 2.10 — Update Python workspace path assumptions (R-2.10)
- [x] 2.11 — Update tests that hardcoded paths (R-2.11)
- [x] 2.12 — Verification: `docker compose -f docker-compose.yml config` and `-f docker-compose.test.yml config` exit 0 (R-2.12)
- [ ] **12 — CHECKPOINT C-2 reviewer PASS** (R-7.1)

## Wave 2 — Packages move (C-3) — gated on C-2

- [ ] 3.1 — Create `packages/{python,go}/` directory tree (R-3.1)
- [ ] 3.2 — `git mv mintkey-models/ packages/python/mintkey-models/` (R-3.2)
- [ ] 3.3 — `git mv internal/<pkg>/ packages/go/<pkg>/` for 7 Go packages (R-3.3)
- [ ] 3.4 — Delete empty `internal/cfg/` and `internal/models/` (R-3.4)
- [ ] 3.5 — Remove empty `internal/` top-level (R-3.5)
- [ ] 3.6 — Rewrite Go imports: `<mod>/internal/<pkg>` → `<mod>/packages/go/<pkg>` (R-3.6)
- [ ] 3.7 — Update `go.work` `use` directives for new package paths (R-3.7)
- [ ] 3.8 — Verification: `go work sync && go test ./...` exit 0 (R-3.8)
- [ ] 3.9 — Python import names unchanged — verify (R-3.9)
- [ ] 3.10 — Update `pyproject.toml [tool.uv.workspace]` references (R-3.10)
- [ ] 3.11 — Update Dockerfile `COPY mintkey-models/ ...` → `COPY packages/python/mintkey-models/ ...` (R-3.11)
- [ ] 3.12 — Verification: `cd packages/python/mintkey-models && uv run pytest tests/` exit 0 (R-3.12)

## Wave 2 — Infra grouping (C-4) — gated on C-2

- [ ] 4.1 — Create `infra/{compose,observability,keycloak}/` directory tree (R-5.1)
- [ ] 4.2 — `git mv docker-compose.yml infra/compose/docker-compose.yml` (R-5.2)
- [ ] 4.3 — `git mv docker-compose.test.yml infra/compose/docker-compose.test.yml` (R-5.3)
- [ ] 4.4 — `git mv {prometheus.yml,alert_rules.yml,otel-collector-config.yaml} infra/observability/` (R-5.4)
- [ ] 4.5 — `git mv grafana/ infra/observability/grafana/` (R-5.4)
- [ ] 4.6 — Decision per CD-2: `realm-mintkey.json` stays in `apps/seed-job/` (no move; document in 99-report)
- [ ] 4.7 — Create root `docker-compose.yml` shim per CD-1 (include or symlink) (R-5.6)
- [ ] 4.8 — Verify Makefile targets still work: `make help`, `make dev`, `make demo`, `make smoke`, dev-test family (R-5.7)
- [ ] 4.9 — Update Compose volume paths / config mounts to new infra paths (R-5.8)
- [ ] 4.10 — Verification: `docker compose -f infra/compose/docker-compose.yml config` and `-f infra/compose/docker-compose.test.yml config` exit 0 (R-5.9)
- [ ] 4.11 — Update `scripts/*` that call `docker compose -f docker-compose.yml` (R-5.10)

## Wave 3 — Docs/Kiro/CI sweep (C-5)

- [ ] 6.1 — Update `README.md` repo map (R-6.1)
- [ ] 6.2 — Update `KIRO.md` link hub (R-6.2)
- [ ] 6.3 — Update `AGENTS.md` and `CLAUDE.md` (R-6.3)
- [ ] 6.4 — Sweep `.kiro/specs/*` for stale paths (R-6.4)
- [ ] 6.5 — Sweep `.kiro/steering/*` for stale paths (R-6.5)
- [ ] 6.6 — Sweep `docs/` (HOW-TO, DEBUG, DEPLOYMENT, RELEASE, NETWORK, AUTH, DEV-TEST, patterns, architecture/00-vision) (R-6.6)
- [ ] 6.7 — Update `PORTS.md` if it references compose paths (R-6.7)
- [ ] 6.8 — Confirm `Makefile` targets reflect new paths (R-6.8)
- [ ] 6.9 — Update `.github/workflows/*` paths-filters (R-6.9)
- [ ] 6.10 — Update `CODEOWNERS` (R-6.10)
- [ ] 6.11 — Audit root + per-service `.dockerignore` (R-6.11)
- [ ] 6.12 — Confirm repo-root file list matches R-6.12 inventory (R-6.12)

## Wave 4 — Final reviewer (C-6)

- [ ] **17 — CHECKPOINT C-6 final reviewer PASS** (R-7.2)
  - go test ./... (or document why not run)
  - docker compose config (or document why not run)
  - make help / make lint-contracts
  - stale-path scan results (`team/remediation`, `internal/`, `services/`, top-level service dirs, top-level compose, top-level observability)
  - red-team grep clean
  - ADR no-edit check
  - no Co-Authored-By trailer
