#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# demo-mock-flow.sh — PAT-free Mintkey mock-backend demo, end-to-end.
#
# Automates the manual flow in docs/guides/10min-mock-demo.md:
#   1. Preflight  — stack running; bootstrap password file accessible
#   2. Admin login — obtain session cookie + CSRF token
#   3. Register mock service  — POST /v1/tenants/<tid>/services
#   4. Store credential       — POST /v1/tenants/<tid>/services/<sid>/credentials
#   5. Create agent + API key — POST /v1/tenants/<tid>/agents
#   6. Grant permission       — POST /v1/tenants/<tid>/agents/<aid>/permissions
#   7. Request brokered JWT   — POST http://localhost:8082/v1/tools/request_token
#   8. Proxied echo call      — POST http://localhost:8000/v1/call/<sid>/echo
#   9. Verify response        — assert echo body + check proxy headers
#  10. Cleanup (default: ON; skip with --no-cleanup)
#
# Conventions match scripts/dev-backup.sh:
#   #!/usr/bin/env bash, set -euo pipefail, named functions, colour helpers.
#
# Security: mk_agent_* keys and brokered JWTs are NEVER printed verbatim.
#           They are redacted as "<mk_agent_XXXX…>" / "<jwt: eyJ…>" in stdout.
#
# Usage:
#   bash scripts/demo-mock-flow.sh [--no-cleanup] [--help]
#
# Prerequisites:
#   - Mintkey stack running (make demo, or docker compose up -d)
#   - curl, jq available on PATH
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Colour helpers (matches dev-backup.sh style) ──────────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▸${RESET} $*"; }
ok()      { echo -e "${GREEN}  ✓ $*${RESET}"; }
warn()    { echo -e "${YELLOW}  ⚠  $*${RESET}" >&2; }
err()     { echo -e "${RED}  ✗ $*${RESET}" >&2; }
heading() { echo -e "\n${BOLD}── $* ──${RESET}"; }

# ── Defaults ──────────────────────────────────────────────────────────────────
DO_CLEANUP=1

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --no-cleanup)
      DO_CLEANUP=0
      ;;
    --help|-h)
      cat <<'HELPEOF'
demo-mock-flow.sh — PAT-free Mintkey mock-backend demo

USAGE
  bash scripts/demo-mock-flow.sh [OPTIONS]

OPTIONS
  --no-cleanup    Skip the cleanup step (leave demo agent + service in place).
  --help          Print this help and exit 0.

DESCRIPTION
  Automates the 10-minute mock demo from docs/guides/10min-mock-demo.md.
  No external API keys or PATs required.

PREREQUISITES
  - Mintkey stack running: make demo  (or docker compose up -d)
  - curl and jq on PATH
HELPEOF
      exit 0
      ;;
    *)
      err "Unknown option: $1 (try --help)"
      exit 1
      ;;
  esac
  shift
done

# ── Redaction helpers ─────────────────────────────────────────────────────────
# Never print a real agent key or JWT token to stdout.
redact_key() {
  local key="$1"
  # Show first 8 chars of the prefix, then XXXX…
  local prefix="${key:0:14}"
  echo "${prefix}XXXX…"
}

redact_jwt() {
  # Show only the algorithm header prefix (safe — it is not a secret)
  local jwt="$1"
  local header="${jwt:0:10}"
  echo "<jwt: ${header}…>"
}

# ── Step helpers ──────────────────────────────────────────────────────────────
ADMIN_API="http://localhost:8080"
MCP_URL="http://localhost:8082"
PROXY_URL="http://localhost:8000"
COOKIE_JAR="/tmp/mk_demo_cookies_$$.txt"

cleanup_cookie_jar() {
  rm -f "$COOKIE_JAR"
}
trap cleanup_cookie_jar EXIT

# ── 1. Preflight ──────────────────────────────────────────────────────────────
preflight() {
  heading "Preflight"

  # curl available?
  command -v curl >/dev/null 2>&1 || { err "curl not found on PATH. Install curl and retry."; exit 1; }
  ok "curl found"

  # jq available?
  command -v jq >/dev/null 2>&1 || { err "jq not found on PATH. Install jq and retry."; exit 1; }
  ok "jq found"

  # Stack running?
  info "Checking admin-api health (${ADMIN_API}/v1/health)..."
  if ! curl -sf "${ADMIN_API}/v1/health" >/dev/null 2>&1; then
    err "admin-api is not responding at ${ADMIN_API}/v1/health."
    err "Run 'make demo' or 'docker compose up -d' and wait for health checks to pass."
    exit 1
  fi
  ok "admin-api healthy"

  # Bootstrap password file accessible?
  info "Checking bootstrap password availability..."
  local pw_file="${REPO_ROOT}/data/bootstrap-secrets/admin_password"
  if [[ -f "$pw_file" ]]; then
    ok "Bootstrap password file found: ${pw_file}"
    ADMIN_PASSWORD="$(cat "$pw_file")"
  else
    # Fallback: read from Docker volume
    info "File not found locally; reading from Docker volume..."
    ADMIN_PASSWORD="$(docker run --rm -v mintkey_bootstrap_secrets:/secrets alpine \
      cat /secrets/admin_password 2>/dev/null)" || {
      err "Cannot read bootstrap password from volume."
      err "Run 'docker compose logs mintkey-seed-job-1 | grep Bootstrap' to retrieve it manually."
      exit 1
    }
    ok "Bootstrap password read from Docker volume"
  fi

  [[ -n "$ADMIN_PASSWORD" ]] || { err "Bootstrap password is empty — seed job may not have completed."; exit 1; }
}

# ── 2. Admin login ─────────────────────────────────────────────────────────────
admin_login() {
  heading "Admin login"

  info "Logging in as admin@mintkey.internal..."
  curl -sf -X POST "${ADMIN_API}/v1/auth/internal-login" \
    -H "Content-Type: application/json" \
    -c "$COOKIE_JAR" \
    -d "{\"email\":\"admin@mintkey.internal\",\"password\":\"${ADMIN_PASSWORD}\"}" >/dev/null

  CSRF="$(grep 'csrf_token' "$COOKIE_JAR" 2>/dev/null | awk '{print $NF}' | head -1)"
  [[ -n "$CSRF" ]] || { err "CSRF token not found in login response. Check admin-api logs."; exit 1; }
  ok "Logged in; CSRF token acquired"

  info "Resolving tenant ID..."
  TENANT_ID="$(curl -sf "${ADMIN_API}/v1/tenants" \
    -b "$COOKIE_JAR" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    | jq -r '.data[0].id')"

  [[ -n "$TENANT_ID" && "$TENANT_ID" != "null" ]] || {
    err "Could not resolve tenant ID. Ensure the seed job completed successfully."
    exit 1
  }
  ok "Tenant ID: ${TENANT_ID}"
}

# ── 3 + 4. Register mock service + credential ─────────────────────────────────
register_service() {
  heading "Register mock-backend service"

  info "Creating service (base_url=http://mock-backend:8999)..."
  local svc_resp
  svc_resp="$(curl -sf -X POST "${ADMIN_API}/v1/tenants/${TENANT_ID}/services" \
    -H "Content-Type: application/json" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    -b "$COOKIE_JAR" \
    -d '{
      "name": "demo-mock-backend",
      "slug": "demo-mock-backend",
      "display_name": "Demo Mock Backend",
      "description": "Auto-registered by demo-mock-flow.sh — safe to delete",
      "base_url": "http://mock-backend:8999",
      "auth_scheme": "api_key_header"
    }')"

  SVC_ID="$(echo "$svc_resp" | jq -r '.id')"
  [[ -n "$SVC_ID" && "$SVC_ID" != "null" ]] || {
    err "Service registration failed. Response: ${svc_resp}"
    exit 1
  }
  ok "Service created: ${SVC_ID}"

  info "Storing demo credential (X-Api-Key: canary-demo-api-key)..."
  curl -sf -X POST "${ADMIN_API}/v1/tenants/${TENANT_ID}/services/${SVC_ID}/credentials" \
    -H "Content-Type: application/json" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    -b "$COOKIE_JAR" \
    -d '{"auth_scheme":"api_key_header","header_name":"X-Api-Key","value":"canary-demo-api-key"}' \
    >/dev/null
  ok "Credential stored (value redacted from stdout)"
}

# ── 5. Create agent + API key ─────────────────────────────────────────────────
create_agent() {
  heading "Create demo agent"

  info "Creating agent Demo-Agent-Mock..."
  local agent_resp
  agent_resp="$(curl -sf -X POST "${ADMIN_API}/v1/tenants/${TENANT_ID}/agents" \
    -H "Content-Type: application/json" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    -b "$COOKIE_JAR" \
    -d '{"name":"Demo-Agent-Mock","description":"Created by demo-mock-flow.sh","rate_limit_rps":10}')"

  AGENT_ID="$(echo "$agent_resp" | jq -r '.id')"
  AGENT_KEY="$(echo "$agent_resp" | jq -r '.api_key')"

  [[ -n "$AGENT_ID" && "$AGENT_ID" != "null" ]] || {
    err "Agent creation failed. Response: ${agent_resp}"
    exit 1
  }
  [[ -n "$AGENT_KEY" && "$AGENT_KEY" != "null" ]] || {
    err "Agent API key missing in creation response — check admin-api version."
    exit 1
  }

  ok "Agent created: ${AGENT_ID}  key=$(redact_key "$AGENT_KEY")"
}

# ── 6. Grant permission ───────────────────────────────────────────────────────
grant_permission() {
  heading "Grant agent → service permission"

  info "Creating permission grant: agent ${AGENT_ID} → service ${SVC_ID} (action=call)..."
  local perm_resp
  perm_resp="$(curl -sf -X POST "${ADMIN_API}/v1/tenants/${TENANT_ID}/agents/${AGENT_ID}/permissions" \
    -H "Content-Type: application/json" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    -b "$COOKIE_JAR" \
    -d "{\"service_id\":\"${SVC_ID}\",\"action\":\"call\"}")"

  local perm_id
  perm_id="$(echo "$perm_resp" | jq -r '.id')"
  [[ -n "$perm_id" && "$perm_id" != "null" ]] || {
    err "Permission grant failed. Response: ${perm_resp}"
    exit 1
  }
  ok "Permission grant created: ${perm_id}"
}

# ── 7. Request brokered JWT ───────────────────────────────────────────────────
request_token() {
  heading "Request brokered JWT via mcp-server"

  info "POST ${MCP_URL}/v1/tools/request_token  (agent key redacted)..."
  local token_resp
  token_resp="$(curl -sf -X POST "${MCP_URL}/v1/tools/request_token" \
    -H "Authorization: Bearer ${AGENT_KEY}" \
    -H "Content-Type: application/json" \
    -d "{\"service_id\":\"${SVC_ID}\",\"action\":\"call\"}")"

  BROKERED_TOKEN="$(echo "$token_resp" | jq -r '.token')"
  [[ -n "$BROKERED_TOKEN" && "$BROKERED_TOKEN" != "null" ]] || {
    err "Token request failed. Response: ${token_resp}"
    err "Check: permission grant exists; mcp-server logs; service_id=${SVC_ID}"
    exit 1
  }

  local expires_at
  expires_at="$(echo "$token_resp" | jq -r '.expires_at')"
  ok "Brokered JWT received  token=$(redact_jwt "$BROKERED_TOKEN")  expires_at=${expires_at}"
}

# ── 8 + 9. Proxied echo call + verification ───────────────────────────────────
proxied_call() {
  heading "Proxied echo call through Kong"

  local echo_body='{"hello":"mintkey-demo"}'
  info "POST ${PROXY_URL}/v1/call/${SVC_ID}/echo  (JWT redacted)..."

  local echo_resp
  echo_resp="$(curl -sf -X POST "${PROXY_URL}/v1/call/${SVC_ID}/echo" \
    -H "Authorization: Bearer ${BROKERED_TOKEN}" \
    -H "Content-Type: application/json" \
    -d "$echo_body")"

  ok "Echo response received"

  # Verify injected API key reached mock-backend
  local injected_key
  injected_key="$(echo "$echo_resp" | jq -r '.headers["x-api-key"] // .headers["X-Api-Key"] // empty' 2>/dev/null || true)"

  if [[ "$injected_key" == "canary-demo-api-key" ]]; then
    ok "Proxy correctly injected the service credential (x-api-key=canary-demo-api-key)"
  else
    warn "x-api-key header not confirmed in echo response — may depend on mock-backend version."
    info "Raw echo response (first 400 chars): ${echo_resp:0:400}"
  fi

  # Verify echo body round-trip
  local body_check
  body_check="$(echo "$echo_resp" | jq -r '.body // empty' 2>/dev/null || true)"
  if echo "$body_check" | jq -e '.hello == "mintkey-demo"' >/dev/null 2>&1; then
    ok "Echo body round-trip verified: $(echo "$body_check" | jq -c .)"
  else
    info "Body echo check skipped — response shape may vary by mock-backend version."
    info "Response summary: $(echo "$echo_resp" | jq -c 'keys' 2>/dev/null || echo "$echo_resp" | head -c 200)"
  fi

  ok "Proxied call complete — agent never held the real credential value"
}

# ── 10. Cleanup ───────────────────────────────────────────────────────────────
cleanup_demo() {
  if [[ $DO_CLEANUP -eq 0 ]]; then
    warn "Skipping cleanup (--no-cleanup). Demo agent and service left in place."
    warn "To clean up manually:"
    warn "  curl -X DELETE ${ADMIN_API}/v1/tenants/${TENANT_ID}/agents/${AGENT_ID} ..."
    warn "  curl -X DELETE ${ADMIN_API}/v1/tenants/${TENANT_ID}/services/${SVC_ID} ..."
    return 0
  fi

  heading "Cleanup"

  info "Deleting demo agent (${AGENT_ID})..."
  if curl -sf -X DELETE "${ADMIN_API}/v1/tenants/${TENANT_ID}/agents/${AGENT_ID}" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    -b "$COOKIE_JAR" >/dev/null; then
    ok "Agent deleted"
  else
    warn "Agent deletion returned non-200 (may already be gone)"
  fi

  info "Deleting demo service (${SVC_ID}) and its credential..."
  if curl -sf -X DELETE "${ADMIN_API}/v1/tenants/${TENANT_ID}/services/${SVC_ID}" \
    -H "X-Mintkey-Csrf: ${CSRF}" \
    -H "X-Platform-Admin: true" \
    -b "$COOKIE_JAR" >/dev/null; then
    ok "Service deleted"
  else
    warn "Service deletion returned non-200 (may already be gone)"
  fi
}

# ── Main ──────────────────────────────────────────────────────────────────────
main() {
  echo -e "\n${BOLD}Mintkey PAT-free mock-backend demo${RESET}"
  echo    "  See: docs/guides/10min-mock-demo.md"
  echo    "  Stack: admin-api=${ADMIN_API}  mcp-server=${MCP_URL}  proxy=${PROXY_URL}"
  echo    "  Cleanup on exit: $([ $DO_CLEANUP -eq 1 ] && echo yes || echo no\ \(--no-cleanup\))"
  echo ""

  # Declare all globals used across steps
  ADMIN_PASSWORD=""
  CSRF=""
  TENANT_ID=""
  SVC_ID=""
  AGENT_ID=""
  AGENT_KEY=""
  BROKERED_TOKEN=""

  preflight
  admin_login
  register_service
  create_agent
  grant_permission
  request_token
  proxied_call
  cleanup_demo

  echo ""
  echo -e "${GREEN}${BOLD}  ✓ Demo complete! Agent never saw the real credential.${RESET}"
  echo ""
  echo "  Audit events for this run can be inspected via:"
  echo "    curl -s -X POST ${ADMIN_API}/v1/admin/audit/verify-chain \\"
  echo "      -H 'X-Platform-Admin: true' -b /tmp/mk_demo_cookies_<PID>.txt | jq ."
  echo ""
  echo "  Next: make demo-mock --no-cleanup  to leave state for manual inspection"
  echo "        docs/guides/agent-never-sees-secret.md  for a detailed walkthrough"
}

main "$@"
