# CI Bugs Round 2 — Session Plan

**Session:** `2026-05-16-ci-bugs-round2`
**Branch:** `fix/ci-bugs-round2-2026-05-16` (from main @ `2efa5e9`)
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)

## Mission

Make CI green on main HEAD; bring repo to "good condition" per OpenSSF Scorecard's actionable checks (Token-Permissions + Pinned-Dependencies). 5 CI failures plus broad Scorecard cleanup, in 4 chunks (3 Wave-1 parallel + 1 Wave-2 sequential), then fresh REVIEWER.

## Approach

Owner-locked decisions (in `ISSUE_INTAKE.md`):
- Full Python conversion: pyproject.toml replaces requirements.txt; Dockerfiles use uv.
- Full Scorecard cleanup: perms hoist + SHA-pin actions + SHA-pin Dockerfile FROMs.

## Chunks

| # | Wave | Chunk | Owner files |
|---|---|---|---|
| CB-WORKFLOWS | 1 | golangci-lint v6→v8 + perm hoist + SHA-pin actions | `.github/workflows/*.yml` (6 files) |
| CB-PY-ADMIN-API | 1 | requirements.txt → pyproject.toml; pip → uv | `admin-api/{pyproject.toml(new),requirements.txt(del),Dockerfile}` |
| CB-PY-MCP-SERVER | 1 | requirements.txt → pyproject.toml; pip → uv | `mcp-server/{pyproject.toml(new),requirements.txt(del),Dockerfile}` |
| CB-DOCKERFILE-PIN | 2 | SHA-pin FROM directives across all Dockerfiles | all Dockerfiles (after Wave 1) |

Wave 1: 3 implementer subagents in parallel (disjoint file ownership).
Wave 2: CB-DOCKERFILE-PIN after Wave 1's Dockerfile changes land (touches admin-api/mcp-server Dockerfiles).
Wave 3: REVIEWER (Opus, fresh) — re-runs all verifications.

## Hard rules (every chunk)

- No `Co-Authored-By` trailer.
- No `--no-verify`.
- No `docker compose down -v`.
- No edits to accepted ADRs.
- No Python source code changes (admin-api/src, mcp-server/src untouched).
- No production behavior changes — pyproject.toml mirrors existing dep set; Docker images install same packages via uv instead of pip.
- Atomic commits per chunk.
- Validate via tools: each chunk's implementer pastes its verification command output into the report.

## Closing acceptance criteria

- All 5 CI failures clear: Lint Go, Lint Python, Architecture Tests, Python Unit Tests, Schema Integrity Gates, OpenSSF Scorecard.
- Scorecard score improves (target ≥ 6 from current 4.5).
- All chunks PASS fresh REVIEWER.
- `99-report.md` written.
- PR opened; on next-run CI all jobs green (or pre-existing red unrelated to our chunks documented).
