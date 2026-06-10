# Design — External Secret Providers (Phase 2)

## Context

ADR-0025 (D9) explicitly deferred external provider backends to phase 2. Phase 1 shipped with a `PostgresStore` implementing the `AgentSecretStore` interface (`apps/vault-adapter/internal/store/agent_secret.go`) with three methods: `PutAgentSecret`, `GetAgentSecret`, `DeleteAgentSecret`. The gRPC service `AgentSecretsVault` wires those methods into the vault-adapter; the MCP server is the only caller.

The task is to slot two new implementations behind `AgentSecretStore` without touching the gRPC surface, the MCP tools, or any wire contracts. The precedent for pluggable backends is `MINTKEY_VAULT_BACKEND={postgres|sqlite}` (ADR-0021).

Constraints:
- The `AgentSecretStore` interface boundary is frozen for this phase — no method additions.
- Mintkey's envelope encryption (AES-256-GCM DEK + KEK) is preserved regardless of backend. External providers supply additional at-rest encryption (defence in depth). Removing Mintkey-side encryption would require ADR-0025 amendment and a migration of all existing secrets.
- Agent-facing wire contract (MCP tools) is unchanged — this is a purely internal implementation swap.
- The per-tenant backend model is deferred (see D1 below).

---

## Goals / Non-Goals

**Goals:**
- Two new `AgentSecretStore` implementations: `hashicorp-vault` and `azure-key-vault`.
- Backend selection via single env var; zero-change for existing Postgres deployments.
- Conformance test suite all backends must pass (the primary correctness gate).
- Migration tooling: Postgres → HashiCorp Vault, Postgres → Azure Key Vault.
- Provider outage fails closed with an operator-distinguishable error.
- `GET /v1/health/agent-secret-backend` for deployment tooling.

**Non-Goals:**
- Per-tenant backend configuration stored in the DB (deferred — see D1).
- Version history reads (KV v2 versioned get, Azure KV version listing) — phase 1 overwrites in place; phase 3 if needed.
- Agent-to-agent sharing without operator involvement (ADR-0025 open follow-up).
- Reverse migration (external backend → Postgres).
- Removing Mintkey-side envelope encryption when using an external provider.
- New MCP tools or new agent-facing REST endpoints.

---

## Decisions

**D1 — Per-deployment env var, not per-tenant DB config.**

Two models exist:
- *Per-deployment*: `MINTKEY_AGENT_SECRET_BACKEND` env var; one backend per vault-adapter instance; operators control it via docker compose / Kubernetes manifests; zero DB changes.
- *Per-tenant*: an `agent_secret_backend_config` table lets each tenant select a different provider; backend becomes a runtime lookup per request; requires DB schema, admin API endpoints, UI.

For the first cut, per-deployment wins on Simplicity First grounds:
1. The stated use-case ("operator-configured external secret provider") is a deployment-level policy decision, not a per-tenant one. Operators already differentiate deployments (e.g. separate compose stacks per compliance boundary).
2. Zero DB schema change: no new Liquibase changelog, no RLS policy, no SQLAlchemy mirror update.
3. Eliminates a whole class of security questions (can tenants mix backends? what happens if a tenant's config row is missing?).
4. Per-tenant config requires ADR-0026 to weigh in on: multi-backend key namespace collisions, cross-backend migration complexity, and the admin API surface for secret provider credentials — all non-trivial. Deferring avoids encoding a premature decision.

Per-tenant config is listed as a follow-up in ADR-0026.

**D2 — Preserve Mintkey envelope encryption at all backends.**

One could argue: "HashiCorp Vault and Azure Key Vault already encrypt at rest — skip Mintkey's AES-256-GCM layer to save CPU."

Rejected:
1. ADR-0025 defines the ciphertext as the stored artefact. Changing this requires all existing phase-1 secrets to be re-stored as plaintext — a migration with a plaintext-in-transit window.
2. Defence in depth: the vault-adapter process's KEK is the only entity that can decrypt secrets; the Vault/AKV admin has encrypted blobs, not plaintext. This is an explicitly desired property.
3. CPU cost of AES-256-GCM on ≤ 64 KiB payloads is ~1 µs — not measurable in context.

Implementation note: the packed blob written to an external provider is `len(wrapped_dek) || wrapped_dek || enc_payload` encoded as base64. The exact same `crypto.Seal/Open` call path used by `PostgresStore` is reused. The only difference is *where* the bytes land.

**D3 — HashiCorp Vault KV v2 path convention.**

Secret path: `{mount}/{tenant_id}/{secret_id}`. This makes cross-tenant enumeration via Vault's `LIST` API impossible without knowing a valid `tenant_id` prefix. Vault `LIST` on `{mount}/` would return top-level keys (tenant IDs); this is acceptable because `tenant_id` values are ULIDs, not human-readable names, and LIST access can be restricted by Vault policy.

Alternative considered: `{mount}/mintkey/{secret_id}` (flat). Rejected: no tenant isolation at the Vault ACL level; two different Mintkey tenants' secrets are indistinguishable to a Vault admin with mount-level read access.

API calls (verified against HashiCorp Vault API docs, KV v2, as of 2026-06):
- Write: `POST /v1/{mount}/data/{tenant_id}/{secret_id}` — body `{"data":{"wrapped_dek":"<b64>","enc_payload":"<b64>","key_version":<int>}}`
- Read: `GET /v1/{mount}/data/{tenant_id}/{secret_id}` — returns `data.data.{wrapped_dek,enc_payload,key_version}`
- Hard-destroy latest: `DELETE /v1/{mount}/data/{tenant_id}/{secret_id}` (soft-delete) then `PUT /v1/{mount}/destroy/{tenant_id}/{secret_id}` with `{"versions":[<N>]}` (Vault accepts POST and PUT interchangeably on write endpoints; PUT is the doc-canonical verb) — ensures the secret cannot be recovered via KV v2 undelete.

Token header: `X-Vault-Token: {token}`. Enterprise namespace header: `X-Vault-Namespace: {namespace}`. Both documented in HashiCorp Vault API reference.

**D4 — HashiCorp Vault auth: token or AppRole; Mintkey does NOT manage Vault token lifecycle in token mode.**

Token mode is a deliberate escape hatch for operators who already manage Vault tokens via external tooling (vault-agent, Kubernetes ServiceAccount JWT auth, etc.). The static token is passed as-is; Mintkey does not attempt renewal. If the token expires, the next store operation fails with a provider error.

AppRole mode is the recommended production path. At startup, Mintkey calls `POST /v1/auth/approle/login` with `role_id` + `secret_id` (both from env vars). The returned `auth.client_token` has a TTL (`lease_duration` field). A background goroutine attempts `POST /v1/auth/token/renew-self` when TTL remaining < 60 s. If renew fails (non-renewable token policy), the adapter re-logins. The `role_id` and `secret_id` themselves are bootstrap credentials — they must be provided to vault-adapter by the deployment operator (Kubernetes Secret, CI pipeline secret injection, vault-agent sidecar). This is the standard chicken-and-egg resolution for AppRole: the broker app (Mintkey) holds AppRole credentials, not Vault tokens.

**D5 — Azure Key Vault secret name encoding.**

Azure Key Vault secret names are 1-127 chars, MUST start with a letter, and may contain only `0-9a-zA-Z-`. The `mk-` encoding prefix guarantees the leading-letter rule; the encoder's unit tests must assert every encoded name begins with `mk-` so this cannot regress. Mintkey `sec_` IDs are Crockford Base32 (uppercase), and tenant IDs are `tenant_` prefix + Crockford Base32 — both contain uppercase letters and the underscore character. Underscore is not in Azure KV's allowed charset.

Resolution: encode the Azure KV secret name as `mk-{8-char-tenant-prefix}-{secret_id_body}` where `secret_id_body` is the 26-char Crockford body of the `sec_` ULID (digits + uppercase letters, no underscore). The 8-char tenant prefix is enough to differentiate tenants in a single-tenant deployment; for multi-tenant per-deployment scenarios the full tenant ULID is stored in the `tags.mintkey_tenant` field and verified on read, providing the authoritative isolation check.

Maximum name length: `mk-` (3) + 8 + `-` (1) + 26 = 38 chars. Well within the 127-char limit.

**D6 — Encryption model: always double-encrypt; external provider is ciphertext store only.**

See D2. The blob layout is: `4 bytes big-endian DEK length | wrapped_dek bytes | enc_payload bytes`, base64url-encoded for HashiCorp Vault (`"data"` fields) and Azure KV (`"value"` field). The `key_version` integer is stored as a metadata tag/field alongside the blob so the adapter can select the correct KEK for unwrapping.

**D7 — Provider outage: fail closed, operator-distinguishable error.**

When the backend is unreachable (TCP timeout, DNS failure, HTTP 5xx), the store method returns a non-nil error that is NOT `ErrAgentSecretNotFound`. The gRPC service layer maps this to `codes.Unavailable`. The MCP tool layer maps `Unavailable` to a generic internal-error MCP response (no provider-specific language in the agent-facing message).

At the vault-adapter structured log level, a field `error.kind=provider_outage` distinguishes provider errors from `not_found` (`error.kind=not_found`). OTel spans on the store methods carry `error.kind` as an attribute; this is within the existing allowlist (`error.kind` does not match any of the `*_token`, `*_secret`, `*_password`, `*_passphrase`, `Authorization`, `Cookie` patterns from ADR-0017.6).

**D8 — Conformance suite structure.**

The conformance suite lives at `apps/vault-adapter/internal/store/conformance/suite.go`. It exports a single function `RunSuite(t testing.TB, newStore func() store.AgentSecretStore, teardown func())`. Each backend test file calls `RunSuite` with a constructor for its backend. The suite exercises: put→get round-trip, overwrite, delete idempotency, not-found behaviour, cross-tenant isolation, and byte equality of blob content.

The suite is the normative contract. If a backend passes `RunSuite`, it is considered correctly implemented. Backend-specific tests (e.g. token renewal logic, Azure KV name encoding) are additive.

**D9 — No new gRPC methods; no new MCP tools; no wire-contract changes.**

The `AgentSecretsVault` gRPC service, the four MCP tools, the openapi.yaml (agent-facing paths), and the audit-event schema are untouched. The only additions are:
1. `GET /v1/health/agent-secret-backend` in admin-api (operator tooling; not agent-facing).
2. New env vars documented in HOW-TO.md.
3. The migration binary (`apps/vault-adapter/cmd/migrate-agent-secrets/`).

No new ADR-0025 entries or amends; ADR-0026 is new and covers the decisions in this design.

**D10 — Azure Key Vault local emulator strategy.**

Azure Key Vault has no Microsoft-published local emulator. Options evaluated:
- **Lowkey Vault** (`nagyesta/lowkey-vault`): Most complete community emulator; supports secrets CRUD; Docker image available; actively maintained (2026 releases noted on GitHub). Recommended for integration tests.
- **james-gould/azure-keyvault-emulator**: .NET/Aspire-oriented; limited secrets coverage.
- **Contract mock** (httptest server in Go): Maximum control, zero external dependency, but requires manual implementation of response shapes. Appropriate for unit tests of the adapter's HTTP client logic.

Recommendation: use Lowkey Vault for the conformance suite integration tests (tagged `//go:build integration`); use an `httptest` contract mock for unit tests of retry/backoff/name-encoding logic.

---

## Risks / Trade-offs

- **[Provider authentication credentials are outside Mintkey's control]** → Documented in HOW-TO.md; the operator is responsible for rotating and distributing AppRole `secret_id` / Azure Client Secret. Mintkey cannot audit what it doesn't manage.
- **[HashiCorp Vault KV v2 soft-delete window]** → The adapter performs soft-delete then hard-destroy in sequence for delete operations. If the process crashes between the two calls, the soft-deleted secret is recoverable via Vault for up to the configured retention window. Mitigation: `DeleteAgentSecret` is idempotent; the next call will re-issue the destroy. This is an acceptable transient state.
- **[Azure Key Vault rate limit: 4,000 GET/SET per 10 s per vault]** → At expected Mintkey agent secret rates (secrets are read infrequently, typically at agent startup), this limit is not a concern. If Mintkey becomes a high-throughput secret reader, ADR-0026 should be revisited to add caching. Caching plaintext KEK-decrypted secrets in memory would violate ADR-0025 D2 (plaintext in RAM has a different threat profile from plaintext in logs — this is an acceptable trade-off at operator discretion; deferred).
- **[No dual-read transition window for migration]** → Secrets written after cutover to an external backend but before a hypothetical rollback are in the external backend only. Documented prominently in migration tool `--help` and HOW-TO.md. Operators must plan migration windows accordingly.
- **[Lowkey Vault is a community project]** → If it falls behind the Azure KV API, integration tests may give false confidence. Mitigation: the tests are tagged `//go:build integration`; CI runs them in the PR gate but they can be disabled if the emulator diverges. The contract mock remains the primary unit test vehicle.
- **[Double-encryption CPU overhead]** → Negligible for ≤ 64 KiB payloads (~1 µs AES-GCM). No mitigation needed.

---

## Migration Plan

See `backend-migration` spec for normative requirements. Summary:

1. Operator runs `make backup` (mandatory pre-flight; standard runbook from ADR-0021).
2. Operator runs `make migrate-agent-secrets-pg-to-hv` or `make migrate-agent-secrets-pg-to-akv`.
3. Migration tool reads every row from `vault.agent_secrets`, writes to target backend. Skip-on-conflict (idempotent). After all rows written, reads back 5 random rows and asserts byte equality.
4. Operator sets `MINTKEY_AGENT_SECRET_BACKEND` in compose env and restarts vault-adapter.
5. Verify: vault-adapter startup log shows `agent_secret_backend=hashicorp-vault` (or `azure-key-vault`).
6. Rollback: set `MINTKEY_AGENT_SECRET_BACKEND=postgres` (or unset), restart. Postgres rows are still present.

---

## Open Questions

- **OQ-EXT-1**: Per-tenant backend config — when is it needed? Track operator demand before designing the DB model. Likely needs a new ADR when the demand materialises.
- **OQ-EXT-2**: Should the migration tool support *incremental* migration (only rows newer than a given timestamp) for large tenants? Not needed now but the binary's design should not preclude it.
- **OQ-EXT-3**: If an operator wants to use two different Azure Key Vaults for two different compliance zones within one Mintkey deployment — is that a per-tenant-config driver? Probably yes. Track under OQ-EXT-1.
- **OQ-EXT-4**: Azure Key Vault soft-delete retention is 7–90 days. Should Mintkey expose a configurable `MINTKEY_AKV_SOFT_DELETE_RETENTION_DAYS` that the operator also configures on the vault, to be checked at startup? Currently out of scope but worth a follow-up.
