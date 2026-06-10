# Tasks — External Secret Providers (Phase 2)

## 1. Conformance Suite (implement first — gates all backends)

- [ ] 1.1 Create `apps/vault-adapter/internal/store/conformance/suite.go` exporting `RunSuite(t testing.TB, newStore func() AgentSecretStore, teardown func())` with test cases: put→get round-trip, overwrite, delete idempotency, not-found sentinel, cross-tenant isolation, byte-equality of blob. All cases use table-driven style; no external dependencies.
- [ ] 1.2 Wire `RunSuite` into the existing Postgres store test (`apps/vault-adapter/internal/store/agent_secret_test.go`); ensure `//go:build postgres` tests pass: `go test -tags postgres ./internal/store/... -run TestAgentSecretConformance`
- [ ] 1.3 Capture test output and exit code; "conformance suite passes on Postgres" is the acceptance check for 1.1–1.2

## 2. HashiCorp Vault KV v2 Backend

- [ ] 2.1 Create `apps/vault-adapter/internal/store/hashicorp_vault.go`: `HashicorpVaultStore` struct implementing `AgentSecretStore`; path convention `{mount}/{tenant_id}/{secret_id}`; blob layout `4-byte DEK-len | wrapped_dek | enc_payload` base64url-encoded into `data.wrapped_dek` + `data.enc_payload` fields; `key_version` as integer field in the KV v2 `data` object
- [ ] 2.2 Implement `PutAgentSecret` — `POST /v1/{mount}/data/{tid}/{sid}` with correct Content-Type; map HTTP 200/204 to nil error; map non-2xx to typed errors
- [ ] 2.3 Implement `GetAgentSecret` — `GET /v1/{mount}/data/{tid}/{sid}`; parse `data.data`; map HTTP 404 to `ErrAgentSecretNotFound`; map non-2xx to typed errors
- [ ] 2.4 Implement `DeleteAgentSecret` — soft-delete `DELETE /v1/{mount}/data/{tid}/{sid}` then hard-destroy `POST /v1/{mount}/destroy/{tid}/{sid}` with `{"versions":[N]}`; idempotent (404 on either call is not an error)
- [ ] 2.5 Implement token auth path: `X-Vault-Token` header from `MINTKEY_HV_TOKEN`; optional `X-Vault-Namespace` from `MINTKEY_HV_NAMESPACE`
- [ ] 2.6 Implement AppRole auth path: `POST /v1/auth/approle/login` at startup; background goroutine for renewal (TTL < 60 s → `POST /v1/auth/token/renew-self`; if non-renewable → re-login); thread-safe token access with `sync.RWMutex`
- [ ] 2.7 Implement `error.kind=provider_outage` structured log field for all non-`ErrAgentSecretNotFound` errors; ensure the error does not propagate credential values
- [ ] 2.8 Create `apps/vault-adapter/internal/store/hashicorp_vault_test.go` with: unit tests using `httptest.NewTLSServer` mocking Vault responses (name-encoding, token header, namespace header, retry on re-login); conformance suite integration tests tagged `//go:build integration` using `docker run --rm -d -e VAULT_DEV_ROOT_TOKEN_ID=root -p 8200:8200 vault:1.17 server -dev`
- [ ] 2.9 `go test -short ./internal/store/...` green (unit tests only); `go test -tags integration ./internal/store/...` green (requires Vault dev container running)

## 3. Azure Key Vault Backend

- [ ] 3.1 Create `apps/vault-adapter/internal/store/azure_key_vault.go`: `AzureKeyVaultStore` struct implementing `AgentSecretStore`; secret name encoding `mk-{8-char-tenant-prefix}-{secret_id_body}` (strip `sec_` prefix, take Crockford body); blob stored as base64url in AKV `value` field; `key_version` and full `tenant_id` in AKV `tags`
- [ ] 3.2 Implement `PutAgentSecret` — `PUT {vaultUri}/secrets/{name}?api-version=2025-07-01` with `{"value":"<b64>","contentType":"application/octet-stream","tags":{"mintkey_tenant":"{tid}","mintkey_key_version":"{kv}"}}`; map HTTP 200 to nil error; map non-2xx to typed errors
- [ ] 3.3 Implement `GetAgentSecret` — `GET {vaultUri}/secrets/{name}?api-version=2025-07-01`; decode `value`; verify `tags.mintkey_tenant == tid` (mismatch → `ErrAgentSecretNotFound`); map HTTP 404 to `ErrAgentSecretNotFound`
- [ ] 3.4 Implement `DeleteAgentSecret` — soft-delete `DELETE {vaultUri}/secrets/{name}?api-version=2025-07-01`; if `MINTKEY_AKV_PURGE_ON_DELETE=true`, follow with purge `DELETE {vaultUri}/deletedsecrets/{name}?api-version=2025-07-01`; idempotent (404 is not an error)
- [ ] 3.5 Implement HTTP 429 backoff: parse `Retry-After` header (seconds); exponential backoff with jitter for retries without `Retry-After`; max 3 retries before returning provider error
- [ ] 3.6 Implement `azidentity.NewDefaultAzureCredential()` authentication; scope `https://vault.azure.net/.default`; token refresh handled by the SDK
- [ ] 3.7 Implement `error.kind=provider_outage` structured log field (same pattern as HashiCorp Vault backend)
- [ ] 3.8 Create `apps/vault-adapter/internal/store/azure_key_vault_test.go` with: unit tests using `httptest.NewTLSServer` mocking Azure KV responses (name encoding, tenant tag verification, 429 retry, purge-on-delete toggle); conformance suite integration tests tagged `//go:build integration` using Lowkey Vault container (`docker run --rm -d -p 8443:8443 nagyesta/lowkey-vault:latest`)
- [ ] 3.9 `go test -short ./internal/store/...` green; `go test -tags integration ./internal/store/...` green (requires Lowkey Vault container)

## 4. Backend Selector and Startup Validation

- [ ] 4.1 Update `apps/vault-adapter/cmd/vault-adapter/main.go`: read `MINTKEY_AGENT_SECRET_BACKEND`; validate known values (`postgres`, `hashicorp-vault`, `azure-key-vault`), exit non-zero on unknown; construct the correct `AgentSecretStore` implementation and pass it to `AgentSecretsVaultServer`
- [ ] 4.2 Implement startup validation for each backend: HashiCorp Vault — require `MINTKEY_HV_ADDR`; if `AUTH_METHOD=approle` require `MINTKEY_HV_ROLE_ID` and `MINTKEY_HV_SECRET_ID`; exit non-zero with a clear message if missing. Azure KV — require `MINTKEY_AKV_VAULT_URI`; exit non-zero if missing.
- [ ] 4.3 Log `agent_secret_backend={name}` at `INFO` level on startup so operators can confirm which backend is active
- [ ] 4.4 Unit test: startup validation returns correct errors for each missing mandatory env var; `go test -short ./cmd/vault-adapter/...` green

## 5. Health Endpoint

- [ ] 5.1 Add `GET /v1/health/agent-secret-backend` handler to admin-api (`apps/admin-api/src/admin_api/api/health.py` or a new `health_backend.py` router); calls a no-op probe on the current backend store (Postgres: `SELECT 1`; HashiCorp Vault: `GET /v1/sys/health`; Azure KV: `GET {vaultUri}/secrets?api-version=2025-07-01&maxresults=1`); returns `{"backend":"<name>","status":"ok"}` on 200 or `{"backend":"<name>","status":"error","message":"<opaque>"}` on 503; message MUST NOT contain env var values
- [ ] 5.2 Register the health router in `apps/admin-api/src/admin_api/main.py`
- [ ] 5.3 Unit test `apps/admin-api/tests/unit/admin_api/test_health_backend.py`: ok path (mock backend returns immediately), error path (mock raises), message contains no credential material

## 6. Migration Tooling

- [ ] 6.1 Create `apps/vault-adapter/cmd/migrate-agent-secrets/main.go`: CLI flags `--source postgres --target {hashicorp-vault|azure-key-vault}`, `--dry-run`; reads `vault.agent_secrets` from Postgres (all rows across all tenants); writes each to target backend using the target `AgentSecretStore.PutAgentSecret`; skip-on-conflict (catch and count); after all writes, sample 5 random rows from both stores and assert byte equality; print summary; `--help` prominently documents the rollback gap
- [ ] 6.2 Add `Makefile` targets: `migrate-agent-secrets-pg-to-hv` and `migrate-agent-secrets-pg-to-akv` (each set appropriate env vars and run the migration binary)
- [ ] 6.3 Add migration tool binary to the vault-adapter Docker image (or as a separate `migrate` image target in `apps/vault-adapter/Dockerfile`)
- [ ] 6.4 Unit test `migrate_test.go`: dry-run mode produces no writes; idempotent run skips existing secrets; byte-equality mismatch causes exit non-zero; `go test -short ./cmd/migrate-agent-secrets/...` green

## 7. Documentation and Configuration

- [ ] 7.1 Update `docker-compose.yml`: add commented-out env var blocks for `MINTKEY_HV_*` and `MINTKEY_AKV_*` under the `vault-adapter` service; add a comment referencing HOW-TO.md §External Secret Providers
- [ ] 7.2 Add `docs/HOW-TO.md §7 External Secret Providers`: subsections for HashiCorp Vault (token setup, AppRole setup, namespace config, Vault Enterprise notes, migration steps) and Azure Key Vault (Managed Identity, Client Secret, Lowkey Vault for local dev, migration steps, soft-delete/purge semantics, rate-limit guidance)
- [ ] 7.3 Add `MINTKEY_AGENT_SECRET_BACKEND` to the `CLAUDE.md` guardrails table (the `MINTKEY_VAULT_BACKEND` row is the precedent)

## 8. CI and Final Verification

- [ ] 8.1 Add CI job `agent-secret-backend-conformance` that runs `go test -tags postgres,integration ./...` in vault-adapter with Vault dev server and Lowkey Vault containers started via `docker compose -f docker-compose.test.yml up -d vault-dev lowkey-vault`; publish test output as CI artifact
- [ ] 8.2 Run full suite: `make test` (unit + arch), `go test ./... -short` (fast Go tests), conformance suite with each backend (tagged), migration dry-run smoke test — all green with exit codes captured
- [ ] 8.3 PR: intake stub in PR body, CI green, independent reviewer findings addressed, merge
