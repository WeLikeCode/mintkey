# Dependabot Vulnerabilities Remediation — Session Plan

**Session:** `2026-05-16-dependabot-vulns-remediation`
**Branch:** `fix/dependabot-vulns-2026-05-16` (branched from main 2026-05-16)
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)
**Sister session:** `2026-05-16-ci-pipeline-remediation` (PR #33)

## Mission

Close all 8 open Dependabot alerts (3 H, 4 M, 1 L) on `WeLikeCode/mintkey`. 2 chunks — npm bumps in admin-ui (batched per owner decision) and Go OTel SDK bumps across services. No product code changes; bumps are surgical and verified locally before push.

## Hard rules

- No `Co-Authored-By` trailer (per `~/.claude/CLAUDE.md`).
- No `--no-verify`.
- No `docker compose down -v`.
- No edits to accepted ADRs.
- No product code changes.
- No force-push.
- Atomic commits — per owner decision: 1 commit for admin-ui batch; 1 commit per affected Go service for the OTel bump (since each service has its own go.mod).
- Validate via tools: paste command outputs into commit body or `04-progress.md`.
- Preserve existing `@tiptap/core@2.27.2` + `@tiptap/pm@2.27.2` overrides.

## Chunks

| # | Chunk | Owner files | Owner |
|---|---|---|---|
| DV-1 | npm bumps (admin-ui) — 6 alerts | `admin-ui/package.json`, `admin-ui/pnpm-lock.yaml` | IMPLEMENTER-DV-1 |
| DV-2 | Go OTel SDK bump to ≥ 1.43.0 across all Go services | `services/*/go.mod`, `services/*/go.sum`, possibly `go.work` | IMPLEMENTER-DV-2 |

## Cross-dependency on PR #33

PR #33 (`fix/ci-pipeline-remediation`) fixes the CI infrastructure (scorecard pin, setup-go cache, container-scan build context, Trivy allow-list). CI on this vuln-fix PR will be partially red until #33 merges and this PR rebases on the new main. Documented in the PR body; not a blocker for owner review of the bumps themselves.

## Closing acceptance criteria

- All 2 chunks pass fresh REVIEWER.
- All 8 Dependabot alerts close to `fixed` state after merge (or auto-close on next Dependabot scan).
- `99-report.md` written.
- Owner pushes/approves PR; merge happens in owner-chosen order with PR #33.
