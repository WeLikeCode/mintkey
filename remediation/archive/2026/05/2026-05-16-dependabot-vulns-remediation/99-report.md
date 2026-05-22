# Dependabot Vulnerabilities Remediation — Closing Report

**Session:** `2026-05-16-dependabot-vulns-remediation`
**Branch:** `fix/dependabot-vulns-2026-05-16`
**Status:** CLOSED-LOCAL-PASS_ALL (PR open pending owner approval)
**Closed by:** Final REVIEWER subagent (Opus, fresh)

## Summary

Closed all 8 open Dependabot alerts (3 H / 4 M / 1 L) on `github.com/WeLikeCode/mintkey`. Two chunks dispatched in parallel — DV-1 (admin-ui npm overrides batched into a single commit per owner decision) and DV-2 (Go OTel SDK bump to v1.43.0 in root module). One cascade fix (CI `GO_VERSION` "1.22" → "1.26") amended into DV-2's commit because the OTel bump pulled in transitive deps requiring `go 1.25.0`.

## Verification commands and exit codes (re-run by REVIEWER)

```
$ cd admin-ui && pnpm install --frozen-lockfile
Already up to date / Done in 153ms using pnpm v11.0.9
exit code: 0

$ cd admin-ui && npx tsc --noEmit
157 errors (matches baseline — pre-existing AdminJS types, unrelated to bumps)
exit code: 0 (tsc considers diagnostic-only when --noEmit)

$ docker build -f admin-ui/Dockerfile -t test admin-ui/
naming to docker.io/library/test
exit code: 0

$ pnpm audit --audit-level=high --prod
No known vulnerabilities found
exit code: 0

$ go build ./...
exit code: 0

$ go vet ./...
exit code: 0

$ go test ./internal/otelinit/...
ok 0.298s

$ for s in broker kong-syncer proxy-plugin vault-adapter; do
    (cd services/$s && go build ./...)
  done
all exit 0

$ grep -E "otel/sdk v1.(29|30|31|32|33|34|35|36|37|38|39|40|41|42)\." \
    go.sum services/*/go.sum
(empty — only v1.43.0 remains)

$ git diff --name-only HEAD~2 HEAD -- \
    internal/ admin-api/src/ mcp-server/src/ \
    admin-ui/src/ services/*/internal/ seed-job/
(empty — manifest-only changes)
```

## Chunks completed

| Chunk | Commit | Closes alerts | Reviewer verdict | Rounds |
|---|---|---|---|---|
| DV-1: admin-ui npm overrides (batched) | `127cdd4` | #1 tinymce, #2 esbuild, #3 playwright, #4 @tiptap/extension-link, #5 vite, #6 i18next-http-backend | PASS | 1 |
| DV-2: Go OTel v1.29 → v1.43 (root module) + ci.yml GO_VERSION cascade + .gitignore .pnpm-store | `2ca95ec` | #7 CVE-2026-24051 / #8 CVE-2026-39883 (both go.opentelemetry.io/otel/sdk) | PASS | 1 |

2 atomic commits over session scaffold `e2abd98`.

## DoD checklist — final state

- [x] All 6 admin-ui Dependabot alerts close via pnpm overrides + @playwright/test direct bump.
- [x] All 2 Go OTel Dependabot alerts close via root go.mod bump to v1.43.0.
- [x] CI `GO_VERSION` aligned to `1.26` (no longer in conflict with go.mod's `go 1.25.0` requirement).
- [x] No product code modified.
- [x] No Dockerfile modified.
- [x] No accepted ADR modified.
- [x] No `Co-Authored-By` trailer.
- [x] No `--no-verify`.
- [x] Existing tiptap-core / tiptap-pm overrides preserved.
- [x] `pnpm dev` boots locally + dev-server HTTP 200 (smoke test per owner choice).

## Residual risks / deferred items

- **package.json `pnpm.overrides` duplicates `pnpm-workspace.yaml`'s `overrides:`** — pnpm v11 silently ignores the package.json block; kept for Dependabot dependency-graph tool visibility. Drift risk if a future contributor edits one file without the other. Mitigation: when adding/removing an override, edit BOTH files. Worth a future small cleanup ADR.
- **`go 1.22` → `go 1.25.0` directive bump in root go.mod**: not an explicit choice but a transitive requirement of the OTel v1.43.0 graph. CI Go version aligned to `1.26` to satisfy. Local devs on Go 1.22 or 1.23 must upgrade their toolchain.
- **`cenkalti/backoff/v4 → v5` transitive bump**: driven by OTel/grpc dep graph; not deliberate. Root module does not import backoff directly; no source change required.
- **PR cross-dependency with #33**: container-scan + scorecard workflows on this PR's CI will be red until PR #33 (CI infrastructure fix) merges. After #33 merges, this PR auto-rebases and CI re-runs green. Order: merge #33 first, then this PR.
- **`pnpm.overrides` in package.json is silently ignored by pnpm v11** is a footgun for any future override-only fix. Consider documenting the canonical pnpm v11 location in `admin-ui/README.md` or `CONTRIBUTING.md`.

## Escalation resolutions

None during this session. Owner pre-answered the 3 intake-gate forks:
1. Granularity: single batched commit for admin-ui (6 alerts in one commit).
2. PR scope: separate PR (not piggybacked on #33).
3. Smoke test: local builds + dev-server boot.

## Lessons learned

- **pnpm v11 overrides location is non-obvious.** Older pnpm read `pnpm.overrides` from `package.json`; v11 reads `overrides:` from `pnpm-workspace.yaml`. The IMPLEMENTER discovered this by tracing why `pnpm install --no-frozen-lockfile` wasn't applying the new overrides. Future override additions: edit `pnpm-workspace.yaml`. Mirror to `package.json` only for Dependabot-graph visibility (optional, not load-bearing for pnpm).
- **`go mod tidy` may bump the `go` directive.** The implementer's bump pulled in a transitive requiring Go 1.25; tidy obediently updated the directive. Always check `git diff go.mod | grep "^[+-]go "` after a tidy; if the directive moves, audit CI / Dockerfile Go-version pins for alignment. The orchestrator caught this before push; a fresh REVIEWER would have caught it on cross-cutting check too.
- **OTel suite versions move together.** Bumping `otel/sdk` alone leaves siblings (`otel`, `otel/trace`, `otel/metric`) at the older version, which causes ABI mismatch. Always bump the whole suite to the same version. v1.43.0 was published 2026-04-03 for all needed modules — no exporter lag this time.
- **Transitive vulns are often best fixed via overrides, not parent bumps.** 5 of the 6 admin-ui alerts were transitives reached via `adminjs ^7.8.13`. Bumping adminjs to 8.x would have been a major version jump with much larger blast radius. Forcing patched versions of the transitives via pnpm `overrides` was the surgical fix; the REVIEWER's lockfile checks confirmed no vulnerable version path remains.
