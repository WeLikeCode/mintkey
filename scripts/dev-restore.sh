#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# dev-restore.sh — Restore local Mintkey developer state from a backup
#                  created by dev-backup.sh.
#
# Usage:
#   bash scripts/dev-restore.sh [OPTIONS] <backup-directory>
#
# By default the script runs in --dry-run mode: it reads the manifest and
# shows what would change without writing anything.  Pass --apply to restore.
# Most operations require explicit per-file confirmation unless --yes is given.
#
# EvidenceRefs:
#   EV-ENV-002       .env restore
#   EV-ENV-003       .env.local restore
#   EV-ENV-005       admin-ui/e2e/.env.local restore
#   EV-APP-002       alias for EV-ENV-005
#   EV-BOOTSTRAP-001..006  bootstrap-secrets restore
#   EV-VOL-001       postgres_data / pg_dump restore
#   EV-VOL-002       vault_data volume restore
#   EV-VOL-003       vault_kek volume restore
#   EV-VOL-004       bootstrap_secrets volume restore
#   EV-DB-001..008   DB table restore
#   EV-WIPE-001      anchor incident motivating this script
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
DRY_RUN=1
APPLY=0
YES=0
WITH_SECRETS=0
ACCEPT_STALE=0
BACKUP_DIR=""

# ── Argument parsing ──────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --help|-h)
      cat <<'HELPEOF'
dev-restore.sh — Mintkey local developer state restore

USAGE
  bash scripts/dev-restore.sh [OPTIONS] <backup-directory>

ARGUMENTS
  <backup-directory>  Path to a backup directory created by dev-backup.sh.
                      Must contain a manifest.json.

OPTIONS
  --dry-run           (default) Diff backup vs current; show what would change.
                      No files are written.
  --apply             Actually restore files.  Still prompts y/n per file
                      unless --yes is also given.
  --yes               Skip per-file prompts (use with --apply).
  --with-secrets      Decrypt secret payloads using MINTKEY_BOOTSTRAP_KEK.
                      Required when the backup has secrets:true in its manifest.
                      Exit 4 if MINTKEY_BOOTSTRAP_KEK is unset.
  --accept-stale      Proceed even when the backup's kek_fingerprint does not
                      match the current environment's KEK (cross-env restore).
                      Without this flag, a mismatch causes exit 3.
  --help              Print this help and exit 0.

CLASSIFICATION-BASED BEHAVIOUR
  repo-tracked default   SKIP — already in git; restoring would clobber the
                         live source.
  local user config      Diff + prompt (or --yes) → write.
  generated secret       Requires --with-secrets; decrypt + diff + prompt.
                         Skipped silently in default mode with a note.
  Docker volume state    Requires --apply + --with-secrets; always prompts
                         with the volume name before an irreversible restore.
  seeded database state  Requires --apply + --with-secrets; prompts explicitly
                         before DROP+restore.

EXIT CODES
  0  success (or dry-run completed with no changes needed)
  1  backup directory not found / manifest.json missing
  2  user declined
  3  KEK fingerprint mismatch + --accept-stale not passed
  4  --with-secrets requested but MINTKEY_BOOTSTRAP_KEK is unset
HELPEOF
      exit 0
      ;;
    --dry-run)      DRY_RUN=1;  APPLY=0 ;;
    --apply)        DRY_RUN=0;  APPLY=1 ;;
    --yes)          YES=1 ;;
    --with-secrets) WITH_SECRETS=1 ;;
    --accept-stale) ACCEPT_STALE=1 ;;
    -*)
      err "Unknown option: $1 (try --help)"
      exit 1
      ;;
    *)
      if [[ -z "$BACKUP_DIR" ]]; then
        BACKUP_DIR="$1"
      else
        err "Unexpected positional argument: $1"
        exit 1
      fi
      ;;
  esac
  shift
done

# ── 0. Validate backup directory ─────────────────────────────────────────────
heading "Preflight checks"

if [[ -z "$BACKUP_DIR" ]]; then
  err "No backup directory specified.  Usage: dev-restore.sh [OPTIONS] <backup-directory>"
  exit 1
fi

if [[ ! -d "$BACKUP_DIR" ]]; then
  err "Backup directory not found: ${BACKUP_DIR}"
  exit 1
fi

MANIFEST_FILE="${BACKUP_DIR}/manifest.json"
if [[ ! -f "$MANIFEST_FILE" ]]; then
  err "manifest.json not found in ${BACKUP_DIR}"
  err "This directory was not created by dev-backup.sh or is incomplete."
  exit 1
fi
ok "manifest.json found: ${MANIFEST_FILE}"

# ── 0a. Parse manifest ────────────────────────────────────────────────────────
MANIFEST_SECRETS="$(python3 -c "
import sys, json
m = json.load(open('${MANIFEST_FILE}'))
print(str(m.get('secrets', False)).lower())
" 2>/dev/null || echo "false")"

MANIFEST_KEK_FP="$(python3 -c "
import sys, json
m = json.load(open('${MANIFEST_FILE}'))
print(m.get('kek_fingerprint', ''))
" 2>/dev/null || echo "")"

MANIFEST_TIMESTAMP="$(python3 -c "
import sys, json
m = json.load(open('${MANIFEST_FILE}'))
print(m.get('timestamp', 'unknown'))
" 2>/dev/null || echo "unknown")"

info "Backup timestamp : ${MANIFEST_TIMESTAMP}"
info "Backup has secrets: ${MANIFEST_SECRETS}"

# ── 0b. KEK check ─────────────────────────────────────────────────────────────
if [[ $WITH_SECRETS -eq 1 ]]; then
  if [[ -z "${MINTKEY_BOOTSTRAP_KEK:-}" ]]; then
    err "--with-secrets requested but MINTKEY_BOOTSTRAP_KEK is not set in the environment."
    exit 4
  fi
fi

# ── 0c. KEK fingerprint mismatch guard ───────────────────────────────────────
# EvidenceRef: EV-SECRET-002 (MINTKEY_BOOTSTRAP_KEK is a per-env Fernet key)
if [[ "$MANIFEST_SECRETS" == "true" && -n "$MANIFEST_KEK_FP" ]]; then
  if [[ -n "${MINTKEY_BOOTSTRAP_KEK:-}" ]]; then
    CURRENT_KEK_FP="$(printf '%s' "${MINTKEY_BOOTSTRAP_KEK}" | python3 -c "
import sys, hashlib
kek = sys.stdin.read()
print(hashlib.sha256(kek.encode()).hexdigest()[:8])
")"
    if [[ "$CURRENT_KEK_FP" != "$MANIFEST_KEK_FP" ]]; then
      warn "════════════════════════════════════════════════════════════════"
      warn "STALE SECRETS — different environment?"
      warn "Backup KEK fingerprint  : ${MANIFEST_KEK_FP}"
      warn "Current KEK fingerprint : ${CURRENT_KEK_FP}"
      warn "Restoring secrets from a different environment will fail to"
      warn "decrypt and may corrupt your local state."
      warn "════════════════════════════════════════════════════════════════"
      if [[ $ACCEPT_STALE -eq 0 ]]; then
        err "Aborting.  Re-run with --accept-stale to proceed anyway."
        exit 3
      else
        warn "Proceeding because --accept-stale was passed."
      fi
    else
      ok "KEK fingerprint matches (${CURRENT_KEK_FP})"
    fi
  fi
fi

# ── Helper: prompt y/n ────────────────────────────────────────────────────────
# Returns 0 if yes, 1 if no.
prompt_yn() {
  local msg="$1"
  if [[ $YES -eq 1 ]]; then
    echo -e "${CYAN}  [auto-yes]${RESET} ${msg}"
    return 0
  fi
  printf '%b' "${CYAN}  ${msg} [y/N]${RESET} "
  read -r _answer </dev/tty
  case "${_answer:-n}" in
    [Yy]*) return 0 ;;
    *)     return 1 ;;
  esac
}

# ── Helper: Fernet-decrypt a file ─────────────────────────────────────────────
# Writes decrypted content to a temp file; stdout is the temp path.
# Never prints plaintext directly.  EvidenceRef: EV-SECRET-002
fernet_decrypt_to_tmp() {
  local src="$1"
  local kek="$2"
  local tmp; tmp="$(mktemp)"
  python3 - "$src" "$tmp" "$kek" <<'PYEOF'
import sys
from cryptography.fernet import Fernet
src, dst, kek = sys.argv[1], sys.argv[2], sys.argv[3]
ciphertext = open(src, "rb").read()
plaintext = Fernet(kek.encode()).decrypt(ciphertext)
open(dst, "wb").write(plaintext)
PYEOF
  echo "$tmp"
}

# ── Helper: show diff between two files (or new file) ────────────────────────
show_diff() {
  local label="$1" backup_f="$2" current_f="$3"
  echo -e "\n  ${BOLD}--- diff for ${label} ---${RESET}"
  if [[ ! -f "$current_f" ]]; then
    echo "  (current file does not exist — this would be a NEW file)"
    return 0
  fi
  diff --unified=3 "$current_f" "$backup_f" 2>/dev/null || true
}

# ── Section: iterate manifest entries ─────────────────────────────────────────
heading "Processing manifest entries"

ENTRY_COUNT="$(python3 -c "
import json
m = json.load(open('${MANIFEST_FILE}'))
print(len(m.get('files', [])))
" 2>/dev/null || echo "0")"

info "Manifest contains ${ENTRY_COUNT} file entries."

RESTORED=0
SKIPPED=0
FAILED=0

# Iterate via python to avoid bash JSON parsing complexity
while IFS='|' read -r rel_path classification redacted; do
  backup_file="${BACKUP_DIR}/${rel_path}"

  case "$classification" in
    # ── repo-tracked default: always skip ─────────────────────────────────
    "repo-tracked default")
      info "  SKIP (repo-tracked): ${rel_path}"
      SKIPPED=$((SKIPPED + 1))
      continue
      ;;

    # ── local user config: diff + prompt ──────────────────────────────────
    "local user config")
      # Determine current file path from the backup filename
      current_file=""
      case "$rel_path" in
        env.redacted|env.fernet)         current_file="${REPO_ROOT}/.env" ;;
        env_local.redacted|env_local.fernet) current_file="${REPO_ROOT}/.env.local" ;;
        e2e_env_local.redacted|e2e_env_local.fernet) current_file="${REPO_ROOT}/apps/admin-ui/e2e/.env.local" ;;
        *)
          warn "  Unknown user-config path mapping: ${rel_path} — skipping"
          SKIPPED=$((SKIPPED + 1))
          continue
          ;;
      esac

      if [[ "$redacted" == "true" ]]; then
        # .redacted file: show the redacted diff (no secret values ever shown)
        if [[ $DRY_RUN -eq 1 ]]; then
          show_diff "$rel_path" "$backup_file" "$current_file"
        else
          show_diff "$rel_path" "$backup_file" "$current_file"
          if prompt_yn "Restore ${rel_path} → ${current_file}?"; then
            mkdir -p "$(dirname "$current_file")"
            cp "$backup_file" "$current_file"
            chmod 600 "$current_file"
            ok "Restored: ${current_file}"
            RESTORED=$((RESTORED + 1))
          else
            info "  Skipped by user: ${rel_path}"
            SKIPPED=$((SKIPPED + 1))
          fi
        fi
      else
        # Encrypted file: requires --with-secrets
        if [[ $WITH_SECRETS -eq 0 ]]; then
          info "  secret skipped — re-run with --with-secrets to include: ${rel_path}"
          SKIPPED=$((SKIPPED + 1))
        else
          tmp_plain="$(fernet_decrypt_to_tmp "$backup_file" "${MINTKEY_BOOTSTRAP_KEK}")"
          if [[ $DRY_RUN -eq 1 ]]; then
            show_diff "$rel_path (decrypted)" "$tmp_plain" "$current_file"
            rm -f "$tmp_plain"
          else
            show_diff "$rel_path (decrypted)" "$tmp_plain" "$current_file"
            if prompt_yn "Restore DECRYPTED ${rel_path} → ${current_file}?"; then
              mkdir -p "$(dirname "$current_file")"
              cp "$tmp_plain" "$current_file"
              chmod 600 "$current_file"
              ok "Restored (decrypted): ${current_file}"
              RESTORED=$((RESTORED + 1))
            else
              info "  Skipped by user: ${rel_path}"
              SKIPPED=$((SKIPPED + 1))
            fi
            rm -f "$tmp_plain"
          fi
        fi
      fi
      ;;

    # ── generated secret: bootstrap-secrets files ─────────────────────────
    "generated secret")
      if [[ "$redacted" == "true" ]]; then
        # Just a .meta marker; nothing to restore
        info "  secret (metadata-only) skipped — re-run with --with-secrets to include: ${rel_path}"
        SKIPPED=$((SKIPPED + 1))
      else
        # Actual ciphertext backup (--with-secrets was used at backup time)
        if [[ $WITH_SECRETS -eq 0 ]]; then
          info "  secret skipped — re-run with --with-secrets to include: ${rel_path}"
          SKIPPED=$((SKIPPED + 1))
        else
          # Derive target path from filename pattern: bootstrap_secret_<fname>
          fname="${rel_path#bootstrap_secret_}"
          target="${REPO_ROOT}/data/bootstrap-secrets/${fname}"
          if [[ $DRY_RUN -eq 1 ]]; then
            info "  WOULD restore: ${rel_path} → ${target}   [EV-BOOTSTRAP-001..006]"
          else
            if prompt_yn "Restore bootstrap secret ${fname}?   [EV-BOOTSTRAP-001..006]"; then
              mkdir -p "$(dirname "$target")"
              cp "$backup_file" "$target"
              chmod 600 "$target"
              ok "Restored bootstrap secret: ${fname}"
              RESTORED=$((RESTORED + 1))
            else
              info "  Skipped by user: ${rel_path}"
              SKIPPED=$((SKIPPED + 1))
            fi
          fi
        fi
      fi
      ;;

    # ── Docker volume state ───────────────────────────────────────────────
    "Docker volume state")
      # .skipped markers are informational only
      if [[ "$rel_path" == *.skipped ]]; then
        info "  Volume was skipped at backup time (marker): ${rel_path}"
        SKIPPED=$((SKIPPED + 1))
        continue
      fi
      if [[ $APPLY -eq 0 ]]; then
        info "  WOULD restore volume snapshot: ${rel_path}   (requires --apply + --with-secrets)"
        SKIPPED=$((SKIPPED + 1))
        continue
      fi
      if [[ $WITH_SECRETS -eq 0 ]]; then
        info "  volume snapshot skipped — re-run with --with-secrets to include: ${rel_path}"
        SKIPPED=$((SKIPPED + 1))
        continue
      fi
      # Infer volume name from file name: vault_data.tar.gz → mintkey_vault_data
      vol_base="${rel_path%.tar.gz}"
      vol_name="mintkey_${vol_base}"
      warn "════════════════════════════════════════════════════════════════"
      warn "DESTRUCTIVE VOLUME RESTORE"
      warn "This will OVERWRITE all data in Docker volume: ${vol_name}"
      warn "Any existing data in the volume WILL BE LOST."
      warn "════════════════════════════════════════════════════════════════"
      if prompt_yn "Restore volume ${vol_name} from ${rel_path}?"; then
        if docker run --rm \
            -v "${vol_name}:/data" \
            -v "${BACKUP_DIR}:/backup" \
            alpine sh -c "rm -rf /data/* /data/..?* /data/.[!.]* 2>/dev/null; tar xzf /backup/${rel_path} --strip-components=1 -C /data" 2>/dev/null; then
          ok "Volume ${vol_name} restored from ${rel_path}"
          RESTORED=$((RESTORED + 1))
        else
          err "Volume restore failed: ${vol_name}"
          FAILED=$((FAILED + 1))
        fi
      else
        info "  Skipped by user: ${rel_path}"
        SKIPPED=$((SKIPPED + 1))
      fi
      ;;

    # ── seeded database state ─────────────────────────────────────────────
    "seeded database state")
      if [[ "$rel_path" == *.skipped ]]; then
        info "  DB dump was skipped at backup time (marker): ${rel_path}"
        SKIPPED=$((SKIPPED + 1))
        continue
      fi
      if [[ $APPLY -eq 0 ]]; then
        info "  WOULD restore pg_dump: ${rel_path}   (requires --apply + --with-secrets)"
        SKIPPED=$((SKIPPED + 1))
        continue
      fi
      if [[ $WITH_SECRETS -eq 0 ]]; then
        info "  pg_dump skipped — re-run with --with-secrets to include: ${rel_path}"
        SKIPPED=$((SKIPPED + 1))
        continue
      fi
      warn "════════════════════════════════════════════════════════════════"
      warn "DESTRUCTIVE DATABASE RESTORE"
      warn "This will DROP and recreate tables in the mintkey database:"
      warn "  agents, services, permissions, tenants, operators,"
      warn "  credentials, audit_events, audit_chain_state,"
      warn "  permission_grants, and all other tables in the dump."
      warn "ALL EXISTING DATA WILL BE LOST."
      warn "════════════════════════════════════════════════════════════════"
      if prompt_yn "Restore pg_dump to mintkey database from ${rel_path}?"; then
        # Handle encrypted dump
        local_dump="$backup_file"
        tmp_decrypted=""
        if [[ "$rel_path" == *.fernet ]]; then
          tmp_decrypted="$(fernet_decrypt_to_tmp "$backup_file" "${MINTKEY_BOOTSTRAP_KEK}")"
          local_dump="$tmp_decrypted"
        fi
        if gunzip -c "$local_dump" \
            | docker compose -f "${REPO_ROOT}/infra/compose/docker-compose.yml" exec -T postgres \
              psql -U mintkey_migrate -d mintkey 2>/dev/null; then
          ok "pg_dump restored to mintkey database   [EV-VOL-001/EV-DB-001..008]"
          RESTORED=$((RESTORED + 1))
        else
          err "pg_dump restore failed"
          FAILED=$((FAILED + 1))
        fi
        [[ -n "$tmp_decrypted" ]] && rm -f "$tmp_decrypted"
      else
        info "  Skipped by user: ${rel_path}"
        SKIPPED=$((SKIPPED + 1))
      fi
      ;;

    *)
      warn "  Unknown classification '${classification}' for ${rel_path} — skipping"
      SKIPPED=$((SKIPPED + 1))
      ;;
  esac

done < <(python3 -c "
import json
m = json.load(open('${MANIFEST_FILE}'))
for f in m.get('files', []):
    print(f['path'] + '|' + f['classification'] + '|' + str(f.get('redacted', True)).lower())
" 2>/dev/null)

# ── Summary ───────────────────────────────────────────────────────────────────
echo "" >&2
if [[ $DRY_RUN -eq 1 ]]; then
  echo -e "${BOLD}DRY-RUN summary${RESET} — no files written." >&2
  echo "  Re-run with --apply to restore (and optionally --yes to skip prompts)." >&2
else
  echo -e "${BOLD}Restore summary${RESET}" >&2
  printf "  Restored : %d\n" "$RESTORED" >&2
  printf "  Skipped  : %d\n" "$SKIPPED" >&2
  printf "  Failed   : %d\n" "$FAILED" >&2
fi

if [[ $FAILED -gt 0 ]]; then
  exit 1
fi
exit 0
