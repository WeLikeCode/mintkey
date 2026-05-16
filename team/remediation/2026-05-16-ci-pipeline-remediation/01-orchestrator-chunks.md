# CI Pipeline Remediation — Chunk Catalog

**Session:** `2026-05-16-ci-pipeline-remediation`
**Driver:** orchestrator pattern
**Phase 0:** ✅ baseline complete (failures pulled from GitHub Actions API by ORCHESTRATOR before dispatch)

---

## Locked decisions

| Decision | Value | Source |
|---|---|---|
| Trivy CVE-gate handling | Allow-list known CVEs in `.trivyignore` with documented IDs + expiry dates | Owner answer 2026-05-16 |
| pnpm lockfile fix | Regenerate `admin-ui/pnpm-lock.yaml`; keep `--frozen-lockfile` in Docker | Owner answer 2026-05-16 |
| Session scope | Workflows + pnpm-lock.yaml regen in one session | Owner answer 2026-05-16 |
| Co-Authored-By trailers | NONE on any commit | `~/.claude/CLAUDE.md` |

---

## Universal hard rules

- No `Co-Authored-By` trailer on any commit
- No `--no-verify`
- No `docker compose down -v`
- No edits to accepted ADRs
- No product code changes
- Atomic commits — one chunk per commit
- Validate via tools: paste command output into commit body or `04-progress.md`
- Update `02-matrix.md` row before committing

---

## Wave 1 — parallel (disjoint file ownership)

### CI-A — Pin `ossf/scorecard-action` to a valid version

**Target file:** `.github/workflows/scorecard.yml`
**Owner:** IMPLEMENTER-A (Sonnet)
**Root cause:** `ossf/scorecard-action@v2` does not exist; only specific semver tags or SHAs.
**Fix:** Pin to `ossf/scorecard-action@v2.4.0` (or the latest stable `v2.4.x` tag). Use the published SHA for that tag for OpenSSF Scorecard best practice (pinned-deps).
**Verification:**
- `actionlint .github/workflows/scorecard.yml` returns 0.
- `grep "ossf/scorecard-action" .github/workflows/scorecard.yml` shows the pinned version.
- Post-push: scorecard.yml run reaches the `Run scorecard` step (no "unable to resolve" error in `Set up job` step).

### CI-B — Disable `setup-go` cache to avoid collision with golangci-lint-action

**Target file:** `.github/workflows/ci.yml`
**Owner:** IMPLEMENTER-B (Sonnet)
**Root cause:** `actions/setup-go` and `golangci/golangci-lint-action@v6` both extract the Go toolchain cache; the second extraction fails with `tar: Cannot open: File exists`.
**Fix:** Add `cache: false` to the `actions/setup-go@vN` step inside the `Lint Go` job (golangci-lint-action manages its own cache).
**Verification:**
- `actionlint .github/workflows/ci.yml` returns 0.
- `grep -A 3 "setup-go" .github/workflows/ci.yml` shows `cache: false` under the Lint Go job's setup-go step.
- Post-push: `Lint Go` job runs golangci-lint to completion (passes OR fails on actual lint findings, but no toolchain "File exists" error).

### CI-C1 — Fix container-scan build context to see sibling `mintkey-models/`

**Target file:** `.github/workflows/container-scan.yml`
**Owner:** IMPLEMENTER-C1 (Sonnet)
**Root cause:** Workflow builds with `context: <service-dir>` but Dockerfiles `COPY mintkey-models/mintkey_models/ …` — they need repo-root context.
**Fix (preferred):** Change each affected service matrix entry's build step to:
```yaml
- name: Build image — ${{ matrix.service }}
  uses: docker/build-push-action@v6
  with:
    context: .
    file: ${{ matrix.dockerfile }}  # e.g. admin-api/Dockerfile
    tags: mintkey-${{ matrix.service }}:scan
    load: true
```
Update the matrix to carry `dockerfile:` paths. Only services that COPY from `mintkey-models/` need the change; admin-ui doesn't. If matrix is service-name only, extend it with a `dockerfile` key per entry.
**Verification:**
- Local: `cd /Users/alexandruiacobescu/gooseProjects/mintkey && docker build -f admin-api/Dockerfile -t test-admin-api .` succeeds (or the equivalent for each affected service).
- `actionlint .github/workflows/container-scan.yml` returns 0.
- Post-push: `Build image — admin-api`, `Build image — mcp-server`, `Build image — vault-adapter`, `Build image — proxy-plugin` jobs reach `Trivy scan` step (CI-D handles whether Trivy itself passes).

### CI-C2 — Regenerate admin-ui pnpm-lock.yaml after overrides drift

**Target files:** `admin-ui/pnpm-lock.yaml` (regenerate), possibly `admin-ui/package.json` (only if `overrides` block needs cleanup, not value change).
**Owner:** IMPLEMENTER-C2 (Sonnet)
**Root cause:** `package.json` `overrides` (or `pnpm.overrides`) drifted from `pnpm-lock.yaml`; `--frozen-lockfile` rejects.
**Fix:**
1. `cd admin-ui && pnpm install --no-frozen-lockfile` to regenerate `pnpm-lock.yaml`.
2. Verify: `pnpm install --frozen-lockfile` now succeeds.
3. Commit ONLY the lockfile change (do NOT bump dep versions in `package.json`; if `pnpm install` wants to bump versions, stop and escalate to `03-escalations.md` — owner must approve).
**Verification:**
- `cd admin-ui && pnpm install --frozen-lockfile` → exit 0.
- `git diff admin-ui/package.json` — empty OR `overrides`-block-only changes (no dep version bumps).
- Local Docker build: `docker build -f admin-ui/Dockerfile -t test-admin-ui admin-ui/` succeeds (admin-ui Dockerfile context is already correct — admin-ui doesn't COPY siblings).

### CI-D — Trivy CVE allow-list

**Target file:** `.trivyignore` (NEW at repo root) — possibly per-service `.trivyignore` if Trivy CLI looks per-context.
**Owner:** IMPLEMENTER-D (Sonnet)
**Root cause:** HIGH/CRITICAL CVEs in Debian 13 base image (`python:3.12-slim`) and jaeger base trip `exit-code: 1` Trivy gate.
**Fix:**
1. Fetch the exact CVE IDs from the failing Trivy run logs (jobs `76329132592` seed-job, `76329132597` jaeger-auth) — implementer must enumerate them, not blanket-ignore.
2. Create `.trivyignore` (or `.trivyignore.yaml` if container-scan workflow expects schema format) listing each CVE ID with a comment of: (a) package, (b) brief justification (e.g., "Debian 13 unfixable, not in our codepath"), (c) expiry date `2026-08-16` (3 months).
3. Workflow tweak (if needed): ensure `trivyignores:` parameter on `aquasecurity/trivy-action` points to the new file (it usually auto-detects `.trivyignore` at repo root).
**Verification:**
- Local: `trivy image --severity HIGH,CRITICAL --ignorefile .trivyignore mintkey-seed-job:scan` exits 0.
- Post-push: `Trivy scan — seed-job` and `Trivy scan — jaeger-auth` jobs exit 0; SARIF still uploaded (Security tab still receives findings as warnings).
- File documented: `.trivyignore` header explains the allow-list policy + expiry.

**Note for IMPLEMENTER-D:** If the Trivy logs from those job IDs are not easily retrievable from the host (no GitHub access from local Bash), IMPLEMENTER-D may use `trivy image --severity HIGH,CRITICAL --format json mintkey-seed-job:scan` locally to enumerate CVEs (build the image first via CI-C1's Dockerfile context fix). If that path is blocked, escalate to `03-escalations.md`.

---

## Wave 2 — REVIEWER (Opus, fresh)

| # | Chunk | Acceptance |
|---|---|---|
| REV-1 | Verify CI-A | Reviewer pulls scorecard.yml, confirms version pin matches `vX.Y.Z` semver tag |
| REV-2 | Verify CI-B | Reviewer pulls ci.yml, confirms `cache: false` under correct setup-go invocation |
| REV-3 | Verify CI-C1 | Reviewer pulls container-scan.yml; runs `actionlint`; if local Docker available, runs `docker build -f admin-api/Dockerfile -t test .` from repo root |
| REV-4 | Verify CI-C2 | Reviewer runs `cd admin-ui && pnpm install --frozen-lockfile`; checks `git diff admin-ui/package.json` |
| REV-5 | Verify CI-D | Reviewer reads `.trivyignore`; confirms each CVE has package + justification + expiry; confirms expiry ≥ 60 days out |

PASS_ALL gate: only after all 5 sub-reviews pass does ORCHESTRATOR push branch + open PR.

---

## Status legend

| Symbol | Meaning |
|---|---|
| ⬜ | Pending |
| 🔵 | Dispatched (in-flight) |
| ✅ | Reviewer PASS |
| ❌ | Reviewer FAIL — new implementer dispatched |
| 🛑 | Hard-stop — 3 failures; awaiting user |
| ⚠️ | Escalated — awaiting owner decision |
