# Requirements — Monorepo Structure Cleanup

**Spec name:** `monorepo-structure-cleanup`
**Owner:** architect (CiprianSpot)
**Created:** 2026-05-22
**Branch:** `chore/monorepo-restructure-2026-05-22`
**Companion session:** `remediation/active/2026-05-22-monorepo-structure-cleanup/`
**Scope:** Phases 1, 2, 3, 5, 6 from the mission brief. **Phase 4 (canonical contracts promotion) is explicitly out of scope** for this pass.

---

## R-0 — Invariants

- **R-0.1** No runtime behavior change. This is a structural migration only. All apps must build and run identically before and after.
- **R-0.2** No accepted-ADR edits (`docs/architecture/01-architecture/adr/*` are read-only).
- **R-0.3** No remediation-session deletion. All history-bearing records are archived/moved, never removed.
- **R-0.4** No destructive data operations without explicit owner approval (no `docker volume rm`, no `git push --force` on shared branches, no DB drops).
- **R-0.5** No `Co-Authored-By` trailer on any commit.
- **R-0.6** Every move SHALL have an `EvidenceRef` row in `EVIDENCE_LEDGER.md` explaining (a) why the move is needed and (b) what reference scan confirms the move is safe.
- **R-0.7** Use `git mv` for all renames so history is preserved.
- **R-0.8** Each chunk commit MUST be self-contained: only that chunk's owner-files modified, no stray drive-by edits.

## R-1 — Phase 1: Archive completed remediation noise

- **R-1.1** A new top-level `remediation/` directory SHALL exist with subdirectories `SESSION_TEMPLATE/`, `active/`, and `archive/2026/05/`.
- **R-1.2** `team/remediation/SESSION_TEMPLATE/` (if present) SHALL move to `remediation/SESSION_TEMPLATE/`.
- **R-1.3** The 43 completed remediation sessions currently under `team/remediation/` (dates 2026-05-12 through 2026-05-19) SHALL move to `remediation/archive/2026/05/<session>/` preserving session-folder layout.
- **R-1.4** The current active session `2026-05-22-monorepo-structure-cleanup/` SHALL live at `remediation/active/2026-05-22-monorepo-structure-cleanup/` from the start (this Phase 0 already creates it there).
- **R-1.5** `team/remediation/README.md` (if present) SHALL move to `remediation/README.md`. The "backup before reset" HOWTO (if present at `team/remediation/HOWTO-backup-before-reset.md`) SHALL move to `docs/operations/backup-before-reset.md` if it is operator-facing.
- **R-1.6** After the moves, the top-level `team/` directory MAY be deleted only if it is empty after `.gitkeep` removal; otherwise it stays with a note in `remediation/README.md`.
- **R-1.7** All 285 references to `team/remediation` in tracked files SHALL be either (a) updated to the new path or (b) intentionally preserved with a comment indicating "historical reference to old layout" (e.g., in archived 99-reports that quote the original session path).
- **R-1.8** No remediation-session content SHALL be edited beyond path-reference fixes — the 99-reports/matrices remain historically accurate.

## R-2 — Phase 2: Normalize deployable apps under `apps/`

- **R-2.1** A new top-level `apps/` directory SHALL exist.
- **R-2.2** The following 11 deployable units SHALL move (`git mv`) into `apps/`:
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
- **R-2.3** After R-2.2, the `services/` top-level directory SHALL be deleted (it is empty post-move).
- **R-2.4** `docker-compose.yml` and `docker-compose.test.yml` build contexts SHALL be updated to the new app paths.
- **R-2.5** All Dockerfiles whose paths reference internal directories above the build context SHALL be updated (no Dockerfile is expected to need internal changes since paths are typically relative to the service root).
- **R-2.6** `Makefile` targets that reference old paths SHALL be updated.
- **R-2.7** `.github/workflows/*` paths-filters and step working-directories SHALL be updated.
- **R-2.8** `go.work` `use` directives SHALL be updated for the four Go services (broker, proxy-plugin, kong-syncer, vault-adapter).
- **R-2.9** Go module *import paths* SHALL NOT change unless explicitly required (R-3 has the constraint for `internal/*` imports). The 4 Go service `go.mod` names already point to repo-local paths via `go.work`, so the move is path-only.
- **R-2.10** Python workspace path assumptions in `pyproject.toml` `[tool.uv.workspace]` (if any) SHALL be updated.
- **R-2.11** Tests that reference old paths SHALL be updated; the test must still pass after the path-only edit.
- **R-2.12** `docker compose config` and `docker compose -f docker-compose.test.yml config` SHALL exit 0 after the move.

## R-3 — Phase 3: Normalize shared packages under `packages/`

- **R-3.1** A new `packages/python/` and `packages/go/` SHALL exist.
- **R-3.2** `mintkey-models/` → `packages/python/mintkey-models/` (path-only).
- **R-3.3** The following 7 Go packages SHALL move from `internal/` to `packages/go/`:
  - `internal/audit/` → `packages/go/audit/`
  - `internal/auditq/` → `packages/go/auditq/`
  - `internal/changes/` → `packages/go/changes/`
  - `internal/otelinit/` → `packages/go/otelinit/`
  - `internal/svcid/` → `packages/go/svcid/`
  - `internal/ulid/` → `packages/go/ulid/`
  - `internal/vault/` → `packages/go/vault/`
- **R-3.4** `internal/cfg/` and `internal/models/` are empty placeholder directories with only 1-2 historical references in `.kiro/specs/mintkey-mvp/design.md`. They SHALL be removed (no `git mv`, just `git rm` if tracked; otherwise just delete). The historical references in the kiro spec are an out-of-scope concern; flag in escalations.
- **R-3.5** After R-3.3 + R-3.4, the top-level `internal/` directory SHALL be deleted (it is empty post-move).
- **R-3.6** Go import paths SHALL be updated mechanically: any import beginning with `<module>/internal/<pkg>` → `<module>/packages/go/<pkg>`. Module root assumed to be `github.com/welikecode/mintkey` (or similar — verify against `go.mod`).
- **R-3.7** `go.work` SHALL `use` the new package paths.
- **R-3.8** `go test ./...` from repo root SHALL exit 0 after the moves.
- **R-3.9** Python imports SHALL be unchanged (the package name `mintkey_models` is a Python import, not a path).
- **R-3.10** `pyproject.toml [tool.uv.workspace]` references to `mintkey-models` (if any) SHALL be updated to `packages/python/mintkey-models`.
- **R-3.11** Dockerfile `COPY` paths that reference `mintkey-models/` SHALL be updated to `packages/python/mintkey-models/`.
- **R-3.12** `cd packages/python/mintkey-models && uv run pytest tests/` SHALL exit 0.

## R-5 — Phase 5: Group infra under `infra/`

- **R-5.1** A new top-level `infra/` SHALL exist with subdirectories `compose/`, `observability/`, and `keycloak/`.
- **R-5.2** `docker-compose.yml` → `infra/compose/docker-compose.yml`.
- **R-5.3** `docker-compose.test.yml` → `infra/compose/docker-compose.test.yml`.
- **R-5.4** `prometheus.yml`, `alert_rules.yml`, `otel-collector-config.yaml`, `grafana/` → `infra/observability/{prometheus.yml,alert_rules.yml,otel-collector-config.yaml,grafana/}`.
- **R-5.5** `apps/seed-job/realm-mintkey.json` MAY move to `infra/keycloak/realm-mintkey.json` only if seed-job's Dockerfile / source still reads it cleanly. If the move is risky (in-image relative paths), it SHALL stay in `apps/seed-job/` and the decision SHALL be documented in `03-escalations.md`.
- **R-5.6** A root-level `docker-compose.yml` compatibility wrapper SHALL exist that does `include: - infra/compose/docker-compose.yml` (or equivalent shim that preserves `docker compose up` from repo root). If `include` is not supported on the local Compose version, a symlink `docker-compose.yml -> infra/compose/docker-compose.yml` is acceptable.
- **R-5.7** Makefile targets `make dev`, `make demo`, `make smoke`, `make demo-mock`, `make dev-test`, `make dev-test-down`, `make dev-test-logs`, `make dev-test-reset`, `make smoke-test-ns` SHALL continue to work from repo root with no user-facing command change.
- **R-5.8** Compose volume paths and config mounts SHALL be updated to point at the new infra paths.
- **R-5.9** `docker compose -f infra/compose/docker-compose.yml config` AND `docker compose -f infra/compose/docker-compose.test.yml config` SHALL exit 0.
- **R-5.10** Scripts under `scripts/` that invoke `docker compose` SHALL be updated to either (a) call `docker compose` from repo root (using the shim) or (b) point explicitly at `infra/compose/docker-compose.yml`.

## R-6 — Phase 6: Update docs, Kiro, CI, Makefile, repo maps

- **R-6.1** `README.md` repo-map section SHALL reflect the new layout.
- **R-6.2** `KIRO.md` link hub SHALL be updated (any `apps/`, `packages/`, `infra/` references must resolve).
- **R-6.3** `AGENTS.md` and `CLAUDE.md` SHALL be updated for any path references they contain (e.g., "the service code lives in `services/` " → "in `apps/` ").
- **R-6.4** `.kiro/specs/*` SHALL be updated for stale path references EXCEPT in the canonical kiro-spec files of historical past specs that document state-at-that-time — those keep historical paths with a one-line note.
- **R-6.5** `.kiro/steering/*` SHALL be updated for stale paths.
- **R-6.6** `docs/architecture/00-vision/06-roadmap.md`, `docs/architecture/00-vision/07-kiro-readiness.md`, `docs/HOW-TO.md`, `docs/DEBUG.md`, `docs/DEPLOYMENT.md`, `docs/RELEASE.md`, `docs/NETWORK.md`, `docs/AUTH.md`, `docs/DEV-TEST.md`, `docs/patterns/*` SHALL be path-swept.
- **R-6.7** `PORTS.md` SHALL be updated if it references compose paths.
- **R-6.8** `Makefile` SHALL be the canonical entry point; targets that wrap docker compose SHALL absorb the new compose path.
- **R-6.9** `.github/workflows/*` paths-filters (under `on:.push.paths` and `on:.pull_request.paths`) SHALL be updated.
- **R-6.10** `CODEOWNERS` (if path-scoped) SHALL be updated.
- **R-6.11** `.dockerignore` at repo root and per-service `.dockerignore` SHALL be reviewed for stale references.
- **R-6.12** After R-6, the repo-root file list SHALL be reduced to: `README.md`, `LICENSE`, `CHANGELOG.md`, `SECURITY.md`, `CONTRIBUTING.md`, `AGENTS.md`, `CLAUDE.md`, `KIRO.md`, `Makefile`, `.env.example`, `go.work`, `go.mod` (if still present), `docker-compose.yml` (as compatibility shim per R-5.6), `package.json` (if root-level needed for tooling), `.dockerignore`, `.gitignore`, `.trivyignore`, `CODEOWNERS`, `CODE_OF_CONDUCT.md`, `GOVERNANCE.md`, `SUPPORT.md`, `PORTS.md`, `QUICKSTART.md`. Any other files at root SHALL be documented as intentionally retained OR moved.

## R-7 — Verification gates

- **R-7.1** After each chunk lands, the fresh REVIEWER SHALL replicate the path-scan and confirm no broken references.
- **R-7.2** After all chunks land, the final C-6 REVIEWER SHALL:
  - confirm `go test ./...` exits 0 from repo root (if Go toolchain available)
  - confirm `docker compose config` exits 0 from repo root (if Docker available)
  - confirm `make help` lists all expected targets
  - confirm `make lint-contracts` exits 0
  - replicate the path-reference scan with zero hits for old paths (excluding intentional historical references)
  - confirm no `Co-Authored-By` trailer on any commit
- **R-7.3** Tests not runnable in the current environment (e.g., docker compose if Docker missing, Go tests if toolchain absent) SHALL be documented in `99-report.md` "Tests not run and why".

## Out of scope (intentional)

- **OOS-1** Phase 4 (canonical contracts promotion to `contracts/` at repo root). `docs/architecture/contracts/` stays where it is. Path references to it are NOT updated as part of this pass.
- **OOS-2** Tooling layout (`tools/`, `scripts/`, `bootstrap/`, `ci/` → `tooling/`) is NOT explicitly in the user's move-list. The user's target tree shows `tooling/scripts/`, `tooling/ci/`, etc., but the phases don't cover it. **Decision deferred** to `03-escalations.md` — if owner confirms, a follow-up `tooling/` PR will land after this one.
- **OOS-3** `data/`, `marketing/`, `examples/`, `tests/`, `.kiro/`, `.agents/`, `.claude/`, `.codex/`, `.vscode/`, `.github/` stay where they are.
- **OOS-4** Code style, lint, dependency upgrades — none of these are touched in this pass.
- **OOS-5** Repo-root install logs (`install-*.log`, ~350 files) are untracked already (see baseline inventory); no action needed.
