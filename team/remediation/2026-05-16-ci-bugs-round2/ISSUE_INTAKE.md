# Issue Intake — 2026-05-16-ci-bugs-round2

**Session:** `team/remediation/2026-05-16-ci-bugs-round2/`
**Reported:** 2026-05-16
**Reporter:** Owner — "open a session to fix the Python CI bugs and any other CI bugs. Make it work and in good condition. Use the orchestrator pattern."
**Triaged via:** Mintkey-brokered GitHub Actions API on main HEAD (2efa5e9)

---

## Problem statement (required)

After merging PR #33 (CI infra) and PR #34 (Dependabot vulns), CI on main HEAD has 5 failing check-runs revealing pre-existing structural defects we never addressed:

1. **Lint Go** — golangci-lint-action@v6 ships a linter binary built with Go 1.24; can't typecheck source targeting `go 1.25.0` (which our go.mod now declares due to OTel v1.43.0 transitive requirement).
2. **Lint Python / Architecture Tests / Python Unit Tests / Schema Integrity Gates** (4 jobs, same root cause) — workflows run `uv sync` in `admin-api/` and `mcp-server/`, but those directories have `requirements.txt`, not `pyproject.toml`. The repo is split-tooled: mock-backend + mintkey-models use uv (pyproject.toml); admin-api + mcp-server use pip (requirements.txt). CI assumes uv everywhere.
3. **OpenSSF Scorecard** — workflow runs successfully (SHA-pin from PR #33 worked) but publish to scorecard.dev rejects: top-level `security-events: write` permissions not allowed when publishing. Score currently 4.5 due to other warnings (unpinned actions, unpinned Dockerfile bases, unpinned pip commands, no fuzzing, etc.).

## User-visible symptom (required)

- `Actions` tab on `WeLikeCode/mintkey` shows red across last main push.
- Branch protection requires `dependency-review` to pass; that workflow itself does pass but the auxiliary failures block the GitHub status indicators users see.
- Future contributors opening PRs will see chronically-red CI on their branches.
- OpenSSF Scorecard badge would show 4.5/10 if displayed.

## Expected behavior (required)

- All ci.yml jobs green on main HEAD and on new PRs.
- OpenSSF Scorecard publishes successfully; score improved (target ~6-7 from current 4.5 — score 10 requires items out of scope this session like CII badge, fuzzing, etc.).
- All Python services use a single tooling convention (uv + pyproject.toml).
- All GitHub Actions SHA-pinned (eliminates pinned-dependencies warnings).
- All Dockerfile FROM directives SHA-pinned with semver tag comment.
- Workflow permissions hoisted from top-level to job-level (least privilege).

## Evidence (required)

Pulled from GitHub Actions API on 2026-05-16 against main HEAD `2efa5e9d835e`:

### Lint Go failure (job 76333939745)
```
Error: can't load config: the Go language version (go1.24) used to build golangci-lint
is lower than the targeted Go version (1.25.0)
```
golangci-lint-action@v6 → golangci-lint v1.x built with Go 1.24. Bump to @v7 or @v8 (golangci-lint v2.x built with Go 1.25+).

### Python jobs (4 jobs, ids 76333939752, 76333939750, 76333939748, 76333939742)
```
error: No `pyproject.toml` found in current directory or any parent directory
##[error]Process completed with exit code 2.
```
admin-api/ has: Dockerfile, db/, requirements.txt (14 deps), src/. NO pyproject.toml.
mcp-server/ has: Dockerfile, nginx.conf, requirements.txt (10 deps), skills/, src/, tests/. NO pyproject.toml.
mock-backend/ has: pyproject.toml ✓
mintkey-models/ has: pyproject.toml ✓

### Scorecard publish failure (job 76333939771)
```
2026/05/16 16:57:42 error sending scorecard results to webapp: http response 400,
status: 400 Bad Request, error: {"code":400,"message":"workflow verification failed:
workflow verification failed: global perm is set to write: permission for
security-events is set to write, see
https://github.com/ossf/scorecard-action#workflow-restrictions for details."}
```
Scorecard score = 4.5 (Dependency-Update-Tool 10, Security-Policy 10, Dangerous-Workflow 10, Binary-Artifacts 10, SAST 10, License 9, CI-Tests 5, plus several 0s).
Failing checks worth fixing in this session:
- Token-Permissions (0): 5 workflows have top-level `security-events: write`
- Pinned-Dependencies (0): 0/30 GitHub Actions SHA-pinned; 0/15 Dockerfile FROM directives SHA-pinned; 0/8 pipCommand pinned

## Scope (required)

May be changed:
- `.github/workflows/ci.yml` (golangci-lint-action bump + perms hoist + action SHA pins)
- `.github/workflows/scorecard.yml` (perms hoist + action SHA pins)
- `.github/workflows/codeql.yml` (perms hoist + action SHA pins)
- `.github/workflows/container-scan.yml` (perms hoist + action SHA pins)
- `.github/workflows/dependency-review.yml` (perms hoist + action SHA pins)
- `.github/workflows/playwright.yml` (perms hoist + action SHA pins)
- `admin-api/pyproject.toml` (NEW; converts requirements.txt)
- `admin-api/requirements.txt` (DELETE after conversion)
- `admin-api/Dockerfile` (switch pip → uv)
- `mcp-server/pyproject.toml` (NEW)
- `mcp-server/requirements.txt` (DELETE)
- `mcp-server/Dockerfile` (switch pip → uv)
- All Dockerfiles for SHA-pin of FROM: admin-api, mcp-server, admin-ui, jaeger-auth, mock-backend, seed-job, services/broker (2 stages), services/kong-syncer (2 stages), services/proxy-plugin (2 stages), services/vault-adapter (2 stages)
- Session folder

## Out of scope (required)

MUST NOT be touched:
- Python source code (admin-api/src, mcp-server/src) — pyproject.toml mirrors existing dep set; no API/import changes.
- mintkey-models / mock-backend Python source or pyproject.toml (already correct).
- seed-job + mock-backend pip→uv conversion (their CI doesn't fail; tangential surgery; deferred).
- tools/deps.sh — ops script, not CI; scorecard warning preserved.
- Scorecard improvements requiring external action: CII Best Practices badge, fuzzing setup, signed releases, contributors-from-multiple-orgs (these score 0 but unfixable in a code session).
- Branch-Protection scorecard check (-1) — internal token-permissions error; needs fine-grained token; out-of-scope.
- Maintained / Code-Review scorecard checks (0) — time-based, unfixable.
- Product code (admin-api/src, mcp-server/src, services/*/internal).
- Accepted ADRs.

## Risk level (required)

- **CI** (primary): blocks visible green status; affects every PR.
- **Build reproducibility / supply-chain security**: secondary — SHA-pinning actions + Dockerfiles closes a real attack vector.
- **Runtime regression**: low — pyproject.toml conversion preserves exact dep set (Dockerfile install changes from pip to uv but installs the same versions; uv ≥ pip in correctness).

## Verification target (required)

Per chunk:

### CB-WORKFLOWS (chunk 1)
- `actionlint .github/workflows/*.yml` returns 0 OR documented unavailable; YAML parses for each.
- Each top-level `permissions:` block in the 6 workflow files limited to `contents: read` (or removed). All write perms (security-events, id-token, packages, etc.) appear only at job level.
- Every `uses: <action>@<version>` line is replaced with `uses: <action>@<40-hex-sha> # <semver>`.
- `golangci/golangci-lint-action@v6` bumped to `@v8.x` (latest stable v8) — fixes Lint Go.

### CB-PY-ADMIN-API (chunk 2)
- `admin-api/pyproject.toml` created; `[project.dependencies]` matches the 14 entries from current requirements.txt (versions preserved).
- `admin-api/requirements.txt` deleted.
- `admin-api/Dockerfile` switched from `FROM python:3.12-slim` + `pip install -r requirements.txt` to a uv-based install (e.g., `FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim` + `uv sync --frozen`).
- Local verification: `cd admin-api && uv sync` exits 0 (creates .venv).
- Local Docker build from repo root: `docker build -f admin-api/Dockerfile -t test-admin-api .` succeeds.
- Image runs (HEALTHCHECK passes).

### CB-PY-MCP-SERVER (chunk 3) — same as CB-PY-ADMIN-API for mcp-server

### CB-DOCKERFILE-PIN (chunk 4 — runs after chunks 2+3)
- Every `FROM <image>:<tag>` in every Dockerfile becomes `FROM <image>:<tag>@sha256:<digest>` with `# <comment>` if needed.
- Affected: admin-api/Dockerfile (post-conversion), mcp-server/Dockerfile (post-conversion), admin-ui/Dockerfile, jaeger-auth/Dockerfile (2 FROMs), mock-backend/Dockerfile, seed-job/Dockerfile, services/{broker,kong-syncer,proxy-plugin,vault-adapter}/Dockerfile (each 2 FROMs).
- Each Dockerfile `docker build` succeeds (or at least `docker pull` of the pinned image works).
- Optional: Add a comment-line above each FROM noting the date of pinning + how to refresh.

### Final integration
- Push branch, open PR, watch CI on the PR; expected green on all jobs from the failure list (5 failures should clear). Scorecard score expected to rise to ~6-7.

## Owner decisions

- ✅ **Python conversion**: full — replace requirements.txt with pyproject.toml + Dockerfile uses uv.
- ✅ **Scorecard scope**: full cleanup — hoist perms + SHA-pin all actions + SHA-pin all Dockerfile FROMs + pin pip commands (where applicable in the Python conversions; seed-job/mock-backend left for separate session).

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete check-run / job IDs)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target (per chunk)
- [x] Owner decisions noted
