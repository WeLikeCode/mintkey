#!/bin/sh
# SSO-E: oauth2-proxy entrypoint — reads cookie secret from file at runtime.
# The distroless quay.io/oauth2-proxy image has no shell, so we layer oauth2-proxy
# on top of Alpine and exec it here after loading the file-backed secret.
set -e

COOKIE_SECRET_FILE="/run/secrets/mintkey/bootstrap-secrets/jaeger_oauth2_cookie_secret"

if [ ! -f "${COOKIE_SECRET_FILE}" ]; then
  echo "ERROR: cookie secret file not found: ${COOKIE_SECRET_FILE}" >&2
  exit 1
fi

# oauth2-proxy requires the cookie secret as a 16/24/32-byte value.
# The seed-job writes a 32-byte hex string (64 hex chars); we base64-encode it
# so oauth2-proxy receives the 32 raw bytes in the format it expects.
COOKIE_SECRET_HEX="$(cat "${COOKIE_SECRET_FILE}")"
export OAUTH2_PROXY_COOKIE_SECRET="$(printf '%s' "${COOKIE_SECRET_HEX}" | xxd -r -p | base64)"

exec /bin/oauth2-proxy "$@"
