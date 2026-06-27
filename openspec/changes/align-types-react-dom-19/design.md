# Align @types/react-dom to React 19 (admin-ui dependabot #183)

## Purpose

Dependabot PR #183 bumps `apps/admin-ui` to React 19:
- `react` 18.3.1 → 19.2.7
- `react-dom` 18.3.1 → 19.2.7
- `@types/react` ^18.3.0 → ^19.2.17

It left `@types/react-dom` at `^18.3.0`. This change completes the bump by aligning `@types/react-dom` to `^19`, eliminating an unmet peer-dependency.

## Investigation (boil-the-ocean, verified with tools)

Method: created two worktrees (`origin/main` baseline and the PR branch), ran `pnpm install`, `npx tsc --noEmit`, and the full `vitest` suite on BOTH, and diffed the results to isolate the React-19 delta from pre-existing noise.

### React 19 breaking-change audit — all clear
Greps across all 34 `.tsx` components in `apps/admin-ui/src/`:
- `ReactDOM.render()` removed → **0 usages** (admin-ui has no React root; AdminJS owns it).
- `act()` async-only → the single async-act render test (`tests/EmailServiceOAuth2Setup.render.test.tsx`) already uses async `act` from `@testing-library/react@16` (React-19-native).
- String refs removed → **0 usages**.
- Legacy context API removed → **0 usages** of `childContextTypes`/`getChildContext`/`contextTypes`.
- `propTypes` support removed from the React package → **0 usages** (and `@types/react` still ships the types regardless).
- `forwardRef` type changes → **0 usages** of `forwardRef`.
- JSX transform → `tsconfig.json` uses `"jsx": "react"` (classic runtime); every component keeps `import React`. No automatic-runtime migration involved; unchanged by the bump.

### Empirical parity (PR branch vs origin/main)
| Check | main | PR #183 | Delta |
|---|---|---|---|
| `tsc --noEmit` errored files (non-peer) | 12 | 12 (same set) | **0 new** |
| jsdom render tests | 62 pass | 62 pass | none |
| full vitest | 593 total, 590 pass, 3 fail | 593 total, 590 pass, 3 fail | **identical** |

The 3 failures (`test_ssh_test_panel.test.ts`, `test_permissions.test.ts`, `test_oauth2_providers_resource.test.ts`) are pre-existing on `main` and are source-text grep assertions, not React behavior. Out of scope.

### AdminJS 7 React-19 compatibility
`adminjs@^7.8.13` + `@adminjs/express@^6.1.1` bundle and serve their own React via the AdminJS component compiler at runtime. admin-ui's `react`/`react-dom` are dev+test-only deps (used by vitest jsdom render tests through `tests/__mocks__/*` stubs). `@testing-library/react@16.3.2` peer-accepts `^18 || ^19`. No AdminJS-side incompatibility surfaces.

## The one real defect
`@types/react-dom@18.3.7` declares `peerDependencies: { "@types/react": "^18.0.0" }`. With `@types/react@19.2.17` installed, this peer is unmet. Because no `src/` or `tests/` file imports react-dom types (only `react-router-dom` is imported), it produces no compile error in this codebase today — but it is a latent mismatch that pnpm and future type usage would surface. Aligning to `^19` is the correct, minimal completion of the dependabot bump.

## What changes and why
- `apps/admin-ui/package.json`: `@types/react-dom` `^18.3.0` → `^19.2.0` (match `@types/react@19`).
- `apps/admin-ui/pnpm-lock.yaml`: regenerated via `pnpm install`.

Nothing else. No `.tsx` edits — there is no `createRoot` migration to perform (admin-ui renders no root).

## Testing
```
cd apps/admin-ui
npx vitest run --project render-tests   # 62 passed (React 19 jsdom)
npx vitest run                          # 593 total / 590 pass / 3 pre-existing fail (unchanged)
npx tsc --noEmit                        # same 12-file baseline error set; no react-dom type errors
```
Success criterion: parity with the pre-fix baseline is preserved AND no `@types/react-dom`/`react-dom` peer or type error appears.

## Risk
Low. Dev/test-only type-definition alignment; runtime React for the served UI is owned by AdminJS and untouched. Full reproduction performed; React 19 introduces zero new failures.
