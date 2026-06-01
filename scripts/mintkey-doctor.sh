#!/usr/bin/env bash
# scripts/mintkey-doctor.sh — Mintkey stack consistency checks
#
# Verifies the live local stack against known-good invariants.
# Safe to re-run; read-only, no side effects.
#
# Exit 0: all green.  Exit 1: any red.
#
# Usage: bash scripts/mintkey-doctor.sh
#        (also called by tools/doctor.sh as section [6/6])

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ERRORS=0
WARNINGS=0

# ── Color helpers ──────────────────────────────────────────────────────────────
_color_supported() {
  [ -t 1 ] && command -v tput >/dev/null 2>&1
}

GREEN=""
YELLOW=""
RED=""
RESET=""
if _color_supported; then
  GREEN="$(tput setaf 2)"
  YELLOW="$(tput setaf 3)"
  RED="$(tput setaf 1)"
  RESET="$(tput sgr0)"
fi

pass()  { printf "${GREEN}  ✓ %s${RESET}\n" "$1"; }
warn()  { printf "${YELLOW}  ⚠ %s${RESET}\n" "$1"; WARNINGS=$((WARNINGS+1)); }
fail()  { printf "${RED}  ✗ %s${RESET}\n"  "$1"; ERRORS=$((ERRORS+1)); }
info()  { printf "    %s\n" "$1"; }

# ── Helper: run SQL against the compose postgres container ─────────────────────
# Usage: _psql "SELECT ..."  → stdout of psql, exits non-zero on psql error
_psql() {
  docker exec mintkey-postgres-1 psql -U mintkey_migrate -d mintkey -tAc "$1" 2>/dev/null
}

echo ""
echo "=== Mintkey stack — Doctor ==="
echo ""

# ── [a] Registered MCP key resolves to a live agent ───────────────────────────
echo "[a] Registered MCP agent key"

if ! command -v claude >/dev/null 2>&1; then
  warn "claude CLI not found; skipping MCP key check"
else
  # Extract the mk_agent_* key from `claude mcp get mintkey` output
  MK_KEY="$(claude mcp get mintkey 2>/dev/null | grep -oE 'mk_agent_[A-Za-z0-9]+' | head -1 || true)"

  if [ -z "$MK_KEY" ]; then
    fail "Could not read mk_agent_* key from 'claude mcp get mintkey' — server not configured?"
  else
    # Compute SHA-256[:8] fingerprint exactly as admin-api does (agents.py line ~114):
    #   hashlib.sha256(plaintext.encode()).digest()[:8].hex()
    FINGERPRINT="$(python3 -c "import hashlib; print(hashlib.sha256('${MK_KEY}'.encode()).digest()[:8].hex())")"

    if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'mintkey-postgres-1'; then
      warn "mintkey-postgres-1 not running; skipping DB fingerprint check"
    else
      AGENT_NAME="$(_psql "SELECT name FROM agents WHERE api_key_fingerprint = '${FINGERPRINT}'" 2>/dev/null | tr -d '[:space:]' || true)"
      if [ -z "$AGENT_NAME" ]; then
        fail "Registered MCP key (fingerprint ${FINGERPRINT}) does NOT match any agent in the DB — key has drifted! Run: make fix-mcp-key or rotate the registered key."
      else
        pass "Registered MCP key binds to agent '${AGENT_NAME}' (fingerprint ${FINGERPRINT})"
      fi
    fi
  fi
fi

# ── [b] Vault-adapter service identities are configured ───────────────────────
echo ""
echo "[b] Vault-adapter service identity tokens"

VAULT_CONTAINER="mintkey-vault-adapter-1"
if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q "${VAULT_CONTAINER}"; then
  fail "vault-adapter container (${VAULT_CONTAINER}) is not running"
else
  # Check each of the three expected token env vars inside the running container
  for token_var in MINTKEY_VAULT_ADMIN_TOKEN MINTKEY_VAULT_PROXY_TOKEN MINTKEY_VAULT_SSH_PROXY_TOKEN; do
    val="$(docker exec "${VAULT_CONTAINER}" printenv "${token_var}" 2>/dev/null || true)"
    if [ -z "$val" ]; then
      fail "vault-adapter: ${token_var} is not set — service credential operations will fail with PERMISSION_DENIED"
    else
      pass "vault-adapter: ${token_var} is set (${#val} chars)"
    fi
  done
fi

# ── [c] No orphan SSH credentials with missing target_address / ssh_user ───────
echo ""
echo "[c] SSH credentials completeness (auth_scheme IN (11,13))"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'mintkey-postgres-1'; then
  warn "mintkey-postgres-1 not running; skipping vault credential check"
else
  BAD_CREDS="$(_psql "SELECT count(*) FROM vault.credentials WHERE auth_scheme IN (11,13) AND (target_address = '' OR ssh_user = '')" 2>/dev/null | tr -d '[:space:]' || echo "ERROR")"
  if [ "$BAD_CREDS" = "ERROR" ]; then
    warn "Could not query vault.credentials (schema might be missing)"
  elif [ "$BAD_CREDS" -gt 0 ] 2>/dev/null; then
    warn "vault.credentials: ${BAD_CREDS} SSH credential(s) with auth_scheme IN (11,13) have empty target_address or ssh_user — these are legacy rows from before the Dockerfile fix. Re-create the credentials."
  else
    pass "vault.credentials: 0 incomplete SSH credentials"
  fi
fi

# ── [d] No agents with NULL api_key_hash or api_key_fingerprint ───────────────
echo ""
echo "[d] Agent key integrity (no NULL hashes)"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'mintkey-postgres-1'; then
  warn "mintkey-postgres-1 not running; skipping agent NULL check"
else
  # Check column names first (api_key_hash vs api_key_fingerprint)
  NULL_COUNT="$(_psql "SELECT count(*) FROM agents WHERE api_key_fingerprint IS NULL" 2>/dev/null | tr -d '[:space:]' || echo "ERROR")"
  if [ "$NULL_COUNT" = "ERROR" ]; then
    fail "Could not query agents table"
  elif [ "$NULL_COUNT" -gt 0 ] 2>/dev/null; then
    fail "agents: ${NULL_COUNT} row(s) with NULL api_key_fingerprint — these agents cannot authenticate. Check for incomplete migrations."
  else
    pass "agents: all rows have non-NULL api_key_fingerprint"
  fi

  # api_key_hash column check (stored as argon2id hash)
  HASH_COL="$(_psql "SELECT column_name FROM information_schema.columns WHERE table_name='agents' AND column_name='api_key_hash'" 2>/dev/null | tr -d '[:space:]' || true)"
  if [ -n "$HASH_COL" ]; then
    NULL_HASH="$(_psql "SELECT count(*) FROM agents WHERE api_key_hash IS NULL" 2>/dev/null | tr -d '[:space:]' || echo "ERROR")"
    if [ "$NULL_HASH" = "ERROR" ]; then
      fail "Could not query agents.api_key_hash"
    elif [ "$NULL_HASH" -gt 0 ] 2>/dev/null; then
      fail "agents: ${NULL_HASH} row(s) with NULL api_key_hash — authentication will fail for these agents"
    else
      pass "agents: all rows have non-NULL api_key_hash"
    fi
  else
    info "(api_key_hash column not present — skipping; only fingerprint checked)"
  fi
fi

# ── [e] Kong-syncer health + last reconcile age ────────────────────────────────
echo ""
echo "[e] Kong-syncer health"

KONG_SYNCER_PORT="8085"
KONG_SYNCER_METRICS_URL="http://localhost:${KONG_SYNCER_PORT}/metrics"
KONG_SYNCER_HEALTH_URL="http://localhost:${KONG_SYNCER_PORT}/v1/health"

if ! docker ps --format '{{.Names}}' 2>/dev/null | grep -q 'mintkey-kong-syncer-1'; then
  fail "kong-syncer container (mintkey-kong-syncer-1) is not running"
else
  # Check health status
  HEALTH_RESP="$(curl -sf "${KONG_SYNCER_HEALTH_URL}" 2>/dev/null || true)"
  if [ -z "$HEALTH_RESP" ]; then
    warn "kong-syncer /v1/health not reachable on port ${KONG_SYNCER_PORT}"
  else
    STATUS="$(python3 -c "import json,sys; print(json.loads('${HEALTH_RESP}').get('status','?'))" 2>/dev/null || echo "?")"
    if [ "$STATUS" = "ok" ]; then
      pass "kong-syncer: status=ok"
    else
      REASON="$(python3 -c "import json,sys; print(json.loads('${HEALTH_RESP}').get('reason','unknown'))" 2>/dev/null || echo "unknown")"
      warn "kong-syncer: status=${STATUS} — ${REASON} (304 = no config change is typically benign)"
    fi
  fi

  # Check last push age via metrics
  METRICS_RESP="$(curl -sf "${KONG_SYNCER_METRICS_URL}" 2>/dev/null || true)"
  if [ -n "$METRICS_RESP" ]; then
    LAST_PUSH_AGE="$(echo "${METRICS_RESP}" | grep '^mintkey_kong_syncer_last_push_seconds ' | awk '{print $2}' | head -1 || true)"
    if [ -z "$LAST_PUSH_AGE" ] || [ "$LAST_PUSH_AGE" = "0" ]; then
      warn "kong-syncer: no successful Kong push recorded yet (never pushed or metrics not available)"
    else
      MAX_AGE=600  # 10 minutes
      if [ "$LAST_PUSH_AGE" -gt "$MAX_AGE" ] 2>/dev/null; then
        warn "kong-syncer: last successful push was ${LAST_PUSH_AGE}s ago (threshold: ${MAX_AGE}s) — 304 responses from Kong are expected when config has not changed"
      else
        pass "kong-syncer: last successful push ${LAST_PUSH_AGE}s ago"
      fi
    fi
  fi
fi

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
if [ "$ERRORS" -gt 0 ]; then
  printf "${RED}✗ %d error(s), %d warning(s). Fix errors before using the stack.${RESET}\n" "$ERRORS" "$WARNINGS"
  exit 1
elif [ "$WARNINGS" -gt 0 ]; then
  printf "${YELLOW}⚠ %d warning(s). Stack usable; review warnings above.${RESET}\n" "$WARNINGS"
  exit 0
else
  printf "${GREEN}✓ All Mintkey stack checks passed.${RESET}\n"
  exit 0
fi
