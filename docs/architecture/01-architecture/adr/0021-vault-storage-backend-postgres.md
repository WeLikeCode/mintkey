# ADR-0021: Vault Adapter default storage backend — Postgres

## Status
Accepted — 2026-05-31.

Amends [ADR-0003](0003-credential-storage-strategy.md): v1 SQLite file backend is demoted to opt-in fallback; Postgres is the new default. KEK/DEK scheme (ADR-0003 §Decision 2) is unchanged.

---

## Context

ADR-0003 shipped a pluggable Vault Adapter with SQLite as the v1 backend (`apps/vault-adapter/internal/store/sqlite.go`, credential file at `MINTKEY_VAULT_FILE_PATH`, mounted on docker volume `mintkey_vault_data`). Postgres was already running in the stack for admin-api metadata, but vault credentials lived outside it.

Two problems emerged at local-stack scale:

1. **Incomplete backups.** `pg_dump mintkey` captured agents, services, permissions, and audit events but missed vault state entirely. Operators had to separately `docker cp` or `tar` the SQLite volume, creating a two-step, error-prone backup procedure with a silent failure mode (a postgres-only restore yields a running stack with no credentials).

2. **Two stores, no single source of truth.** The stack already carries one Postgres instance (`mintkey` DB, pgx/v5, Liquibase-managed schema). Running a second, structurally different store for the most sensitive data — encrypted credentials — increased operational complexity without providing any benefit over a dedicated schema in the existing DB.

At the time of this ADR: 138 credentials were in the SQLite store. The admin-api `public.credentials` table existed but had empty `ciphertext` columns — vault-adapter was the sole source of truth for encrypted blobs.

---

## Decision

Add a Postgres backend for the Vault Adapter (`vault.credentials` table in the `vault` schema of the existing `mintkey` DB), make it the **default backend post-2026-05-31**, and retain SQLite as an opt-in fallback.

**Backend selector:** `MINTKEY_VAULT_BACKEND={postgres|sqlite}`. Default is `postgres`. The SQLite path is unchanged and accessible by setting `MINTKEY_VAULT_BACKEND=sqlite` (or for new deploys with no history, `MINTKEY_VAULT_BACKEND` is simply omitted — the default is postgres).

**Schema:** Liquibase changelog `018-vault-schema.yaml` creates `vault.credentials` with 13 columns mirroring the SQLite schema (`credential_id`, `tenant_id`, `service_id`, `key_version`, `auth_scheme`, `wrapped_dek`, `enc_payload`, `is_current`, `is_revoked`, `created_at`, `target_url`, `header_name`, `query_param`), a UNIQUE constraint on `(tenant_id, service_id, key_version)`, an RLS policy (`tenant_isolation` USING `current_setting('app.current_tenant', true)::uuid`), and grants to `mintkey_app` (SELECT/INSERT/UPDATE) and `mintkey_migrate` (ALL).

**Concurrency:** Concurrent `Put` for the same `(tenant_id, service_id)` is serialised via `pg_advisory_xact_lock(hashtextextended(tenant_id||service_id, 0))`. The UNIQUE constraint is the second-line defense.

**Migration:** A one-shot migration tool (`apps/vault-adapter/cmd/vault-migrate-sqlite-to-pg/`) performs an idempotent copy from the SQLite store to the Postgres store: skip-on-conflict for existing `credential_id`, 5-sample byte-equal round-trip verification, row-count assertion. Invoked via `make migrate-vault-sqlite-to-pg`. See [§ Migration procedure](#migration-procedure).

**Outcome:** 138 credentials migrated on 2026-05-31. Stack restarted with `MINTKEY_VAULT_BACKEND=postgres`. Apple JWT (`/v1/apps` → HTTP 200) and Google OAuth2 (`tokeninfo` → HTTP 200, `expires_in=3575`) verified post-cutover.

---

## Consequences

### Positive
- **Single `pg_dump` captures complete mintkey state.** `pg_dump -F custom mintkey` now covers vault credentials, admin metadata, agents, services, permissions, and audit events in one operation. The `make backup` / `make restore` pair (C6 / ADR-aligned) issues one `pg_dump` and separately archives the KEK volume and bootstrap secrets — see [docs/HOW-TO.md §4](../../HOW-TO.md#4-backup-and-restore).
- **RLS parity with admin-api tables.** `tenant_isolation` policy is identical in shape to `public.credentials`; `mintkey_app` role is RLS-subject at runtime; no per-request GUC bookkeeping needed beyond what the broker already sets.
- **No new infrastructure.** The existing `mintkey` Postgres instance is reused; no new container, no new DSN.

### Costs
- **DSN required.** `MINTKEY_VAULT_PG_DSN` must be set for the vault-adapter container. Compose env is wired (C3); new deployments from the updated compose get it automatically.
- **SQLite still in code.** `apps/vault-adapter/internal/store/sqlite.go` is retained; the `modernc.org/sqlite` dependency stays in the Go workspace. This is deliberate — offline/embedded deploy support.
- **No destructive migration.** SQLite data is left on the volume after migration; it is not deleted. Rollback to SQLite is `MINTKEY_VAULT_BACKEND=sqlite` + service restart.

### Constraints inherited
- KEK volume (`mintkey_vault_kek`) is independent of the storage backend — always required to decrypt envelopes. Backup/restore must always include the KEK.
- `pg_advisory_xact_lock` serialises concurrent `Put` for the same row; this is acceptable at expected write rates (credential rotation is infrequent).

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Separate `mintkey_vault` database | Two DB instances = two `pg_dump` invocations, two connection pool configs, no cross-DB diagnostic queries. No benefit over a dedicated schema. |
| `public.vault_credentials` table (no schema isolation) | Weaker namespace isolation; would sit adjacent to admin-api tables that have no need to touch vault blobs; dedicated `vault` schema matches existing `public.credentials` layout more cleanly and is searchable (`\dt vault.*`). |
| Remove SQLite code entirely | Rejected by owner: offline/embedded deploys (laptop dev with no Postgres) should remain possible. SQLite is an opt-in escape hatch, not a deprecated dead path. |
| HashiCorp Vault (ADR-0003 v2 backend) | Still planned as v2; deferred. This ADR advances the v1 SQLite → Postgres within the existing stack without requiring a new container. |

---

## Migration procedure

See [docs/HOW-TO.md § Vault migration: SQLite → Postgres](../../HOW-TO.md#vault-migration-sqlite--postgres) for the operator runbook.

Summary:
1. `make backup` (mandatory pre-flight).
2. Confirm `vault.credentials` exists: `\dt vault.*` in `psql`.
3. `make migrate-vault-sqlite-to-pg`.
4. `docker compose up -d --no-deps --force-recreate vault-adapter`.
5. Verify startup log for `vault-adapter: store backend = postgres`.

---

## Related

- [ADR-0003](0003-credential-storage-strategy.md) — pluggable Vault Adapter; KEK/DEK scheme; amended here (SQLite demoted to opt-in fallback).
- [ADR-0008](0008-multi-tenancy-row-level-with-db-tier.md) — tenant context via `app.current_tenant` GUC; RLS policy shape reused.
- [ADR-0011](0011-shared-go-stack.md) — Go stack (`pgx/v5`, `modernc.org/sqlite`); both remain in use.
- [ADR-0015](0015-liquibase-schema-source-of-truth.md) — Liquibase as schema source of truth; changelog `018-vault-schema.yaml`.
- [`docs/HOW-TO.md`](../../HOW-TO.md) — operator playbook; §4 Backup and restore; §5 Vault migration.
- `remediation/active/2026-05-31-vault-pg-migration/00-state.md` — cutover evidence (C5 verification, pre/post gRPC hashes, live API probes).

---

## Corrigendum — vault.credentials.target_address deprecated for SSH per ADR-0023

**Date:** 2026-06-01. **Authority:** [ADR-0023](0023-ssh-upstream-base-url-canonical.md).

The §Decision §Schema block lists `target_address` as an active column read by ssh-proxy for SSH
routing. As of ADR-0023:

- For SSH auth schemes (`ssh_password`, `ssh_private_key`, `ssh_ca`), **`services.base_url` is the
  canonical upstream address**. vault-adapter's `GetCredential` LEFT JOINs `public.services` and
  returns `base_url`; ssh-proxy uses it directly.
- `vault.credentials.target_address` is **deprecated** for SSH routing. It is retained in the
  schema as a transition safety net and kept in sync via the C-6 cascade (admin-api writes
  `target_address` when `base_url` changes), but it is no longer the authoritative field.
- A follow-up migration (ADR-0023 §Follow-up F2) will `DROP COLUMN vault.credentials.target_address`
  after a quiet observation period.

This does not change the KEK/DEK scheme, RLS policy, backup procedure, or any other aspect of
this ADR.
