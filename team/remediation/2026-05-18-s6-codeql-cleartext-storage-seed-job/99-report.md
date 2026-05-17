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
