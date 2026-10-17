# Bump admin-ui `uuid` 11 → 14

## Purpose

Dependabot PR #181 raises `@mintkey/admin-ui`'s `uuid` dependency from `^11.0.0` to `^14.0.0`. This document records what actually changes, why the raw Dependabot diff is insufficient, and how to verify the upgrade.

## Context: what changed in uuid between v11 and v14

- **v7 (already past for this repo):** uuid removed deep sub-path exports. `import { v4 } from 'uuid/v4'` no longer works; only the package-root named export `import { v4 } from 'uuid'` is supported. uuid also began shipping its own TypeScript declarations (`dist/index.d.ts`), making `@types/uuid` obsolete.
- **v11 → v14:** ESM/exports hardening and internal changes; the public named-export API (`v1`, `v3`, `v4`, `v5`, `v6`, `v7`, `validate`, `version`, `parse`, `stringify`, `NIL`, `MAX`) is stable. No call-site changes required for code already on the named-export form.

## Breaking-change audit (verified with tools, not assumed)

- **Sub-path imports:** `grep -rn "uuid/v"` across `apps/admin-ui` (ts/tsx/js, excluding node_modules) → **zero hits**. No deep-import breakage.
- **Only runtime usage:** `apps/admin-ui/src/lib/signed-request.ts:25` — `import { v4 as uuidv4 } from "uuid";`, used at line 88 (`.setJti(uuidv4())`). This is the supported v14 form; no change needed. Other `uuid` text matches in the repo are string literals (resource `type: "uuid"`, comments), not imports.
- **Runtime check:** installed `uuid@14.0.0` in isolation; `import { v4 } from 'uuid'; v4()` returns a valid UUID. Named export confirmed present and callable.
- **Types:** v14's `package.json` declares `types: ./dist/index.d.ts` and ships full `dist/*.d.ts`. `@types/uuid@^10.0.0` (devDependencies) is therefore redundant.
- **tsc:** `npx tsc --noEmit | grep uuid` → no uuid-related diagnostics. (Pre-existing unrelated TS2307 errors for `@adminjs/design-system` / `react-router-dom` are missing-transitive-peer noise and predate this PR.)
- **Engines:** uuid@14 declares no `engines` constraint; repo runs Node 22 — no conflict.

## The real defect in the Dependabot diff

`apps/admin-ui/package.json` carries a `pnpm.overrides` block. Dependabot bumped `dependencies.uuid` to `^14.0.0` (line 28) **but left `pnpm.overrides.uuid` at `^11.0.0`** (line 44). pnpm overrides take precedence over the dependency range, so after `pnpm install` the resolved version is **still `uuid@11.1.1`** — verified in `node_modules/uuid/package.json` (`"version": "11.1.1"`) and in `pnpm-lock.yaml` (`uuid@11.1.1`). **As shipped, the PR upgrades nothing.**

Additionally, `pnpm-workspace.yaml` also carries an override `"uuid": "^11.1.1"` which pnpm uses in resolution and which Dependabot also did not update.

## What to change and why

1. **`pnpm.overrides.uuid: "^11.0.0"` → `"^14.0.0"`** in `package.json` (required). Without this the override pins v11 and the bump is inert. This is the load-bearing change.
2. **`overrides.uuid: "^11.1.1"` → `"^14.0.0"`** in `pnpm-workspace.yaml` (required). pnpm resolves from the workspace file; the package.json override alone is insufficient.
3. **Remove `@types/uuid: "^10.0.0"`** from devDependencies in `package.json` (recommended). uuid bundles its own types since v7; the external `@types/uuid` is obsolete dead weight describing an older API.
4. **Regenerate `pnpm-lock.yaml`** via `pnpm install --lockfile-only` so the lock resolves `uuid@14` (and drops `@types/uuid@10` if removed).

No source files change.

## Testing

```sh
cd apps/admin-ui
pnpm install --lockfile-only            # regenerate lock under the synced override
grep -n 'uuid@' pnpm-lock.yaml          # expect uuid@14.x.x, NOT uuid@11.1.1
node -e "console.log(require('./node_modules/uuid/package.json').version)"  # expect 14.x
npx tsc --noEmit 2>&1 | grep -i uuid || echo 'no uuid type errors'  # expect none
npx vitest run                          # signed-request + p0 boot suites green
```

Acceptance: lockfile resolves `uuid@14`, `signed-request` JWT signing still produces a valid `jti`, vitest green, no new tsc errors.

## Risk

Low. One-line override sync + one obsolete devDep removal + lockfile regen. Single named-export call site, already v14-shaped. Fully reversible.
