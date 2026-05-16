# team/remediation/

A structured workspace for multi-step code remediation sessions. Each session
is a dated directory; completed or superseded sessions are moved to `_archive/`.

## Folder pattern

- `YYYY-MM-DD-<kebab-slug>/` — an active or completed session
- `_archive/YYYY-MM-DD-<kebab-slug>/` — a closed / superseded session

### Role-numbered files inside a session

| File | Role |
|---|---|
| `00-plan.md` | Session plan or driving prompt |
| `01-spec.md` | Detailed spec (UX, API, etc.) |
| `01-orchestrator-chunks.md` | Orchestrator chunk-catalog (alternative to spec) |
| `02-matrix.md` | Tracking matrix (action grid, DoD checklist, etc.) |
| `03-escalations.md` | Escalation log — items requiring out-of-scope decisions |
| `04-progress.md` | Live orchestration state file (optional) |
| `99-report.md` | Closing summary / post-mortem |

Only the files that apply to a given session need to exist.

## The orchestrator pattern

The orchestrator pattern (dispatch IMPLEMENTER subagents, verify with fresh
REVIEWER subagents, loop on FAIL, hard-stop at 3 strikes) is project-agnostic
and lives in the `remediation-orchestrator` skill:

```
~/.claude/skills/remediation-orchestrator/SKILL.md
```

Invoke it by saying "use the orchestrator pattern", "dispatch subagents to fix
this", or "orchestrate this remediation". Original Mintkey-specific prompt
artifacts that inspired the skill are archived at
`_archive/2026-05-12-mintkey-mvp/`.

## When to use remediation vs Kiro/spec-driven work

**Use a `team/remediation/` session** when the work is *fixing something concrete that exists*: a broken behavior, a missing piece of OSS hygiene, a regression, an audit finding, a release blocker, a security gap. Remediation work has an issue intake, surgical scope, and ends with a closing report.

**Use the Kiro spec-driven flow (`.kiro/specs/`)** when the work introduces a new capability, a new wire surface, a new ADR-worthy decision, or any greenfield feature. Spec-driven work has requirements → design → tasks → implementation, with ADRs for architectural decisions.

The decision table below codifies which path applies.

## Issue intake (required before remediation starts)

Every `team/remediation/` session opens with the 9 intake fields (see [`ISSUE_INTAKE_TEMPLATE.md`](ISSUE_INTAKE_TEMPLATE.md)):

1. Problem statement
2. User-visible symptom
3. Expected behavior
4. Evidence (logs / screenshots / failing tests / file:line)
5. Scope
6. Out of scope
7. Risk level
8. Verification target
9. Owner decisions needed (if any)

**If any required field is missing, the agent must ask the user before starting** — or, if already inside a session, write the missing intake to `03-escalations.md` and pause dispatch. Do NOT guess.

For convenience, a new session can be scaffolded with:

```bash
cp -r team/remediation/SESSION_TEMPLATE/ team/remediation/$(date +%F)-<slug>/
# Then fill in ISSUE_INTAKE.md (or 00-issue-intake.md) before any other file.
```

## Decision table — which path?

| Request Type | Required Path | Issue Intake | Reviewer |
|---|---|---|---|
| "Fix this bug" with clear evidence | `team/remediation/YYYY-MM-DD-<topic>/` | Full intake file (`ISSUE_INTAKE_TEMPLATE.md`) | Independent REVIEWER subagent |
| "Fix this bug" without clear evidence | Ask for issue intake first; **do not start** | Required BEFORE any chunk dispatch | After intake lands |
| Multi-file remediation | Orchestrator pattern required (`remediation-orchestrator` skill) | Full intake file | Independent REVIEWER per chunk |
| Security, release, auth, audit, credential, tenant isolation issue | Orchestrator pattern required | Full intake file | Independent REVIEWER per chunk |
| New feature | Kiro spec-driven flow (`.kiro/specs/`) | Use Kiro requirements + ADR/proposal | Per Kiro process |
| Wire contract change | Proposal/ADR + contract-first flow | Full intake + ADR/proposal link | ADR review + contract review |
| Database schema change | Liquibase-first flow (`admin-api/db/changelog/`) | Full intake + changeset link | Schema review + migration verify |
| Documentation typo | Direct small PR allowed | Brief intake stub (Problem + Evidence) in PR body | Standard PR review |
| Dependency bump | Direct PR allowed if tests/verification included | Brief intake stub (Problem + Evidence + Verification) | Standard PR review |

Per the F4 owner decision: **every PR has an Issue Definition section in the template** — even doc typos and dep bumps fill it (just briefer). "Direct PR allowed" means "no session folder required", NOT "no intake fields required".

## PASS / FAIL / ESCALATE — review flow

Every chunk goes through a fresh REVIEWER subagent that re-runs the verification commands independently. Possible verdicts:

- **PASS** → matrix row flipped ✅; next chunk dispatched.
- **FAIL** → new IMPLEMENTER dispatched with the reviewer's findings in `<prior_review_findings>`. Re-review. **Hard-stop at 3 failed reviews for the same chunk** — orchestrator stops and surfaces to the user (last diff + reviewer findings + root-cause assessment).
- **ESCALATE** → reviewer cannot adjudicate (owner decision needed). Orchestrator opens an OQ in `03-escalations.md` and waits.

The 3-strike rule prevents indefinite IMPLEMENTER thrashing. A chunk that fails 3 reviews has a deeper problem than the chunk brief captured.

## Starting a new session

```bash
cp -r team/remediation/SESSION_TEMPLATE/ team/remediation/$(date +%F)-<topic>/
# Then fill in ISSUE_INTAKE.md before any other file.
```

Then write the plan and invoke the `remediation-orchestrator` skill (or run
solo via the prompt).

## Active sessions

| Session | Contents |
|---|---|
| [`2026-05-12-admin-ui-rework/`](2026-05-12-admin-ui-rework/) | AdminJS boot + full per-screen UX rework (00-plan, 01-spec) |
| [`2026-05-13-admin-ui-action-grid/`](2026-05-13-admin-ui-action-grid/) | Action-grid completion: inventory + fix every AdminJS action cell (00-plan, 01-orchestrator-chunks, 02-matrix, 03-escalations) |
| [`2026-05-16-oss-readiness/`](2026-05-16-oss-readiness/) | OSS hygiene: CONTRIBUTING.md, no-Co-Authored-By, governance files (closed) |
| [`2026-05-16-public-github-release-readiness/`](2026-05-16-public-github-release-readiness/) | Public release blockers: secrets scan, license, CI hardening (closed) |
| [`2026-05-16-pattern-enforcement/`](2026-05-16-pattern-enforcement/) | Governance: enforce remediation pattern, intake gate, decision table, PR template |

## Archive

| Archive | Contents |
|---|---|
| [`_archive/2026-05-12-mintkey-mvp/`](_archive/2026-05-12-mintkey-mvp/) | Original Mintkey MVP remediation plan + solo + orchestrator prompts |
| [`_archive/2026-05-13-playwright-extension/`](_archive/2026-05-13-playwright-extension/) | Playwright W0–W8 extension plan + solo + orchestrator prompts |
