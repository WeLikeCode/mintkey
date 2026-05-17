# S6 codeql-cleartext-storage-seed-job — Closing Report

**Session:** `2026-05-18-s6-codeql-cleartext-storage-seed-job`
**Branch:** `fix/s6-codeql-cleartext-storage-seed-job-2026-05-18` (from `main @ 5203e23`)
**Status:** **CLOSED**
**Closed:** 2026-05-18

**Commits (strike-1 + strike-2 + strike-3):**
- `a1c36d7` fix(seed-job): encrypt bootstrap admin password with Fernet (S6 CodeQL)
- `df3bc90` feat(mintkey-models): shared Fernet decrypt helper
- `def66fa` fix(readers): patch 14 readers
- `47822b0` fix(admin-ui, compose): JS decrypt + admin-ui KEK env
- `74bf31b` docs(security, ports, report): KEK docs + seed-job _fernet() cleanup
- `49cc84b` fix(compose): unify MINTKEY_BOOTSTRAP_KEK default across seed-job and admin-ui
- `6911bbd` fix(admin-ui): surface Fernet decrypt errors instead of silent catch
- `034eff2` docs(s6): 99-report status header + strike-3 supplement

---

**Date**: 2026-05-18
**Alerts closed**: 2 HIGH — `py/clear-text-storage-sensitive-data` at
`seed-job/main.py:352` and `seed-job/main.py:354`

## What was done

Implemented **Approach C** (Fernet encryption with `MINTKEY_BOOTSTRAP_KEK`).

### Changes

| File | Change |
|------|--------|
| `seed-job/requirements.txt` | Added `cryptography>=42.0` |
| `seed-job/main.py` | Added `_BOOTSTRAP_KEK_RAW`, `_fernet()`, updated `_ensure_admin_password_file` to write Fernet ciphertext, updated `_sync_admin_password` to decrypt before Keycloak call, fixed `_ensure_secret_file` to chmod 0o600 before overwriting read-only files |
| `docker-compose.yml` | Added `MINTKEY_BOOTSTRAP_KEK` env var to seed-job service (defaults to a dev key; override in prod) |
| `scripts/e2e-setup-env.sh` | Updated to decrypt the file with a `python3` one-liner before writing to Playwright `.env.local` |
| `seed-job/tests/test_bootstrap_encryption.py` | New: 9 unit tests covering encryption, idempotency, key rotation, permission dispatch |

### Bonus fix

`_ensure_secret_file` had a latent bug: when re-generating a file that was
already `chmod 0o400`, the write would fail with `PermissionError`. Fixed by
adding `path.chmod(0o600)` immediately before the overwrite when the file already
exists.

## Verification

```
9 passed in 0.18s
```

## Owner actions required before production deploy

1. Set `MINTKEY_BOOTSTRAP_KEK` to a fresh Fernet key in your production secrets
   manager / `.env`.  The docker-compose default is a **dev-only** key.
2. Ensure any CI job running the seed-job exports a valid `MINTKEY_BOOTSTRAP_KEK`.
3. If any existing production volume has a plaintext `admin_password` file, the
   next seed-job run will detect it as invalid (cannot decrypt) and regenerate —
   re-triggering Keycloak password sync.  Plan accordingly.

---

## Strike-2 supplement (2026-05-18)

**Scope expansion approved by owner.** Strike-1 encrypted the file but left 14 downstream readers
broken. Strike-2 adds a shared decrypt helper and patches all readers.

### What was done

| Area | Change |
|------|--------|
| `mintkey-models/mintkey_models/bootstrap_password.py` | New shared module: `read_bootstrap_password()`, `read_bootstrap_password_bytes()`, `BootstrapPasswordError`. Reads `MINTKEY_BOOTSTRAP_KEK` from env; raises clear error if missing/malformed. |
| `mintkey-models/pyproject.toml` | Added `cryptography>=42.0` dependency. |
| `mintkey-models/tests/test_bootstrap_password.py` | 11 unit tests: happy-path, missing-KEK, wrong-KEK, tampered ciphertext, plaintext rejection, missing-file. |
| `tests/acceptance/test_golden_path.py` | Patched `_pwd_file.read_text()` → `read_bootstrap_password()`. |
| `tests/acceptance/test_mock_backend_registered.py` | Patched inline `open(...).read().strip()` → `read_bootstrap_password()`. |
| `tests/acceptance/test_data_plane_smoke.py` | Patched. |
| `tests/acceptance/test_data_plane_resilience.py` | Patched. |
| `tests/acceptance/test_services_uuid_derivation.py` | Patched. |
| `tests/acceptance/test_mcp_auth_chain.py` | Patched. |
| `tests/acceptance/test_api_keys_and_permissions_carry_forward.py` | Patched. |
| `tests/acceptance/test_api_keys_and_permissions_chain.py` | Patched. |
| `tests/acceptance/test_test_service_body_parsing.py` | Patched. |
| `tests/acceptance/test_agent_wire_id_handling.py` | Patched. |
| `tests/integration/admin_api/test_credentials_live_vault.py` | Patched. |
| `mcp-server/tests/test_describe_service.py` | Patched (mcp-server conftest already adds mintkey-models to path). |
| `mcp-server/tests/test_request_token.py` | Patched. |
| `scripts/e2e_smoke.py` | `get_admin_password()` now decrypts via inline Fernet using `MINTKEY_BOOTSTRAP_KEK`; falls back to plaintext if KEK is unset (for dev stacks without KEK). |
| `admin-ui/src/lib/api-client.ts` | `getAdminPassword()` now decrypts Fernet ciphertext using Node.js built-in `crypto` (AES-128-CBC + HMAC-SHA256); no new npm dependency. Falls back to plaintext if `MINTKEY_BOOTSTRAP_KEK` is not set. |
| `docker-compose.yml` | Added `MINTKEY_BOOTSTRAP_KEK` to `admin-ui` service (same default syntax as `seed-job`). |
| `SECURITY.md` | Pluralised "dev KEK" → "dev KEKs (vault, bootstrap)"; added `MINTKEY_BOOTSTRAP_KEK` paragraph. |
| `PORTS.md` | Added "Bootstrap admin password KEK" section with env var, generation command, and operator note. |

### Readers patched: 14 total

11 acceptance tests + 2 mcp-server tests + 1 integration test + 1 script (`e2e_smoke.py`) + 1 JS file (`admin-ui/src/lib/api-client.ts`).

Note: `test_audit_append_only.py` matched the rg pattern but only uses `"admin_password"` as a PostgreSQL dict key — no file read. Not patched.

### Operator instructions — CI

Any pipeline that reads `admin_password` from the bootstrap-secrets volume (directly or via a mounted path) must export `MINTKEY_BOOTSTRAP_KEK` equal to the value used by the seed-job. Without it, `read_bootstrap_password()` raises `BootstrapPasswordError` with a clear message.

---

## Strike-3 supplement (2026-05-18)

Addressed three reviewer-flagged issues; no scope expansion.

### Issue #1 closed — KEK default mismatch (docker-compose.yml)

`admin-ui` had `jePSMThbHXS8J0V2d3xrOOgLmYhXx3V7VCcpVYeX6_0=` as the
`${MINTKEY_BOOTSTRAP_KEK:-...}` fallback, while `seed-job` and
`scripts/e2e-setup-env.sh` used `TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas=`.
In dev (no env override), seed-job encrypted with one key, admin-ui tried to
decrypt with the other — Fernet HMAC fails, login silently breaks.

Fix: `docker-compose.yml:236` updated to use the same canonical dev key as
line 126 (seed-job) and `scripts/e2e-setup-env.sh:71`.

| File | Change |
|------|--------|
| `docker-compose.yml:236` | `jePSMT...` → `TUQpz9...` (admin-ui KEK default) |

### Issue #2 closed — silent catch in admin-ui/src/lib/api-client.ts

`getAdminPassword` previously had a bare `catch { /* fall through */ }` that
swallowed every decrypt error (HMAC fail, malformed ciphertext, missing KEK),
then silently returned `""`. This made the KEK-mismatch bug invisible and left
server-to-server admin-api calls running unauthenticated.

New behaviour:
- `MINTKEY_BOOTSTRAP_KEK` **unset**: silent plaintext/env-var fallback
  (documented dev path, no error log).
- `MINTKEY_BOOTSTRAP_KEK` **set** but decrypt fails: `console.error` with the
  error message (KEK value is never logged), returns `""` so `getApiSession`
  treats it as auth-unavailable.
- In `NODE_ENV=production`: error is rethrown so misconfiguration is loud at
  startup.

8 vitest tests added in `admin-ui/tests/test_security_config.test.ts` covering
both paths (including `vi.spyOn(console, 'error')` assertions).

| File | Change |
|------|--------|
| `admin-ui/src/lib/api-client.ts` | Reshaped `getAdminPassword`; exported `@internal` for tests |
| `admin-ui/tests/test_security_config.test.ts` | New: 8 tests for KEK-absent and KEK-set-wrong paths |

### Issue #3 closed — 99-report header + commit SHA citations

This report now has the standard closing-report header block (matching
`team/remediation/2026-05-17-kong-syncer-startup-retry/99-report.md` convention)
with `**Status:** **CLOSED**`, branch/session metadata, and all 8 commit SHAs
cited.

### Verification

```
rg -nA1 "MINTKEY_BOOTSTRAP_KEK:-" docker-compose.yml
# 126: seed-job  TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas=
# 236: admin-ui  TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas=  ← now match

cd admin-ui && pnpm exec vitest run tests/test_security_config.test.ts
# 8 passed

cd seed-job && python -m pytest tests/ -x -q
# 9 passed
```
