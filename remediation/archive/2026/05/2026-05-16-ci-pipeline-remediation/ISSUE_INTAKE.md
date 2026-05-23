# Issue Intake — 2026-05-16-ci-pipeline-remediation

**Session:** `team/remediation/2026-05-16-ci-pipeline-remediation/`
**Reported:** 2026-05-16
**Reporter:** Owner (user) — "Check mintkeys CI pipeline. It seems to be failed state"
**Triaged via:** Mintkey-brokered GitHub Actions API (agent_01KRRQAKNHDRD55F6Z8518F27E → svc_01KRRQ9Q7V9KN4R2H9P505B9WW)

---

## Problem statement (required)

The CI pipeline on `github.com/WeLikeCode/mintkey` is in a chronically failed state across four distinct workflow bugs. All 32 open Dependabot PRs are blocked from merging because the required status check `dependency-review` cannot pass while sibling workflows fail. Failures are structural CI defects — they are NOT caused by Dependabot's bumps, and the same failures will recur on every PR until the workflows are fixed.

## User-visible symptom (required)

- `Actions` tab on GitHub shows ❌ across most recent runs.
- 32 open Dependabot PRs show `mergeable_state: blocked`.
- `scorecard.yml` fails on every run at "Set up job".
- `ci.yml` fails the `Lint Go` job during Go toolchain setup.
- `container-scan.yml` shows 10 failing matrix jobs.
- Only `codeql.yml` is consistently green.

## Expected behavior (required)

- `scorecard.yml`, `ci.yml`, `container-scan.yml`, `dependency-review.yml`, `playwright.yml`, `codeql.yml` all green on PR runs.
- `dependency-review` status check passes → Dependabot PRs become mergeable.
- A clean PR (e.g., the fix-CI PR itself) lands all checks green.

## Evidence (required)

Pulled via GitHub Actions API on 2026-05-16. Exact failures:

### Bug CI-A — scorecard.yml: invalid action version
- Run: `25965785316` (main branch, 2026-05-16)
- Job: `76328940486` ("Set up job" step)
- Error: `Unable to resolve action 'ossf/scorecard-action@v2', unable to find version 'v2'`
- Root cause: `ossf/scorecard-action` does not publish a floating `v2` tag; only specific semver tags (e.g., `v2.4.0`) or SHAs.

### Bug CI-B — ci.yml Lint Go: cache collision
- Run: `25965858777`
- Job: `76329132482` (Lint Go)
- Error (sample, repeated dozens of times): `/usr/bin/tar: ../../../go/pkg/mod/golang.org/toolchain@v0.0.1-go1.26.2.linux-amd64/src/net/http/h2_error.go: Cannot open: File exists`
- Root cause: `actions/setup-go` extracts the Go toolchain cache, then `golangci/golangci-lint-action@v6` re-extracts the same toolchain, hitting "File exists" on every file. The action's cache and setup-go's cache collide.

### Bug CI-C1 — container-scan.yml: build context missing sibling `mintkey-models`
- Run: `25965858776` / Job: `76329132598` (admin-api)
- Error: `failed to compute cache key: failed to calculate checksum of ref ...: "/mintkey-models/mintkey_models": not found`
- Dockerfile line: `COPY mintkey-models/mintkey_models/ src/mintkey_models/` (Dockerfile:13)
- Root cause: workflow sets build context to `admin-api/` (or per-service dir) but Dockerfile expects repo-root context to see sibling `mintkey-models/`.
- Affected services: admin-api, mcp-server, vault-adapter, proxy-plugin (5 jobs).

### Bug CI-C2 — container-scan.yml admin-ui: pnpm lockfile drift
- Job: `76329132590` (admin-ui)
- Error: `[ERR_PNPM_LOCKFILE_CONFIG_MISMATCH] Cannot proceed with the frozen installation. The current "overrides" configuration doesn't match the value found in the lockfile`
- Root cause: `admin-ui/package.json` has `overrides` (or `pnpm.overrides`) section that drifted from `admin-ui/pnpm-lock.yaml`.

### Bug CI-D — container-scan.yml Trivy gate: HIGH/CRITICAL exit-1
- Jobs: `76329132592` (seed-job), `76329132597` (jaeger-auth) — "Trivy scan" step exit code 1.
- Root cause: HIGH/CRITICAL CVEs in base images (`python:3.12-slim` Debian 13, custom jaeger) trip `exit-code: 1` gate.

## Scope (required)

May be changed:
- `.github/workflows/scorecard.yml` (CI-A)
- `.github/workflows/ci.yml` (CI-B)
- `.github/workflows/container-scan.yml` (CI-C, CI-D)
- `admin-ui/pnpm-lock.yaml` (regenerate — CI-C2)
- `admin-ui/package.json` if overrides need adjustment for clean lockfile regen
- `.trivyignore` (NEW — CI-D allow-list)
- Session folder `team/remediation/2026-05-16-ci-pipeline-remediation/`

## Out of scope (required)

MUST NOT be touched:
- Product code (`admin-api/src/`, `mcp-server/src/`, `services/`, `admin-ui/src/`)
- Dockerfiles for product services (unless build-arg or COPY path change strictly required to fix CI-C1 — prefer workflow-side fix)
- Dependabot dep bumps (separate PRs, already approved in bulk)
- Branch protection / GitHub repo settings
- Accepted ADRs in `docs/architecture/01-architecture/adr/`
- Other Mintkey services not listed in Scope

## Risk level (required)

- **CI** (primary): blocks all 32 Dependabot PR merges and all future PR merges until fixed.
- **Release**: the CI gate is the release-readiness signal.
- **Security**: low — `.trivyignore` allow-list adds documented CVE exceptions with expiry dates, not a blanket gate disable. Vulnerabilities still surface in Trivy logs + future scans pick up new CVEs.

## Verification target (required)

Per chunk:
- **CI-A**: `actionlint .github/workflows/scorecard.yml` clean + push branch → scorecard.yml run reaches `Run scorecard` step (no "unable to resolve" error).
- **CI-B**: push branch → ci.yml `Lint Go` job completes without `tar: Cannot open: File exists`. Golangci-lint runs to completion (pass or fail on actual lint findings — but it RUNS).
- **CI-C1**: locally: `docker build -f admin-api/Dockerfile -t test-admin-api .` from repo root succeeds. Push → container-scan.yml `Build image — admin-api` job passes.
- **CI-C2**: locally: `cd admin-ui && pnpm install --frozen-lockfile` succeeds. Push → container-scan.yml `Build image — admin-ui` job passes.
- **CI-D**: push → container-scan.yml `Trivy scan — seed-job` and `Trivy scan — jaeger-auth` jobs exit 0. SARIF still uploaded; Security tab still shows findings.

Final acceptance: push `fix/ci-pipeline-remediation` branch → open PR → all 6 workflow runs green (CodeQL, dep-review, ci, container-scan, scorecard, playwright).

## Owner decisions needed

- ✅ **Trivy CVE-gate handling**: Owner chose **Allow-list known CVEs** (`.trivyignore`).
- ✅ **pnpm lockfile fix**: Owner chose **Regenerate lockfile** (commit updated `pnpm-lock.yaml`; keep `--frozen-lockfile` enforcement in Docker build).
- ✅ **Session scope**: Owner chose **Workflows + pnpm-lock.yaml regen** in one session.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line and run/job IDs)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted
