# Deployment Guide — Mintkey

> **Pre-alpha. Unsupported for production.** Mintkey is a self-hostable
> credential broker for AI agents in pre-alpha. This guide describes the
> only currently-supported deployment posture (Docker Compose on a single
> host for evaluation) and explicitly lists what is NOT validated for
> production. Use at your own risk.

---

## Supported posture — Docker Compose on a single host

For evaluation, demos, and small-team self-hosting:

- Docker Compose v2 (`docker compose ...`)
- Single host (Linux or macOS)
- All services share one Docker network (`mintkey`)
- Postgres, Keycloak, Kong, Mintkey services, Grafana, and Jaeger all in compose
- Operator-facing URLs configured via `MINTKEY_*_PUBLIC_URL` env vars (see [`docs/NETWORK.md`](NETWORK.md))
- Keycloak SSO for operator authentication (see [`docs/AUTH.md`](AUTH.md))
- Agent identities via API keys (`mk_agent_*`)

### Deploy on a fresh host

```bash
# 1. Clone the repo
git clone https://github.com/WeLikeCode/mintkey.git
cd mintkey

# 2. Copy the example env file and set your URLs
cp .env.example .env
# Edit .env — at minimum set MINTKEY_*_PUBLIC_URL if accessing from a remote machine.
# See docs/NETWORK.md for the full variable reference.

# 3. Start the stack (all 17 services)
docker compose up -d

# 4. Wait for healthy status
docker compose ps --format "table {{.Service}}\t{{.Status}}"

# 5. First login — navigate to http://localhost:8081
# Default operator email: admin@mintkey.internal
# Default password: read from data/bootstrap-secrets/admin_password
```

For detailed first-login and break-glass procedures see [`docs/AUTH.md`](AUTH.md).
For agent configuration and MCP client setup see [`docs/HOW-TO.md`](HOW-TO.md).

---

## NOT supported / explicitly out of scope for pre-alpha

These deployment paths are recognised but NOT validated. Attempting them may work, but there
is no tested procedure, no documented failure mode, and no support commitment for pre-alpha.

| Path | Status | Notes |
|---|---|---|
| Production HA (multiple replicas of admin-api / broker / proxy) | NOT validated | The OIDC `_state_store` is in-process — single-replica only. Tracked in ADR-0020 open follow-ups. |
| Managed secrets (Vault, AWS Secrets Manager, GCP Secret Manager) | NOT integrated | `data/bootstrap-secrets/` is the only supported secret source today. |
| TLS ingress to the stack | NOT documented | Compose exposes plain HTTP; operators must front the stack with a reverse proxy (Caddy, nginx, cloud LB). See [`docs/NETWORK.md`](NETWORK.md) for the URL contracts. |
| Database backup / restore / DR | NOT documented | Postgres data lives in the `postgres_data` Docker volume; no point-in-time recovery, no off-host backup automation. |
| Kubernetes (Helm chart / operator) | NOT shipped | No Helm chart in this repo. Operators choose how to translate compose to k8s. Images will be published to `ghcr.io/welikecode/mintkey-*` once the release workflow ships. |
| Multi-tenant production isolation | RLS only | Row-level isolation works; no per-tenant network isolation, no per-tenant rate limits. |
| SOC2 / FedRAMP / HIPAA-grade audit | NOT certified | Audit chain is implemented (hash-linked); no third-party certification. |
| Image signing / SBOM / SLSA provenance | NOT shipped | Tracked in OSS-4; deferred this session. See `docs/RELEASE.md` (forthcoming). |
| Long-term support / patches | NOT offered | Pre-alpha; semver pre-releases only. See `docs/RELEASE.md` (forthcoming). |

---

## Hardening checklist for evaluators

If you are self-hosting Mintkey for an internal team, even pre-alpha, work through this
checklist before sharing access with others:

- [ ] Set `MINTKEY_KEYCLOAK_PUBLIC_URL` and the other `MINTKEY_*_PUBLIC_URL` vars in `.env`
      (NEVER use the localhost defaults from a remote machine — see [`docs/NETWORK.md`](NETWORK.md))
- [ ] Front the stack with a TLS-terminating reverse proxy (Caddy, nginx, or a cloud load balancer)
- [ ] Run the stack on its own host or VM — do not co-mingle with other workloads
- [ ] Restrict Kong admin port (`127.0.0.1:8001`) — already enforced in compose; verify if you
      add a custom network configuration
- [ ] Back up the `postgres_data` and `bootstrap_secrets` Docker volumes before any upgrade:
      ```bash
      docker run --rm -v mintkey_postgres_data:/data -v $(pwd):/backup alpine \
        tar czf /backup/postgres_data_backup.tar.gz /data
      ```
- [ ] Pin Mintkey to a specific commit SHA via `git checkout <sha>` — do not track `main`
- [ ] Monitor `mintkey_audit_chain_violation_total` (Prometheus / Grafana) — a non-zero value
      indicates a potential audit-chain integrity compromise
- [ ] Read [`SECURITY.md`](../SECURITY.md) and follow the vulnerability disclosure policy before
      deploying to any network that is not fully trusted

---

## Container hardening status (pre-alpha gaps)

The table below is an audit snapshot reflecting the state after REL-3 (2026-05-16).

**Audit date:** 2026-05-16  
**Dockerfiles surveyed:** 10

| Service | Dockerfile | Base image | USER directive | HEALTHCHECK | Base pinned by digest |
|---|---|---|---|---|---|
| admin-api | `apps/admin-api/Dockerfile` | `python:3.12-slim` | UID 65532 (`nonroot`) | `python3` urllib fallback on `:8080/v1/health` | No (tag only) |
| admin-ui | `admin-ui/Dockerfile` | `node:22-slim` | `node` user (UID 1000, pre-created by base image) | `node` http.get on `:8081/health` | No (tag only) |
| jaeger-auth | `jaeger-auth/Dockerfile` | `quay.io/oauth2-proxy/oauth2-proxy:v7.6.0` (build) + `alpine:3.19` (runtime) | UID 65532 (`oauth2proxy`) | `wget -qO- http://localhost:4180/ping` | No (tag only) |
| mcp-server | `apps/mcp-server/Dockerfile` | `python:3.12-slim` | UID 65532 (`nonroot`) | `python3` urllib fallback on `:8082/health` | No (tag only) |
| mock-backend | `mock-backend/Dockerfile` | `python:3.12-slim` | UID 65532 (`nonroot`) | `python3` urllib fallback on `:8999/health` | No (tag only) |
| seed-job | `seed-job/Dockerfile` | `python:3.12-slim` | UID 65532 (`nonroot`) | None (one-shot job — HEALTHCHECK deferred) | No (tag only) |
| broker | `apps/broker/Dockerfile` | `golang:1.26-alpine` (build) + `gcr.io/distroless/static-debian12` (runtime) | None — distroless default is non-root UID 65534 (nonroot), but no explicit USER | None | No (tag only) |
| kong-syncer | `apps/kong-syncer/Dockerfile` | `golang:1.26-alpine` (build) + `gcr.io/distroless/static-debian12` (runtime) | None — distroless default is non-root UID 65534 (nonroot), but no explicit USER | None | No (tag only) |
| proxy-plugin | `apps/proxy-plugin/Dockerfile` | `golang:1.26-alpine` (build) + `gcr.io/distroless/static-debian12` (runtime) | None — distroless default is non-root UID 65534 (nonroot), but no explicit USER | None | No (tag only) |
| vault-adapter | `apps/vault-adapter/Dockerfile` | `golang:1.26-alpine` (build) + `gcr.io/distroless/static-debian12` (runtime) | None — distroless default is non-root UID 65534 (nonroot), but no explicit USER | `grpc_health_probe` binary bundled but no HEALTHCHECK directive | No (tag only) |

### Summary

- **USER directive:** 6 of 10 Dockerfiles now have an explicit `USER` directive (REL-3, 2026-05-16).
  The four Go services use `gcr.io/distroless/static-debian12` which defaults to UID 65534
  (`nonroot`) implicitly; explicit USER addition for distroless services is deferred.
- **HEALTHCHECK directive:** 5 of 10 Dockerfiles now have a `HEALTHCHECK` instruction (REL-3,
  2026-05-16). `seed-job` is a one-shot init container — HEALTHCHECK not applicable. The four Go
  distroless services have no Dockerfile HEALTHCHECK; compose-level healthchecks cover them for
  compose deployments. The `vault-adapter` bundles `grpc_health_probe` for liveness but does not
  wire it as a Dockerfile `HEALTHCHECK`. Dockerfile HEALTHCHECK for distroless services is deferred.
- **Digest pinning:** 0 of 10 Dockerfiles pin base images by `@sha256` digest. All use mutable
  tags. A compromised tag redeploy would silently change the base image. Digest pinning is
  deferred to a future session alongside the release workflow (OSS-4).

### Operator note — bootstrap_secrets volume on existing installs

When upgrading from a pre-REL-3 installation, the `bootstrap_secrets` Docker volume may contain
files owned by root (UID 0). The six non-distroless services now run as UID 65532 (or UID 1000
for admin-ui). To fix permissions after a stack upgrade:

```bash
# One-time migration — safe to run with stack up:
docker run --rm -v mintkey_bootstrap_secrets:/secrets alpine:3.19 chown -R 65532:65532 /secrets
```

Fresh installs are unaffected — Docker creates the volume directory owned by the first writer
(UID 65532 from seed-job).

**REL-3 verification (2026-05-16):** All 5 long-running services (admin-api, mcp-server, admin-ui,
mock-backend, jaeger-auth) rebuilt and confirmed healthy; `id` check confirms uid != 0 for each;
HEALTHCHECK registered on all 5 containers; data preserved (svc=4, agents=3, grants=2).

---

## Getting help

- Bug reports and questions: see [`SUPPORT.md`](../SUPPORT.md) (forthcoming via OSS-2) — in the
  meantime, open a GitHub Issue or Discussion at
  <https://github.com/WeLikeCode/mintkey>
- Security vulnerabilities: see [`SECURITY.md`](../SECURITY.md) (private email disclosure)
- Architecture context: [`docs/architecture/`](architecture/)
- Operator how-to cookbook: [`docs/HOW-TO.md`](HOW-TO.md)
