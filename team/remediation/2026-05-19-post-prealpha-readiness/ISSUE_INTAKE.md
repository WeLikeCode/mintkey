# Issue Intake — 2026-05-19-post-prealpha-readiness

**Session:** `team/remediation/2026-05-19-post-prealpha-readiness/`
**Branch:** `feature/post-prealpha-readiness-2026-05-19` (from `main @ a16aed0`)
**Reported:** 2026-05-19
**Reporter:** Owner — "use the orchestrator pattern and the implementer skill to implement the kiro specs post-prealpha-readiness for mintkey. Keep track as kiro of implemented tasks."

## Problem statement (required)

Implement the Kiro spec at `.kiro/specs/post-prealpha-readiness/` (requirements.md + design.md + tasks.md, ~50 KB total). The spec covers four workstreams that bring Mintkey from `v0.1.0-prealpha` to a state where:

1. **WS-1 Documentation accuracy**: Roadmap_Doc claims match verified state; every status sentence has an EvidenceRef.
2. **WS-2 Security residual closure**: SECURITY.md gains GitHub-UI dismissal click-paths, GO-2026-XXXX resolution, weak-hash migration strategy, audit-SHA-256 invariant.
3. **WS-3 Builder B-1 experience**: `make demo` + `make demo-mock` targets, agent-never-sees-secret walkthrough, Python/TypeScript/OpenAI-compatible snippet examples, expanded DEBUG.md.
4. **WS-4 Kiro enablement**: `/KIRO.md` link hub, 3 pattern docs (REST endpoint, MCP tool, audit event), stubs plan, kiro-readiness.md status updates.

Tracking convention: update `.kiro/specs/post-prealpha-readiness/tasks.md` checkboxes from `[ ]` to `[x]` as each task completes — this is the canonical Kiro progress tracker.

## User-visible symptom (required)

- Reading the roadmap, an outsider sees stale capability claims (e.g., "No backup/restore procedure" — actually false, `scripts/dev-backup.sh` shipped 2026-05-18).
- A new Builder cloning the repo has no `make demo` target — first-time setup requires reading multiple docs.
- An ops review of SECURITY.md sees "Accepted Scorecard Residuals" listed but no click-path for dismissal in the GitHub UI.
- A new contributor reads `docs/architecture/` and gets architecture but not "how do I add a REST endpoint / MCP tool / audit event" — the pattern library is missing.

## Expected behavior (required)

Per the kiro spec — 14 actionable tasks (1.1-1.3 already done; 2.1 through 17.2 remain):

- WS-1 (tasks 2.x): roadmap.md edits + evidence.md
- WS-2 (tasks 3.x, 4.x): SECURITY.md updates + new security-notes doc
- WS-3 (tasks 6.x-11.x): Makefile + scripts + docs/guides/ + examples/
- WS-4 (tasks 13.x-16.x): /KIRO.md + docs/patterns/ + tests/stubs/ + kiro-readiness update
- Verification (17.x): file-existence + red-team grep + final report

## Evidence (required)

See `EVIDENCE_LEDGER.md` for the spec-derived evidence index. Primary anchors:

- **The kiro spec itself** at `.kiro/specs/post-prealpha-readiness/{requirements,design,tasks}.md` — all 21 requirements and the dependency graph.
- **2026-05-18 backup/restore session artifacts**: `scripts/dev-backup.sh`, `scripts/dev-restore.sh`, `scripts/dev-backup-cron.example.sh`, `team/remediation/HOWTO-backup-before-reset.md`, `SECURITY.md §Accepted Scorecard Residuals` — these PROVE the roadmap claim "No backup/restore procedure" is now false.
- **GitHub Code Scanning state post-2026-05-18 campaign**: ~5 CodeQL alerts (in-flight close), 8 Scorecard residuals (5 from S11 + 3 newly documented in PR #77), ~860 Trivy alerts in steady-state pending Debian patches.

## Scope (required)

In scope (per the spec, plus the orchestrator session folder):

- New files under `examples/python-agent-snippet/`, `examples/typescript-agent-snippet/`, `examples/openai-compatible/`
- New files: `/KIRO.md`, `docs/patterns/{add-rest-endpoint,add-mcp-tool,add-audit-event}.md`, `tests/stubs/README.md`, `docs/guides/agent-never-sees-secret.md`, `docs/architecture/01-architecture/security-notes/weak-hash-migration.md`, `scripts/demo-mock-flow.sh`, `.kiro/specs/post-prealpha-readiness/evidence.md`
- Edits to: `docs/architecture/00-vision/06-roadmap.md`, `docs/architecture/00-vision/07-kiro-readiness.md`, `SECURITY.md`, `docs/DEBUG.md`, `Makefile`
- The `.kiro/specs/post-prealpha-readiness/tasks.md` — flip `[ ]` → `[x]` as each task completes (this is the kiro tracking convention; the spec is now part of this branch)
- Session folder

## Out of scope (required)

- **Accepted ADRs** — per spec Requirement 9, no ADR-0001…ADR-0020 edits. Security changes go to SECURITY.md, not ADRs.
- **Core service code** in `admin-api/`, `admin-ui/`, `mcp-server/`, `services/`, `mintkey-models/`, `mock-backend/`, `seed-job/` — the spec is explicitly documentation + Makefile + scripts + examples; no service-code changes.
- **Property-based tests** — verification is file-existence + content assertions + red-team greps per the spec.
- **Production DR / cloud backup** — that's a separate concern from dev-workflow backup/restore.

## Risk level (required)

- **Documentation accuracy**: high positive — closes stale claims that today read as overclaim or underclaim.
- **Security posture**: medium positive — SECURITY.md gains operator click-paths + decision records that close the May 18 residuals.
- **Builder B-1 onboarding**: high positive — `make demo` + snippets cut first-time-setup time substantially.
- **Code regression**: zero — no service code change.
- **Real secrets in examples**: must be guarded. Spec Requirement 8 mandates red-team fingerprint grep on every deliverable with zero matches.

## Verification target (required)

Per the spec task 17.1:

1. All deliverable files exist at expected paths (file-existence audit).
2. `rg "mk_agent_[A-Z0-9]{50,}" examples/ docs/ Makefile` returns ZERO matches (no real agent keys in examples).
3. `rg "mk_svckey_[A-Z0-9]{30,}" examples/ docs/ Makefile` returns ZERO matches.
4. `rg "mk_agentkey_[A-Z0-9]{20,}" examples/ docs/ Makefile` returns ZERO matches.
5. `git diff --stat origin/main..HEAD -- docs/architecture/01-architecture/adr/` returns empty (no ADR edits).
6. `docs/architecture/00-vision/07-kiro-readiness.md` status table reflects the 3 row updates from task 16.1.
7. `.kiro/specs/post-prealpha-readiness/evidence.md` exists and every claim in roadmap.md Sections 1 + 3 traces to it.
8. `.kiro/specs/post-prealpha-readiness/tasks.md` — every actionable task `[ ]` flipped to `[x]` (the kiro tracking deliverable).

## Owner decisions (required — locked from the spec)

- ✅ Implement per the spec's task list + dependency graph (waves 0-6).
- ✅ Group by file-conflict (intra-wave SECURITY.md edits and roadmap.md edits each consolidated to ONE implementer to avoid merge conflicts on the shared branch).
- ✅ Use orchestrator pattern: implementer subagents (Sonnet) + fresh reviewer (Opus).
- ✅ Track via tasks.md checkboxes — flipped as part of each implementer's chunk commit OR as a final batch update at session close.
- ✅ One PR for the entire session (one feature branch, multiple commits).

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (anchor refs + spec)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions
