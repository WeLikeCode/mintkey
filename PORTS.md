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
| 11 | `jaeger` | *(internal)* | Trace backend — no host port; access via `jaeger-auth` |
| 11a | `jaeger-auth` | **16686** | oauth2-proxy fronting Jaeger UI (host 16686:4180; SSO required) |
| 12 | `grafana` | **3003** | Dashboards |

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
| URL | <http://localhost:3003> |

Sign in with Mintkey SSO (Keycloak). See [docs/AUTH.md](docs/AUTH.md) for the OIDC flow.

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

### Bootstrap admin password KEK

The seed-job encrypts the bootstrap admin password with a Fernet key before writing it to the `bootstrap-secrets` Docker volume (S6 CodeQL cleartext-storage fix). All services that read `admin_password` from the volume need this key.

```
MINTKEY_BOOTSTRAP_KEK=<URL-safe base64-encoded 32-byte Fernet key>
```

A dev default is hardcoded in `docker-compose.yml`. Generate a production key with:

```sh
python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Inject the same key into: `seed-job`, `admin-ui`, and any CI job that reads `admin_password` from the volume. Do not use the dev default in production.

---

## Quick access

```sh
make dev                              # start the stack
docker compose logs seed-job          # bootstrap admin password
open http://localhost:8080/v1/health  # admin-api health
open http://localhost:8443/admin      # keycloak admin
open http://localhost:3003            # grafana
open http://localhost:16686           # jaeger (via jaeger-auth; Keycloak login required)
```
