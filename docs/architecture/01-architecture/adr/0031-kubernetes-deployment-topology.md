# ADR-0031: Kubernetes Deployment Topology (Helm Chart)

## Status

Proposed — 2026-07-05

---

## Context

Mintkey ships no Kubernetes deployment artifact (`docs/DEPLOYMENT.md`: "Kubernetes (Helm chart / operator): NOT shipped. No Helm chart in this repo."). Operators translating `infra/compose/docker-compose.yml` by hand re-derive the same 5-tier startup graph, PVC set, secret wiring, and internal-vs-external exposure decisions every time. The security-sensitive parts — the SSH bastion as raw TCP, the Kong admin plane unexposed, and the KEK as a mounted file rather than an env var — are routinely mis-handled. A maintained, first-party Helm chart makes Mintkey deployable and upgradable on any cluster with correct defaults.

All 12 first-party images are already published to `ghcr.io/welikecode/mintkey-<service>:<tag>` via `.github/workflows/publish.yml`. The chart references them by pinned tag/digest. No build step and no private registry are required; an optional `imagePullSecret` is supported for private package visibility.

**Dependency:** This chart is only correct once [ADR-0030](0030-kubernetes-readiness-restart-safety.md) has landed — the broker signing key, OIDC state, admin-ui keypair, and DB-role secrets must be restart/replica-safe before the chart can be considered production-worthy.

Quality attributes affected:

- **S-SEC-1** — Agent never holds a usable backend credential; exposure model must preserve this at the network boundary.
- **S-OPS-1** — The system must be deployable and upgradable without operator error on the security-sensitive paths (SSH bastion, Kong admin plane, KEK).
- **S-MOD-1** — No application code changes are introduced by the chart itself.

---

## Decision

### D1 — Helm chart at `deploy/helm/mintkey/`

Publish a first-party Helm chart at `deploy/helm/mintkey/` (`Chart.yaml`, `values.yaml`, `templates/`, `README.md`). The chart deploys the full Mintkey core stack from `ghcr.io/welikecode/mintkey-<service>` images. Observability components (Grafana, Prometheus, Jaeger) are included but disabled by default via `values.observability.enabled: false`, so clusters with their own observability stack incur no redundant workloads.

No application code is changed by the chart. If the chart surfaces a missing readiness/liveness endpoint or a `localhost`-defaulted URL that cannot be overridden, the defect is raised against the `kubernetes-readiness` track (ADR-0030), not patched around in templates.

### D2 — Startup ordering: Helm hook Jobs + initContainers

Compose `depends_on` has no direct Kubernetes equivalent. Startup ordering is reimplemented as:

| Component | Kind | Hook weight | Purpose |
|---|---|---|---|
| `mintkey-liquibase` | Helm hook Job (`pre-install`, `pre-upgrade`) | `-5` | Run Liquibase migrations against Postgres before any application pod starts. |
| `mintkey-seed-job` | Helm hook Job (`pre-install`, `pre-upgrade`) | `-4` | Bootstrap the default tenant, generate the admin-UI keypair, seed Vault Adapter key material. Runs after Liquibase completes. |

Dependent application pods (admin-api, broker, vault-adapter, etc.) carry an `initContainer` that waits for the hook Jobs to reach `Completed` status before the main container starts. `readinessProbe`s on each pod gate traffic until the application is ready.

**Workload kinds by statefulness:**

| Service | Kind | Notes |
|---|---|---|
| `postgres` | `StatefulSet` | Chart-managed by default; `values.postgres.external: true` switches to an external/CNPG DB. |
| `keycloak` | `StatefulSet` | Persistent realm configuration; production HA topology is out of scope. |
| `vault-adapter` | `StatefulSet` | Needs a stable network identity for gRPC callers (`vault-adapter:8084`). |
| `admin-api`, `admin-ui`, `mcp-server`, `broker`, `kong`, `kong-syncer`, `proxy-plugin`, `email-proxy` | `Deployment` | Stateless; replicas ≥1 safe once ADR-0030 code fixes are in place (guardrail comment in values). |
| `ssh-proxy` | `Deployment` | Stateless session bridging; stateful recording written to PVC. |

### D3 — PVC set

The following PersistentVolumeClaims are created by the chart:

| PVC | Purpose | Notes |
|---|---|---|
| `postgres-data` | Postgres data directory | Sized via `values.postgres.storage`. |
| `vault-data` | Vault Adapter encrypted credential store (`vault.credentials`) | |
| `vault-kek` | Key Encryption Key file for the Vault Adapter | See D5 for KEK policy. |
| `bootstrap-secrets` | Shared volume: admin-UI keypair, seed outputs | Mounted by seed-job (write), admin-api, and admin-ui (read). |
| `grafana-data` | Grafana dashboards and state | Provisioned only when `values.observability.enabled: true`. |
| `broker-wal` | Broker write-ahead log | |
| `proxy-wal` | Proxy plugin write-ahead log | |
| `ssh-proxy-hostkey` | Pre-seeded SSH host key | `SSH_PROXY_HOST_KEY_GENERATE=false` is set; the PVC is pre-seeded by the seed-job. Prevents host-key change on pod restart breaking agent `known_hosts`. |
| `ssh-proxy-recordings` | Asciicast v2 session recordings (ADR-0022) | |

### D4 — Secret model: externally-managed Secrets only

No secret material appears in `values.yaml` defaults or in any chart-rendered template literal. The chart references externally-managed Kubernetes Secrets by name; operators create them before `helm install`. The `deploy/helm/mintkey/README.md` enumerates every required Secret key.

Required Secrets include (non-exhaustive; see chart README for the canonical list):

- `MINTKEY_AUDIT_HMAC_KEY`
- Four service bearer tokens (admin-api, broker, mcp-server, kong-syncer)
- Per-service vault identity tokens
- Keycloak admin credentials
- `MINTKEY_VAULT_KEK_FILE` content (mounted; see D5)
- `MINTKEY_BOOTSTRAP_KEK`
- DB role passwords (`MINTKEY_DB_APP_PASSWORD`, `MINTKEY_DB_SUBSCRIBER_PASSWORD` — from ADR-0030 D4)
- OAuth2 client secrets (from ADR-0020)
- Broker signing key (from ADR-0030 D1)

### D5 — KEK policy: file mount in production

When `MINTKEY_ENV=production`, the Vault Adapter KEK **must** be supplied via `MINTKEY_VAULT_KEK_FILE` (a path pointing to a file mounted from a Kubernetes Secret). The hex env-var form (`MINTKEY_VAULT_KEK`) is rejected at startup in production. The chart mounts the KEK Secret as a file at `/run/secrets/vault_kek` and sets `MINTKEY_VAULT_KEK_FILE=/run/secrets/vault_kek`.

This matches the compose behavior documented in `PORTS.md` and is consistent with S-SEC-1 — the KEK never appears in process environment listings scraped by container runtimes or OTel host metrics.

### D6 — Exposure model

The chart encodes the exposure model from `docs/NETWORK.md` and the relevant ADRs:

**HTTP Ingress-eligible services** (exposed via `Ingress` resource, hosts driven by `values.ingress.*`):

| Service | Internal port | ADR |
|---|---|---|
| `admin-api` | `:8080` | ADR-0005 |
| `admin-ui` | `:3000` | ADR-0019 |
| `mcp-server` | `:8083` | ADR-0009 |
| Kong proxy | `:8000` | ADR-0004, ADR-0007 |
| `keycloak` | `:8080` | ADR-0020 |
| `grafana` | `:3000` | ADR-0005 |
| `email-proxy` | `:8088` | ADR-0024 |
| Jaeger auth (`oauth2-proxy`) | `:4180` | ADR-0020 |

Every `*_PUBLIC_URL` environment variable for ingress-eligible services **must** be set to the real host. No `localhost` defaults are accepted in production.

**Raw TCP — ssh-proxy `:2222`** (ADR-0022):

The SSH bastion is exposed via a dedicated `Service` of type `values.sshProxy.serviceType` (default: `ClusterIP`). HTTP Ingress cannot carry SSH wire protocol. Operators that need external reach set `serviceType: LoadBalancer` or `NodePort`; tailnet-only deployments leave the default. The service is never placed behind an Ingress controller.

**Never exposed** (ClusterIP only, no Ingress, no NodePort by default):

| Component | Port | Reason |
|---|---|---|
| Kong admin | `:8001` | Kong admin plane must not be reachable outside the cluster. Compose enforces this with `127.0.0.1` bind; k8s enforces it by having no Service/Ingress for this port. |
| `postgres` | `:5432` | DB not reachable from outside. |
| `vault-adapter` gRPC | `:8084` | Internal credential RPC only. |
| `kong-syncer` | `:8085` | Internal only. |
| `proxy-plugin` | `:8086` | Internal only. |
| `otel-collector` | `:4317` | Internal telemetry ingestion. |
| Broker issue endpoint | `:8082` | MCP-facing only, not agent-directly reachable from outside. |

A `NetworkPolicy` manifest is included in `templates/network-policy.yaml` (opt-in via `values.networkPolicy.enabled: true`) that enforces the above restrictions at the CNI layer for clusters that support it.

### D7 — Observability: optional, default off

Grafana, Prometheus, and Jaeger are deployed only when `values.observability.enabled: true`. The flag defaults to `false`. Operators running their own observability stack set the flag off and configure OTel export endpoints via `values.otel.*`. Prometheus PVC is provisioned only when observability is enabled.

### D8 — Intentional omissions

The following components present in the compose stack are intentionally excluded from the Helm chart:

| Component | Reason |
|---|---|
| `cadvisor` | Requires host-mount DaemonSet pattern; cluster node metrics are typically provided by the cluster operator (kube-state-metrics / node-exporter). |
| `hashicorp-vault` (dev profile) | Dev-profile only in compose; Mintkey's production vault backend is Postgres (ADR-0021). |
| `mock-backend` | Demo/testing only; not a production workload. |

---

## Consequences

### Positive

- `helm install mintkey deploy/helm/mintkey -f values.yaml` (with required Secrets pre-created) brings up the full core stack with correct startup ordering, persistence, and exposure model.
- The SSH bastion is on raw TCP with a configurable Service type — the operator cannot accidentally put it behind an HTTP Ingress.
- Kong admin `:8001` has no Service/Ingress, closing the most common Kong misconfiguration.
- KEK is file-mounted in production; the hex env-var form is rejected, removing the risk of KEK exposure via environment listings.
- The ssh-proxy host key is pre-seeded and stable across pod restarts; agents' `known_hosts` entries remain valid.
- Observability is off by default, preventing redundant workloads on clusters with existing stacks.

### Costs

- Operators must pre-create all required Kubernetes Secrets before `helm install`; the chart provides no secret generation. The chart README enumerates all required keys.
- The chart is only production-correct after ADR-0030 code fixes land; a guardrail comment in `values.yaml` documents this dependency.
- StatefulSet pod disruption during upgrades requires care (postgres, keycloak, vault-adapter); the chart documents recommended upgrade procedures.
- `cadvisor` and `hashicorp-vault` dev-profile features are not available in the Helm path; operators needing them must supplement.

### Wire-shape invariants preserved

- No REST/MCP/gRPC wire shapes changed.
- No database schema changed.
- No audit event types added or removed.
- No new application environment variables introduced beyond what ADR-0030 already defines.

---

## Alternatives considered

| Alternative | Why rejected |
|---|---|
| Kustomize-only manifests | No release artifact; operators still hand-derive the startup graph. Values parameterization is more ergonomic in Helm. |
| Operator pattern (custom controller) | Significantly higher implementation cost; not warranted for a single-tenant-by-default product at this stage. |
| Expose Kong admin behind auth proxy | Any reachable Kong admin is a lateral-movement risk if the auth proxy is misconfigured. ClusterIP-only is the only correct default. |
| KEK as env var in production | Process environment is accessible via `/proc/PID/environ` in many runtimes; file mount reduces attack surface. Rejected per S-SEC-1. |
| ssh-proxy behind HTTP Ingress with TCP passthrough | TCP passthrough in Nginx/Traefik Ingress is non-standard and controller-specific; a dedicated Service is simpler and universal. |
| Bundle cadvisor as DaemonSet | DaemonSets require `hostPath` mounts and elevated RBAC; not appropriate for a chart that may be installed in multi-tenant clusters. |

---

## Related

- [ADR-0004](0004-egress-proxy-kong.md) — Kong Gateway as egress proxy; Kong admin `:8001` exposure model.
- [ADR-0007](0007-proxy-deployment-topology.md) — Proxy deployment topology; Kong proxy `:8000`.
- [ADR-0009](0009-mcp-server-stack-python.md) — MCP Server; internal port `:8083`.
- [ADR-0019](0019-admin-ui-bff-and-write-auth.md) — Admin-UI BFF; `bootstrap_secrets` volume for keypair.
- [ADR-0020](0020-sso-keycloak-canonical-idp.md) — Keycloak as canonical IdP; `oauth2-proxy` for Jaeger.
- [ADR-0021](0021-vault-storage-backend-postgres.md) — Postgres vault backend; `vault.credentials`; KEK file form.
- [ADR-0022](0022-ssh-bastion.md) — SSH bastion on `:2222`; raw TCP requirement; host key; session recording PVC.
- [ADR-0024](0024-email-proxy-support.md) — Email proxy on `:8088`; Ingress-eligible.
- [ADR-0030](0030-kubernetes-readiness-restart-safety.md) — Kubernetes readiness fixes this chart depends on: broker key persistence, OIDC state in Postgres, admin-UI keypair generation, DB-role password env substitution.
