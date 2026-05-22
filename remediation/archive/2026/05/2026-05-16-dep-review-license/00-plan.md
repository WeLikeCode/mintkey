# Dependency Review License — Session Plan

**Session:** `2026-05-16-dep-review-license`
**Driver:** `remediation-orchestrator` (super-orchestrator)
**Status:** CLOSED

---

## Mission

Add `PSF-2.0` (Python Software Foundation License 2.0) to the `allow-licenses` list in `.github/workflows/dependency-review.yml`. This license was missing and caused the dependency-review CI job to reject `pywin32@311` (a Windows-only transitive dep of `testcontainers`).

---

## Hard rules (every chunk inherits)

- No `Co-Authored-By` trailer on any commit
- No `--no-verify`
- No `docker compose down -v`
- No edits to accepted ADRs
- No product-code changes outside the scope defined in `ISSUE_INTAKE.md`
- Validate via tools: every "done" claim carries command output
- Surgical changes; one logical change per commit
- NEVER add GPL-3.0, AGPL-3.0, or other strong-copyleft licenses

---

## Phase 1 — Single chunk: expand allow-licenses

**Chunk C-1:** Edit `.github/workflows/dependency-review.yml` to add `PSF-2.0` to `allow-licenses`. Validate YAML.

---

## Closing

Verified via `python3 -c "import yaml; yaml.safe_load(...)"` — YAML valid.
Full CI validation happens when the PR runs the workflow.
