# CI Pipeline Remediation — Session Plan

**Session:** `2026-05-16-ci-pipeline-remediation`
**Branch:** `fix/ci-pipeline-remediation`
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)
**Status:** Step 1 — implementation dispatch

## Mission

Restore `github.com/WeLikeCode/mintkey` CI from chronic red to green. Four distinct workflow defects identified from job logs; intake gate complete (see `ISSUE_INTAKE.md`); owner has locked all decisions. Unblocks 32 approved Dependabot PRs.

## Approach

Workflow-only + one generated-file regen (pnpm-lock.yaml) + one new file (`.trivyignore`). No product code changes. 5 chunks dispatched as IMPLEMENTER subagents (parallel where files don't overlap); single REVIEWER pass verifies all; PR opened from `fix/ci-pipeline-remediation`; CI on PR is the integration test.

## Hard rules (every chunk)

- No `Co-Authored-By` trailer (per `~/.claude/CLAUDE.md`).
- No `--no-verify`.
- No `docker compose down -v`.
- No edits to accepted ADRs.
- No product code changes.
- No force-push.
- Atomic commits — one chunk per commit.
- Validate via tools (each chunk has a verification command — implementer pastes output into the commit body or progress file).
- Reviewer is FRESH (separate subagent, not the implementer of any chunk).

## Chunks — overview (full spec in `01-orchestrator-chunks.md`)

| # | Bug | Target file(s) | Owner |
|---|---|---|---|
| CI-A | scorecard.yml action version | `.github/workflows/scorecard.yml` | IMPLEMENTER-A |
| CI-B | ci.yml setup-go cache collision | `.github/workflows/ci.yml` | IMPLEMENTER-B |
| CI-C1 | container-scan.yml build context | `.github/workflows/container-scan.yml` | IMPLEMENTER-C1 |
| CI-C2 | admin-ui pnpm lockfile drift | `admin-ui/pnpm-lock.yaml`, possibly `admin-ui/package.json` | IMPLEMENTER-C2 |
| CI-D | Trivy CVE allow-list | `.trivyignore` (NEW) + workflow tweak if needed | IMPLEMENTER-D |

## Out-of-session

- Merging Dependabot PRs after CI is green (owner-driven).
- Adding matrix job names to `required_status_checks` (originally deferred from branch protection session).
- Upgrading base images to eliminate the CVEs allow-listed in this session — separate dedicated session.

## Closing acceptance criteria

- All 5 chunks committed atomically on `fix/ci-pipeline-remediation`.
- Final REVIEWER returns PASS_ALL with reproducible evidence per chunk.
- `99-report.md` written.
- Owner-decision: push branch + open PR.
- CI on the resulting PR: all 6 workflows green.
