# Chunk Catalog — Monorepo Structure Cleanup

**Session:** `2026-05-22-monorepo-structure-cleanup`
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → fresh REVIEWERs Opus → final reviewer)

---

## Hard rules (carry to every chunk)

- No accepted-ADR edits (`docs/architecture/01-architecture/adr/**` read-only).
- No real secrets in any example.
- Every move uses `git mv` (history-preserving).
- Every move has an EvidenceRef row in `EVIDENCE_LEDGER.md` BEFORE the move.
- tasks.md checkboxes flip in the SAME COMMIT as the deliverable.
- Validate via tools (run commands; don't claim PASS without exit codes).
- No `Co-Authored-By` trailer.
- No `--no-verify`.

---

## C-0 — Bootstrap (ORCHESTRATOR)

| Field | Value |
|---|---|
| Owner | ORCHESTRATOR Opus (this turn) |
| Owner files | `.kiro/specs/monorepo-structure-cleanup/*`, `remediation/active/2026-05-22-monorepo-structure-cleanup/*`, branch creation |
| EvidenceRefs | EV-INV-001..010, EV-REF-001..033 |
| Tools | `git fetch`, `git checkout -b`, `find`, `git ls-files`, `grep -F`, `Write` |
| Forbidden | Any code moves; any path-reference rewrites |

### DoD
- Branch `chore/monorepo-restructure-2026-05-22` exists.
- 4 spec files written.
- 8 session files written.
- Baseline inventory captured in `EVIDENCE_LEDGER.md` and `evidence.md`.
- Single commit "chore(repo): C-0 — Kiro spec + remediation session scaffold for monorepo-structure-cleanup".

---

## C-1 — Remediation archive (IMPLEMENTER)

| Field | Value |
|---|---|
| Owner | IMPLEMENTER Sonnet |
| Owner files | `team/remediation/**`, `remediation/**` (post-C-0), references-to-team/remediation in: `README.md`, `KIRO.md`, `AGENTS.md`, `CLAUDE.md`, `Makefile`, `docs/**`, `.kiro/**`, `.github/workflows/**` |
| EvidenceRefs | EV-INV-004, EV-REF-028, EV-PRIOR-001..004 |
| Tools | `git mv`, `mkdir -p`, `git rm` (empty `team/.gitkeep`), `rg -F "team/remediation"`, `sed -i.bak` for non-historical reference updates |
| Forbidden | Editing session 99-reports/matrices (historical content); editing any service code; touching `apps/`, `packages/`, `infra/`, `docker-compose*` |

### DoD
- Directory tree `remediation/{SESSION_TEMPLATE,active/,archive/2026/05/}` exists.
- All 43 dated sessions from `team/remediation/2026-05-*/` moved to `remediation/archive/2026/05/<session>/`.
- `team/remediation/SESSION_TEMPLATE/` (if present) moved to `remediation/SESSION_TEMPLATE/`.
- `team/remediation/README.md` (if present) moved to `remediation/README.md`.
- `team/` deleted if empty (after `.gitkeep` removal); otherwise documented.
- All non-historical references to `team/remediation/` updated to new paths.
- Verification: `git ls-files | xargs grep -l "team/remediation"` returns ONLY archived session files (historical-quote context); zero hits in `README.md`, `KIRO.md`, `AGENTS.md`, `CLAUDE.md`, `Makefile`, `docs/`, `.github/workflows/`.
- Atomic commit `chore(repo): C-1 — archive 43 remediation sessions to remediation/archive/2026/05/`.

---

## C-2 — Apps move (IMPLEMENTER)

| Field | Value |
|---|---|
| Owner | IMPLEMENTER Sonnet |
| Owner files | `apps/**` (new), `services/**` (during move), 11 top-level service dirs (during move), `docker-compose.yml`, `docker-compose.test.yml`, `Makefile`, `.github/workflows/**`, `go.work`, Dockerfiles, test files referencing paths |
| EvidenceRefs | EV-INV-001, EV-REF-001..011, EV-INV-007..008, EV-PRIOR-001 |
| Tools | `git mv`, `git rm` (empty `services/`), `rg -F` (path-ref scan), `sed -i.bak` for compose/Makefile/workflow updates, `docker compose -f <path> config` (verification) |
| Forbidden | Touching `internal/`, `mintkey-models/`, `team/remediation/`, `remediation/`, `infra/`; editing observability config; changing Go module identity (only `go.work use` directive) |

### Move list (atomic; preserve history)

| From | To |
|---|---|
| `admin-api/` | `apps/admin-api/` |
| `admin-ui/` | `apps/admin-ui/` |
| `mcp-server/` | `apps/mcp-server/` |
| `mock-backend/` | `apps/mock-backend/` |
| `seed-job/` | `apps/seed-job/` |
| `audit-verify-job/` | `apps/audit-verify-job/` |
| `jaeger-auth/` | `apps/jaeger-auth/` |
| `services/broker/` | `apps/broker/` |
| `services/proxy-plugin/` | `apps/proxy-plugin/` |
| `services/kong-syncer/` | `apps/kong-syncer/` |
| `services/vault-adapter/` | `apps/vault-adapter/` |

### Path-reference updates required
- `docker-compose.yml`: every `build: { context: ./<svc> }` and `build: { context: ./services/<svc> }` → `./apps/<svc>` (also `dockerfile:` paths if relative).
- `docker-compose.test.yml`: same as above.
- `.github/workflows/*.yml`: `on.*.paths:` patterns referencing service dirs (e.g., `'admin-api/**'` → `'apps/admin-api/**'`); `working-directory:` references.
- `Makefile`: any target that `cd`s into a service dir.
- `go.work`: `use ./services/broker` → `use ./apps/broker` (and the 3 others).
- Tests: any `pytest` fixture or `os.path` reference to old paths.

### DoD
- 11 `git mv` operations completed.
- `services/` directory removed (empty after move).
- All path references updated (compose, Makefile, workflows, go.work, tests).
- Verification: `docker compose -f docker-compose.yml config` exit 0; `docker compose -f docker-compose.test.yml config` exit 0.
- Path-ref scan: zero hits for `services/broker`, `services/proxy-plugin`, etc. in non-archived files; zero hits for `./admin-api`, `./admin-ui` etc. as compose contexts.
- Atomic commit `chore(repo): C-2 — move 11 deployable apps to apps/`.

---

## C-3 — Packages move (IMPLEMENTER) — gated on C-2

| Field | Value |
|---|---|
| Owner | IMPLEMENTER Sonnet |
| Owner files | `packages/**` (new), `mintkey-models/` (during move), `internal/**` (during move + delete), `*.go` (for import rewrites), `pyproject.toml` (workspace), `go.work`, Dockerfile `COPY` lines for `mintkey-models/` |
| EvidenceRefs | EV-INV-002, EV-REF-012..021, EV-INV-006 (empty dirs), EV-RISK-002 |
| Tools | `git mv`, `git rm -rf` (empty `internal/cfg/`, `internal/models/`, `internal/`), `find . -name '*.go' \| xargs sed -i.bak`, `go work sync`, `go test ./...`, `uv run pytest tests/` |
| Forbidden | Touching `apps/` source code (only Dockerfile COPY lines if needed); touching `team/remediation/`, `remediation/`, `infra/`, `docker-compose*` |

### Move list

| From | To |
|---|---|
| `mintkey-models/` | `packages/python/mintkey-models/` |
| `internal/audit/` | `packages/go/audit/` |
| `internal/auditq/` | `packages/go/auditq/` |
| `internal/changes/` | `packages/go/changes/` |
| `internal/otelinit/` | `packages/go/otelinit/` |
| `internal/svcid/` | `packages/go/svcid/` |
| `internal/ulid/` | `packages/go/ulid/` |
| `internal/vault/` | `packages/go/vault/` |
| `internal/cfg/` | (delete — empty) |
| `internal/models/` | (delete — empty) |
| `internal/` | (delete — empty post-move) |

### Path-reference updates required
- Go imports: `<module>/internal/<pkg>` → `<module>/packages/go/<pkg>` mechanically across `*.go` (and `*.go.tmpl` if any). Module root determined from `go.mod` at repo root (likely `github.com/welikecode/mintkey`).
- `go.work` `use` directives.
- `pyproject.toml [tool.uv.workspace]` if it lists `mintkey-models`.
- Dockerfile `COPY mintkey-models/ ...` (admin-api, mcp-server, seed-job, audit-verify-job — verify) → `COPY packages/python/mintkey-models/ ...` (or adjust build context accordingly).
- Doc references in `docs/`, `.kiro/specs/mintkey-mvp/design.md`, etc. (Some refs are historical and should stay — flag in escalations if uncertain.)

### DoD
- 8 `git mv` operations completed.
- `internal/` removed.
- All Go imports rewritten.
- `go work sync` exit 0.
- `go test ./...` exit 0 (from repo root).
- `cd packages/python/mintkey-models && uv run pytest tests/` exit 0.
- `cd packages/python/mintkey-models && uv run mypy --strict mintkey_models/` exit 0.
- Path-ref scan: zero hits for `mintkey-models/` or `internal/<pkg>` in non-archived files.
- Atomic commit `chore(repo): C-3 — move shared packages to packages/{python,go}/`.

---

## C-4 — Infra grouping (IMPLEMENTER) — gated on C-2

| Field | Value |
|---|---|
| Owner | IMPLEMENTER Sonnet |
| Owner files | `infra/**` (new), `docker-compose.yml` (split into shim + moved), `docker-compose.test.yml`, `prometheus.yml`, `alert_rules.yml`, `otel-collector-config.yaml`, `grafana/`, `scripts/*.sh` that call `docker compose -f ...` |
| EvidenceRefs | EV-INV-003, EV-REF-022..027, CD-1, CD-2 |
| Tools | `git mv`, `Write` (root compose shim), `docker compose -f <path> config`, `make help`, `make -n demo` (dry run) |
| Forbidden | Touching `apps/` source, `packages/`, `team/remediation/`, `remediation/`; changing observability semantics (only file location) |

### Move list

| From | To |
|---|---|
| `docker-compose.yml` | `infra/compose/docker-compose.yml` |
| `docker-compose.test.yml` | `infra/compose/docker-compose.test.yml` |
| `prometheus.yml` | `infra/observability/prometheus.yml` |
| `alert_rules.yml` | `infra/observability/alert_rules.yml` |
| `otel-collector-config.yaml` | `infra/observability/otel-collector-config.yaml` |
| `grafana/` | `infra/observability/grafana/` |
| `apps/seed-job/realm-mintkey.json` | **NO MOVE** per CD-2 (Docker COPY context constraint) |

### Compose shim (CD-1)

Create new root `docker-compose.yml`:
```yaml
include:
  - ./infra/compose/docker-compose.yml
```
If `docker compose version` < 2.20.0 (no `include:` support): create a relative symlink `docker-compose.yml -> infra/compose/docker-compose.yml`. Test with `docker compose config` from repo root.

### Compose internal updates
- Volume mounts referencing `./prometheus.yml` etc. → relative paths from `infra/compose/docker-compose.yml` (so `../observability/prometheus.yml`).
- `grafana/provisioning/...` mount → `../observability/grafana/provisioning/...`.

### DoD
- 5 file/dir `git mv` operations completed.
- `infra/keycloak/` exists as empty directory with `.gitkeep` (so future moves have a slot).
- Root `docker-compose.yml` shim exists and works.
- `docker compose -f infra/compose/docker-compose.yml config` exit 0.
- `docker compose -f infra/compose/docker-compose.test.yml config` exit 0.
- `docker compose config` (from repo root, using shim) exit 0.
- `make help` lists all expected targets.
- `make -n demo` (dry run) shows correct paths.
- Path-ref scan: zero hits for top-level `prometheus.yml`, `alert_rules.yml`, etc. outside `infra/` and `archive/2026/05/`.
- Atomic commit `chore(repo): C-4 — group compose + observability under infra/`.

---

## C-5 — Docs/Kiro/CI sweep (IMPLEMENTER) — gated on C-2, C-3, C-4

| Field | Value |
|---|---|
| Owner | IMPLEMENTER Sonnet |
| Owner files | `README.md`, `KIRO.md`, `AGENTS.md`, `CLAUDE.md`, `docs/**`, `.kiro/**` (except current spec/session), `.github/workflows/**`, `CODEOWNERS`, `Makefile`, `PORTS.md`, `.dockerignore`, per-service `.dockerignore` if changed |
| EvidenceRefs | EV-INV-001..010, EV-REF-001..033, all prior chunks' moves |
| Tools | `rg`, `sed -i.bak`, `Edit` (precise rewrites), `make help`, render-test for mermaid blocks if changed |
| Forbidden | Editing accepted ADRs; editing archived session content; touching `apps/`, `packages/`, `infra/` source/config (only path refs in docs) |

### Sweep targets (non-exhaustive — find with rg)
- `README.md` repo-map: rewrite.
- `KIRO.md` link hub: update repo-tree section.
- `AGENTS.md`: any "service code lives in services/" type references.
- `CLAUDE.md`: same.
- `docs/HOW-TO.md`, `docs/DEBUG.md`, `docs/DEPLOYMENT.md`, `docs/RELEASE.md`, `docs/NETWORK.md`, `docs/AUTH.md`, `docs/DEV-TEST.md`, `docs/patterns/*`, `docs/architecture/00-vision/{06-roadmap,07-kiro-readiness}.md`: all swept.
- `PORTS.md`: compose path refs.
- `Makefile`: confirm all paths now point at new locations (most updated in C-2/C-4; final pass here).
- `.github/workflows/*.yml`: paths-filters confirmed.
- `CODEOWNERS`: path-scoped entries.
- Root `.dockerignore` + per-service `.dockerignore`.

### DoD
- `rg -F "team/remediation"` returns only archived-session-internal hits.
- `rg -F "services/"` returns only archived/historical hits.
- `rg -F "internal/audit"`, `"internal/auditq"`, etc. — same.
- `rg -F "./admin-api"`, `"./admin-ui"`, etc. — same.
- `rg -F "./docker-compose.yml"` from root — only the shim and archived hits.
- `rg -F "./prometheus.yml"` — only `infra/` references and archived hits.
- `make help` lists expected targets.
- `make lint-contracts` exit 0.
- Atomic commit `chore(repo): C-5 — sweep docs/Kiro/CI for stale paths`.

---

## C-6 — Final fresh REVIEWER

| Field | Value |
|---|---|
| Owner | fresh REVIEWER Opus (no prior context of this session) |
| Read-only | YES — no commits; reports PASS/FAIL with reproducible commands |
| EvidenceRefs | all |
| Tools | `git diff origin/main..HEAD`, `git log --oneline origin/main..HEAD`, `rg`, `go test ./...`, `docker compose config`, `make help`, `make lint-contracts` |

### Checks
1. Diff scope: every chunk's diff is contained to its owner-files in `01-orchestrator-chunks.md`.
2. tasks.md final state: every actionable `[ ]` flipped to `[x]`. Checkpoint tasks 5/12/17 flipped.
3. Red-team grep: `rg "mk_agent_[A-Z0-9]{50,}"`, `rg "mk_svckey_[A-Z0-9]{30,}"`, `rg "mk_agentkey_[A-Z0-9]{20,}"` — zero NEW hits in this PR.
4. ADR no-edit: `git diff --stat origin/main..HEAD -- docs/architecture/01-architecture/adr/` empty.
5. No Co-Authored-By trailer in any commit.
6. Stale-path scan (replicate C-5's verification).
7. Behavior preservation: `docker compose config` exit 0; `go test ./...` exit 0; `make help` shows expected targets.
8. EVIDENCE_LEDGER.md has a row for every move in the PR diff.

### Outcomes
- PASS_ALL → ORCHESTRATOR opens PR.
- FAIL → list the failing items; ORCHESTRATOR dispatches strike-2 implementer for the relevant chunk(s).
