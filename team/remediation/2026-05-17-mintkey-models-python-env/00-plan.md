# mintkey-models Python Env — Session Plan

**Session:** `2026-05-17-mintkey-models-python-env`
**Driver:** IMPLEMENTER MM-ENV
**Branch:** `fix/mintkey-models-python-env-2026-05-17`
**Status:** In progress

---

## Mission

`mintkey-models/pyproject.toml` is missing its `[dependency-groups].dev` section, causing `uv sync` to not install pytest/ruff/mypy. CI jobs `Lint Python` and `Python Unit Tests` fail with spawn errors. This session adds dev deps, regenerates the lockfile, fixes any discovered lint/type/test issues, and opens a PR.

---

## Hard rules (every chunk inherits)

- No `Co-Authored-By` trailer on any commit
- No `--no-verify`
- No `docker compose down -v`
- No edits to accepted ADRs
- No product-code changes outside scope defined in `ISSUE_INTAKE.md`
- Validate via tools: every "done" claim carries command output
- Surgical changes; one logical change per commit

---

## Chunks

### Chunk 0 — Scaffold (this file + ISSUE_INTAKE.md)

Fill ISSUE_INTAKE.md (9 fields) and this plan.

### Chunk 1 — Add dev deps + regenerate lockfile

Edit `mintkey-models/pyproject.toml`:
- Add `[dependency-groups].dev` with pytest>=8.0, pytest-asyncio>=0.24, ruff>=0.9, mypy>=1.10
- Add `[tool.uv] default-groups = ["dev"]`
- Add `[tool.mypy] strict = true, python_version = "3.12"`

Then: `rm -f uv.lock && uv sync`

Commit: `fix(mintkey-models): add dev deps (pytest, pytest-asyncio, ruff, mypy)`

### Chunk 2 — Fix ruff errors (if any)

Run `uv run ruff check mintkey_models/`. Fix in-place or with `--fix`. If > 10, use `--fix` first.

Commit: `fix(mintkey-models): clear N ruff errors` (if needed)

### Chunk 3 — Fix mypy --strict errors (if any)

Run `uv run mypy --strict mintkey_models/`. Add annotations, cast(), or type-ignores with justifications.

Commit: `fix(types): clear N mypy --strict errors in mintkey-models` (if needed)

### Chunk 4 — Fix pytest failures (if any)

Run `uv run pytest tests/ -v --tb=short`. Fix test bugs or schema issues (with justification if schema changes).

Commit: `fix(mintkey-models): <describe>` (if needed)

### Chunk 5 — Final verification

All 3 commands exit 0. Admin-api regression check (138 passed).

### Chunk 6 — Write 99-report, commit docs, push, open PR

Commit: `docs(mintkey-models-env): close session`
Push. Open PR via Mintkey proxy.

---

## DoD

- [ ] `mintkey-models/pyproject.toml` has dev deps + `[tool.mypy]` + `[tool.uv]`
- [ ] `mintkey-models/uv.lock` regenerated
- [ ] `uv run ruff check mintkey_models/` exits 0
- [ ] `uv run mypy --strict mintkey_models/` exits 0
- [ ] `uv run pytest tests/` exits 0
- [ ] admin-api unit tests still pass (138 passed)
- [ ] PR opened; PR number returned
