# SSO-E: Jaeger auth proxy — oauth2-proxy v7.15.6 on Alpine (shell needed to
# read the cookie secret from a volume-mounted file at startup).
# The upstream distroless image has no shell; we put the binary onto Alpine
# so that entrypoint.sh can read the bootstrap secret and exec into it.

# oauth2-proxy is built from source (the same pattern as vault-adapter's grpc_health_probe), so that it carries the
# builder's Go 1.27.4 and golang.org/x/net v0.62.0: the upstream v7.15.5 binary is built with Go 1.26.8 and x/net
# v0.59.0 (2026-10: CVE-2026-78667, CVE-2026-78669, CVE-2026-97031, all HIGH, denial of service on the HTTP/2,
# Range-header and TLS paths this proxy serves). Upstream has no replace directives, so only x/net and what
# it requires move. Go back to the upstream image once it ships a build with a fixed Go.
# 2026-11: v7.15.6 no longer imports github.com/go-jose/go-jose/v3 (CVE-2026-116587, no fixed v3 release exists;
# v7.15.5 compiled it in) and resolves go-jose/v4 to 4.1.8.
# Pinned 2026-11-22; re-pin every quarter.
FROM golang:1.27-alpine@sha256:70bd7ddea8b6cbe5d6943cde279d6b67feb10cc924fb9100d1d8757c1575b280 AS proxy
RUN mkdir -p /tmp/build && cd /tmp/build && \
    printf 'module oauth2-proxy-build\ngo 1.26\n' > go.mod && \
    GOWORK=off go get github.com/oauth2-proxy/oauth2-proxy/v7@v7.15.6 golang.org/x/net@v0.62.0 && \
    CGO_ENABLED=0 GOWORK=off go build -trimpath \
      -ldflags "-s -w -X github.com/oauth2-proxy/oauth2-proxy/v7/pkg/version.VERSION=v7.15.6" \
      -o /bin/oauth2-proxy github.com/oauth2-proxy/oauth2-proxy/v7

# Pinned 2026-10-17; re-pin every quarter.
FROM alpine:3.24@sha256:f59abe656b692d901e184be3445e084786602108599d2a51d229c0f5a48c71bf

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
