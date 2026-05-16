# Mintkey Pattern Enforcement — Session Plan

**Session:** `2026-05-16-pattern-enforcement`
**Driver:** `remediation-orchestrator` skill
**Status:** Step 0 (design) — implementation paused until design lands.

## Mission

Make the existing remediation pattern **mandatory and easy to follow** for Codex, Claude, opencode, Kiro/spec-driven work, and GitHub PRs.

This is governance + workflow + documentation + template work. NO product code changes.

## Sister sessions (already-shipped context)

- `2026-05-12-mintkey-mvp/_archive/` — the original orchestrator pattern (frozen)
- `2026-05-16-oss-readiness/99-report.md` — closed; added CONTRIBUTING.md no-co-author + governance files
- `2026-05-16-public-github-release-readiness/99-report.md` — closed; release blockers fixed
- `team/remediation/README.md` — already exists; needs extension
- `~/.claude/skills/remediation-orchestrator/SKILL.md` — already exists; needs issue-intake gate extension

## Mega-prompt (verbatim from user)

The full mega-prompt is reproduced below. Source-of-truth for chunk planning.

---

You are working in the Mintkey repository. Your task is to make the existing remediation pattern mandatory and easy to follow for Codex, Claude, opencode, Kiro/spec-driven work, and GitHub PRs.

Do not implement unrelated product changes. This is a governance, workflow, documentation, and template update.

### Objective

Mintkey already has a remediation structure under `team/remediation/` and an orchestrator pattern:

- Session folder: `team/remediation/YYYY-MM-DD-<topic>/`
- Files such as `00-plan.md`, `01-spec.md`, `01-orchestrator-chunks.md`, `02-matrix.md`, `03-escalations.md`, `04-progress.md`, `99-report.md`
- Orchestrator pattern: ORCHESTRATOR → IMPLEMENTER → fresh REVIEWER → PASS/FAIL/ESCALATE → 3-strike hard stop

The goal is to enforce this pattern whenever a user asks to fix a concrete issue, especially multi-step or cross-file issues.

If the user has not clearly defined the issue, the agent must first request a clear issue statement before remediation begins.

If the work is not a remediation, it must follow the existing Kiro/spec-driven development path.

### Read First (for the designer + implementer)

1. `AGENTS.md`
2. `CLAUDE.md`
3. `team/remediation/README.md`
4. Existing remediation sessions under `team/remediation/`
5. `.kiro/specs/mintkey-mvp/requirements.md`
6. `.kiro/specs/mintkey-mvp/design.md`
7. `.kiro/specs/mintkey-mvp/tasks.md`
8. `CONTRIBUTING.md`
9. `docs/SDD.md`
10. `.github/workflows/ci.yml`
11. Existing `.github/` files

### Required Behavior To Document — Issue Intake

Every remediation must start with an issue intake answering:

| Field | Required? | Description |
|---|---:|---|
| Problem statement | Yes | What is broken or risky? |
| User-visible symptom | Yes | What does the user/operator see? |
| Expected behavior | Yes | What should happen instead? |
| Evidence | Yes | Logs, screenshots, failing tests, commands, or exact file references |
| Scope | Yes | Which areas may be changed? |
| Out of scope | Yes | Which areas must not be touched? |
| Risk level | Yes | Security, data loss, UX, CI, docs, release, etc. |
| Verification target | Yes | Which command/test proves the fix? |
| Owner decisions needed | If any | What cannot be guessed? |

If missing: ask for the missing info OR create a `03-escalations.md` entry if already inside a session.

### Files To Add Or Update

1. `team/remediation/README.md` — extend with intake + decision rules + PASS/FAIL/ESCALATE/3-strike rules
2. `team/remediation/ISSUE_INTAKE_TEMPLATE.md` — NEW reusable template
3. `team/remediation/SESSION_TEMPLATE/` — NEW starter files
4. `.github/pull_request_template.md` — enforce provenance + verification + agent rules
5. `CONTRIBUTING.md` — add "Remediation vs Spec-Driven Work" section
6. `AGENTS.md` and `CLAUDE.md` — add decision-table guardrails; lock-step

### Required Decision Rules

| Request Type | Required Path |
|---|---|
| "Fix this bug" with clear evidence | `team/remediation/YYYY-MM-DD-<topic>/` |
| "Fix this bug" without clear evidence | Ask for issue intake first |
| Multi-file remediation | Orchestrator pattern required |
| Security, release, auth, audit, credential, tenant isolation issue | Orchestrator pattern required |
| New feature | Kiro spec-driven flow |
| Wire contract change | Proposal/ADR + contract-first flow |
| Database schema change | Liquibase-first flow |
| Documentation typo | Direct small PR allowed |
| Dependency bump | Direct PR allowed if tests/verification included |

### GitHub PR Template Required Sections

```markdown
## Change Type
- [ ] Remediation session
- [ ] Kiro/spec-driven feature
- [ ] Documentation-only
- [ ] Dependency-only
- [ ] Other

## Required Provenance
For remediation:
- Session folder:
- Issue intake file:
- Matrix row(s):
- Reviewer result:

For Kiro/spec-driven work:
- Requirement:
- Design section:
- Task:
- ADR/proposal, if applicable:

## Issue Definition
- Problem:
- Expected behavior:
- Evidence:
- Scope:
- Out of scope:

## Verification
Paste command output and exit codes.
- [ ] Tests run
- [ ] Linters/validators run
- [ ] Smoke/integration run if relevant
- [ ] Security/plaintext checks run if relevant

## Agent/Automation Rules
- [ ] No `--no-verify`
- [ ] No unverified "tests pass" claim
- [ ] No unrelated refactor
- [ ] No accepted ADR edited
- [ ] No `Co-Authored-By` trailer required or added
```

---

## Step 0 — Design (current phase)

Designer (Opus) surveys existing state of each target file, identifies deltas vs the requirements above, proposes chunk decomposition.

## Step 1+ — Implementation

After design, implementer chunks land per the design.

## Hard rules (every chunk inherits)

- No `Co-Authored-By` trailer (per `~/.claude/CLAUDE.md`)
- No `--no-verify`
- No push
- No edits to accepted ADRs
- No product code changes
- Honor pre-existing dirty working-tree files (don't touch them)
- Honor data preservation (no `docker compose down -v`)
