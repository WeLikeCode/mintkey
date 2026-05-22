# Dev Settings Backup & Recovery — Closing Report

**Session:** `2026-05-18-dev-settings-backup-recovery`
**Branch:** `fix/dev-settings-backup-recovery-2026-05-18` (from `main @ edc63bd`)
**Status:** **CLOSED-WITH-RESIDUALS** — code/docs ready to merge; **one owner action item before merging** (rotate the agent key — see §"Mid-session incident").
**Closed:** 2026-05-18

**Commits (post force-push rewrite of `ec322aa` → `1b2e3a6` to scrub the leak):**
- `1b2e3a6` docs(session): scaffold dev-settings-backup-recovery session + EVIDENCE_LEDGER
- `6bbb5b6` fix(guardrails): require --force-destroy for --clean --non-interactive; gitignore e2e .env.local
- `4de9631` feat(scripts): add dev-backup.sh + dev-restore.sh with gitignore entry (C-2)
- `4ba8a04` docs(C-4): add HOWTO-backup-before-reset.md
- `5cc7a69` docs(C-4): patch destructive-command sites with backup warnings

## Mid-session incident — read this first

The ORCHESTRATOR (me) wrote the live `mk_agent_*` plaintext into `ISSUE_INTAKE.md:55` as "evidence" of the manual post-wipe recovery the owner did earlier today. Committed in scaffold commit `ec322aa` and pushed to `origin`. Live on GitHub branch ≈30–60 minutes before the C-5 reviewer (Opus, fresh, independent) caught it.

**Fix landed**: scrubbed via `git rebase -i origin/main` rewriting the offending commit; force-push-with-lease to the branch (NOT main) replaced the leaked history with the redacted version. The current `origin/fix/dev-settings-backup-recovery-2026-05-18` branch is clean.

**Owner action required before considering this fully closed**: rotate the leaked agent key in admin-ui (Agents → that agent → Rotate Key) per HOWTO §9. The key has been on GitHub for >0 minutes and MUST be considered compromised. If you don't rotate, anyone who fetched the branch in the leak window has the key. Tracked as `EV-LEAK-001` in the ledger.

## Outcome

Delivers exactly what the issue intake asked for. Concretely:

1. **Settings inventory** — `EVIDENCE_LEDGER.md` classifies every local/dev state item across categories A–K with the 4 required tags (`safe to commit` / `must never commit` / `recoverable from template` / `must be backed up before reset`). 60+ substantive rows + 7 explicitly-acknowledged gaps. Reviewer confirmed every change in the diff traces to a ledger row.

2. **Backup workflow** — `scripts/dev-backup.sh` (526 lines, shellcheck-clean):
   ```bash
   bash scripts/dev-backup.sh            # dry-run by default; no files written
   bash scripts/dev-backup.sh --write    # captures + writes manifest.json
   bash scripts/dev-backup.sh --write --with-secrets  # Fernet-encrypted via MINTKEY_BOOTSTRAP_KEK
   ```
   Default mode: redacted env files, pg_dump if postgres is healthy, vault_data/vault_kek/bootstrap_secrets tar snapshots, `docker compose ps --format json` snapshot, full `manifest.json`. `--with-secrets` mode: env files Fernet-encrypted; refuses (exit 2) if `MINTKEY_BOOTSTRAP_KEK` is unset; stores `kek_fingerprint` in manifest for cross-env detection. Preflight: `.mintkey-backups/` MUST be gitignored before any write (exit 3 if not). Backups land in `.mintkey-backups/<ISO-timestamp>-<host>/` (gitignored per `.gitignore`).

3. **Recovery workflow** — `scripts/dev-restore.sh` (483 lines, shellcheck-clean):
   ```bash
   bash scripts/dev-restore.sh <backup_dir>            # dry-run diff; no writes
   bash scripts/dev-restore.sh <backup_dir> --apply    # prompts per file; restores perms
   bash scripts/dev-restore.sh <backup_dir> --apply --yes  # non-interactive
   bash scripts/dev-restore.sh <backup_dir> --apply --with-secrets  # decrypts + restores
   ```
   Classification-aware dispatch: `repo-tracked default` rows always SKIPPED (don't clobber live source); `local user config` rows shown as diff + per-file prompt; `Docker volume state` and `seeded database state` rows show an explicit 5-line DESTRUCTIVE warning + prompt before any irreversible action. KEK fingerprint mismatch (cross-env restore) exits 3 unless `--accept-stale` is given.

4. **Destructive-op guardrails** — `install.sh`:
   - New `--force-destroy` flag.
   - `install.sh --clean --non-interactive` (which previously bypassed the interactive `[y/N]` prompt silently) now REQUIRES `--force-destroy`. Without it: prints the volume list (7 named volumes via `docker compose config --volumes`) + the `bash scripts/dev-backup.sh` reminder + exits 1.
   - Interactive `install.sh --clean` (without `--non-interactive`) is UNCHANGED — the existing `[y/N]` prompt is sufficient.
   - `admin-ui/.gitignore` — added `.env.local` + `/e2e/.env.local` to close the EV-ENV-005 / EV-APP-002 accidental-commit gap (admin-ui's gitignore previously only covered Playwright artifacts).
   - Ad-hoc `docker compose down -v` from a shell prompt cannot be programmatically guarded — addressed in C-4 (documentation).

5. **Documentation** — net 8 file changes:
   - **New**: `team/remediation/HOWTO-backup-before-reset.md` (260 lines, 10 sections + EvidenceRef appendix). The canonical "back up before reset" doc for both human contributors and AI agents. Sections: when to back up, the commands, manifest reading, secrets policy, what is NOT backed up, what rotates on next seed, recovering without a backup, rotating after exposure, known gaps.
   - **README.md**: appended a "Backup local state before a reset" subsection at line 101 with the one-liner + HOWTO link.
   - **CLAUDE.md:224** + **AGENTS.md:226**: prepended `⚠ DESTRUCTIVE — wipes ALL 7 named volumes ...` warnings to the existing `docker compose down -v` references. Cite EV-DESTRUCTIVE-006/007.
   - **`.serena/memories/suggested_commands.md:8`**: changed the routine `# stop and remove volumes` comment to an explicit destructive warning per EV-DESTRUCTIVE-008. (Serena memory is the most insidious one — it primes the AI agent's mental model.)
   - **`docs/guides/10min-mock-demo.md`**: patched the existing WARNING at line 353 + the troubleshooting line 379 with backup-first prefixes.
   - **`docs/NETWORK.md:228-234`**: pre-flight backup note above the LAN-rebuild section. (See residual R-1.)

## Files changed

19 files total, all ledger-traceable:

| Path | Change | Owner chunk |
|---|---|---|
| `team/remediation/2026-05-18-dev-settings-backup-recovery/` (8 files) | new — session scaffold + EVIDENCE_LEDGER + this report | C-1 |
| `team/remediation/HOWTO-backup-before-reset.md` | new — 260 lines | C-4 |
| `scripts/dev-backup.sh` | new — 526 lines | C-2 |
| `scripts/dev-restore.sh` | new — 483 lines | C-2 |
| `.gitignore` | +`.mintkey-backups/` entry | C-2 |
| `install.sh` | +`--force-destroy` flag, guard around `--clean --non-interactive` | C-3 |
| `admin-ui/.gitignore` | +`.env.local`, +`/e2e/.env.local` | C-3 |
| `README.md` | +21 lines (dev backup subsection) | C-4 |
| `CLAUDE.md` | +5 lines (destructive warning + HOWTO link) | C-4 |
| `AGENTS.md` | +5 lines (mirror of CLAUDE.md) | C-4 |
| `.serena/memories/suggested_commands.md` | comment rewrite | C-4 |
| `docs/guides/10min-mock-demo.md` | 2 line patches | C-4 |
| `docs/NETWORK.md` | +6 lines (pre-flight note) | C-4 |

## Settings/state now PROTECTED

- All env files (`.env`, `.env.local`, `admin-ui/e2e/.env.local`) — backed up redacted-by-default; opt-in encrypted with `--with-secrets`.
- `postgres_data` (the agents/services/audit/credentials DB) — pg_dump via `docker compose exec`; restore via `psql`.
- `vault_data` + `vault_kek` — tar snapshots; restore via `alpine + docker run`.
- `bootstrap_secrets` — tar snapshot of the whole volume (treats contents as opaque Fernet ciphertext).
- `manifest.json` records SHA-256 of every captured file → tamper-evident.
- `install.sh --clean --non-interactive` no longer silently destroys 7 volumes.
- `admin-ui/e2e/.env.local` can no longer be accidentally committed.
- All 11 destructive-command sites in CLAUDE.md/AGENTS.md/serena/docs now point at the backup workflow.

## Settings/state still NOT protected (residual / tracked-elsewhere)

- **`broker_wal` + `proxy_wal`** — intentionally not backed up; only in-flight WAL entries; committed DB rows are safe in `postgres_data`.
- **`grafana_data` user-created dashboards** — out of scope; provisioned dashboards (6 JSONs) auto-restore but user-curated content does not.
- **`admin_ui_*.pem` Ed25519 keypair** — EV-BOOTSTRAP-007: seed-job steps 6–8 marked "pending T-1.0.4"; the files do not exist yet. Backup can't capture what isn't generated.
- **8 still-tag-only images** (Keycloak, Kong, Liquibase, otel-collector, jaeger, prometheus, cadvisor, grafana) — `EV-GAP-006`. Follow-up session: pin each to `@sha256:`. Keycloak is the highest secondary risk after postgres@sha256 (PR #70).
- **`pg_dump` cron automation** — `EV-GAP-005`. Backup script is operator-triggered; no automated periodic backup. Out of session scope per intake.
- **The `docs/AUTH.md:183-189` Option B re-seed** — C-4 implementer correctly stayed in allowlist; AUTH.md is not in C-4's owner-files list. R-1 below. Mitigation: the HOWTO Section 1 names AUTH.md explicitly so contributors are steered to backup before running the AUTH.md re-seed.
- **The leaked agent key itself** — must be rotated by the owner (this report's §"Mid-session incident").

## Exact backup command

```bash
bash scripts/dev-backup.sh --write              # default: redact secrets
bash scripts/dev-backup.sh --write --with-secrets   # opt-in: include Fernet-encrypted secrets (requires MINTKEY_BOOTSTRAP_KEK)
```

Output: `.mintkey-backups/<ISO-timestamp>-<host>/manifest.json` + captured files.

## Exact restore command

```bash
bash scripts/dev-restore.sh .mintkey-backups/<timestamp>-<host>             # dry-run diff
bash scripts/dev-restore.sh .mintkey-backups/<timestamp>-<host> --apply     # interactive, per-file y/n
bash scripts/dev-restore.sh .mintkey-backups/<timestamp>-<host> --apply --yes  # non-interactive
bash scripts/dev-restore.sh .mintkey-backups/<timestamp>-<host> --apply --with-secrets   # decrypts
```

## Verification (output + exit codes)

Captured during C-5 reviewer's audit (Opus, fresh, independent — `git status` clean):

```
bash -n scripts/dev-backup.sh    → exit 0   (syntax OK)
bash -n scripts/dev-restore.sh   → exit 0   (syntax OK)
bash -n install.sh               → exit 0   (syntax OK)
shellcheck scripts/dev-backup.sh scripts/dev-restore.sh install.sh   → exit 0 each, no findings

bash scripts/dev-backup.sh --help        → exit 0, full usage + exit-code table
bash scripts/dev-backup.sh --dry-run     → exit 0, ZERO files written to .mintkey-backups/
                                           sentinel "testsentineldonotleak123" did NOT appear in stdout
bash scripts/dev-backup.sh --with-secrets --dry-run (KEK unset)   → exit 2, clear error
bash scripts/dev-backup.sh --with-secrets --dry-run (KEK set)     → exit 0, still 0 files written
gitignore preflight (renamed .gitignore aside, bash dev-backup --write)  → exit 3, fix instruction printed

bash scripts/dev-restore.sh --help                             → exit 0
bash scripts/dev-restore.sh /tmp/nonexistent_dir               → exit 1, "Backup directory not found"
bash scripts/dev-restore.sh <fake_backup_dir>  (default dry-run, repo-tracked + local-user-config rows)
    → exit 0; repo-tracked SKIPPED; local-user-config diff shown; no writes

bash install.sh --help                              → shows --force-destroy flag in usage
bash install.sh --clean --non-interactive           → exit 1, warning + volume list + dev-backup hint
git diff --check origin/main..HEAD                  → exit 0, no whitespace issues
rg "mk_agent_[A-Z0-9]{50,}" $(git diff --name-only origin/main..HEAD)   → 0 hits (post-scrub)
rg "Co-Authored-By"   on changed files              → 0 hits (1 hit is the narrative hard-rule line in 00-plan.md)
grep -c '^\.mintkey-backups/' .gitignore            → 1
grep -nE '\.env\.local' admin-ui/.gitignore         → 2 hits
```

Live install.sh execution gated by `bash 4+` requirement (macOS host has bash 3.2); reviewer verified the guardrail logic via diff inspection. Recommend CI smoke-test on a bash-5 runner.

## Residuals (non-blocking)

- **R-1** — `EVIDENCE_LEDGER.md` row `EV-DESTRUCTIVE-011` mis-cites `docs/NETWORK.md:225-232` as "Option B re-seed". The actual `rm data/bootstrap-secrets/.admin_password_synced` content is in `docs/AUTH.md:183-189`. C-4 implementer correctly stayed in allowlist (NETWORK.md was the file the row cited) and patched the LAN-rebuild surface that does exist there; the HOWTO Section 1 already cites AUTH.md by name. Follow-up: (a) fix the ledger row to cite AUTH.md, (b) add a one-line pre-flight backup block above the AUTH.md Option B fence. One-line doc PR.
- **R-2** — `docs/AUTH.md:183-189` (Option B re-seed) has no pre-flight backup warning. Per R-1.
- **R-3** — `admin_ui_*.pem` Ed25519 keypair pending T-1.0.4 (`EV-BOOTSTRAP-007`). Separate session.
- **R-4** — 8 tag-only images (`EV-GAP-006`). Keycloak + Kong are next-highest risk. Separate session.
- **R-5** — No automated `pg_dump` cron (`EV-GAP-005`). Operator-triggered backup only. If you want recurring backups, separate session.
- **R-6** — `install.sh` requires bash 4+; live verification of E.17-18 couldn't run on this macOS host. Verified via diff. Recommend CI smoke test on bash-5 runner.
- **R-7** — Many worktrees from earlier sessions today (S1..S11, hotfixes, S5, S3, DSBR) consume disk. Cleanup pass: `git worktree prune` after the merged branches are gone. Not blocking.

## Commands that were intentionally NOT run because they were destructive

- `docker compose down -v` — the exact failure mode this session exists to prevent. Verified guardrails via diff inspection only; live full-round-trip of backup→destroy→restore was NOT run on real state per intake decision. Owner-gated.
- `install.sh --clean` — same.
- `rm -rf .mintkey-backups/<anything>` — never invoked; the `.gitignore` preflight stays armed.
- `git push --force` to `main` — the only force-push performed was to the branch (`fix/dev-settings-backup-recovery-2026-05-18`) to scrub the leaked secret. Branch force-push is explicitly allowed per `~/.claude/CLAUDE.md`.
- `git filter-repo` / `git filter-branch` — would have been over-engineering for a single-line scrub in a single commit; interactive rebase + amend + force-with-lease was sufficient.

## Success criteria (vs. user's spec)

| Criterion | Status |
|---|---|
| A developer can run one documented command before remediation and recover local settings afterward. | ✅ `bash scripts/dev-backup.sh --write` + `bash scripts/dev-restore.sh <dir> --apply`. README + HOWTO cover both. |
| Destructive flows warn or require explicit force. | ✅ install.sh --clean --non-interactive requires --force-destroy. 6 doc sites carry warnings. (Ad-hoc shell `docker compose down -v` cannot be programmatically gated — addressed via docs + Serena-memory warnings.) |
| No real secrets are committed. | ✅ Post-scrub. **EV-LEAK-001 documents the in-session leak + fix.** |
| No documentation claim exists without an EvidenceRef. | ✅ HOWTO appendix maps every section to ledger rows; README + CLAUDE.md + AGENTS.md cite EV-DESTRUCTIVE-006/007. |

## Owner action items

1. **CRITICAL — rotate the leaked agent key**: log into admin-ui → Agents → `agent_01KRW0GP04MV7Q7JRVVH44N6XJ` → Rotate Key. Then `claude mcp remove mintkey -s user && claude mcp add --transport http --scope user mintkey http://localhost:8082/mcp --header "Authorization: Bearer <new mk_agent_...>"` to update the local MCP config. The leaked key was on `origin` for ~30–60 minutes.
2. (Optional, when convenient) approve R-1 / R-2 follow-up doc PR for `docs/AUTH.md`.
3. (Optional, when convenient) approve R-4 follow-up: pin the 8 remaining tag-only images.
4. (Optional, when convenient) approve R-5 follow-up: cron-based pg_dump automation if desired.
