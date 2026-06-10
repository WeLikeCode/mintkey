# External Secret Providers

## Why

Phase 1 stores agent secrets in Mintkey's own Postgres database (ADR-0025 D9). Operators who already run HashiCorp Vault or Azure Key Vault as their organisation's secret infrastructure want Mintkey agent secrets to live there instead — for compliance, centralised rotation auditing, and existing DRP coverage. The `AgentSecretStore` interface defined in Phase 1 was deliberately designed to accommodate additional backends; this change slots them in.

## What Changes

- New `hashicorp-vault` backend for `AgentSecretsVault`: reads/writes secrets in a HashiCorp Vault KV v2 mount using token auth (static bootstrap) or AppRole (dynamic, short-lived tokens); supports Vault Enterprise namespaces via `X-Vault-Namespace` header.
- New `azure-key-vault` backend for `AgentSecretsVault`: reads/writes secrets in Azure Key Vault via the REST API (`api-version=2025-07-01`); authenticates via `azidentity` DefaultAzureCredential chain (Workload Identity → Managed Identity → Client Secret env vars), covering both container and bare-metal deployments.
- New per-deployment configuration model: a single `MINTKEY_AGENT_SECRET_BACKEND={postgres|hashicorp-vault|azure-key-vault}` env var selects the backend at process start. Backend-specific settings use prefixed env vars (e.g. `MINTKEY_HV_ADDR`, `MINTKEY_AKV_VAULT_URI`). The per-tenant configuration model (operator configures via admin API, stored in DB) is **explicitly deferred** to a follow-up.
- New `AgentSecretStore` conformance test suite: a shared Go test package that every backend MUST pass before it is eligible for merge.
- Migration tooling: `make migrate-agent-secrets-{pg-to-hv|pg-to-akv}` following the `migrate-vault-sqlite-to-pg` precedent (ADR-0021).
- **ZERO wire-contract changes for agents**: the four MCP tools (`secret_put`, `secret_get`, `secret_list`, `secret_delete`) are unchanged; agents observe no difference in request or response shape regardless of backend.
- Minor admin-api additions (health endpoint) only if per-deployment config is used (no DB config rows needed; health is deployment-operator tooling, not a wire-contract change for agent clients).

## Capabilities

### New Capabilities

- `external-provider-backend`: pluggable backend implementations — HashiCorp Vault KV v2 and Azure Key Vault — behind the existing `AgentSecretStore` interface; backend selection via env var; conformance test suite all backends must pass.
- `provider-configuration`: operator-level deployment configuration model for selecting and bootstrapping an external backend; includes the chicken-and-egg analysis and the auth bootstrap strategy for each provider.
- `backend-migration`: tooling and semantics for moving existing agent secrets between backends (Postgres → HashiCorp Vault, Postgres → Azure Key Vault).

### Modified Capabilities

<!-- None — the agent-facing MCP tool requirements (agent-secret-storage, agent-secret-sharing) are unchanged. The only behavioural change observable by operators is provider-outage error shape, which is a new observable behaviour added in external-provider-backend, not a modification of an existing requirement. -->

## Impact

- **`AgentSecretStore` interface** (`apps/vault-adapter/internal/store/agent_secret.go`): no changes to the interface; two new implementing types added alongside `PostgresStore`.
- **vault-adapter**: new `store/hashicorp_vault.go`, new `store/azure_key_vault.go`; updated `cmd/vault-adapter/main.go` backend selector; new `conformance/` test package.
- **Configuration**: `docker-compose.yml` env blocks; `docs/HOW-TO.md` new section.
- **Migration**: new `apps/vault-adapter/cmd/migrate-agent-secrets/` binary; `Makefile` targets.
- **Admin API**: optional single new `GET /v1/health/agent-secret-backend` endpoint (no DB schema change, no new tables, no Liquibase changelog needed).
- **ADR-0026** (new): covers backend selection strategy, encryption model, migration semantics, and provider outage behaviour. Does NOT change ADR-0025 wire IDs, event types, or MCP tool shapes — those stay exactly as defined.
- **Conformance suite**: new `apps/vault-adapter/internal/store/conformance/` package; CI updated to run it against all registered backends.
- **No changes** to: `public.agent_secrets`, `public.agent_secret_grants`, `vault.agent_secrets` (Postgres tables stay as the default-backend tables and the authoritative state for any Postgres-backed tenant); openapi.yaml (agent-facing tools, sharing endpoints); tools.yaml; audit-event.schema.json; mcp-server code.
