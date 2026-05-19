# Post-Prealpha Readiness — Closing Report

**Session:** `2026-05-19-post-prealpha-readiness`
**Branch:** `feature/post-prealpha-readiness-2026-05-19` (from `main @ a16aed0`)
**Status:** **CLOSED** — all 14 actionable kiro tasks implemented; 19/19 deliverables exist; red-team grep clean; ADR-no-edit invariant held.
**Closed:** 2026-05-19

## Outcome

The full kiro spec at `.kiro/specs/post-prealpha-readiness/` (21 requirements, 14 actionable tasks across 6 waves) is implemented in 6 atomic commits on `feature/post-prealpha-readiness-2026-05-19`. The session followed the orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus) with logical-file groups (C-2..C-6) rewriting the spec's wave-based parallelism to avoid intra-branch merge conflicts on shared files (`SECURITY.md`, `06-roadmap.md`).

## Commits (oldest → newest)

| SHA | Subject | Chunk | Kiro tasks |
|---|---|---|---|
| `4dff4c2` | docs(session): scaffold post-prealpha-readiness session + commit kiro spec | C-1 | (spec ingest) |
| `5967d10` | docs(roadmap): fix backup/restore claim + add EvidenceRefs + evidence.md | C-2 | 2.1, 2.2, 2.3 |
| `275b5aa` | feat(demo): add make demo + make demo-mock targets + scripts/demo-mock-flow.sh | C-4 | 6.1, 6.2 |
| `12a6486` | docs(security): add Scorecard dismissal steps, resolve GO-2026-4918, weak-hash migration doc | C-3 | 3.1, 3.2, 3.3, 3.4, 4.1 |
| `bcac857` | docs(builder-b1): agent-never-sees-secret walkthrough, agent snippets, OpenAI-compat, DEBUG.md +6 | C-5 | 7.1, 8.1, 9.1, 10.1, 11.1 |
| `d5d0771` | docs(kiro): KIRO.md link hub, pattern library (3 docs), stubs plan, kiro-readiness updates | C-6 | 13.1, 14.1-3, 15.1, 16.1 |

## Deliverables (19 new/modified files)

### WS-1 — Documentation accuracy

- `docs/architecture/00-vision/06-roadmap.md` — Section 1 backup/restore claim fixed; 46 EvidenceRef parentheticals added across Sections 1 + 3 (C-2)
- `.kiro/specs/post-prealpha-readiness/evidence.md` — NEW, 24-row claim-to-evidence table (C-2)

### WS-2 — Security residual closure

- `SECURITY.md` — appended: 8× "GitHub UI Dismissal Steps" subsections, resolved GO-2026-XXXX → **GO-2026-4918** (CVE-2026-33814, `golang.org/x/net` HTTP/2 infinite loop, patched at v0.53.0 — dep-bump follow-up documented), "Audit hash chain integrity" section, "Fixable Scorecard residuals — backlog" section, weak-hash acceptance + revisit criterion (C-3)
- `docs/architecture/01-architecture/security-notes/weak-hash-migration.md` — NEW (new directory); 3 CodeQL sites + risk assessment + accept-for-prealpha + revisit trigger (C-3)

### WS-3 — Builder B-1 experience

- `Makefile` — `make demo` (Docker check + `up -d` + 180s health-poll + success banner) and `make demo-mock` (auto-start + run `scripts/demo-mock-flow.sh`); never destructive (C-4)
- `scripts/demo-mock-flow.sh` — NEW, 247 lines, shellcheck-clean; PAT-free mock-backend demo end-to-end; redacts all `mk_agent_*` and JWTs in stdout (C-4)
- `docs/guides/agent-never-sees-secret.md` — NEW, 269 lines; 6-section structured walkthrough proving zero credential exposure (C-5)
- `examples/python-agent-snippet/{agent.py, requirements.txt, README.md}` — NEW, ~40-line Python agent using httpx (C-5)
- `examples/typescript-agent-snippet/{agent.ts, package.json, tsconfig.json, README.md}` — NEW, ~40-line TS agent using native fetch (C-5)
- `examples/openai-compatible/{README.md, register-service.sh, agent.py}` — NEW; OpenAI SDK against Mintkey proxy (C-5)
- `docs/DEBUG.md` — appended 6 entries (§11–16): Stack not running, KEK mismatch, Jaeger auth, make smoke failures, Backup before reset, MCP config mismatch (C-5)

### WS-4 — Kiro enablement

- `KIRO.md` — NEW at repo root, 50 lines (hard cap was 100); product summary + quick links + tech-stack table + how-to-make-a-change recipe + P-1..P-4 invariants from `.kiro/steering/architecture-principles.md` (C-6)
- `docs/patterns/add-rest-endpoint.md` — NEW, 123 lines, 6 sections (C-6)
- `docs/patterns/add-mcp-tool.md` — NEW, 108 lines, 6 sections (C-6)
- `docs/patterns/add-audit-event.md` — NEW, 134 lines, 6 sections (C-6)
- `tests/stubs/README.md` — NEW, 139 lines; plan-only for 3 stubs (Vault Adapter Go gRPC, Proxy Recorder Go HTTP, OIDC Mock Python FastAPI); uniform conventions + CI integration plan (C-6)
- `docs/architecture/00-vision/07-kiro-readiness.md` — 3 status-table rows updated: KIRO.md ⏳→✅, Pattern library ❌→🟢 partial, Stub services ❌→🟢 plan; bottom "Fastest path" steps 3/4/5/6 also updated (C-6)

### Kiro tracking

- `.kiro/specs/post-prealpha-readiness/tasks.md` — 14 actionable tasks `[ ]` flipped to `[x]` (C-2..C-6); 3 checkpoint/verification tasks (5, 12, 17) flipped by ORCHESTRATOR C-7 audit.

## Verification (C-7 audit, ORCHESTRATOR, 2026-05-19)

```
file-existence audit: 19/19 ✓
red-team grep mk_agent_[A-Z0-9]{50,}    → 1 hit, pre-existing placeholder in
                                          docs/architecture/contracts/rest/openapi.yaml
                                          (NOT in this PR's diff; obviously synthetic
                                          "NEWKEYVALUE0...")
red-team grep mk_svckey_[A-Z0-9]{30,}    → 0 hits ✓
red-team grep mk_agentkey_[A-Z0-9]{20,}  → 0 hits ✓
git diff --stat origin/main..HEAD -- docs/architecture/01-architecture/adr/
                                         → empty ✓
remaining `- [ ]` actionable tasks       → 0 ✓
                                          (only checkpoint/verification tasks
                                          5/12/17 had `[ ]` after Wave 2; flipped
                                          by C-7)
git log --oneline origin/main..HEAD      → 6 commits
```

## GO-2026-XXXX → GO-2026-4918 (resolved)

The spec's Task 3.2 asked the implementer to identify the truncated advisory ID. C-3 used the Mintkey proxy + pkg.go.dev lookup and resolved it:

- **Advisory**: GO-2026-4918 (alias CVE-2026-33814)
- **Module**: `golang.org/x/net` (currently `v0.52.0` per `go.mod`)
- **Issue**: HTTP/2 transport infinite loop on `SETTINGS_MAX_FRAME_SIZE=0`
- **Patch**: `v0.53.0` is available
- **Action**: `go get golang.org/x/net@v0.53.0 && go mod tidy` — documented as a one-line follow-up task in `SECURITY.md §Fixable Scorecard residuals — backlog`. This is the FIRST formally fixable Scorecard residual on the dashboard.

## Per-requirement coverage (all 21 requirements addressed)

- Reqs 1, 2, 3 → C-2 (roadmap fix + EvidenceRef audit + evidence.md)
- Reqs 4, 5 → C-3 (Scorecard UI steps + GO-2026 resolution)
- Reqs 6, 7 → C-3 (weak-hash migration + audit-SHA-256 invariant docs)
- Reqs 8, 9, 10 → enforced by hard rules + C-7 audit (red-team grep + ADR no-edit + evidence policy)
- Reqs 11, 12 → C-4 (make demo + make demo-mock)
- Reqs 13 → C-5 (agent-never-sees-secret)
- Reqs 14, 15, 16 → C-5 (Python + TS + OpenAI-compatible examples)
- Reqs 17 → C-5 (DEBUG.md +6 entries)
- Reqs 18 → C-6 (KIRO.md)
- Reqs 19 → C-6 (3 pattern docs)
- Reqs 20 → C-6 (tests/stubs/README.md)
- Reqs 21 → C-6 (kiro-readiness.md 3 status rows)

## Residuals (non-blocking, tracked)

- **GO-2026-4918 dep bump** — `golang.org/x/net v0.52.0 → v0.53.0`. Documented in SECURITY.md as a one-line follow-up; the actual `go mod` edit is out of this session's scope (would require service-code branch work).
- **Pre-existing Makefile `.PHONY: test:e2e` syntax warning on GNU Make 3.81 (macOS default)** — surfaced by C-4 but pre-existing on main; not introduced by this session.
- **Pre-existing placeholder `mk_agent_NEWKEYVALUE...` in `docs/architecture/contracts/rest/openapi.yaml`** — pattern-matches the red-team regex but is obviously a synthetic OpenAPI example value; pre-existing on main; not in this session's diff.
- **Bigger pattern library / more stubs** — `docs/patterns/` only has 3 entries (add-rest-endpoint, add-mcp-tool, add-audit-event) per spec scope; `tests/stubs/README.md` is plan-only with no implementations. Both are intentional pre-v1 minimum-viable shape per spec Requirement 20.

## Owner action items

1. **Land the dep bump** for GO-2026-4918 (`golang.org/x/net v0.53.0`) in a follow-up session. SECURITY.md has the one-line fix command.
2. **Manual GitHub-UI dismissals** for the 8 accepted Scorecard residuals — SECURITY.md now has exact click-paths per residual.
3. **Implement the 3 stubs** when the test-isolation pain justifies it (CI integration plan in `tests/stubs/README.md`).
4. **Review KIRO.md** for accuracy — pulled the P-1..P-4 invariants from `.kiro/steering/architecture-principles.md`; verify those are the canonical ones you want surfaced.

## Process

| Wave | Chunk(s) | Outcome |
|---|---|---|
| 0 | C-1 scaffold + spec ingest | committed |
| 1 (parallel) | C-2 roadmap, C-3 SECURITY.md, C-4 Makefile+scripts | 3 commits, no file conflicts |
| 2 (parallel) | C-5 Builder B-1 docs, C-6 Kiro enablement | 2 commits, no file conflicts |
| 3 | C-7 ORCHESTRATOR verification | 19/19 deliverables; tasks.md fully `[x]` |
| 4 | C-8 fresh REVIEWER (Opus) | _pending — about to dispatch_ |
| 5 | push + PR + admin-merge | _pending — after C-8 PASS_ |

All implementers were Sonnet, single-pass (no strike-2 needed in this session). All hard rules held: no Co-Author trailer, no ADR edits, no service-code edits, no real secrets.
