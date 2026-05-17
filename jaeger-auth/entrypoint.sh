#!/bin/sh
# SSO-E: oauth2-proxy entrypoint — reads the base64-encoded cookie secret and
# passes it via --cookie-secret (the only supported flag in v7.6.0; the
# --cookie-secret-file flag does not exist in this version).
#
# The seed-job writes urlsafe-base64 of 32 random bytes (44 ASCII chars, no
# null bytes), so reading with `cat` is safe.  oauth2-proxy auto-decodes a
# 44-char base64 value to 32 raw bytes (AES-256) at startup.
set -e

COOKIE_SECRET_FILE="/run/secrets/mintkey/bootstrap-secrets/jaeger_oauth2_cookie_secret"

if [ ! -f "${COOKIE_SECRET_FILE}" ]; then
  echo "ERROR: cookie secret file not found: ${COOKIE_SECRET_FILE}" >&2
  exit 1
fi

COOKIE_SECRET=$(cat "$COOKIE_SECRET_FILE")
# --code-challenge-method=S256 required because the Keycloak realm enforces
# PKCE S256 on the mintkey-jaeger client (seed-job _enforce_pkce_on_clients).
exec /bin/oauth2-proxy --cookie-secret="$COOKIE_SECRET" --code-challenge-method=S256 "$@"
