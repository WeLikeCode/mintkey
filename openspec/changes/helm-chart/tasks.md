# Tasks — Helm Chart

Sonnet IMPLEMENTER (test-first where testable: `helm lint`, `helm template | kubeconform`), fresh Opus REVIEWER per chunk, 3-strike hard-stop. **Prerequisite: `kubernetes-readiness` has landed** (broker key, OIDC state, admin-ui keypair, DB-role secrets). Land in order: §1 ADR → §2 chart skeleton → §3 core workloads → §4 ordering/jobs → §5 persistence → §6 secrets/config → §7 exposure → §8 smoke deploy.

## 1. ADR
- [ ] 1.1 Write **ADR-0030** `docs/architecture/01-architecture/adr/0030-kubernetes-deployment-topology.md` (Proposed): the deployment topology, hook-Job ordering, PVC set, externally-managed Secrets, ConfigMap config, and the exposure model (Ingress-eligible vs raw-TCP ssh-proxy vs never-exposed Kong-admin/internal). Symlink + index row. `openspec validate helm-chart --strict`.

## 2. Chart skeleton
- [ ] 2.1 `deploy/helm/mintkey/Chart.yaml` + `values.yaml` (image registry/tag pinned to GHCR, per-service `replicas`/`resources`, feature flags: `observability.enabled`, `database.mode: chart|external`, `sshProxy.serviceType`, `imagePullSecret`). `helm lint` green.
- [ ] 2.2 `_helpers.tpl` (names, labels, the `*_PUBLIC_URL` wiring so no value defaults to `localhost`).

## 3. Core workloads (Deployments + Services)
- [ ] 3.1 Stateless services: admin-api, admin-ui, mcp-server, broker, kong, kong-syncer, proxy-plugin, email-proxy — Deployment + ClusterIP Service each, env from values + Secret refs, readiness/liveness probes (flag the admin-api `/v1/health` DB-coverage question from the analysis to the reviewer).
- [ ] 3.2 vault-adapter + keycloak (stateful deps) as Deployments/StatefulSets with their PVCs (see §5).
- [ ] 3.3 Database: `database.mode=chart` → a postgres StatefulSet + PVC; `database.mode=external` → consume a connection from a Secret (this is how a cluster with CNPG wires it). Document both in values.
- [ ] 3.4 `helm template | kubeconform` (or `kubectl apply --dry-run=server`) green for the whole chart.

## 4. Startup ordering (hook Jobs + init containers)
- [ ] 4.1 Liquibase as a Helm `pre-install,pre-upgrade` hook Job (hook-weight lower than seed-job); seed-job as a hook Job depending on liquibase; both idempotent (safe to re-run each upgrade).
- [ ] 4.2 wait-for-dependency initContainers on dependents (admin-api waits for vault-adapter + seed-job completion; proxy-plugin waits for kong; ssh-proxy waits for vault-adapter+broker) — poll readiness, no compose `depends_on`.

## 5. Persistence (PVCs)
- [ ] 5.1 PVCs: postgres data, vault data + KEK, `bootstrap_secrets`, grafana (if observability on), broker WAL, proxy WAL, **ssh-proxy host key (pre-seeded, `SSH_PROXY_HOST_KEY_GENERATE=false`)**, ssh-proxy recordings. Prometheus PVC behind `observability.enabled`.
- [ ] 5.2 Document the ssh-proxy host-key pre-seed procedure (equivalent of `make ssh-proxy-init`) in the chart README — a fresh host key on every deploy would break known-hosts trust.

## 6. Secrets & ConfigMaps
- [ ] 6.1 Secret references (chart consumes externally-created Secrets by name; NO secret material in `values.yaml`): audit HMAC, 4 service bearer tokens, per-service vault identities, Keycloak admin, `MINTKEY_VAULT_KEK_FILE` (mounted file), bootstrap KEK, DB role passwords, broker signing key, OAuth2 client secrets. README lists every required Secret + key.
- [ ] 6.2 ConfigMaps for Kong declarative config, OTel/Prometheus/Grafana configs (from `infra/observability/`). No bind mounts.
- [ ] 6.3 `MINTKEY_ENV=production` set; assert KEK uses `MINTKEY_VAULT_KEK_FILE` (env-var form is rejected in prod).

## 7. Exposure model
- [ ] 7.1 Ingress templates (values-driven hosts, TLS optional) for admin-api, admin-ui, mcp-server, kong proxy, keycloak, grafana, email-proxy, jaeger-auth. Every corresponding `*_PUBLIC_URL` set to the real host.
- [ ] 7.2 ssh-proxy `:2222` Service `type` from `values.sshProxy.serviceType` (default ClusterIP for tailnet-only; LoadBalancer/NodePort optional). Explicit: no Ingress for SSH.
- [ ] 7.3 Guarantee NO Service/Ingress for Kong admin `:8001`, postgres, vault-adapter, kong-syncer, proxy-plugin, otel-collector, broker issue endpoint (ClusterIP-internal only); optional NetworkPolicy templates.
- [ ] 7.4 Omit cadvisor, hashicorp-vault dev profile, mock-backend; note omissions in README.

## 8. Smoke deploy (gates the change)
- [ ] 8.1 Live deploy to a real cluster (e.g. a scratch namespace): migrations + seed Jobs `Completed`, core pods `Ready`.
- [ ] 8.2 In-cluster proof: from a pod, `request_token` via mcp-server → brokered proxy call returns `Via: kong`. Restart the broker Deployment → the previously-issued token still validates (confirms `kubernetes-readiness` A1 holds under the chart).
- [ ] 8.3 Exposure proof: admin-ui reachable via its Ingress host; `nc` to the ssh-proxy Service works; Kong admin `:8001` has no reachable Service; KEK confirmed loaded from the mounted file.
- [ ] 8.4 `helm lint`, `helm template | kubeconform`, `openspec validate helm-chart --strict` all green.
