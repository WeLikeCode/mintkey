# Vault Adapter — Go 1.26, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared packages/go/ packages).
# Pinned 2026-05-18; re-pin every quarter.
FROM golang:1.27-alpine@sha256:4c9fe60190a2a3350ddc51de80d0224b8a6698d12bdfc999fee45ea9d6c46dbc AS builder

WORKDIR /workspace

# Copy workspace files first for layer caching
COPY go.work go.work.sum ./
COPY go.mod go.sum ./
COPY packages/go/ packages/go/

# Copy all service go.mod/go.sum so the workspace can resolve every listed module.
COPY apps/broker/go.mod apps/broker/go.sum apps/broker/
COPY apps/email-proxy/go.mod apps/email-proxy/go.sum apps/email-proxy/
COPY apps/kong-syncer/go.mod apps/kong-syncer/go.sum apps/kong-syncer/
COPY apps/proxy-plugin/go.mod apps/proxy-plugin/go.sum apps/proxy-plugin/
COPY apps/ssh-proxy/go.mod apps/ssh-proxy/go.sum apps/ssh-proxy/
COPY apps/vault-adapter/go.mod apps/vault-adapter/go.sum apps/vault-adapter/

# Copy only this service's full source.
COPY apps/vault-adapter/ apps/vault-adapter/

WORKDIR /workspace/apps/vault-adapter
RUN go build -o /vault-adapter ./cmd/vault-adapter

# Build grpc_health_probe from source so it inherits the same Go stdlib as the
# builder image (Go 1.26.4), avoiding CVE-2026-42504 in any pre-built binary.
# Use a throwaway module to pin golang.org/x/net >= v0.55.0, overriding the
# v0.53.0 pinned in grpc-health-probe's own go.mod (CVE-2026-25680 et al).
RUN mkdir -p /tmp/grpc-build && cd /tmp/grpc-build && \
    printf 'module grpc-build\ngo 1.26\n' > go.mod && \
    GOWORK=off go get github.com/grpc-ecosystem/grpc-health-probe@v0.4.50 golang.org/x/net@v0.55.0 && \
    GOWORK=off go build -o /grpc_health_probe github.com/grpc-ecosystem/grpc-health-probe/... && \
    chmod +x /grpc_health_probe

# Pinned 2026-06-19; re-pin every quarter.
FROM gcr.io/distroless/static-debian12@sha256:9c346e4be81b5ca7ff31a0d89eaeade58b0f95cfd3baed1f36083ddb47ca3160
COPY --from=builder /vault-adapter /vault-adapter
COPY --from=builder /grpc_health_probe /grpc_health_probe
ENTRYPOINT ["/vault-adapter"]
