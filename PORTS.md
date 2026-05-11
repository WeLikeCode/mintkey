# Mintkey — ports and credentials reference

All values reflect the default `docker compose` dev stack. Do not use these in production.

---

## Service port map

| # | Service | Host port | Purpose |
|---|---------|-----------|---------|
| 1 | `keycloak` | **8443** | OIDC / Admin UI |
| 2 | `admin-api` | **8080** | FastAPI REST API (`/v1/`) |
| 3 | `admin-ui` | **8081** | AdminJS operator UI |
| 4 | `mcp-server` | **8082** | MCP tool server |
| 5 | `broker` | **8083** | Credential Broker (`/v1/`) |
| 6 | `vault-adapter` | **8084** | Vault gRPC service |
| 7 | `kong-syncer` | **8085** | Kong config sync (`/v1/`) |
| 8 | `kong` (proxy) | **8000** | Kong data plane (agent → backend) |
| 8 | `kong` (admin) | **8001** | Kong admin API |
| 9 | `mock-backend` | **8999** | Stub backend for smoke tests |
| 10 | `otel-collector` | **4317** | OTLP gRPC ingest |
| 11 | `jaeger` | **16686** | Trace UI |
| 12 | `grafana` | **3000** | Dashboards |

**Internal only (no host port):** `postgres` (5432), `prometheus` (9090), `proxy-plugin`, `kong-syncer`.
Grafana queries Prometheus at `http://prometheus:9090` inside the Docker network.

---

## Default credentials

### PostgreSQL

| Setting | Value |
|---------|-------|
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

```sh
# From seed-job logs (printed once at first boot):
docker compose logs seed-job | grep "Bootstrap admin password"

# Or read from the volume directly:
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

Replace with a proper secret manager reference before any non-local deployment (ADR-0003).

---

## Quick access

```sh
make dev                              # start the stack
docker compose logs seed-job          # bootstrap admin password
open http://localhost:8080/v1/health  # admin-api health
open http://localhost:8443/admin      # keycloak admin
open http://localhost:3000            # grafana
open http://localhost:16686           # jaeger
```
