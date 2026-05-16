# Python Test Infra — Session Plan

**Session:** `2026-05-16-python-test-infra`
**Driver:** `remediation-orchestrator` (super-orchestrator)
**Status:** CLOSED-WITH-RESIDUALS

---

## Mission

Fix CI Python test infra gaps. The primary blocker is `testcontainers` missing from `admin-api/pyproject.toml` dev deps, which prevents 4 acceptance test modules from even being collected. A successful session adds the missing dep, regenerates uv.lock, and verifies all 41 acceptance tests pass.

---

## Hard rules (every chunk inherits)

- No `Co-Authored-By` trailer on any commit
- No `--no-verify`
- No `docker compose down -v`
- No edits to accepted ADRs
- No product-code changes outside the scope defined in `ISSUE_INTAKE.md`
- Validate via tools: every "done" claim carries command output
- Surgical changes; one logical change per commit

---

## Phase 1 — Add testcontainers to admin-api dev deps

**Chunk C-1:** Add `testcontainers[postgres]>=4.7` to `admin-api/pyproject.toml` `[dependency-groups].dev`. Regenerate `admin-api/uv.lock` via `rm uv.lock && uv sync`.

---

## Deferred (escalated)

- `admin-api` ruff: 53 pre-existing lint errors — needs dedicated lint session
- `admin-api` mypy: 126 pre-existing type errors — needs dedicated type session
- `mintkey-models` Python 3.9 env issue: system anaconda runs with wrong Python version; pyproject.toml correctly specifies `>=3.11` — needs env fix in CI, not code
- `mcp-server` ruff: 3 pre-existing lint errors — low priority, dedicated lint session

---

## Closing

Verified via acceptance test command — all 41 pass.
