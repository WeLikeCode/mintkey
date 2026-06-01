# syntax=docker/dockerfile:1.6
# SSH Proxy — distroless Go binary (ADR-0011 shared Go stack).
# Build: docker build -f apps/ssh-proxy/Dockerfile -t mintkey-ssh-proxy .

FROM golang:1.22-alpine AS build
WORKDIR /src

# Cache deps
COPY apps/ssh-proxy/go.mod apps/ssh-proxy/go.sum ./apps/ssh-proxy/
COPY internal/ ./internal/
RUN cd apps/ssh-proxy && go mod download

# Build
COPY apps/ssh-proxy/ ./apps/ssh-proxy/
RUN cd apps/ssh-proxy && CGO_ENABLED=0 GOOS=linux go build -ldflags="-s -w" -o /out/ssh-proxy ./cmd/ssh-proxy

# Runtime
FROM gcr.io/distroless/static-debian12:nonroot
COPY --from=build /out/ssh-proxy /ssh-proxy
USER nonroot:nonroot
EXPOSE 2222 8087
ENTRYPOINT ["/ssh-proxy"]
