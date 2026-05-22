# Issue Intake — 2026-05-18-r5-pg-dump-cron-docs

**Session:** `team/remediation/2026-05-18-r5-pg-dump-cron-docs/`
**Branch:** `fix/r5-pg-dump-cron-docs-2026-05-18` (from `main`)
**Reported:** 2026-05-18
**Residual:** R-5 from `2026-05-18-dev-settings-backup-recovery/99-report.md`

## Problem statement

EV-GAP-005 (HOWTO §10): `dev-backup.sh` is operator-triggered only. There is no
documented, operator-installable pattern for running it on a schedule via cron.
Developers running long-lived local stacks have no safety net between manual backups.

## User-visible symptom

A developer forgets to run `bash scripts/dev-backup.sh --write` before an overnight
session or destructive operation, suffers a wipe (EV-WIPE-001 class), and discovers
their last backup is days old (or doesn't exist).

## Expected behavior

1. A wrapper script (`scripts/dev-backup-cron.example.sh`) is available for operators
   to install as a cron job. It sources the KEK from a file (so the KEK never appears
   in crontab), runs `dev-backup.sh --write [--with-secrets]`, logs output, and prunes
   old backups.
2. `HOWTO-backup-before-reset.md` gains a "Periodic backups via cron" section with the
   crontab line shape, 3-step install, retention policy, and a reference to EV-GAP-005.
3. Nothing auto-installs into the operator's crontab. Opt-in only.

## Scope

Owner files (no other files may be touched):
- `scripts/dev-backup-cron.example.sh` (new)
- `team/remediation/HOWTO-backup-before-reset.md` (append §11)
- `team/remediation/2026-05-18-r5-pg-dump-cron-docs/ISSUE_INTAKE.md` (this file)
- `team/remediation/2026-05-18-r5-pg-dump-cron-docs/99-report.md` (new)

Out of scope: modifying `scripts/dev-backup.sh`, any crontab, `/etc/cron*`,
CI configuration, product source code.

## Risk level

Low. Pure additive: new example script + doc section. The wrapper script is never
auto-executed; it only runs when the operator explicitly installs it.

## Verification target

```bash
bash -n scripts/dev-backup-cron.example.sh && echo "syntax OK"
bash scripts/dev-backup-cron.example.sh 2>&1; echo "exit=$?"
# Expect: non-zero + "MINTKEY_REPO_DIR is not set"
grep -n "Periodic backups via cron" team/remediation/HOWTO-backup-before-reset.md
grep -n "EV-GAP-005" team/remediation/HOWTO-backup-before-reset.md
```

## Owner decisions

- Wrapper is an `.example.sh` (not auto-installed, clearly advisory by name).
- KEK loaded from file via `MINTKEY_BOOTSTRAP_KEK_FILE`; never from the crontab
  line value directly.
- Pruning: `find … -mtime +N -type d` under `.mintkey-backups/`; log file not pruned.
- Exit code of the wrapper propagates from `dev-backup.sh`.
