# Egress Proxy Plugin — Go 1.22, multi-stage, distroless (ADR-0004, ADR-0011)
# Build context must be repo root (go.work workspace includes shared internal/ packages).
FROM golang:1.22-alpine AS builder

WORKDIR /workspace

COPY go.work go.work.sum ./
COPY go.mod go.sum ./
COPY internal/ internal/

COPY services/proxy-plugin/go.mod services/proxy-plugin/
COPY services/proxy-plugin/ services/proxy-plugin/

WORKDIR /workspace/services/proxy-plugin
RUN go build -o /proxy-plugin ./cmd/proxy-plugin

FROM gcr.io/distroless/static-debian12
COPY --from=builder /proxy-plugin /proxy-plugin
ENTRYPOINT ["/proxy-plugin"]
