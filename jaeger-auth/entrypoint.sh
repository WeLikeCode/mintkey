#!/bin/sh
# SSO-E: oauth2-proxy entrypoint — passes cookie secret file path directly to
# oauth2-proxy via --cookie-secret-file (supported since v7; binary-safe).
# The seed-job writes 32 raw random bytes; shell variables cannot hold binary
# data (null bytes truncate the value), so we never read the file contents here.
set -e

COOKIE_SECRET_FILE="/run/secrets/mintkey/bootstrap-secrets/jaeger_oauth2_cookie_secret"

if [ ! -f "${COOKIE_SECRET_FILE}" ]; then
  echo "ERROR: cookie secret file not found: ${COOKIE_SECRET_FILE}" >&2
  exit 1
fi

exec /bin/oauth2-proxy --cookie-secret-file="${COOKIE_SECRET_FILE}" "$@"
