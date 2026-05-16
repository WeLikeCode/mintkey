# SSO-E: Jaeger auth proxy — oauth2-proxy v7.6.0 on Alpine (shell needed to
# read the cookie secret from a volume-mounted file at startup).
# The upstream distroless image has no shell; we copy the binary onto Alpine
# so that entrypoint.sh can read the bootstrap secret and exec into it.

FROM quay.io/oauth2-proxy/oauth2-proxy:v7.6.0 AS proxy

FROM alpine:3.19

# xxd is in util-linux-misc (or vim) on Alpine; use busybox xxd alternative
# Actually busybox xxd is available via the xxd package in Alpine 3.16+
RUN apk add --no-cache xxd

COPY --from=proxy /bin/oauth2-proxy /bin/oauth2-proxy
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
