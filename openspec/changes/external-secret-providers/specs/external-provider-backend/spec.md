# External Provider Backend

## ADDED Requirements

### Requirement: All backends satisfy the AgentSecretStore conformance suite

A shared Go test package (`apps/vault-adapter/internal/store/conformance`) SHALL define the canonical behavioural contract for `AgentSecretStore`. Every backend implementation (Postgres, HashiCorp Vault, Azure Key Vault) MUST pass the full conformance suite before it is eligible to merge. The suite is the single arbiter of parity; backend-specific unit tests MAY add coverage but MUST NOT weaken conformance requirements.

#### Scenario: Conformance suite runs against Postgres backend
- **WHEN** the conformance suite is executed with a Postgres-backed store (requires `MINTKEY_TEST_PG_APP_DSN` env var, `//go:build postgres` tag)
- **THEN** all conformance tests pass and `go test` exits 0

#### Scenario: Conformance suite runs against HashiCorp Vault backend
- **WHEN** the conformance suite is executed with a HashiCorp Vault dev-server container (started via `docker run -e VAULT_DEV_ROOT_TOKEN_ID=root vault:1.17 server -dev`) and `MINTKEY_TEST_HV_ADDR` + `MINTKEY_TEST_HV_TOKEN` set
- **THEN** all conformance tests pass and `go test` exits 0

#### Scenario: Conformance suite runs against Azure Key Vault backend
- **WHEN** the conformance suite is executed with a Lowkey Vault container (image: `nagyesta/lowkey-vault`, listening on `https://localhost:8443`) and `MINTKEY_TEST_AKV_VAULT_URI=https://localhost:8443` set
- **THEN** all conformance tests pass and `go test` exits 0

#### Scenario: Conformance test — put then get returns same ciphertext record
- **WHEN** a `PutAgentSecret` call is made with a given `(tenant_id, secret_id, enc_payload)` and then `GetAgentSecret` is called with the same keys
- **THEN** the returned `AgentSecretRecord` has identical `WrappedDEK`, `EncPayload`, and `KeyVersion` fields to what was put

#### Scenario: Conformance test — get of absent key returns ErrAgentSecretNotFound
- **WHEN** `GetAgentSecret` is called for a `(tenant_id, secret_id)` that was never stored
- **THEN** the error wraps `store.ErrAgentSecretNotFound`

#### Scenario: Conformance test — delete is idempotent
- **WHEN** `DeleteAgentSecret` is called twice for the same `(tenant_id, secret_id)`, the second time after the row no longer exists
- **THEN** both calls return nil error

#### Scenario: Conformance test — put overwrites existing record
- **WHEN** `PutAgentSecret` is called for the same `(tenant_id, secret_id)` with a different `enc_payload`
- **THEN** `GetAgentSecret` returns the second payload, not the first

#### Scenario: Conformance test — tenant isolation (cross-tenant get returns not-found)
- **WHEN** a secret is stored under `tenant_id = A` and `GetAgentSecret` is called with `tenant_id = B` and the same `secret_id`
- **THEN** the error wraps `store.ErrAgentSecretNotFound`

---

### Requirement: HashiCorp Vault KV v2 backend is a valid AgentSecretStore

The `hashicorp-vault` backend SHALL implement `AgentSecretStore` by storing encrypted blobs in a HashiCorp Vault KV v2 mount. Mintkey MUST continue to envelope-encrypt the payload before writing (Mintkey's AES-256-GCM DEK + KEK); the blob written to Vault is ciphertext, not plaintext. Vault provides an additional encryption layer at rest (Vault's own storage backend encryption); this double-encryption is intentional (defence in depth; the Vault operator cannot read Mintkey agent secret values even with full Vault admin access).

The backend MUST map `AgentSecretStore` calls to Vault KV v2 API calls as follows:

| Store method | Vault API call |
|---|---|
| `PutAgentSecret(rec)` | `POST /v1/{mount}/data/{tenant_id}/{secret_id}` with body `{"data":{"wrapped_dek":"<base64>","enc_payload":"<base64>","key_version":<int>}}` |
| `GetAgentSecret(tid, sid)` | `GET /v1/{mount}/data/{tenant_id}/{secret_id}` (latest version) |
| `DeleteAgentSecret(tid, sid)` | `DELETE /v1/{mount}/data/{tenant_id}/{secret_id}` (soft-delete latest) followed by `POST /v1/{mount}/destroy/{tenant_id}/{secret_id}` with `{"versions":[<latest>]}` to hard-destroy the version |

The path convention `{mount}/{tenant_id}/{secret_id}` provides per-tenant prefix isolation within a single KV mount; cross-tenant isolation in the absence of Vault namespaces is enforced by Mintkey's own `tenant_id` keying (the Vault path itself encodes the tenant).

The backend MUST support Vault Enterprise namespaces: when `MINTKEY_HV_NAMESPACE` is set, include the `X-Vault-Namespace: {namespace}` header on every request.

#### Scenario: Put and get round-trip through KV v2
- **WHEN** `PutAgentSecret` is called and then `GetAgentSecret` is called
- **THEN** the data fields in `GET /v1/{mount}/data/{tid}/{sid}` response match what was written and are returned correctly by the store

#### Scenario: Namespace header is forwarded on all requests
- **WHEN** `MINTKEY_HV_NAMESPACE=admin/mintkey` is set and any store method is called
- **THEN** every HTTP request to Vault includes `X-Vault-Namespace: admin/mintkey`

#### Scenario: Vault 404 maps to ErrAgentSecretNotFound
- **WHEN** Vault returns HTTP 404 for `GetAgentSecret`
- **THEN** the store returns an error wrapping `store.ErrAgentSecretNotFound`

---

### Requirement: HashiCorp Vault backend authenticates via token or AppRole

The `hashicorp-vault` backend SHALL support two auth methods, selected by the `MINTKEY_HV_AUTH_METHOD` env var:

- `token` (default): static `MINTKEY_HV_TOKEN` is used directly as the `X-Vault-Token` header on every request. Suitable for dev environments. The operator is responsible for token renewal; Mintkey does NOT manage token lifecycle in this mode.
- `approle`: Mintkey calls `POST /v1/auth/approle/login` with `{"role_id": "$MINTKEY_HV_ROLE_ID", "secret_id": "$MINTKEY_HV_SECRET_ID"}` at startup to obtain a `auth.client_token`; uses it for subsequent requests. The adapter MUST renew the token before expiry (when `auth.lease_duration - buffer < 0`; buffer = 60 s). The AppRole `role_id` and `secret_id` are themselves bootstrap credentials — they are loaded from env vars at startup and are NOT stored in Mintkey's own database; the chicken-and-egg is resolved by the deployment operator (Kubernetes Secret, CI secret, or a separate vault-agent sidecar injector).

#### Scenario: Token auth — requests use X-Vault-Token header
- **WHEN** `MINTKEY_HV_AUTH_METHOD=token` and `MINTKEY_HV_TOKEN=my-token` are set
- **THEN** every request to Vault includes `X-Vault-Token: my-token`

#### Scenario: AppRole auth — login call fires at startup and token is used
- **WHEN** `MINTKEY_HV_AUTH_METHOD=approle` with valid `MINTKEY_HV_ROLE_ID` and `MINTKEY_HV_SECRET_ID` are set
- **THEN** at startup `POST /v1/auth/approle/login` is called exactly once, and subsequent store requests use the resulting `auth.client_token` as `X-Vault-Token`

#### Scenario: AppRole token renewal before expiry
- **WHEN** the remaining TTL of the AppRole token drops below 60 seconds
- **THEN** the adapter calls `POST /v1/auth/token/renew-self` (or re-logins if the token is not renewable) before the next store operation

---

### Requirement: Azure Key Vault backend is a valid AgentSecretStore

The `azure-key-vault` backend SHALL implement `AgentSecretStore` by storing encrypted blobs in an Azure Key Vault instance. As with the HashiCorp Vault backend, Mintkey MUST continue to envelope-encrypt before writing; Azure Key Vault receives ciphertext only. Azure Key Vault provides additional encryption at rest; this is intentional double-encryption (defence in depth; the Azure Key Vault administrator cannot read Mintkey agent secret values).

The backend MUST map `AgentSecretStore` calls to Azure Key Vault REST API calls as follows:

| Store method | Azure KV API call |
|---|---|
| `PutAgentSecret(rec)` | `PUT {vaultUri}/secrets/{secretName}?api-version=2025-07-01` with body `{"value":"<base64-blob>","contentType":"application/octet-stream","tags":{"mintkey_tenant":"{tenant_id}","mintkey_key_version":"{key_version}"}}` |
| `GetAgentSecret(tid, sid)` | `GET {vaultUri}/secrets/{secretName}?api-version=2025-07-01` (latest version); verify `tags.mintkey_tenant == tid` to enforce tenant isolation |
| `DeleteAgentSecret(tid, sid)` | `DELETE {vaultUri}/secrets/{secretName}?api-version=2025-07-01` (soft delete); if vault has purge-protection disabled, optionally follow with `DELETE {vaultUri}/deletedsecrets/{secretName}?api-version=2025-07-01` (purge). The adapter MUST NOT hard-purge when purge-protection is enabled. |

The `secretName` in Azure Key Vault MUST be derived as `mk-{short_tenant_id}-{secret_id}` where `short_tenant_id` is the first 8 characters of the tenant ULID body (to satisfy Azure KV's `^[0-9a-zA-Z-]+$` name constraint). The `tags.mintkey_tenant` tag carries the full tenant ULID for verification.

Azure Key Vault secrets rate limits (2025-07-01 API): GET/SET/DELETE transactions share a limit of 4,000 per 10 seconds per vault (GET/SET/LIST), with CREATE secret limited to 300 per 10 seconds (collectively across secret create, certificate import, key import). Note: `PutAgentSecret` performs a SET on a (usually new) secret name, which counts against the 300/10s CREATE bucket — not the 4,000/10s read bucket — so the backoff requirement matters most on write bursts such as migration. The adapter MUST honour HTTP 429 responses with exponential backoff, using the `Retry-After` response header when present.

#### Scenario: Put encodes blob as base64 with tenant tag
- **WHEN** `PutAgentSecret` is called with tenant `A` and some `enc_payload`
- **THEN** the Azure KV `PUT` request body contains `value` equal to the base64-encoded packed blob and `tags.mintkey_tenant` equal to tenant `A`'s ULID

#### Scenario: Get verifies tenant tag before returning
- **WHEN** `GetAgentSecret` is called for `(tenant_id=A, secret_id=X)` but the Azure KV secret's `tags.mintkey_tenant` is `B`
- **THEN** the store returns an error wrapping `store.ErrAgentSecretNotFound` (tenant mismatch treated as not-found)

#### Scenario: HTTP 429 from Azure KV triggers exponential backoff
- **WHEN** Azure KV returns HTTP 429 with a `Retry-After: 2` header
- **THEN** the adapter waits at least 2 seconds before retrying; the retry eventually succeeds; no error is returned to the caller if the retry succeeds within the deadline

#### Scenario: Soft-delete on vault without purge-protection
- **WHEN** `DeleteAgentSecret` is called and the vault has `softDelete` enabled without purge-protection
- **THEN** the adapter issues the soft-delete `DELETE` request and also issues the purge `DELETE /deletedsecrets/...` request, resulting in the secret being unrecoverable immediately

---

### Requirement: Azure Key Vault backend authenticates via azidentity credential chain

The `azure-key-vault` backend SHALL authenticate using the `azidentity.DefaultAzureCredential` chain from the Azure SDK for Go. The chain attempts authentication in order: Workload Identity (Kubernetes), Managed Identity (Azure VMs/containers), then environment variables (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`). The operator configures exactly one path from this chain; Mintkey itself takes no opinion. The credential materials used to authenticate to Azure Key Vault are NOT stored in Mintkey's own database — they are deployment-level secrets managed by the operator (Kubernetes Secret, Azure Managed Identity, environment). This resolves the chicken-and-egg: Mintkey secrets live in AKV, but AKV access credentials come from the deployment infrastructure, not from Mintkey itself.

The OAuth2 scope for Azure Key Vault is `https://vault.azure.net/.default`.

#### Scenario: Managed Identity path — no explicit credentials required
- **WHEN** `MINTKEY_AGENT_SECRET_BACKEND=azure-key-vault` and `MINTKEY_AKV_VAULT_URI` are set, and the workload runs on an Azure resource with a Managed Identity assigned
- **THEN** the adapter acquires a token from IMDS without any `AZURE_CLIENT_*` env vars; subsequent store calls succeed

#### Scenario: Client secret path — explicit env vars used
- **WHEN** `AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, and `AZURE_CLIENT_SECRET` are set
- **THEN** the adapter acquires a token using client credential flow and subsequent store calls succeed

---

### Requirement: Provider outage causes secret_get to fail closed with an operator-distinguishable error

When the configured external backend is unavailable (network timeout, HTTP 5xx, provider down), the adapter MUST fail closed: `secret_get` MUST return an error to the MCP server that results in an MCP-level error response to the agent. The agent-facing error shape MUST be the same internal-error shape used for other non-credential failures (the agent MUST NOT see "vault is down" in the message). Operators MUST be able to distinguish a provider-outage error from a `secret_not_found` error via structured logs or OTel spans (log field `error.kind=provider_outage` vs `error.kind=not_found`). The agent-facing MCP error code MUST remain the same as for any other internal error — the outage MUST NOT be disclosed to the calling agent.

#### Scenario: HashiCorp Vault unreachable causes internal error, not secret_not_found
- **WHEN** Vault is unreachable (connection refused) and an agent calls `secret_get`
- **THEN** the MCP tool returns an error response with an internal-error code (not `secret_not_found`), and the vault-adapter logs contain `error.kind=provider_outage` with the underlying connection error

#### Scenario: Azure Key Vault returns 503 — agent sees internal error, operator sees provider_outage
- **WHEN** Azure Key Vault returns HTTP 503 and an agent calls `secret_get`
- **THEN** the MCP tool returns an internal-error response to the agent; vault-adapter structured logs contain `error.kind=provider_outage` and `http.status=503`

#### Scenario: Postgres backend connection lost — same fail-closed behaviour
- **WHEN** the Postgres backend is unreachable (existing phase-1 behaviour verified)
- **THEN** `secret_get` returns an internal-error response to the agent (verifies behavioural parity across all backends)
