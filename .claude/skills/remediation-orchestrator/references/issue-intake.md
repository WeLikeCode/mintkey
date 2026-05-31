# Issue Intake (project-agnostic template)

Every remediation session starts with this intake. Fill every required field. If a field genuinely doesn't apply, write `n/a` and justify in one line.

**Missing any required field = ask for it OR open `03-escalations.md` if already inside a session. Do NOT proceed without all required fields.**

---

## Problem statement (required)

What is broken or risky? One paragraph max.

## User-visible symptom (required)

What does the user/operator see? Logs, screenshots, error message.

## Expected behavior (required)

What should happen instead?

## Evidence (required)

Logs, failing tests, commands run, file:line references. Be concrete.

## Scope (required)

Which areas MAY be changed?

## Out of scope (required)

Which areas MUST NOT be touched?

## Risk level (required)

`security / data-loss / UX / CI / docs / release / availability / compliance / other`

## Verification target (required)

Which command/test proves the fix?

## Owner decisions needed (if any)

What cannot be guessed by the implementer?

---

## Checklist (orchestrator may not start without all required fields)

- [ ] Problem statement
- [ ] User-visible symptom
- [ ] Expected behavior
- [ ] Evidence (with concrete file:line or command)
- [ ] Scope
- [ ] Out of scope
- [ ] Risk level
- [ ] Verification target
- [ ] Owner decisions noted (or "none")
