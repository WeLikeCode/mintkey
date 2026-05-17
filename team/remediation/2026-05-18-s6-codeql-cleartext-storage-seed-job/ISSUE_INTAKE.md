# Issue Intake — S6 codeql-cleartext-storage-seed-job

## Problem statement

CodeQL rule `py/clear-text-storage-sensitive-data` fires at `seed-job/main.py:352`
and `seed-job/main.py:354` because `_ensure_secret_file` writes the bootstrap
admin password in plaintext via `path.write_text(value)` / `path.write_bytes(value)`.
The password is a random `secrets.token_urlsafe(32)` value seeded into Keycloak for
the first operator login; it lives on the `bootstrap_secrets` Docker named volume.

## User-visible symptom

GitHub code scanning shows 2 HIGH alerts under
`py/clear-text-storage-sensitive-data` pointing at `seed-job/main.py:352` and
`seed-job/main.py:354`.  No runtime failure; the risk is that any process with
volume access can read the admin credential in plaintext.

## Expected behavior

The `data/bootstrap-secrets/admin_password` file on disk should contain
Fernet-encrypted ciphertext, not the raw password string.  Only a process
that holds `MINTKEY_BOOTSTRAP_KEK` can decrypt it.

## Evidence

- `seed-job/main.py:350-357` — `_ensure_secret_file`: `path.write_text(value)` /
  `path.write_bytes(value)` called with the generate()-produced plaintext.
- `seed-job/main.py:907-933` — `_ensure_admin_password_file`: calls
  `_ensure_secret_file` with `generate=lambda: plaintext_password`.
- `seed-job/main.py:617` — `_sync_admin_password`: reads the file back and sends
  the plaintext to Keycloak.
- `scripts/e2e-setup-env.sh:68` — `cat "$BOOTSTRAP_PW_FILE"` reads the plaintext
  for Playwright .env.local.

## Approach chosen: C — Fernet encryption with MINTKEY_BOOTSTRAP_KEK

**Why C over the other options:**

- **(A) Argon2id hash + one-shot token**: requires admin-api changes to verify the
  token on first login — BLOCKED (out of scope for seed-job session).
- **(B) FS perms 0o600 + deletion**: does not close the CodeQL alert; the write is
  still semantically cleartext.
- **(C) Fernet encryption**: closes the CodeQL alert cleanly.  `cryptography` is a
  well-audited stdlib-adjacent dep.  Adding it to `seed-job/requirements.txt` stays
  within seed-job scope.  The KEK is provisioned via a single env var in the seed-job
  service (docker-compose.yml), not shared with any other service.
- **(D) Stdout only**: the password file is read by `_sync_admin_password` (in-process)
  AND by `scripts/e2e-setup-env.sh` (out-of-process, from the host).  Removing the
  file would require changing both the Keycloak sync path and the e2e script; the
  blast radius is larger than Approach C.

## Scope

- `seed-job/main.py` — encryption helpers, `_ensure_admin_password_file`,
  `_sync_admin_password`.
- `seed-job/requirements.txt` — add `cryptography>=42.0`.
- `docker-compose.yml` — add `MINTKEY_BOOTSTRAP_KEK` env var to seed-job service.
- `scripts/e2e-setup-env.sh` — decrypt file before writing to Playwright .env.local.
- `seed-job/tests/test_bootstrap_encryption.py` — new unit tests.
- This intake + `99-report.md`.

## Out of scope

vault-adapter, admin-api, broker code, Keycloak realm JSON, Liquibase migrations,
any service other than seed-job.

## Risk level

`security` — closes 2 HIGH CodeQL alerts.  No runtime regression risk: the
encryption/decryption is symmetric within the same process; the Fernet token is
always fresh when valid.

## Verification target

```bash
cd /Users/alexandruiacobescu/gooseProjects/mintkey-s6-codeql-cleartext-storage-seed-job
cd seed-job && python -m pytest tests/ -x -q 2>&1 | tail -20
```

All tests pass.  The `admin_password` file written by `_ensure_admin_password_file`
must be Fernet ciphertext (starts with `gAAAAA` when decoded from URL-safe base64),
not a raw token string.

## Owner decisions needed

1. **Production KEK rotation**: the docker-compose default dev key
   `TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas=` must be overridden in production
   via an `.env` file or secrets manager before going live.  The seed-job aborts if
   `MINTKEY_BOOTSTRAP_KEK` is unset (no silent cleartext fallback).
2. **CI pipelines**: any CI job that exercises the seed-job must export
   `MINTKEY_BOOTSTRAP_KEK` (any valid Fernet key suffices for CI; it need not match
   production).
3. **Existing volumes**: if a production `bootstrap_secrets` volume already contains
   a plaintext `admin_password` file, the validation step in `_ensure_admin_password_file`
   will see it as invalid (cannot be Fernet-decrypted) and regenerate with a fresh
   encrypted token.  This re-triggers the Keycloak password sync on the next seed-job
   run.  Operator must re-provision their password via `mintkey admin reset-password`
   or allow the seed-job re-sync to overwrite the Keycloak password.

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with concrete file:line)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions noted
