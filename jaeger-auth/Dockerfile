# SSO-E: Jaeger auth proxy — oauth2-proxy v7.6.0 on Alpine (shell needed to
# read the cookie secret from a volume-mounted file at startup).
# The upstream distroless image has no shell; we copy the binary onto Alpine
# so that entrypoint.sh can read the bootstrap secret and exec into it.

# Pinned 2026-05-18; re-pin every quarter.
FROM quay.io/oauth2-proxy/oauth2-proxy:v7.15.2@sha256:aa0bd8dd5ab0c78e4c91c92755ad573a5f92241f88138b4141b8ec803463b4fd AS proxy

# Pinned 2026-05-18; re-pin every quarter.
FROM alpine:3.23@sha256:5b10f432ef3da1b8d4c7eb6c487f2f5a8f096bc91145e68878dd4a5019afde11

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
