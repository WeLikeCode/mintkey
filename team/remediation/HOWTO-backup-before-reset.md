# HOWTO — Back Up Local State Before a Reset

> **One rule: run `bash scripts/dev-backup.sh` before any destructive operation.**
>
> This document is for contributors and agentic sessions. If you are an agent about to
> run `docker compose down -v`, a seed reset, or any `.env` regeneration — stop, back
> up first, then proceed.

---

## 1. When to back up

- **Before any `docker compose down -v`** — this is the root cause of the 2026-05-18
  data wipe (EV-WIPE-001): all 7 named volumes are deleted; every hand-curated agent,
  service, permission grant, and audit row is permanently lost without a backup.
- Before any remediation session that touches Docker volumes or `.env` files
  (EV-DESTRUCTIVE-001, EV-DOC-*).
- Before changing `MINTKEY_VAULT_KEK` or `MINTKEY_BOOTSTRAP_KEK` — stale KEK values
  make a previous backup's encrypted fields unreadable (EV-SECRET-001, EV-SECRET-002).
- Before re-pulling images via `docker compose pull` — a tag-drift re-pull can trigger
  container recreation and volume re-initialisation (EV-WIPE-001, EV-COMPOSE-001).
- Before the Option B re-seed in `docs/AUTH.md` (`rm data/bootstrap-secrets/.admin_password_synced`)
  — this rotates all bootstrap secrets (EV-BOOTSTRAP-001..006, EV-DESTRUCTIVE-011).

---

## 2. The one command

```bash
bash scripts/dev-backup.sh
```

(EV-VOL-001..007, EV-DB-001..008, EV-ENV-002..005)

What it does in three lines:
1. Dumps `postgres_data` (agents, services, permissions, audit, credentials) to a
   compressed `.sql.gz` archive, and snapshots `vault_data` + `vault_kek`.
2. Copies `.env` and `admin-ui/e2e/.env.local` with all secret values **redacted
   by default** (keys only; no plaintext values).
3. Writes a `manifest.json` enumerating every captured item with size, sha256, and
   `redacted: true|false`, then prints a summary to stderr.

Default output location: `.mintkey-backups/<ISO-timestamp>/` at repo root
(gitignored per `.gitignore` — the script self-checks before writing).

---

## 3. Reading the output

After a successful backup you'll find a directory like:

```
.mintkey-backups/2026-05-18T14:30:00Z/
  manifest.json
  postgres_dump.sql.gz
  vault_data.tar.gz
  env.redacted.txt
  e2e_env.redacted.txt
  services_snapshot.txt
```

`manifest.json` fields:

| Field | Meaning |
|---|---|
| `timestamp` | ISO-8601 UTC timestamp of the backup run |
| `items[].path` | Path that was captured (relative to backup dir) |
| `items[].size_bytes` | On-disk size after compression |
| `items[].sha256` | SHA-256 of the captured file |
| `items[].redacted` | `true` = secret values replaced with `<REDACTED>` |
| `secrets` | `true` only if `--with-secrets` was used |

`redacted: true` means the file was captured (key names are visible for audit) but
all values matching known secret patterns were replaced before writing to disk.
You can verify what was captured without ever exposing plaintext secrets in logs or
commit diffs.

---

## 4. The restore command

**Always dry-run first:**

```bash
bash scripts/dev-restore.sh .mintkey-backups/<timestamp> --dry-run
```

This prints every file that would change and every database row that would be
restored — no writes. Review the output, then apply:

```bash
bash scripts/dev-restore.sh .mintkey-backups/<timestamp> --apply
```

(EV-VOL-001..007, EV-DB-001..008)

The restore script:
- Diffs each file in the backup against the current file before touching anything.
- Prompts `y/n` per file when run interactively; use `--yes` to skip prompts in
  non-interactive contexts.
- Refuses to restore a backup with `secrets: true` if the current environment's
  `MINTKEY_BOOTSTRAP_KEK` differs from the backup's KEK fingerprint ("stale secrets —
  different env?" error, exit 3).

Exit codes: `0` success; `1` backup not found; `2` user declined; `3` KEK mismatch.

---

## 5. Secrets policy

| Mode | What's included | Requirement |
|---|---|---|
| Default (no flag) | Key names only; values replaced with `<REDACTED>` | None |
| `--with-secrets` | `.env` values + bootstrap secrets ciphertext | `MINTKEY_BOOTSTRAP_KEK` must be set; backup is encrypted at rest using that key |

`--with-secrets` is opt-in by design. The script self-checks that `.mintkey-backups/`
appears in `.gitignore` before writing any secrets-containing archive. If the gitignore
entry is missing, the script exits 3 and prints a one-line fix.

**Cross-environment warning**: a secrets backup created in dev (with the
`MINTKEY_BOOTSTRAP_KEK` fixture from `docker-compose.yml`) cannot be restored in an
environment using a different KEK. The restore script enforces this via KEK fingerprint
comparison (exit 3 on mismatch).

(EV-SECRET-001, EV-SECRET-002, EV-ENV-002..005)

---

## 6. What is NOT backed up

The following items are **outside the scope** of `dev-backup.sh`:

- **Other contributors' local state** — the script only captures what is on _this_
  machine; another developer's hand-curated agents/services cannot be backed up here
  (EV-GAP-001).
- **Remote production state** — this backup is dev-only. Production backup and
  disaster recovery is a separate concern (out of session scope per ISSUE_INTAKE.md).
- **Kong's declarative config** (`services/proxy-plugin/kong.yml`) — this file is
  auto-regenerated by the kong-syncer from the postgres database on every startup;
  it does not need to be independently backed up (EV-OBS-006).
- **`admin_ui_private.pem` / `admin_ui_public.pem`** — the Ed25519 keypair for signed
  admin-ui requests is **not yet generated** by the seed-job (T-1.0.4 pending;
  EV-BOOTSTRAP-007, EV-GAP-002). There is nothing to back up. admin-ui operates in
  unsigned fallback mode until T-1.0.4 is implemented.

---

## 7. What is intentionally rotated on next seed-job run

Restoring a backup does **not** restore all secrets to their pre-wipe state. The
following items are regenerated by the seed-job on first run after a reset, and their
values **will change** even if you restore the backup:

| Item | EvidenceRef | Impact |
|---|---|---|
| Admin password (`admin_password`) | EV-BOOTSTRAP-001 | Log in with the newly-generated password; extract it via `docker run --rm -v mintkey_bootstrap_secrets:/s alpine cat /s/admin_password` |
| OIDC client secret (`oidc_client_secret`) | EV-BOOTSTRAP-002 | seed-job re-fetches from Keycloak; brief mismatch until admin-api restarts |
| Grafana OIDC client secret | EV-BOOTSTRAP-003 | Same — Grafana may show SSO error until the container restarts |
| Jaeger OIDC client secret | EV-BOOTSTRAP-004 | Same |
| oauth2 cookie secret | EV-BOOTSTRAP-005 | All Jaeger browser sessions are invalidated; users must log in again |
| `.admin_password_synced` sentinel | EV-BOOTSTRAP-006 | Re-created by seed-job; controls whether password sync runs |

**Restart strategy after restore**: if you restore `bootstrap_secrets` from an old
backup and then run the seed-job (e.g., `docker compose up -d`), the seed-job may
re-rotate these secrets and overwrite your restored values. To avoid this, either
(a) restore _after_ the seed-job has run and services are healthy, or (b) restore to
an already-running stack without restarting it.

---

## 8. Recovering without a backup

If you have no backup and the stack was wiped, you must manually re-create your state
via the admin-ui. This is the workflow used on 2026-05-18 after EV-WIPE-001:

1. Start the stack: `docker compose up -d`
2. Get the bootstrap admin password:
   ```bash
   docker run --rm -v mintkey_bootstrap_secrets:/s alpine cat /s/admin_password
   ```
3. Log in at `http://localhost:8081` — click **Sign in with Keycloak**, use the
   password above (the Keycloak admin user is `admin`).
4. Create a new Agent via admin-ui: **Agents → New Agent** — copy the resulting
   `mk_agent_*` key; it is shown once.
5. Register any external services via admin-ui: **Services → New Service** — re-enter
   base URLs and credential references.
6. Re-create permission grants: **Agents → (agent) → Permissions → Grant**.

Full operator walkthrough: [`docs/guides/github-quickstart.md`](../docs/guides/github-quickstart.md).

(EV-OPERATOR-RECOVERY, EV-DB-001..008)

---

## 9. Rotating secrets after accidental exposure

If a secret has been accidentally committed or logged, rotate it immediately.

**KEK (`MINTKEY_VAULT_KEK` or `MINTKEY_BOOTSTRAP_KEK`)**
Re-generate the key, update `.env`, restart the stack. Any existing backup encrypted
with the old KEK can no longer be restored until the old KEK is re-supplied manually.
(EV-SECRET-001, EV-SECRET-002)

**Agent key (`mk_agent_*`)**
In admin-ui: **Agents → (agent) → Rotate Key**. The old key is invalidated immediately.
Update any `.env` or CI secrets that referenced it.
(EV-DB-001)

**Service token (`mk_svctoken_*`)**
In admin-ui: **Services → (service) → Rotate Token**. All active Kong routes using the
old token will return 401 until updated. Update `MINTKEY_BROKER_SERVICE_TOKEN` or
`MINTKEY_PROXY_SERVICE_TOKEN` in `.env` and restart the affected services.
(EV-SECRET-003, EV-SECRET-004)

**Admin password**
Force a re-seed via Option B in `docs/AUTH.md`:
```bash
docker compose down
rm data/bootstrap-secrets/.admin_password_synced
docker compose up -d
```
Back up first — see section 1 and 2 above. (EV-BOOTSTRAP-001)

---

## 10. Known gaps

The following gaps are acknowledged from this session's evidence audit. They are
not addressed in this session (see reasons); they are documented here so no
contributor is surprised.

| EvidenceRef | Gap | Status |
|---|---|---|
| EV-GAP-001 | No `pg_dump` was taken before the 2026-05-18 wipe; those rows are permanently lost | Operational fact — historical state cannot be recovered |
| EV-GAP-002 | `admin_ui_private.pem` / `admin_ui_public.pem` generation not yet in seed-job (T-1.0.4 pending) | Product-code change in seed-job; out of session scope |
| EV-GAP-003 | Actual `.env` contents not audited by this session (not on disk at audit time) | Operator-only knowledge; cannot audit what isn't present |
| EV-GAP-004 | Whether production uses a custom `MINTKEY_VAULT_KEK` | Operator-only knowledge |
| EV-GAP-005 | No automated/scheduled `pg_dump` (cron / health-check sidecar) | Out of session scope; doc-only mention |
| EV-GAP-006 | 8 unpinned images (Keycloak, Kong, etc.) remain after PR #70 closed postgres only | Follow-up session; see EV-COMPOSE-001..003 |
| EV-GAP-007 | `--rotate-bootstrap` flag behaviour not yet implemented | Depends on T-1.0.4; out of session scope |

---

---

## 11. Periodic backups via cron (optional)

> **OPT-IN only.** Nothing in this repository auto-installs a cron job. The steps
> below are advisory; run them only if you want recurring automated backups.
>
> **EV-GAP-005 closed** by `scripts/dev-backup-cron.example.sh` +
> `team/remediation/2026-05-18-r5-pg-dump-cron-docs/`.

### Why periodic backups

The one-time backup in section 2 requires manual invocation.  For long-running
development environments where you want a daily safety net — especially before
unattended overnight work — you can install a cron job that calls the wrapper
script automatically.

### The wrapper script

`scripts/dev-backup-cron.example.sh` is a thin orchestration layer around
`scripts/dev-backup.sh --write`.  It:

1. Validates `MINTKEY_REPO_DIR` is set and points to a git repository.
2. Optionally sources `MINTKEY_BOOTSTRAP_KEK` from a file
   (`MINTKEY_BOOTSTRAP_KEK_FILE`) so the KEK is never stored in the crontab
   itself, and passes `--with-secrets` to the backup when the file is present.
3. Appends all stdout+stderr to `.mintkey-backups/cron.log` (gitignored).
4. On success, prunes `.mintkey-backups/` subdirectories older than
   `MINTKEY_BACKUP_RETENTION_DAYS` days (default: 14).
5. **Fails closed** — any preflight failure (missing `MINTKEY_REPO_DIR`, not a
   git repo, `dev-backup.sh` missing, empty KEK file) exits non-zero with a
   clear error message and does NOT proceed.

### Crontab line shape

```
0 3 * * *  MINTKEY_REPO_DIR=/path/to/mintkey  MINTKEY_BOOTSTRAP_KEK_FILE=/secure/path/to/kek  bash /path/to/mintkey/scripts/dev-backup-cron.example.sh
```

To back up **without** secrets (keys-only, no KEK required):

```
0 3 * * *  MINTKEY_REPO_DIR=/path/to/mintkey  bash /path/to/mintkey/scripts/dev-backup-cron.example.sh
```

### 3-step install

1. **Verify the script works manually** (should fail with a clear error if env
   vars are missing):

   ```bash
   # Expect: exit non-zero + "MINTKEY_REPO_DIR is not set" message
   bash scripts/dev-backup-cron.example.sh 2>&1; echo "exit=$?"

   # Expect: exit 0 + backup written to .mintkey-backups/
   MINTKEY_REPO_DIR=/path/to/mintkey bash scripts/dev-backup-cron.example.sh
   ```

2. **Open your personal crontab** (never the system crontab):

   ```bash
   crontab -e
   ```

3. **Add a line** using the shape above.  Replace paths; adjust the hour (the
   `0 3 * * *` example runs at 03:00 UTC daily).  Save and exit.

   Verify with `crontab -l` that the line appears.

### Retention policy

- Default: backups older than **14 days** are pruned on each successful run.
- Override: set `MINTKEY_BACKUP_RETENTION_DAYS=N` in the crontab line.

  ```
  0 3 * * *  MINTKEY_REPO_DIR=/path/to/mintkey  MINTKEY_BACKUP_RETENTION_DAYS=30  bash /path/to/mintkey/scripts/dev-backup-cron.example.sh
  ```

- The log file `.mintkey-backups/cron.log` is **not** pruned; it grows
  indefinitely.  Rotate it manually or with `logrotate` if disk space is a
  concern.

### Checking the log

```bash
tail -50 .mintkey-backups/cron.log
```

### Security notes

- The `MINTKEY_BOOTSTRAP_KEK_FILE` path should be **outside the repo** (e.g.,
  `~/.config/mintkey/kek` or a secrets-manager socket path) and readable only
  by the user running cron (`chmod 600`).
- Never put the KEK value directly in the crontab line — that would expose it
  via `crontab -l` and process listings.
- The cron wrapper inherits the same secrets-handling guarantees as
  `dev-backup.sh`: values are Fernet-encrypted or redacted; nothing is printed
  to stdout/stderr in plaintext.

---

## Source / EvidenceRef map

Every claim in this document traces to a row in
[`team/remediation/2026-05-18-dev-settings-backup-recovery/EVIDENCE_LEDGER.md`](2026-05-18-dev-settings-backup-recovery/EVIDENCE_LEDGER.md).

| Section | EvidenceRefs cited |
|---|---|
| 1 — When to back up | EV-WIPE-001, EV-DESTRUCTIVE-001, EV-SECRET-001, EV-SECRET-002, EV-COMPOSE-001, EV-BOOTSTRAP-001..006, EV-DESTRUCTIVE-011 |
| 2 — The one command | EV-VOL-001..007, EV-DB-001..008, EV-ENV-002..005 |
| 3 — Reading the output | (manifest format, no separate row needed — derived from section 2 refs) |
| 4 — The restore command | EV-VOL-001..007, EV-DB-001..008 |
| 5 — Secrets policy | EV-SECRET-001, EV-SECRET-002, EV-ENV-002..005 |
| 6 — What is NOT backed up | EV-GAP-001, EV-GAP-002, EV-OBS-006, EV-BOOTSTRAP-007 |
| 7 — What is rotated on re-seed | EV-BOOTSTRAP-001..006 |
| 8 — Recovering without a backup | EV-OPERATOR-RECOVERY, EV-DB-001..008 |
| 9 — Rotating secrets | EV-SECRET-001..004, EV-BOOTSTRAP-001, EV-DB-001 |
| 10 — Known gaps | EV-GAP-001..007 |
| 11 — Periodic backups via cron | EV-GAP-005 |
