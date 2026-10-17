# Bump admin-api mypy dev dependency 1.13 → 2.1.0

## Purpose

Dependabot PR #210 raises the `mypy` dev-dependency floor for the Admin REST API
(`apps/admin-api`) from `>=1.13` to `>=2.1.0`. CI runs `uv run mypy --strict src/admin_api/`
as a required gate (`.github/workflows/ci.yml`, job `lint-python`, step `Lint admin-api`).
This document records the migration verification and the one consistency fix needed.

## Scope

- In scope: `apps/admin-api/pyproject.toml` (the pin) and `apps/admin-api/uv.lock`
  (manifest specifier regeneration).
- Out of scope: `packages/python/mintkey-models/` and `apps/mcp-server/` — they carry
  independent `pyproject.toml`/`uv.lock` files with their own mypy pins and are not
  affected by this PR. Their CI mypy jobs resolve from their own unchanged lockfiles.

## Breaking-change analysis (mypy 1.x → 2.x family)

The major mypy 2.x line tightens several strict-mode behaviors (stricter
TypeVarTuple/ParamSpec handling, `--strict` implications, stricter overload resolution,
tighter Callable/Protocol edge cases). The investigation checked whether any of these
trip the admin-api codebase:

- Ran `uv sync` to install mypy `2.1.0` (compiled: yes) on Python 3.12.
- Ran the exact CI command `uv run mypy --strict src/admin_api/`.
- Result: **`Success: no issues found in 55 source files`** (exit 0).
- Ran `uv run ruff check src/` → `All checks passed!`.

No "error: …" lines were produced. The codebase already conforms to mypy 2.1.0 strict.
The only `# type: ignore` directives (4, all in `services/vault_client.py` covering the
auto-generated `vault_pb2` / `vault_pb2_grpc` stubs, which are excluded by
`[tool.mypy].exclude`) remain valid and are not reported as unused.

## What changed and why

1. `apps/admin-api/pyproject.toml`: `mypy>=1.13` → `mypy>=2.1.0` (Dependabot's change).
   Reason: keep the type-checker current; the new floor is the latest release on PyPI.
2. `apps/admin-api/uv.lock`: regenerate via `uv lock` so the `[manifest]` block records
   `specifier = ">=2.1.0"`. Dependabot bumped only `pyproject.toml`; the committed lock's
   manifest still reads `>=1.13`. The resolved mypy entry is already `version = "2.1.0"`
   (2.1.0 satisfies both constraints), so this is a consistency cleanup, not a functional
   fix — `uv sync` re-resolves on CI regardless.

No application/source code changes. This is a pure dev-tooling bump.

## Testing / verification

Run from `apps/admin-api`:

    uv lock                                 # regenerate manifest to >=2.1.0
    uv sync
    uv run ruff check src/                  # All checks passed!
    uv run mypy --strict src/admin_api/     # Success: no issues found in 55 source files

All verified during research with mypy 2.1.0 on CPython 3.12.

## Risk

Low. Dev-dependency only; no runtime/import impact (mypy is never imported by the app —
confirmed only `# type: ignore` comments reference it). Type checker passes clean. The
worst realistic failure (a new strict diagnostic) did not materialize.
