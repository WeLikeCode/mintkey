# Vault Adapter — Go 1.22, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared internal/ packages).
FROM golang:1.22-alpine AS builder

WORKDIR /workspace

# Copy workspace files first for layer caching
COPY go.work go.work.sum ./
COPY go.mod go.sum ./
COPY internal/ internal/

COPY services/vault-adapter/go.mod services/vault-adapter/go.sum services/vault-adapter/
COPY services/vault-adapter/ services/vault-adapter/

WORKDIR /workspace/services/vault-adapter
RUN go build -o /vault-adapter ./cmd/vault-adapter

FROM gcr.io/distroless/static-debian12
COPY --from=builder /vault-adapter /vault-adapter
ENTRYPOINT ["/vault-adapter"]
