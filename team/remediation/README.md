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

## Starting a new session

```sh
mkdir team/remediation/$(date +%F)-<topic>
touch team/remediation/$(date +%F)-<topic>/00-plan.md
```

Then write the plan and invoke the `remediation-orchestrator` skill (or run
solo via the prompt).

## Active sessions

| Session | Contents |
|---|---|
| [`2026-05-12-admin-ui-rework/`](2026-05-12-admin-ui-rework/) | AdminJS boot + full per-screen UX rework (00-plan, 01-spec) |
| [`2026-05-13-admin-ui-action-grid/`](2026-05-13-admin-ui-action-grid/) | Action-grid completion: inventory + fix every AdminJS action cell (00-plan, 01-orchestrator-chunks, 02-matrix, 03-escalations) |

## Archive

| Archive | Contents |
|---|---|
| [`_archive/2026-05-12-mintkey-mvp/`](_archive/2026-05-12-mintkey-mvp/) | Original Mintkey MVP remediation plan + solo + orchestrator prompts |
| [`_archive/2026-05-13-playwright-extension/`](_archive/2026-05-13-playwright-extension/) | Playwright W0–W8 extension plan + solo + orchestrator prompts |
