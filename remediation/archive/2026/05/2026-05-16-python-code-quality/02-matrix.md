# python-code-quality — Tracking Matrix

**Session:** `2026-05-16-python-code-quality`
**Status:** Wave 1 MY-CONFIG done; Wave 2 (per-file fixes) pending

---

## Severity legend

| Severity | Meaning |
|---|---|
| P0 | Blocking — session cannot close without this |
| P1 | High — must address before the closing report |
| P2 | Medium — fix this session if possible; escalate if not |
| P3 | Low — document as residual; defer acceptable |

## Status legend

| Symbol | Meaning |
|---|---|
| ⬜ | Not started |
| 🔵 | In progress |
| ✅ | Fixed and reviewer-verified |
| ⏭️ | Deferred to a future session (document in 99-report.md) |
| n/a | Not applicable |

---

## Matrix

| # | Area | Finding | Severity | Chunk | Status | Notes |
|---|---|---|---|---|---|---|
| M-1 | mypy config | vault_pb2*.py (auto-generated) counted in strict mypy | P0 | MY-CONFIG | ✅ | Excluded via `[tool.mypy] exclude`; 46 errors eliminated |
| M-2 | mypy config | Missing type stubs for grpc, protobuf, authlib | P1 | MY-CONFIG | ✅ | grpc-stubs, types-protobuf, types-authlib installed; 8 import-untyped eliminated |
| M-3 | mypy config | mintkey_models.* not typed (no py.typed, not in admin-api deps) | P1 | MY-CONFIG | ✅ | `ignore_missing_imports = true` override; 26 import-not-found eliminated |
| M-4 | mypy source | 52 remaining real-code errors across 19 files | P1 | Wave 2 | ⬜ | Per-file fixes; see top error files below |
| M-5 | ruff | admin-api: 53 ruff errors (19 auto-fixable) | P1 | RUFF-AUTO | ⬜ | Separate chunk |
| M-6 | ruff | mcp-server: 3 ruff errors | P2 | RUFF-AUTO | ⬜ | Separate chunk |

---

## MY-CONFIG results (Wave 1 config chunk)

### Stubs installed (3)

| Package | Version pinned | Resolves |
|---|---|---|
| `grpc-stubs` | `>=1.53` (resolved 1.53.0.6) | `[import-untyped]` for `grpc`, `grpc.aio`, `grpc._utilities` |
| `types-protobuf` | `>=6.31` (resolved 7.34.1.20260508) | `[import-untyped]` for `google.protobuf`, `google.protobuf.internal` |
| `types-authlib` | `>=1.3` (resolved 1.6.11.20260514) | `[import-untyped]` for `authlib.jose`, `authlib.jose.errors` |

### ignore_missing_imports overrides (1)

| Module | Reason |
|---|---|
| `mintkey_models.*` | Internal workspace package; no `py.typed` marker; not declared in admin-api deps; mypy cannot resolve it. Wave 2 can add py.typed to mintkey-models or declare it as a dep, but that is out of scope here. |

### Error count delta

- **Before:** 126 errors in 29 files
- **After:** 52 errors in 19 files (checked 45 source files)
- **Reduction:** -74 errors, -10 files
- vault_pb2*.py: not present in any error line (confirmed by grep)

---

## Top remaining error files (Wave 2 planning)

| File | Errors | Top error codes |
|---|---|---|
| `services/vault_client.py` | 8 | attr-defined (3), type-arg, call-arg, no-untyped-call |
| `auth/signed_request.py` | 7 | no-untyped-def, no-any-return, type-arg, no-untyped-call |
| `middleware/csrf.py` | 5 | type-arg (2), no-any-return (3) |
| `api/api_keys.py` | 5 | type-arg (4), no-untyped-def, no-any-return |
| `api/service_templates.py` | 3 | type-arg, no-untyped-def (2) |
| `api/internal.py` | 3 | type-arg (3) |
| `api/credentials.py` | 3 | type-arg (3) |
| `api/auth.py` | 3 | type-arg (2), arg-type |
| `auth/oidc.py` | 2 | type-arg, call-overload |
| `api/tenants.py` | 2 | type-arg, assignment |
| `api/health.py` | 2 | assignment (2) |
| `api/audit_admin.py` | 2 | type-arg (2) |
| `middleware/metrics.py` | 1 | no-untyped-def |
| `main.py` | 1 | no-untyped-def |
| `cli.py` | 1 | no-untyped-def |
| `changes/publisher.py` | 1 | type-arg |
| `auth/internal.py` | 1 | return-value |
| `api/services.py` | 1 | type-arg |
| `api/agents.py` | 1 | union-attr |

---

## Verification DoD checklist

- [x] vault_pb2*.py NOT in any mypy error line — verified: `grep "vault_pb2" <output>` is empty
- [x] `[tool.mypy]` section in pyproject.toml: `strict = true`, python_version = "3.12", excludes vault_pb2*.py
- [x] 3 stub packages in `[dependency-groups].dev`
- [x] `mintkey_models.*` override with `ignore_missing_imports = true`
- [x] uv.lock regenerated (4 packages installed: grpc-stubs 1.53.0.6, types-protobuf 7.34.1.20260508, types-authlib 1.6.11.20260514 + admin-api re-built)
- [x] Error count reduced: 126 → 52 (target was ~50-60)
- [ ] Wave 2: per-file source fixes to reach 0
- [ ] No `Co-Authored-By` trailer in any new commit
- [ ] No `--no-verify` used
