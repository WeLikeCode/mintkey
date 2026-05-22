# Chunk Catalog — Post-Prealpha Readiness

**Session:** `2026-05-19-post-prealpha-readiness`
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)

## Hard rules (carry over from `00-plan.md`)

- No accepted-ADR edits.
- No core-service-code edits.
- No real secrets in any example.
- Tasks.md checkboxes flip in the SAME COMMIT as the deliverable.
- Validate via tools.

## Wave 1 — three parallel implementers (disjoint files)

### C-2: Roadmap accuracy (kiro tasks 2.1, 2.2, 2.3)

| Field | Value |
|---|---|
| Owner files | `docs/architecture/00-vision/06-roadmap.md`, `.kiro/specs/post-prealpha-readiness/evidence.md` (NEW), `.kiro/specs/post-prealpha-readiness/tasks.md` (flip 2.1/2.2/2.3) |
| EvidenceRefs | EV-PRIOR-001..004, EV-PRIOR-010, EV-PRIOR-011, EV-GAP-001, EV-GAP-002 |
| Tools | `rg` for "No backup/restore" + similar stale claims; verify EvidenceRefs match real files |
| Forbidden | Editing other docs; flipping tasks.md checkboxes for other chunks' tasks |

#### Outcomes required

- `06-roadmap.md` Section 1: remove "No backup/restore procedure" claim; replace with accurate statement distinguishing dev-workflow scripts from production DR; cite `scripts/dev-backup.sh`, `scripts/dev-restore.sh`, `scripts/dev-backup-cron.example.sh`.
- `06-roadmap.md` Sections 1 + 3: every status sentence carries an `EvidenceRef` (file path, commit SHA, or CI output). Sentences contradicting verified state are corrected.
- New `evidence.md` at `.kiro/specs/post-prealpha-readiness/evidence.md` with columns: Claim | EvidenceRef | Verified (yes/no) | Notes. Populated with every claim referenced in the roadmap edits.
- `tasks.md` items 2.1, 2.2, 2.3 flipped from `[ ]` to `[x]`.

### C-3: SECURITY.md updates (kiro tasks 3.1, 3.2, 3.3, 3.4, 4.1)

| Field | Value |
|---|---|
| Owner files | `SECURITY.md`, `docs/architecture/01-architecture/security-notes/weak-hash-migration.md` (NEW), `.kiro/specs/post-prealpha-readiness/tasks.md` (flip 3.1/3.2/3.3/3.4/4.1) |
| EvidenceRefs | EV-PRIOR-005, EV-PRIOR-006, EV-PRIOR-007, EV-GAP-003..006 |
| Tools | Read SECURITY.md before editing; preserve existing residual sections |
| Forbidden | Editing the audit-chain SHA-256 in code; touching ADR-0014.7 |

#### Outcomes required

- For each accepted Scorecard residual already in SECURITY.md, append a "GitHub UI Dismissal Steps" subsection with the exact click-path (Security tab → Code scanning → filter → Dismiss → reason → comment-text-to-paste).
- For GO-2026-XXXX: query the live GitHub Security tab via the Mintkey proxy to identify the full advisory ID; document either (a) the dep-bump path if upstream patched, OR (b) the deferral rationale + revisit trigger.
- New `docs/architecture/01-architecture/security-notes/weak-hash-migration.md` (NEW directory + file): document current state (3 BLOCKED sites per S5), risk assessment, chosen approach (accept-for-prealpha), revisit trigger. Cross-link from SECURITY.md.
- SECURITY.md gains a §Audit hash chain integrity section: SHA-256 is per ADR-0014.7; any change requires a new ADR; cites `tests/acceptance/test_audit_append_only.py`.
- For each Scorecard residual with an available code fix (vs. an "accepted forever" residual): create a concrete one-line remediation task entry (linked to a follow-up session).
- `tasks.md` items 3.1, 3.2, 3.3, 3.4, 4.1 flipped to `[x]`.

### C-4: Builder B-1 — Makefile + demo scripts (kiro tasks 6.1, 6.2)

| Field | Value |
|---|---|
| Owner files | `Makefile`, `scripts/demo-mock-flow.sh` (NEW), `.kiro/specs/post-prealpha-readiness/tasks.md` (flip 6.1/6.2) |
| EvidenceRefs | EV-PRIOR-001..003 (backup script availability), EV-PRIOR-012 (proxy pattern) |
| Tools | `bash -n scripts/demo-mock-flow.sh`; `make -n demo` and `make -n demo-mock` dry-runs; shellcheck if available |
| Forbidden | Adding `docker compose down -v` or any volume-destructive command |

#### Outcomes required

- `make demo` target: Docker availability check; `docker compose up -d`; poll health endpoints (180s timeout); on success print admin URL + bootstrap-password retrieval command + next steps. Never destroys volumes; recommends `scripts/dev-backup.sh` before any reset.
- `make demo-mock` target: auto-start stack if not running; then run `scripts/demo-mock-flow.sh`.
- `scripts/demo-mock-flow.sh`: register a mock service via admin-api, create an agent + API key, request a brokered JWT via mcp-server, make a proxied call to the mock backend, verify the response. PAT-free. Mirror conventions in `scripts/dev-backup.sh` (shellcheck-clean, fail-closed).
- `tasks.md` items 6.1, 6.2 flipped to `[x]`.

## Wave 2 — two parallel implementers (disjoint files; depend on C-2 evidence stabilising)

### C-5: Builder B-1 — Walkthrough + examples + DEBUG.md (kiro tasks 7.1, 8.1, 9.1, 10.1, 11.1)

| Field | Value |
|---|---|
| Owner files | `docs/guides/agent-never-sees-secret.md` (NEW), `examples/python-agent-snippet/{agent.py, requirements.txt, README.md}` (NEW), `examples/typescript-agent-snippet/{agent.ts, package.json, tsconfig.json, README.md}` (NEW), `examples/openai-compatible/{README.md, register-service.sh, agent.py}` (NEW), `docs/DEBUG.md`, `tasks.md` (flip 7.1/8.1/9.1/10.1/11.1) |
| EvidenceRefs | EV-PRIOR-012, EV-PRIOR-009, EV-GAP-009..013 |
| Tools | `rg` red-team grep for `mk_agent_[A-Z0-9]{50,}` / `mk_svckey_*` / `mk_agentkey_*` over the new files (must be 0); `python3 -m py_compile examples/**/*.py`; `cd examples/typescript-agent-snippet && pnpm exec tsc --noEmit` if pnpm available |
| Forbidden | Real secrets — placeholders only (`YOUR_AGENT_API_KEY`, `<agent-key>`) |

#### Outcomes required

- `docs/guides/agent-never-sees-secret.md`: structured walkthrough (Setup → Token request → Proxy call → Audit log check → OTel trace check → Conclusion). Copy-paste commands executable against a running stack. Demonstrate zero credential exposure at each step.
- `examples/python-agent-snippet/`: ~40-line `agent.py` (authenticate with agent-key, request JWT via MCP, call backend through proxy); `requirements.txt` with `httpx`; `README.md` with prerequisites + execution.
- `examples/typescript-agent-snippet/`: same shape; ~40-line `agent.ts`; `package.json` minimal; `tsconfig.json` minimal; `README.md`.
- `examples/openai-compatible/`: `README.md` explaining the pattern; `register-service.sh` with curl commands; `agent.py` calling OpenAI-compatible endpoint through Mintkey proxy. Use mock-backend in echo mode (no real OpenAI key).
- `docs/DEBUG.md`: append 6 entries — "Stack not running", "Bootstrap password / KEK mismatch", "oauth2-proxy / Jaeger auth issues", "`make smoke` failures", "Backup before reset", "MCP config mismatch". Follow existing DEBUG.md format: symptom / diagnostic / resolution.
- `tasks.md` items 7.1, 8.1, 9.1, 10.1, 11.1 flipped to `[x]`.

### C-6: Kiro enablement (kiro tasks 13.1, 14.1, 14.2, 14.3, 15.1, 16.1)

| Field | Value |
|---|---|
| Owner files | `/KIRO.md` (NEW), `docs/patterns/{add-rest-endpoint,add-mcp-tool,add-audit-event}.md` (NEW), `tests/stubs/README.md` (NEW), `docs/architecture/00-vision/07-kiro-readiness.md`, `.kiro/specs/post-prealpha-readiness/tasks.md` (flip 13.1/14.1/14.2/14.3/15.1/16.1) |
| EvidenceRefs | EV-PRIOR-008, EV-GAP-014..017 |
| Tools | `rg "AGENTS.md\|07-kiro-readiness\|01-architecture\|patterns/" KIRO.md` to confirm cross-links; relative-path lint on every pattern doc |
| Forbidden | Duplicating content from AGENTS.md or architecture docs in KIRO.md (it's a link hub, < 100 lines) |

#### Outcomes required

- `/KIRO.md` at repo root: < 100 lines; one-paragraph summary; quick links to AGENTS.md, `.kiro/steering/`, `docs/architecture/`, `docs/patterns/`; tech-stack table; "How to make a change" pointer; key invariants (P-1 through P-4 — find these in `.kiro/steering/` or the spec).
- `docs/patterns/add-rest-endpoint.md`: six sections (Goal / Where the change lives / Step-by-step / Tests to write / Common pitfalls / References). Relative links to ADRs + contracts.
- `docs/patterns/add-mcp-tool.md`: same shape.
- `docs/patterns/add-audit-event.md`: same shape.
- `tests/stubs/README.md`: document 3 priority stubs — Vault Adapter (in-memory, Go), Kong/Proxy Recorder (HTTP, Go), OIDC/Keycloak Mock (Python). For each: interface, location, minimum-viable scope, language. Include uniform conventions + CI integration plan.
- `docs/architecture/00-vision/07-kiro-readiness.md` status table: 3 row updates per Task 16.1 — "KIRO.md project conventions" ⏳→✅ with `EvidenceRef /KIRO.md`; "Pattern library" ❌→🟢 (partial) with EvidenceRef `docs/patterns/*.md`; "Stub services" ❌→🟢 (plan documented) with EvidenceRef `tests/stubs/README.md`.
- `tasks.md` items 13.1, 14.1, 14.2, 14.3, 15.1, 16.1 flipped to `[x]`.

## Wave 3 — Orchestrator verification (C-7)

ORCHESTRATOR runs (no subagent):

1. File-existence audit per the spec's verification checklist (task 17.1).
2. Red-team fingerprint grep:
   ```bash
   rg "mk_agent_[A-Z0-9]{50,}" examples/ docs/ Makefile
   rg "mk_svckey_[A-Z0-9]{30,}" examples/ docs/ Makefile
   rg "mk_agentkey_[A-Z0-9]{20,}" examples/ docs/ Makefile
   ```
   Each must return 0 hits.
3. ADR-no-edit check: `git diff --stat origin/main..HEAD -- docs/architecture/01-architecture/adr/` must be empty.
4. tasks.md final audit: every actionable `[ ]` flipped to `[x]`. ORCHESTRATOR fixes any missed flips by a strike-2 implementer or inline if trivial.
5. Write `99-report.md` with all commit SHAs + per-task EvidenceRef map.

## Wave 4 — REVIEWER (Opus, fresh)

C-8 covers all of C-2 through C-7. Reviewer checklist:

- Scope hygiene (only files in the allowlist; no ADRs touched; no service code touched).
- Red-team grep replicated (zero hits).
- `tasks.md` checkboxes all flipped.
- Every section of the 21 requirements maps to a deliverable.
- All new files exist and are non-empty.
- `make -n demo` and `make -n demo-mock` dry-runs work.
- `bash -n` clean on all new shell scripts.
- `python3 -m py_compile` clean on all new Python files.
- Reviewer reads the `evidence.md` cross-reference and confirms each roadmap claim has a real backing artifact.
- No `Co-Authored-By` trailer; no `--no-verify` used.

PASS_ALL gate before push + PR + admin-merge.

## Wave 5 — Push + PR + admin-merge

- Single PR for the whole session.
- Open via Mintkey proxy.
- Admin-merge after CI green (or owner-gated for sensitive doc changes).
