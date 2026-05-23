# Design — Monorepo Structure Cleanup

**Spec name:** `monorepo-structure-cleanup`
**Created:** 2026-05-22
**Branch:** `chore/monorepo-restructure-2026-05-22`
**Companion session:** `remediation/active/2026-05-22-monorepo-structure-cleanup/`

---

## Goal

Reorganize the Mintkey repository top-level into a conventional monorepo layout — `apps/` for deployables, `packages/` for shared libraries, `infra/` for compose+observability, `remediation/` (replacing `team/remediation/`) for session records — without changing any runtime behavior. Phase 4 (canonical contracts promotion) is intentionally deferred to a follow-up.

## Target layout

```
mintkey/
  apps/
    admin-api/  admin-ui/  mcp-server/  mock-backend/
    seed-job/  audit-verify-job/  jaeger-auth/
    broker/  proxy-plugin/  kong-syncer/  vault-adapter/
  packages/
    python/mintkey-models/
    go/{audit,auditq,changes,otelinit,svcid,ulid,vault}/
  infra/
    compose/{docker-compose.yml,docker-compose.test.yml}
    observability/{prometheus.yml,alert_rules.yml,otel-collector-config.yaml,grafana/}
    keycloak/realm-mintkey.json    # only if move is safe (R-5.5)
  remediation/
    SESSION_TEMPLATE/
    active/2026-05-22-monorepo-structure-cleanup/
    archive/2026/05/<43 archived sessions>/
  docs/   examples/   tests/   marketing/
  .kiro/  .agents/  .claude/  .codex/  .vscode/  .github/
  README.md  LICENSE  CHANGELOG.md  SECURITY.md  CONTRIBUTING.md
  AGENTS.md  CLAUDE.md  KIRO.md  Makefile  .env.example
  go.work  (go.mod if still at root)
  docker-compose.yml  (compatibility shim per R-5.6)
```

## Workstream layout

This work is decomposed into 5 chunks (C-1..C-5) plus the bootstrap (C-0) and a final reviewer (C-6). Dependencies dictate the wave order:

```
Wave 0 (ORCHESTRATOR, this turn):
  C-0  Kiro spec + session + branch creation + baseline inventory

Wave 1 (IMPLEMENTERs, parallel — no shared files):
  C-1  Remediation archive               (touches team/remediation/, remediation/, doc path refs to it)
  C-2  Apps move                          (touches apps/, top-level service dirs, services/, compose, Makefile, .github/workflows/, Dockerfiles, go.work)

Wave 1 review (fresh REVIEWERs):
  C-1 reviewer    C-2 reviewer

Wave 2 (IMPLEMENTERs, parallel — gated on C-2):
  C-3  Packages move                      (touches mintkey-models/, internal/, packages/, go.work, Go imports, Python pyproject)
  C-4  Infra grouping                     (touches docker-compose*, prometheus.yml, otel-collector-config.yaml, grafana/, alert_rules.yml, infra/, scripts/ that call compose)

Wave 2 review:
  C-3 reviewer    C-4 reviewer

Wave 3 (IMPLEMENTER):
  C-5  Docs/Kiro/CI sweep                 (touches README, KIRO, AGENTS, CLAUDE, docs/, .kiro/, .github/, CODEOWNERS, Makefile)

Wave 3 review:
  C-5 reviewer

Wave 4 (final REVIEWER):
  C-6  Full-session audit, stale-path scan, behavior-preservation evidence
```

Each implementer commits on the same branch (`chore/monorepo-restructure-2026-05-22`). Each reviewer reads the implementer's diff but has no commit authority — they emit PASS / FAIL with reproducible commands.

## Compatibility decisions (documented up-front)

### CD-1: Root `docker-compose.yml` as a shim (R-5.6)

After Phase 5, `infra/compose/docker-compose.yml` is the canonical compose file. To preserve the user-facing `docker compose up -d` from the repo root, we create a root-level `docker-compose.yml` that uses Compose's `include:` directive:

```yaml
include:
  - ./infra/compose/docker-compose.yml
```

This avoids requiring the user to type `-f infra/compose/docker-compose.yml` every time. If `include:` is not supported on the local Compose version, fall back to a relative symlink (`ln -s infra/compose/docker-compose.yml docker-compose.yml`).

Verification: `docker compose config` from repo root SHALL produce the same output before and after the move (modulo line-noise like absolute paths).

### CD-2: Keycloak realm-mintkey.json stays under apps/seed-job/

The seed-job Dockerfile / Python code typically `COPY realm-mintkey.json` from the build context. Moving the file to `infra/keycloak/` requires either (a) widening the build context to repo root (security regression — exposes everything) or (b) `COPY ../../infra/keycloak/realm-mintkey.json` (not allowed in Docker without buildkit's `--build-context` flag). The cleanest path is to **leave `realm-mintkey.json` in `apps/seed-job/`** and document a symlink/copy from `infra/keycloak/` for discoverability. Decision: keep in `apps/seed-job/`; do not symlink; document in `99-report.md`.

### CD-3: `tooling/` consolidation deferred

The user's target tree shows `tooling/{scripts,ci,bootstrap,dev}` but no phase explicitly assigns it. Mass-moving these directories is high-blast-radius (~600 refs combined across scripts/tools/bootstrap/ci). This pass leaves them at root. Escalated for owner decision in `03-escalations.md`.

### CD-4: Old-path references in archived 99-reports

Many of the 285 references to `team/remediation/` live INSIDE archived session 99-reports that quote the original path (e.g., "Session: `team/remediation/2026-05-17-jaeger-cookie-b64`"). These are historical artifacts — the 99-report described the path AT THE TIME. We do NOT rewrite these. Instead, the C-1 implementer rewrites only references in NON-session files (README, KIRO.md, docs, Makefile, .github/workflows/, .kiro/) AND any 99-reports that explicitly reference still-active session paths.

### CD-5: `go.mod` at repo root

There is a top-level `go.mod` in addition to the four service-specific ones. The user's target tree includes `go.mod` at root as optional. We keep it as-is — it's used for `go.work` consistency. Phase 3 only updates the four service `go.mod` files if their internal paths are referenced (they're not — they each declare their own module).

### CD-6: Go import path policy

The four Go services (broker, proxy-plugin, kong-syncer, vault-adapter) currently import from `<module>/internal/<pkg>`. After C-3 moves them to `packages/go/<pkg>`, every import line `<module>/internal/<pkg>` becomes `<module>/packages/go/<pkg>`. This is mechanical sed. The implementer SHALL use `find ... -name '*.go' | xargs sed -i.bak 's|/internal/|/packages/go/|g'` with care (preview first) and remove `.bak` files post-validation.

If `<module>/internal/<pkg>` paths are also referenced from tests or generated code, those get the same treatment.

## Chunk-by-chunk file ownership

| Chunk | Owner files (exclusive write authority) | Cross-references (read-only allowed) |
|---|---|---|
| C-0 | `.kiro/specs/monorepo-structure-cleanup/*`, `remediation/active/2026-05-22-monorepo-structure-cleanup/*` | entire repo (baseline inventory) |
| C-1 | `team/remediation/**`, `remediation/**` (post-C-0), references in `README.md`, `KIRO.md`, `AGENTS.md`, `CLAUDE.md`, `docs/`, `Makefile`, `.kiro/`, `.github/workflows/` ONLY where the reference is to `team/remediation/` | none mutating |
| C-2 | `apps/**`, `services/**` (during the move only — empty after), `admin-api/`, `admin-ui/`, `mcp-server/`, `mock-backend/`, `seed-job/`, `audit-verify-job/`, `jaeger-auth/` (deleting after `git mv`), `docker-compose.yml`, `docker-compose.test.yml`, `Makefile`, `.github/workflows/`, `go.work`, Dockerfiles, tests referencing old paths | C-1's `remediation/**` (read-only) |
| C-3 | `packages/**`, `mintkey-models/` (during move only), `internal/**` (during move only), `go.work`, `*.go` (for import rewrites), `pyproject.toml`, Dockerfile `COPY` lines for moved packages | C-2's `apps/**` |
| C-4 | `infra/**`, `docker-compose.yml`, `docker-compose.test.yml`, `prometheus.yml`, `alert_rules.yml`, `otel-collector-config.yaml`, `grafana/`, `apps/seed-job/realm-mintkey.json` (decision per CD-2), `scripts/` (only those that call `docker compose`), root `docker-compose.yml` shim | C-2's `apps/**`, C-3's `packages/**` |
| C-5 | `README.md`, `KIRO.md`, `AGENTS.md`, `CLAUDE.md`, `docs/**`, `.kiro/**` (except current spec/session), `.github/workflows/**`, `CODEOWNERS`, `Makefile`, `PORTS.md`, `.dockerignore` (root + per-service if changed) | all preceding chunks' changes |
| C-6 | (no writes — final reviewer only) | entire repo |

## Tools and conventions

- **`git mv`** for every move (preserves history).
- **`find ... -name '*.go' | xargs sed -i.bak ...`** for mechanical Go import rewrites (preview with `grep -rE` first, validate post-rewrite with `go test ./...`).
- **`docker compose -f <path> config`** for compose validation.
- **`go work sync`** + **`go test ./...`** for Go validation.
- **`uv run pytest tests/`** for Python validation per package (only the moved one needs re-run).
- **`rg`** for path-reference scans across the repo.
- **Red-team-grep** patterns to confirm no real secrets leaked (carryover from prior sessions): `rg "mk_agent_[A-Z0-9]{50,}"`, `rg "mk_svckey_[A-Z0-9]{30,}"`, `rg "mk_agentkey_[A-Z0-9]{20,}"`.

## Hard stops

- Any unresolved import/path break after 3 implementer attempts on the same chunk → ORCHESTRATOR escalates to owner.
- Any need to edit accepted ADRs → STOP.
- Any destructive data operation → STOP and ask.
- Any uncertainty about canonical contract location → STOP (this pass treats Phase 4 as out-of-scope; if a path move would force a Phase-4-like decision, escalate).
- Any CI path update that cannot be verified locally → land the change behind a comment block flagging the un-verifiable step + escalate.

## Reviewer checklist (per chunk)

The fresh REVIEWER (Opus) for each chunk SHALL:

1. Read the chunk's owner-file list from `01-orchestrator-chunks.md` and confirm the diff touches ONLY those files.
2. Replicate the chunk's verification commands and capture exit codes.
3. Run a path-reference scan: `rg -F "<old-path>"` for every move in the chunk. Each remaining reference must be either (a) a historical mention in an archived 99-report (acceptable), or (b) explicitly documented in `EVIDENCE_LEDGER.md`.
4. Confirm no `Co-Authored-By:` trailer.
5. Confirm no ADR edits: `git diff origin/main..HEAD -- docs/architecture/01-architecture/adr/` empty.
6. Emit PASS or FAIL with the strike count.

If FAIL: ORCHESTRATOR dispatches a strike-2 implementer with the specific fixes needed. After 3 strikes on the same chunk: hard stop.

## Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Dockerfile COPY paths break | M | H | Build each service image after the move; CI also validates |
| `docker compose config` fails | L | H | Validate after each compose-touching chunk |
| Go import-rewrite typos | M | M | `go test ./...` after the sed; reviewer re-runs |
| Hidden references in generated code (e.g., protobuf-go) | L | M | scan generated files; regenerate if necessary |
| `team/remediation/` symlinks/junctions on case-insensitive macOS FS | L | L | use `git mv` (case-aware) |
| Mass moves break in-flight dependabot PRs | M | L | document; conflicts are mechanical to resolve |
| `make demo` breaks because compose moved | M | M | CD-1 shim covers this; verify before merge |

## Coverage map (requirements → chunks)

- R-0.* → all chunks (invariants)
- R-1.* → C-1
- R-2.* → C-2
- R-3.* → C-3
- R-5.* → C-4
- R-6.* → C-5
- R-7.* → C-6 (final) + per-chunk fresh reviewer
