# ADR‑0011: Shared Go stack for Broker, Vault Adapter, Kong‑syncer, and Egress Proxy plugin

## Status
Accepted — 2026-05-10.

## Context
Four Mintkey containers are written in Go:
- **Credential Broker (C5)** — JWT issuer per [ADR‑0006](0006-token-format-and-binding.md).
- **Vault Adapter (C6)** — credential storage per [ADR‑0003](0003-credential-storage-strategy.md).
- **Kong‑syncer** — declarative YAML pusher per [ADR‑0004](0004-egress-proxy-kong.md).
- **Egress Proxy plugin** — Kong `go-pdk` plugin per [ADR‑0004](0004-egress-proxy-kong.md).

All four share infrastructure: HTTP/gRPC, observability, configuration, logging, DB access (where applicable), and the change‑channel client. Pinning these shared libraries in one ADR avoids per‑container rediscovery and keeps the Go services consistent.

## Decision

### Shared library set

| Concern                  | Choice                                                                       | Rationale |
|--------------------------|------------------------------------------------------------------------------|-----------|
| Go version               | **Go 1.22+**                                                                 | `slog` stdlib, range‑over‑func, broad library support |
| Module structure         | **Go workspace** (`go.work`) at the repo root; one Go module per service under `services/<name>/` plus a shared `internal/` module | Monorepo with shared packages without `replace` directives |
| Configuration            | **`caarlos0/env/v10`** (env vars only)                                       | 12‑factor; no config‑file complexity |
| Logger                   | **stdlib `log/slog`** with JSON handler                                       | No third‑party logger; structured; OTel‑correlated |
| OTel SDK                 | `go.opentelemetry.io/otel` + `otelhttp` + `otelgrpc` + `otelpgx`              | Vendor‑neutral, well‑instrumented |
| HTTP framework           | stdlib `net/http` + **`go-chi/chi/v5`** for routing                            | Minimal; idiomatic |
| gRPC                     | **`google.golang.org/grpc`** + `protoc-gen-go` + `protoc-gen-go-grpc`         | Standard |
| Postgres driver          | **`jackc/pgx/v5`**                                                            | Best‑in‑class; native `LISTEN/NOTIFY` support |
| Type‑safe queries        | **`sqlc`** for codegen from raw SQL                                           | Schema‑first matches Liquibase posture |
| JWT (sign + verify)      | **`go-jose/go-jose/v4`**                                                       | EdDSA (Ed25519) native, mature |
| Encryption (Vault)       | stdlib `crypto/cipher` (AES‑256‑GCM) + `crypto/rand` for nonces               | No third‑party crypto code |
| Vault file format (v1)   | **SQLite** via `modernc.org/sqlite` (pure Go; no CGO)                         | Atomic transactions for rotate; queryable; no CGO ⇒ trivial container builds |
| Change‑channel client    | small `internal/changes` package wrapping `pgx.Conn.WaitForNotification`       | Per [ADR‑0010](0010-change-channel-postgres-listen-notify.md) |
| Audit emission           | small `internal/audit` package (single‑function helper)                        | Enforces the audit chokepoint pattern from [ADR‑0001](0001-record-architecture-decisions.md) |
| ULID                     | **`oklog/ulid/v2`**                                                            | The Mintkey ID convention |
| Testing                  | stdlib `testing` + **`stretchr/testify`** + **`testcontainers-go`**            | Postgres + Kong + Keycloak via testcontainers |
| Linting                  | **`golangci-lint`** with `errcheck`, `goimports`, `revive`, `gosec`, `govet`, `gocyclo`, `gocritic` | Comprehensive |
| Code generation          | `sqlc generate`, `protoc`, `mockery` for service‑boundary mocks                | Build‑time |
| Dependency management    | Go modules + Renovate                                                          | Standard |
| Container image          | multi‑stage build → **`gcr.io/distroless/static-debian12:nonroot`**            | Minimal attack surface |

### Per‑container specifics

These are small additions on top of the shared stack; none warrants its own ADR.

**Credential Broker (C5)**
- `go-jose/v4` for EdDSA signing.
- Private key loaded at startup from the Vault Adapter (gRPC) under credential type `signing_key`.
- Exposes JWKS at `/.well-known/jwks.json`.
- Subscribes to the change channel for `agent.revoked` and `token.revoked`.

**Vault Adapter (C6)**
- SQLite for the v1 file backend.
- AES‑256‑GCM envelope: per‑credential DEK, KEK from keyfile (preferred) or env (per [ADR‑0003](0003-credential-storage-strategy.md)).
- Exposes gRPC service `VaultAdapter` (IDL in `docs/contracts/vault-adapter/vault.proto`).
- Multi‑tenant: `tenant_id` is part of the lookup key per [ADR‑0008](0008-multi-tenancy-row-level-with-db-tier.md).
- Plaintext zeroized after each request scope.

**Kong‑syncer**
- Subscribes to `mintkey:*:service` and `mintkey:*:agent` channels (or per‑tenant subset).
- Generates declarative YAML (Kong DB‑less) and POSTs to Kong's `/config` endpoint.
- Tenant‑scoped routes per [ADR‑0008](0008-multi-tenancy-row-level-with-db-tier.md) and [ADR‑0007](0007-proxy-deployment-topology.md).

**Egress Proxy plugin (Kong `go-pdk`)**
- Uses `Kong/go-pdk` for the plugin framework.
- Subscribes to the change channel for cache invalidation.
- Plaintext credential cache keyed by `(tenant_id, service_id, key_version)` with TTL ≤ JWT TTL.
- Calls the Vault Adapter via gRPC on cache miss.

### Project layout (repo root)

```
go.work
internal/
  changes/     # change-channel client (publisher + subscriber)
  models/      # shared Go structs, mirroring mintkey-models in Python
  ulid/        # ULID helpers + prefix conventions
  audit/       # audit emission helpers
  otelinit/    # OTel bootstrap (resource, exporter, propagator)
  cfg/         # config struct + env loader
services/
  broker/
    cmd/broker/main.go
    internal/...
    Dockerfile
  vault-adapter/
    cmd/vault-adapter/main.go
    internal/...
    Dockerfile
  kong-syncer/
    cmd/kong-syncer/main.go
    internal/...
    Dockerfile
  proxy-plugin/
    cmd/proxy-plugin/main.go
    internal/...
    Dockerfile
contracts/        # symlink to docs/contracts/ for proto/JSON schema build inputs
```

### Versions
Specific versions pinned at the time of acceptance; Renovate handles drift:
- Go 1.22 (or current stable when implementation begins).
- `pgx/v5`, `chi/v5`, `go-jose/v4`, `caarlos0/env/v10`, `testify`, `testcontainers-go`, `modernc.org/sqlite`, `oklog/ulid/v2` — latest stable.
- `Kong/go-pdk` matched to Kong 3.x.
- `golangci-lint` latest stable; config checked into the repo.

## Consequences

### Positive
- Four Go services share the same library tree → faster onboarding, consistent upgrades, easier security patching.
- Go workspace lets us iterate on shared `internal/` packages without versioning friction.
- `slog` stdlib means no logger‑library Babel.
- `sqlc` enforces schema‑first; matches the Liquibase posture; type‑safety from compile time.
- `pgx`'s native `LISTEN/NOTIFY` pairs perfectly with [ADR‑0010](0010-change-channel-postgres-listen-notify.md).
- Pure‑Go SQLite avoids CGO complications in distroless container builds.
- Distroless images shrink the attack surface in line with the threat model (proxy plugin runs in the data‑plane node).

### Costs
- Go workspace requires Go 1.21+; teams used to vendor or per‑repo modules need a small adjustment.
- Renovate config must understand the workspace; minor effort.

### Risks
- `modernc.org/sqlite` (pure Go) is somewhat slower than CGO `mattn/go-sqlite3`; acceptable at our credentials volume (low write rate, low row count).
- `sqlc` doesn't yet support every advanced Postgres feature (e.g., complex CTEs); workaround is hand‑written queries with `pgx` directly.
- `go-jose/v4` is the chosen JWT lib; if it ever drops EdDSA support (very unlikely) we re‑platform to `golang-jwt/jwt/v5` with a minor effort.

## Implications
- Every Go service uses the same Dockerfile pattern (multi‑stage Go 1.22 build → distroless final).
- Every Go service emits OTel via the same bootstrap (`internal/otelinit`).
- The shared `internal/changes` is the only package that talks to the change channel.
- [`02-container-view.md`](../02-container-view.md) doesn't change; this ADR is implementation detail.
- Iteration 4 contracts include the proto IDL for the Vault Adapter (subagent producing those now).

## Open follow‑ups
- Lock the exact Go version once implementation begins (1.22 vs 1.23).
- Mockery vs. handwritten test doubles for service‑to‑service tests. *Lean: handwritten for clarity at our small scope.*
- `go-jose/v4` exclusively, or also `golang-jwt/v5` for verification on the proxy side. *Lean: go‑jose for both signing and verification, single library.*
- Build cache strategy in CI (Go module cache, `golangci-lint` cache, sqlc output cache).

## Related
- [ADR‑0003 credential storage](0003-credential-storage-strategy.md) — Vault Adapter implementation.
- [ADR‑0004 egress proxy Kong](0004-egress-proxy-kong.md) — proxy plugin and Kong‑syncer.
- [ADR‑0006 token format](0006-token-format-and-binding.md) — Broker JWT signing.
- [ADR‑0008 multi‑tenancy](0008-multi-tenancy-row-level-with-db-tier.md) — `tenant_id` everywhere.
- [ADR‑0010 change channel](0010-change-channel-postgres-listen-notify.md) — `pgx` LISTEN/NOTIFY.
