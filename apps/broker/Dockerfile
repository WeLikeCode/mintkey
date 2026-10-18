# Credential Broker — Go 1.27, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared packages/go/ packages).
# Pinned 2026-05-18; re-pin every quarter.
FROM golang:1.27-alpine@sha256:f92b6ef800e499660581efdabdf25d9d817a9d124eaf900924f0504e7e27e12d AS builder

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
COPY apps/broker/ apps/broker/

WORKDIR /workspace/apps/broker
RUN go build -o /broker ./cmd/broker

# Pinned 2026-06-19; re-pin every quarter.
FROM gcr.io/distroless/static-debian12@sha256:d75cdd72874d4790092fcb1b058493ecf6bb5bf2b2b897045b00ff01d91843f2
COPY --from=busybox:musl /bin/wget /wget
COPY --from=builder /broker /broker
ENTRYPOINT ["/broker"]
