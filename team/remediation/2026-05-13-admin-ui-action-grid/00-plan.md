# Admin UI Action-Grid Completion — Mega Prompt (Sonnet)

You are a Sonnet implementer working in the Mintkey repo root. **Mission: every action on every resource in the Mintkey AdminJS admin UI works end-to-end in a real browser.** A user hit a "You have to implement action component for your Action..." error on the Service API Keys "Create" page — that is the *symptom*; the *cause* is that nobody ever systematically walked the AdminJS action grid. You will: (1) inventory every action on every resource, (2) classify each cell as working / broken / not-implemented / not-applicable in the live UI, (3) fix every broken/not-implemented cell, (4) keep a tracking matrix at `team/remediation/ADMIN_UI_ACTION_MATRIX.md` that you create and update after every change. The matrix is your contract; it MUST be ≥98% ✅ before you declare DONE. **Do not start fixing anything until Phase 0 (the full audit) is complete.**

---

## Read before starting (in this order)
1. `team/remediation/PLAYWRIGHT_EXTENSION_PLAN.md` — the consolidated Playwright suite (W0–W8 just landed; new tests go in `admin-ui/e2e/tests/`).
2. `team/remediation/ADMIN_UI_SPEC.md` (if present — the per-screen UX spec).
3. `AGENTS.md` and `CLAUDE.md`.
4. ADRs: `0013-adminjs-pin.md` (custom actions pattern), `0014-iter-1-2-corrections.md` (§14.5–14.6 AdminUiSignedRequest), `0018-classical-service-api-keys.md` (the `mk_svckey_…` flow), `0019-admin-ui-bff-and-write-auth.md` (write-auth contract).
5. Every `admin-ui/src/resources/*.ts` (services, credentials, agents, permissions, api_keys, audit, tenants).
6. `admin-ui/src/components/index.ts` (the ComponentLoader — see what's registered) and every `admin-ui/src/components/**/*.tsx`.
7. `admin-ui/src/lib/api-client.ts`, `signed-request.ts`, `rest-resource.ts`.
8. `docs/architecture/contracts/rest/openapi.yaml` — confirm which admin-api endpoints exist for each custom action.

---

## The action matrix (you create + maintain it)

First thing you do: write `team/remediation/ADMIN_UI_ACTION_MATRIX.md` with this exact shape, populated after Phase 0:

```markdown
# Admin UI Action Matrix

**Legend:** ✅ verified working in live browser · 🚧 in progress · ❌ broken · 🚫 not-implemented · n/a not applicable · ⬜ untested

Updated after every code change. The "Browser" column is the live UI verification; the "Spec" column is the Playwright test file:line that covers it.

## Standard actions
| Resource | list | show | new | edit | delete | bulkDelete |
|---|---|---|---|---|---|---|
| services | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| credentials | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| agents | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| permission_grants | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| service_api_keys | ⬜ | ⬜ | ❌ (Create UI errors: "implement action component") | ⬜ | ⬜ | ⬜ |
| audit_events | ⬜ | ⬜ | n/a (immutable) | n/a | n/a | n/a |
| tenants | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

## Custom actions (per ADR-0013 / ADR-0018)
| Resource | Action | API endpoint | UI wiring | Browser | Spec |
|---|---|---|---|---|---|
| credentials | rotate | `POST /v1/tenants/{tid}/services/{sid}/credentials` | ⬜ | ⬜ | |
| credentials | revoke | `DELETE /v1/tenants/{tid}/services/{sid}/credentials/{kv}` | ⬜ | ⬜ | |
| agents | revoke | `POST /v1/tenants/{tid}/agents/{aid}/revoke` | ⬜ | ⬜ | |
| permission_grants | grant | `POST /v1/tenants/{tid}/agents/{aid}/permissions` | ⬜ | ⬜ | |
| permission_grants | revoke | `DELETE /v1/tenants/{tid}/agents/{aid}/permissions/{pid}` | ⬜ | ⬜ | |
| service_api_keys | create-and-show-once | `POST /v1/tenants/{tid}/agents/{aid}/api-keys` (ADR-0018) | ⬜ | ⬜ | |
| service_api_keys | revoke | `DELETE /v1/tenants/{tid}/agents/{aid}/api-keys/{kid}` | ⬜ | ⬜ | |

## Cross-cutting
| Concern | Status | Notes |
|---|---|---|
| Dashboard | ⬜ | |
| Settings page | ⬜ | |
| Logout | ⬜ | |
| 7 resource intro paragraphs | ⬜ | |
| Search/`q` filter | ⬜ | |
| Contextual filters | ⬜ | |
| Pagination | ⬜ | |
| Sorting | ⬜ | |
| Tenants PlatformAdmin gate | ⬜ | |

## Phase log
- Phase 0 audit completed: <date> <commit>
- Phase 1 <resource>: <date> <commit>
- ...
```

Update this file as the FIRST commit of every phase, and again as part of EVERY commit that touches a resource. It is the receipt that prevents "we kept fixing the most-recent-screenshot" from happening again.

---

## Hard rules (non-negotiable)

- **Never claim a cell is ✅ without a live-browser screenshot you READ with the Read tool.** The previous incidents (`record.errors`, React #31, `[object Object]` filter, this Create-Api-Key error) all happened because someone marked work done without driving the actual feature in a browser. Stop the pattern.
- **Never `--no-verify`** / `--no-gpg-sign`. Never `test.skip` / `test.fixme` / `expect(true).toBe(true)` (justified `test.fixme` for not-yet-shipped features with `// TODO` is allowed but rare).
- **No hardcoded passwords / no hardcoded UUIDs** beyond the bootstrap tenant `9593e3ba-…`. Use fixtures / `firstRecordId` patterns.
- **No edits to `admin-api/`, `services/`, `docs/architecture/` (except updating this matrix), `.kiro/`, `docker-compose.yml`, Liquibase changelogs.** If a fix requires admin-api changes (e.g. an endpoint genuinely doesn't exist), STOP and ESCALATE.
- **Conventional commits, one logical chunk each.** `feat(admin-ui): wire <resource> <action> + tests` or `fix(admin-ui): <resource> <action> renders / submits`. No squashing across phases.
- **TDD-leaning**: for every broken/not-implemented cell, write the failing Playwright test FIRST in `admin-ui/e2e/tests/` (extends the W0–W8 consolidated suite); run it; capture failure output; THEN implement. If the failing test won't actually fail (the code already "works"), you misidentified the problem — re-investigate.
- **Use Page Objects** (`admin-ui/e2e/pages/*.ts`) — extend existing ones; don't write raw selectors in spec files.
- **Console-error fixture is mandatory** — import `test` from `admin-ui/e2e/fixtures/test.ts` (created in W0); a JS error during your test = automatic fail.
- **Sensitive/destructive actions** (delete, revoke) test against records you create in the same test (namespaced `e2e-actiongrid-{nanoid}`) — never against seed data.

---

## Phases

### Phase 0 — Full audit (you do this FIRST, in one commit)

1. Read every `admin-ui/src/resources/*.ts`. For each resource, list (a) which AdminJS actions are explicitly configured, (b) which reference a custom `component`, (c) which custom-action handlers exist. Cross-reference against `admin-ui/src/components/index.ts`'s ComponentLoader registrations to find dangling component-name references (these are the "implement action component for your Action…" errors).
2. Read `docs/architecture/contracts/rest/openapi.yaml`. For each custom action in the matrix, find the backing endpoint and verify it exists in the spec. If an endpoint is missing, mark the row 🚫 ESCALATE in the matrix.
3. Drive the live UI for EVERY standard-action cell (42 cells minus n/a). For each: navigate (`/admin/resources/<r>` for list, `/admin/resources/<r>/records/<id>/show` for show, `/admin/resources/<r>/actions/new` for new, `/admin/resources/<r>/records/<id>/edit` for edit, etc.), capture a screenshot, read it, classify as ✅ / ❌ (with the visible error message quoted) / 🚫. For destructive (delete/bulkDelete) DON'T actually delete seed data — visit the action's confirmation modal/page; capture; cancel.
4. Write the full populated matrix to `team/remediation/ADMIN_UI_ACTION_MATRIX.md`.
5. Commit: `docs(admin-ui): inventory all AdminJS actions per resource (Phase 0 of action-grid completion)`. Body: how many cells in each state (✅/❌/🚫/n/a counts). NO source changes in this commit. Pure audit.

After Phase 0 the matrix tells you (and the user) exactly how much work is left. The user can redirect priority based on the audit before you implement.

### Phase 1..N — Per-resource implementation

Pick the resource with the most ❌/🚫 cells first; or `service_api_keys` since the user-screenshot is on it. Per resource:

1. For each broken/not-implemented cell:
   - Write the failing Playwright test (e.g. `admin-ui/e2e/tests/31-<resource>-<action>.spec.ts` OR extend an existing CRUD spec from W1/W2). The test exercises the action end-to-end via the UI — open the page, fill form, submit, assert real outcome (new row in list, server response carries expected field, etc.).
   - Run the spec; observe failure; capture in the commit body.
   - Diagnose: missing component? Wrong component name? Missing handler? Missing API call from BFF? Bad prop wiring? AdminJS version quirk?
   - Implement the smallest correct fix. For custom action components (Service API Key "show generated token once" modal, credential rotate confirmation, agent revoke confirmation), build a small React component under `admin-ui/src/components/actions/<Name>.tsx`, register it in `admin-ui/src/components/index.ts`, wire it in the resource config's `actions.<name>.component`. For action handlers (the BFF-side that calls admin-api), extend `admin-ui/src/lib/api-client.ts` and the resource's `actions.<name>.handler`.
   - Re-run; spec passes.
   - Browser drive: open the page yourself via Playwright; screenshot; READ the screenshot; describe what you saw in the commit body (specific text rendered, specific button click result).
   - Update the matrix cell to ✅.
2. After all cells for the resource are ✅ (or justified 🚫/n/a), run the full `pnpm test:e2e` to confirm no regressions.
3. Commit: `feat(admin-ui): implement remaining <resource> actions (Phase N of action-grid)`. Body: which cells went ✅; which (if any) ESCALATEd to admin-api; the matrix delta.
4. Update the matrix's "Phase log" section.

### Phase Final — Whole-grid verification

1. The matrix has ZERO ⬜ and ZERO ❌; only ✅, 🚫 (justified, ESCALATE'd), and n/a.
2. `pnpm test:e2e` is green; total tests ≥ (previous + ~25 new for the action grid).
3. Drive a final end-to-end smoke yourself: log in → for each resource, visit list / show / new / edit (don't delete) → take one screenshot per page → assert no JS-error box and no "implement action component" AdminJS message anywhere.
4. Update the matrix's last row: `Phase Final completed: <date> <commit>`.
5. Commit: `test(admin-ui): action-grid completion verified end-to-end`.

---

## Anti-patterns to avoid (lessons from prior incidents)

- **"Just unwire the broken component" shortcut.** If a custom action's component reference is the bug, removing it falls back to AdminJS's stock — which often crashes or shows a default that's wrong for the domain (e.g. showing the bare `mk_svckey_…` token in a form input that's visible forever, defeating "show once" per ADR-0018). Implement the proper component; don't just hide the breakage.
- **"It compiles, ship it."** AdminJS resolves component names at runtime. A typo'd component string (`Components.ApiKeyCrate` vs `ApiKeyCreate`) compiles fine, renders the ActionSee error in production. Cross-check every `component:` reference against ComponentLoader registrations.
- **Custom action without backing API call.** If the action's `handler` just returns a fake success / a record stub, the UI looks fine but admin-api never gets called → no audit event → ADR-0014 broken. Always wire the real `apiWrite(...)` through the signed-request path per ADR-0019.
- **Tautological tests** (URL-contains without row narrowing) — caught the FilterElement bug. Don't repeat: every action test asserts a real downstream effect (new row exists, modal shows the right key, validation message names the right field).
- **No browser drive** = no claim of ✅. The Playwright spec passing is necessary but not sufficient (W0–W8 already proved tests can be tautological). Always read the screenshot for the final ✅.

---

## When to STOP and ESCALATE

Write a note in `team/remediation/ACTION_GRID_ESCALATIONS.md` (create if needed) and STOP if:

1. A custom action's backing admin-api endpoint genuinely doesn't exist (cross-stack work — out of scope).
2. AdminJS 7.x has no clean way to express an action you need (e.g. a multi-step wizard for service API key creation).
3. The matrix has more than 5 cells you can't fix (the action grid is bigger than one orchestration — surface for re-planning).
4. You hit a 3rd consecutive `failing-test-doesn't-fail` situation in the same phase — your root-cause assumption is wrong; surface for the user.

Don't push through ESCALATEs to keep counting commits. Honest STOP is the discipline.

---

## Out of scope (explicit)

- Adding new resources, new endpoints, new ADRs.
- Refactoring `admin-ui/src/lib/rest-resource.ts` beyond what's needed for an action.
- The accessibility / cross-browser / CI workflow done in W7/W8 — those are independent of this work; if your changes affect a11y violations or break a browser, fix them; don't redo the chunks.
- A separate Playwright-extension review may be running in the background — its verdict is about W0–W8, not about the action grid. If it returns FAIL on something W0–W8 touched, the orchestrator will dispatch a separate chunk to address.

---

## Start sequence (your first 10 minutes)

1. Read PLAYWRIGHT_EXTENSION_PLAN.md, ADMIN_UI_SPEC.md (if present), AGENTS.md, CLAUDE.md.
2. Read ADR-0013, 0014, 0018, 0019.
3. Read every resource config: `admin-ui/src/resources/*.ts`.
4. Read `admin-ui/src/components/index.ts`; list every registered component name. Then grep every resource for `component:` references; cross-check for dangling names. (Expect to find the Service API Key one immediately.)
5. Curl admin-api to confirm each custom-action endpoint exists. (Use the bootstrap session cookie.)
6. Begin Phase 0: drive every cell of the matrix in a real browser; populate `ADMIN_UI_ACTION_MATRIX.md`; commit with NO source changes.
7. Surface the audit result. Wait for the user to confirm priority (which resource first), OR proceed with the most-broken-first if the audit is clear.

**No source changes until the matrix exists and is populated.** That's the discipline that prevents the next "I don't understand how things are still broken" iteration.
