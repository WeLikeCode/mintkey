# Kong Syncer — Go 1.22, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared internal/ packages).
FROM golang:1.22-alpine AS builder

WORKDIR /workspace

COPY go.work go.work.sum ./
COPY go.mod go.sum ./
COPY internal/ internal/

COPY services/kong-syncer/go.mod services/kong-syncer/
COPY services/kong-syncer/ services/kong-syncer/

WORKDIR /workspace/services/kong-syncer
RUN go build -o /kong-syncer ./cmd/kong-syncer

FROM gcr.io/distroless/static-debian12
COPY --from=builder /kong-syncer /kong-syncer
ENTRYPOINT ["/kong-syncer"]
