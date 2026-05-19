# Dev-Test Namespace

Run a second, fully isolated Mintkey stack on the same machine — no risk to your primary environment.

## Concept

The dev-test namespace is a parallel Mintkey instance launched via Docker Compose's multi-file override mechanism. It layers `docker-compose.test.yml` on top of the primary `docker-compose.yml`, shifting all host ports by +100 and isolating volumes, networks, and data under the project name `mintkey-test`.

Both instances share the same Docker images (no rebuild required). The primary instance does **not** need to be running — the test namespace works standalone.

## Port Mapping

Every host port is offset by **+100**. Container-internal ports are unchanged.

| # | Service | Primary Port | Test Port | Container Port |
|---|---------|:------------:|:---------:|:--------------:|
| 1 | keycloak | 8443 | **8543** | 8443 |
| 2 | admin-api | 8080 | **8180** | 8080 |
| 3 | admin-ui | 8081 | **8181** | 8081 |
| 4 | mcp-server | 8082 | **8182** | 8082 |
| 5 | broker | 8083 | **8183** | 8083 |
| 6 | vault-adapter (gRPC) | 8084 | **8184** | 8084 |
| 7 | vault-adapter (HTTP) | 8087 | **8187** | 8087 |
| 8 | kong-syncer | 8085 | **8185** | 8085 |
| 9 | kong (proxy) | 8000 | **8100** | 8000 |
| 10 | kong (admin) | 8001 | **8101** | 8001 |
| 11 | proxy-plugin | 8086 | **8186** | 8086 |
| 12 | mock-backend | 8999 | **9099** | 8999 |
| 13 | otel-collector | 4317 | **4417** | 4317 |
| 14 | jaeger-auth | 16686 | **16786** | 4180 |
| 15 | grafana | 3003 | **3103** | 3000 |
| 16 | cAdvisor | 8088 | **8188** | 8080 |

Kong admin binds to `127.0.0.1` only (localhost-restricted), matching the primary instance.

## Usage

### Start the test namespace

```sh
make dev-test
```

Prints access URLs and the bootstrap admin password on success.

### Stop (preserves data)

```sh
make dev-test-down
```

Removes containers but keeps volumes intact — your test data persists across restarts.

### Tail logs

```sh
make dev-test-logs
```

### Full reset (destroys test data)

```sh
make dev-test-reset
```

Removes containers **and** all `mintkey-test_*` volumes. Primary instance data is unaffected.

### Run smoke tests against the test namespace

```sh
make smoke-test-ns
```

Runs the acceptance test suite against the offset ports. The test namespace must be running first.

## Verify health

```sh
curl -sf http://localhost:8180/v1/health   # admin-api
curl -sf http://localhost:8181/health       # admin-ui
curl -sf http://localhost:3103/api/health   # grafana
```

## Isolation guarantees

| Resource | Primary | Test Namespace |
|----------|---------|----------------|
| Project name | `mintkey` | `mintkey-test` |
| Host ports | Base | Base + 100 |
| Volumes | `mintkey_*` | `mintkey-test_*` |
| Network | `mintkey_mintkey` | `mintkey-test_mintkey` |
| Images | `mintkey-<svc>` | Same (shared) |

Operations on one namespace never affect the other. Tearing down the test namespace (even with `--volumes`) leaves the primary instance running and its data intact.

## Why `MINTKEY_KEYCLOAK_INTERNAL_URL` doesn't need overriding

Inside the Docker network, services reach Keycloak via the container hostname (`keycloak:8443`), not the host port. Docker Compose creates a per-project bridge network (`mintkey-test_mintkey`), so DNS resolution of `keycloak` within the test namespace resolves to the test namespace's Keycloak container — not the primary's. No internal URL override is needed.

## Memory requirements

| Configuration | RAM |
|---------------|-----|
| Single stack (primary or test) | ~4 GB |
| Both stacks simultaneously | ~8 GB |
| Recommended (dual + headroom) | **12 GB** |

Allocate at least 8 GB to Docker Desktop when running both stacks. 12 GB is recommended for comfortable operation with IDE and browser overhead.

## Troubleshooting

### Port conflicts

If a service fails to start with a "bind: address already in use" error:

```sh
# Find what's using the port (example: 8180)
lsof -i :8180
```

Common causes: another dev tool, a previous test namespace that wasn't stopped, or the primary instance if port arithmetic is wrong.

### Verifying the primary is unaffected

After any test namespace operation, confirm the primary still responds:

```sh
curl -sf http://localhost:8080/v1/health   # admin-api (primary)
curl -sf http://localhost:8081/health       # admin-ui (primary)
```

If the primary is running, these should return 200. Test namespace operations never touch primary containers or volumes.

### Shell environment variable precedence

Docker Compose resolves `${MINTKEY_*}` variables in this order:

1. Shell environment (exported vars in your terminal)
2. `--env-file` (`.env.test` for the test namespace)
3. Defaults in `docker-compose.yml`

If you have `MINTKEY_KEYCLOAK_PUBLIC_URL` exported in your shell, it will **override** the value from `.env.test`, causing SSO redirects to point to the wrong port.

**Fix:** unset any `MINTKEY_*` shell variables before running `make dev-test`, or run in a clean shell:

```sh
env -u MINTKEY_KEYCLOAK_PUBLIC_URL -u MINTKEY_ADMIN_API_PUBLIC_URL \
    -u MINTKEY_ADMIN_UI_PUBLIC_URL -u MINTKEY_MCP_PUBLIC_URL \
    -u MINTKEY_PROXY_PUBLIC_URL -u MINTKEY_GRAFANA_PUBLIC_URL \
    -u MINTKEY_JAEGER_PUBLIC_URL \
    make dev-test
```

### SSO login redirects to wrong port

This is almost always the env var precedence issue above. Verify the running container has the correct URL:

```sh
docker compose --project-name mintkey-test exec admin-api env | grep PUBLIC_URL
```

All URLs should show offset ports (8180, 8181, 8543, etc.).
