#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# dev-backup-cron.example.sh — Operator-installed cron wrapper for dev-backup.sh
#
# PURPOSE
#   Runs scripts/dev-backup.sh --write [--with-secrets] on a schedule and prunes
#   backups older than MINTKEY_BACKUP_RETENTION_DAYS (default: 14).
#
# OPERATOR INSTALL (do NOT auto-install; see HOWTO-backup-before-reset.md):
#   1. Copy this file somewhere outside the repo, or reference it in-place.
#   2. Set the required env vars (MINTKEY_REPO_DIR, optionally
#      MINTKEY_BOOTSTRAP_KEK_FILE and MINTKEY_BACKUP_RETENTION_DAYS).
#   3. Add a crontab line, e.g.:
#        0 3 * * * MINTKEY_REPO_DIR=/path/to/mintkey \
#                  MINTKEY_BOOTSTRAP_KEK_FILE=/secure/path/to/kek \
#                  bash /path/to/mintkey/scripts/dev-backup-cron.example.sh
#
# ENVIRONMENT VARIABLES
#   MINTKEY_REPO_DIR            (required) Absolute path to the Mintkey repo root.
#                               The script verifies this is a git repository before
#                               doing anything else.
#   MINTKEY_BOOTSTRAP_KEK_FILE  (optional) Path to a file containing the Fernet
#                               KEK value (single line, no trailing newline required).
#                               When set, sources MINTKEY_BOOTSTRAP_KEK from that
#                               file and passes --with-secrets to dev-backup.sh.
#                               When unset, backup runs without --with-secrets.
#   MINTKEY_BACKUP_RETENTION_DAYS (optional, default 14) Backup directories in
#                               .mintkey-backups/ older than this many days are
#                               pruned on a successful backup run.
#
# FAIL-CLOSED DESIGN
#   - Missing MINTKEY_REPO_DIR → exit 1
#   - MINTKEY_REPO_DIR is not a git repo → exit 1
#   - dev-backup.sh not found → exit 1
#   - dev-backup.sh exits non-zero → propagate that exit code; no pruning
#
# LOGS
#   stdout + stderr are appended to <MINTKEY_REPO_DIR>/.mintkey-backups/cron.log
#   That directory is gitignored (ensured by dev-backup.sh preflight).
#
# EvidenceRef: EV-GAP-005 (closed by this file + HOWTO section)
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Colour helpers (matches dev-backup.sh style) ─────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'
CYAN='\033[0;36m'; BOLD='\033[1m'; RESET='\033[0m'

info()    { echo -e "${CYAN}▸${RESET} $*"; }
ok()      { echo -e "${GREEN}  ✅ $*${RESET}"; }
err()     { echo -e "${RED}  ❌ $*${RESET}" >&2; }
heading() { echo -e "\n${BOLD}$*${RESET}"; }

# ── Timestamp for log lines ───────────────────────────────────────────────────
TIMESTAMP="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
echo ""
heading "[${TIMESTAMP}] dev-backup-cron.example.sh starting"

# ── Preflight 1: MINTKEY_REPO_DIR must be set ─────────────────────────────────
if [[ -z "${MINTKEY_REPO_DIR:-}" ]]; then
  err "MINTKEY_REPO_DIR is not set."
  err "Set it to the absolute path of your Mintkey repo root."
  err "Example: MINTKEY_REPO_DIR=/home/user/mintkey bash scripts/dev-backup-cron.example.sh"
  exit 1
fi

# ── Preflight 2: MINTKEY_REPO_DIR must be a git repository ───────────────────
if ! git -C "${MINTKEY_REPO_DIR}" rev-parse --show-toplevel &>/dev/null; then
  err "MINTKEY_REPO_DIR does not point to a git repository: ${MINTKEY_REPO_DIR}"
  err "Verify the path is correct and the directory exists."
  exit 1
fi
info "Repo root verified: ${MINTKEY_REPO_DIR}"

# ── Preflight 3: dev-backup.sh must exist and be executable ──────────────────
BACKUP_SCRIPT="${MINTKEY_REPO_DIR}/scripts/dev-backup.sh"
if [[ ! -f "${BACKUP_SCRIPT}" ]]; then
  err "dev-backup.sh not found: ${BACKUP_SCRIPT}"
  err "Ensure scripts/dev-backup.sh exists in the repo (merged via PR #72)."
  exit 1
fi
info "dev-backup.sh found: ${BACKUP_SCRIPT}"

# ── Ensure log directory exists ───────────────────────────────────────────────
# .mintkey-backups/ is gitignored (dev-backup.sh's preflight verifies this
# before writing any files, so the log directory itself is safe to pre-create).
LOG_DIR="${MINTKEY_REPO_DIR}/.mintkey-backups"
mkdir -p "${LOG_DIR}" 2>/dev/null || {
  err "Cannot create log directory: ${LOG_DIR}"
  exit 1
}
LOG_FILE="${LOG_DIR}/cron.log"

# ── Redirect all subsequent output to cron.log ───────────────────────────────
# Both stdout and stderr from this point on (including the backup run) go to the
# log file.  A copy also goes to the original stderr for any cron mail / systemd
# journal capture.
exec >> >(tee -a "${LOG_FILE}") 2>&1

# ── Secrets: load KEK from file if provided ───────────────────────────────────
WITH_SECRETS_FLAG=""
if [[ -n "${MINTKEY_BOOTSTRAP_KEK_FILE:-}" ]]; then
  if [[ ! -f "${MINTKEY_BOOTSTRAP_KEK_FILE}" ]]; then
    err "MINTKEY_BOOTSTRAP_KEK_FILE is set but the file does not exist: ${MINTKEY_BOOTSTRAP_KEK_FILE}"
    exit 1
  fi
  # Read KEK value; strip trailing newline; never print it.
  MINTKEY_BOOTSTRAP_KEK="$(tr -d '\n' < "${MINTKEY_BOOTSTRAP_KEK_FILE}")"
  if [[ -z "${MINTKEY_BOOTSTRAP_KEK}" ]]; then
    err "MINTKEY_BOOTSTRAP_KEK_FILE is empty: ${MINTKEY_BOOTSTRAP_KEK_FILE}"
    exit 1
  fi
  export MINTKEY_BOOTSTRAP_KEK
  WITH_SECRETS_FLAG="--with-secrets"
  info "KEK loaded from MINTKEY_BOOTSTRAP_KEK_FILE (value not echoed)."
else
  info "MINTKEY_BOOTSTRAP_KEK_FILE not set — running without --with-secrets."
fi

# ── Retention policy ──────────────────────────────────────────────────────────
RETENTION_DAYS="${MINTKEY_BACKUP_RETENTION_DAYS:-14}"
# Validate it's a positive integer.
if ! [[ "${RETENTION_DAYS}" =~ ^[0-9]+$ ]] || [[ "${RETENTION_DAYS}" -lt 1 ]]; then
  err "MINTKEY_BACKUP_RETENTION_DAYS must be a positive integer; got: ${RETENTION_DAYS}"
  exit 1
fi
info "Retention policy: prune backups older than ${RETENTION_DAYS} days."

# ── Run dev-backup.sh ─────────────────────────────────────────────────────────
heading "Running dev-backup.sh"
info "Command: bash ${BACKUP_SCRIPT} --write ${WITH_SECRETS_FLAG}"

# cd to repo root so dev-backup.sh resolves relative paths correctly.
cd "${MINTKEY_REPO_DIR}"

# Run the backup; capture its exit code explicitly (set -e does not apply across
# the subshell boundary here because we use || to capture the code).
BACKUP_EXIT=0
bash "${BACKUP_SCRIPT}" --write ${WITH_SECRETS_FLAG} || BACKUP_EXIT=$?

if [[ "${BACKUP_EXIT}" -ne 0 ]]; then
  err "dev-backup.sh exited with code ${BACKUP_EXIT} — skipping retention pruning."
  exit "${BACKUP_EXIT}"
fi

ok "dev-backup.sh completed successfully (exit 0)."

# ── Prune old backups ─────────────────────────────────────────────────────────
heading "Pruning backups older than ${RETENTION_DAYS} days"

# Each backup is a directory directly under .mintkey-backups/.
# We prune directories (not the log file or any loose files) older than
# RETENTION_DAYS days using mtime.
PRUNED=0
while IFS= read -r -d '' old_dir; do
  if [[ -d "${old_dir}" ]]; then
    info "  Removing old backup: ${old_dir}"
    rm -rf "${old_dir}"
    PRUNED=$((PRUNED + 1))
  fi
done < <(find "${LOG_DIR}" -mindepth 1 -maxdepth 1 -type d \
           -mtime "+${RETENTION_DAYS}" -print0 2>/dev/null)

if [[ "${PRUNED}" -gt 0 ]]; then
  ok "Pruned ${PRUNED} backup director$([ "${PRUNED}" -eq 1 ] && echo y || echo ies) older than ${RETENTION_DAYS} days."
else
  info "No backups to prune (none older than ${RETENTION_DAYS} days)."
fi

heading "dev-backup-cron.example.sh finished at $(date -u '+%Y-%m-%dT%H:%M:%SZ') — exit 0"
exit 0
