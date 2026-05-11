# Credential Broker — Go 1.22, multi-stage, distroless (ADR-0011)
# Build context must be repo root (go.work workspace includes shared internal/ packages).
FROM golang:1.22-alpine AS builder

WORKDIR /workspace

COPY go.work go.work.sum ./
COPY go.mod go.sum ./
COPY internal/ internal/

COPY services/broker/go.mod services/broker/go.sum services/broker/
COPY services/broker/ services/broker/

WORKDIR /workspace/services/broker
RUN go build -o /broker ./cmd/broker

FROM gcr.io/distroless/static-debian12
COPY --from=builder /broker /broker
ENTRYPOINT ["/broker"]
