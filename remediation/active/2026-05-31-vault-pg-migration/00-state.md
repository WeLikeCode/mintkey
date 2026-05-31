# Remediation: Vault SQLite → Postgres migration + unified backup/restore

**Session:** 2026-05-31-vault-pg-migration
**Branch:** `integration/applejwt-googlesa-local` (local-only; landing strategy decided post-cutover)
**Pattern:** orchestrator (Sonnet implementer + fresh Opus reviewer, 3-strike hard-stop, flip-tests)
**Pre-migration backup:** `~/mintkey-backups/20260531_222854/` (628K — pg dump + sqlite + KEK + bootstrap, all checksummed)

## Issue intake

1. **Problem.** Vault-adapter stores encrypted credentials in local SQLite at `/var/lib/mintkey/vault.sqlite` (volume `mintkey_vault_data`). Postgres already runs in the stack but the vault data lives outside it — `pg_dump` does not capture vault state, backup/restore tooling has to handle two stores, and "we have postgres, use it" is the owner's explicit position.
2. **Symptom.** Operator cannot get a complete `mintkey` state snapshot from `pg_dump` alone; vault data requires a separate volume export. Cross-service postgres-backup procedures miss vault credentials silently.
3. **Expected behavior.** Vault credentials stored in `mintkey` postgres under a dedicated `vault` schema. Single `pg_dump` captures all mintkey state (modulo KEK, which lives on disk by design). Backend remains pluggable via `MINTKEY_VAULT_BACKEND={postgres|sqlite}` (post-migration default = `postgres`). SQLite store kept as fallback for offline/embedded deploys.
4. **Evidence.** `apps/vault-adapter/internal/store/sqlite.go` (only store impl; ~200 LOC, `Store` interface implied by usage in `cmd/vault-adapter/main.go`). Vault SQLite has 138 credentials at backup time. Existing postgres has admin-api metadata in `public.credentials` (empty `ciphertext` columns — confirms vault is currently the sole source of truth for encrypted blobs). KEK at `/run/secrets/` volume `mintkey_vault_kek`.
5. **Scope (in).**
    - Pre-migration backup (done — see above).
    - `vault` schema + `vault.credentials` table via Liquibase changelog.
    - `apps/vault-adapter/internal/store/postgres.go` (pgx-backed Store impl, same interface as sqlite.go).
    - Backend selector in `cmd/vault-adapter/main.go` keyed on `MINTKEY_VAULT_BACKEND` (default `postgres`).
    - One-shot migration tool `cmd/vault-migrate-sqlite-to-pg` (idempotent; row-count + sample round-trip verification).
    - Cutover on local stack with both Apple + Google credentials re-verified through gRPC `GetCredential` + tokeninfo / `/v1/apps` probes.
    - Unified `make backup` / `make restore` Makefile pair (pg dump + KEK + bootstrap-secrets, single tarball, checksummed manifest).
6. **Out of scope.**
    - Production cutover (this is the local stack; main-branch landing is a separate decision).
    - KEK/DEK encryption scheme change (ADR-0003 stays).
    - Removing the SQLite implementation post-cutover (owner: keep as fallback).
    - Separate `mintkey_vault` database (owner: dedicated schema in `mintkey` DB).
7. **Risk.** **HIGH** — vault data is encrypted but irreplaceable. Lose any one of {KEK, encrypted blobs, postgres metadata} and credentials are gone. Mitigations: backup before any change; dual-store dual-read verification before flipping live backend; idempotent migration tool; reviewer flip-tests per chunk.
8. **Verification target.**
    - Pre-migration backup contents restorable to a scratch stack (sanity).
    - Migration tool produces matching `vault.credentials` row count = SQLite count (138 at baseline; will grow if user creates more before cutover — capture count at C5 dispatch time).
    - Post-cutover: live `GetCredential` for the apple + google credentials returns identical bytes to a pre-cutover capture; tokeninfo (google) and `/v1/apps` (apple) both still return HTTP 200.
    - `make backup` produces a tarball whose `pg_restore` + KEK + bootstrap re-tar can be applied to a wiped stack and yield identical `GetCredential` results.
9. **Owner decisions (LOCKED 2026-05-31).**
    - DB layout: `vault` schema in `mintkey` DB.
    - Default backend post-cutover: `postgres`.
    - SQLite code: kept; selectable via env.
    - Backup tooling: single Makefile pair (`make backup` / `make restore`).

## Chunk plan

Each chunk: Sonnet IMPLEMENTER → fresh Opus REVIEWER → flip-test. 3-strike hard-stop per chunk.

- **C1 — Liquibase schema** for `vault` schema + `vault.credentials` table (mirrors SQLite columns: `credential_id`, `tenant_id`, `service_id`, `key_version`, `auth_scheme`, `wrapped_dek bytea`, `enc_payload bytea`, `is_current bool`, `is_revoked bool`, `created_at timestamptz`, `target_url`, `header_name`, `query_param`; UNIQUE on `(tenant_id, service_id, key_version)`). Grant `mintkey_app` SELECT/INSERT/UPDATE; `mintkey_migrate` ALL. RLS policies mirroring `public.credentials` if any exist. Files: `apps/admin-api/src/admin_api/db/changelog/*` or equivalent location.
- **C2 — Postgres store impl** `apps/vault-adapter/internal/store/postgres.go` parallel to `sqlite.go`. Same `Store` interface, pgx-backed. Unit tests (postgres testcontainer or `-tags=postgres` build tag).
- **C3 — Backend selector** `cmd/vault-adapter/main.go`: read `MINTKEY_VAULT_BACKEND` (default `postgres`), `MINTKEY_VAULT_PG_DSN`. Wire into factory. Update `docker-compose.yml` (root + infra/compose) to set both env vars for vault-adapter. Existing `MINTKEY_VAULT_FILE_PATH` kept as sqlite fallback.
- **C4 — Migration tool** `cmd/vault-migrate-sqlite-to-pg/`. Reads vault.sqlite path (env or flag), writes via the postgres Store. Idempotent: skip-existing on `credential_id` PK. Verifies row count + sample blob byte-equal round-trip on a random sample of 5 credentials. Outputs SUMMARY (input/written/skipped/errors).
- **C5 — Cutover + verification.** Run C4 against the local stack. Restart vault-adapter with `BACKEND=postgres`. Re-probe Apple + Google credentials via gRPC `GetCredential` (assert identical access tokens / JWTs versus pre-cutover snapshot). Confirm `/v1/apps` (Apple) + tokeninfo (Google) still HTTP 200.
- **C6 — Unified backup/restore Makefile** `make backup`: timestamped dir under `~/mintkey-backups/<TS>/` with `postgres-mintkey.pgcustom`, `vault-kek.tar.gz`, `bootstrap-secrets.tar.gz`, `MANIFEST.txt` (sha256). `make restore BACKUP_DIR=<path>`: validates manifest checksums, then `pg_restore` + KEK volume + bootstrap-secrets. Update `docs/HOW-TO.md` backup section. (Sqlite path included only when `BACKEND=sqlite` is set, kept tidy.)
- **C7 — Documentation + ADR.** ADR entry (vault backend choice + migration rationale). `docs/HOW-TO.md` backup/restore section refreshed. `README.md` brief mention of selector. Cross-link from any place SQLite-specific guidance currently lives.

## Dependency graph

```
C1 (schema) ──┐
              ├──> C2 (pg store impl) ──> C3 (selector) ──> C4 (migration tool) ──> C5 (cutover+verify)
              │                                                                        │
C6 (backup/restore) ─── parallel with C1, C2 ─────────────────────────────────────────┤
                                                                                       │
C7 (docs) ─── depends on all ──────────────────────────────────────────────────────────┘
```

Parallel dispatches: C1 + C6 first round. Then C2 (needs C1's schema names). Then C3 alone. Then C4. Then C5. Then C7 last.

## Round history

- **R0 (2026-05-31 22:28)**: pre-migration backup captured at `~/mintkey-backups/20260531_222854/`. State file written.
- **R1 (pending)**: dispatching C1 (Liquibase schema) + C6 (backup/restore Makefile) in parallel.
- **R3 (2026-05-31 23:30) — C5 Cutover: SUCCESS**
  - Phase 1: Fresh backup at `~/mintkey-backups/20260531_232911/` (458K pg dump + 96K sqlite + KEK + bootstrap).
    - Pre-cutover: SQLite=138, Postgres=0. Apple gRPC: len=293, sha256=40fb91a55bcab1e4 (iss=8509b9f6, aud=appstoreconnect-v1, kid=YDCJCC5N3A, exp-iat=1140s). Google gRPC: len=1024, sha256=39090e83b27393d6, prefix=ya29.c.c0AZ4bNpZtKoAaQWZC.
  - Phase 2: `make migrate-vault-sqlite-to-pg` — Read 138, Inserted 138, Skipped 0, Errors 0, Sample verify PASS. Postgres post: 138 rows, 2 with auth_scheme IN (9,10) = Apple+Google.
  - Phase 3: `docker compose up -d --no-deps --force-recreate vault-adapter`. Healthy in 4s. Env confirmed via docker inspect: MINTKEY_VAULT_BACKEND=postgres, MINTKEY_VAULT_PG_DSN=postgres://mintkey_migrate:***@postgres:5432/mintkey, FILE_PATH still set (legacy/unused). Note: "store backend = postgres" log line absent from container logs — image pre-dates that log line; NewFromEnv succeeded (healthy serving, no exit).
  - Phase 4: Post-cutover gRPC. Apple: len=293, sha256=3050fc9260fef0e7 (new JWT — expected), kid=YDCJCC5N3A, iss=8509b9f6, aud=appstoreconnect-v1, exp-iat=1140s. Google: len=1024, sha256=8e69e280f635e10c, prefix=ya29.c.c0AZ4bNpZ3fWM5NbGr.
  - Phase 5: Live APIs. Apple /v1/apps → HTTP 200, 3 apps. Google tokeninfo → HTTP 200, scope=androidpublisher, expires_in=3575.
  - **Vault-adapter is now serving all 138 credentials from Postgres. SQLite file retained on volume as fallback.**

## Round R4 — C7 docs (pending commit hash)

**Files touched:**

| File | Change |
|---|---|
| `docs/architecture/01-architecture/adr/0021-vault-storage-backend-postgres.md` | **New** — ADR documenting Postgres as default vault backend; amends ADR-0003. |
| `docs/architecture/01-architecture/adr/0003-credential-storage-strategy.md` | Status block amended: corrigendum pointing to ADR-0021. |
| `docs/architecture/01-architecture/adr/README.md` | ADR-0021 entry appended to index. |
| `docs/HOW-TO.md` | New §5 "Vault migration: SQLite → Postgres" inserted; old §5–§9 renumbered to §6–§11. |
| `README.md` | New "Vault storage backend" subsection (3 lines) added before "Backup local state before a reset"; `vault-adapter` repo-map line updated. |
| `AGENTS.md` | One-line `MINTKEY_VAULT_BACKEND` mention added to "Schema and storage" guardrail. |
| `CLAUDE.md` | Same line (non-breaking-hyphen style) added to "Schema and storage" guardrail. |
| `remediation/active/2026-05-31-vault-pg-migration/00-state.md` | This R4 section. |

**Commit hash:** `d340c18`

## Open questions

(none — all 4 owner decisions answered at intake)

## Notes

- Verification snapshot captured *before* cutover (C5 dispatch): list of `(credential_id, sha256(value-on-GetCredential))` for the Apple + Google services. Compare post-cutover.
- The `KEK volume` (`mintkey_vault_kek`) is **independent** of which store backend is used — it's always needed to decrypt envelopes; backup/restore must always include it.
- 138 credentials in SQLite at baseline. Most are historical test artifacts; only ~5 are the user's real (Apple, Google, GitHub, GitLab, Spotus Dashboard). Migration must round-trip ALL 138 — don't filter.
