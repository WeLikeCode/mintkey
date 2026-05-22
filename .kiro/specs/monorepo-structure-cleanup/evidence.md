# Evidence Ledger — Monorepo Structure Cleanup

**Spec name:** `monorepo-structure-cleanup`
**Format:** Each row maps a requirement to the current-state evidence that justifies the deliverable.

**Prefix namespace:**
- `EV-INV-*` — baseline inventory observation (this Kiro spec's C-0 baseline)
- `EV-REF-*` — path-reference scan count
- `EV-PRIOR-*` — prior session artifact establishing the convention to align with
- `EV-RISK-*` — risk catalog entry referenced by a requirement

---

## Baseline inventory (captured 2026-05-22, branch `chore/monorepo-restructure-2026-05-22` off `main @ 590cb78`)

| EvidenceRef | Source | Observation |
|---|---|---|
| EV-INV-001 | `find . -maxdepth 2 -mindepth 1` | Repo root has 11 service dirs at top level (admin-api, admin-ui, mcp-server, mock-backend, seed-job, audit-verify-job, jaeger-auth) + 4 under `services/` (broker, kong-syncer, proxy-plugin, vault-adapter) |
| EV-INV-002 | `find . -maxdepth 2 -mindepth 1` | Repo root has 1 Python shared pkg (`mintkey-models/`) + 9 Go internal pkgs under `internal/` (audit, auditq, cfg, changes, models, otelinit, svcid, ulid, vault) |
| EV-INV-003 | `find . -maxdepth 2 -mindepth 1` | Repo root has 2 compose files, 3 observability files, 1 grafana dir |
| EV-INV-004 | `find team/remediation -maxdepth 1 -type d -name '20*'` | 44 dated remediation sessions (2026-05-12 → 2026-05-19); the 2026-05-22 session is created freshly under `remediation/active/` |
| EV-INV-005 | `git ls-files install-*.log` | 0 install logs are git-tracked; the ~350 root-level install logs are local-only noise (gitignored) |
| EV-INV-006 | `ls internal/cfg/ internal/models/` | Both directories are EMPTY (no tracked files). Only 1-2 historical references in `.kiro/specs/mintkey-mvp/design.md`. Safe to delete in C-3 |

## Path-reference scan (against git-tracked text files only)

| EvidenceRef | Path | Files-with-ref | Occurrences | Notes |
|---|---|---|---|---|
| EV-REF-001 | `admin-api/` | 134 | 313 | Most-referenced single path; C-2 highest blast radius |
| EV-REF-002 | `admin-ui/` | 88 | 313 | C-2 |
| EV-REF-003 | `mcp-server/` | 60 | 116 | C-2 |
| EV-REF-004 | `mock-backend/` | 33 | 54 | C-2 |
| EV-REF-005 | `seed-job/` | 33 | 76 | C-2 |
| EV-REF-006 | `audit-verify-job/` | 12 | 15 | C-2 |
| EV-REF-007 | `jaeger-auth/` | 16 | 33 | C-2 |
| EV-REF-008 | `services/broker` | 39 | 57 | C-2 |
| EV-REF-009 | `services/proxy-plugin` | 55 | 106 | C-2 |
| EV-REF-010 | `services/kong-syncer` | 37 | 61 | C-2 |
| EV-REF-011 | `services/vault-adapter` | 38 | 63 | C-2 |
| EV-REF-012 | `mintkey-models/` | 58 | 111 | C-3 |
| EV-REF-013 | `internal/audit` | 37 | 96 | C-3 (Go imports + docs) |
| EV-REF-014 | `internal/auditq` | 15 | 52 | C-3 |
| EV-REF-015 | `internal/changes` | 28 | 48 | C-3 |
| EV-REF-016 | `internal/otelinit` | 11 | 14 | C-3 |
| EV-REF-017 | `internal/svcid` | 3 | 4 | C-3 |
| EV-REF-018 | `internal/ulid` | 6 | 6 | C-3 |
| EV-REF-019 | `internal/vault` | 13 | 14 | C-3 |
| EV-REF-020 | `internal/cfg` | 1 | 1 | EMPTY dir, doc-only ref; C-3 deletes |
| EV-REF-021 | `internal/models` | 1 | 2 | EMPTY dir, doc-only ref; C-3 deletes |
| EV-REF-022 | `docker-compose.yml` | 79 | 163 | C-4 |
| EV-REF-023 | `docker-compose.test.yml` | 10 | 28 | C-4 |
| EV-REF-024 | `prometheus.yml` | 6 | 20 | C-4 |
| EV-REF-025 | `alert_rules.yml` | 4 | 12 | C-4 |
| EV-REF-026 | `otel-collector-config.yaml` | 14 | 22 | C-4 |
| EV-REF-027 | `grafana/` | 15 | 32 | C-4 |
| EV-REF-028 | `team/remediation` | 86 | 285 | C-1 (most refs are inside session 99-reports — historical, CD-4 says leave) |
| EV-REF-029 | `contracts/` | 111 | 393 | **OUT OF SCOPE** — Phase 4 deferred |
| EV-REF-030 | `tools/` | 72 | 323 | OOS-2; tooling/ consolidation deferred |
| EV-REF-031 | `scripts/` | 57 | 197 | OOS-2; tooling/ consolidation deferred |
| EV-REF-032 | `bootstrap/` | 12 | 35 | OOS-2 |
| EV-REF-033 | `ci/` | 7 | 9 | OOS-2 |

## Build manifests (informs Go/Python workspace updates)

| EvidenceRef | Source | Observation |
|---|---|---|
| EV-INV-007 | `git ls-files '*.mod'` | 5 `go.mod` files: 1 at root, 4 under `services/<svc>/`. C-2 moves the 4 to `apps/<svc>/`. C-3 doesn't touch any `go.mod` (only imports). |
| EV-INV-008 | `git ls-files 'go.work'` | 1 `go.work` at root. C-2 and C-3 both rewrite `use` directives. |
| EV-INV-009 | `git ls-files 'pyproject.toml'` | 4 pyproject files: admin-api, mcp-server, mintkey-models, mock-backend. C-3 may update workspace refs. |
| EV-INV-010 | `git ls-files 'package.json'` | 4 package.json: admin-ui (incl. pnpm-workspace), admin-ui/e2e, examples/typescript-agent-snippet, root. C-2 moves admin-ui's tree intact. |

## Prior-session artifacts (convention alignment)

| EvidenceRef | Source | Convention to preserve |
|---|---|---|
| EV-PRIOR-001 | `team/remediation/2026-05-19-post-prealpha-readiness/` (PR #88) | 8-file session layout (ISSUE_INTAKE, 00-plan, 01-orchestrator-chunks, 02-matrix, 03-escalations, 04-progress, 99-report, EVIDENCE_LEDGER) |
| EV-PRIOR-002 | `team/remediation/2026-05-18-codescanning-master/` | Multi-session campaign structure — informs how to archive the S1-S11 family together |
| EV-PRIOR-003 | `.kiro/specs/post-prealpha-readiness/` (PR #88) | Spec pattern: 4-file `{requirements,design,tasks,evidence}.md` layout |
| EV-PRIOR-004 | `team/remediation/2026-05-17-doc-state-sync/` | Doc-sweep pattern — informs C-5 |

## Risks referenced by this spec

| EvidenceRef | Description | Phase |
|---|---|---|
| EV-RISK-001 | Dockerfile COPY paths breaking after move | C-2 |
| EV-RISK-002 | Hidden refs in generated code (protobuf-go) | C-3 |
| EV-RISK-003 | Mass-move conflicting with in-flight dependabot PRs | all |
| EV-RISK-004 | `make demo` user-facing command breaking | C-4 |
| EV-RISK-005 | `team/remediation` references inside historical 99-reports → false-positive on stale-path scan | C-1 |

## Coverage check (post-implementation, run before C-6)

The C-6 final reviewer SHALL confirm every requirement R-1.* through R-7.* maps to a landed deliverable AND that every move row in `EVIDENCE_LEDGER.md` has a verification command + exit code.
