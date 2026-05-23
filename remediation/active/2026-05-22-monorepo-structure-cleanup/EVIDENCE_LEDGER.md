# Evidence Ledger — Monorepo Structure Cleanup

**Session:** `2026-05-22-monorepo-structure-cleanup`
**Format (mandated by mission brief):**
| EvidenceRef | Source | Current path/state | Proposed path/state | Why move is needed | Risk | Verification |

Each row is one move. EvidenceRef prefix:
- `EV-MOVE-1-*` — Phase 1 (remediation archive)
- `EV-MOVE-2-*` — Phase 2 (apps)
- `EV-MOVE-3-*` — Phase 3 (packages)
- `EV-MOVE-5-*` — Phase 5 (infra)
- `EV-MOVE-6-*` — Phase 6 (docs/Kiro/CI sweep)
- `EV-DEL-*` — deletion (no move target)
- `EV-CREATE-*` — new file (no source)

---

## Phase 1 — Remediation archive (C-1)

| EvidenceRef | Source | Current path/state | Proposed path/state | Why move is needed | Risk | Verification |
|---|---|---|---|---|---|---|
| EV-CREATE-1-001 | EV-INV-004 | (n/a — new) | `remediation/SESSION_TEMPLATE/`, `remediation/active/`, `remediation/archive/2026/05/` | Establish new convention (R-1.1) | None | `find remediation -maxdepth 3 -type d` returns expected layout |
| EV-MOVE-1-002 | EV-PRIOR-001 | `team/remediation/SESSION_TEMPLATE/` (if present) | `remediation/SESSION_TEMPLATE/` | New convention; SESSION_TEMPLATE is the canonical scaffold (R-1.2) | None | `git status` shows rename |
| EV-MOVE-1-003 | EV-INV-004 | `team/remediation/2026-05-12-admin-ui-rework/` | `remediation/archive/2026/05/2026-05-12-admin-ui-rework/` | Completed session; archive (R-1.3) | Possible doc backlinks | `rg -F "team/remediation/2026-05-12-admin-ui-rework"` returns only archived-content hits |
| EV-MOVE-1-004 | EV-INV-004 | `team/remediation/2026-05-13-admin-ui-action-grid/` | `remediation/archive/2026/05/2026-05-13-admin-ui-action-grid/` | Completed session | Same | Same |
| EV-MOVE-1-005..045 | EV-INV-004 | 41 additional dated sessions (2026-05-16-*, 2026-05-17-*, 2026-05-18-*, 2026-05-19-*) | `remediation/archive/2026/05/<session>/` | Completed sessions | Same | Same |
| EV-MOVE-1-046 | EV-PRIOR-001 | `team/remediation/README.md` (if present) | `remediation/README.md` | Index for new convention (R-1.5) | None | File diff |
| EV-MOVE-1-047 | EV-PRIOR-001 | `team/remediation/HOWTO-backup-before-reset.md` (if present) | `docs/operations/backup-before-reset.md` (default per E-5.B) | Operator-facing runbook; promote to canonical user docs (R-1.5) | Backlinks from `docs/AUTH.md`, `docs/NETWORK.md` | C-1 implementer updates referrers; `rg -F "team/remediation/HOWTO"` returns 0 |
| EV-DEL-1-048 | EV-INV-004 | `team/.gitkeep`, `team/` | (deleted if empty) | Clean root (R-1.6) | None | `ls -la` confirms removal |

---

## Phase 2 — Apps move (C-2)

| EvidenceRef | Source | Current path/state | Proposed path/state | Why move is needed | Risk | Verification |
|---|---|---|---|---|---|---|
| EV-CREATE-2-001 | EV-INV-001 | (n/a — new) | `apps/` | Standard monorepo layout (R-2.1) | None | `ls apps/` |
| EV-MOVE-2-002 | EV-REF-001 | `admin-api/` | `apps/admin-api/` | Normalize deployables (R-2.2) | 134 referrers; Dockerfile COPY paths | `docker compose -f infra/compose/docker-compose.yml config` exit 0; `rg -F "admin-api/" --type-not md` only-archived hits |
| EV-MOVE-2-003 | EV-REF-002 | `admin-ui/` | `apps/admin-ui/` | Same | 88 referrers; node_modules; pnpm-workspace | Same |
| EV-MOVE-2-004 | EV-REF-003 | `mcp-server/` | `apps/mcp-server/` | Same | 60 referrers | Same |
| EV-MOVE-2-005 | EV-REF-004 | `mock-backend/` | `apps/mock-backend/` | Same | 33 referrers | Same |
| EV-MOVE-2-006 | EV-REF-005 | `seed-job/` | `apps/seed-job/` | Same; `realm-mintkey.json` stays here per CD-2 | 33 referrers | Same |
| EV-MOVE-2-007 | EV-REF-006 | `audit-verify-job/` | `apps/audit-verify-job/` | Same | 12 referrers | Same |
| EV-MOVE-2-008 | EV-REF-007 | `jaeger-auth/` | `apps/jaeger-auth/` | Same | 16 referrers; entrypoint.sh | Same |
| EV-MOVE-2-009 | EV-REF-008 | `services/broker/` | `apps/broker/` | Normalize all deployables to one level (R-2.2) | 39 referrers; Go module via go.work | `go work sync && go build ./...` exit 0 |
| EV-MOVE-2-010 | EV-REF-009 | `services/proxy-plugin/` | `apps/proxy-plugin/` | Same | 55 referrers; Kong plugin Go module | Same |
| EV-MOVE-2-011 | EV-REF-010 | `services/kong-syncer/` | `apps/kong-syncer/` | Same | 37 referrers | Same |
| EV-MOVE-2-012 | EV-REF-011 | `services/vault-adapter/` | `apps/vault-adapter/` | Same | 38 referrers; gRPC stubs | Same |
| EV-DEL-2-013 | EV-INV-001 | `services/` (empty after move) | (deleted) | Clean root (R-2.3) | None | `ls services/` → not found |
| EV-MOVE-2-014 | EV-INV-007 | `docker-compose.yml` (build contexts) | edited in place at root, MOVED later to `infra/compose/` by C-4 | C-2 updates build contexts; C-4 moves the file (R-2.4) | Compose schema | `docker compose config` exit 0 |
| EV-MOVE-2-015 | EV-INV-007 | `docker-compose.test.yml` (same) | Same | Same | Same | Same |
| EV-MOVE-2-016 | EV-INV-008 | `go.work` `use` directives | `use ./apps/broker`, `use ./apps/proxy-plugin`, `use ./apps/kong-syncer`, `use ./apps/vault-adapter` | go.work must reflect new paths (R-2.8) | Module resolution | `go work sync` exit 0 |

---

## Phase 3 — Packages move (C-3) — gated on C-2

| EvidenceRef | Source | Current path/state | Proposed path/state | Why move is needed | Risk | Verification |
|---|---|---|---|---|---|---|
| EV-CREATE-3-001 | EV-INV-002 | (n/a — new) | `packages/python/`, `packages/go/` | Standard layout for shared libs (R-3.1) | None | `ls packages/` |
| EV-MOVE-3-002 | EV-REF-012 | `mintkey-models/` | `packages/python/mintkey-models/` | Shared Python package (R-3.2) | 58 referrers; pyproject workspace; Dockerfile COPY | `cd packages/python/mintkey-models && uv run pytest tests/` exit 0 |
| EV-MOVE-3-003 | EV-REF-013 | `internal/audit/` | `packages/go/audit/` | Shared Go pkg used by 4 services (R-3.3) | 37 referrers; Go import paths | `go test ./...` exit 0 |
| EV-MOVE-3-004 | EV-REF-014 | `internal/auditq/` | `packages/go/auditq/` | Same | 15 referrers | Same |
| EV-MOVE-3-005 | EV-REF-015 | `internal/changes/` | `packages/go/changes/` | Same | 28 referrers | Same |
| EV-MOVE-3-006 | EV-REF-016 | `internal/otelinit/` | `packages/go/otelinit/` | Same | 11 referrers | Same |
| EV-MOVE-3-007 | EV-REF-017 | `internal/svcid/` | `packages/go/svcid/` | Same | 3 referrers | Same |
| EV-MOVE-3-008 | EV-REF-018 | `internal/ulid/` | `packages/go/ulid/` | Same | 6 referrers | Same |
| EV-MOVE-3-009 | EV-REF-019 | `internal/vault/` | `packages/go/vault/` | Same | 13 referrers | Same |
| EV-DEL-3-010 | EV-INV-006 + EV-REF-020 | `internal/cfg/` (empty) | (deleted) | Empty placeholder; only doc-ref is historical (R-3.4 + E-1.A default) | None | `ls internal/cfg/` → not found |
| EV-DEL-3-011 | EV-INV-006 + EV-REF-021 | `internal/models/` (empty) | (deleted) | Same | None | Same |
| EV-DEL-3-012 | EV-INV-002 | `internal/` (empty after moves) | (deleted) | Clean root (R-3.5) | None | `ls internal/` → not found |
| EV-MOVE-3-013 | EV-INV-008 | `go.work` `use` directives | adds `use ./packages/go/<pkg>` for 7 pkgs | go.work must list package paths (R-3.7) | Module resolution | `go work sync` exit 0 |

---

## Phase 5 — Infra grouping (C-4) — gated on C-2

| EvidenceRef | Source | Current path/state | Proposed path/state | Why move is needed | Risk | Verification |
|---|---|---|---|---|---|---|
| EV-CREATE-5-001 | EV-INV-003 | (n/a — new) | `infra/compose/`, `infra/observability/`, `infra/keycloak/` | Group infra config (R-5.1) | None | `ls infra/` |
| EV-MOVE-5-002 | EV-REF-022 | `docker-compose.yml` (post-C-2 edits) | `infra/compose/docker-compose.yml` | Group with infra (R-5.2) | 79 referrers | `docker compose -f infra/compose/docker-compose.yml config` exit 0 |
| EV-MOVE-5-003 | EV-REF-023 | `docker-compose.test.yml` (post-C-2 edits) | `infra/compose/docker-compose.test.yml` | Same (R-5.3) | 10 referrers | Same |
| EV-MOVE-5-004 | EV-REF-024 | `prometheus.yml` | `infra/observability/prometheus.yml` | Group with observability (R-5.4) | 6 referrers; compose mount | Same |
| EV-MOVE-5-005 | EV-REF-025 | `alert_rules.yml` | `infra/observability/alert_rules.yml` | Same | 4 referrers | Same |
| EV-MOVE-5-006 | EV-REF-026 | `otel-collector-config.yaml` | `infra/observability/otel-collector-config.yaml` | Same | 14 referrers | Same |
| EV-MOVE-5-007 | EV-REF-027 | `grafana/` | `infra/observability/grafana/` | Same | 15 referrers; provisioning paths in compose | Same |
| EV-CREATE-5-008 | CD-1 | (n/a — new shim) | root `docker-compose.yml` with `include: - ./infra/compose/docker-compose.yml` (or symlink) | Preserve `docker compose up` from repo root (R-5.6) | Compose version mismatch (handled by fallback to symlink) | `docker compose config` from repo root exit 0 |
| EV-KEEP-5-009 | CD-2 | `apps/seed-job/realm-mintkey.json` | (STAY — no move) | Dockerfile COPY context constraint (CD-2 + E-3.A) | None | Documented in 99-report |

---

## Phase 6 — Docs/Kiro/CI sweep (C-5)

| EvidenceRef | Source | Current path/state | Proposed path/state | Why update | Risk | Verification |
|---|---|---|---|---|---|---|
| EV-MOVE-6-001 | EV-REF-001..033 | All stale paths in `README.md`, `KIRO.md`, `AGENTS.md`, `CLAUDE.md`, `docs/**`, `.kiro/**`, `.github/workflows/**`, `CODEOWNERS`, `Makefile`, `PORTS.md`, `.dockerignore` | rewritten to new paths | Docs and tooling must reflect new layout (R-6.1..R-6.11) | Doc cross-links, mermaid render | `rg -F "<old-path>"` returns only archived-content hits |
| EV-CREATE-6-002 | R-6.12 | `docs/operations/backup-before-reset.md` | (new file from E-5.B move) | Operator runbook canonical location | Backlinks from AUTH.md, NETWORK.md | `rg -F "team/remediation/HOWTO"` returns 0 |

---

## Coverage check

Final C-6 reviewer SHALL confirm every move row has:
- A verification command run.
- An exit code captured.
- A path-reference scan with expected results.

If any row's verification was NOT executable in the current environment (e.g., `docker compose config` if Docker missing): document in 99-report "Tests not run and why".
