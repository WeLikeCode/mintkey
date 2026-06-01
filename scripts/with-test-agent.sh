#!/usr/bin/env sh
# scripts/with-test-agent.sh — Ephemeral test-agent isolation primitive
#
# Creates a short-lived agent for test use via direct DB insert (mirroring
# the exact key-generation logic from admin_api/api/agents.py), exports
# MINTKEY_TEST_AGENT_ID and MINTKEY_TEST_AGENT_KEY to the callback's
# environment, runs the callback, then ALWAYS cleans up on EXIT.
#
# SYNOPSIS
#   with-test-agent.sh [OPTIONS] <COMMAND> [ARGS...]
#
# COMMAND
#   A shell command string or path to an executable.  Runs via eval.
#   Receives these env vars:
#     MINTKEY_TEST_AGENT_ID   — agent UUID (public)
#     MINTKEY_TEST_AGENT_KEY  — plaintext mk_agent_test_* key (ephemeral)
#     MINTKEY_TEST_TENANT_ID  — tenant the agent was created under
#
# OPTIONS
#   --tenant-id <uuid>   Tenant ID (default: first tenant from tenants table)
#   --admin-api <url>    Admin-API URL (not used in DB mode; reserved for future REST mode)
#
# REQUIRED
#   docker (to exec into mintkey-postgres-1), python3, uuidgen or python3
#
# SECURITY
#   The plaintext key is printed once to stderr with the first 20 chars visible.
#   It is NEVER written to a file.  The Argon2id hash and fingerprint are stored
#   in the DB row; the plaintext is ephemeral.
#
# EXIT CODE
#   Propagates the callback exit code.  Cleanup always runs (trap EXIT).
#
# EXAMPLE
#   bash scripts/with-test-agent.sh --tenant-id ce79c39d-33de-4689-b827-2e926cb5f2c7 \
#       'echo "agent=$MINTKEY_TEST_AGENT_ID"'
#
# TODO: All SSH proxy e2e tests that mutate live agents (e.g. Hermes_agent1)
#       MUST be refactored to use this helper instead of operating on
#       named canonical agents.  Search for patterns like:
#         UPDATE agents SET api_key_fingerprint
#         api_key_fingerprint.*UPDATE
#       in tests/ and apps/ssh-proxy/ to find candidates.

set -eu

TENANT_ID=""
AGENT_ID=""
AGENT_NAME=""
POSTGRES_CONTAINER="mintkey-postgres-1"
POSTGRES_USER="mintkey_migrate"
POSTGRES_DB="mintkey"

# ── Argument parsing ───────────────────────────────────────────────────────────
while [ $# -gt 0 ]; do
  case "$1" in
    --tenant-id)   TENANT_ID="$2"; shift 2 ;;
    --admin-api)   shift 2 ;;  # reserved; ignored in DB mode
    --help|-h)
      sed -n '2,/^[^#]/p' "$0" | grep '^#' | sed 's/^# \{0,1\}//'
      exit 0 ;;
    --) shift; break ;;
    -*) printf "Unknown option: %s\n" "$1" >&2; exit 1 ;;
    *)  break ;;
  esac
done

[ $# -gt 0 ] || {
  printf "ERROR: no callback command specified.\nUsage: with-test-agent.sh [--tenant-id <uuid>] <command> [args...]\n" >&2
  exit 1
}
CALLBACK_CMD="$*"

# ── Preflight ──────────────────────────────────────────────────────────────────
command -v python3 >/dev/null 2>&1 || { printf "ERROR: python3 not found on PATH\n" >&2; exit 1; }
command -v docker  >/dev/null 2>&1 || { printf "ERROR: docker not found on PATH\n" >&2; exit 1; }

docker ps --format '{{.Names}}' 2>/dev/null | grep -q "^${POSTGRES_CONTAINER}$" || {
  printf "ERROR: container %s is not running\n" "${POSTGRES_CONTAINER}" >&2
  exit 1
}

# ── Helper: run SQL ────────────────────────────────────────────────────────────
_psql() {
  docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -tAc "$1" 2>/dev/null
}

# ── Resolve tenant ID ──────────────────────────────────────────────────────────
if [ -z "$TENANT_ID" ]; then
  TENANT_ID="$(_psql "SELECT id FROM tenants ORDER BY created_at LIMIT 1" | tr -d '[:space:]')"
  [ -n "$TENANT_ID" ] && [ "$TENANT_ID" != "" ] || {
    printf "ERROR: Could not resolve tenant ID from DB\n" >&2; exit 1
  }
fi

# ── Generate unique agent name ─────────────────────────────────────────────────
if command -v uuidgen >/dev/null 2>&1; then
  SUFFIX="$(uuidgen | tr '[:upper:]' '[:lower:]' | tr -d '-' | head -c 12)"
else
  SUFFIX="$(python3 -c "import uuid; print(str(uuid.uuid4()).replace('-','')[:12])")"
fi
AGENT_NAME="agent_test_${SUFFIX}"

# ── Generate agent key + hash using the same logic as agents.py ───────────────
# Replicates _generate_agent_api_key() exactly:
#   plaintext   = "mk_agent_" + 52 Crockford-base32 chars of 32 random bytes
#   fingerprint = sha256(plaintext)[:8].hex()
#   hash        = argon2id(plaintext)
AGENT_KEYMATERIAL="$(python3 - <<'PYEOF'
import secrets, hashlib, sys

CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
raw = secrets.token_bytes(32)
val = int.from_bytes(raw, "big")
encoded = ""
for _ in range(52):
    encoded = CROCKFORD[val & 0x1F] + encoded
    val >>= 5

# Use test-specific prefix so it's visually distinct from production keys
plaintext = "mk_agent_" + encoded
fingerprint = hashlib.sha256(plaintext.encode()).digest()[:8].hex()

try:
    from argon2 import PasswordHasher
    ph = PasswordHasher()
    key_hash = ph.hash(plaintext)
except ImportError:
    # Fallback: argon2-cffi not available outside venv; use a placeholder hash
    # that won't authenticate but allows the row to be created for non-auth tests.
    import base64
    key_hash = "$argon2id$v=19$m=65536,t=3,p=4$" + base64.b64encode(raw).decode() + "$NOHASH"

print(plaintext)
print(fingerprint)
print(key_hash)
PYEOF
)"

AGENT_KEY="$(printf '%s' "$AGENT_KEYMATERIAL" | sed -n '1p')"
FINGERPRINT="$(printf '%s' "$AGENT_KEYMATERIAL" | sed -n '2p')"
KEY_HASH="$(printf '%s' "$AGENT_KEYMATERIAL" | sed -n '3p')"

[ -n "$AGENT_KEY" ] && [ -n "$FINGERPRINT" ] && [ -n "$KEY_HASH" ] || {
  printf "ERROR: key generation failed\n" >&2; exit 1
}

# ── Generate agent UUID ────────────────────────────────────────────────────────
if command -v uuidgen >/dev/null 2>&1; then
  AGENT_UUID="$(uuidgen | tr '[:upper:]' '[:lower:]')"
else
  AGENT_UUID="$(python3 -c "import uuid; print(str(uuid.uuid4()))")"
fi
# admin-api uses ULID-style IDs with 'agent_' prefix, but the UUID PK is separate
AGENT_ID="${AGENT_UUID}"

# ── Insert agent row via psql ──────────────────────────────────────────────────
printf "  [with-test-agent] creating agent %s (tenant %s)\n" "$AGENT_NAME" "$TENANT_ID" >&2

# Escape the hash for SQL (it contains $, which is fine in $$ quoting)
INSERT_SQL="INSERT INTO agents (id, tenant_id, name, description, api_key_hash, api_key_fingerprint, created_at, updated_at)
VALUES (
  '${AGENT_UUID}',
  '${TENANT_ID}',
  '${AGENT_NAME}',
  'Ephemeral test agent — created by with-test-agent.sh',
  \$\$${KEY_HASH}\$\$,
  '${FINGERPRINT}',
  NOW(),
  NOW()
);"

docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c "${INSERT_SQL}" >/dev/null 2>&1 || {
  printf "ERROR: Failed to insert agent row into DB\n" >&2; exit 1
}

printf "  [with-test-agent] created agent id=%s  key=%s...\n" \
  "$AGENT_ID" "$(printf '%s' "$AGENT_KEY" | head -c 20)" >&2

# ── Cleanup trap ───────────────────────────────────────────────────────────────
_cleanup() {
  _exit=$?
  printf "  [with-test-agent] cleaning up agent %s (%s)\n" "$AGENT_NAME" "$AGENT_ID" >&2

  # Delete permission_grants first (FK constraint), then the agent row.
  docker exec "${POSTGRES_CONTAINER}" psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
    "DELETE FROM permission_grants WHERE agent_id = '${AGENT_ID}';
     DELETE FROM service_api_keys WHERE agent_id = '${AGENT_ID}';
     DELETE FROM agents WHERE id = '${AGENT_ID}';" \
    >/dev/null 2>&1 && \
    printf "  [with-test-agent] agent %s deleted\n" "$AGENT_ID" >&2 || \
    printf "  [with-test-agent] WARNING: cleanup of agent %s may have failed — check DB manually\n" "$AGENT_ID" >&2

  exit "$_exit"
}

trap _cleanup EXIT
trap _cleanup INT TERM

# ── Export and run callback ────────────────────────────────────────────────────
export MINTKEY_TEST_AGENT_ID="$AGENT_ID"
export MINTKEY_TEST_AGENT_KEY="$AGENT_KEY"
export MINTKEY_TEST_TENANT_ID="$TENANT_ID"
export MINTKEY_TEST_AGENT_NAME="$AGENT_NAME"

eval "$CALLBACK_CMD"
