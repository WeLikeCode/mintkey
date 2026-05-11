# Vault Adapter — Go 1.26, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared internal/ packages).
FROM golang:1.26-alpine AS builder

WORKDIR /workspace

# Copy workspace files first for layer caching
COPY go.work go.work.sum ./
COPY go.mod go.sum ./
COPY internal/ internal/

# Copy all service go.mod/go.sum so the workspace can resolve every listed module.
COPY services/broker/go.mod services/broker/go.sum services/broker/
COPY services/kong-syncer/go.mod services/kong-syncer/go.sum services/kong-syncer/
COPY services/proxy-plugin/go.mod services/proxy-plugin/go.sum services/proxy-plugin/
COPY services/vault-adapter/go.mod services/vault-adapter/go.sum services/vault-adapter/

# Copy only this service's full source.
COPY services/vault-adapter/ services/vault-adapter/

WORKDIR /workspace/services/vault-adapter
RUN go build -o /vault-adapter ./cmd/vault-adapter

# Download grpc_health_probe for distroless healthchecking.
RUN GOARCH=$(go env GOARCH) && \
    wget -qO /grpc_health_probe \
      "https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.28/grpc_health_probe-linux-${GOARCH}" && \
    chmod +x /grpc_health_probe

FROM gcr.io/distroless/static-debian12
COPY --from=builder /vault-adapter /vault-adapter
COPY --from=builder /grpc_health_probe /grpc_health_probe
ENTRYPOINT ["/vault-adapter"]
