# Kong Syncer — Go 1.26, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared internal/ packages).
# Pinned 2026-05-18; re-pin every quarter.
FROM golang:1.26-alpine@sha256:91eda9776261207ea25fd06b5b7fed8d397dd2c0a283e77f2ab6e91bfa71079d AS builder

WORKDIR /workspace

COPY go.work go.work.sum ./
COPY go.mod go.sum ./
COPY internal/ internal/

# Copy all service go.mod/go.sum so the workspace can resolve every listed module.
COPY services/broker/go.mod services/broker/go.sum services/broker/
COPY services/kong-syncer/go.mod services/kong-syncer/go.sum services/kong-syncer/
COPY services/proxy-plugin/go.mod services/proxy-plugin/go.sum services/proxy-plugin/
COPY services/vault-adapter/go.mod services/vault-adapter/go.sum services/vault-adapter/

# Copy only this service's full source.
COPY services/kong-syncer/ services/kong-syncer/

WORKDIR /workspace/services/kong-syncer
RUN go build -o /kong-syncer ./cmd/kong-syncer

# Pinned 2026-05-18; re-pin every quarter.
FROM gcr.io/distroless/static-debian12@sha256:9c346e4be81b5ca7ff31a0d89eaeade58b0f95cfd3baed1f36083ddb47ca3160
COPY --from=busybox:musl /bin/wget /wget
COPY --from=builder /kong-syncer /kong-syncer
ENTRYPOINT ["/kong-syncer"]
