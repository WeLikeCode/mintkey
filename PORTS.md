# Mintkey — ports and credentials reference

All values reflect the default `docker compose` dev stack. Do not use these in production.

---

## Service port map

| # | Service | Host port(s) | Container port | Purpose |
|---|---------|-------------|----------------|---------|
| 1 | `postgres` | — | 5432 (internal only) | PostgreSQL 16 |
| 2 | `keycloak` | **8443** | 8443 | OIDC / Admin UI |
| 3 | `admin-api` | **8080** | 8080 | FastAPI REST API (`/v1/`) |
| 4 | `admin-ui` | **8081** | 8081 | AdminJS operator UI |
| 5 | `mcp-server` | **8082** | 8082 | MCP tool server |
| 6 | `broker` | **8083** | 8083 | Credential Broker (`/v1/`) |
| 7 | `vault-adapter` | **8084** | 8084 | Vault gRPC service |
| 8 | `kong-syncer` | **8085** | 8085 | Kong config sync (`/v1/`) |
| 9 | `proxy-plugin` | **8086** | 8086 | Kong go-pdk egress plugin |
| 10 | `kong` (proxy) | **8000** | 8000 | Kong data plane (agent → backend) |
| 10 | `kong` (admin) | **8001** | 8001 | Kong admin API |
| 11 | `mock-backend` | **8999** | 8999 | Stub backend for smoke tests |
| 12 | `otel-collector` | **4317** | 4317 | OTLP gRPC ingest |
| 13 | `jaeger` | **16686** | 16686 | Trace UI |
| 14 | `prometheus` | **9091** | 9090 | Metrics scrape + query |
| 15 | `grafana` | **3000** | 3000 | Dashboards |

> **Port 9090** is occupied by Docker Desktop on macOS, so Prometheus is remapped to `9091` on the host.
> `proxy-plugin` communicates with Kong via a Unix socket (go-pdk), not HTTP.

---

## Default credentials

### PostgreSQL

| Setting | Value |
|---------|-------|
| Host (from host) | `localhost:5432` — **not exposed**; use `docker compose exec postgres psql` |
| Host (service-to-service) | `postgres:5432` |
| Database | `mintkey` |
| Migration user | `mintkey_migrate` / `changeme` (BYPASSRLS) |
| App user | `mintkey_app` (no password — peer auth inside Docker network) |

```sh
docker compose exec postgres psql -U mintkey_migrate -d mintkey
```

### Keycloak

| Setting | Value |
|---------|-------|
| URL | <http://localhost:8443> |
| Admin console | <http://localhost:8443/admin> |
| Admin username | `admin` |
| Admin password | `changeme` |

### Grafana

| Setting | Value |
|---------|-------|
| URL | <http://localhost:3000> |
| Username | `admin` |
| Password | `changeme` |

### Admin API — bootstrap operator

The seed-job generates a **random** password on first boot and writes it to a Docker named volume.

**Retrieve it:**

```sh
# From seed-job logs (printed once at first boot):
docker compose logs seed-job | grep "Bootstrap admin password"

# Or read directly from the volume via a one-shot container:
docker run --rm -v mintkey_bootstrap_secrets:/secrets alpine \
  cat /secrets/admin_password
```

| Setting | Value |
|---------|-------|
| Email | `admin@mintkey.internal` (override: `MINTKEY_BOOTSTRAP_EMAIL`) |
| Password | *(random — see above)* |
| Role | Platform admin |

### Vault Adapter (dev KEK)

The Key Encryption Key is hardcoded in `docker-compose.yml` for local development:

```
MINTKEY_VAULT_KEK=0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c1d1e1f20
```

This is a 32-byte dev secret. Replace it with a proper secret manager reference before any non-local deployment (ADR-0003).

---

## Quick access

```sh
make dev                       # start the stack
docker compose logs seed-job   # see bootstrap admin password
open http://localhost:8080/v1/health   # admin-api health
open http://localhost:8443/admin       # keycloak admin
open http://localhost:3000             # grafana
open http://localhost:16686            # jaeger
open http://localhost:9091             # prometheus
```
