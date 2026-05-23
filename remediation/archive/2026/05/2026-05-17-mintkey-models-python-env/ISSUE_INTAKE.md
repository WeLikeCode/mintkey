# Issue Intake — 2026-05-17-mintkey-models-python-env

## Problem statement (required)

CI jobs `Lint Python` and `Python Unit Tests` both fail with `error: Failed to spawn: ruff` / `pytest` when running against `mintkey-models/`. Root cause: `mintkey-models/pyproject.toml` has no `[dependency-groups].dev` section, so pytest, ruff, and mypy are not installed when `uv sync` runs. `uv run` cannot find these binaries, causing all lint and test CI steps to fail with spawn errors.

## User-visible symptom (required)

CI output:
```
error: Failed to spawn: `ruff`
  Caused by: No such file or directory (os error 2)
error: Failed to spawn: `pytest`
  Caused by: No such file or directory (os error 2)
```
Jobs `Lint Python` and `Python Unit Tests` are red on every PR touching `mintkey-models/`.

## Expected behavior (required)

`uv sync` in `mintkey-models/` installs dev dependencies (pytest, ruff, mypy) automatically. `uv run ruff check`, `uv run mypy --strict`, and `uv run pytest tests/` all complete successfully and exit 0.

## Evidence (required)

- `mintkey-models/pyproject.toml` — no `[dependency-groups]` section; no `[tool.uv]` section.
- `.github/workflows/ci.yml` — Lint and Test steps call `uv sync` then `uv run ruff/mypy/pytest` with working-directory `mintkey-models/`.
- Same pattern fixed for admin-api in PR #35 and PR #39 (testcontainers).

## Scope (required)

- `mintkey-models/pyproject.toml` — add `[dependency-groups].dev`, `[tool.uv]`, `[tool.mypy]`.
- `mintkey-models/uv.lock` — regenerate.
- `mintkey-models/mintkey_models/*.py` — fix any ruff/mypy errors discovered.
- `mintkey-models/tests/*.py` — fix any test failures discovered.

## Out of scope (required)

- `admin-api/`, `mcp-server/`, `services/` (do not modify unless mintkey-models schema had a real bug requiring cascade fix, and only then with documented justification).
- Accepted ADRs.
- Any CI workflow file changes.
- Runtime behavior of schemas (no silent semantic changes without commit message justification).

## Risk level (required)

CI (lint/test jobs completely broken for mintkey-models).

## Verification target (required)

All three commands must exit 0 from `mintkey-models/`:
```
uv run ruff check mintkey_models/   && echo "RUFF OK"
uv run mypy --strict mintkey_models/ && echo "MYPY OK"
uv run pytest tests/                 && echo "PYTEST OK"
```
Plus admin-api regression: `cd admin-api && uv run pytest ../tests/unit/admin_api/ --tb=line` must show 138 passed.

## Owner decisions needed (if any)

None. Fix pattern is established (PR #35, #39); dev-dep versions align with admin-api policy.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line or command)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted (none)
