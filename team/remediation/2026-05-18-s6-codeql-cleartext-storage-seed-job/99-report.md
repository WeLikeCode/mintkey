# Remediation Report — S6 codeql-cleartext-storage-seed-job

**Date**: 2026-05-18
**Branch**: `fix/s6-codeql-cleartext-storage-seed-job-2026-05-18`
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
