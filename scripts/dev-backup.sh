#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# dev-backup.sh — Capture local Mintkey developer state to a timestamped,
#                 gitignored backup directory.
#
# Usage:
#   bash scripts/dev-backup.sh [--dry-run] [--write] [--with-secrets]
#                               [--backup-root <path>] [--help]
#
# By default the script runs in --dry-run mode: it prints what would be
# captured but writes no files.  Pass --write to actually create the backup.
#
# Secrets are REDACTED by default (keys-only for env files; metadata-only for
# binary secrets).  Pass --with-secrets to include encrypted payloads; the
# MINTKEY_BOOTSTRAP_KEK env var must be set.
#
# EvidenceRefs:
#   EV-ENV-002     .env (local user config, must never commit)
#   EV-ENV-003     .env.local (local user config, must never commit)
#   EV-ENV-005     apps/admin-ui/e2e/.env.local (generated secret, gitignore gap)
#   EV-APP-002     apps/admin-ui/e2e/.env.local alias for EV-ENV-005
#   EV-BOOTSTRAP-001..006  bootstrap-secrets directory contents
#   EV-VOL-001     postgres_data / pg_dump
#   EV-VOL-002     vault_data volume snapshot
#   EV-VOL-003     vault_kek volume snapshot
#   EV-VOL-004     bootstrap_secrets volume snapshot
#   EV-DB-001..008 DB tables (agents, services, permissions, etc.)
#   EV-COMPOSE-001..003  running services + image digests
#   EV-WIPE-001    anchor incident motivating the entire backup workflow
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(dirname "$SCRIPT_DIR")"

# ── Colour helpers (matches e2e-setup-env.sh style) ───────────────────────────
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▸${RESET} $*"; }
ok()      { echo -e "${GREEN}  ✅ $*${RESET}"; }
warn()    { echo -e "${YELLOW}  ⚠  $*${RESET}" >&2; }
err()     { echo -e "${RED}  ❌ $*${RESET}" >&2; }
heading() { echo -e "\n${BOLD}$*${RESET}"; }

# ── Defaults ──────────────────────────────────────────────────────────────────
DRY_RUN=1          # default: dry-run; --write clears this
WITH_SECRETS=0
BACKUP_ROOT=""     # override with --backup-root <path>

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      cat <<'HELPEOF'
dev-backup.sh — Mintkey local developer state backup

USAGE
  bash scripts/dev-backup.sh [OPTIONS]

OPTIONS
  --dry-run         (default) Print what would be captured; no files written.
  --write           Actually perform the backup.
  --with-secrets    Include encrypted secret payloads in the backup.
                    Requires MINTKEY_BOOTSTRAP_KEK env var to be set.
                    Exit 2 if unset.
  --backup-root <p> Override the default .mintkey-backups/ root (testing).
  --help            Print this help and exit 0.

DEFAULTS
  The script defaults to --dry-run.  No files are written unless --write is
  passed explicitly.

WHAT IS CAPTURED
  .env                               keys-only (REDACTED)     EV-ENV-002
  .env.local                         keys-only (REDACTED)     EV-ENV-003
  apps/admin-ui/e2e/.env.local       keys-only (REDACTED)     EV-ENV-005/EV-APP-002
  data/bootstrap-secrets/*           existence+sha256 only    EV-BOOTSTRAP-001..006
  postgres mintkey pg_dump (gzip)    if postgres healthy       EV-VOL-001/EV-DB-001..008
  vault_data volume snapshot (tar)   if vault-adapter running  EV-VOL-002/EV-VOL-003
  vault_kek volume snapshot (tar)    if vault-adapter running  EV-VOL-003
  bootstrap_secrets snapshot (tar)   always (sealed)           EV-VOL-004
  services.json (docker compose ps)  running service list      EV-COMPOSE-001..003
  manifest.json                      index of all captured     all above

WITH --with-secrets (additive)
  env files are Fernet-encrypted with MINTKEY_BOOTSTRAP_KEK instead of redacted.
  bootstrap-secrets are copied as-is (already Fernet-encrypted).
  pg_dump is Fernet-encrypted before writing.
  manifest gains secrets:true + kek_fingerprint (first 8 hex chars of sha256(KEK)).
  SECRET VALUES ARE NEVER PRINTED TO STDOUT/STDERR IN ANY MODE.

EXIT CODES
  0  success
  1  missing prerequisite (docker not running when expected)
  2  --with-secrets requested but MINTKEY_BOOTSTRAP_KEK is unset
  3  .mintkey-backups/ not in .gitignore — preflight failed
  4  backup root not writable
  5  user aborted
HELPEOF
      exit 0
      ;;
    --dry-run)     DRY_RUN=1 ;;
    --write)       DRY_RUN=0 ;;
    --with-secrets) WITH_SECRETS=1 ;;
    --backup-root)
      shift
      BACKUP_ROOT="$1"
      ;;
    *)
      err "Unknown option: $1 (try --help)"
      exit 1
      ;;
  esac
  shift
done

# ── 0. Must be inside the repo ────────────────────────────────────────────────
heading "Preflight checks"
if ! git -C "$REPO_ROOT" rev-parse --show-toplevel &>/dev/null; then
  err "Not inside a git repository. Cannot run backup outside the Mintkey repo root."
  exit 1
fi

# ── 0a. KEK check for --with-secrets ─────────────────────────────────────────
if [[ $WITH_SECRETS -eq 1 ]]; then
  if [[ -z "${MINTKEY_BOOTSTRAP_KEK:-}" ]]; then
    err "--with-secrets requested but MINTKEY_BOOTSTRAP_KEK is not set in the environment."
    err "Set it to the Fernet key used at bootstrap time, then re-run."
    exit 2
  fi
fi

# ── 0b. Gitignore preflight ───────────────────────────────────────────────────
GITIGNORE_FILE="${REPO_ROOT}/.gitignore"
if [[ ! -f "$GITIGNORE_FILE" ]] || ! grep -q '^\.mintkey-backups/' "$GITIGNORE_FILE"; then
  err ".mintkey-backups/ is not in ${GITIGNORE_FILE}."
  err "Fix: echo '.mintkey-backups/' >> ${GITIGNORE_FILE}"
  err "This is required to prevent secrets from being accidentally committed to git."
  exit 3
fi
ok "Gitignore entry present: .mintkey-backups/"

# ── 0c. Resolve backup root ───────────────────────────────────────────────────
if [[ -z "$BACKUP_ROOT" ]]; then
  BACKUP_ROOT="${REPO_ROOT}/.mintkey-backups"
fi

# ── 0d. Generate timestamped backup directory name ───────────────────────────
TIMESTAMP="$(date -u '+%Y%m%dT%H%M%SZ')"
SHORT_HOST="$(hostname -s 2>/dev/null || echo 'unknown')"
BACKUP_DIR="${BACKUP_ROOT}/${TIMESTAMP}-${SHORT_HOST}"

if [[ $DRY_RUN -eq 1 ]]; then
  info "DRY-RUN mode — no files will be written."
  info "Would create backup at: ${BACKUP_DIR}"
else
  # Ensure backup root is writable
  mkdir -p "$BACKUP_ROOT" 2>/dev/null || { err "Cannot create backup root: $BACKUP_ROOT"; exit 4; }
  if [[ ! -w "$BACKUP_ROOT" ]]; then
    err "Backup root is not writable: $BACKUP_ROOT"
    exit 4
  fi
  mkdir -p "$BACKUP_DIR"
  ok "Backup directory created: ${BACKUP_DIR}"
fi

# ── Helper: redact an env file (keys-only) ───────────────────────────────────
# Writes KEY=<redacted> for every non-blank, non-comment line.
# EvidenceRef: EV-ENV-002, EV-ENV-003, EV-ENV-005
redact_env_file() {
  local src="$1"
  while IFS= read -r line; do
    if [[ "$line" =~ ^[[:space:]]*# ]] || [[ -z "${line// /}" ]]; then
      echo "$line"
    elif [[ "$line" =~ ^([A-Za-z_][A-Za-z0-9_]*)= ]]; then
      echo "${BASH_REMATCH[1]}=<redacted>"
    else
      echo "$line"
    fi
  done < "$src"
}

# ── Helper: sha256 of a file ─────────────────────────────────────────────────
file_sha256() {
  local f="$1"
  if command -v sha256sum &>/dev/null; then
    sha256sum "$f" | awk '{print $1}'
  else
    shasum -a 256 "$f" | awk '{print $1}'
  fi
}

# ── Helper: Fernet-encrypt a file to a destination ───────────────────────────
# Uses python3 cryptography.fernet (already a project dep, matches
# scripts/e2e-setup-env.sh:71-77 pattern).
# Never prints the plaintext.  EvidenceRef: EV-SECRET-002
fernet_encrypt_file() {
  local src="$1"
  local dst="$2"
  local kek="$3"
  python3 - "$src" "$dst" "$kek" <<'PYEOF'
import sys
from cryptography.fernet import Fernet
src, dst, kek = sys.argv[1], sys.argv[2], sys.argv[3]
plaintext = open(src, "rb").read()
ciphertext = Fernet(kek.encode()).encrypt(plaintext)
open(dst, "wb").write(ciphertext)
PYEOF
}

# ── Helper: KEK fingerprint (first 8 hex chars of sha256(kek)) ───────────────
kek_fingerprint() {
  local kek="$1"
  printf '%s' "$kek" | python3 -c "
import sys, hashlib
kek = sys.stdin.read()
print(hashlib.sha256(kek.encode()).hexdigest()[:8])
"
}

# ── Manifest accumulator ──────────────────────────────────────────────────────
# MANIFEST_LINES holds JSON objects (one per line) appended throughout.
MANIFEST_LINES=()
CAPTURED_COUNT=0
CAPTURED_BYTES=0

# Adds an entry to the in-memory manifest.
# Args: rel_path size sha256 classification redacted(true|false)
manifest_add() {
  local rel_path="$1" size="$2" sha256="$3" classification="$4" redacted="$5"
  MANIFEST_LINES+=("{\"path\":\"${rel_path}\",\"size\":${size},\"sha256\":\"${sha256}\",\"classification\":\"${classification}\",\"redacted\":${redacted}}")
  CAPTURED_COUNT=$((CAPTURED_COUNT + 1))
  CAPTURED_BYTES=$((CAPTURED_BYTES + size))
}

# ── Section 1: Env files ──────────────────────────────────────────────────────
heading "1. Env files"

# Captures one env file (redact or encrypt depending on mode)
# Args: src_path relative_dest_name classification evidenceref
capture_env_file() {
  local src="$1" rel_dest="$2" classification="$3" evref="$4"
  if [[ ! -f "${REPO_ROOT}/${src}" ]]; then
    info "  ${src} — not present (skipped)   [${evref}]"
    return 0
  fi
  local src_full="${REPO_ROOT}/${src}"
  local dest_name="${rel_dest}"
  if [[ $DRY_RUN -eq 1 ]]; then
    info "  WOULD capture: ${src} (${classification})   [${evref}]"
    if [[ $WITH_SECRETS -eq 1 ]]; then
      info "    → Fernet-encrypted copy (--with-secrets)"
    else
      info "    → keys-only (REDACTED)"
    fi
  else
    local dest_file="${BACKUP_DIR}/${dest_name}"
    if [[ $WITH_SECRETS -eq 1 ]]; then
      fernet_encrypt_file "$src_full" "${dest_file}.fernet" "${MINTKEY_BOOTSTRAP_KEK}"
      local sz; sz=$(wc -c < "${dest_file}.fernet" | tr -d ' ')
      local sha; sha=$(file_sha256 "${dest_file}.fernet")
      manifest_add "${dest_name}.fernet" "$sz" "$sha" "$classification" "false"
      ok "${src} — Fernet-encrypted   [${evref}]"
    else
      redact_env_file "$src_full" > "${dest_file}.redacted"
      local sz; sz=$(wc -c < "${dest_file}.redacted" | tr -d ' ')
      local sha; sha=$(file_sha256 "${dest_file}.redacted")
      manifest_add "${dest_name}.redacted" "$sz" "$sha" "$classification" "true"
      ok "${src} — redacted   [${evref}]"
    fi
  fi
}

capture_env_file ".env"                   "env"           "local user config"  "EV-ENV-002"
capture_env_file ".env.local"             "env_local"     "local user config"  "EV-ENV-003"
capture_env_file "apps/admin-ui/e2e/.env.local" "e2e_env_local" "local user config"  "EV-ENV-005/EV-APP-002"

# ── Section 2: bootstrap-secrets ─────────────────────────────────────────────
heading "2. bootstrap-secrets (data/bootstrap-secrets/)"
# EvidenceRef: EV-BOOTSTRAP-001..006

BOOTSTRAP_DIR="${REPO_ROOT}/data/bootstrap-secrets"
if [[ ! -d "$BOOTSTRAP_DIR" ]]; then
  warn "data/bootstrap-secrets/ does not exist — volume may not be mounted or stack not run yet."
else
  for f in "${BOOTSTRAP_DIR}"/*; do
    [[ -f "$f" ]] || continue
    fname="$(basename "$f")"
    if [[ $DRY_RUN -eq 1 ]]; then
      local_size=$(wc -c < "$f" | tr -d ' ')
      local_sha=$(file_sha256 "$f")
      info "  WOULD capture: data/bootstrap-secrets/${fname}   [EV-BOOTSTRAP-001..006]"
      info "    size=${local_size}  sha256=${local_sha:0:16}...  (existence+hash metadata only)"
      if [[ $WITH_SECRETS -eq 1 ]]; then
        info "    → full ciphertext copy (--with-secrets, already Fernet-encrypted)"
      fi
    else
      local_size=$(wc -c < "$f" | tr -d ' ')
      local_sha=$(file_sha256 "$f")
      if [[ $WITH_SECRETS -eq 1 ]]; then
        # Copy opaque ciphertext as-is (already Fernet-encrypted per e2e-setup-env.sh:68-79)
        cp "$f" "${BACKUP_DIR}/bootstrap_secret_${fname}"
        manifest_add "bootstrap_secret_${fname}" "$local_size" "$local_sha" "generated secret" "false"
        ok "data/bootstrap-secrets/${fname} — copied (opaque Fernet ciphertext)   [EV-BOOTSTRAP-001..006]"
      else
        # Write metadata-only marker
        cat > "${BACKUP_DIR}/bootstrap_secret_${fname}.meta" <<METAEOF
# EvidenceRef: EV-BOOTSTRAP-001..006
# Metadata-only marker — run with --with-secrets to include ciphertext.
filename=${fname}
size_bytes=${local_size}
sha256=${local_sha}
METAEOF
        meta_sz=$(wc -c < "${BACKUP_DIR}/bootstrap_secret_${fname}.meta" | tr -d ' ')
        manifest_add "bootstrap_secret_${fname}.meta" "$meta_sz" "$(file_sha256 "${BACKUP_DIR}/bootstrap_secret_${fname}.meta")" "generated secret" "true"
        ok "data/bootstrap-secrets/${fname} — metadata marker written   [EV-BOOTSTRAP-001..006]"
      fi
    fi
  done
fi

# ── Section 3: postgres pg_dump ───────────────────────────────────────────────
heading "3. Postgres pg_dump"
# EvidenceRef: EV-VOL-001, EV-DB-001..008

PG_HEALTHY=0
if docker compose -f "${REPO_ROOT}/infra/compose/docker-compose.yml" ps --format json 2>/dev/null \
    | python3 -c "
import sys, json
# Fix: docker compose ps --format json returns Service='postgres' and
# Name='mintkey-postgres-1'. The prior check used Name.endswith('postgres')
# which never matched because Compose appends '-N' to container names.
# Use the Service field instead — it's the stable compose service identifier.
data = sys.stdin.read().strip()
rows = json.loads(data) if data.startswith('[') else [json.loads(l) for l in data.splitlines() if l.strip()]
healthy = any(r.get('Service','') == 'postgres' and r.get('Health','') == 'healthy' and r.get('State','') == 'running' for r in rows)
sys.exit(0 if healthy else 1)
" 2>/dev/null; then
  PG_HEALTHY=1
fi

if [[ $PG_HEALTHY -eq 0 ]]; then
  if [[ $DRY_RUN -eq 1 ]]; then
    warn "postgres container not running/healthy — pg_dump would be skipped (postgres_dump.skipped marker)"
  else
    {
      echo "# EvidenceRef: EV-VOL-001, EV-DB-001..008"
      echo "# Postgres container was not running or not healthy at backup time."
      echo "reason=container_not_running_or_unhealthy"
      echo "timestamp=${TIMESTAMP}"
    } > "${BACKUP_DIR}/postgres_dump.skipped"
    local_sz=$(wc -c < "${BACKUP_DIR}/postgres_dump.skipped" | tr -d ' ')
    manifest_add "postgres_dump.skipped" "$local_sz" "$(file_sha256 "${BACKUP_DIR}/postgres_dump.skipped")" "seeded database state" "false"
    warn "postgres not running — wrote postgres_dump.skipped marker   [EV-VOL-001]"
  fi
else
  if [[ $DRY_RUN -eq 1 ]]; then
    info "WOULD pg_dump mintkey database (gzip) via docker compose exec postgres   [EV-VOL-001/EV-DB-001..008]"
    if [[ $WITH_SECRETS -eq 1 ]]; then
      info "  → then Fernet-encrypt the gzipped dump (--with-secrets)"
    fi
  else
    DUMP_TMP="${BACKUP_DIR}/postgres_dump.sql.gz.tmp"
    info "Running pg_dump…"
    if docker compose -f "${REPO_ROOT}/infra/compose/docker-compose.yml" exec -T postgres \
        pg_dump -U mintkey_migrate -d mintkey --no-owner --no-privileges 2>/dev/null \
        | gzip > "$DUMP_TMP"; then
      if [[ $WITH_SECRETS -eq 1 ]]; then
        fernet_encrypt_file "$DUMP_TMP" "${BACKUP_DIR}/postgres_dump.sql.gz.fernet" "${MINTKEY_BOOTSTRAP_KEK}"
        rm -f "$DUMP_TMP"
        local_sz=$(wc -c < "${BACKUP_DIR}/postgres_dump.sql.gz.fernet" | tr -d ' ')
        manifest_add "postgres_dump.sql.gz.fernet" "$local_sz" "$(file_sha256 "${BACKUP_DIR}/postgres_dump.sql.gz.fernet")" "seeded database state" "false"
        ok "pg_dump complete — Fernet-encrypted   [EV-VOL-001/EV-DB-001..008]"
      else
        mv "$DUMP_TMP" "${BACKUP_DIR}/postgres_dump.sql.gz"
        local_sz=$(wc -c < "${BACKUP_DIR}/postgres_dump.sql.gz" | tr -d ' ')
        manifest_add "postgres_dump.sql.gz" "$local_sz" "$(file_sha256 "${BACKUP_DIR}/postgres_dump.sql.gz")" "seeded database state" "false"
        ok "pg_dump complete   [EV-VOL-001/EV-DB-001..008]"
      fi
    else
      warn "pg_dump failed — writing skipped marker   [EV-VOL-001]"
      rm -f "$DUMP_TMP"
      cat > "${BACKUP_DIR}/postgres_dump.skipped" <<SKIPEOF
# EvidenceRef: EV-VOL-001, EV-DB-001..008
reason=pg_dump_command_failed
timestamp=${TIMESTAMP}
SKIPEOF
      local_sz=$(wc -c < "${BACKUP_DIR}/postgres_dump.skipped" | tr -d ' ')
      manifest_add "postgres_dump.skipped" "$local_sz" "$(file_sha256 "${BACKUP_DIR}/postgres_dump.skipped")" "seeded database state" "false"
    fi
  fi
fi

# ── Section 4: Docker volume snapshots ────────────────────────────────────────
heading "4. Docker volume snapshots"

# Check if vault-adapter is running
# EvidenceRef: EV-VOL-002, EV-VOL-003, EV-VOL-004
VAULT_RUNNING=0
if docker compose -f "${REPO_ROOT}/infra/compose/docker-compose.yml" ps --format json 2>/dev/null \
    | python3 -c "
import sys, json
data = sys.stdin.read().strip()
rows = json.loads(data) if data.startswith('[') else [json.loads(l) for l in data.splitlines() if l.strip()]
ok = any('vault' in str(r.get('Name','')).lower() and r.get('State','') == 'running' for r in rows)
sys.exit(0 if ok else 1)
" 2>/dev/null; then
  VAULT_RUNNING=1
fi

# Capture a Docker named volume using alpine tar
# Args: volume_name dest_tar_name evidenceref
capture_volume() {
  local vol="$1" dest_name="$2" evref="$3"
  if [[ $DRY_RUN -eq 1 ]]; then
    info "  WOULD snapshot volume ${vol} → ${dest_name}   [${evref}]"
  else
    if docker run --rm \
        -v "${vol}:/data" \
        -v "${BACKUP_DIR}:/backup" \
        alpine tar czf "/backup/${dest_name}" /data 2>/dev/null; then
      local_sz=$(wc -c < "${BACKUP_DIR}/${dest_name}" | tr -d ' ')
      manifest_add "$dest_name" "$local_sz" "$(file_sha256 "${BACKUP_DIR}/${dest_name}")" "Docker volume state" "false"
      ok "Volume ${vol} → ${dest_name}   [${evref}]"
    else
      warn "Volume snapshot failed: ${vol}   [${evref}]"
    fi
  fi
}

if [[ $VAULT_RUNNING -eq 1 ]]; then
  capture_volume "mintkey_vault_data"  "vault_data.tar.gz"  "EV-VOL-002/EV-VOL-003"
  capture_volume "mintkey_vault_kek"   "vault_kek.tar.gz"   "EV-VOL-003"
else
  warn "vault-adapter not running — vault_data and vault_kek snapshots skipped   [EV-VOL-002/EV-VOL-003]"
  if [[ $DRY_RUN -eq 0 ]]; then
    for skipped_vol in vault_data vault_kek; do
      cat > "${BACKUP_DIR}/${skipped_vol}.skipped" <<SKIPEOF
# EvidenceRef: EV-VOL-002/EV-VOL-003
reason=vault_adapter_not_running
timestamp=${TIMESTAMP}
SKIPEOF
      local_sz=$(wc -c < "${BACKUP_DIR}/${skipped_vol}.skipped" | tr -d ' ')
      manifest_add "${skipped_vol}.skipped" "$local_sz" "$(file_sha256 "${BACKUP_DIR}/${skipped_vol}.skipped")" "Docker volume state" "false"
    done
  fi
fi

# bootstrap_secrets volume — always attempt (seed-job mounts it rw)
# EvidenceRef: EV-VOL-004
if docker volume inspect mintkey_bootstrap_secrets &>/dev/null 2>&1; then
  capture_volume "mintkey_bootstrap_secrets" "bootstrap_secrets.tar.gz" "EV-VOL-004"
else
  warn "Volume mintkey_bootstrap_secrets not found — skipping snapshot   [EV-VOL-004]"
  if [[ $DRY_RUN -eq 0 ]]; then
    cat > "${BACKUP_DIR}/bootstrap_secrets.skipped" <<SKIPEOF
# EvidenceRef: EV-VOL-004
reason=volume_not_found
timestamp=${TIMESTAMP}
SKIPEOF
    local_sz=$(wc -c < "${BACKUP_DIR}/bootstrap_secrets.skipped" | tr -d ' ')
    manifest_add "bootstrap_secrets.skipped" "$local_sz" "$(file_sha256 "${BACKUP_DIR}/bootstrap_secrets.skipped")" "Docker volume state" "false"
  fi
fi

# ── Section 5: Running services list ─────────────────────────────────────────
heading "5. Running services + image digests"
# EvidenceRef: EV-COMPOSE-001..003

if [[ $DRY_RUN -eq 1 ]]; then
  info "WOULD capture: docker compose ps --format json → services.json   [EV-COMPOSE-001..003]"
else
  if docker compose -f "${REPO_ROOT}/infra/compose/docker-compose.yml" ps --format json \
      > "${BACKUP_DIR}/services.json" 2>/dev/null; then
    local_sz=$(wc -c < "${BACKUP_DIR}/services.json" | tr -d ' ')
    manifest_add "services.json" "$local_sz" "$(file_sha256 "${BACKUP_DIR}/services.json")" "repo-tracked default" "false"
    ok "services.json written   [EV-COMPOSE-001..003]"
  else
    warn "docker compose ps failed — services.json not written   [EV-COMPOSE-001..003]"
  fi
fi

# ── Section 6: Write manifest.json ───────────────────────────────────────────
heading "6. Manifest"

if [[ $DRY_RUN -eq 1 ]]; then
  info "WOULD write manifest.json with ${#MANIFEST_LINES[@]} entries"
else
  # Build JSON
  {
    echo "{"
    echo "  \"session\": \"dev-backup\","
    echo "  \"timestamp\": \"${TIMESTAMP}\","
    echo "  \"host\": \"${SHORT_HOST}\","
    echo "  \"backup_dir\": \"${BACKUP_DIR}\","
    if [[ $WITH_SECRETS -eq 1 ]]; then
      echo "  \"secrets\": true,"
      echo "  \"kek_fingerprint\": \"$(kek_fingerprint "${MINTKEY_BOOTSTRAP_KEK}")\","
    else
      echo "  \"secrets\": false,"
    fi
    echo "  \"files\": ["
    first=1
    for line in "${MANIFEST_LINES[@]}"; do
      if [[ $first -eq 1 ]]; then
        echo "    ${line}"
        first=0
      else
        echo "    ,${line}"
      fi
    done
    echo "  ]"
    echo "}"
  } > "${BACKUP_DIR}/manifest.json"
  ok "manifest.json written (${CAPTURED_COUNT} entries)"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
echo "" >&2
if [[ $DRY_RUN -eq 1 ]]; then
  echo -e "${BOLD}DRY-RUN summary${RESET} — no files written." >&2
  echo "  Would have captured the items listed above." >&2
  echo "  Re-run with --write to actually create the backup." >&2
else
  echo -e "${BOLD}Backup summary${RESET}" >&2
  printf "  Files captured : %d\n" "$CAPTURED_COUNT" >&2
  printf "  Total size     : %d bytes\n" "$CAPTURED_BYTES" >&2
  printf "  Backup path    : %s\n" "$BACKUP_DIR" >&2
fi
