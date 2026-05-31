#!/usr/bin/env bash
# Mintkey Clone-free Installer — operator "just Docker" path.
# Requires: docker (with compose plugin v2), and curl or wget.
# Optional: python3 (cryptography) or openssl for Fernet KEK generation.
#
# One-liner usage (no git clone required):
#   curl -fsSL https://raw.githubusercontent.com/WeLikeCode/mintkey/main/install.sh | sh
#   — or —
#   sh install.sh
#
# Idempotent: re-running in the same directory preserves the existing .env/KEK,
# re-downloads fresh configs, and runs `docker compose up -d --remove-orphans`.
#
# To target a specific release tag:
#   MINTKEY_BRANCH=v1.2.3 sh install.sh
#
# Developer install (requires git clone):
#   git clone https://github.com/WeLikeCode/mintkey.git && cd mintkey
#   docker compose -f infra/compose/docker-compose.yml up -d

set -euo pipefail

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MINTKEY_REPO="WeLikeCode/mintkey"
MINTKEY_BRANCH="${MINTKEY_BRANCH:-main}"
RAW_BASE="https://raw.githubusercontent.com/${MINTKEY_REPO}/${MINTKEY_BRANCH}"
COMPOSE_FILE="docker-compose.ghcr.yml"
COMPOSE_URL="${RAW_BASE}/infra/compose/${COMPOSE_FILE}"
INSTALL_DIR="${MINTKEY_INSTALL_DIR:-$(pwd)}"
CONFIG_DIR="${INSTALL_DIR}/config"
DATA_DIR="${INSTALL_DIR}/data/bootstrap-secrets"
ENV_FILE="${INSTALL_DIR}/.env"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
info()  { printf '\033[0;32m[mintkey]\033[0m %s\n' "$*"; }
warn()  { printf '\033[0;33m[mintkey]\033[0m %s\n' "$*" >&2; }
fatal() { printf '\033[0;31m[mintkey]\033[0m FATAL: %s\n' "$*" >&2; exit 1; }

need_cmd() {
  command -v "$1" >/dev/null 2>&1 || fatal "Required command not found: $1"
}

fetch() {
  # fetch <url> <dest>
  _url="$1" _dest="$2"
  mkdir -p "$(dirname "$_dest")"
  if command -v curl >/dev/null 2>&1; then
    curl -fsSL "$_url" -o "$_dest"
  elif command -v wget >/dev/null 2>&1; then
    wget -qO "$_dest" "$_url"
  else
    fatal "Neither curl nor wget found. Install one and retry."
  fi
}

# ---------------------------------------------------------------------------
# Pre-flight
# ---------------------------------------------------------------------------
need_cmd docker

# Verify Docker Compose plugin (v2 style)
docker compose version >/dev/null 2>&1 || fatal "Docker Compose plugin not found. Install Docker Desktop or 'docker compose' CLI plugin."

info "Installing Mintkey into: ${INSTALL_DIR}"
mkdir -p "${CONFIG_DIR}" "${DATA_DIR}"

# ---------------------------------------------------------------------------
# 1. Download docker-compose.ghcr.yml
# ---------------------------------------------------------------------------
info "Downloading ${COMPOSE_FILE} ..."
fetch "${COMPOSE_URL}" "${INSTALL_DIR}/${COMPOSE_FILE}"

# ---------------------------------------------------------------------------
# 2. Download bind-mounted config files
# ---------------------------------------------------------------------------
info "Downloading config files ..."

# Liquibase changelog (admin-api/db/changelog)
for f in \
  db.changelog-master.yaml \
  001-tenants.yaml \
  002-operators.yaml \
  003-agents.yaml \
  004-services.yaml \
  005-credentials.yaml \
  006-permission-grants.yaml \
  007-audit-events.yaml \
  008-platform-tables.yaml \
  009-roles.yaml \
  010-indexes.yaml \
  011-schema-fixes.yaml \
  012-service-api-keys.yaml \
  013-agent-key-lifecycle.yaml \
  014-operators-keycloak.yaml \
  015-app-role-passwords.yaml \
  016-sessions-auth-method.yaml \
  017-services-template-id.yaml; do
  fetch \
    "${RAW_BASE}/apps/admin-api/db/changelog/${f}" \
    "${CONFIG_DIR}/apps/admin-api/db/changelog/${f}"
done

# Kong declarative config
fetch \
  "${RAW_BASE}/apps/proxy-plugin/kong.yml" \
  "${CONFIG_DIR}/apps/proxy-plugin/kong.yml"

# OTel collector config
fetch \
  "${RAW_BASE}/infra/observability/otel-collector-config.yaml" \
  "${CONFIG_DIR}/infra/observability/otel-collector-config.yaml"

# Prometheus config + alert rules
fetch \
  "${RAW_BASE}/infra/observability/prometheus.yml" \
  "${CONFIG_DIR}/infra/observability/prometheus.yml"

fetch \
  "${RAW_BASE}/infra/observability/alert_rules.yml" \
  "${CONFIG_DIR}/infra/observability/alert_rules.yml"

# Grafana provisioning — dashboards provider + datasource
fetch \
  "${RAW_BASE}/infra/observability/grafana/provisioning/dashboards/provider.yaml" \
  "${CONFIG_DIR}/infra/observability/grafana/provisioning/dashboards/provider.yaml"

fetch \
  "${RAW_BASE}/infra/observability/grafana/provisioning/datasources/prometheus.yaml" \
  "${CONFIG_DIR}/infra/observability/grafana/provisioning/datasources/prometheus.yaml"

# Grafana dashboard JSONs
for f in \
  mintkey-audit.json \
  mintkey-credential-cache.json \
  mintkey-memory.json \
  mintkey-overview.json \
  mintkey-per-service.json \
  request-monitoring.json; do
  fetch \
    "${RAW_BASE}/infra/observability/grafana/provisioning/dashboards/${f}" \
    "${CONFIG_DIR}/infra/observability/grafana/provisioning/dashboards/${f}"
done

info "Config files downloaded."

# ---------------------------------------------------------------------------
# 3. Generate or load Fernet KEK
# ---------------------------------------------------------------------------
if [ -f "${ENV_FILE}" ] && grep -q "^MINTKEY_BOOTSTRAP_KEK=" "${ENV_FILE}" 2>/dev/null; then
  info ".env already contains MINTKEY_BOOTSTRAP_KEK — preserving existing key."
  MINTKEY_BOOTSTRAP_KEK="$(grep '^MINTKEY_BOOTSTRAP_KEK=' "${ENV_FILE}" | head -1 | cut -d= -f2-)"
else
  info "Generating Fernet KEK ..."
  # Try python3 cryptography first (produces a proper Fernet key).
  if python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" >/dev/null 2>&1; then
    MINTKEY_BOOTSTRAP_KEK="$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())")"
  elif command -v openssl >/dev/null 2>&1; then
    # Fernet key = URL-safe base64 of 32 random bytes = exactly 44 chars with one trailing =
    _raw="$(openssl rand -base64 32 | tr '/+' '_-' | tr -d '\n=')"
    MINTKEY_BOOTSTRAP_KEK="${_raw}="
    if [ ${#MINTKEY_BOOTSTRAP_KEK} -ne 44 ]; then
      fatal "generated KEK has wrong length (${#MINTKEY_BOOTSTRAP_KEK} chars, expected 44); openssl output was unexpected"
    fi
  else
    fatal "Cannot generate Fernet key: python3 (cryptography) or openssl required. Install one and retry."
  fi
  info "KEK generated."
fi

# ---------------------------------------------------------------------------
# 4. Write .env (idempotent — preserve existing values, append new ones)
# ---------------------------------------------------------------------------
_write_env_var() {
  _key="$1" _val="$2"
  if [ -f "${ENV_FILE}" ] && grep -q "^${_key}=" "${ENV_FILE}" 2>/dev/null; then
    : # already present — leave it
  else
    printf '%s=%s\n' "$_key" "$_val" >> "${ENV_FILE}"
  fi
}

info "Writing .env ..."
# Bootstrap KEK (may be new even if file exists)
if ! ([ -f "${ENV_FILE}" ] && grep -q "^MINTKEY_BOOTSTRAP_KEK=" "${ENV_FILE}" 2>/dev/null); then
  printf 'MINTKEY_BOOTSTRAP_KEK=%s\n' "${MINTKEY_BOOTSTRAP_KEK}" >> "${ENV_FILE}"
fi

_write_env_var "MINTKEY_TAG"                   "latest"
_write_env_var "MINTKEY_MCP_PUBLIC_URL"        "http://localhost:8082"
_write_env_var "MINTKEY_PROXY_PUBLIC_URL"      "http://localhost:8000"
_write_env_var "MINTKEY_ADMIN_API_PUBLIC_URL"  "http://localhost:8080"
_write_env_var "MINTKEY_ADMIN_UI_PUBLIC_URL"   "http://localhost:8081"
_write_env_var "MINTKEY_GRAFANA_PUBLIC_URL"    "http://localhost:3003"
_write_env_var "MINTKEY_JAEGER_PUBLIC_URL"     "http://localhost:16686"
_write_env_var "MINTKEY_KEYCLOAK_PUBLIC_URL"   "http://localhost:8443"
_write_env_var "MINTKEY_KEYCLOAK_INTERNAL_URL" "http://keycloak:8443"

# ---------------------------------------------------------------------------
# 5. Pull images + start stack
# ---------------------------------------------------------------------------
info "Pulling images (this may take a few minutes on first run) ..."
docker compose \
  --project-directory "${INSTALL_DIR}" \
  -f "${INSTALL_DIR}/${COMPOSE_FILE}" \
  --env-file "${ENV_FILE}" \
  pull

info "Starting Mintkey stack ..."
docker compose \
  --project-directory "${INSTALL_DIR}" \
  -f "${INSTALL_DIR}/${COMPOSE_FILE}" \
  --env-file "${ENV_FILE}" \
  up -d --remove-orphans

# ---------------------------------------------------------------------------
# 6. Post-install instructions
# ---------------------------------------------------------------------------
cat <<EOF

=========================================================
  Mintkey is starting up!
=========================================================

  Admin UI:   http://localhost:8081
  Admin API:  http://localhost:8080/v1/health
  MCP server: http://localhost:8082
  Grafana:    http://localhost:3003
  Jaeger:     http://localhost:16686
  Keycloak:   http://localhost:8443

To retrieve the bootstrap admin password once the seed-job
completes (watch with: docker compose logs -f seed-job):

  MINTKEY_BOOTSTRAP_KEK=\$(grep MINTKEY_BOOTSTRAP_KEK "${ENV_FILE}" | cut -d= -f2-)
  python3 - <<'PYEOF'
import sys, os
from cryptography.fernet import Fernet
kek = os.environ['MINTKEY_BOOTSTRAP_KEK'].encode()
with open('${DATA_DIR}/admin_password', 'rb') as f:
    print(Fernet(kek).decrypt(f.read().strip()).decode())
PYEOF

IMPORTANT: Keep ${ENV_FILE} safe.
Losing MINTKEY_BOOTSTRAP_KEK makes the bootstrap admin
password unrecoverable without a full stack reset.

To stop:  docker compose -f "${INSTALL_DIR}/${COMPOSE_FILE}" down
To reset: docker compose -f "${INSTALL_DIR}/${COMPOSE_FILE}" down -v
=========================================================
EOF
