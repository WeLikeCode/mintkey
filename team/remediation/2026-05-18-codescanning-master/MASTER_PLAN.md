# Code-Scanning Remediation — Master Plan

**Created:** 2026-05-18
**Source:** `gh api /repos/WeLikeCode/mintkey/code-scanning/alerts?state=open&per_page=100` × 9 pages (via Mintkey proxy 2026-05-18)
**Author:** ORCHESTRATOR (Opus)
**Status:** PROPOSED — awaiting dispatch of Wave 0

## Snapshot at plan creation (2026-05-18)

| Metric | Count |
|---|---|
| Total open alerts | **893** |
| Critical | 16 |
| High | 63 |
| Medium | 414 |
| Low | 379 |
| Note | 21 |
| By tool: Trivy / CodeQL / Scorecard | 852 / 28 / 13 |

Most Trivy alerts are duplicates of the same underlying Debian-base CVE across 5 container images — collapses to a small number of root causes.

## Owner-locked decisions

1. **Base-image strategy (S2):** Bump tag to latest patched (stay on `python:3.12-slim-bookworm` / `node:22-bookworm-slim` family) and re-pin `@sha256:…` across every Dockerfile. No distroless/alpine migration in this campaign.
2. **PR cadence:** One PR per session (11 PRs total). Matches the established pattern (PRs #43–#55).
3. **CodeReviewID (S11):** Document as accepted residual via `SECURITY.md` / `.scorecard.yml` — solo-author project pre-v1; admin-merge stays allowed. Do NOT enforce 1-reviewer + no-bypass branch protection in this campaign.
4. **Test-file CodeQL findings:** Fix in code (not suppress). Poor tests for bad URL handling are still wrong.

Universal hard rules (carry over from `~/.claude/CLAUDE.md` and prior sessions):
- No `Co-Authored-By` trailer.
- No `--no-verify`.
- No edits to accepted ADRs (0001–0020 immutable per ADR-0001).
- Each session = one branch = one PR = atomic per-chunk commits.
- Validate via tools; reviewer re-runs DoD commands.
- 3-strike implementer cap → ORCHESTRATOR escalates.
- Proxy-egress for GitHub state changes (per `feedback_use_mintkey_proxy_for_github` memory).

## Sessions

11 sessions; one session = one PR. Each follows the standard layout:
`ISSUE_INTAKE.md`, `00-plan.md`, `01-orchestrator-chunks.md`, `02-matrix.md`, `03-escalations.md`, `04-progress.md`, `99-report.md`.

### Wave 0 — top-priority (independent; can run in parallel)

#### S1 — `2026-05-18-codeql-ssrf-admin-api-services`
- **Cluster:** 1 critical CodeQL alert.
- **Rule:** `py/full-ssrf`.
- **Location:** `admin-api/src/admin_api/api/services.py:537`.
- **Likely fix:** wrap upstream URL with `urllib.parse` + enforce a per-service allowlist before `httpx.AsyncClient.send`. Add unit test covering the SSRF payload that triggered the alert.
- **Chunks (proposed):** C-1 scaffold, C-2 patch + test, C-3 reviewer.
- **Risk:** high positive on security; behavior regression risk requires careful test coverage.

#### S2 — `2026-05-18-trivy-base-image-bump`
- **Cluster:** ~750 Trivy alerts driven by shared Debian base images. Closes the bulk of the 893.
- **Locked decision:** bump tag + repin SHA (not distroless/alpine).
- **Files:** every `Dockerfile` in `services/`, `admin-api/`, `admin-ui/`, `mcp-server/`, `mock-backend/`, `seed-job/`, `jaeger-auth/` (~10). Plus `.github/workflows/*` if any pin base FROMs there.
- **Chunks:**
  - C-1 scaffold.
  - C-2 inventory all current FROM lines + look up latest patched tag for each (`docker pull` + `docker inspect` to get `@sha256:`); write to a `BASE_IMAGE_LOCK.md`.
  - C-3 implementer: apply new FROM lines across Dockerfiles.
  - C-4 implementer: `docker compose build` smoke test all services start.
  - C-5 reviewer (Opus, fresh): verify diff is FROM-only; runs `docker compose build` + `docker compose up -d --wait` + hits `/v1/health` on every service.
- **Risk:** high blast radius (every image rebuilt); behavior regression risk if a base image changed Python version etc. CI catches.
- **Gate:** must land before S9.

### Wave 1 — CodeQL clusters (parallel; disjoint owner files)

#### S3 — `2026-05-18-codeql-cleartext-logging-py`
- **Cluster:** 11 high `py/clear-text-logging-sensitive-data`.
- **Files (preview):** `mock-backend/src/mock_backend/rest/main.py:25,35,…`, `scripts/e2e_smoke.py:100,108,…`, plus 4–5 others (full list in S3's `ISSUE_INTAKE.md`).
- **Fix pattern:** redact tokens/secrets in log statements — substitute `secret_value` with `secret_value[:4]+'…'` or use a `redact()` helper. Add `log.RedactionFilter` if pattern is widespread.
- **Chunks:** C-1 scaffold, C-2 redact helper + apply, C-3 reviewer.

#### S4 — `2026-05-18-codeql-cleartext-logging-go`
- **Cluster:** 4 high `go/clear-text-logging`.
- **Location:** `services/proxy-plugin/cmd/proxy-plugin/main.go:273,310,…`.
- **Fix pattern:** same — redact sensitive log fields; likely auth headers / tokens leaking into structured logs.
- **Chunks:** C-1 scaffold, C-2 redact + apply, C-3 reviewer.

#### S5 — `2026-05-18-codeql-weak-hashing`
- **Cluster:** 3 high `py/weak-sensitive-data-hashing` (SHA-1/MD5 used on sensitive data).
- **Files:** `admin-api/src/admin_api/api/internal.py:119`, `admin-api/src/admin_api/api/proxy.py:64`, `mintkey-models/mintkey_models/audit.py:85`.
- **Fix pattern:** swap to SHA-256 / BLAKE2 / Argon2 depending on use. Audit hashes used for indexing/dedupe vs. authentication — different replacements per use.
- **Risk:** if these hashes are stored in DB and read back, this is a migration not a swap. Implementer's first chunk = classify each use before patching.
- **Chunks:** C-1 scaffold + classify, C-2 patch, C-3 reviewer.

#### S6 — `2026-05-18-codeql-cleartext-storage-seed-job`
- **Cluster:** 2 high `py/clear-text-storage-sensitive-data`.
- **Location:** `seed-job/main.py:352,354`.
- **Fix pattern:** likely writing bootstrap admin password to disk in cleartext. Options: filesystem perms 0o600 + immediate read+delete; or write via Docker secrets; or use the existing vault-adapter to store and one-shot read. Investigate.
- **Chunks:** C-1 scaffold, C-2 patch, C-3 reviewer.

#### S7 — `2026-05-18-codeql-url-sanitization`
- **Cluster:** 3 alerts — 2 high `js/incomplete-url-substring-sanitization` (admin-ui e2e) + 1 high `py/incomplete-url-substring-sanitization` (mcp-server tests).
- **Files:** `admin-ui/e2e/tests/99-runbook-ui-verify.spec.ts:499`, `admin-ui/e2e/verify-targeted.mjs:259`, `mcp-server/tests/test_landing.py:172`.
- **Fix pattern:** replace `url.includes("github.com")` with proper URL parse + `URL.hostname === 'github.com'` (or === `'api.github.com'` etc.). Per locked decision: fix in tests, do NOT suppress.
- **Chunks:** C-1 scaffold, C-2 patch, C-3 reviewer.

#### S8 — `2026-05-18-codeql-admin-ui-misc`
- **Cluster:** 4 alerts — 1 high `js/missing-rate-limiting`, 1 medium `js/clear-text-cookie`, 2 medium `py/stack-trace-exposure`.
- **Files:** `admin-ui/src/index.ts:181,203`, `admin-api/src/admin_api/api/agents.py:641`, `admin-api/src/admin_api/api/services.py:802`.
- **Fix patterns:**
  - rate-limiting → `express-rate-limit` or analogous middleware on the admin-ui server (or behind Kong if more appropriate).
  - cookie → set `Secure` + `HttpOnly` + `SameSite=Strict` (review against existing session cookie config).
  - stack-trace exposure → ensure `detail` field of error responses doesn't return full Python traceback; FastAPI exception-handler tightening.
- **Chunks:** C-1 scaffold, C-2 rate-limit + cookie, C-3 stack-trace, C-4 reviewer (separate implementer chunks because files are in different services).

### Wave 2 — cleanup (after Wave 0 + 1 land)

#### S9 — `2026-05-18-trivy-bundled-bins`
- **Cluster:** 45 oauth2-proxy CVEs + 37 grpc_health_probe CVEs + 38 esbuild CVEs.
- **Files:** `jaeger-auth/Dockerfile`, various Dockerfiles for grpc_health_probe download, `admin-ui/package.json` + `pnpm-lock.yaml`.
- **Fix:** bump each binary to latest patched release; SHA-pin downloads.
- **Gate:** depends on S2 landing first (so the binaries are layered on a current base).

#### S10 — `2026-05-18-scorecard-pin-actions-and-pip`
- **Cluster:** 9 `PinnedDependenciesID`.
- **Files:** `.github/workflows/*.yml` (pin GitHub-owned actions to `@sha256:` via dependabot-friendly format), `requirements*.txt` / `pyproject.toml` (add `--require-hashes` to pip commands invoked in CI).
- **Fix pattern:** mechanical pin + commit dependabot config to keep them current.
- **Chunks:** C-1 scaffold, C-2 actions pin, C-3 pip-require-hashes, C-4 reviewer.

#### S11 — `2026-05-18-scorecard-residuals-policy`
- **Cluster:** 1 high CodeReviewID + 1 high VulnerabilitiesID (GO-2026-* dep CVE not yet covered by Trivy) + 1 high MaintainedID (project age) + 1 medium FuzzingID + 1 low CIIBestPracticesID.
- **Fix per locked decision:** document as accepted residuals.
  - Add `SECURITY.md` section "Accepted Scorecard Residuals (v0.1.0-prealpha)" with rationale per item.
  - `.scorecard.yml` (or `.github/scorecard.yml`) — if Scorecard config supports per-check overrides, use it.
  - Track in `docs/architecture/00-vision/06-roadmap.md` as items to revisit at v1.0.
- **Chunks:** C-1 scaffold, C-2 docs, C-3 reviewer.

## Sequencing / dependency graph

```
Wave 0 (parallel):  S1 — SSRF
                    S2 — base image bump  ───┐
                                             │
Wave 1 (parallel):  S3 S4 S5 S6 S7 S8        │ (Wave 1 is independent of S2; can start in parallel)
                                             │
Wave 2:             S9 — bundled bins     ←──┘ (waits for S2)
                    S10 — pin actions/pip      (independent; can run with S9)
                    S11 — scorecard residuals  (independent)
```

Concretely:
- Day 1: dispatch S1 + S2 in parallel. Land both PRs.
- Day 2: dispatch S3, S4, S5, S6, S7, S8 in parallel (6 PRs across 6 disjoint file sets). Land as they pass.
- Day 3: dispatch S9, S10, S11 in parallel. Land.

Total: 11 PRs across ~3 working sessions if everything passes on first reviewer pass.

## Post-campaign verification

After all 11 PRs are merged, ORCHESTRATOR re-runs:

```bash
curl … /repos/WeLikeCode/mintkey/code-scanning/alerts?state=open  # expect << 893
```

Acceptance target: ≤ 30 open alerts remaining (the residuals: maintained <90d auto-resolves at day 90; CodeReview accepted; Fuzzing accepted; CII accepted; any CVEs without upstream fix yet documented in `99-report.md` of S2 or S9).

## How to dispatch a session from this plan

1. `cd /Users/alexandruiacobescu/gooseProjects/mintkey`
2. `git checkout main && git pull --ff-only`
3. `git checkout -b fix/<session-slug>-2026-05-18`
4. ORCHESTRATOR (Opus) scaffolds the 6 session files using the templates in any prior session (e.g., `team/remediation/2026-05-17-kong-syncer-startup-retry/`).
5. Commit scaffold.
6. Dispatch implementers per `01-orchestrator-chunks.md`.
7. Fresh reviewer.
8. Commit chunks, write 99-report, push branch.
9. Open PR via Mintkey proxy (`svc_01KRRQ9Q7V9KN4R2H9P505B9WW`).
10. Admin-merge via proxy after CI green.

## Open follow-ups not covered by this plan

- **VulnerabilitiesID** Scorecard alert references `GO-2026-4…` (truncated in the API response). Need to fetch the full Scorecard report to identify the Go dep. May fold into S2 or S9 once identified.
- **Trivy MEDIUM CVE backlog (414 alerts)** — most will be closed by S2 + S9. Re-survey after Wave 1 + Wave 2 to identify any not closed; consider one cleanup session if >50 remain.
- **CodeQL future regressions** — consider adding CodeQL to the required-status-checks on `main` so net-new findings block merge (separate session if desired).
