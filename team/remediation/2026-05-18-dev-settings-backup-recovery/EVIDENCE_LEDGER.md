# Evidence Ledger — Dev Settings Backup & Recovery

**Session:** `2026-05-18-dev-settings-backup-recovery`

This ledger is the source of truth for every change in this session. Every row must trace to (a) a real file/script/doc in the repo or (b) a documented external state (Docker volume, DB row, env var). No implementer chunk may modify a file that does not appear here.

**Schema:**

| EvidenceRef | Source | Setting/state affected | Destructive path | Why backup/recovery is needed | Proposed fix |
|---|---|---|---|---|---|

`EvidenceRef` namespace prefixes:
- `EV-WIPE-*` — anchor incidents (the data wipe that motivated this session)
- `EV-ENV-*` — env files
- `EV-COMPOSE-*` — docker-compose + overrides
- `EV-VOL-*` — Docker named volumes
- `EV-BOOTSTRAP-*` — bootstrap-secrets
- `EV-KC-*` — Keycloak realm/client/admin
- `EV-OBS-*` — Grafana/Jaeger/oauth2-proxy/Kong settings
- `EV-APP-*` — admin-api / admin-ui / mcp-server local config
- `EV-KIRO-*` — Kiro/Codex/remediation session config
- `EV-SECRETS-*` — generated secrets/keys
- `EV-DB-*` — local DB seed/admin state
- `EV-DESTRUCTIVE-*` — destructive scripts/commands
- `EV-DOC-*` — destructive doc instructions
- `EV-GAP-*` — explicit "we searched and found nothing" rows
- `EV-LEAK-*` — secrets accidentally committed during this session (post-mortem; treat as audit trail)

## Mid-session incidents

| EvidenceRef | Source | What happened | Mitigation |
|---|---|---|---|
| EV-LEAK-001 | This session, scaffold commit `ec322aa` (later rewritten to `1b2e3a6`) | The ORCHESTRATOR (me) wrote the live `mk_agent_*` plaintext into `ISSUE_INTAKE.md:55` as "evidence" of the manual post-wipe recovery. Committed and pushed to `origin/fix/dev-settings-backup-recovery-2026-05-18`. Live on GitHub for ~30–60 minutes. | C-5 reviewer (Opus, fresh) caught the leak on first pass. Orchestrator scrubbed via `git rebase -i` rewriting the offending commit, then `git push --force-with-lease`. Branch history is now clean. **Owner action required**: rotate the agent's key in admin-ui (Agents → that agent → Rotate Key), per the HOWTO Section 9 workflow this very session authored. Failure mode is the exact class this session exists to prevent — proves the value of the C-5 fresh-reviewer gate. |

## Anchor entries (pre-investigation)

| EvidenceRef | Source | Setting/state affected | Destructive path | Why backup/recovery is needed | Proposed fix |
|---|---|---|---|---|---|
| EV-WIPE-001 | This session's intake; postgres container created-time `2026-05-17T21:38:32Z`; `SELECT COUNT(*) FROM agents` returned 0 post-wipe | `agents`, `services`, `permissions`, all manually-curated DB rows in postgres | `docker compose up -d --wait` re-pulling `postgres:16` after Docker Hub tag-digest drift → fresh `postgres_data` volume init | Lost ~10 minutes of mid-campaign orchestrator work; required manual re-create via admin-ui | PR #70 (postgres pin) closes the trigger; this session covers the broader class — provide a backup-before-reset workflow that captures these tables |
| EV-WIPE-002 | `admin-api/src/admin_api/api/auth.py:74` D2-b gate | Operator login via internal-login disabled (`internal_password_hash IS NULL`) → must use OIDC via Keycloak browser flow | Any reset that doesn't restore Keycloak's `operators.internal_password_hash` leaves the operator unable to log in without the Keycloak admin UI | After a wipe, the only login path requires a Keycloak browser session — automation can't recover the operator credential without manual help | Backup must capture (or document re-derivation of) the Keycloak admin password + the operator's Keycloak user state |
| EV-OPERATOR-RECOVERY | This conversation; agent `agent_01KRW0GP04MV7Q7JRVVH44N6XJ` created post-wipe by user | Agent records + their `mk_agent_*` keys | Volume wipe + seed-job doesn't re-create agents | Without backup, every agent + permission grant has to be hand-rebuilt | dev-backup.sh should `pg_dump` the agents/services/permissions tables; dev-restore.sh should restore them |

## C-1 audit findings

Distilled from the C-1 Investigator's `/tmp/c1_evidence_report.md` (Sonnet, 2026-05-18). Every row below is independently re-verifiable by reading the cited file at the cited line.

### Category A — env files

| EvidenceRef | Source | Setting/state affected | Destructive path | Why backup/recovery is needed | Proposed fix |
|---|---|---|---|---|---|
| EV-ENV-001 | `.env.example` | `repo-tracked default`, `safe to commit` | N/A (template) | Reference template | None — leave as-is |
| EV-ENV-002 | `.env` (user-created; not on disk) | `local user config`, `must never commit` | Accidental `git add -A`; fresh clone overwrites | User-edited overrides | Already gitignored (root `.gitignore:9`); backup script includes it (redacted by default) |
| EV-ENV-003 | `.env.local` (user-created; not on disk) | `local user config`, `must never commit` | Accidental commit | User-edited overrides | Already gitignored (root `.gitignore:10`); backup script includes it (redacted) |
| EV-ENV-004 | `admin-ui/e2e/.env.example` | `repo-tracked default`, `safe to commit` | N/A | Reference template | None |
| EV-ENV-005 | `admin-ui/e2e/.env.local` (auto-generated by `scripts/e2e-setup-env.sh`) | `generated secret`, `local user config`, `must never commit` | Stack wipe + re-seed rotates the embedded password; `make test:e2e-setup` regenerates | **NOT gitignored in `admin-ui/.gitignore`** — accidental-commit risk + recovery requires rerun | C-2 backup includes it (redacted); **C-3 must add `e2e/.env.local` to `admin-ui/.gitignore`** |
| EV-ENV-006 | No sub-package `.env` files in admin-api/mcp-server/services/seed-job/mock-backend/mintkey-models | `EV-GAP` | N/A — these packages get env from docker-compose | N/A | None |

### Category B — docker-compose + image pins

| EvidenceRef | Source | Setting/state affected | Destructive path | Why backup/recovery is needed | Proposed fix |
|---|---|---|---|---|---|
| EV-COMPOSE-001 | `docker-compose.yml` — 9 image refs | Image references | Tag-only refs subject to digest drift (PR #70 closed postgres only) | Today's wipe was postgres digest drift. 8 images remain tag-only. | Pin Keycloak + Kong as next-highest-risk follow-up session; document the risk in this session's docs |
| EV-COMPOSE-002 | `quay.io/keycloak/keycloak:24.0` (compose line 54) | `repo-tracked default`, image tag | Digest drift → schema migration → postgres_data corruption | Highest secondary risk after postgres | Pin in follow-up |
| EV-COMPOSE-003 | `kong:3.6`, `liquibase/liquibase:4.27.0`, `otel/...:0.104.0`, `jaegertracing/all-in-one:1.56`, `prom/prometheus:v2.51.0`, `gcr.io/cadvisor/cadvisor:v0.49.1`, `grafana/grafana:10.3.3` (compose; 7 lines) | Tag-only images | Digest drift on `up -d` (lower risk than Keycloak/Postgres) | Lower probability of breakage but still possible | Pin in follow-up |

### Category B — Docker volumes (mapped to the 7 named volumes)

| EvidenceRef | Volume | Mountpath / service | Data type | Destructive path | Recovery path |
|---|---|---|---|---|---|
| EV-VOL-001 | `postgres_data` | `/var/lib/postgresql/data` (postgres) | tenants, operators, **agents** (user-created), **services** (user-created), credentials, audit_events, audit_chain_state, permission_grants, Keycloak realm/client/user config | `docker compose down -v`; postgres digest drift (CLOSED by PR #70) | `pg_dump` before; seed-job re-seeds structural; **user rows lost permanently** without backup |
| EV-VOL-002 | `vault_data` | `/var/lib/mintkey` (vault-adapter) | Encrypted credential envelopes (AES-GCM, DEK-wrapped per ADR-0003) | `docker compose down -v` | Loss of `vault_data` OR `vault_kek` → credentials unrecoverable |
| EV-VOL-003 | `vault_kek` | `/run/secrets` (vault-adapter) | AES-256 Key Encryption Key (separate mount per ADR-0003) | `docker compose down -v` | Same — both volumes required |
| EV-VOL-004 | `bootstrap_secrets` | `/run/secrets/mintkey/bootstrap-secrets/` (seed-job rw; admin-api/admin-ui/grafana/jaeger-auth ro) | Fernet-encrypted admin password, OIDC client secrets (×3), oauth2 cookie secret, admin_ui keypair (NOT yet generated), `.admin_password_synced` sentinel | `docker compose down -v` | seed-job regenerates (rotates all secrets); admin-ui keypair gap (see EV-BOOTSTRAP-007) |
| EV-VOL-005 | `grafana_data` | `/var/lib/grafana` (grafana) | User-created dashboards, org settings, user preferences | `docker compose down -v` | Provisioned dashboards (6 JSONs) auto-restore; user-created content lost permanently |
| EV-VOL-006 | `broker_wal` | `/var/lib/mintkey` (broker) | In-flight WAL only | `docker compose down -v` | Auto-recovers; committed rows safe |
| EV-VOL-007 | `proxy_wal` | `/var/lib/mintkey` (proxy-plugin) | In-flight WAL only | `docker compose down -v` | Auto-recovers |

### Category C — bootstrap secrets (in `bootstrap_secrets` volume)

| EvidenceRef | File | Description | Destructive path | Recovery path |
|---|---|---|---|---|
| EV-BOOTSTRAP-001 | `admin_password` (Fernet-encrypted) | Bootstrap admin password | `docker compose down -v` | seed-job regenerates (rotates) |
| EV-BOOTSTRAP-002 | `oidc_client_secret` (admin-api) | Keycloak OIDC client secret | `docker compose down -v` | seed-job re-fetches from Keycloak |
| EV-BOOTSTRAP-003 | `grafana_oidc_client_secret` | Grafana OIDC | `docker compose down -v` | seed-job re-fetches |
| EV-BOOTSTRAP-004 | `jaeger_oidc_client_secret` | Jaeger OIDC | `docker compose down -v` | seed-job re-fetches |
| EV-BOOTSTRAP-005 | `jaeger_oauth2_cookie_secret` | 44-char base64 cookie secret | `docker compose down -v` | seed-job regenerates idempotently |
| EV-BOOTSTRAP-006 | `.admin_password_synced` sentinel | "Already synced to Keycloak" marker | `docker compose down -v`; explicit delete in `docs/NETWORK.md` Option B re-seed | seed-job recreates |
| EV-BOOTSTRAP-007 | `admin_ui_private.pem` / `admin_ui_public.pem` | Ed25519 keypair for signed admin-ui requests | seed-job steps 6-8 NEVER generate these (pending T-1.0.4 per `seed-job/main.py:1040`) | **GAP** — admin-ui falls back to unsigned mode (per `docs/AUTH.md:228`) |

### Category D — Keycloak

| EvidenceRef | Source | Setting | Destructive path | Recovery path |
|---|---|---|---|---|
| EV-KC-001 | `seed-job/realm-mintkey.json` | Realm definition | N/A — committed to git | None needed |
| EV-KC-002 | Keycloak client secrets (DB-stored) | mintkey-admin-api, mintkey-grafana, mintkey-jaeger | `docker compose down -v` (Keycloak shares `postgres_data`) | seed-job re-fetches → bootstrap_secrets |
| EV-KC-003 | `KEYCLOAK_ADMIN_PASSWORD: changeme` (compose line 68) | Dev fixture password | N/A for dev | Hardcoded |
| EV-KC-004 | Keycloak redirect URIs / public URLs | Set via `.env`'s `MINTKEY_*_PUBLIC_URL` vars | `.env` deletion → defaults to localhost | Set in `.env`; seed-job patches |

### Category E — Grafana / Jaeger / Kong / oauth2-proxy

| EvidenceRef | Source | Description | Destructive path | Recovery path |
|---|---|---|---|---|
| EV-OBS-001 | `grafana/provisioning/dashboards/*.json` (6 files) | Provisioned dashboards | N/A — committed | None needed |
| EV-OBS-002 | `grafana/provisioning/datasources/prometheus.yaml` | Prometheus datasource | N/A — committed | None needed |
| EV-OBS-003 | `grafana_data` user-created content | User dashboards/orgs/prefs | `docker compose down -v` | None — lost permanently |
| EV-OBS-004 | jaeger-auth `entrypoint.sh` | Auth script | N/A — committed | None |
| EV-OBS-005 | jaeger OIDC client secret + cookie secret | (see EV-BOOTSTRAP-004,005) | `docker compose down -v` | seed-job regenerates |
| EV-OBS-006 | `services/proxy-plugin/kong.yml` (declarative) | Auto-regenerated by kong-syncer from DB | Manual edit + `git checkout` would lose it; kong-syncer regenerates from postgres | git + kong-syncer |

### Category F — admin-api / admin-ui local config

| EvidenceRef | Source | Description | Destructive path | Recovery path |
|---|---|---|---|---|
| EV-APP-001 | `admin-api/src/admin_api/api/settings.py` | Repo-tracked Python module | N/A — committed | None needed |
| EV-APP-002 | `admin-ui/e2e/.env.local` (auto-gen) | Per EV-ENV-005 (gitignore gap) | Stack wipe; not gitignored in admin-ui | Re-run `make test:e2e-setup`; **C-3 to add gitignore entry** |

### Category G — Kiro / Codex / remediation session config

| EvidenceRef | Source | Description | Destructive path | Recovery path |
|---|---|---|---|---|
| EV-KIRO-001 | `.kiro/settings/mcp.json` | Tool config; no secrets | N/A — committed | None |
| EV-KIRO-002 | `.kiro/setup-state.json` | Setup checkpoint | N/A — committed | None |
| EV-KIRO-003 | `.kiro/specs/` (4 specs) | Repo-tracked specs | N/A — committed | None |
| EV-KIRO-004 | `.kiro/steering/` (11 docs) | Repo-tracked steering | N/A — committed | None |
| EV-CODEX-001 | `.codex` (empty file) | N/A | N/A | N/A |
| EV-SESSION-001 | `team/remediation/<session>/` | Intended-to-commit once closed | N/A | git |

### Category H — generated secrets / keys

| EvidenceRef | Source | Description | Destructive path | Recovery path |
|---|---|---|---|---|
| EV-SECRET-001 | `MINTKEY_VAULT_KEK: "0102030405..."` (compose line 149) | Dev KEK fixture (documented in `SECURITY.md:61,104`) | N/A for dev | Override via `.env` in production |
| EV-SECRET-002 | `MINTKEY_BOOTSTRAP_KEK: "TUQpz9CU..."` (compose lines 129,239; scripts/e2e-setup-env.sh:71) | Dev Fernet key fixture | N/A for dev | Override via `.env` |
| EV-SECRET-003 | `MINTKEY_BROKER_SERVICE_TOKEN: "mk_svctoken_dev_broker_..."` | Dev fixture | N/A for dev | Override via `.env` |
| EV-SECRET-004 | `MINTKEY_PROXY_SERVICE_TOKEN: "mk_svctoken_dev_proxy_..."` | Dev fixture | N/A for dev | Override via `.env` |
| EV-SECRET-005 | `SESSION_SECRET: mintkey-session-secret-change-in-production` | Dev fixture | N/A for dev | Override via `.env` |
| EV-SECRET-006 | `POSTGRES_PASSWORD: changeme` | Dev fixture | N/A for dev | Override via `.env` |

### Category I — local DB seed/admin state

| EvidenceRef | Table | Status | Destructive path | Recovery path |
|---|---|---|---|---|
| EV-DB-001 | `agents` | **User-created via admin-ui; not seeded** | `docker compose down -v` | `pg_dump` before; **no automation today**; lost permanently otherwise |
| EV-DB-002 | `services` | **User-created via admin-ui; not seeded** | `docker compose down -v` | Same as EV-DB-001 |
| EV-DB-003 | `tenants` (`t_default`) | Seeded by seed-job | `docker compose down -v` | seed-job re-seeds idempotently |
| EV-DB-004 | `operators` (bootstrap admin) | Seeded by seed-job | `docker compose down -v` | seed-job re-seeds; password rotates |
| EV-DB-005 | `audit_chain_state` genesis row | Deterministic from tenant_id | `docker compose down -v` | seed-job re-seeds |
| EV-DB-006 | `audit_events` rows | Immutable audit trail | `docker compose down -v` | **NOT recoverable** once lost |
| EV-DB-007 | `credentials` (vault-encrypted envelopes) | User-created | `docker compose down -v` | **NOT recoverable** without both vault_data AND vault_kek volumes |
| EV-DB-008 | `permission_grants` | User-created via admin-ui | `docker compose down -v` | Lost permanently without backup |

### Category J — destructive scripts and commands

| EvidenceRef | Source:line | Operation | Confirmation today | C-3 action |
|---|---|---|---|---|
| EV-DESTRUCTIVE-001 | Ad-hoc `docker compose down -v` (no script) | Removes all 7 named volumes | **NONE** | Cannot guard ad-hoc shell commands; **mitigated by docs warnings (C-4) + the backup script** |
| EV-DESTRUCTIVE-002 | `install.sh --clean` (interactive) — line ~1000 | `docker compose down -v --timeout 30` | YES — `[y/N]` prompt with 30s timeout | Already gated — **no change needed**; verify in C-3 read |
| EV-DESTRUCTIVE-003 | `install.sh --clean --non-interactive` | Bypasses prompt | **NONE** — non-interactive flag exists | **C-3: require additional `--force-destroy` (or equivalent) when combined with --clean+--non-interactive** |
| EV-DESTRUCTIVE-004 | `.github/workflows/ci.yml:261` — `docker compose down -v` | CI cleanup | N/A — ephemeral runner | **No change** (CI runner has no persistent state) |
| EV-DESTRUCTIVE-005 | `.github/workflows/playwright.yml:96,170` | CI cleanup | N/A — ephemeral runner | **No change** |
| EV-DESTRUCTIVE-006 | `CLAUDE.md:224` — text "suggested command" | AI-agent-readable instruction | NONE | **C-4 doc fix**: prepend `# WARNING` + link to HOWTO |
| EV-DESTRUCTIVE-007 | `AGENTS.md:226` | Same as CLAUDE.md | NONE | **C-4 doc fix**: same |
| EV-DESTRUCTIVE-008 | `.serena/memories/suggested_commands.md:8` — `# stop and remove volumes` | Routine-command framing | NONE | **C-4 doc fix**: change comment to destructive warning |
| EV-DESTRUCTIVE-009 | `docs/guides/10min-mock-demo.md:353` — `# WARNING: deletes all volumes` | Already has a warning comment | Comment only; no gate | **C-4 doc fix**: link to backup HOWTO |
| EV-DESTRUCTIVE-010 | `docs/guides/10min-mock-demo.md:379` — `docker volume rm mintkey_postgres_data (data loss!)` | Inline-note in troubleshooting table | Inline note | **C-4 doc fix**: explicit "pg_dump first" prefix |
| EV-DESTRUCTIVE-011 | `docs/NETWORK.md:225-232` — Option B re-seed | `down` + delete sentinel + `up -d` → rotates bootstrap secrets | Comment warns "last resort" | **C-4 doc fix**: add explicit pre-flight backup step |

### Category K — destructive doc instructions

Folded into EV-DESTRUCTIVE-006..011 above (the documentation IS the destructive surface for these). No separate K-rows.

### Gaps explicitly acknowledged

| EvidenceRef | Gap | Why deferred from this session |
|---|---|---|
| EV-GAP-001 | Pre-incident `pg_dump` — none was taken; today's wiped agents/services rows are permanently lost | Operational fact; cannot recover historical state |
| EV-GAP-002 | `admin_ui_private.pem` / `admin_ui_public.pem` generation (T-1.0.4 pending) | Product-code change in seed-job; out of session scope per intake |
| EV-GAP-003 | Actual `.env` contents | Not on this orchestrator's disk; can't audit what isn't there |
| EV-GAP-004 | Whether prod uses a custom `MINTKEY_VAULT_KEK` | Operator-only knowledge |
| EV-GAP-005 | `pg_dump` automation (cron / scheduled) | Out of session scope; **doc-only mention** in C-4 |
| EV-GAP-006 | 8 unpinned images (Keycloak/Kong/etc.) | **Follow-up session**; doc-only mention in C-4 |
| EV-GAP-007 | `--rotate-bootstrap` flag behaviour | Depends on T-1.0.4; out of session scope |

## Coverage check

- Category A (env files): ✅ EV-ENV-001..006
- Category B (docker-compose + volumes + image pins): ✅ EV-COMPOSE-001..003 + EV-VOL-001..007
- Category C (bootstrap secrets): ✅ EV-BOOTSTRAP-001..007
- Category D (Keycloak): ✅ EV-KC-001..004
- Category E (Grafana/Jaeger/Kong/oauth2-proxy): ✅ EV-OBS-001..006
- Category F (admin-api/admin-ui local config): ✅ EV-APP-001..002
- Category G (Kiro/Codex/remediation): ✅ EV-KIRO-001..004 + EV-CODEX-001 + EV-SESSION-001
- Category H (generated secrets/keys): ✅ EV-SECRET-001..006
- Category I (local DB seed/admin state): ✅ EV-DB-001..008
- Category J (destructive scripts): ✅ EV-DESTRUCTIVE-001..011
- Category K (destructive doc instructions): ✅ (folded into Category J)
- Gaps: ✅ EV-GAP-001..007
