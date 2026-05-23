# 99-report — Monorepo Structure Cleanup

**Session:** `2026-05-22-monorepo-structure-cleanup`
**Branch:** `chore/monorepo-restructure-2026-05-22`
**Status:** **CLOSED** — C-6 round-3 PASS_ALL.
**Closed:** 2026-05-22
**Baseline:** `590cb78` (main, tag `v0.1.0-preview.1`) → **HEAD:** post-conftest-fix (22 commits since baseline).

---

## Outcome

The Mintkey monorepo is restructured for clarity. Phases 1, 2, 3, 5, 6 from the mission brief are implemented; **phase 4 (canonical contracts promotion) is deferred** as instructed. Runtime behavior is preserved (R-0.1 honored). The PR is ready to open.

## Final tree summary

```
mintkey/
  apps/
    admin-api/  admin-ui/  mcp-server/  mock-backend/
    seed-job/   audit-verify-job/  jaeger-auth/
    broker/  proxy-plugin/  kong-syncer/  vault-adapter/
  packages/
    python/mintkey-models/
    go/{audit,auditq,changes,otelinit,svcid,ulid,vault}/
  infra/
    compose/{docker-compose.yml, docker-compose.test.yml}
    observability/{prometheus.yml, alert_rules.yml, otel-collector-config.yaml, grafana/}
    keycloak/.gitkeep                # placeholder; realm-mintkey.json stays in apps/seed-job/ per CD-2
  remediation/
    SESSION_TEMPLATE/
    active/2026-05-22-monorepo-structure-cleanup/
    archive/2026/05/                 # 46 archived sessions
  docs/  tests/  examples/  marketing/  archetypes/  data/
  .github/  .kiro/  .agents/  .claude/  .codex/  .vscode/
  docker-compose.yml                 # root shim: include: - ./infra/compose/docker-compose.yml
  README.md  LICENSE  CHANGELOG.md  SECURITY.md  CONTRIBUTING.md
  AGENTS.md  CLAUDE.md  KIRO.md  Makefile  go.work  go.mod  go.sum  go.work.sum
  PORTS.md  QUICKSTART.md  CODEOWNERS  CODE_OF_CONDUCT.md  GOVERNANCE.md  SUPPORT.md
  BOOTSTRAP.md  PROGRESS.md  Agentic_Architectural_Approach.md  ORCHESTRATION_STATE.md
  .dockerignore  .gitignore  .trivyignore  .env.example
  package.json  package-lock.json    # root tooling
  install.sh
```

## Files / directories moved (counts per phase)

| Phase | Moves | Notes |
|---|---|---|
| Phase 1 (C-1) | 46 sessions + SESSION_TEMPLATE + README + HOWTO + ISSUE_INTAKE_TEMPLATE → `remediation/`; `docs/operations/backup-before-reset.md` created (E-5.B); `team/` removed | 21 non-session files swept for path-ref updates |
| Phase 2 (C-2) | 11 apps moved to `apps/`; `services/` removed; `go.work` use-directives updated | strike-2 reverted drive-by `go.mod`/`go.sum` dep bumps |
| Phase 3 (C-3) | 1 Python pkg + 7 Go pkgs → `packages/`; 20 `.go` files import-rewritten; 6 Dockerfile COPY paths; `internal/` removed | `vault.pb.go` rawDesc preserved byte-identically (proto regen OOS) |
| Phase 5 (C-4) | 5 file moves + grafana/ dir to `infra/`; root `docker-compose.yml` shim via Compose `include:` (CD-1); 10 build-context updates + 7 volume-mount updates inside compose | `realm-mintkey.json` stays in apps/seed-job/ per CD-2 |
| Phase 6 (C-5) | 57 docs/Kiro/CI/config files swept | strike-1 missed 6 stale paths (Makefile/CI/dependabot/QUICKSTART/docs/.gitignore); strike-2 fixed those; strike-3 fixed ~38 broken pytest runtime path constructors |
| Phase 6 (C-5.5) | root `go.mod`/`go.sum` MVS sync with workspace (one-time) | Option A — accept the natural MVS-propagated bumps (grpc/x/net/x/sys/x/text + indirects); they were already in `apps/*/go.mod` |
| Phase 6 (C-7 orchestrator residual cleanup) | 5 test runtime paths (grafana/prometheus.yml/otel-collector-config/internal/auditq) + 1 Kiro `fileMatchPattern` + 1 `apps/mcp-server/tests/conftest.py` `parents[N]` indexing | Strike-3 search list missed this token class; C-6 round-2 reviewer caught conftest issue |

## Compatibility decisions taken

| ID | Decision | Outcome |
|---|---|---|
| CD-1 | Root `docker-compose.yml` shim | `include:` directive (Compose v5.1.4 supports it; no symlink needed) |
| CD-2 | `realm-mintkey.json` location | Stays in `apps/seed-job/` (Dockerfile COPY context constraint). `infra/keycloak/.gitkeep` is a directory-symmetry placeholder |
| CD-3 | `tooling/` consolidation (E-2.A) | DEFERRED — out of scope this PR; follow-up candidate |
| CD-4 | Historical refs in archived 99-reports | Left as-is; only non-archive references swept |
| CD-5 | Root `go.mod` retained | Yes, kept (workspace-mode decoupled; C-5.5 sync makes it consistent) |
| CD-6 | Go import rewrite policy | Mechanical sed for `<mod>/internal/<pkg>` → `<mod>/packages/go/<pkg>`; one binary protobuf rawDesc reverted to preserve length prefix |

## Commits (oldest → newest, 22 total since baseline `590cb78`)

| SHA | Subject | Chunk |
|---|---|---|
| `e477369` | C-0 — Kiro spec + remediation session scaffold | C-0 |
| `b9b3733` | C-1 — archive 44 remediation sessions to `remediation/archive/2026/05/` | C-1 impl |
| `ce3870d` | C-2 — move 11 deployable apps to apps/ | C-2 strike-1 |
| `dda501a` | C-2 — update matrix with commit SHA ce3870d | C-2 bookkeeping |
| `5196bbf` | C-1 reviewer PASS — bookkeeping + matrix SHA fixup | C-1 reviewer-PASS |
| `188c870` | C-2 strike-2 — revert go.mod/go.sum to pre-restructure pinning | C-2 strike-2 |
| `f27dafb` | C-2 strike-2 — update matrix with commit SHA 188c870 | C-2 bookkeeping |
| `df48155` | C-3 — move shared packages to packages/{python,go}/ + rewrite Go imports | C-3 impl |
| `f369132` | C-3 — update matrix with commit SHA df48155 | C-3 bookkeeping |
| `0e0de41` | C-4 — group compose + observability under infra/ + root shim | C-4 impl |
| `c1ca13c` | C-4 — update matrix with commit SHA 0e0de41 | C-4 bookkeeping |
| `fc036b9` | C-3 + C-4 reviewer PASS — bookkeeping | reviewer-PASS |
| `3a1a420` | C-5 — sweep docs/Kiro/CI for stale paths | C-5 strike-1 |
| `f890bfa` | C-5 — record commit SHA in 02-matrix.md | C-5 bookkeeping |
| `4fa8819` | C-5.5 — sync root go.mod with workspace MVS (one-time post-restructure) | C-5.5 |
| `287e745` | C-5.5 bookkeeping — matrix + progress + tasks for go.mod sync | C-5.5 bookkeeping |
| `296a0d8` | C-5 strike-2 — fix 6 stale-path misses | C-5 strike-2 |
| `3a143b8` | C-5 strike-2 — record strike-2 SHA in 02-matrix.md | C-5 bookkeeping |
| `5f51301` | C-5 strike-3 — fix ~38 test files with broken runtime path constructors | C-5 strike-3 |
| `8340dce` | C-5 strike-3 — record commit SHA in bookkeeping | C-5 bookkeeping |
| `abac09b` | orchestrator residual cleanup — 5 test runtime paths + 1 Kiro fileMatchPattern | C-7 orchestrator |
| `_this commit_` | session close — C-6 round-3 PASS_ALL + apps/mcp-server/tests/conftest.py parents[N] fix + 99-report | C-7 + checkpoint 17 |

## Verification (R-7.2)

| Check | Result |
|---|---|
| `git diff 590cb78..HEAD --stat -- docs/architecture/01-architecture/adr/ docs/architecture/adrs/` | empty (R-0.2 ✓) |
| Actual `Co-Authored-By:` trailers in `git log 590cb78..HEAD` | 0 (R-0.5 ✓) |
| `docker compose config` (root shim) | exit 0 |
| `docker compose -f infra/compose/docker-compose.yml config` | exit 0 |
| `docker compose -f infra/compose/docker-compose.yml -f infra/compose/docker-compose.test.yml config` | exit 0 |
| `go work sync` | exit 0; idempotent (empty diff against `go.mod` / `go.sum` after C-5.5) |
| `go test ./...` (root + 4 service sub-modules) | exit 0 |
| `python3 -m pytest tests/ --collect-only` (repo-root tests) | exit 0, **738 tests** |
| `cd apps/mcp-server && uv run pytest tests/ --collect-only` | exit 0, **132 tests** (baseline-matched) |
| `cd packages/python/mintkey-models && uv run pytest tests/` | exit 0, **60 passed** + 1 pre-existing DeprecationWarning |

## Tests not run and why

- `make help` / `make -n test-unit` / `make -n lint-python` / `make lint-contracts` — all hit the **pre-existing** Makefile line-18 `*** multiple target patterns. Stop.` error from `.PHONY:` + colon-pattern target names (e.g., `test:e2e`). Verified byte-identical at `590cb78` baseline. NOT a regression introduced by this PR.
- Live integration tests (`docker compose up` + smoke) — owner-gated; reviewer verified config syntax only.
- `apps/seed-job` local pytest — fails with pyodbc/anaconda metadata error on this dev's machine. Verified identical at baseline; pre-existing local-env issue, NOT a regression.

## Stale-path scan summary

All remaining tokens in the final-state grep are EITHER:
- Inside `remediation/archive/2026/05/**` (historical 99-reports — CD-4)
- Inside `.kiro/specs/long-lived-api-keys/{design,tasks}.md` or `.kiro/specs/mintkey-mvp/{design,tasks}.md` — DRAFT specs with mixed-prefix references (long-lived-api-keys lines 230/321/322; mintkey-mvp line 357). Both blocked on respective ADR work; non-blocking; **follow-up candidates** to normalize in a small cleanup PR.
- Display strings (Makefile echo line 114; CI step labels; QUICKSTART section heading; dependabot group name) — labels, not paths
- Comments-in-code (e.g., `apps/broker/internal/metrics/metrics.go:6,49` references `internal/auditq/metrics.go` in design comments)
- Historical mentions in `CHANGELOG.md`, `PROGRESS.md`, `BOOTSTRAP.md` (preserved as history)

## Residual risks (non-blocking)

1. **Draft kiro specs** (`long-lived-api-keys`, `mintkey-mvp`) have mixed-prefix references inside table rows / task narratives. Owners should sweep at next edit.
2. **Pre-existing Makefile line-18 error** — `*** multiple target patterns. Stop.` from `.PHONY:` with `test:e2e` colon patterns. Affects `make help` etc. on GNU make 3.81 (macOS default). Fix is to escape or rename the colon-pattern targets in a separate small PR. NOT introduced by this PR.
3. **C-5.5 root `go.mod` MVS sync** — bumped grpc 1.80→1.81, x/net 0.52→0.53, x/sys 0.42→0.44, x/text 0.35→0.37 plus testify indirects. These versions were already required by `apps/proxy-plugin/go.mod` and `apps/vault-adapter/go.mod`; this PR only propagates them to the root for `go work sync` idempotency. Worth surfacing in PR description.
4. **`apps/broker/internal/metrics/metrics.go` design-note comments** reference `internal/auditq/metrics.go` (now `packages/go/auditq/metrics.go`). Cosmetic; doc-comment only.
5. **`packages/go/audit/emit_test.go:4`** test docstring `(internal/audit is the single audit chokepoint)` cosmetic.
6. **`apps/admin-ui/e2e/tests/26-smoke-regression.spec.ts`** references `team/remediation/ADMIN_UI_SPEC.md` (an untracked historical artifact). Outside C-1 owner-file scope; left untouched.
7. **Per-developer `.venv/` shebangs** under `apps/admin-api/`, `apps/mcp-server/`, `packages/python/mintkey-models/` have absolute paths hardcoded at virtualenv-creation time. After pulling this branch, devs need to `rm -rf <svc>/.venv && uv sync`. Local-machine state, not in-repo.

## Follow-up plan for phase 4 (canonical contracts)

Out of scope this PR. Recommended approach:
- `contracts/` is currently at repo root with content under `contracts/{asyncapi,fixtures,jsonschema,openapi}/`.
- `docs/architecture/contracts/` exists separately (this PR did NOT touch it).
- A follow-up PR should decide which is the canonical home, consolidate, and update the 393 references found in the baseline path-reference scan.
- Sequencing: do this as its own dedicated session (orchestrator pattern recommended given the reference count).

## Follow-up plan for root files intentionally left in place

R-6.12 specified a reduced root file list. Items currently at root NOT in that list:
- `BOOTSTRAP.md`, `Agentic_Architectural_Approach.md`, `ORCHESTRATION_STATE.md`, `PROGRESS.md` — root-level project narrative; could move to `docs/` in a follow-up cleanup but they are referenced as repo-root files in multiple places; defer.
- `archetypes/`, `marketing/`, `data/`, `install.sh` — intentionally retained per OOS-3.
- `node_modules/`, `package.json`, `package-lock.json` — root tooling (e.g., bats test-runner). Intentionally retained.
- Per-developer caches `.hypothesis/`, `.pytest_cache/`, `.ruff_cache/`, `.serena/`, `.mintkey-backups/` — local-only, all gitignored.
- ~313 untracked `install-*.log` files — gitignored per EV-INV-005; no action needed.
- `tooling/` consolidation (E-2.A) — DEFERRED to a follow-up `chore(repo): tooling/ consolidation` PR.

## Per-chunk reviewer evidence

- **C-1**: round-1 fresh Opus REVIEWER → PASS (1 nit: matrix SHA placeholder; fixed in bookkeeping commit).
- **C-2**: round-1 → FAIL strike-1 (go.mod/go.sum drive-by bumps); strike-2 reverted → PASS.
- **C-3**: round-1 → PASS (notable: `vault.pb.go` rawDesc revert documented as OOS proto-regen).
- **C-4**: round-1 → PASS (notable: pre-existing Makefile line-18 not a C-4 regression — git-blame verified).
- **C-5**: round-1 → FAIL strike-1 (6 stale paths); strike-2 → PASS but then C-6 round-1 caught wider regression → strike-3 fixed ~38 test files.
- **C-5.5**: orchestrator inline-verified (Option A chosen + verified).
- **C-7 (orchestrator residual cleanup)**: round-2 C-6 caught one more (apps/mcp-server/tests/conftest.py parents[N]) → fixed → round-3 PASS_ALL.

## Process notes (for retrospective)

The C-5 reviewer rounds caught issues incrementally:
1. **C-5 strike-1 reviewer**: searched docs/Makefile/CI/dependabot/QUICKSTART/.gitignore. Missed Python runtime path constructors in tests.
2. **C-6 round-1**: caught the test path regression (~38 files) but only enumerated `mintkey-models`/`admin-api`/`seed-job`/`audit-verify-job` cases.
3. **C-6 round-2**: caught `apps/mcp-server/tests/conftest.py` `parents[N]` indexing AND additional `grafana`/`prometheus.yml`/`otel-collector-config`/`internal/auditq` test path constants that strike-3's pattern didn't cover.

**Lesson**: stale-path reviewer scans should always include the FULL set of moved tokens, not the subset the implementer happened to enumerate. The C-6 round-1 review's substitution-list enumeration matched the strike-3 implementer's pattern, so they both missed the same class. A reviewer that recomputed the full token list from `EVIDENCE_LEDGER.md` would have caught this in round-1.

## Ready for PR

Owner can open the PR via the Mintkey proxy with the following branch:
- Branch: `chore/monorepo-restructure-2026-05-22`
- Title: `chore(repo): monorepo restructure — apps/, packages/, infra/, remediation/ layout (phases 1+2+3+5+6; phase 4 deferred)`
- Body: this report's "Outcome", "Files / directories moved", "Compatibility decisions", "Verification", and "Residual risks" sections.

Per the user's earlier choice, PR open is deferred until C-6 PASS_ALL — which is the state at this commit.
