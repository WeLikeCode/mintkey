# Provider Configuration

## ADDED Requirements

### Requirement: Backend is selected per deployment via environment variable

An operator deploying Mintkey SHALL be able to select the agent-secret backend by setting `MINTKEY_AGENT_SECRET_BACKEND` to one of: `postgres` (default), `hashicorp-vault`, or `azure-key-vault`. The setting applies to the vault-adapter process at startup and is immutable for the lifetime of the process (restart required to change backend). A per-tenant configuration model (operator configures via admin API, stored in DB) is explicitly not supported in this phase.

If `MINTKEY_AGENT_SECRET_BACKEND` is absent or empty, the backend MUST default to `postgres` — no behaviour change for existing deployments.

#### Scenario: Unset MINTKEY_AGENT_SECRET_BACKEND defaults to postgres
- **WHEN** vault-adapter starts with no `MINTKEY_AGENT_SECRET_BACKEND` env var set
- **THEN** the startup log records `agent_secret_backend=postgres` and the Postgres implementation is used for all agent-secret operations

#### Scenario: Unknown backend value causes startup failure
- **WHEN** `MINTKEY_AGENT_SECRET_BACKEND=s3` is set (unsupported value)
- **THEN** vault-adapter exits immediately with a non-zero exit code and logs `unknown agent_secret_backend: s3`

---

### Requirement: HashiCorp Vault backend is fully configured via prefixed env vars

When `MINTKEY_AGENT_SECRET_BACKEND=hashicorp-vault` is set, the vault-adapter SHALL require the following env vars and MUST fail at startup if mandatory ones are absent:

| Env var | Required | Description |
|---|---|---|
| `MINTKEY_HV_ADDR` | yes | Vault server address, e.g. `https://vault.example.com:8200` |
| `MINTKEY_HV_MOUNT` | no (default: `secret`) | KV v2 mount path |
| `MINTKEY_HV_AUTH_METHOD` | no (default: `token`) | `token` or `approle` |
| `MINTKEY_HV_TOKEN` | if `AUTH_METHOD=token` | Static Vault token |
| `MINTKEY_HV_ROLE_ID` | if `AUTH_METHOD=approle` | AppRole RoleID |
| `MINTKEY_HV_SECRET_ID` | if `AUTH_METHOD=approle` | AppRole SecretID |
| `MINTKEY_HV_NAMESPACE` | no | Vault Enterprise namespace (maps to `X-Vault-Namespace` header) |
| `MINTKEY_HV_TLS_SKIP_VERIFY` | no (default: `false`) | Set `true` only for dev environments |

#### Scenario: Missing MINTKEY_HV_ADDR causes startup failure
- **WHEN** `MINTKEY_AGENT_SECRET_BACKEND=hashicorp-vault` is set but `MINTKEY_HV_ADDR` is absent
- **THEN** vault-adapter exits with a non-zero exit code and logs `missing required env var: MINTKEY_HV_ADDR`

#### Scenario: AppRole missing MINTKEY_HV_ROLE_ID causes startup failure
- **WHEN** `MINTKEY_HV_AUTH_METHOD=approle` is set but `MINTKEY_HV_ROLE_ID` is absent
- **THEN** vault-adapter exits with a non-zero exit code and logs `approle auth requires MINTKEY_HV_ROLE_ID and MINTKEY_HV_SECRET_ID`

---

### Requirement: Azure Key Vault backend is fully configured via prefixed env vars

When `MINTKEY_AGENT_SECRET_BACKEND=azure-key-vault` is set, the vault-adapter SHALL require the following env vars and MUST fail at startup if mandatory ones are absent:

| Env var | Required | Description |
|---|---|---|
| `MINTKEY_AKV_VAULT_URI` | yes | Azure Key Vault base URI, e.g. `https://mymintkey.vault.azure.net` |
| `MINTKEY_AKV_PURGE_ON_DELETE` | no (default: `false`) | If `true` and vault has no purge-protection, issue hard-purge after soft-delete |

Authentication is provided via the `azidentity` environment chain (`AZURE_TENANT_ID`, `AZURE_CLIENT_ID`, `AZURE_CLIENT_SECRET`, or workload/managed identity); no Mintkey-specific auth env vars are defined for Azure KV (the SDK handles them).

#### Scenario: Missing MINTKEY_AKV_VAULT_URI causes startup failure
- **WHEN** `MINTKEY_AGENT_SECRET_BACKEND=azure-key-vault` is set but `MINTKEY_AKV_VAULT_URI` is absent
- **THEN** vault-adapter exits with a non-zero exit code and logs `missing required env var: MINTKEY_AKV_VAULT_URI`

---

### Requirement: Health check reflects current backend status

The admin API SHALL expose `GET /v1/health/agent-secret-backend` which returns a JSON body indicating the active backend name and a reachability probe result. This endpoint is for operator tooling (load balancer health checks, deployment readiness gates). It MUST NOT expose any secret values, credentials, or detailed internal state. A `200 OK` response with `{"backend":"hashicorp-vault","status":"ok"}` indicates the backend is reachable; a `503 Service Unavailable` with `{"backend":"hashicorp-vault","status":"error","message":"<opaque-string>"}` indicates it is not. The message MUST NOT contain credential values.

#### Scenario: Health check returns ok when backend reachable
- **WHEN** `GET /v1/health/agent-secret-backend` is called and the configured backend responds to a no-op probe
- **THEN** the response is `200 OK` with `{"backend":"<name>","status":"ok"}`

#### Scenario: Health check returns 503 when backend unreachable
- **WHEN** the configured backend is unreachable and `GET /v1/health/agent-secret-backend` is called
- **THEN** the response is `503 Service Unavailable` with `{"backend":"<name>","status":"error","message":"<opaque-string>"}`

#### Scenario: Health check message contains no credential material
- **WHEN** the backend returns an auth error (e.g. expired token) and `GET /v1/health/agent-secret-backend` is called
- **THEN** the response body message does not contain the value of any `MINTKEY_HV_*` or `MINTKEY_AKV_*` env var
