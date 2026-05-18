# Chunk Catalog — Dev Settings Backup & Recovery

**Session:** `2026-05-18-dev-settings-backup-recovery`
**Driver:** orchestrator pattern (ORCHESTRATOR Opus → IMPLEMENTERs Sonnet → REVIEWER Opus)

## Locked decisions (from owner intake)

| Decision | Value |
|---|---|
| Script style | Standalone shell scripts under `scripts/` matching `scripts/e2e-setup-env.sh` |
| Backup root | `.mintkey-backups/<timestamp>/` at repo root |
| Backup root gitignore | Required before any write; script self-checks |
| Default secret handling | REDACT in default backup; `--with-secrets` opt-in |
| Secrets-at-rest in backup | Encrypted with existing `MINTKEY_BOOTSTRAP_KEK` if `--with-secrets`; refuse if KEK absent |
| Restore default | `--dry-run`; explicit `--apply` (or `--yes` for non-interactive) |
| Destructive existing scripts | `--force` flag with explicit warning otherwise; show what will be destroyed |
| No destructive ops in session | ORCHESTRATOR + every subagent MUST NOT actually wipe state during testing |
| Full round-trip test | Owner-gated; default to dry-run testing only |

## Universal hard rules

- See `00-plan.md`. Strict: no Co-Author trailer, no `--no-verify`, no ADR edits, no product-code edits without escalation, no real secrets in commits, no destructive ops.

## Wave 0 — ORCHESTRATOR scaffold + Evidence

### C-1: Evidence + state inventory (ORCHESTRATOR + Investigator subagent)

- Owner: ORCHESTRATOR (me); Investigator subagent does the read-only audit
- Output: `EVIDENCE_LEDGER.md` populated; this `01-orchestrator-chunks.md`; `00-plan.md`; `ISSUE_INTAKE.md`; `02-matrix.md`; `03-escalations.md`; `04-progress.md` scaffolded
- Reviewer pass condition (per intake):
  - Every category A–K in the intake has at least one EvidenceRef row (or an explicit "none found" entry with the search command that justified the gap).
  - Each EvidenceRef row has all 6 columns filled.
  - Settings classification table is complete for every file/volume identified.
  - Destructive-scripts table covers every match for the search patterns in the intake.

## Wave 1 — Parallel implementer chunks (disjoint file scope)

### C-2: Backup/restore implementation

| Field | Value |
|---|---|
| Owner files | `scripts/dev-backup.sh` (new), `scripts/dev-restore.sh` (new), `.gitignore` (append `.mintkey-backups/` if not present) |
| EvidenceRefs (anchors) | `EV-ENV-*`, `EV-VOL-*`, `EV-SECRETS-*`, `EV-BOOTSTRAP-*` (filled by C-1) |
| Tools | bash (POSIX-portable where reasonable but bashisms OK — the repo's other shell scripts use bash); `pg_dump`-via-`docker compose exec` for postgres data; `tar`/`gzip` for archive |
| Forbidden | Python rewrite; Makefile target; product-code change |

#### `scripts/dev-backup.sh` — required behavior

- `--help` exits 0 with usage
- `--dry-run` (default): print what would be backed up, redact secrets, no writes
- (no flag): create `.mintkey-backups/<ISO-timestamp>/` and back up:
  - `.env` if present (REDACTED — keys-only)
  - `admin-ui/e2e/.env.local` if present (REDACTED)
  - `data/bootstrap-secrets/admin_password` if present (REDACTED — just a marker that it exists)
  - `pg_dump` of mintkey database (compressed) IF postgres container is running (else warn)
  - `vault_data` volume snapshot (tar) IF vault-adapter is running
  - List of all running services + their image digests
  - `manifest.json` enumerating each captured file with size, sha256, and `redacted: true|false`
- `--with-secrets` flag:
  - Include `.env` values (encrypted with `MINTKEY_BOOTSTRAP_KEK` via Fernet)
  - Include `data/bootstrap-secrets/admin_password` ciphertext as-is (already Fernet)
  - Refuse to write if `MINTKEY_BOOTSTRAP_KEK` env is unset
  - Add `secrets: true` to manifest
- Self-check before any write: `.mintkey-backups/` MUST appear in `.gitignore` AND the file MUST exist; else refuse and print a one-line fix.
- Stderr summary at end: count of files backed up + total size + path.
- Exit codes: 0 success; 1 missing prerequisites (e.g., docker not running); 2 KEK missing for --with-secrets; 3 gitignore preflight failed.

#### `scripts/dev-restore.sh` — required behavior

- `--help` exits 0 with usage
- Takes a backup directory path as positional arg
- `--dry-run` (default): diff each file in backup vs. current; show what would change; no writes
- `--apply` (or `--yes` for non-interactive): actually restore
  - For each file: if current exists and differs, prompt y/n (or skip prompt with `--yes`)
  - Restore file permissions per manifest
  - For pg_dump: prompt before `psql -c "DROP TABLE …"` or pg_restore
- Refuse to restore if backup `secrets: true` AND current env's `MINTKEY_BOOTSTRAP_KEK` differs from backup's KEK fingerprint (warns "stale secrets — different env?").
- Exit codes: 0 success; 1 backup not found; 2 user declined; 3 KEK mismatch.

### C-3: Destructive-operation guardrails

| Field | Value |
|---|---|
| Owner files | Any script identified by C-1 as performing destructive ops without confirmation (NO PRE-EMPTIVE EDITS — the C-1 catalog drives the file list) |
| EvidenceRefs (anchors) | `EV-DESTRUCTIVE-*` (filled by C-1) |
| Forbidden | Don't add `--force` to scripts that already have good guards. Don't break existing workflows that pipe these scripts. |

#### Pattern for each destructive script

Add at the top of the script (after `#!/bin/bash` + `set` lines):

```bash
# Destructive operation guard — added 2026-05-18 per session
# 2026-05-18-dev-settings-backup-recovery (EvidenceRef EV-DESTRUCTIVE-NN).
FORCE=""
for arg in "$@"; do case "$arg" in --force) FORCE=1 ;; esac; done

if [[ -z "$FORCE" ]]; then
  cat <<'EOF' >&2
⚠  This script will destroy:
   - <list what's destroyed; populated per-script>

   Back up first: bash scripts/dev-backup.sh
   Run again with --force when you've confirmed.
EOF
  exit 1
fi
```

Per-script list comes from C-1 evidence rows.

If a script's interactive mode already guards, just add `--force` as a way to skip the prompt (preserving existing UX).

### C-4: Documentation

| Field | Value |
|---|---|
| Owner files | `README.md` (dev setup / reset section), new `team/remediation/HOWTO-backup-before-reset.md`, possibly `docs/` (per C-1 findings) |
| EvidenceRefs (anchors) | `EV-DOC-*` (filled by C-1) |
| Forbidden | Don't update accepted ADRs |

#### Required content

- **README dev section** — append a "Backup local state before a reset" subsection:
  - What's preserved by `docker compose down` (without `-v`) vs lost
  - What's lost by `docker compose down -v` (cite the volume names)
  - The one-line `bash scripts/dev-backup.sh` command
  - Pointer to the HOWTO

- **New `team/remediation/HOWTO-backup-before-reset.md`** — read-once doc for contributors + agents:
  - When to back up (before any remediation that touches docker / volumes / .env)
  - The backup command, output explanation
  - The restore command, dry-run-first emphasis
  - Secrets policy (redact-by-default, --with-secrets opt-in, encryption-at-rest)
  - What is NOT backed up (e.g., other contributors' state; remote prod; kong's declarative config — auto-regenerated)
  - How to recover after a wipe if you have NO backup (manual re-create via admin-ui — link to the workflow)
  - How to rotate secrets after accidental exposure

- **Update any C-1-flagged destructive doc**: if a doc says "run `docker compose down -v`" without warning, prepend a one-line "BACKUP FIRST: see HOWTO" pointer.

## Wave 2 — REVIEWER (Opus, fresh)

### C-5: review the full session

| Field | Value |
|---|---|
| Reviewer | fresh Opus subagent (no prior context) |
| What to verify | (a) no real secrets committed; (b) every diff line maps to an EvidenceRef; (c) `dev-backup.sh` and `dev-restore.sh` dry-runs work AND don't leak secrets in output; (d) destructive-script guardrails fire as expected without --force; (e) backup directory gitignored before any sample write; (f) docs match implementation (no doc claim without an EvidenceRef); (g) `bash -n` and `shellcheck` (if available) pass on new scripts |

PASS_ALL gate before commit-and-PR. 3-strike cap per chunk; escalate via `03-escalations.md`.

## Wave 3 — Push + PR via Mintkey proxy + admin-merge

- Commit each chunk atomically.
- Push branch.
- Open PR via `svc_01KRW0G089YCDPAAQ6G146B3GB`.
- Admin-merge after CI green.

## Status legend (`02-matrix.md`)

| Symbol | Meaning |
|---|---|
| ⬜ | Pending |
| 🔵 | Dispatched (in-flight) |
| ✅ | PASS |
| ❌ | FAIL — re-dispatched |
| 🛑 | Hard-stop |
| ⚠️ | Escalated |
