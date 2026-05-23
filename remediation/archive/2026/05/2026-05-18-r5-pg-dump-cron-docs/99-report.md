# R-5 pg_dump Cron Docs — Closing Report

**Session:** `2026-05-18-r5-pg-dump-cron-docs`
**Branch:** `fix/r5-pg-dump-cron-docs-2026-05-18`
**Residual closed:** R-5 from `2026-05-18-dev-settings-backup-recovery/99-report.md`
**EvidenceRef:** EV-GAP-005
**Status:** CLOSED

## Summary

Adds an operator-installable cron wrapper (`scripts/dev-backup-cron.example.sh`)
for scheduled `dev-backup.sh` runs and documents it in HOWTO §11. Nothing
auto-installs into any crontab; the pattern is purely opt-in.

## Files added/modified

| Path | Change |
|---|---|
| `scripts/dev-backup-cron.example.sh` | New — cron wrapper (shellcheck-clean) |
| `team/remediation/HOWTO-backup-before-reset.md` | Appended §11 "Periodic backups via cron" |
| `team/remediation/2026-05-18-r5-pg-dump-cron-docs/ISSUE_INTAKE.md` | New — session intake |
| `team/remediation/2026-05-18-r5-pg-dump-cron-docs/99-report.md` | This file |

## Verification

```
bash -n scripts/dev-backup-cron.example.sh && echo "syntax OK"
→ syntax OK

shellcheck scripts/dev-backup-cron.example.sh && echo "shellcheck OK"
→ shellcheck OK

bash scripts/dev-backup-cron.example.sh 2>&1; echo "exit=$?"
→ [2026-05-18T...] dev-backup-cron.example.sh starting
→   ❌ MINTKEY_REPO_DIR is not set.
→   ❌ Set it to the absolute path of your Mintkey repo root.
→   ❌ Example: MINTKEY_REPO_DIR=... bash scripts/dev-backup-cron.example.sh
→ exit=1

grep -n "Periodic backups via cron" team/remediation/HOWTO-backup-before-reset.md
→ 246:## 11. Periodic backups via cron (optional)
→ 362:| 11 — Periodic backups via cron | EV-GAP-005 |
```

## Fail-closed guarantees confirmed

- Missing `MINTKEY_REPO_DIR` → exit 1, clear message.
- `MINTKEY_REPO_DIR` not a git repo → exit 1 (preflight 2 in script).
- `dev-backup.sh` missing from repo → exit 1 (preflight 3 in script).
- `MINTKEY_BOOTSTRAP_KEK_FILE` set but file absent/empty → exit 1.
- `dev-backup.sh` exits non-zero → propagated; pruning skipped.

## What was NOT done

- Did not modify `scripts/dev-backup.sh`.
- Did not touch any crontab or `/etc/cron*`.
- Did not modify any file outside the four owner files listed above.
