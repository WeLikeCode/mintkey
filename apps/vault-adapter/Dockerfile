# Vault Adapter — Go 1.26, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared internal/ packages).
# Pinned 2026-05-18; re-pin every quarter.
FROM golang:1.26-alpine@sha256:91eda9776261207ea25fd06b5b7fed8d397dd2c0a283e77f2ab6e91bfa71079d AS builder

WORKDIR /workspace

# Copy workspace files first for layer caching
COPY go.work go.work.sum ./
COPY go.mod go.sum ./
COPY internal/ internal/

# Copy all service go.mod/go.sum so the workspace can resolve every listed module.
COPY apps/broker/go.mod apps/broker/go.sum apps/broker/
COPY apps/kong-syncer/go.mod apps/kong-syncer/go.sum apps/kong-syncer/
COPY apps/proxy-plugin/go.mod apps/proxy-plugin/go.sum apps/proxy-plugin/
COPY apps/vault-adapter/go.mod apps/vault-adapter/go.sum apps/vault-adapter/

# Copy only this service's full source.
COPY apps/vault-adapter/ apps/vault-adapter/

WORKDIR /workspace/apps/vault-adapter
RUN go build -o /vault-adapter ./cmd/vault-adapter

# Download grpc_health_probe for distroless healthchecking.
# SHA256 digests from https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.50/checksums.txt
RUN GOARCH=$(go env GOARCH) && \
    case "${GOARCH}" in \
      amd64) SHA256="84fb8aa14a6f5467bf12144320e8e91f4e888956c3229efa7da0b8bdb10de8d2" ;; \
      arm64) SHA256="6cf28a5fa8fae69d71a12800e8702cc3f0465b6f6e804bc4268f868709ca37a5" ;; \
      *) echo "Unsupported GOARCH: ${GOARCH}" && exit 1 ;; \
    esac && \
    wget -qO /grpc_health_probe \
      "https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/v0.4.50/grpc_health_probe-linux-${GOARCH}" && \
    echo "${SHA256}  /grpc_health_probe" | sha256sum -c - && \
    chmod +x /grpc_health_probe

# Pinned 2026-05-18; re-pin every quarter.
FROM gcr.io/distroless/static-debian12@sha256:20bc6c0bc4d625a22a8fde3e55f6515709b32055ef8fb9cfbddaa06d1760f838
COPY --from=builder /vault-adapter /vault-adapter
COPY --from=builder /grpc_health_probe /grpc_health_probe
ENTRYPOINT ["/vault-adapter"]
