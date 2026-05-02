---
name: task-implement
description: Pick up a Mintkey Kiro task from `.kiro/specs/mintkey-mvp/tasks.md` (T-M.N.K), verify design-readiness, plan with TDD discipline, then execute with milestone review/test gates. Activate when the user says "implement task T-1.0.1", "pick up the next task", "start the next Kiro task", or "work on tasks.md".
---

# task-implement (Mintkey)

You implement a single Kiro task end-to-end while honoring this project's discipline (architecture immutability, audit chokepoint, RLS coverage, plaintext-zero, Liquibase-source-of-truth, ADR-aligned). You DO NOT redesign, write specs, or modify governance.

This skill is **Mintkey-specific**. It assumes the repository structure described in [`AGENTS.md`](../../../AGENTS.md) / [`CLAUDE.md`](../../../CLAUDE.md), the Phase-1 task list at `.kiro/specs/mintkey-mvp/tasks.md`, and the 17 accepted ADRs under `docs/architecture/01-architecture/adr/`.

## When to invoke

- "Implement task `T-1.N.K`" (e.g. `T-1.0.1`, `T-1.6.8`).
- "Pick up the next task in `mintkey-mvp`/tasks.md."
- "Start the next Kiro task."
- "Work on tasks.md for `mintkey-mvp`."

## When NOT to invoke

- The task references `requirements.md` or `design.md` content that doesn't exist (or is a stub) → STOP. Architect must complete it. Do **not** invent design content.
- The task is architectural / governance work (writing an ADR, modifying contracts, modifying open-questions) → wrong skill. Architect governs; this skill ships code.
- Pure refactor / test-only / doc-only change with no task ID → just edit; no skill activation.
- The task ID doesn't exist in `.kiro/specs/mintkey-mvp/tasks.md` → ask the user; do not guess.

## Inputs

- `task-id` (optional) — e.g. `T-1.0.1`. If absent, pick the **first unchecked** `- [ ]` item in the Phase 1 Exit Criteria Checklist (or, if that's all checked, ask the user).

---

## Workflow — six phases. All are mandatory.

### Phase 1 — Pickup and citation

1. **Read** `.kiro/specs/mintkey-mvp/tasks.md`. Locate the task by ID. If `task-id` is absent, take the first `- [ ]` from the Phase 1 Exit Criteria Checklist whose milestone has not yet been completed.
2. **Extract** from the task body:
   - Task title and milestone (e.g. `M1.0 — Foundation Skeleton / T-1.0.1`).
   - `What`, `Test first`, `Implement`, `Clarifications`, `Sonnet hint`, `Acceptance`, `Refs`.
3. **Resolve every `Refs` citation** to a concrete file:
   - `Req <N> AC<K>` → `.kiro/specs/mintkey-mvp/requirements.md` § Req `<N>`.
   - `S-*-*` → `docs/architecture/01-architecture/03-quality-attributes.md`.
   - `ADR-NNNN[.X]` → `docs/architecture/01-architecture/adr/NNNN-*.md`.
   - `design §<N>` → `.kiro/specs/mintkey-mvp/design.md` § `<N>`.
4. **Read** every cited section in full. Do **not** rely on the task body alone — the task is a pointer; the spec is the authority.
5. **Restate** the task in chat with full citations and confirm with the user before any code is written. Show:
   - The task ID, milestone, and one-line summary.
   - The first failing test you intend to write (file path + assertion).
   - The first file you intend to touch.

### Phase 2 — Think and plan **(hard gate — do not skip)**

Use extended thinking before further tool use. Then output a plan with these sections, and **wait for user approval** before Phase 3:

**Plan format:**

1. **Scope** — bullet list of behavior to ship; bullet list of what's explicitly out (defer to a later task or another T-ID).
2. **Work units** — atomic deliverables sized for the **Sonnet hint** in the task. Each unit names the file(s) it will touch. Example:
   - U1: Write `tests/unit/admin_api/test_health.py` with the 4 assertions from REQ-1 AC7.
   - U2: Implement `admin-api/src/admin_api/api/health.py` `/v1/health` endpoint.
   - U3: Implement `admin-api/src/admin_api/api/health.py` `/v1/ready` endpoint with the 4 dependency checks.
3. **Dependency graph** — for each unit, list which other units must finish first. Mark units with no upstream as `[parallelizable]`. (For most Mintkey tasks, units are sequential because of the TDD `test → impl → verify` cadence; parallelism appears mostly inside Phase 4 cohorts when independent test files are being written.)
4. **Milestones** — group units into 1–4 milestones following the Sonnet hint's session boundaries (e.g. M1 schema + RLS template; M2 architecture test). Each milestone ends with a Phase-5 review/test gate.
5. **Validators that will run** — list the specific commands from `AGENTS.md` § "Verification commands" that this task's Acceptance criteria require (e.g. `pytest tests/architecture/test_rls_coverage.py`, `mmdc` if Mermaid touched, `sqlacodegen` if schema touched, etc.).
6. **Risk-of-discovery items** — anything that, if it surfaces during implementation, requires escalation: a missing ADR, a contradiction between two ADRs, a `design.md` gap, an `OQ-NNN` collision, a quality-attribute scenario that the existing test fixtures can't satisfy. List them up-front so the user can pre-approve handling.

If the user rejects or revises the plan, redraft. Do not proceed without explicit approval.

### Phase 3 — Design-readiness verification **(STOP if any check fails)**

Before any code is written, ALL must hold:

1. `.kiro/specs/mintkey-mvp/design.md` exists AND is not a stub. The section the task references (e.g. `design §4`) is present and substantive (≥150 words; named components or sequence steps).
2. Every `Req <N>` cited in `Refs` is in `.kiro/specs/mintkey-mvp/requirements.md` with full Acceptance Criteria. (No `?TBD?`, no placeholders.)
3. Every contract referenced exists and lints clean:
   - REST: `docs/architecture/contracts/rest/openapi.yaml` (run `openapi-spec-validator`).
   - MCP: `docs/architecture/contracts/mcp/tools.yaml` (run `yaml.safe_load`).
   - Events: `docs/architecture/contracts/events/{audit,change}-event.schema.json` (run `Draft202012Validator.check_schema`).
   - Proto: `docs/architecture/contracts/vault-adapter/vault.proto` (run `protoc --descriptor_set_out=/dev/null`).
4. Every ADR cited in `Refs` exists at `docs/architecture/01-architecture/adr/NNNN-*.md` with status `Accepted` (not `Superseded` unless the task knowingly targets the new one).
5. No `OQ-NNN` in `docs/architecture/01-architecture/open-questions.md` is marked as blocking the requirement IDs this task touches.
6. The Liquibase changelogs the task depends on are present at `admin-api/db/changelog/` (or, if the task itself adds them, the parent migration that sets up `databasechangelog` is present).
7. The `mintkey-models` shared package has the schemas/models the task imports (or the task itself adds them per Liquibase-then-mirror discipline; never the other way around).

If ANY check fails: STOP. Output the missing artifact, the steering rule that requires it (`AGENTS.md` Principle 2 — "Do not invent contract surfaces"), and the recommended next action (e.g. "ask the architect to add §4.3 to design.md", "open OQ-NNN", "add Liquibase changelog 002 first as task T-1.0.1.a"). Do NOT silently invent design content.

### Phase 4 — Execution (TDD per work unit)

For each milestone in turn, execute its work units. The default cadence per unit is **strict TDD**:

1. **Write the failing test** as specified in the task's `Test first` line.
2. **Run the test** — expect it to fail for the right reason (missing implementation, not a syntax error).
3. **Implement the minimum code** that turns it green (Karpathy rule 2 — Simplicity First).
4. **Run the test again** — expect green.
5. **Run all relevant validators** for this unit (linters, schema validators, RLS coverage if schema touched, Mermaid render if doc touched, plaintext-canary grep if a code path could leak credentials, etc.).
6. **Re-read the diff** before declaring the unit done (Karpathy rule 3 — Surgical Changes). Every changed line should trace to the task's `What` / `Acceptance`.

**Parallelism guidance:**

- If the work-unit graph has independent units in the same cohort (e.g. "write 6 separate auth-scheme test files"), and your runtime supports parallel sub-tasks, dispatch them in a **single message with multiple sub-task tool uses**. Each sub-task gets:
  - The exact files it owns (no overlap with siblings).
  - The relevant spec / ADR citations.
  - The smallest-first-cut directive: "Do not expand scope. Do not touch files outside the listed paths."
  - The cite-sources directive: "Inline-cite the WHY for any non-obvious decision; reference the ADR by number, not by name."
- **Do not run cohorts in parallel if they share file ownership** — that produces merge conflicts. One sub-task per file per cohort.

**File-ownership boundaries (enforced — do not cross):**

- **You may touch:**
  - `admin-api/`, `mcp-server/`, `services/<name>/` (Go services), `mintkey-models/`, `admin-ui/`, `mock-backend/`, `seed-job/`, `audit-verify-job/`.
  - `tests/unit/`, `tests/acceptance/`, `tests/architecture/`.
  - The task's own line in `.kiro/specs/mintkey-mvp/tasks.md` (Phase 6 close-out only).
  - `docker-compose.yml` (only if the task explicitly touches it, e.g. T-1.0.10).
- **You may NOT touch:**
  - `docs/architecture/` (canonical architecture; immutable in implementation phase).
  - `.kiro/steering/` (governance).
  - `.kiro/specs/mintkey-mvp/{requirements,design}.md` (the spec; only `tasks.md` line for close-out).
  - `docs/architecture/contracts/` (canonical wire contracts; FastAPI emits OpenAPI and the CI diff is the gate).

If a genuinely-needed change falls outside your boundary, **STOP** and surface it. Suggest a draft under `team/<your-handle>/drafts/` (or chat) and escalate to architect; do not proceed.

**Per-Mintkey-task cross-checks** (run when the listed surface is touched):

| If the task touches… | Run before declaring the unit done |
|---|---|
| Liquibase changelogs | RLS architecture test (T-1.0.11); SQLAlchemy mirror diff (T-1.11.6) |
| Any state-change endpoint | Audit chokepoint architecture test (T-1.7.3); audit hash chain integrity (T-1.7.5) |
| FastAPI route shape | OpenAPI parity gate (T-1.11.5) |
| Mermaid blocks in any doc | Mermaid render gate (T-1.11.7) |
| A code path that handles credentials | Plaintext-canary grep (T-1.3.3) — zero matches required |
| `pg_notify` or LISTEN | SQL injection architecture test (T-1.0.15) — bound parameters only |
| OTel emission | SDK redaction test (T-1.0.14) and Collector redaction test (T-1.10.1) |
| Any tenant-scoped query | RLS coverage test (T-1.0.11); cross-tenant isolation test (T-1.12.2) if a new endpoint |

### Phase 5 — Milestone review/test gate **(mandatory after every milestone)**

After each milestone's units complete, **conduct a structured review** before proceeding to the next milestone. If your runtime supports independent sub-task agents, spawn one with this prompt; otherwise, perform the review yourself and write the verdict back into the task chat.

**Review prompt template:**

```
You are the milestone review/test gate for milestone {M-N} of task {T-X} in feature mintkey-mvp.
You are NOT here to write code. You are here to verify and report.

INPUTS:
- Milestone scope: {paste the milestone's work units}
- Files changed in this milestone: {list}
- Cited spec sources: {paste from Phase 1 + 3}

DO:
1. Diff-review every changed file against the cited requirement / design / ADR. Flag drift.
2. Verify the failing-test-first cadence: every implementation file has a corresponding test that was written first (check git log or the order in this session's transcript).
3. Verify cite-sources discipline: every non-obvious choice has an inline reason or chat citation referencing the ADR by number.
4. Verify smallest-first-cut: flag any scope creep beyond the milestone's stated work units.
5. Verify file-ownership boundary: NO edits to docs/architecture/, .kiro/steering/, .kiro/specs/.../{requirements,design}.md, docs/architecture/contracts/.
6. Run the test suite scoped to changed files:
   - Python: `pytest <changed-test-files> -v`.
   - Go: `go test ./...` from the relevant module root.
   - TypeScript: `pnpm --filter <package> test`.
7. Run any cross-check from the Phase-4 table that applies to surfaces touched in this milestone.
8. Produce three lists:
   - PASS: what's verified clean (with exit code).
   - BLOCKERS: must-fix before the milestone can close (with file:line and the rule violated).
   - SUGGESTIONS: nice-to-haves; not blocking.

DO NOT:
- Edit files. You only report.
- Approve drift "because it's small." Refer it to the architect.
- Run `--no-verify` or skip hooks.

REPORT FORMAT:
Milestone {M-N} review:
- PASS: ...
- BLOCKERS: ...
- SUGGESTIONS: ...
- Verdict: PROCEED | FIX BLOCKERS | ESCALATE TO ARCHITECT
```

If the gate returns BLOCKERS: address them (loop back into Phase 4 with a tightened scope), then re-run the gate. If it returns ESCALATE: stop and surface to the user / architect; do not proceed.

### Phase 6 — Close out

1. **Update `tasks.md`**: change the task's status marker (if the task body has a `- [ ]` line in the Phase 1 Exit Criteria Checklist, change it to `- [x]`). Append a parenthetical with key artifact paths, e.g.:
   ```
   - [x] T-1.0.1: Liquibase changelogs — initial schema (impl: admin-api/db/changelog/001-initial-schema.yaml..010-indexes.yaml; test: tests/architecture/test_rls_coverage.py; review: PASS at M1, M2)
   ```
2. **Surface deferred sub-items** as new entries in `tasks.md` — never bury them in chat. Use the next-available sub-numeric (e.g. `T-1.0.1.a`).
3. **Run the Phase-1 Exit-Criteria-Checklist sweep** at the bottom of `tasks.md` and tick any rows your task fully satisfies.
4. **If implementation revealed**:
   - A new architectural decision → recommend writing a new ADR (do **not** edit existing ones).
   - An invalid assumption → recommend updating `docs/architecture/01-architecture/open-questions.md` (or the task's own `Risk-of-discovery items`).
   - A new failure mode → recommend updating the failure-mode catalog in `design.md` (architect-owned; flag, do not edit).
5. **Suggest a commit message**; do not commit unless the user asks. Format:
   ```
   <T-ID>: <one-line title>
   
   <2-4 line summary referencing the satisfied Acceptance criteria and the cited ADRs>
   ```

---

## Output

- **Phase 1**: cited task summary + first test + first file.
- **Phase 2**: plan (scope, work units, dependency graph, milestones, validators, risks). **Wait for approval.**
- **Phase 3**: green-light or refusal with named gap.
- **Phase 4**: per-cohort progress (TDD cadence visible).
- **Phase 5**: reviewer verdict per milestone. PROCEED or loop.
- **Phase 6**: updated `tasks.md` line + Exit Criteria sweep + suggested commit message + governance flags.

## Anti-patterns

- ❌ Skipping Phase 2 because the task "looks small". The plan is the gate that prevents drift; without it, sub-task scope creeps.
- ❌ Skipping Phase 3 because the design "seems clear". Mintkey has 17 ADRs and 22 open questions; the spec is dense for a reason.
- ❌ Running Phase 4 cohorts in parallel when they share files. Produces merge conflicts and overlapping edits.
- ❌ Skipping Phase 5 between milestones. Defeats the review/test discipline.
- ❌ **Editing `docs/architecture/`, `docs/architecture/contracts/`, `.kiro/steering/`, or `.kiro/specs/.../{requirements,design}.md`** to make verification pass. These are governance-owned; surface and escalate.
- ❌ Inferring design intent when `design.md` is silent. Escalate to architect; do not decide.
- ❌ Marking a task `[x]` when only part shipped. Split into sub-tasks (`T-X.a`, `T-X.b`) instead.
- ❌ Adding scope not in the task (smallest-first-cut violation per Karpathy rule 2 / `AGENTS.md` Principle 0 reconciliation).
- ❌ Citing "the spec" without a section anchor. Always cite as `Req <N> AC<K>` / `ADR-NNNN[.X]` / `design §<N>` / `S-<DOMAIN>-<NUM>`.
- ❌ Running `--no-verify` to push past hooks instead of fixing the underlying break.
- ❌ Letting a reviewer sub-task agent edit code. Its only job is to report.
- ❌ Adding a column in SQLAlchemy. Liquibase only (per `AGENTS.md` Mintkey guardrails / ADR-0015).
- ❌ Caching plaintext credentials in the proxy plugin. Per-request only (per ADR-0014.4).
- ❌ Using f-string interpolation into SQL `text(...)`. Bound parameters only (per `AGENTS.md` SQL injection rule / T-1.0.15).
- ❌ Using per-tenant change-channel names. Channels are global; the filter is in the wrapper (per ADR-0014.1).
- ❌ Claiming "tests pass" without showing the runner output and exit code (per `AGENTS.md` Principle 1).

## See also

- [`AGENTS.md`](../../../AGENTS.md) — operating principles, Mintkey guardrails, verification commands, anti-patterns.
- [`CLAUDE.md`](../../../CLAUDE.md) — Claude-Code-flavored sibling (kept in lock-step with AGENTS.md).
- [`.kiro/specs/mintkey-mvp/tasks.md`](../../../.kiro/specs/mintkey-mvp/tasks.md) — the task list this skill consumes.
- [`.kiro/specs/mintkey-mvp/requirements.md`](../../../.kiro/specs/mintkey-mvp/requirements.md) — Phase-1 functional + non-functional requirements.
- [`.kiro/specs/mintkey-mvp/design.md`](../../../.kiro/specs/mintkey-mvp/design.md) — Phase-1 component design.
- [`docs/architecture/`](../../../docs/architecture/) — architectural source of truth (17 ADRs, 9 proposals, contracts, flows, threat model).
