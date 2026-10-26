# SSO-E: Jaeger auth proxy — oauth2-proxy v7.15.5 on Alpine (shell needed to
# read the cookie secret from a volume-mounted file at startup).
# The upstream distroless image has no shell; we put the binary onto Alpine
# so that entrypoint.sh can read the bootstrap secret and exec into it.

# oauth2-proxy is built from source (the same pattern as vault-adapter's grpc_health_probe), so that it carries the
# builder's Go 1.27.2 and golang.org/x/net v0.61.0: the upstream v7.15.5 binary is built with Go 1.26.8 and x/net
# v0.59.0 (2026-10: CVE-2026-78667, CVE-2026-78669, CVE-2026-97031, all HIGH, denial of service on the HTTP/2,
# Range-header and TLS paths this proxy serves). Upstream v7.15.5 has no replace directives, so only x/net and what
# it requires move. Go back to the upstream image once it ships a build with a fixed Go.
# Pinned 2026-10-17; re-pin every quarter.
FROM golang:1.27-alpine@sha256:f92b6ef800e499660581efdabdf25d9d817a9d124eaf900924f0504e7e27e12d AS proxy
RUN mkdir -p /tmp/build && cd /tmp/build && \
    printf 'module oauth2-proxy-build\ngo 1.26\n' > go.mod && \
    GOWORK=off go get github.com/oauth2-proxy/oauth2-proxy/v7@v7.15.5 golang.org/x/net@v0.61.0 && \
    CGO_ENABLED=0 GOWORK=off go build -trimpath \
      -ldflags "-s -w -X github.com/oauth2-proxy/oauth2-proxy/v7/pkg/version.VERSION=v7.15.5" \
      -o /bin/oauth2-proxy github.com/oauth2-proxy/oauth2-proxy/v7

# Pinned 2026-10-17; re-pin every quarter.
FROM alpine:3.24@sha256:be2656061b536c1883c4034790e21d0a09c5aaaf51968b89368a3c0371ea2c9a

# wget is needed for the HEALTHCHECK; xxd is no longer needed (cookie secret
# is passed via --cookie-secret-file, not read/decoded in the entrypoint).
RUN apk add --no-cache wget

COPY --from=proxy /bin/oauth2-proxy /bin/oauth2-proxy
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Run as non-root (UID 65532 matches distroless nonroot convention for consistency)
RUN adduser -D -u 65532 -s /sbin/nologin oauth2proxy
USER 65532:65532

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:4180/ping || exit 1

ENTRYPOINT ["/entrypoint.sh"]
