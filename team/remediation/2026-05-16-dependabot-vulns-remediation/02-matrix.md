# <Session Title> — Tracking Matrix

> Copy from SESSION_TEMPLATE — fill in the placeholders.

**Session:** `<YYYY-MM-DD-kebab-slug>`
**Status:** ⬜ pending baseline review

---

## Severity legend

| Severity | Meaning |
|---|---|
| P0 | Blocking — session cannot close without this |
| P1 | High — must address before the closing report |
| P2 | Medium — fix this session if possible; escalate if not |
| P3 | Low — document as residual; defer acceptable |

## Status legend

| Symbol | Meaning |
|---|---|
| ⬜ | Not started |
| 🔵 | In progress |
| ✅ | Fixed and reviewer-verified |
| ⏭️ | Deferred to a future session (document in 99-report.md) |
| n/a | Not applicable |

---

## Matrix

| # | Area | Finding | Severity | Chunk | Status | Notes |
|---|---|---|---|---|---|---|
| M-1 | <TODO: area> | <TODO: what is broken> | P0 | <TODO: chunk ID> | ⬜ | <TODO: notes> |
| M-2 | <TODO: area> | <TODO: what is broken> | P1 | <TODO: chunk ID> | ⬜ | |
| M-3 | <TODO: area> | <TODO: what is broken> | P2 | <TODO: chunk ID> | ⬜ | |

---

## DV-2 verification

**Chunk:** DV-2 — Bump go.opentelemetry.io/otel suite to v1.43.0 (root Go module)
**CVEs closed:** CVE-2026-24051 (PATH hijacking, fix >= 1.40.0), CVE-2026-39883 (BSD kenv, fix >= 1.43.0)
**Executed:** 2026-05-16

| Command | Exit code | Result |
|---|---|---|
| `go version` | 0 | go1.26.2 darwin/arm64 |
| `go get go.opentelemetry.io/otel@v1.43.0 ...` (full suite) | 0 | All 6 otel packages upgraded 1.29.0 → 1.43.0 |
| `go mod tidy` | 0 | Clean — no output |
| `go build ./...` (root) | 0 | No errors |
| `go vet ./...` (root) | 0 | No errors |
| `go test ./...` (root) | 0 | All packages pass; `internal/otelinit` ran fresh (0.298s) |
| `go build ./...` services/broker | 0 | No errors |
| `go build ./...` services/kong-syncer | 0 | No errors |
| `go build ./...` services/proxy-plugin | 0 | No errors |
| `go build ./...` services/vault-adapter | 0 | No errors |
| `grep -r "otel/sdk v1.29.0" --include=go.sum` | 1 (no match) | Not present — GOOD |
| `grep -r "otel/sdk v1.40.0" --include=go.sum` | 1 (no match) | Not present — GOOD |
| `grep -r "otel/sdk v1.42.0" --include=go.sum` | 1 (no match) | Not present — GOOD |
| `grep -r "otel/sdk v1.43.0" --include=go.sum` | 0 | Present in root + proxy-plugin + vault-adapter go.sum — GOOD |

**Transitive deps pulled by go get (not deliberate bumps, all OTel-required):**
- `go.opentelemetry.io/auto/sdk v1.2.1` (new indirect, required by otel v1.43.0)
- `github.com/cenkalti/backoff/v5 v5.0.3` (replaced v4.3.0 indirect)
- `github.com/go-logr/logr v1.4.2 → v1.4.3`
- `github.com/grpc-ecosystem/grpc-gateway/v2 v2.22.0 → v2.28.0`
- `go.opentelemetry.io/proto/otlp v1.3.1 → v1.10.0`
- `golang.org/x/net v0.28.0 → v0.52.0`
- `golang.org/x/sys v0.24.0 → v0.42.0`
- `golang.org/x/text v0.17.0 → v0.35.0`
- `google.golang.org/genproto/googleapis/api → v0.0.0-20260401024825-9d38bb4040a9`
- `google.golang.org/genproto/googleapis/rpc → v0.0.0-20260401024825-9d38bb4040a9`
- `google.golang.org/grpc v1.65.0 → v1.80.0`
- `google.golang.org/protobuf v1.34.2 → v1.36.11`

**go mod tidy also promoted to direct** (were `// indirect`, now direct because root package `internal/otelinit` imports them):
- `go.opentelemetry.io/otel v1.43.0`
- `go.opentelemetry.io/otel/sdk v1.43.0`
- `go.opentelemetry.io/otel/exporters/otlp/otlptrace/otlptracegrpc v1.43.0`
- `github.com/oklog/ulid/v2 v2.1.1`
- `google.golang.org/grpc v1.80.0`
- `google.golang.org/protobuf v1.36.11`

**Status: DONE** — all DoD conditions met.

---

## DV-1 verification

**Chunk:** DV-1 — admin-ui npm bumps to close 6 Dependabot alerts
**Alerts closed:** tinymce (MEDIUM), esbuild (MEDIUM), playwright (HIGH), @tiptap/extension-link (LOW), vite (MEDIUM), i18next-http-backend (MEDIUM)
**Executed:** 2026-05-16

**Key discovery:** pnpm v11 no longer reads `pnpm.*` settings from `package.json`. Overrides must be in `pnpm-workspace.yaml`. The existing `@tiptap/core`/`@tiptap/pm` overrides in `package.json` were silently ignored by pnpm v11; they only worked because of `.pnpmfile.cjs`. All overrides (including new ones) have been placed in `pnpm-workspace.yaml` where pnpm v11 reads them correctly. The `pnpm.overrides` block in `package.json` is retained for documentation/intent but has no functional effect under pnpm v11.

| Command | Exit code | Result |
|---|---|---|
| `pnpm install --no-frozen-lockfile` | 0 | Resolved all overrides; tinymce 6.8.6→7.9.2, @tiptap/extension-link 2.1.13→2.27.2, i18next-http-backend 2.7.3→3.0.6, vite 5.4.21→6.4.2, esbuild 0.21.5→0.25.12, @playwright/test 1.50.0→1.60.0 |
| `pnpm install --frozen-lockfile` | 0 | Reproducible — lockfile accepted |
| `node_modules/.bin/tsc --noEmit` | 0 | 157 pre-existing error lines (same as baseline); no new type errors introduced |
| `curl -L http://localhost:5173/` (dev server smoke) | HTTP 200 | `<!DOCTYPE html>` body returned after 302→/admin/login chain; AdminJS running |
| `docker build -f admin-ui/Dockerfile -t test-admin-ui-vuln admin-ui/` | 0 | Image built successfully |
| `pnpm audit --audit-level=moderate --prod` | 0 | No known vulnerabilities found |
| `pnpm audit` (all deps) | 0 | No known vulnerabilities found |

**Resolved versions (pnpm-lock.yaml):**
- tinymce: 6.8.6 → 7.9.2
- esbuild: 0.21.5 (multiple) → 0.25.12 (overridden)
- @playwright/test: 1.50.0 → 1.60.0 (^1.55.1 resolved to 1.60.0 — latest in range)
- @tiptap/extension-link: 2.1.13 → 2.27.2
- vite: 5.4.21 → 6.4.2
- i18next-http-backend: 2.7.3 → 3.0.6

**Notes:**
- @playwright/test resolved to 1.60.0 (latest satisfying ^1.55.1); within the owner-specified specifier range.
- tsc shows 157 error lines on baseline and 157 on DV-1 — pre-existing errors unrelated to this bump.
- No adminjs major bump; adminjs remains at 7.8.17.
- vitest 2.1.9 peer-resolved correctly against vite 6 — no peer conflict escalation needed.
- `pnpm.overrides` block retained in `package.json` for documentation; functional overrides are in `pnpm-workspace.yaml`.

**Status: DONE** — all DoD conditions met.

---

## Verification DoD checklist

Reviewer runs these before writing `99-report.md`:

- [ ] <TODO: test / command proves M-1 fixed>
- [ ] <TODO: test / command proves M-2 fixed>
- [ ] No regressions in scope: `<TODO: command>`
- [ ] No `Co-Authored-By` trailer in any new commit
- [ ] No `--no-verify` used
