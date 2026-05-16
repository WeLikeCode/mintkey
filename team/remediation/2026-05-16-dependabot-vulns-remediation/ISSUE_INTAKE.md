# Issue Intake — 2026-05-16-dependabot-vulns-remediation

**Session:** `team/remediation/2026-05-16-dependabot-vulns-remediation/`
**Reported:** 2026-05-16
**Reporter:** Owner — "tackle next the dependable vulnerabilities from the image" (8 open Dependabot alerts on WeLikeCode/mintkey)
**Triaged via:** Mintkey-brokered GitHub Dependabot Alerts API

---

## Problem statement (required)

GitHub Dependabot reports 8 open vulnerability alerts on `github.com/WeLikeCode/mintkey` (3 high, 4 medium/moderate, 1 low). All 8 have published patched versions — no zero-days awaiting upstream. Six target `admin-ui/pnpm-lock.yaml` (npm ecosystem), two target `go.mod` (Go ecosystem); the two Go alerts both concern the same module (`go.opentelemetry.io/otel/sdk`) and are jointly fixed by bumping to `>= 1.43.0`.

## User-visible symptom (required)

- GitHub Security tab → Dependabot alerts → 8 open.
- Push to `main` triggers a remote warning: "GitHub found 8 vulnerabilities on WeLikeCode/mintkey's default branch (3 high, 4 moderate, 1 low)".
- Future product users (post-public-release) will see the vulnerabilities flagged in repo signals (Scorecard, deps.dev, etc.).
- No exploit observed in any Mintkey deployment; this is preventive remediation.

## Expected behavior (required)

- All 8 alerts closed (state: `fixed`) after PR merges.
- `admin-ui/pnpm-lock.yaml` reflects patched versions of: tinymce, esbuild, playwright, @tiptap/extension-link, vite, i18next-http-backend.
- `go.mod` for each Go service has `go.opentelemetry.io/otel/sdk >= 1.43.0` (the higher of the two patched-from versions).
- admin-ui builds + boots clean locally (`pnpm install --frozen-lockfile` + `pnpm dev` reaches "ready" without errors).
- Go services build + their existing tests pass.

## Evidence (required)

Fetched 2026-05-16 via Dependabot Alerts API (`GET /repos/WeLikeCode/mintkey/dependabot/alerts?state=open`):

| # | Sev | Ecosystem/Package | Vulnerable range | Fix | Scope | Manifest | CVE / GHSA |
|---|---|---|---|---|---|---|---|
| 1 | MEDIUM | npm / tinymce | `< 7.0.0` | `7.0.0` | runtime | admin-ui/pnpm-lock.yaml | CVE-2024-29881 / GHSA-5359-pvf2-pw78 |
| 2 | MEDIUM | npm / esbuild | `<= 0.24.2` | `0.25.0` | development | admin-ui/pnpm-lock.yaml | (no CVE) / GHSA-67mh-4wv8-2f99 |
| 3 | HIGH   | npm / playwright | `< 1.55.1` | `1.55.1` | development | admin-ui/pnpm-lock.yaml | CVE-2025-59288 / GHSA-7mvr-c777-76hp |
| 4 | LOW    | npm / @tiptap/extension-link | `< 2.10.4` | `2.10.4` | runtime | admin-ui/pnpm-lock.yaml | CVE-2025-14284 / GHSA-vhrc-hgrq-x75r |
| 5 | MEDIUM | npm / vite | `<= 6.4.1` | `6.4.2` | development | admin-ui/pnpm-lock.yaml | CVE-2026-39365 / GHSA-4w7w-66w2-5vf9 |
| 6 | MEDIUM | npm / i18next-http-backend | `< 3.0.5` | `3.0.5` | runtime | admin-ui/pnpm-lock.yaml | CVE-2026-41691 / GHSA-q89c-q3h5-w34g |
| 7 | HIGH   | go / go.opentelemetry.io/otel/sdk | `>= 1.21.0, < 1.40.0` | `1.40.0` | runtime | go.mod | CVE-2026-24051 / GHSA-9h8m-3fm2-qjrq |
| 8 | HIGH   | go / go.opentelemetry.io/otel/sdk | `>= 1.15.0, <= 1.42.0` | `1.43.0` | runtime | go.mod | CVE-2026-39883 / GHSA-hfvc-g4fc-pqhx |

## Scope (required)

May be changed:
- `admin-ui/package.json` (bump 6 packages or their nearest direct deps that pull the vulnerable transitives)
- `admin-ui/pnpm-lock.yaml` (regenerated)
- `services/*/go.mod` / `services/*/go.sum` for each Go service that imports `go.opentelemetry.io/otel/sdk`
- `go.work` if it pins module versions
- Possibly `admin-ui/.pnpmfile.cjs` if existing tiptap pins (`@tiptap/core@2.27.2`, `@tiptap/pm@2.27.2`) require coordination
- Session folder `team/remediation/2026-05-16-dependabot-vulns-remediation/`

## Out of scope (required)

MUST NOT be touched:
- Product code (admin-ui/src, admin-api/src, mcp-server/src, services/*/internal, etc.)
- Dockerfiles (deps come from manifests; Dockerfiles install via `pnpm install --frozen-lockfile` or `go build`)
- CI workflows (handled by sister PR fix/ci-pipeline-remediation)
- Accepted ADRs
- Other Mintkey services not importing `go.opentelemetry.io/otel/sdk`
- Existing `@tiptap/core: 2.27.2` and `@tiptap/pm: 2.27.2` overrides — DO NOT change those values (tiptap core API stable across 2.x patches; only `@tiptap/extension-link` needs bump and it lives under the same major)

## Risk level (required)

- **Security**: primary (3 high alerts; runtime-scope tinymce XSS + i18next path traversal + OTel PATH hijacking).
- **UX / regression**: medium — tinymce 6→7 is a major bump; potential editor API changes in admin-ui. Vite 6→6 is a patch. Playwright 1.x→1.55 is a minor.
- **CI**: low — the npm bumps regenerate pnpm-lock; Go bumps require `go mod tidy` + `go build` per service.

## Verification target (required)

Per chunk:

### DV-1 (admin-ui npm bumps)
- `cd admin-ui && pnpm update <packages> --latest` for the 6 vulnerable deps (preserving existing tiptap-core/pm overrides).
- `pnpm install --frozen-lockfile` exits 0.
- `pnpm audit --audit-level=high --prod` returns clean for high+ severity in prod deps.
- Typecheck succeeds (`pnpm tsc --noEmit` or equivalent) — confirms tinymce 6→7 didn't break compile.
- `pnpm dev` boots; HTTP GET on the dev server's port returns 200 OK (no manual click-through; the subagent automates the boot+probe).
- `docker build -f admin-ui/Dockerfile -t test-admin-ui admin-ui/` succeeds.

### DV-2 (Go OTel SDK bumps)
- Identify every Go service that imports `go.opentelemetry.io/otel/sdk`: `grep -rE "go.opentelemetry.io/otel/sdk" --include="go.mod" services/`.
- For each: `cd <service> && go get go.opentelemetry.io/otel/sdk@v1.43.0 && go mod tidy && go build ./... && go test ./...`.
- `go.sum` updated atomically alongside `go.mod`.
- No regression in OTel emit (existing telemetry tests still pass).

Final integration: push branch, open PR, observe CI. The CI is partially blocked by sister PR #33 (the CI infrastructure fix). Document that cross-dependency in the PR body; expect container-scan/scorecard to remain red until #33 merges and this PR rebases.

## Owner decisions

- ✅ **Granularity**: single batched commit for admin-ui (6 packages in one pnpm update + one commit).
- ✅ **PR scope**: separate PR on new branch `fix/dependabot-vulns-2026-05-16`. CI cross-dependency on #33 documented.
- ✅ **Smoke test**: local builds + `pnpm dev` boot smoke (no full E2E).
- ✅ **tiptap overrides**: preserve `@tiptap/core: 2.27.2` and `@tiptap/pm: 2.27.2`; only `@tiptap/extension-link` is bumped (different package, same major).

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (per-CVE table with alert IDs)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target (per chunk)
- [x] Owner decisions noted
