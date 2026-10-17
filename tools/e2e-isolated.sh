#!/usr/bin/env bash
# Run the stack-dependent tests (Playwright admin-ui e2e + the stack-based Python tests) against an
# ISOLATED compose project -- never against whatever happens to own the default ports.
#
#   E2E_PROJECT=mintkey-e2e tools/e2e-isolated.sh up|test|down|check|creds|pw [playwright args]|py [pytest args]
#
# Why this exists (footguns it removes):
#   * apps/admin-ui/e2e/playwright.config.ts used to default to http://localhost:8081 and the
#     fixtures to http://localhost:8080 -- the live dev stack on a developer machine.
#   * `make smoke`, `make test-golden` and `make test-data-plane*` find "the stack" with
#     `docker compose ps` in the checkout, and tests/acceptance/test_e2e_smoke.py (DB teardown via
#     `docker compose exec postgres`) and test_data_plane_resilience.py (`docker compose pause
#     vault-adapter`) shell out to compose with no -p: the compose file says `name: mintkey`,
#     i.e. the live project. COMPOSE_PROJECT_NAME (exported below) outranks `name:`, so those
#     calls land in the isolated project.
#   * the seed-job mirrors the bootstrap admin password into data/bootstrap-secrets of the checkout;
#     the overlay redirects that bind to $E2E_SECRETS_DIR.
#
# Environment (all optional except E2E_PROJECT):
#   E2E_PROJECT          compose project name, REQUIRED, not `mintkey` / `mintkey-test`
#   E2E_ENV_FILE         env file for compose (default: <scratch>/env, generated from .env.example)
#   E2E_SECRETS_DIR      host dir for the bootstrap secret mirror (default data/e2e/<project>/bootstrap-secrets)
#   E2E_PORT_*           host ports, see infra/compose/docker-compose.e2e.yml (defaults: the +300 set)
#   E2E_BROWSERS         space separated Playwright projects (default: chromium)
#   E2E_SUITES           what `test` runs: space separated of playwright smoke integration golden data-plane
#                        (default: all of them)
#   E2E_FORCE_REBUILD    set to 1 to pass --build (default for `up`)
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

die() { echo "e2e-isolated: $*" >&2; exit 2; }

PROJECT="${E2E_PROJECT:-}"
[ -n "$PROJECT" ] || die "E2E_PROJECT is not set. Name the isolated compose project explicitly, e.g. E2E_PROJECT=mintkey-e2e"
case "$PROJECT" in
  mintkey|mintkey-test) die "refusing project name '$PROJECT': it is the live / test-namespace stack" ;;
esac
[[ "$PROJECT" =~ ^[a-z0-9][a-z0-9_-]*$ ]] || die "invalid project name '$PROJECT'"

STATE_DIR="${E2E_STATE_DIR:-$ROOT/data/e2e/$PROJECT}"
export E2E_PROJECT="$PROJECT"
export E2E_SECRETS_DIR="${E2E_SECRETS_DIR:-$STATE_DIR/bootstrap-secrets}"
ENV_FILE="${E2E_ENV_FILE:-$STATE_DIR/env}"
OVERLAY="$ROOT/infra/compose/docker-compose.e2e.yml"

P_ADMIN_API="${E2E_PORT_ADMIN_API:-8380}"
P_ADMIN_UI="${E2E_PORT_ADMIN_UI:-8381}"
P_MCP="${E2E_PORT_MCP:-8382}"
P_BROKER="${E2E_PORT_BROKER:-8383}"
P_VAULT_GRPC="${E2E_PORT_VAULT_GRPC:-8384}"
P_KONG="${E2E_PORT_KONG:-8300}"
P_KONG_ADMIN="${E2E_PORT_KONG_ADMIN:-8301}"
P_KEYCLOAK="${E2E_PORT_KEYCLOAK:-8643}"
P_GRAFANA="${E2E_PORT_GRAFANA:-3303}"
P_JAEGER="${E2E_PORT_JAEGER:-16986}"

# Ports that belong to the live stack (primary) and to the +100 test namespace. (8301 is the test
# namespace's hashicorp-vault port, but only under a profile that is off by default; it is also the
# isolated Kong admin port, so it is checked for being free rather than forbidden.)
FORBIDDEN_PORTS=" 8000 8001 8080 8081 8082 8083 8084 8085 8086 8087 8088 8089 8090 8091 8092 8201 8443 8999 3003 16686 4317 2222 \
8100 8101 8180 8181 8182 8183 8184 8185 8186 8187 8188 8189 8190 8191 8192 8543 9099 3103 16786 4417 2322 "

compose() {
  docker compose -p "$PROJECT" --env-file "$ENV_FILE" \
    -f infra/compose/docker-compose.yml -f "$OVERLAY" "$@"
}

ensure_env_file() {
  [ -f "$ENV_FILE" ] && return 0
  mkdir -p "$(dirname "$ENV_FILE")"
  python3 - "$ROOT/.env.example" "$ENV_FILE" <<'PY'
import re, secrets, sys
t = re.sub(r"REPLACE_WITH_openssl_rand_hex_32", lambda m: secrets.token_hex(32), open(sys.argv[1]).read())
open(sys.argv[2], "w").write(t + "\n# --- generated for the isolated e2e stack ---\n")
PY
  { cat <<E2
MINTKEY_KEYCLOAK_PUBLIC_URL=http://localhost:${P_KEYCLOAK}
MINTKEY_ADMIN_API_PUBLIC_URL=http://localhost:${P_ADMIN_API}
MINTKEY_ADMIN_UI_PUBLIC_URL=http://localhost:${P_ADMIN_UI}
MINTKEY_MCP_PUBLIC_URL=http://localhost:${P_MCP}
MINTKEY_PROXY_PUBLIC_URL=http://localhost:${P_KONG}
MINTKEY_GRAFANA_PUBLIC_URL=http://localhost:${P_GRAFANA}
MINTKEY_JAEGER_PUBLIC_URL=http://localhost:${P_JAEGER}
E2
  } >> "$ENV_FILE"
  chmod 600 "$ENV_FILE"
  echo "e2e-isolated: wrote $ENV_FILE"
}

# Print the resolved config problems; exit non-zero if any.
check_config() {
  ensure_env_file
  mkdir -p "$E2E_SECRETS_DIR"
  local json
  json="$(compose --profile '*' config --format json)"
  FORBIDDEN="$FORBIDDEN_PORTS" PROJECT="$PROJECT" python3 - "$json" <<'PY'
import json, os, sys
cfg = json.loads(sys.argv[1]); project = os.environ["PROJECT"]
forbidden = {int(p) for p in os.environ["FORBIDDEN"].split()}
bad = []
if cfg.get("name") != project:
    bad.append(f"compose project resolves to {cfg.get('name')!r}, expected {project!r}")
for name, svc in cfg["services"].items():
    if svc.get("container_name"):
        bad.append(f"{name}: container_name={svc['container_name']} is shared across projects")
    if "build" in svc:
        img = svc.get("image", "")
        if not img.startswith(project + "-"):
            bad.append(f"{name}: built image {img!r} must be tagged {project}-{name} (not a shared mintkey-<service> tag)")
    for p in svc.get("ports", []):
        if p.get("published") and int(p["published"]) in forbidden:
            bad.append(f"{name}: host port {p['published']} belongs to the live / test-namespace stack")
for key, vol in cfg.get("volumes", {}).items():
    if not str(vol.get("name", "")).startswith(project):
        bad.append(f"volume {key}: name {vol.get('name')!r} is not scoped to project {project}")
for key, net in cfg.get("networks", {}).items():
    if not str(net.get("name", "")).startswith(project):
        bad.append(f"network {key}: name {net.get('name')!r} is not scoped to project {project}")
secrets_dir = os.environ.get("E2E_SECRETS_DIR", "")
for name, svc in cfg["services"].items():
    for v in svc.get("volumes", []):
        if v.get("type") == "bind" and v["source"].rstrip("/").endswith("data/bootstrap-secrets"):
            bad.append(f"{name}: binds the checkout's data/bootstrap-secrets (the live stack's admin password mirror)")
if bad:
    print("e2e-isolated: unsafe compose config:", file=sys.stderr)
    for b in bad:
        print("  - " + b, file=sys.stderr)
    sys.exit(1)
print(f"e2e-isolated: config ok for project {project} ({len(cfg['services'])} services)")
PY
}

ports_free() {
  local busy=0 p
  for p in "$P_ADMIN_API" "$P_ADMIN_UI" "$P_MCP" "$P_BROKER" "$P_VAULT_GRPC" "$P_KONG" "$P_KONG_ADMIN" "$P_KEYCLOAK" "$P_GRAFANA" "$P_JAEGER"; do
    if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
      # fine if it is already our own stack
      if ! compose ps --format '{{.Name}}' 2>/dev/null | grep -q .; then
        echo "e2e-isolated: port $p is already in use by something else" >&2; busy=1
      fi
    fi
  done
  [ "$busy" = 0 ] || exit 3
}

cmd_up() {
  check_config
  ports_free
  SSH_PROXY_HOST_KEY_GENERATE=true compose up -d --build --wait --timeout 300
  echo "e2e-isolated: stack '$PROJECT' is up: admin-ui http://localhost:${P_ADMIN_UI}  admin-api http://localhost:${P_ADMIN_API}"
}

cmd_down() {
  check_config >/dev/null
  compose down --volumes
  rm -rf "$STATE_DIR/bootstrap-secrets"
  echo "e2e-isolated: stack '$PROJECT' removed (images ${PROJECT}-* are kept; remove them with: docker image ls '${PROJECT}-*')"
}

# Decrypt the bootstrap admin password (Fernet, KEK from the compose default / MINTKEY_BOOTSTRAP_KEK).
admin_password() {
  local f="$E2E_SECRETS_DIR/admin_password"
  [ -f "$f" ] || die "no $f -- is the stack up (seed-job done)?"
  uv run --quiet --no-project --python 3.12 --with cryptography python3 -c '
import sys
from cryptography.fernet import Fernet
print(Fernet(sys.argv[2].encode()).decrypt(open(sys.argv[1], "rb").read()).decode().strip())
' "$f" "${MINTKEY_BOOTSTRAP_KEK:-TUQpz9CUkfOvVJiM0yBUL8J9xAgrzE__JkNnwcocVas=}"
}

tenant_id() {
  compose exec -T postgres env PGPASSWORD=changeme psql -U mintkey_migrate -d mintkey -t -A \
    -c "SELECT id FROM tenants WHERE slug = 't_default' LIMIT 1;" | tr -d '[:space:]'
}

export_env() {
  export COMPOSE_PROJECT_NAME="$PROJECT"
  unset COMPOSE_FILE COMPOSE_ENV_FILES COMPOSE_PROFILES || true
  export MINTKEY_INTEGRATION_TEST=true
  export MINTKEY_API_URL="http://localhost:${P_ADMIN_API}"
  export MINTKEY_MCP_URL="http://localhost:${P_MCP}"
  export MINTKEY_KONG_URL="http://localhost:${P_KONG}"
  export MINTKEY_KONG_ADMIN_URL="http://localhost:${P_KONG_ADMIN}"
  export MINTKEY_BROKER_URL="http://localhost:${P_BROKER}"
  export MINTKEY_VAULT_GRPC="localhost:${P_VAULT_GRPC}"
  export VAULT_GRPC_ADDR="localhost:${P_VAULT_GRPC}"
  export MINTKEY_VAULT_ADAPTER_METRICS_URL="http://localhost:${E2E_PORT_VAULT_HTTP:-8387}"
  # Plain assignments first: `export X="$(cmd)"` would swallow a failing cmd under `set -e`.
  local password tenant
  password="$(admin_password)"
  tenant="$(tenant_id)"
  [ -n "$password" ] || die "could not decrypt the bootstrap admin password"
  [ -n "$tenant" ] || die "could not read the t_default tenant id from the stack"
  # MINTKEY_MCP_SERVICE_TOKEN is deliberately left alone: docker-compose.yml pins it to the
  # `dev-mcp-service-token` the tests default to.
  export MINTKEY_BOOTSTRAP_PASSWORD="$password"
  export PLAYWRIGHT_BASE_URL="http://localhost:${P_ADMIN_UI}"
  export ADMIN_API_URL="http://localhost:${P_ADMIN_API}"
  export PLAYWRIGHT_USER="admin@mintkey.internal"
  export PLAYWRIGHT_PASS="$password"
  export PLAYWRIGHT_TENANT_ID="$tenant"
}

assert_stack_is_ours() {
  # Every endpoint we are about to hit must be answered by *our* project's containers.
  local running
  running="$(compose ps --status running --format '{{.Name}}' | wc -l | tr -d ' ')"
  [ "$running" -ge 10 ] || die "project '$PROJECT' has only $running running containers -- run the 'up' step first"
  curl -fsS "http://localhost:${P_ADMIN_UI}/health" >/dev/null || die "admin-ui not answering on ${P_ADMIN_UI}"
}

cmd_test() {
  check_config >/dev/null
  assert_stack_is_ours
  export_env
  local suites="${E2E_SUITES:-playwright smoke integration golden data-plane}"
  local browsers="${E2E_BROWSERS:-chromium}"
  local rc=0 s b
  for s in $suites; do
    case "$s" in
      playwright)
        for b in $browsers; do
          echo "=== playwright ($b) against $PLAYWRIGHT_BASE_URL ==="
          ( cd apps/admin-ui && CI=true npx playwright test --config e2e/playwright.config.ts --project="$b" ) || rc=1
        done ;;
      smoke)
        echo "=== acceptance smoke ==="
        uv run --project apps/admin-api pytest tests/acceptance/test_e2e_smoke.py -v -s || rc=1 ;;
      integration)
        echo "=== test-integration set ==="
        ( cd apps/admin-api && uv run pytest \
            "$ROOT/tests/acceptance/test_brokered_call.py" \
            "$ROOT/tests/acceptance/test_rotation_propagation.py" \
            "$ROOT/tests/acceptance/test_revocation_timing.py" \
            "$ROOT/tests/acceptance/test_token_issuance_perf.py" \
            "$ROOT/tests/acceptance/test_proxy_latency.py" \
            "$ROOT/tests/acceptance/test_avail.py" -v ) || rc=1 ;;
      golden)
        echo "=== golden path ==="
        uv run --project apps/admin-api pytest tests/acceptance/test_golden_path.py -v -s || rc=1 ;;
      data-plane)
        echo "=== data-plane smoke + resilience ==="
        uv run --project apps/admin-api pytest tests/acceptance/test_data_plane_smoke.py tests/acceptance/test_data_plane_resilience.py -v || rc=1 ;;
      *) die "unknown suite '$s'" ;;
    esac
  done
  return $rc
}

# Run Playwright with the isolated stack's environment and arbitrary extra arguments, e.g.
#   E2E_PROJECT=mintkey-e2e tools/e2e-isolated.sh pw --project=firefox e2e/tests/21-logout-session.spec.ts
cmd_pw() {
  check_config >/dev/null
  assert_stack_is_ours
  export_env
  ( cd apps/admin-ui && CI=true npx playwright test --config e2e/playwright.config.ts "$@" )
}

# Run pytest (root-level acceptance tests) with the isolated stack's environment, e.g.
#   E2E_PROJECT=mintkey-e2e tools/e2e-isolated.sh py tests/acceptance/test_golden_path.py -k ws9 -x
cmd_py() {
  check_config >/dev/null
  assert_stack_is_ours
  export_env
  uv run --project apps/admin-api pytest "$@"
}

case "${1:-}" in
  check) check_config ;;
  py)    shift; cmd_py "$@" ;;
  pw)    shift; cmd_pw "$@" ;;
  up)    cmd_up ;;
  test)  cmd_test ;;
  down)  cmd_down ;;
  creds) check_config >/dev/null; export_env; env | grep -E '^(PLAYWRIGHT_|ADMIN_API_URL|MINTKEY_)' | sed -E 's/(PASS(WORD)?|TOKEN)=.*/\1=***/' ;;
  *) die "usage: E2E_PROJECT=<name> $0 up|test|down|check|creds|pw [playwright args]|py [pytest args]" ;;
esac
