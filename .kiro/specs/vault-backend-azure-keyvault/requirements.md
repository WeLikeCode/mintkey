# Requirements — Vault Adapter backend: Azure Key Vault

> Kiro spec for adding an Azure Key Vault storage backend to the Mintkey Vault Adapter.
> Status: Draft. Target ADR on acceptance: **ADR-0026**.
> Authoritative constraints read from: `apps/vault-adapter/internal/store/store.go`,
> `docs/architecture/01-architecture/adr/0003-credential-storage-strategy.md`,
> `docs/architecture/01-architecture/adr/0011-shared-go-stack.md`,
> `docs/architecture/01-architecture/adr/0021-vault-storage-backend-postgres.md`,
> `docs/architecture/contracts/vault-adapter/vault.proto`.

---

## 1. Summary

The Vault Adapter (container C6) stores envelope-encrypted credentials in Postgres (default) or
SQLite (opt-in), selected by `MINTKEY_VAULT_BACKEND={postgres|sqlite}`. This spec adds a fourth,
opt-in value `MINTKEY_VAULT_BACKEND=azure`, backed by **Azure Key Vault** for operators running
on Azure who want credential storage in their managed Key Vault.

**Storage model (do not deviate).** Mintkey's KEK/DEK envelope (AES-256-GCM, per-credential DEK
wrapped by the KEK — ADR-0003 §Decision 2) is **unchanged**. Azure Key Vault holds the
already-encrypted envelope blobs and metadata as **secret values**; we do NOT use Azure Key
Vault's Keys (RSA/EC) or the Managed HSM crypto operations. The new backend is a `store.Backend`
implementation only — the same role Postgres/SQLite/HashiCorp play.

**Auth model.** Authentication uses `DefaultAzureCredential` from `azure-sdk-for-go`
(`azidentity`), which resolves environment credentials → workload identity → managed identity →
Azure CLI in order. This lets the same binary authenticate via a service principal in CI, a
managed identity in production, and the developer's `az login` locally without code changes.

---

## 2. User stories

- **US-1.** As an operator running Mintkey on Azure, I want to point the Vault Adapter at my
  Azure Key Vault so credential storage lives in my managed Key Vault rather than Postgres.

- **US-2.** As an operator, I want to select the Azure backend with one env var
  (`MINTKEY_VAULT_BACKEND=azure`) while `postgres`/`sqlite`/`hashicorp` keep working unchanged.

- **US-3.** As an operator, I want a one-shot migration command
  (`make migrate-vault-to-azure`) that copies every credential from my current Postgres vault
  store into Azure Key Vault idempotently with a byte-equal sample verification.

- **US-4.** As a security owner, I want auth via `DefaultAzureCredential` (no static secret in
  the binary in production — managed identity) and I want any client secret used in CI to never
  be logged or placed in an OTel span attribute.

- **US-5.** As a developer, I want local dev/CI to run against a **mock** Key Vault HTTP server
  (no real Azure account needed) via an endpoint override, and integration tests to run against
  that mock with `httptest`.

---

## 3. Functional requirements

| ID | Requirement |
|----|-------------|
| **FR-1** | `store.NewFromEnv` MUST accept `MINTKEY_VAULT_BACKEND=azure` and return an `*AzureKeyVaultStore` satisfying the existing `store.Backend` interface (`Put`, `Get`, `Revoke`, `ListVersions`, `Close`). |
| **FR-2** | `azure` MUST be additive: `postgres` (default when unset), `sqlite`, `hashicorp`, and all existing error paths MUST behave exactly as today; the unknown-backend error MUST still fire for any other value. |
| **FR-3** | `Put(ctx, rec)` MUST assign the next `key_version` = `MAX(key_version)+1` per `(tenant_id, service_id)` (min 1), demote prior versions to `is_current=false`, write the new version `is_current=true, is_revoked=false`, and return the assigned `key_version` — semantics identical to `PostgresStore.Put`. |
| **FR-4** | `Get(ctx, tenantID, serviceID, keyVersion)` with `keyVersion==0` MUST return the `is_current=true` version; `keyVersion>0` MUST return that exact version regardless of `is_revoked`; no match MUST return a wrapped `sql.ErrNoRows` so `errors.Is(err, sql.ErrNoRows)` holds. |
| **FR-5** | `Revoke` MUST set `is_revoked=true` on a non-current version, return `store.ErrRevokeCurrent` for the current version, and wrapped `sql.ErrNoRows` for a missing version. |
| **FR-6** | `ListVersions` MUST return metadata-only records (`WrappedDEK`/`EncPayload` empty), ascending `key_version`, `key_version > afterKeyVersion`, `limit` clamped to 50 when 0 or > 200. |
| **FR-7** | Stored values MUST round-trip every field the SQLite backend persists: `credential_id, tenant_id, service_id, key_version, auth_scheme, wrapped_dek, enc_payload, is_current, is_revoked, created_at, target_url, header_name, query_param, target_address, ssh_user`. Postgres-JOIN-only fields stay empty/zero (same as SQLite). |
| **FR-8** | The backend MUST authenticate via `azidentity.NewDefaultAzureCredential`. The SDK token cache handles refresh; no custom renewal goroutine is required (contrast HashiCorp). |
| **FR-9** | Concurrent `Put` for the same `(tenant_id, service_id)` MUST NOT produce duplicate `key_version`s. Serialise via an in-process per-key mutex; Key Vault `If-Match`/ETag on the index secret is the second-line defence. |
| **FR-10** | A migration command `cmd/vault-migrate-pg-to-azure/` MUST copy every Postgres `vault.credentials` row to Azure Key Vault, be idempotent (skip existing), verify a 5-sample byte-equal round-trip, and assert the count. Invoked via `make migrate-vault-to-azure`. |
| **FR-11** | All new env vars MUST appear in `.env.example` with explanatory comments. |
| **FR-12** | `main.go`'s SSH-RPC wiring (`st.(*store.PostgresStore)`) MUST continue to compile and disable `SSHVaultAdapter` for the Azure backend (type assertion fails), exactly as for SQLite/HashiCorp. No edit to that block beyond what compiles. |
| **FR-13** | The Key Vault **endpoint MUST be overridable** (`MINTKEY_VAULT_AZURE_ENDPOINT`) so local dev/CI can point at a mock HTTP server instead of `https://<name>.vault.azure.net`. |

---

## 4. Non-functional requirements

| ID | Requirement |
|----|-------------|
| **NFR-1 (Security)** | Any Azure client secret (`AZURE_CLIENT_SECRET`, used only by the env-credential path in CI) MUST NEVER appear in any log, error message, or OTel span attribute (ADR-0017.6 allowlist forbids `*_secret`). Verified by a no-leak test. |
| **NFR-2 (Security)** | Plaintext credential bytes MUST NEVER reach Azure Key Vault — only KEK-wrapped `wrapped_dek` and DEK-encrypted `enc_payload`. The KEK stays local (`MINTKEY_VAULT_KEK_FILE`). |
| **NFR-3 (Availability)** | When Key Vault is unreachable/throttled (HTTP 429/5xx), `Get`/`Put` MUST return an error mapped to gRPC `UNAVAILABLE`, not a panic. |
| **NFR-4 (Performance)** | `Get` of current version MUST be ≤ 2 Key Vault reads (index secret + version secret); no full-vault enumeration on the hot path. Key Vault soft-delete/purge semantics MUST NOT break re-`Put` of a previously-revoked logical version (use distinct secret names per version — see design). |
| **NFR-5 (Compat)** | No Liquibase change, no SQLAlchemy change, no `vault.proto` change, no `CredentialRecord` change, no `init()` side effects. |
| **NFR-6 (Lint)** | New Go code MUST pass `go vet ./...` and `staticcheck ./...` with zero findings in the `vault-adapter` module. |

---

## 5. Out of scope (explicit)

- Azure Key Vault **Keys** (RSA/EC crypto operations) and **Managed HSM** — we keep our KEK/DEK envelope.
- Azure Key Vault **Certificates**.
- Making Azure the **default** backend — opt-in only; Postgres stays default.
- Removing/deprecating Postgres, SQLite, or HashiCorp backends.
- SSH RPC support on the Azure backend (`SSHVaultAdapter` stays Postgres-only).
- Direct SQLite→Azure migration (go SQLite→Postgres→Azure; documented, not coded).
- Multi-region replication / geo-failover of the Key Vault (operator-configured at the Azure tier).
- Per-tenant Key Vaults / per-tenant identities. One vault; app-layer tenant scoping via secret
  name prefix. RLS is a Postgres concept and does not transfer.
- Hardening against Key Vault soft-delete name collisions beyond the per-version-distinct-name
  scheme in design §wire-level (purge-protection edge cases are an operator runbook note).

---

## 6. Acceptance criteria (mechanically verifiable by Sonnet)

1. **AC-1 (selector):** `go test ./internal/store/ -run TestNewFromEnv_Azure` passes — asserts
   `MINTKEY_VAULT_BACKEND=azure` returns an `*AzureKeyVaultStore` (or the documented
   missing-config error when the endpoint/vault name is absent). Exit 0.
2. **AC-2 (regression):** `go test ./internal/store/ -run TestNewFromEnv` passes — all existing
   selector tests (`DefaultsToPostgres`, `Sqlite`, `PostgresMissingDSN`, `UnknownBackend`) plus
   any HashiCorp ones remain green.
3. **AC-3 (conformance):** `go test ./internal/store/ -run TestAzure` passes against the mock
   Key Vault HTTP server (`httptest`) — Put→Get(0)→Get(N)→Revoke→ListVersions; monotonic
   versions; current flip; `ErrRevokeCurrent`; not-found → `errors.Is(sql.ErrNoRows)`.
4. **AC-4 (round-trip):** a test seals a random payload via `crypto.Seal`, `Put`s, `Get`s, and
   asserts `bytes.Equal` on `WrappedDEK`/`EncPayload` and equality on every persisted scalar.
5. **AC-5 (no-leak):** `go test ./internal/store/ -run TestAzure_SecretNotLogged` passes — runs a
   `Get` with a configured client secret and asserts the secret substring is absent from captured
   logs.
6. **AC-6 (migration):** `go test ./cmd/vault-migrate-pg-to-azure/` passes — seeds Postgres,
   migrates to the mock Key Vault, asserts read==inserted, 5-sample byte-equal PASS, and a second
   run reports all skipped (idempotency).
7. **AC-7 (lint):** `go vet ./...` and `staticcheck ./...` in `apps/vault-adapter` exit 0.
8. **AC-8 (env doc):** every env var named in design §Env vars is present in `.env.example`.
9. **AC-9 (compose):** `docker compose -f infra/compose/docker-compose.yml config` succeeds with
   the optional `azure-keyvault-mock` service present (dev/CI only).
