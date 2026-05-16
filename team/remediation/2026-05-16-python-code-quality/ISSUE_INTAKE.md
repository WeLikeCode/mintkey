# Issue Intake — 2026-05-16-python-code-quality

**Session:** `team/remediation/2026-05-16-python-code-quality/`
**Branch:** `fix/python-code-quality-2026-05-16` (from main)
**Reported:** 2026-05-16
**Reporter:** Owner — "open a session for the mypy and ruff errors. Use the same orchestrator pattern and parallelise work as much as possible."
**Source:** Lint Python CI job + Session 3 escalation in `team/remediation/2026-05-16-python-test-infra/03-escalations.md`

## Problem statement (required)

Python lint + type-check CI red:
- admin-api: 53 ruff errors (19 auto-fixable) + 126 mypy --strict errors across 29 files.
- mcp-server: 3 ruff errors.
- mintkey-models: Python env mismatch (out of scope — workflow config concern, separate session).

44 of 126 mypy errors are in `vault_pb2_grpc.py` (auto-generated gRPC stub — should not be subject to strict mypy). 26 are `[import-not-found]` (missing type stubs for third-party deps). The rest are real-code findings requiring per-file fixes.

## User-visible symptom (required)

- `Lint Python` job fails on main pushes and PRs (Architecture/Schema gates' Python tasks pass via separate CI jobs but Lint Python is structural).
- Branch protection requires `dependency-review` to pass; Lint Python's failure is visible to PR reviewers.
- Type-safety guarantees claimed by `--strict` aren't actually enforced when CI is red on infrastructure noise.

## Expected behavior (required)

- `cd admin-api && uv run ruff check src/` → exit 0.
- `cd admin-api && uv run mypy --strict src/admin_api/` → exit 0.
- `cd mcp-server && uv run ruff check src/` → exit 0.
- `Lint Python` CI job passes on next push.
- mypy excludes auto-generated gRPC stubs (`vault_pb2*.py`).
- Type stubs installed for third-party untyped deps.

## Evidence (required)

Run on 2026-05-16:

```
$ cd admin-api && uv run ruff check src/
Found 53 errors. [*] 19 fixable with the `--fix` option.

$ cd admin-api && uv run mypy --strict src/admin_api/
Found 126 errors in 29 files (checked 47 source files)
```

Error breakdown by code (mypy):
| Code | Count | Meaning |
|---|---|---|
| `[attr-defined]` | 33 | Attribute access on dynamically-typed object |
| `[import-not-found]` | 26 | Missing type stubs for third-party import |
| `[type-arg]` | 24 | Generic type missing type parameters |
| `[no-untyped-def]` | 20 | Function def missing annotations |
| `[import-untyped]` | 8 | Imported module is untyped |
| `[no-any-return]` | 7 | Returning Any from typed function |
| `[assignment]` | 3 | Type mismatch |
| `[no-untyped-call]` | 2 | Calling untyped function |
| `[union-attr]` | 1 | Attr access on potentially-None |
| `[return-value]` | 1 | Return type mismatch |

Top error-density files (mypy):
| File | Errors |
|---|---|
| `services/vault_pb2_grpc.py` | 44 |
| `services/vault_client.py` | 9 |
| `auth/signed_request.py` | 7 |
| `api/api_keys.py` | 7 |
| `middleware/csrf.py` | 5 |
| `api/internal.py` | 5 |
| `api/credentials.py` | 5 |
| `api/auth.py` | 5 |
| `cli.py`, `auth/oidc.py`, `api/tenants.py`, `api/services.py`, `api/service_templates.py`, `api/audit_admin.py`, `api/agents.py` | 3 each |
| 11 other files | 1-2 each |

mcp-server ruff errors:
- `src/mcp_server/tools/bootstrap.py:28`: F401 `os` imported but unused
- `src/mcp_server/tools/discovery.py:101`: F541 f-string without any placeholders
- (third one in full output not shown — implementer enumerates)

## Scope (required)

May be changed:
- `admin-api/pyproject.toml` ([tool.mypy] config + dev type-stub deps)
- `admin-api/uv.lock` (regenerated after dev-dep additions)
- `admin-api/src/admin_api/**/*.py` (real-code lint/type fixes, ~28 files)
- `mcp-server/pyproject.toml` (dev deps if needed — ruff already there)
- `mcp-server/src/mcp_server/**/*.py` (ruff fixes, 1-3 files)
- Session folder

## Out of scope (required)

- `admin-api/src/admin_api/services/vault_pb2.py` and `vault_pb2_grpc.py` — auto-generated; excluded via mypy config, not edited.
- `mintkey-models/**` — Python env mismatch is a workflow-config concern (out-of-scope per intake).
- Product behavior changes — annotations only; no logic changes.
- Tests (`tests/**`) — separate concern.
- CI workflows (`.github/workflows/`) — Lint Python job calls are already correct.
- Accepted ADRs.

## Risk level (required)

- **Behavior regression**: low — type annotations + lint cleanups + unused-import removals. No runtime code logic changes.
- **CI green**: positive — closes 2 remaining Python-side CI failures (Lint Python + indirectly Python Unit Tests if uv sync picks up new stubs).
- **Compatibility**: stub libraries (e.g., types-protobuf) are version-pinned to match runtime deps; risk of version drift if not synced.

## Verification target (required)

### Wave 1 — RUFF-AUTO
- `cd admin-api && uv run ruff check src/` → exit 0
- `cd mcp-server && uv run ruff check src/` → exit 0

### Wave 1 — MY-CONFIG
- `cd admin-api && uv run mypy --strict src/admin_api/` → reduced error count (target: 126 → ~50-60, after excluding generated + stubs installed)
- `vault_pb2*.py` files NOT in mypy output.
- Each `[import-not-found]` either resolved by a stub install OR documented as truly-untyped with `[[tool.mypy.overrides]] ignore_missing_imports = true` for that specific module.

### Wave 2 — per-file mypy fixes
- Each implementer's verification command shows their assigned file is clean.
- Final aggregate: `uv run mypy --strict src/admin_api/` → exit 0.

### Final integration
- All 3 commands above exit 0.
- All existing tests still pass: `uv run pytest tests/unit/admin_api/ tests/acceptance/`.
- No behavior regression.

## Owner decisions

- ✅ **Strategy**: exclude generated code + install type stubs + fix remaining errors per-file.
- ✅ **Parallelization**: per-file implementer subagents in parallel.
- Implementer choice on annotation style: prefer `from __future__ import annotations` + standard library typing (`list[str]` etc.); match existing style in each file.

---

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (file:line counts + error code breakdown)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted
