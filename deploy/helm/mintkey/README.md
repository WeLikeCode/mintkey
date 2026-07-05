# Mintkey Helm Chart

Deploys the Mintkey credential broker to Kubernetes from published GHCR images
(`ghcr.io/welikecode/mintkey-*`).

**Status: pre-alpha.** Depends on kubernetes-readiness (ADR-0030). Not validated for production.
See [ADR-0031](../../../docs/architecture/01-architecture/adr/0031-kubernetes-deployment-topology.md)
for the full rationale behind the topology choices.

---

## Prerequisites

- Kubernetes 1.24+
- Helm v3.x
- `kubectl` configured for the target cluster
- A StorageClass that supports `ReadWriteOnce` (most cloud providers supply one by default)

---

## Required Kubernetes Secrets

Create **one** Secret before installing. The name defaults to `mintkey-secrets`; override via
`values.secretName`. Every key listed below is required unless noted optional.

```bash
kubectl create secret generic mintkey-secrets \
  --from-literal=POSTGRES_MIGRATE_PASSWORD=... \
  --from-literal=MINTKEY_DB_APP_PASSWORD=... \
  ...
```

### Database

| Key | Description |
|---|---|
| `POSTGRES_MIGRATE_PASSWORD` | Postgres superuser password used by the Liquibase migration Job |
| `MINTKEY_DB_APP_PASSWORD` | Password for the `mintkey_app` role (runtime app connections) |
| `MINTKEY_DB_SUBSCRIBER_PASSWORD` | Password for the `mintkey_subscriber` role (logical replication) |
| `DATABASE_URL` | Full DSN for admin-api / mcp-server / kong-syncer / proxy-plugin — `postgresql+asyncpg://mintkey_app:<pw>@<release>-postgres:5432/mintkey` |
| `MINTKEY_VAULT_PG_DSN` | DSN for vault-adapter — `postgres://mintkey_migrate:<pw>@<release>-postgres:5432/mintkey?sslmode=disable` |

### Keycloak

| Key | Description |
|---|---|
| `KEYCLOAK_ADMIN_PASSWORD` | Keycloak admin console password (also consumed by the seed-job hook) |

### Vault / KEK

| Key | Description |
|---|---|
| `MINTKEY_VAULT_KEK` | 32-byte AES key for vault encryption, stored as a hex string. Mounted as a file at runtime (`MINTKEY_VAULT_KEK_FILE`). The env-var form is rejected in production. Generate: `openssl rand -hex 32` |
| `MINTKEY_BOOTSTRAP_KEK` | Fernet key for encrypting the bootstrap admin password on disk. Generate: `python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

### Service Identity Tokens (vault-adapter scope grants)

| Key | Description |
|---|---|
| `MINTKEY_VAULT_PROXY_IDENTITY_ID` | Vault identity ID for the egress proxy |
| `MINTKEY_VAULT_PROXY_TOKEN` | Vault token for the egress proxy |
| `MINTKEY_VAULT_ADMIN_IDENTITY_ID` | Vault identity ID for admin-api |
| `MINTKEY_VAULT_ADMIN_TOKEN` | Vault token for admin-api |
| `MINTKEY_VAULT_SSH_PROXY_IDENTITY_ID` | Vault identity ID for ssh-proxy |
| `MINTKEY_VAULT_SSH_PROXY_TOKEN` | Vault token for ssh-proxy |
| `MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID` | Vault identity ID for email-proxy |
| `MINTKEY_VAULT_EMAIL_PROXY_TOKEN` | Vault token for email-proxy |
| `MINTKEY_VAULT_MCP_IDENTITY_ID` | Vault identity ID for mcp-server |
| `MINTKEY_VAULT_MCP_TOKEN` | Vault token for mcp-server |

### Service Bearer Tokens (inter-service auth)

| Key | Description |
|---|---|
| `MINTKEY_BROKER_SERVICE_TOKEN` | Static bearer token for the broker service |
| `MINTKEY_PROXY_SERVICE_TOKEN` | Static bearer token for the proxy-plugin service |
| `MINTKEY_MCP_SERVICE_TOKEN` | Static bearer token for the mcp-server service |
| `MINTKEY_EMAIL_PROXY_SERVICE_TOKEN` | Static bearer token for the email-proxy service |

### Admin UI / Session

| Key | Description |
|---|---|
| `SESSION_SECRET` | `express-session` secret for admin-ui. Generate: `openssl rand -hex 32` |
| `MINTKEY_AUDIT_HMAC_KEY` | HMAC key for audit-chain fingerprints. Generate: `openssl rand -hex 32` |

---

## SSH Proxy Host Key (required before install)

`SSH_PROXY_HOST_KEY_GENERATE` is `false` in the chart. Pre-seed the host key on the PVC so the
SSH bastion identity is stable across restarts and pod reschedules.

```bash
# Generate a host key locally
ssh-keygen -t ed25519 -f /tmp/ssh_host_ed25519_key -N ""

# After chart installs (before ssh-proxy starts), copy to the PVC via any running pod:
kubectl cp /tmp/ssh_host_ed25519_key <namespace>/<any-pod>:/tmp/
kubectl exec -n <namespace> <any-pod> -- \
  cp /tmp/ssh_host_ed25519_key /hostkey-mount/ssh_host_ed25519_key
```

Alternatively, run a pre-install Job that executes `ssh-keygen` once and writes the result to
the PVC. The chart intentionally does NOT auto-generate the key.

---

## Install

```bash
helm install mintkey deploy/helm/mintkey \
  -f my-values.yaml \
  --set ingress.adminApi.host=admin-api.example.com \
  --set ingress.adminUi.host=admin-ui.example.com \
  --set ingress.mcpServer.host=mcp.example.com \
  --set ingress.kongProxy.host=proxy.example.com \
  --set ingress.keycloak.host=sso.example.com \
  --set ingress.emailProxy.host=email-proxy.example.com
```

No host defaults are set in `values.yaml`. Ingresses with an empty host are not rendered, so
all six host values must be provided (or set `ingress.enabled=false` for cluster-internal-only
deployments).

## Upgrade

```bash
helm upgrade mintkey deploy/helm/mintkey -f my-values.yaml
```

The Liquibase migration Job and seed-job hook run idempotently on each upgrade
(`hook-delete-policy: before-hook-creation`).

---

## Key Design Decisions

### Kong admin API — internal only

The Kong admin API (port 8001) is exposed only via a ClusterIP Service named `<release>-kong-admin`.
`kong-syncer` reaches it in-cluster at `http://<release>-kong-admin:8001`. There is no Ingress
or LoadBalancer for this Service. Per ADR-0031.

### SSH proxy — raw TCP, not HTTP Ingress

The ssh-proxy Service type is controlled by `values.sshProxy.serviceType` (default: `ClusterIP`).
For external SSH access, set `serviceType: LoadBalancer` or `serviceType: NodePort`. HTTP Ingress
is not used for raw TCP — configure your cloud LB or `kubectl port-forward` for dev access.

### Vault KEK — file mount, not env var

`MINTKEY_VAULT_KEK` is stored in the Secret as a hex string, but mounted as a file at
`/run/secrets/vault_kek` and consumed via `MINTKEY_VAULT_KEK_FILE`. The plain env-var form is
rejected by the vault-adapter in production mode.

### Observability — disabled by default

`values.observability.enabled=false`. Prometheus, Grafana, Jaeger, and the OpenTelemetry
Collector are not deployed by default. Enable only if your cluster does not already run its own
observability stack. When enabled, Grafana and Prometheus each get their own PVC.

### Database — in-cluster Postgres by default

`values.database.mode=chart` deploys a single-replica Postgres 16 StatefulSet. For production,
set `database.mode=external` and supply a `DATABASE_URL` via a Secret referenced by
`database.externalSecretName`.

---

## Intentionally Omitted Components

These components from the Docker Compose stack are NOT deployed by this chart:

| Component | Reason |
|---|---|
| `cadvisor` | Use the cluster's own node-exporter / kube-state-metrics instead |
| `mock-backend` | Development demo only; not intended for production clusters |
| HashiCorp Vault dev profile | Use `MINTKEY_VAULT_BACKEND=postgres` (chart default) |

---

## Smoke Deploy Validation

After install, confirm the following to validate the deployment:

1. The Liquibase migration Job and seed-job complete with `Completed` status:
   ```bash
   kubectl get jobs -n <namespace>
   ```
2. All core pods reach `Ready` state:
   ```bash
   kubectl get pods -n <namespace>
   ```
3. An in-cluster agent can complete the full `request_token` → proxy call flow and receive a
   response with `Via: kong` in the headers.

Full smoke-test procedure: see ADR-0031 §8.

---

## Architecture

See [ADR-0031](../../../docs/architecture/01-architecture/adr/0031-kubernetes-deployment-topology.md)
for the full rationale: service topology, Kong admin isolation, SSH host-key lifecycle, PVC
sizing, and multi-replica caveats.
