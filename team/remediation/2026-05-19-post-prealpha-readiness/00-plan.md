# Post-Prealpha Readiness — Session Plan

**Session:** `2026-05-19-post-prealpha-readiness`
**Branch:** `feature/post-prealpha-readiness-2026-05-19` (from `main @ a16aed0`)
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)

## Mission

Land the kiro spec at `.kiro/specs/post-prealpha-readiness/` in full — 14 actionable tasks across 4 workstreams (WS-1 docs accuracy, WS-2 security residuals, WS-3 Builder B-1, WS-4 Kiro enablement) — and flip every `[ ]` in `tasks.md` to `[x]`.

## Hard rules

- **Never edit accepted ADRs** (Requirement 9). Security goes to `SECURITY.md`.
- **No service-code changes**: `admin-api/`, `admin-ui/`, `mcp-server/`, `services/`, `mintkey-models/`, `mock-backend/`, `seed-job/` are off-limits.
- **Red-team fingerprint grep MUST pass with zero matches** on every deliverable (Requirement 8). No real agent keys, no real service keys, no real bootstrap KEKs in any example.
- **All example code uses placeholders**: `YOUR_AGENT_API_KEY`, `<agent-key>`, `<svc-id>`. Never paste a real `mk_agent_*` or `mk_svckey_*`.
- No `Co-Authored-By` trailer.
- No `--no-verify`.
- Validate via tools: `rg` red-team greps; `bash -n`; `python3 -m py_compile`; `python3 -c "import yaml; yaml.safe_load(...)"`; `docker compose config --quiet` for any compose-touching task; `make -n <target>` dry-run for any Makefile addition.

## Chunk strategy — grouped by file-conflict to avoid intra-branch collisions

The spec's dependency graph parallelises Wave 0 tasks 2.1 + 3.1 + 3.2 — but 3.1 + 3.2 both edit `SECURITY.md` and 2.1 + 2.2 both edit `06-roadmap.md`. Direct parallel execution would force merge conflicts. Regroup by file scope:

| # | Chunk | Owner files | Maps to spec tasks | Parallelisable? |
|---|---|---|---|---|
| C-1 | Orchestrator scaffold + EVIDENCE_LEDGER + the kiro spec checked in | session folder + `.kiro/specs/post-prealpha-readiness/*` | Spec pre-commit | No (Wave 0) |
| C-2 | Roadmap accuracy | `docs/architecture/00-vision/06-roadmap.md` + `.kiro/specs/post-prealpha-readiness/evidence.md` | 2.1, 2.2, 2.3 | Group A — single implementer; serial within |
| C-3 | SECURITY.md updates | `SECURITY.md` + `docs/architecture/01-architecture/security-notes/weak-hash-migration.md` | 3.1, 3.2, 3.3, 3.4, 4.1 | Group B — single implementer |
| C-4 | Builder B-1 — Makefile + demo scripts | `Makefile` + `scripts/demo-mock-flow.sh` | 6.1, 6.2 | Group C |
| C-5 | Builder B-1 — Walkthrough + examples + DEBUG | `docs/guides/agent-never-sees-secret.md`, `examples/python-agent-snippet/`, `examples/typescript-agent-snippet/`, `examples/openai-compatible/`, `docs/DEBUG.md` | 7.1, 8.1, 9.1, 10.1, 11.1 | Group D |
| C-6 | Kiro enablement | `/KIRO.md`, `docs/patterns/{add-rest-endpoint,add-mcp-tool,add-audit-event}.md`, `tests/stubs/README.md`, `docs/architecture/00-vision/07-kiro-readiness.md` | 13.1, 14.1-3, 15.1, 16.1 | Group E |
| C-7 | tasks.md flip + verification | `.kiro/specs/post-prealpha-readiness/tasks.md` + `99-report.md` | 17.1, 17.2 | After C-2…C-6 land |
| C-8 | REVIEWER (Opus, fresh) | full session audit | — | After C-7 |

## Sequencing

```
Wave 0:  [me] → scaffold + commit kiro spec
Wave 1:  C-2 ∥ C-3 ∥ C-4   (parallel; disjoint files)
Wave 2:  C-5 ∥ C-6         (parallel; disjoint files; depend on C-2 evidence refs being settled)
Wave 3:  C-7 (tasks.md flip + verification)
Wave 4:  C-8 (fresh reviewer)
Wave 5:  push + PR via Mintkey proxy + admin-merge
```

## Tracking convention — KIRO

Each implementer MUST flip the relevant `- [ ]` checkboxes in `.kiro/specs/post-prealpha-readiness/tasks.md` to `- [x]` as part of the SAME COMMIT that lands their deliverable. C-7 batch-verifies everything is flipped at the end. This makes the tasks.md the canonical kiro progress tracker.

## Closing acceptance criteria

- All 14 actionable tasks `[ ]` flipped to `[x]` in tasks.md.
- All deliverable files exist at the spec-specified paths.
- Red-team fingerprint grep returns 0 matches across all new/modified files.
- No accepted ADR edited.
- Reviewer PASS_ALL on first or strike-2 pass.
- PR opened + admin-merged via Mintkey proxy.
- `99-report.md` cites every commit SHA.
