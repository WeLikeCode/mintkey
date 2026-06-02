# syntax=docker/dockerfile:1.6
# SSH Proxy — Go 1.26, multi-stage, distroless (ADR-0011 shared Go stack).
# Build context must be repo root so the workspace can resolve packages/go/ deps.
#
# Build via compose: docker compose --env-file .env -f infra/compose/docker-compose.yml build ssh-proxy
# Or from repo root: docker build -f apps/ssh-proxy/Dockerfile -t mintkey-ssh-proxy .

# Pinned 2026-06-01; re-pin every quarter.
FROM golang:1.26-alpine@sha256:91eda9776261207ea25fd06b5b7fed8d397dd2c0a283e77f2ab6e91bfa71079d AS builder

WORKDIR /workspace

# Workspace metadata + shared packages first (cache layer).
COPY go.work go.work.sum ./
COPY go.mod go.sum ./
COPY packages/go/ packages/go/

# Each workspace service's go.mod/go.sum is needed for module resolution.
COPY apps/broker/go.mod apps/broker/go.sum apps/broker/
COPY apps/email-proxy/go.mod apps/email-proxy/go.sum apps/email-proxy/
COPY apps/kong-syncer/go.mod apps/kong-syncer/go.sum apps/kong-syncer/
COPY apps/proxy-plugin/go.mod apps/proxy-plugin/go.sum apps/proxy-plugin/
COPY apps/ssh-proxy/go.mod apps/ssh-proxy/go.sum apps/ssh-proxy/
COPY apps/vault-adapter/go.mod apps/vault-adapter/go.sum apps/vault-adapter/

# Only this service's full source.
COPY apps/ssh-proxy/ apps/ssh-proxy/

WORKDIR /workspace/apps/ssh-proxy
RUN CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /ssh-proxy ./cmd/ssh-proxy

# Runtime — pinned 2026-06-01; re-pin every quarter.
FROM gcr.io/distroless/static-debian12@sha256:9c346e4be81b5ca7ff31a0d89eaeade58b0f95cfd3baed1f36083ddb47ca3160
COPY --from=builder /ssh-proxy /ssh-proxy
USER nonroot:nonroot
EXPOSE 2222 8087
ENTRYPOINT ["/ssh-proxy"]
