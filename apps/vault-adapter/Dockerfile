# Vault Adapter — Go 1.26, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared packages/go/ packages).
# Pinned 2026-05-18; re-pin every quarter.
FROM golang:1.27-alpine@sha256:f92b6ef800e499660581efdabdf25d9d817a9d124eaf900924f0504e7e27e12d AS builder

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
# builder image (Go 1.26.9), avoiding the stdlib CVEs of any pre-built binary.
# Use a throwaway module to pin golang.org/x/net, x/text and google.golang.org/grpc
# to the versions the services use, overriding grpc-health-probe's own go.mod
# (2026-10: CVE-2026-46600, CVE-2026-56852, CVE-2026-78669, CVE-2026-84304, CVE-2026-84445).
RUN mkdir -p /tmp/grpc-build && cd /tmp/grpc-build && \
    printf 'module grpc-build\ngo 1.26\n' > go.mod && \
    GOWORK=off go get github.com/grpc-ecosystem/grpc-health-probe@v0.4.59 golang.org/x/net@v0.61.0 \
        golang.org/x/text@v0.43.0 google.golang.org/grpc@v1.84.0 && \
    GOWORK=off go build -o /grpc_health_probe github.com/grpc-ecosystem/grpc-health-probe/... && \
    chmod +x /grpc_health_probe

# Pinned 2026-06-19; re-pin every quarter.
FROM gcr.io/distroless/static-debian12@sha256:d75cdd72874d4790092fcb1b058493ecf6bb5bf2b2b897045b00ff01d91843f2
COPY --from=builder /vault-adapter /vault-adapter
COPY --from=builder /grpc_health_probe /grpc_health_probe
ENTRYPOINT ["/vault-adapter"]
