# Kong Syncer — Go 1.26, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared packages/go/ packages).
# Pinned 2026-05-18; re-pin every quarter.
FROM golang:1.26-alpine@sha256:f23e8b227fb4493eabe03bede4d5a32d04092da71962f1fb79b5f7d1e6c2a17f AS builder

WORKDIR /workspace

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
COPY apps/kong-syncer/ apps/kong-syncer/

WORKDIR /workspace/apps/kong-syncer
RUN go build -o /kong-syncer ./cmd/kong-syncer

# Pinned 2026-05-18; re-pin every quarter.
FROM gcr.io/distroless/static-debian12@sha256:9c346e4be81b5ca7ff31a0d89eaeade58b0f95cfd3baed1f36083ddb47ca3160
COPY --from=busybox:musl /bin/wget /wget
COPY --from=builder /kong-syncer /kong-syncer
ENTRYPOINT ["/kong-syncer"]
