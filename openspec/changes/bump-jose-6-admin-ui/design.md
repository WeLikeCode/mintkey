# Bump jose 5 → 6 in admin-ui

## Purpose

Dependabot PR #208 upgrades `jose` from `^5.9.6` to `^6.2.3` in `apps/admin-ui`. `jose` is used by the admin-ui BFF to mint the Ed25519-signed `AdminUiSignedRequest` JWT (per ADR-0019 / ADR-0014.5/.6) that authenticates every state-changing call forwarded to admin-api. This document records the single source-level adjustment required for the major bump and the verification performed.

## Breaking changes in jose v6 (relative to this repo's usage)

1. **`KeyLike` type removed.** v5 exported a `KeyLike` type alias used to type imported/generated keys. v6 removes it and exposes `CryptoKey` (and `KeyObject`) instead. `importPKCS8` now returns `Promise<CryptoKey>`; `generateKeyPair` returns `{ privateKey: CryptoKey; publicKey: CryptoKey }`; `SignJWT.prototype.sign` accepts `CryptoKey | KeyObject | JWK | Uint8Array`. This is the **only** change that affects the codebase.
2. **ESM-only / no CJS default export.** Not applicable: `apps/admin-ui` is already `"type": "module"` and builds via `tsc` with `module: ESNext`, `moduleResolution: bundler`. No CJS entry is used.
3. **Exports map tightened (no deep sub-path imports).** Not applicable: only top-level named exports are imported (`SignJWT`, `importPKCS8` in src; `generateKeyPair`, `exportPKCS8` in tests).
4. **Compact sign/verify API.** Unchanged for our call sites — `new SignJWT(payload).setProtectedHeader(...).set*(...).sign(key)` is identical across v5/v6.

## What was changed and why

`apps/admin-ui/src/lib/signed-request.ts` referenced the now-removed `KeyLike` type in four places (import, module-level `_privateKey`, `loadPrivateKey` return type, and the `privateKey?` option). Each `KeyLike` is replaced with `CryptoKey`, the type jose v6 actually returns from `importPKCS8`/`generateKeyPair`. The change is type-level only; no runtime behavior changes. Scope is held to the minimum surface that turns the build green (Simplicity First / Surgical Changes).

No package.json edit is needed beyond what Dependabot already committed (`"jose": "^6.2.3"`). No lockfile edit beyond Dependabot's.

## Evidence / reproduction

- Worktree at `origin/dependabot/npm_and_yarn/apps/admin-ui/jose-6.2.3`, `pnpm install` → jose 6.2.3 resolved.
- `grep KeyLike node_modules/jose/dist/types/index.d.ts` → absent; `CryptoKey` present (exported from `./types.d.ts`).
- `npx tsc --noEmit` on the unpatched branch yields exactly one jose-related error: `src/lib/signed-request.ts(24,37): error TS2305: Module '"jose"' has no exported member 'KeyLike'.` (Other tsc errors on the branch are pre-existing and unrelated: uninstalled optional AdminJS peer deps `@adminjs/design-system` / `react-router-dom`, and AdminJS `PageHandler`/axios typing — none introduced by this PR.)
- After applying the `KeyLike`→`CryptoKey` patch, isolated `tsc --noEmit` on `signed-request.ts` exits 0.

## Testing

- `npx vitest run tests/test_signed_request.test.ts` → 5/5 pass against jose 6.2.3, both before and after the patch (vitest does not type-check; the type-only import is erased at runtime, which is why the break is build-time only).
- Patched test-file type-check: `generateKeyPair` (→ `CryptoKey`) flows into `buildSignedRequest({ privateKey })` with no error.
- Recommended CI gates to confirm: `pnpm --filter admin-ui build` (the `tsc` build — this is the gate that was red) and `pnpm --filter admin-ui test`.

## Risk

Low. One file, four type references, no runtime change, no contract/wire-surface change, no ADR impact. The Ed25519 EdDSA signing path (ADR-0019) is byte-for-byte unchanged.
