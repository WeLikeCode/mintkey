# Helm Deployment

## ADDED Requirements

### Requirement: A Helm chart deploys the Mintkey core stack from published images
The repository SHALL provide a Helm chart at `deploy/helm/mintkey/` that deploys the core stack (postgres-or-external DB, vault-adapter, admin-api, admin-ui, mcp-server, broker, kong, kong-syncer, proxy-plugin, ssh-proxy, email-proxy, keycloak; observability optional) using images from `ghcr.io/welikecode/mintkey-<service>` pinned by tag/digest. The chart MUST NOT require a local build or a private registry beyond an optional `imagePullSecret`.

#### Scenario: Fresh install brings up a working stack
- **WHEN** an operator pre-creates the required Secrets and runs `helm install mintkey deploy/helm/mintkey -f values.yaml`
- **THEN** the Liquibase and seed-job hook Jobs run to Completion, the core pods reach Ready, and an in-cluster agent can `request_token` and make a brokered proxy call that returns `Via: kong`

#### Scenario: No secret material in the chart
- **WHEN** `deploy/helm/mintkey/values.yaml` and templates are inspected
- **THEN** no secret value is embedded; all credentials are referenced from externally-created Kubernetes Secrets by name, and the README enumerates every required Secret and key

### Requirement: Startup ordering is enforced without compose depends_on
The chart SHALL enforce dependency ordering using Helm hook Jobs (Liquibase before seed-job) and wait-for-dependency initContainers, so dependents do not start serving before their prerequisites are ready.

#### Scenario: Migrations precede seed precede app
- **WHEN** the chart installs
- **THEN** Liquibase completes before seed-job starts, seed-job completes before admin-api serves traffic, and both Jobs are idempotent on re-run (upgrade)

### Requirement: Persistence covers all durable state including the SSH host key
The chart SHALL provision PVCs for every durable volume the compose stack uses, including the ssh-proxy host key (pre-seeded, with host-key generation disabled) and session recordings, so identity and audit state survive pod restarts.

#### Scenario: SSH host identity is stable across restarts
- **WHEN** the ssh-proxy pod restarts
- **THEN** it presents the same pre-seeded host key (no client known-hosts break) and prior recordings remain

### Requirement: The exposure model keeps admin and internal planes off the public surface
The chart SHALL expose over HTTP Ingress only the intended services (admin-api, admin-ui, mcp-server, kong proxy, keycloak, grafana, email-proxy, jaeger-auth); expose the ssh-proxy over a raw TCP Service (never HTTP Ingress); and create no Service or Ingress for the Kong admin API (`:8001`), postgres, vault-adapter, kong-syncer, proxy-plugin, otel-collector, or the broker issue endpoint.

#### Scenario: SSH bastion is TCP, not Ingress
- **WHEN** the chart is deployed with the ssh-proxy enabled
- **THEN** the ssh-proxy is reachable as a TCP Service and there is no HTTP Ingress attempting to route SSH

#### Scenario: Kong admin plane is unreachable
- **WHEN** the deployed cluster is inspected
- **THEN** the Kong admin port `:8001` has no Service or Ingress and is reachable only from within the pod, and postgres/vault-adapter/internal services have ClusterIP-only exposure

### Requirement: Production KEK is a mounted file
When deployed via the chart with `MINTKEY_ENV=production`, the vault-adapter KEK SHALL be provided via `MINTKEY_VAULT_KEK_FILE` (a mounted Secret file), not the hex env-var form (which the vault-adapter rejects in production).

#### Scenario: KEK loaded from file in production
- **WHEN** the chart deploys with production settings
- **THEN** the vault-adapter starts with its KEK read from the mounted file path and does not fall back to the env-var form
