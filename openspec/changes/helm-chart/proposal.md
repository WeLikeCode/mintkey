# Helm Chart — first-party Kubernetes deployment artifact

## Why

Mintkey ships no Kubernetes deployment artifact (`docs/DEPLOYMENT.md`: "Kubernetes (Helm chart / operator): NOT shipped. No Helm chart in this repo. Operators choose how to translate compose to k8s."). Operators translating `infra/compose/docker-compose.yml` by hand re-derive the same 5-tier startup graph, PVC set, secret wiring, and internal-vs-external exposure decisions every time, and get the security-sensitive parts (SSH bastion as raw TCP, Kong admin never exposed, KEK as a file not an env var) wrong. A maintained Helm chart makes Mintkey deployable and upgradable on any cluster.

**Depends on `kubernetes-readiness`** — the chart is only correct once the broker key, OIDC state, admin-ui keypair, and DB-role secrets are restart/replica-safe. Do not start this change until that one has landed (or is landing in lockstep, chart authored against the fixed behavior).

All 12 first-party images are already published to `ghcr.io/welikecode/mintkey-<service>:<tag>` (`.github/workflows/publish.yml`), so the chart references them by pinned tag/digest — no build step, no private registry to stand up. Note: `publish.yml` sets package visibility manually per package; if the packages are private the chart supports an optional `imagePullSecret`.

## What Changes

- New **Helm chart** at `deploy/helm/mintkey/` (`Chart.yaml`, `values.yaml`, `templates/`, `README.md`): a parameterized deployment of the core stack — postgres (or an external/CNPG DB via `values`), vault-adapter, admin-api, admin-ui, mcp-server, broker, kong, kong-syncer, proxy-plugin, ssh-proxy, email-proxy, keycloak; observability (grafana/prometheus/jaeger) optional via a values flag so a cluster with its own stack can disable them.
- **Startup ordering** reimplemented for k8s: Liquibase and seed-job as Helm hook Jobs (hook weights: liquibase < seed-job) with a wait-for-job initContainer on dependents; readinessProbes gate traffic. No reliance on compose `depends_on`.
- **Persistence**: PVCs for postgres data, vault data/KEK, `bootstrap_secrets`, grafana, broker WAL, proxy WAL, and — critically — the **ssh-proxy host key** (pre-seeded; `SSH_PROXY_HOST_KEY_GENERATE=false`) and recordings. Prometheus PVC optional.
- **Config → ConfigMaps**: Kong declarative config (`apps/proxy-plugin/kong.yml`), OTel/Prometheus/Grafana configs from `infra/observability/`. No bind mounts.
- **Secrets → k8s Secrets** (never in `values.yaml` defaults): all keys enumerated in `PORTS.md` / `.env.example` — `MINTKEY_AUDIT_HMAC_KEY`, the four service bearer tokens, per-service vault identities, Keycloak admin, `MINTKEY_VAULT_KEK_FILE` (mounted file, since the env-var KEK form is rejected in production), `MINTKEY_BOOTSTRAP_KEK`, DB role passwords (from `kubernetes-readiness`), OAuth2 client secrets, broker signing key (from `kubernetes-readiness`). The chart references externally-managed Secrets by name; it does not generate or embed secret material.
- **Exposure model** encoded in the chart, matching the ADRs and `docs/NETWORK.md`:
  - **Ingress-eligible (HTTP)**: admin-api, admin-ui, mcp-server, kong proxy (`:8000`), keycloak, grafana, email-proxy, jaeger-auth — as `Ingress`/`values`-driven hosts; every `*_PUBLIC_URL` MUST be set to the real host (no `localhost` defaults).
  - **Raw TCP, NOT Ingress**: ssh-proxy `:2222` → a `Service type: LoadBalancer`/`NodePort` (or left cluster-internal for tailnet-only reach); documented that HTTP Ingress cannot carry SSH.
  - **Never exposed**: Kong admin `:8001`, postgres, vault-adapter, kong-syncer, proxy-plugin, otel-collector, broker issue endpoint — ClusterIP only, optionally a NetworkPolicy (the compose `127.0.0.1`-bind has no k8s equivalent, so exposure is controlled by simply not creating a Service/Ingress).
- **Replica policy in values**: admin-api `replicas: 1` with `Recreate` unless the OIDC-state fix is confirmed (guardrail comment referencing `kubernetes-readiness`); broker `replicas` ≥1 safe once key persistence lands.
- **Drop from the k8s path**: `cadvisor` (host-mount DaemonSet pattern, redundant with cluster node metrics), `hashicorp-vault` dev profile, `mock-backend` (demo only) — documented as intentionally omitted.
- Update `docs/DEPLOYMENT.md` to point at the chart and its `values.yaml` contract; new **ADR-0030** recording the k8s deployment topology and exposure model.

## Capabilities

### New Capabilities
- `helm-deployment`: a maintained Helm chart deploys the Mintkey core stack to Kubernetes from published GHCR images, with correct startup ordering (hook Jobs), persistence (PVCs incl. pre-seeded SSH host key), externally-managed Secrets, ConfigMap-based static config, and an exposure model that keeps the SSH bastion on raw TCP, the Kong admin plane unexposed, and the KEK as a mounted file.

## Impact

- **New**: `deploy/helm/mintkey/**`, ADR-0030 (+ symlink + index row).
- **Docs**: `docs/DEPLOYMENT.md` (add the k8s/Helm path), a `deploy/helm/mintkey/README.md` (install, required Secrets, values reference), `PORTS.md` cross-reference.
- **No application code change** beyond what `kubernetes-readiness` already delivers; if the chart surfaces a missing readiness/liveness endpoint or a `localhost`-defaulted URL that cannot be overridden, raise it as a defect against `kubernetes-readiness` rather than patching around it in templates.
- **Out of scope**: production Keycloak HA topology; a production Vault cluster; multi-tenant per-tenant deploys; CI/CD delivery pipeline (the consuming cluster's ArgoCD/GitOps wraps this chart — e.g. the SpotUs DEV cluster references it as an Application).

## Issue Intake (remediation gate)

1. **Problem statement**: Mintkey has no Kubernetes deployment artifact; every operator re-derives the compose→k8s translation and mis-handles the security-sensitive parts.
2. **User-visible symptom**: No `helm install` path; hand-written manifests get SSH bastion, Kong admin exposure, KEK mode, and startup ordering wrong.
3. **Expected behavior**: `helm install mintkey deploy/helm/mintkey -f values.yaml` (with required Secrets pre-created) brings up a working core stack: migrations run, seed completes, an agent can `request_token` and proxy a call in-cluster; admin UI reachable via Ingress; SSH bastion on TCP; Kong admin unreachable.
4. **Evidence**: no chart in repo (full-tree search); `docs/DEPLOYMENT.md` states it; compose exposure/ordering encoded only in `infra/compose/*` + shell tooling.
5. **Scope**: chart + hook Jobs + PVCs + Secret references + ConfigMaps + exposure model + values + docs + ADR-0030.
6. **Out of scope**: see above; also the four code fixes (they are `kubernetes-readiness`).
7. **Risk level**: MEDIUM — no new app code, but mis-templated Secrets/exposure are security-relevant. Independent review of the exposure model + a live smoke deploy required.
8. **Verification target**: `helm lint` + `helm template | kubeconform` (or `kubectl apply --dry-run=server`) green; a live smoke deploy on a real cluster proving: migrations+seed Jobs Completed, core pods Ready, in-cluster `request_token`→proxy call returns `Via: kong`, admin-ui reachable via Ingress, `nc` to ssh-proxy TCP works while Kong admin `:8001` has no Service, KEK loaded from a mounted file.
9. **Owner decisions**: DB = chart-managed postgres by default with a values switch for an external/CNPG DB; observability = optional (default off when the cluster provides its own); ssh-proxy Service type = values-driven (default ClusterIP for tailnet-only). Confirm with reviewer before defaulting any secret.
