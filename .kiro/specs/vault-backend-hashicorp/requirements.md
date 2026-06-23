# Requirements — Vault Adapter backend: HashiCorp Vault (KV v2)

> Kiro spec for adding a HashiCorp Vault storage backend to the Mintkey Vault Adapter.
> Status: Draft. Target ADR on acceptance: **ADR-0025**.
> Authoritative constraints read from: `apps/vault-adapter/internal/store/store.go`,
> `docs/architecture/01-architecture/adr/0003-credential-storage-strategy.md`,
> `docs/architecture/01-architecture/adr/0011-shared-go-stack.md`,
> `docs/architecture/01-architecture/adr/0021-vault-storage-backend-postgres.md`,
> `docs/architecture/contracts/vault-adapter/vault.proto`.

---

## 1. Summary

The Vault Adapter (container C6) currently stores envelope-encrypted credentials in
Postgres (default) or SQLite (opt-in fallback), selected by
`MINTKEY_VAULT_BACKEND={postgres|sqlite}`. ADR-0021 §Alternatives explicitly lists
**"HashiCorp Vault (ADR-0003 v2 backend) — Still planned as v2; deferred."** OQ-003
(Vault Adapter horizontal scaling) names "bring HashiCorp Vault forward as v2" as the
lead candidate. This spec realises that backend as a third, opt-in value:
`MINTKEY_VAULT_BACKEND=hashicorp`.

**Storage model (do not deviate).** Mintkey's KEK/DEK envelope (AES-256-GCM, per-credential
DEK wrapped by the KEK — ADR-0003 §Decision 2) is **unchanged**. HashiCorp Vault is used as
an opaque key/value substrate for the already-encrypted `wrapped_dek` and `enc_payload`
blobs plus metadata, exactly as Postgres/SQLite are today. We do **not** push plaintext into
HashiCorp's Transit engine or store plaintext in KV. The new backend is a `Backend`
implementation, nothing more.

---

## 2. User stories

- **US-1.** As an operator running Mintkey in an environment that already standardises on
  HashiCorp Vault, I want to point the Vault Adapter at my HashiCorp Vault KV v2 mount so
  that credential storage lives in my existing secrets platform instead of Postgres.

- **US-2.** As an operator, I want to select the HashiCorp backend with a single env var
  (`MINTKEY_VAULT_BACKEND=hashicorp`) and have `postgres`/`sqlite` continue to work
  unchanged, so I can adopt it without breaking existing deployments.

- **US-3.** As an operator, I want a one-shot migration command
  (`make migrate-vault-to-hashicorp`) that copies every credential from my current Postgres
  vault store into HashiCorp Vault idempotently and verifies a byte-equal sample, so I can
  cut over safely.

- **US-4.** As a security owner, I want the HashiCorp Vault token to be obtained via AppRole,
  auto-renewed by a background goroutine, and **never** logged or placed in an OTel span
  attribute, so the broker token does not leak.

- **US-5.** As a developer, I want a HashiCorp Vault community container in the dev/CI
  compose so integration tests run hermetically with `testcontainers-go`.

---

## 3. Functional requirements

| ID | Requirement |
|----|-------------|
| **FR-1** | `store.NewFromEnv` MUST accept `MINTKEY_VAULT_BACKEND=hashicorp` and return a `*HashiCorpStore` that satisfies the existing `store.Backend` interface (`Put`, `Get`, `Revoke`, `ListVersions`, `Close`). |
| **FR-2** | `hashicorp` MUST be additive: `postgres` (default when unset), `sqlite`, and the existing error messages MUST behave exactly as today. The unknown-backend error path MUST still fire for any value that is not one of the three. |
| **FR-3** | `Put(ctx, rec)` MUST assign the next `key_version` = `MAX(key_version)+1` per `(tenant_id, service_id)` (min 1), mark all prior versions of that `(tenant_id, service_id)` as `is_current=false`, write the new version as `is_current=true, is_revoked=false`, and return the assigned `key_version` — identical semantics to `PostgresStore.Put`. |
| **FR-4** | `Get(ctx, tenantID, serviceID, keyVersion)` with `keyVersion==0` MUST return the `is_current=true` version; with `keyVersion>0` MUST return that exact version regardless of `is_revoked`. On no match it MUST return a wrapped `sql.ErrNoRows` so `errors.Is(err, sql.ErrNoRows)` holds (parity with both existing backends). |
| **FR-5** | `Revoke(ctx, tenantID, serviceID, keyVersion)` MUST set `is_revoked=true` on a non-current version, return `store.ErrRevokeCurrent` when the target is current, and return a wrapped `sql.ErrNoRows` when the version does not exist. |
| **FR-6** | `ListVersions(ctx, tenantID, serviceID, afterKeyVersion, limit)` MUST return metadata-only records (`WrappedDEK` and `EncPayload` empty) ordered by ascending `key_version`, `key_version > afterKeyVersion`, with `limit` clamped to 50 when 0 or > 200. |
| **FR-7** | Stored values MUST round-trip every `CredentialRecord` field that the SQLite backend persists: `credential_id, tenant_id, service_id, key_version, auth_scheme, wrapped_dek, enc_payload, is_current, is_revoked, created_at, target_url, header_name, query_param, target_address, ssh_user`. (HashiCorp Vault has no JOIN; `ServiceBaseUrl`, `TlsInsecureSkipVerify`, and SMTP/IMAP fields are Postgres-JOIN-only and remain empty/zero, exactly as SQLite leaves them.) |
| **FR-8** | The backend MUST authenticate to HashiCorp Vault using **AppRole** (`role_id` + `secret_id`), obtain a client token, and renew it on a background goroutine before TTL expiry. Token renewal failure MUST be logged (without the token) and retried with backoff. |
| **FR-9** | Concurrent `Put` for the same `(tenant_id, service_id)` MUST NOT produce duplicate `key_version`s. Serialise via an in-process per-key mutex (HashiCorp KV v2 also provides CAS as a second-line defence — see design). |
| **FR-10** | A migration command `cmd/vault-migrate-pg-to-hashicorp/` MUST copy every row from the Postgres `vault.credentials` table to HashiCorp Vault, be idempotent (skip on existing `credential_id`), verify a 5-sample byte-equal round-trip, and assert the migrated count. Invoked via `make migrate-vault-to-hashicorp`. |
| **FR-11** | All new env vars MUST appear in `.env.example` with an explanatory comment (project guardrail). |
| **FR-12** | `main.go`'s SSH-RPC wiring (`if pgStore, ok := st.(*store.PostgresStore); ok`) MUST continue to compile and behave: with the HashiCorp backend selected, `SSHVaultAdapter` is disabled (the type assertion fails), exactly as it does for SQLite today. No change to that block is required or permitted beyond what compiles. |

---

## 4. Non-functional requirements

| ID | Requirement |
|----|-------------|
| **NFR-1 (Security)** | The AppRole `secret_id` and the issued client token MUST NEVER appear in any log line, error message, or OTel span attribute. Verified by the red-team grep (`scripts/red-team-fingerprints.txt` pattern, plus an explicit test asserting the token is absent from captured logs). Matches ADR-0017.6 allowlist: nothing matching `*_token`/`*_secret`. |
| **NFR-2 (Security)** | Plaintext credential bytes MUST NEVER reach HashiCorp Vault. Only the KEK-wrapped `wrapped_dek` and DEK-encrypted `enc_payload` (already ciphertext) are written. The KEK stays local (`MINTKEY_VAULT_KEK_FILE`), never sent to HashiCorp. |
| **NFR-3 (Availability)** | When HashiCorp Vault is unreachable, `Get`/`Put` MUST return an error that the gRPC layer maps to `UNAVAILABLE` (per vault.proto), not a panic. Existing server error mapping is reused. |
| **NFR-4 (Performance)** | `Get` of the current version MUST be a single KV read (plus at most one index read). No full-mount scan on the hot path. p50 under 20 ms against a local HashiCorp Vault container is the target (informational, not gating). |
| **NFR-5 (Compat)** | No Liquibase change. No SQLAlchemy change. No `vault.proto` change. No change to the `CredentialRecord` struct. No `init()` side effects in new packages. |
| **NFR-6 (Lint)** | New Go code MUST pass `go vet ./...` and `staticcheck ./...` with zero findings in the `vault-adapter` module. |

---

## 5. Out of scope (explicit)

- HashiCorp Vault **Transit** engine (server-side encryption) — we keep our own KEK/DEK envelope.
- HashiCorp Vault **dynamic secrets / leases on the upstream credential** — credentials are static blobs from the adapter's perspective.
- HashiCorp Vault **Enterprise** features (namespaces, performance replication, HSM seal).
- Making HashiCorp the **default** backend — it is opt-in; Postgres remains the default.
- Removing or deprecating the Postgres or SQLite backends.
- SSH RPC support on the HashiCorp backend (`SSHVaultAdapter` stays Postgres-only, like SQLite).
- Migrating **from** SQLite to HashiCorp directly (migrate SQLite→Postgres first via the
  existing `make migrate-vault-sqlite-to-pg`, then Postgres→HashiCorp). Documented, not coded.
- Per-tenant HashiCorp mounts / per-tenant AppRoles. One mount, app-layer tenant scoping via
  the path prefix (design §wire-level). RLS is a Postgres concept and does not transfer.
- KEK rotation re-wrap across the HashiCorp store (re-wrap path is unchanged; out of this scope).

---

## 6. Acceptance criteria (mechanically verifiable by Sonnet)

1. **AC-1 (selector):** `go test ./internal/store/ -run TestNewFromEnv_Hashicorp` passes — asserts
   `MINTKEY_VAULT_BACKEND=hashicorp` returns a `*HashiCorpStore` (or the documented
   missing-config error when AppRole env is absent). Exit code 0.
2. **AC-2 (regression):** `go test ./internal/store/ -run TestNewFromEnv` passes — the four
   existing selector tests (`DefaultsToPostgres`, `Sqlite`, `PostgresMissingDSN`, `UnknownBackend`)
   are unchanged and green.
3. **AC-3 (conformance):** `go test ./internal/store/ -run TestHashiCorp -tags=integration` passes
   against a `testcontainers-go` HashiCorp Vault container — exercises Put → Get(0) → Get(v) →
   Revoke → ListVersions and asserts `key_version` monotonicity, current-version flip, and
   `ErrRevokeCurrent` on the current version.
4. **AC-4 (round-trip):** an integration test seals a random payload via `crypto.Seal`, `Put`s the
   `CredentialRecord`, `Get`s it back, and asserts `bytes.Equal` on `WrappedDEK` and `EncPayload`
   and equality on every persisted scalar field.
5. **AC-5 (no-leak):** `go test ./internal/store/ -run TestHashiCorp_TokenNotLogged` passes —
   captures the package logger output during AppRole login + a `Get`, asserts the `secret_id`
   and client token substrings are absent.
6. **AC-6 (migration):** `go test ./cmd/vault-migrate-pg-to-hashicorp/ -tags=integration` passes —
   seeds Postgres `vault.credentials`, runs the migration against a HashiCorp container, asserts
   read-count == inserted-count and a 5-sample byte-equal verification PASS, and that a second run
   reports all rows skipped-on-conflict (idempotency).
7. **AC-7 (lint):** `go vet ./...` and `staticcheck ./...` in `apps/vault-adapter` exit 0.
8. **AC-8 (env doc):** every env var named in design §Env vars is present in `.env.example`
   (grep each name → exit 0).
9. **AC-9 (compose):** `docker compose -f infra/compose/docker-compose.yml config` succeeds with the
   new `hashicorp-vault` service present (CI/dev only).
