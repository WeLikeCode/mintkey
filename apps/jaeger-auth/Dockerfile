# SSO-E: Jaeger auth proxy — oauth2-proxy v7.15.2 on Alpine (shell needed to
# read the cookie secret from a volume-mounted file at startup).
# The upstream distroless image has no shell; we copy the binary onto Alpine
# so that entrypoint.sh can read the bootstrap secret and exec into it.

# Pinned 2026-05-18; re-pin every quarter.
FROM quay.io/oauth2-proxy/oauth2-proxy:v7.15.4@sha256:b1b2021fe8f4004573e8d690dec6c7bb29cc44364572cf8510a05bf3a0ae2ded AS proxy

# Pinned 2026-05-18; re-pin every quarter.
FROM alpine:3.24@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b

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
