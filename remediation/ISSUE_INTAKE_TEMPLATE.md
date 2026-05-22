# Issue Intake — <session-slug>

> Fill every required field before remediation starts. If you don't have evidence yet, GO COLLECT IT. If a field genuinely doesn't apply, write `n/a` and justify in one line.
> When this intake lands in a session, save as `<session-dir>/00-issue-intake.md` (or symlink from `00-plan.md`).

**Missing any required field = ask for it OR open `03-escalations.md` if already inside a session. Do NOT proceed without all required fields.**

---

## Problem statement (required)

What is broken or risky? One paragraph max. Be specific.

> Example: "Permission grants created via admin-ui's `Grants → New` form fail with 405 Method Not Allowed because the front-end POSTs `/v1/tenants/{tid}/permissions` (tenant-wide endpoint that doesn't exist) instead of `/v1/tenants/{tid}/agents/{aid}/permissions` (agent-scoped endpoint that actually exists)."

## User-visible symptom (required)

What does the user/operator see? Screenshots / curl output / error message.

> Example: "Admin UI shows 'Failed to create permission grant'; browser DevTools network tab shows 405 with body `{\"detail\":\"Method Not Allowed\"}`."

## Expected behavior (required)

What should happen instead?

> Example: "Grant should be created successfully, return 201, and appear in the grants list immediately."

## Evidence (required)

Logs, screenshots, failing tests, commands, exact file:line references.

> Example:
> - `admin-ui/src/resources/permission_grants.ts:124` — POST to `/v1/tenants/${tid}/permissions`
> - `admin-api/src/admin_api/api/permissions.py` — only mounts `/agents/{aid}/permissions`
> - Network log attached as `evidence/grant-405.har`

## Scope (required)

Which areas MAY be changed?

> Example: "`admin-ui/src/resources/permission_grants.ts`; admin-ui tests for grants; nothing else."

## Out of scope (required)

Which areas MUST NOT be touched?

> Example: "admin-api endpoint shapes (already correct); RLS; audit chain; other resources' endpoints."

## Risk level (required)

Pick one or multiple: `security / data-loss / UX / CI / docs / release / availability / compliance / other`.

> Example: "UX (operator-facing blocker)."

## Verification target (required)

Which command/test proves the fix?

> Example: "After fix: open admin-ui → Grants → New → fill agent+service+action → click Create. Network tab MUST show POST to `/v1/tenants/{tid}/agents/{aid}/permissions` → 201. Grant appears in list."

## Owner decisions needed (if any)

What cannot be guessed by the implementer?

> Example: "If existing 'action' constraints (`call` vs `*`) are wrong, owner must confirm the canonical action keyword. Otherwise none."

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
