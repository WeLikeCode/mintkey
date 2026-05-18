# Issue Intake — 2026-05-18-dev-settings-backup-recovery

**Session:** `team/remediation/2026-05-18-dev-settings-backup-recovery/`
**Branch:** `fix/dev-settings-backup-recovery-2026-05-18` (from `main @ edc63bd`)
**Reported:** 2026-05-18
**Reporter:** Owner — "local/dev/remediation settings keep getting destroyed, overwritten, or reset during development and remediation sessions"

## Problem statement (required)

Local developer and remediation state is regularly destroyed by routine workflows. The acute trigger was the 2026-05-18 dev-data wipe during S2's `docker compose up -d --wait` verification: `postgres:16` was tag-only, the Docker Hub digest had drifted, Compose recreated the container, the `postgres_data` volume came back empty after seed-job's first-run path executed against a fresh database. Hand-curated agents and services in the local DB were lost; the orchestrator (me) had to ask the owner for a fresh `mk_agent_*` to resume mid-campaign work.

That single incident is one instance of a broader class:

1. **No documented backup mechanism** for developer-curated state (agents, services, permissions, custom dashboards, hand-edited dev configs).
2. **No restore mechanism** if state is lost.
3. **Destructive workflows aren't gated** — `docker compose down -v`, seed-job overwrites, `.env` regeneration scripts (if any) can run without explicit confirmation.
4. **Remediation docs** may instruct contributors to run reset commands without warning about what they destroy.
5. **No clear classification** of which files are repo-tracked defaults vs. user-owned overrides vs. generated secrets — so a contributor has no way to know what's safe to commit, what's safe to back up, what's safe to wipe.

PR #70 (postgres pin) closes the specific digest-drift class. This session addresses the broader pattern.

## User-visible symptom (required)

- A contributor runs `docker compose down -v` (or some equivalent) to "reset their local stack" and loses every agent, service, permission grant, and custom dashboard they had curated.
- An agent (Claude / Codex / Kiro) runs a verification step that recreates containers and unintentionally wipes user state, then has to re-bootstrap from scratch (loses time, surfaces credentials, breaks in-flight work).
- A new contributor reading the README has no obvious "before you reset, back up your local state" step.
- The 2026-05-18 wipe required the user to manually re-create an `mk_agent_*` and a `github_ciprianiacobescu` service via admin-ui to unblock the remediation campaign.

## Expected behavior (required)

1. **Settings inventory exists** as a versioned document: every category of local/dev state is classified (`repo-tracked default` / `local user config` / `generated secret` / `Docker volume state` / `seeded database state` / `external tool setting`) and tagged with `safe to commit` / `must never commit` / `recoverable from template` / `must be backed up before reset`.

2. **One documented backup command** that:
   - Writes a timestamped archive (or directory) to a gitignored backup root (e.g., `.mintkey-backups/<timestamp>/`).
   - Excludes secrets by default; only includes them with an explicit `--with-secrets` flag.
   - Produces a manifest listing what was captured.
   - Redacts known secret patterns in any preview/log output.
   - Warns on missing inputs.

3. **One documented restore command** that:
   - Defaults to `--dry-run`; shows the diff before any write.
   - Requires explicit confirmation (or `--apply`) for actual restore.
   - Restores file permissions where relevant.
   - Refuses to restore stale secrets into a fresh environment without explicit warning.

4. **Destructive scripts** (`docker compose down -v` invocations, seed-reset scripts, anything `rm -rf` on volumes/secrets) require a `--force` flag or explicit "type yes" confirmation. Show what will be destroyed first.

5. **Documentation** (README, dev docs, remediation workflow docs) makes the backup-before-reset workflow obvious and lists what is/isn't preserved.

## Evidence (required)

See `EVIDENCE_LEDGER.md` (populated by chunk C-1). Anchor evidence already gathered:

- **EV-WIPE-001**: 2026-05-18 postgres_data wipe — `agents` and `services` tables came back empty after S2's `docker compose up -d --wait`. Verified via `docker compose exec postgres psql ... -c "SELECT COUNT(*) FROM agents;"` returning `0`. Postgres container created-time `2026-05-17T21:38:32Z` matched the wipe timestamp. Root cause: unpinned `postgres:16`. **Closed by PR #70** (compose pin to `@sha256:b6ccf02e`), but the broader class remains open.
- **EV-OPERATOR-RECOVERY**: After the wipe, owner had to manually log into admin-ui via Keycloak OIDC (internal-login is disabled, D2-b gate at `admin-api/src/admin_api/api/auth.py:74`) and create a fresh agent `agent_01KRW0GP04MV7Q7JRVVH44N6XJ` + `mk_agent_<REDACTED-ROTATE-IMMEDIATELY-see-99-report>` + register a github_ciprianiacobescu service. ~10 min of manual work to unblock the campaign.

Comprehensive evidence (every file/script/destructive path) goes in `EVIDENCE_LEDGER.md`.

## Scope (required)

In scope (may be added / modified):

- `scripts/dev-backup.sh` (or equivalent in the repo style) — new
- `scripts/dev-restore.sh` (or equivalent) — new
- Confirmation/guardrail patches to any existing destructive script identified by C-1
- `.gitignore` additions for backup directory + any newly-discovered uncommitted-but-uningored files
- `README.md` — dev setup section
- `docs/architecture/00-vision/06-roadmap.md` — note the backup workflow if relevant
- `team/remediation/README.md` if it exists, or a new `team/remediation/HOWTO-backup-before-reset.md`
- Session folder (the 8 standard files)

Out of scope:

- Production backup/disaster-recovery for cloud deployments (separate concern, separate session).
- The actual fingerprint-migration work for S5 sites 1+2 (tracked separately).
- Refactoring the seed-job or admin-ui's first-run flow.
- Adding a UI for backup/restore (CLI-only is sufficient).
- The Mintkey product's own credential backup (the proxy + vault — that's separate, handled by ADR-0003).

## Out of scope (required)

See above. Also explicitly:

- ADRs (immutable per ADR-0001).
- Source code in `services/`, `admin-api/`, `admin-ui/`, `mcp-server/`, `mintkey-models/`, `mock-backend/` — backup/restore scripts should NOT need to modify product code. If C-1 finds a place where a one-line product-code change would close a critical destructive path, escalate via `03-escalations.md`.
- Other contributors' uncommitted local state (this session can't read/back-up what's not on this machine).

## Risk level (required)

- **Developer productivity**: high positive — closes a recurring lost-work class.
- **Security**: medium positive if done right — explicit secret handling (redact-by-default, opt-in `--with-secrets`) raises the bar for accidental secret commits. Negative risk if scripts are sloppy and write plaintext secrets to disk in a non-gitignored location.
- **Backwards compat**: zero — pure additive scripts + docs + gitignore additions.
- **Stack stability**: low risk — guardrails on existing scripts MUST default to "old behavior preserved + warn"; flipping to "force required" by default is a separate decision per-script.

## Verification target (required)

- `bash scripts/dev-backup.sh --help` exits 0 and prints usage.
- `bash scripts/dev-backup.sh --dry-run` prints what it would back up; no files written; no secrets in output.
- `bash scripts/dev-backup.sh` (default) creates `.mintkey-backups/<timestamp>/manifest.json` with a redacted listing.
- `bash scripts/dev-backup.sh --with-secrets` includes secrets (explicit opt-in) but the backup dir is verified gitignored before write.
- `bash scripts/dev-restore.sh --dry-run` against an existing backup prints the diff; no files written.
- `bash scripts/dev-restore.sh --apply` requires either `--yes` or an interactive confirmation.
- For any destructive existing script touched: invoking without `--force` prints a 5-line warning + the list of what will be destroyed + an exit-1.
- `.mintkey-backups/` appears in `.gitignore`.
- `rg -n "real-looking-secret"` across the diff finds zero hits (using existing secret-pattern scanners).
- Documentation rg: `rg "docker compose down -v"` returns expected list and each occurrence either has a warning or links to the backup workflow.

Verification commands + exit codes will be captured in `99-report.md`.

## Owner decisions (required — to be locked before implementer dispatch)

- ✅ **Approach**: standalone shell scripts (`scripts/dev-backup.sh` + `scripts/dev-restore.sh`) matching the repo's existing `scripts/e2e-setup-env.sh` style. NOT a Makefile target (no Makefile in repo per quick check); NOT a Python module (overkill for one-off ops scripts).
- ✅ **Backup directory**: `.mintkey-backups/` at repo root, gitignored.
- ✅ **Secrets handling**: redact by default; explicit `--with-secrets` flag to opt in. Backups containing secrets are encrypted-at-rest with the existing `MINTKEY_BOOTSTRAP_KEK` (or refuse to write if that env isn't set).
- ✅ **Confirmation pattern**: `--dry-run` by default for restore; `--apply` to actually write. For destructive existing scripts: `--force` flag with explicit warning otherwise.
- ✅ **No destructive ops in this session**: the orchestrator (me) MUST NOT run `docker compose down -v`, `git clean`, `rm -rf` on volumes, etc., during evidence gathering or testing. Subagents must follow the same rule. If a subagent needs to test the destructive path, they simulate it on a temp dir — never on real state.
- ✅ **Stack reset to test backup/restore**: if the only way to verify restore works is to wipe the stack, ASK OWNER FIRST. Default: dry-run testing only; full round-trip is owner-gated.

## Checklist

- [x] Problem statement
- [x] User-visible symptom
- [x] Expected behavior
- [x] Evidence (with anchor refs; full ledger in C-1)
- [x] Scope
- [x] Out of scope
- [x] Risk level
- [x] Verification target
- [x] Owner decisions locked
