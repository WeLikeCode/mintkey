# email-proxy

Mintkey Email Proxy data-plane service. Authenticates agents via brokered JWTs,
fetches email credentials from the vault-adapter, and proxies IMAP/SMTP/OAuth2
operations to configured email services.

Implements ADR-0024: Email Proxy Support.

HTTP server: `:8088` — REST API + health/readyz/metrics  
Metrics port: `:8090` (dedicated Prometheus endpoint; `:8087` is ssh-proxy healthz)

## Configuration

| Variable | Required | Default | Description |
|---|---|---|---|
| `MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID` | Yes | — | Vault service identity ID |
| `MINTKEY_VAULT_EMAIL_PROXY_TOKEN` | Yes | — | Vault service identity token |
| `MINTKEY_BROKER_JWKS_URL` | No | `http://broker:8083/.well-known/jwks.json` | Broker JWKS endpoint |
| `MINTKEY_VAULT_GRPC_ADDR` | No | `vault-adapter:8084` | Vault adapter gRPC address |
| `MINTKEY_EMAIL_PROXY_HTTP_PORT` | No | `8088` | HTTP listen port |
| `MINTKEY_EMAIL_PROXY_METRICS_PORT` | No | `8090` | Prometheus metrics port |
| `MINTKEY_EMAIL_PROXY_LOG_LEVEL` | No | `info` | Log level (`info`, `debug`) |
| `MINTKEY_ADMIN_API_INTERNAL_URL` | No | `http://admin-api:8080` | Admin API URL (OAuth2 refresh) |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | No | — | OTel Collector gRPC endpoint |

## Build

```bash
# From repo root (required for go.work workspace resolution):
docker build -f apps/email-proxy/Dockerfile -t mintkey-email-proxy .

# Local build:
cd apps/email-proxy && go build ./...

# Tests:
go test ./... -short
```

## Ports

See `PORTS.md` at repo root.
- `:8088` — REST API (liveness/readiness/metrics + stub email endpoints)
- `:8090` — Prometheus metrics (dedicated; avoids collision with ssh-proxy :8087)
