#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# register-service.sh — operator setup for the OpenAI-compatible example.
#
# Creates:
#   1. A service entry pointing to the mock-backend (echo mode)
#   2. A demo credential (placeholder — replace with real key for production)
#   3. An agent with a call permission grant on the new service
#
# Idempotent: skips service/agent creation if slug already exists.
#
# Prerequisites:
#   - Mintkey stack running (make demo)
#   - curl and jq on PATH
#   - Bootstrap admin password accessible (data/bootstrap-secrets/admin_password
#     OR readable from Docker volume)
#
# Usage:
#   bash examples/openai-compatible/register-service.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

ADMIN_API="${MINTKEY_ADMIN_URL:-http://localhost:8080}"
MCP_URL="${MINTKEY_MCP_URL:-http://localhost:8082}"
COOKIE_JAR="/tmp/mk_oai_reg_cookies_$$.txt"

RED='\033[0;31m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; RESET='\033[0m'
info() { printf "${CYAN}▸${RESET} %s\n" "$*"; }
ok()   { printf "${GREEN}  ✓ %s${RESET}\n" "$*"; }
err()  { printf "${RED}  ✗ %s${RESET}\n" "$*" >&2; }

cleanup() { rm -f "$COOKIE_JAR"; }
trap cleanup EXIT

# ── Preflight ─────────────────────────────────────────────────────────────────
command -v curl >/dev/null 2>&1 || { err "curl not found"; exit 1; }
command -v jq   >/dev/null 2>&1 || { err "jq not found";   exit 1; }

info "Checking stack health at ${ADMIN_API}/v1/health ..."
curl -sf "${ADMIN_API}/v1/health" >/dev/null 2>&1 || {
  err "admin-api not responding. Run 'make demo' first."
  exit 1
}
ok "Stack healthy"

# ── Bootstrap password ────────────────────────────────────────────────────────
PW_FILE="${MINTKEY_BOOTSTRAP_PW_FILE:-}"
if [[ -n "$PW_FILE" && -f "$PW_FILE" ]]; then
  ADMIN_PASSWORD="$(cat "$PW_FILE")"
elif [[ -f "data/bootstrap-secrets/admin_password" ]]; then
  ADMIN_PASSWORD="$(cat data/bootstrap-secrets/admin_password)"
else
  info "Reading bootstrap password from Docker volume ..."
  ADMIN_PASSWORD="$(docker run --rm -v mintkey_bootstrap_secrets:/s alpine cat /s/admin_password 2>/dev/null)" || {
    err "Cannot read bootstrap password. Set MINTKEY_BOOTSTRAP_PW_FILE or run the stack."
    exit 1
  }
fi
[[ -n "$ADMIN_PASSWORD" ]] || { err "Bootstrap password is empty."; exit 1; }
ok "Bootstrap password obtained"

# ── Admin login ───────────────────────────────────────────────────────────────
info "Logging in as admin@mintkey.internal ..."
curl -sf -X POST "${ADMIN_API}/v1/auth/internal-login" \
  -H "Content-Type: application/json" \
  -c "$COOKIE_JAR" \
  -d "{\"email\":\"admin@mintkey.internal\",\"password\":\"${ADMIN_PASSWORD}\"}" >/dev/null

CSRF="$(grep 'csrf_token' "$COOKIE_JAR" 2>/dev/null | awk '{print $NF}' | head -1)"
[[ -n "$CSRF" ]] || { err "CSRF token missing from login response."; exit 1; }
ok "Logged in"

TENANT_ID="$(curl -sf "${ADMIN_API}/v1/tenants" \
  -b "$COOKIE_JAR" -H "X-Mintkey-Csrf: ${CSRF}" -H "X-Platform-Admin: true" \
  | jq -r '.data[0].id')"
[[ -n "$TENANT_ID" && "$TENANT_ID" != "null" ]] || { err "Cannot resolve tenant ID."; exit 1; }
ok "Tenant: ${TENANT_ID}"

# ── Service registration (idempotent) ─────────────────────────────────────────
info "Checking for existing service slug 'demo-openai-compatible' ..."
EXISTING_SVC="$(curl -sf "${ADMIN_API}/v1/tenants/${TENANT_ID}/services" \
  -b "$COOKIE_JAR" -H "X-Mintkey-Csrf: ${CSRF}" -H "X-Platform-Admin: true" \
  | jq -r '.data[] | select(.slug=="demo-openai-compatible") | .id' 2>/dev/null || true)"

if [[ -n "$EXISTING_SVC" ]]; then
  SVC_ID="$EXISTING_SVC"
  ok "Service already exists: ${SVC_ID} (skipping creation)"
else
  info "Creating service 'demo-openai-compatible' (mock-backend in echo mode) ..."
  SVC_RESP="$(curl -sf -X POST "${ADMIN_API}/v1/tenants/${TENANT_ID}/services" \
    -H "Content-Type: application/json" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    -b "$COOKIE_JAR" \
    -d '{
      "name": "demo-openai-compatible",
      "slug": "demo-openai-compatible",
      "display_name": "Demo OpenAI-Compatible (mock)",
      "description": "Mock OpenAI-compatible endpoint; auto-created by register-service.sh",
      "base_url": "http://mock-backend:8999",
      "auth_scheme": "bearer_token"
    }')"

  SVC_ID="$(echo "$SVC_RESP" | jq -r '.id')"
  [[ -n "$SVC_ID" && "$SVC_ID" != "null" ]] || {
    err "Service creation failed: ${SVC_RESP}"
    exit 1
  }
  ok "Service created: ${SVC_ID}"

  info "Storing placeholder credential (replace with real key for production) ..."
  curl -sf -X POST "${ADMIN_API}/v1/tenants/${TENANT_ID}/services/${SVC_ID}/credentials" \
    -H "Content-Type: application/json" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    -b "$COOKIE_JAR" \
    -d '{"auth_scheme":"bearer_token","value":"demo-openai-placeholder-key"}' \
    >/dev/null
  ok "Credential stored (placeholder value — redacted from stdout)"
fi

# ── Agent creation (idempotent) ───────────────────────────────────────────────
info "Checking for existing agent 'Demo-OpenAI-Agent' ..."
EXISTING_AGENT="$(curl -sf "${ADMIN_API}/v1/tenants/${TENANT_ID}/agents" \
  -b "$COOKIE_JAR" -H "X-Mintkey-Csrf: ${CSRF}" -H "X-Platform-Admin: true" \
  | jq -r '.data[] | select(.name=="Demo-OpenAI-Agent") | .id' 2>/dev/null || true)"

if [[ -n "$EXISTING_AGENT" ]]; then
  AGENT_ID="$EXISTING_AGENT"
  ok "Agent already exists: ${AGENT_ID} (skipping creation)"
  printf '\n%s\n' "NOTE: To get the agent API key, go to admin UI → Agents → Demo-OpenAI-Agent → Key."
else
  info "Creating agent 'Demo-OpenAI-Agent' ..."
  AGENT_RESP="$(curl -sf -X POST "${ADMIN_API}/v1/tenants/${TENANT_ID}/agents" \
    -H "Content-Type: application/json" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    -b "$COOKIE_JAR" \
    -d '{"name":"Demo-OpenAI-Agent","description":"Created by register-service.sh","rate_limit_rps":10}')"

  AGENT_ID="$(echo "$AGENT_RESP" | jq -r '.id')"
  AGENT_KEY_VALUE="$(echo "$AGENT_RESP" | jq -r '.api_key')"
  [[ -n "$AGENT_ID" && "$AGENT_ID" != "null" ]] || {
    err "Agent creation failed: ${AGENT_RESP}"
    exit 1
  }
  ok "Agent created: ${AGENT_ID}"
  printf '\n  MINTKEY_AGENT_KEY=%s\n\n' "${AGENT_KEY_VALUE:-<see admin UI — shown once>}"
fi

# ── Permission grant (idempotent) ─────────────────────────────────────────────
info "Granting agent ${AGENT_ID} → service ${SVC_ID} (action=call) ..."
PERM_RESP="$(curl -sf -X POST "${ADMIN_API}/v1/tenants/${TENANT_ID}/agents/${AGENT_ID}/permissions" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: ${CSRF}" \
  -H "X-Platform-Admin: true" \
  -b "$COOKIE_JAR" \
  -d "{\"service_id\":\"${SVC_ID}\",\"action\":\"call\"}" 2>&1 || true)"

PERM_ID="$(echo "$PERM_RESP" | jq -r '.id // empty' 2>/dev/null || true)"
if [[ -n "$PERM_ID" ]]; then
  ok "Permission grant created: ${PERM_ID}"
else
  # May already exist; treat as non-fatal
  ok "Permission grant already exists or was created (idempotent)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
printf '\n%s\n' "─────────────────────────────────────────────────────"
printf '%s\n'   "Setup complete. Export these variables and run agent.py:"
printf '\n'
printf '  export MINTKEY_SVC_ID=%s\n' "${SVC_ID}"
printf '  export MINTKEY_AGENT_KEY=mk_agent_YOUR_AGENT_KEY_HERE\n'
printf '  python3 examples/openai-compatible/agent.py\n'
printf '\n%s\n' "─────────────────────────────────────────────────────"
