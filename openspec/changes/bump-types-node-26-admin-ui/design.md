# Bump @types/node 22 -> 26 in apps/admin-ui (PR #211)

## Purpose

Dependabot PR #211 raises the `@types/node` devDependency in `apps/admin-ui`
from `^22.9.0` to `^26.0.0` (resolved 26.0.0). `@types/node` 26 corresponds to
the Node.js 26 API surface. The admin-ui container already runs on
`node:26-bookworm-slim` (see `apps/admin-ui/Dockerfile`), so this bump aligns
the development type definitions with the actual runtime Node major.

## Breaking-change surface (and why none apply here)

`@types/node` 26 carries several known type tightenings. Each was checked
against `apps/admin-ui/src/`:

1. **`Buffer.from()` narrowing** — affects the `arrayLike` overload. admin-ui
   only uses `Buffer.from(string, "base64")`, `Buffer.from(buffer)`, and
   `Buffer.concat([...])` (all in `src/lib/api-client.ts`). None are affected.
2. **`process.env` values `string | undefined`** — every read in `src/` is
   already defensive: `?? "<default>"`, a truthiness guard (`if (val)`,
   `if (!kek)`), `=== "production"` comparison, or indexed `process.env[name]`
   access (which has always been `string | undefined`). Files reviewed:
   `src/dashboard.ts`, `src/auth.ts`, `src/index.ts`, `src/resources/tenants.ts`,
   `src/resources/services.ts`, `src/lib/api-client.ts`, `src/lib/rest-resource.ts`,
   `src/lib/signed-request.ts`, `src/lib/public-urls.ts`.
3. **Globals removed / moved to explicit imports** — admin-ui uses `setTimeout`
   via `ReturnType<typeof setTimeout>` (browser/React component scope) and
   `process.exit` / `readFileSync` (already imported from `fs`). No removed
   global is relied upon.
4. **`ReadableStream` / `WritableStream` tightening** — no usage in `src/`.

## What changed and why

Only the dependency pin (`package.json` + `pnpm-lock.yaml`), exactly as produced
by Dependabot in commit `0b3dc46`. No source file requires modification. The
bump is purely a devDependency type-definition refresh that matches the runtime.

## Evidence

A read-only worktree off the PR branch was used to run `tsc` against both type
versions in the same checkout:

| @types/node | tsc errors | error-code breakdown                                  |
|-------------|-----------:|-------------------------------------------------------|
| 22.20.0     | 111        | 50 TS2353, 32 TS2307, 26 TS2352, 2 TS2322, 1 TS2345   |
| 26.0.0      | 111        | 50 TS2353, 32 TS2307, 26 TS2352, 2 TS2322, 1 TS2345   |

`diff` of the sorted error lines from both runs produced **no differences**. The
111 errors are pre-existing and unrelated to Node types — they stem from
AdminJS peer dependencies (`@adminjs/design-system`, `react-router-dom`) not
being installed as direct deps (so bare `tsc` cannot resolve their declarations)
and from AdminJS/Axios API type drift. They are present identically on the base
branch.

## Why CI is unaffected

The admin-ui `build` script (`tsc`) is not part of CI or the container build:
- `apps/admin-ui/Dockerfile` runs the app via `tsx` (`CMD ["node_modules/.bin/tsx", "src/index.ts"]`) — transpile-only, no type check.
- CI (`.github/workflows/ci.yml`) builds the image via `docker compose build` and runs vitest (esbuild transpile-only).
Neither path type-checks, so even the pre-existing `tsc` errors do not gate
merges, and this type-only bump cannot affect runtime behavior.

## Testing

No new tests needed (type-definition-only change with no source edits).
Regression check (run in `apps/admin-ui` on the PR branch):
```sh
pnpm install --frozen-lockfile=false
npx tsc | grep -c 'error TS'          # expect 111 (unchanged vs base)
pnpm vitest run                       # existing suite must stay green
```
For full equivalence proof, temporarily `pnpm add -D @types/node@22`, capture the
sorted `tsc` errors, restore 26, capture again, and `diff` — the diff must be empty.

## Recommendation

Merge as-is. Low risk; zero source changes.
