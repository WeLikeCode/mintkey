# Vitest 2 → 4 Migration: Workspace → Inline Projects Config

## Purpose

Dependabot PR #178 bumps `vitest` from `2.1.9` to `4.1.9` in `apps/admin-ui`. The bump changes only `package.json` + `pnpm-lock.yaml`. It does **not** update the test configuration, which still uses the Vitest 2/3 *workspace* mechanism that Vitest 4 removed. The result is a silent regression: 62 of 593 tests stop running, while CI stays green.

This change migrates the admin-ui test config to the Vitest 4 `test.projects` model so the full suite runs again.

## Breaking changes in Vitest 4 (relevant to this repo)

Per the official Vitest migration guide (https://github.com/vitest-dev/vitest/blob/main/docs/guide/migration.md):

1. **`defineWorkspace` removed.** The helper imported from `vitest/config` no longer exists.
2. **External `vitest.workspace.ts` no longer supported.** In Vitest 3.2 `test.workspace` could point at an external file; Vitest 4 renamed it to `test.projects` AND requires the project array to be defined inline in `vitest.config.ts`. No external-file form remains.
3. `poolMatchGlobs` / `environmentMatchGlobs` removed in favor of `projects` (not used here, noted for completeness).

## Current (pre-change) state in `apps/admin-ui`

Four files implement a 2-project split:
- `vitest.config.ts` — a node-only "fallback" config (`include: tests/**/*.test.ts`, `environment: node`).
- `vitest.workspace.ts` — `defineWorkspace([...])` pointing at the two project files below.
- `vitest.node.config.ts` — `defineProject` node project (`node-tests`).
- `vitest.render.config.ts` — `defineProject` jsdom project (`render-tests`) with `resolve.alias` stubs for `@adminjs/design-system`, `adminjs`, and `react-router-dom`, collecting `tests/**/*.render.test.tsx`.

## Observed failure (reproduced)

A read-only worktree of the PR branch with deps installed:

| Runner | Files collected | Tests collected |
|---|---|---|
| main @ vitest 2.1.9 | 46 | 593 (3 pre-existing failures) |
| PR @ vitest 4.1.9 (as-is) | 40 | 531 (3 pre-existing failures) |

The 6 missing files are exactly the `*.render.test.tsx` set (62 tests). Under Vitest 4, `vitest.workspace.ts` is ignored, so `vitest run` falls back to root `vitest.config.ts` (node-only) and never loads the render project. `vitest run --project render-tests` errors with `No projects matched the filter "render-tests"`. Running `vitest run --config vitest.render.config.ts` directly DOES pass all 62 — proving the tests and stubs are fine; only the project wiring is broken.

The drop is silent: exit status is governed by the 3 unrelated pre-existing failures, not by the missing project, so neither the PR author nor CI would notice 62 tests vanished.

## What changed and why

- **Consolidate** the four config files into a single `vitest.config.ts` that declares both projects inline via `test.projects`, matching the Vitest 4 API. The `render-tests` project keeps its jsdom environment and the three `resolve.alias` stubs verbatim; the `node-tests` project keeps node env + `tests/**/*.test.ts`.
- **Delete** `vitest.workspace.ts`, `vitest.node.config.ts`, `vitest.render.config.ts` — their content is now inline, and `defineWorkspace`/`defineProject` are obsolete.
- No test files, mock stubs, package scripts, or lockfile entries change. Surgical: the diff traces entirely to the runner-version migration.

## Why not a smaller patch (e.g. just edit the workspace file)

There is no smaller correct patch. Vitest 4 has no external-workspace-file form at all, so the workspace indirection must collapse into the main config regardless. Keeping the three split files alongside an inline `projects` array would leave dead/confusing config. Consolidation is the minimum that both (a) restores the render project and (b) leaves no orphaned files.

## Out of scope

- The 3 pre-existing test failures (`test_oauth2_providers_resource`, `test_permissions`, `test_ssh_test_panel`) — they fail identically on main under vitest 2; they are source/assertion drift, not a vitest concern, and must not be touched in this dependency-bump change.
- The `vi.mock(...)`-inside-`beforeEach` hoisting WARNINGS in `tests/test_services_payload.test.ts` and `tests/test_test_connection.test.ts`. Non-fatal in 4.1.9 (tests pass); flagged for a separate follow-up before they become errors in a later vitest major.

## Testing

From `apps/admin-ui/`:
1. `pnpm install --frozen-lockfile=false`
2. `npx vitest run` → expect `Test Files 3 failed | 43 passed (46)`, `Tests 3 failed | 590 passed (593)`. The 590-pass / 46-file totals (vs 528 / 40 before the fix) are the acceptance signal that the render project is collected again.
3. `npx vitest run --project render-tests` → expect `6 passed (6)` files, `62 passed (62)` tests.
4. `npx vitest run --project node-tests` → node project runs in isolation without the alias stubs.

All four were executed in the research worktree and produced the stated results.
