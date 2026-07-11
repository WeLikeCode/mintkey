# How-To: Mintkey operator playbook

The substantive runbooks live under [`docs/guides/`](guides/). This file is the index. Each
section below names the task and links out to the guide that covers it; content is not duplicated
here.

---

## 1. Prerequisites

Do not repeat the full table here — see [`QUICKSTART.md`](../QUICKSTART.md) "Prerequisites"
section for the exact list (Docker, docker compose, ports, disk space).

---

## 2. First-time setup

| Step | One-line summary | Full instructions |
|---|---|---|
| 1. Generate the SSH proxy host key | `make ssh-proxy-init` — seeds the persistent Ed25519 host key into the `mintkey_ssh_proxy_hostkey` volume (idempotent; skips if key already exists). Must run before `make dev` the first time. | See `make help` |
| 2. Bring the stack up | `make dev` — starts 15 long-running containers + 2 one-shot jobs | [`QUICKSTART.md`](../QUICKSTART.md) §1 |
| 3. Get the bootstrap admin password | Printed once to stdout; also at `./data/bootstrap-secrets/` (mode `0400`) | [`docs/guides/github-quickstart.md`](guides/github-quickstart.md) §0 |
| 4. Open the Admin UI | `http://localhost:8081` | [`PORTS.md`](../PORTS.md) "Quick access" |

> **Note on SSH proxy port exposure:** `make dev` binds `:2222` on all host interfaces by
> default. In production, restrict this to a specific interface (e.g. `0.0.0.0:2222`) behind
> a firewall or load balancer — do not expose it on a public IP without additional access
> controls. The HTTP metrics port (`8089`) should not be publicly reachable.

---

## 3. Service playbooks

| Task | Guide |
|---|---|
| Run the 10-minute demo (no external keys) | [`docs/guides/10min-mock-demo.md`](guides/10min-mock-demo.md) |
| Register a GitHub service (PAT, API key) | [`docs/guides/github-quickstart.md`](guides/github-quickstart.md) |
| Register a CoinGecko service via Hermes | [`docs/guides/hermes-coingecko-quickstart.md`](guides/hermes-coingecko-quickstart.md) |
| Connect Claude Desktop | [`docs/guides/mcp-clients/claude-desktop.md`](guides/mcp-clients/claude-desktop.md) |
| Connect Claude Code | [`docs/guides/mcp-clients/claude-code.md`](guides/mcp-clients/claude-code.md) |
| Connect Cursor | [`docs/guides/mcp-clients/cursor.md`](guides/mcp-clients/cursor.md) |
| Connect mcp-cli | [`docs/guides/mcp-clients/mcp-cli.md`](guides/mcp-clients/mcp-cli.md) |
| Add a new auth scheme (developer task) | [`CONTRIBUTING.md`](../CONTRIBUTING.md) §6; [`CLAUDE.md`](../CLAUDE.md) "How to add an X" |

---

## 4. Backup and restore

### Pre-requisites

- Running Mintkey stack (`make dev` or `docker compose up -d`).
- Docker volumes `mintkey_vault_data` and `mintkey_vault_kek` must exist (they are created on first `make dev`).
- The postgres container `mintkey-postgres-1` must be reachable.

> **WARNING: KEK is required to decrypt any credential.** The `vault-kek.tar.gz` artifact contains the Fernet KEK used to encrypt credentials at rest. Losing the KEK makes all postgres + sqlite dumps permanently unreadable, even with the data intact. Back up the KEK volume along with everything else — `make backup` does this automatically.

### `make backup` — create a timestamped backup

```bash
make backup
```

Creates `~/mintkey-backups/<TS>/` containing:

| File | Contents |
|---|---|
| `postgres-mintkey.pgcustom` | `pg_dump -F custom -Z 9` of the `mintkey` DB (agents, services, permissions, credentials, audit) |
| `vault.sqlite` | Binary copy of the SQLite vault (the primary credential store today) |
| `vault.sqlite.sql` | Text dump of the SQLite vault (for diffing) |
| `vault-kek.tar.gz` | Contents of the `mintkey_vault_kek` Docker volume (the Fernet KEK) |
| `bootstrap-secrets.tar.gz` | Contents of `data/bootstrap-secrets/` (admin password ciphertext) |
| `MANIFEST.txt` | One line per file: `<size>  <sha256>  <filename>` |

Sample output:
```
==> Backup started: /Users/you/mintkey-backups/20260531_225805 (20260531_225805)

--> [1/5] Postgres dump (mintkey DB)...
    postgres dump: OK
--> [2/5] Vault SQLite (mintkey_vault_data volume)...
    vault.sqlite: OK
    vault.sqlite.sql: OK
--> [3/5] KEK volume (mintkey_vault_kek)...
    vault-kek.tar.gz: OK (filenames only — KEK contents not logged)
--> [4/5] Bootstrap secrets (data/bootstrap-secrets/)...
    bootstrap-secrets.tar.gz: OK
--> [5/5] Writing MANIFEST.txt with sha256 checksums...
    MANIFEST.txt: OK

==> Backup complete: /Users/you/mintkey-backups/20260531_225805
    Restore with: make restore BACKUP_DIR=/Users/you/mintkey-backups/20260531_225805
```

### `make restore BACKUP_DIR=<path>` — restore from a backup

```bash
make restore BACKUP_DIR=~/mintkey-backups/20260531_225805
```

Validates all MANIFEST.txt SHA-256 checksums before touching any state, then:
1. Stops dependent services (postgres + keycloak stay up).
2. Restores the postgres DB via `pg_restore --clean --if-exists`.
3. Restores `vault.sqlite` into the `mintkey_vault_data` volume.
4. Restores the KEK into the `mintkey_vault_kek` volume (replaces all contents).
5. Backs up the existing `data/bootstrap-secrets/` to `.bak.<TS>` and extracts the archived version.
6. Restarts all dependent services with `docker compose up -d --no-deps`.

Add `MINTKEY_RESTORE_FORCE=1` to skip the interactive confirmation prompt:

```bash
MINTKEY_RESTORE_FORCE=1 make restore BACKUP_DIR=~/mintkey-backups/20260531_225805
```

### Restoring on a fresh machine

1. Clone the repo and run `make dev` once — this creates all Docker volumes and runs the seed job.
2. Wait for the stack to be fully healthy: `curl http://localhost:8080/v1/health` returns `{"status":"ok"}`.
3. Stop dependent services and restore:
   ```bash
   MINTKEY_RESTORE_FORCE=1 make restore BACKUP_DIR=/path/to/backup
   ```
4. The stack will restart automatically. Verify with `docker compose ps` and `make smoke`.

### Restoring a raw pg_dump into a bare Postgres instance

If you are restoring `postgres_dump.sql.gz` directly (e.g. into a standalone Postgres container for verification or disaster recovery outside the normal stack), the two application roles must exist before the dump is loaded — otherwise every table-ownership statement fails with `role does not exist`:

```bash
psql -U postgres -d mintkey -c "CREATE ROLE mintkey_app;"
psql -U postgres -d mintkey -c "CREATE ROLE mintkey_migrate;"
gunzip -c postgres_dump.sql.gz | psql -U postgres -d mintkey
```

`make restore` handles this automatically (the Makefile pre-creates both roles). This prerequisite only applies when loading the dump manually.

> Note: if the seed-job runs again after restore (e.g. due to a container restart), it may rotate bootstrap secrets. To prevent this, restore *after* the seed-job has run and the stack is healthy — not before.

### List available backups

```bash
make backup-list
```

---

## 5. SSH bastion onboarding

Kong is HTTP-only; SSH is a long-lived TCP protocol. Mintkey therefore runs a separate
SSH listener on `:2222` (the `ssh-proxy` container), independent of Kong.

**Architecture deep-dive:** [docs/architecture/01-architecture/ssh-bastion.md](architecture/01-architecture/ssh-bastion.md) — data-flow diagram, single-port multiplexing explanation, port table, JWT claim map, connection lifecycle, and security boundary.  
**Decision record:** [ADR-0022](architecture/01-architecture/adr/0022-ssh-bastion.md)

### Architecture (overview)

```
agent (ssh client)
        │
        │  TCP :2222  JWT-as-password
        ▼
  ssh-proxy :2222
  ├── validates JWT (JWKS from broker :8083)
  ├── fetches credential (gRPC vault-adapter :8084)
  │     └── vault-adapter JOINs public.services → returns base_url
  └── dials upstream SSH server (host:port from services.base_url)
             │
             ▼
     upstream SSH server (any host:port)
```

> **Routing address vs auth material.** The upstream host:port is owned by the **service's
> `base_url`** (set via Admin UI Services → Edit, format: `ssh://host:port`). The credential row
> holds only auth material: the private key or password, plus `ssh_user`. Per
> [ADR-0023](architecture/01-architecture/adr/0023-ssh-upstream-base-url-canonical.md).

### One-time setup

| Step | Command | Notes |
|---|---|---|
| Seed bastion host key | `make ssh-proxy-init` | Idempotent; seeds Ed25519 host key into `mintkey_ssh_proxy_hostkey` volume. Run before `make dev` the first time. |
| Start the stack | `make dev` | Binds `:2222` on all host interfaces. In production, restrict to a specific interface behind a firewall. |

### Adding an SSH service via the Admin UI

1. **Services → New → From Template**: choose `ssh-bastion-key` (private-key auth) or
   `ssh-bastion-password` (username + password).
2. Replace the placeholder base URL `ssh://CHANGE-ME:22` with your real target, e.g.
   `ssh://internal-server.corp:22`. **This is the canonical upstream address** — ssh-proxy dials
   whatever is set here. Changing this field later takes effect after the next credential fetch
   (subject to DEKCache TTL, ≤ 10 min; see [ADR-0023](architecture/01-architecture/adr/0023-ssh-upstream-base-url-canonical.md) §Follow-up F1).
3. Open the service → **Set Credential** — provide only auth material:
   - For `ssh-bastion-key`: paste the private key (PEM/OpenSSH) in the text area and set
     `ssh_user`. **Do not set `target_address`** — the host:port is inherited from `base_url`.
   - For `ssh-bastion-password`: set `ssh_user` and `ssh_password`. **Do not set
     `target_address`** — the host:port is inherited from `base_url`.
4. **Permission Grants → New**: grant the relevant agent `call` on this service.

> **To change the upstream host:port later:** edit the service's `base_url` (Admin UI Services →
> Edit, or `PATCH /v1/tenants/{tid}/services/{sid}`). Do not edit the credential's `target_address`
> — that field is deprecated and will be removed in a follow-up migration.

### Using the service from an agent

**Step 1 — request a token:**

```bash
TOKEN=$(curl -s -X POST http://localhost:8082/v1/tools/request_token \
  -H "Authorization: Bearer $AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\":\"$SID\",\"action\":\"call\"}" | jq -r '.token')
```

The response includes an `ssh_connect` block alongside the token:

```json
{
  "token": "<JWS>",
  "ssh_connect": {
    "host": "ssh-proxy",
    "port": 2222,
    "external_host": "10.243.1.200",
    "external_port": 2222,
    "ssh_user": "<agent_id>",
    "auth_method": "password",
    "password_is_jwt": true,
    "hint": "ssh -p 2222 <agent_id>@<host> with the token above used as the SSH password"
  },
  "expires_at": "...",
  "service_id": "...",
  "action": "call"
}
```

**Step 2 — SSH in (use `ssh_connect.external_host` and `ssh_connect.ssh_user`):**

```bash
AGENT_ID=$(echo "$TOKEN_RESPONSE" | jq -r '.ssh_connect.ssh_user')
BASTION="10.243.1.200"

# Non-interactive (scripted):
sshpass -p "$TOKEN" ssh -p 2222 \
  -o PreferredAuthentications=password \
  -o PubkeyAuthentication=no \
  -o StrictHostKeyChecking=accept-new \
  "$AGENT_ID@$BASTION" 'whoami'

# Interactive — paste the JWT when prompted:
ssh -p 2222 -o PreferredAuthentications=password "$AGENT_ID@$BASTION"
```

> **JWT lifetime**: ~10 minutes. For long-running operations, re-request a token before
> expiry and reconnect (`request_token` is cheap).

### Verifying it works (operator's view)

**Via Admin UI:** Services → select the SSH service → **Test Service** → "Test SSH
Connection" panel → **Run Test**.

**Via SQL (audit events):**

```sql
SELECT event_type, payload->>'agent_id', payload->>'target_host'
FROM audit_events
WHERE event_type LIKE 'ssh.%'
ORDER BY at DESC LIMIT 10;
```

**Session recordings** are written to `/var/lib/mintkey/ssh-recordings/<session_id>.cast`
inside the `ssh-proxy` container. SHA-256 integrity is embedded in the `ssh.session.ended`
audit event.

### Common confusions (FAQ)

| Question | Answer |
|---|---|
| "Why does Kong return 404/502 for my SSH service?" | Kong is HTTP-only. SSH services have no Kong route. Use the bastion path (`:2222`). |
| "Do I need a Mintkey CLI?" | No. Vanilla `ssh` + the JWT as password. No extra tooling required. |
| "Does the agent see the upstream private key / password?" | No. Only the vault holds it. The agent presents a JWT; the bastion fetches and uses the credential internally. |
| "Where does the JWT come from?" | The MCP `request_token` tool. The bastion validates it against the broker's JWKS endpoint. |

### Security notes

- JWTs are short-lived (~10 min) and single-use for the duration of each connection.
- Upstream host-key trust uses TOFU (trust-on-first-use) at first connection.
- Session recordings are tamper-evident: SHA-256 digest in the `ssh.session.ended` audit event.
- Agent forwarding (`-A`), X11 (`-X`), and local/remote TCP forwarding (`-L`/`-R`) are disabled by the bastion.

---

## 6. Email services

Mintkey can broker email credentials so agents send and receive email without holding passwords
or OAuth2 tokens. A separate `email-proxy` container handles IMAP reads and SMTP sends on port
**`:8088`**. The architecture decision is [ADR-0024](architecture/01-architecture/adr/0024-email-proxy-support.md).

### 6.0 Quick start: Services → New → From Template → Gmail / Outlook / iCloud

1. Open the Admin UI and navigate to **Email Services → Create from Template** (or use the
   **Services** sidebar and select **From Template** — email templates appear in the **Email**
   category).
2. Click the template that matches your provider:
   - **Gmail (OAuth2)** — `imap.gmail.com:993` + `smtp.gmail.com:465`
   - **Outlook / Office 365 (OAuth2)** — `outlook.office365.com:993` + `smtp.office365.com:587`
   - **iCloud Mail (App Password)** — `imap.mail.me.com:993` + `smtp.mail.me.com:587`
   - **Generic IMAP + SMTP (Password)** — fill `imap_host` and `smtp_host` manually
3. Optionally override the **Name** field; all IMAP/SMTP/port/auth fields are pre-filled.
4. Click **Create Email Service from Template**.
5. For OAuth2-flavoured services (Gmail / Outlook), the service row is created first; complete
   the OAuth2 authorization by clicking **Authorize Gmail** (or **Authorize Outlook**) on the
   service's show page. This opens the provider's consent screen; the resulting `refresh_token`
   is stored encrypted in the vault. See ADR-0024 for the full OAuth2 flow.
6. For password / app-password services, add the credential directly via **Set Credential**.

**Architecture overview:**

```
agent (JWT)
       │
       │  HTTP :8088  Authorization: Bearer <JWS>
       ▼
 email-proxy :8088
 ├── validates JWT (JWKS from broker :8083)
 ├── checks permission scope (read:email / send:email / write:email / delete:email)
 ├── fetches credential (gRPC vault-adapter :8084)
 │     └── auth_scheme: email_password | email_oauth2 | email_app_password
 ├── IMAP connection pool (per service, max 5 idle, 5-min TTL)
 └── SMTP per-operation connect
             │
             ▼
     upstream IMAP / SMTP server (imap_host / smtp_host from email_services row)
```

> **No host key required.** Unlike the SSH proxy, the email-proxy does not have a persistent
> host key. TLS to the upstream mail server uses the system trust store.

> **OAuth2 refresh path.** email-proxy NEVER holds the OAuth2 `client_secret`. When an
> access token is expired, it calls `POST /v1/internal/oauth2/{provider}/refresh` on the
> admin-api (service-token authenticated, `X-Mintkey-Service-Token` header). The admin-api
> performs the exchange and returns a new short-lived access token. The refresh token itself
> never travels over that path (NFR-17). See §6.5 below.

### 6.1 Adding an email service

Three auth schemes are supported:

| Scheme | When to use |
|---|---|
| `email_password` | Standard IMAP/SMTP with username + password |
| `email_oauth2` | Gmail or Outlook via OAuth2 (refresh token stored in vault) |
| `email_app_password` | Gmail 2-step verification app password |

**Via Admin UI:**

1. Services → New Email Service → choose provider template (`gmail-oauth2`, `outlook-oauth2`,
   or `imap-password`).
2. Fill **IMAP host** and **SMTP host** (e.g. `imap.gmail.com`, `smtp.gmail.com`).
   > Unlike HTTP services, email services have TWO endpoints (`imap_host` + `smtp_host`)
   > stored on the `email_services` row directly. `services.base_url` remains `NULL`
   > for email services (per ADR-0024 corrigendum §services.base_url divergence).
3. For `email_password` or `email_app_password`: Set Credential → paste username + password.
4. For `email_oauth2`: continue to §6.2 (OAuth2 flow).

**Via curl (email_password):**

```bash
# Step 1 — create the service
SVC=$(curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{
    "name":        "Corp IMAP",
    "slug":        "corp-imap",
    "display_name":"Corp Mail",
    "auth_scheme": "email_password",
    "email_service": {
      "provider":   "generic_imap",
      "imap_host":  "mail.corp.example.com",
      "imap_port":  993,
      "smtp_host":  "smtp.corp.example.com",
      "smtp_port":  587
    }
  }')
SID=$(echo "$SVC" | jq -r '.id')

# Step 2 — store the credential
curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SID/credentials" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{"auth_scheme":"email_password","value":{"username":"ops@corp.example.com","password":"PASS_HERE"}}' \
  | jq .
```

### 6.2 Registering Gmail/Outlook via OAuth2

The OAuth2 flow runs entirely in the Admin UI. The operator clicks **Authorize** and the
admin-api handles the token exchange server-side (the `client_secret` never leaves the
admin-api process, consistent with ADR-0020 / ADR-0024 §D7).

**Operator workflow:**

1. In Admin UI → Email Services → select the service → **Setup OAuth2** tab.
2. Click **Authorize with Google** (or **Authorize with Microsoft**).
   - admin-api generates a cryptographic `state` parameter (stored in `oauth2_state` table
     with a 10-minute TTL; opportunistic GC on expiry — migration 023).
   - Browser redirects to the provider's OAuth2 consent screen.
3. Complete consent in the provider's popup. Provider redirects back to
   `http://localhost:8080/v1/tenants/{tid}/oauth2/gmail/callback?code=...&state=...`.
   The `service_id` is **not** in the redirect URI — it is recovered from the `oauth2_state`
   row via the `state` parameter.  This means you only need to register **one** redirect URI
   per provider per tenant in GCP/Azure Console, regardless of how many email services you
   create for that provider.
4. admin-api validates `state`, performs the token exchange, stores the refresh token in the
   Vault Adapter via gRPC. The `email.oauth2.authorized` audit event is emitted.
5. The Admin UI displays **Connected** status.

**Before authorizing Gmail or Outlook**, an operator must first:

**Step A — Register the redirect URI in GCP/Azure Console (once per tenant per provider).**

For **Gmail**: in Google Cloud Console → APIs & Services → Credentials → your OAuth 2.0 Client ID
→ Authorized redirect URIs, add:

```
${MINTKEY_ADMIN_API_PUBLIC_URL}/v1/tenants/{tenant_id}/oauth2/gmail/callback
```

For local dev this is:
```
http://localhost:8080/v1/tenants/ce79c39d-33de-4689-b827-2e926cb5f2c7/oauth2/gmail/callback
```

You only need to register **one** URI per provider per tenant — creating additional Gmail
email services under the same tenant does **not** require revisiting GCP Console.

**Step B — Configure OAuth2 client credentials in Admin UI.**

1. Open Admin UI → **Email** → **OAuth2 Providers**.
2. Click **New** and fill in:
   - **Provider**: `gmail` or `outlook`
   - **Client ID**: your GCP or Azure OAuth2 client ID
   - **Client Secret**: your OAuth2 client secret (stored encrypted in vault; never shown again)
3. Click **Save**. The `configured_at` timestamp confirms the credentials are stored.
4. Then return to the Email Service and click **Authorize with Google** (or Microsoft).

Each tenant configures their **own** GCP project / Azure app — there is no shared client.

> **Deprecated (backwards compat only):** The following env vars are still honoured as a
> fallback for existing single-tenant deployments. Production deployments should migrate
> to per-tenant configuration via the Admin UI. A deprecation warning is logged on admin-api
> whenever the env-var fallback is used.
>
> ```bash
> # DEPRECATED — use Admin UI → Email → OAuth2 Providers instead
> MINTKEY_OAUTH2_GMAIL_CLIENT_ID=<your-google-client-id>
> MINTKEY_OAUTH2_GMAIL_CLIENT_SECRET=<your-google-client-secret>
> MINTKEY_OAUTH2_OUTLOOK_CLIENT_ID=<your-ms-client-id>
> MINTKEY_OAUTH2_OUTLOOK_CLIENT_SECRET=<your-ms-client-secret>
> ```

**Required env vars on email-proxy** (for the internal refresh call):

```bash
MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_ID=<service-identity-id>
MINTKEY_VAULT_EMAIL_PROXY_IDENTITY_TOKEN=<boot-secret>
```

These two env vars constitute the email-proxy's service identity for the internal
OAuth2 refresh endpoint (OQ-2 resolution, ADR-0024 corrigendum).

### 6.3 Granting agent permission

Email services use action-based scopes rather than a single `call` action. Grant the
appropriate scope(s) based on what the agent needs:

| Action / scope | Implemented tools |
|---|---|
| `read:email` | `email_list_mailboxes`, `email_search_messages`, `email_fetch_message`, `email_list_emails`, `email_download_attachment` |
| `send:email` | `email_send` |
| `write:email` | `email_move_email`, `email_mark_email` |
| `delete:email` | `email_delete_email` |

**Via Admin UI:** Permission Grants → New → select Agent, Service, and one of the four actions.

**Via curl:**

```bash
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/permissions" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d "{\"service_id\":\"$SID\",\"action\":\"read:email\"}" | jq .

# Grant send too (separate call — each action is a separate grant)
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/permissions" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d "{\"service_id\":\"$SID\",\"action\":\"send:email\"}" | jq .
```

### 6.4 Agent calling the email service (MCP tools)

Agents call email services through the MCP tools (see `agent-bootstrap.md`
`<email_services>` block for the full reference). All 9 tools are implemented. A typical flow:

**Step 1 — request a token with the required scope:**

```bash
TOKEN=$(curl -s -X POST http://localhost:8082/v1/tools/request_token \
  -H "Authorization: Bearer $AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\":\"$SID\",\"action\":\"send:email\"}" | jq -r '.token')
```

**Step 2 — call the MCP tool** (the MCP server routes to email-proxy internally):

```json
{
  "tool": "email_send",
  "arguments": {
    "email_service_id": "svc_01...",
    "to": ["alice@example.com"],
    "subject": "Hello from agent",
    "body": "This message was sent by an agent without holding any credentials."
  }
}
```

Expected response: `{"message_id": "<id>", "status": "sent"}`.

**All 9 email tools:**

| Tool | Scope | Description |
|---|---|---|
| `email_list_mailboxes` | `read:email` | List IMAP mailboxes for the service |
| `email_search_messages` | `read:email` | Search messages by RFC 3501 query string |
| `email_fetch_message` | `read:email` | Fetch full message envelope + body by UID |
| `email_list_emails` | `read:email` | Paginated UID listing (limit+offset, default 50, max 200) |
| `email_download_attachment` | `read:email` | Download MIME part by partID → base64 JSON |
| `email_send` | `send:email` | Send via SMTP |
| `email_move_email` | `write:email` | Move message to another mailbox (IMAP MOVE) |
| `email_mark_email` | `write:email` | Set/unset IMAP flags (\\Seen, \\Flagged, \\Answered) |
| `email_delete_email` | `delete:email` | Soft-delete (→ Trash) or hard-delete (?hard=true → EXPUNGE) |

**Parameter note:** all 9 tools accept `email_service_id` (canonical) or `service_id`
(alias, PR #155). Use `service_id` in new code for consistency with the rest of Mintkey.

> **Email body content is never stored by Mintkey.** The broker fetches the body from
> email-proxy on each `email_fetch_message` call. Mintkey only stores the credential
> (password or OAuth2 refresh token) and the service configuration.

### 6.5 Operational notes

**OAuth2 token refresh.** email-proxy calls the admin-api internal refresh endpoint when an
access token is expired:

```
POST /v1/internal/oauth2/{provider}/refresh
X-Mintkey-Service-Token: <boot-secret>
Query: service_id=<sid>&tenant_id=<tid>
Body: (empty)
```

The refresh token itself is fetched by the admin-api directly from vault-adapter via gRPC;
it never appears on the wire between email-proxy and admin-api (NFR-17). On failure
(`token_revoked` or persistent HTTP 400), the `email.service.auth_expired` audit event is
emitted and the service status transitions to `error`. Re-authorize via Admin UI to restore.

Concurrent refresh storms are prevented by a `singleflight` group keyed on
`(tenant_id, service_id)`.

**IMAP connection pool sizing.** Default pool size is 5 connections per `(tenant_id, service_id)`.
Idle timeout is 5 minutes. UIDVALIDITY is tracked per pool; a mismatch invalidates the pool
and forces a reconnect. Adjust pool sizing via:

```bash
MINTKEY_EMAIL_IMAP_POOL_SIZE=10       # max per service (default: 5)
MINTKEY_EMAIL_IMAP_IDLE_TIMEOUT=600   # seconds (default: 300)
```

**Rate limiting.** Rate limits are enforced per `(agent_id, service_id, hour)` via Postgres
advisory locks (shared across email-proxy instances). On `email.rate_limit.exceeded` the
proxy returns `429 Too Many Requests`. The limit is configured per permission grant
`constraints.rate_limit`.

**Domain filtering.** The `allowed_domains` list on an email service restricts outbound SMTP
recipients. Any `To`, `Cc`, or `Bcc` address not matching the allowlist is rejected with
`403 domain_not_allowed` and the `email.domain.blocked` audit event. Configure in Admin UI →
Email Services → Edit → Allowed Domains. An empty list means no domain filtering.

**TLS verification.** email-proxy verifies upstream TLS certificates using the system trust
store. Self-signed or expired certs on the upstream IMAP/SMTP server will cause connection
failure. To accept a custom CA, mount a PEM bundle and set:

```bash
MINTKEY_EMAIL_TLS_CA_BUNDLE=/etc/ssl/custom-ca.pem
```

**Audit trail.** All email operations emit audit events into the per-tenant hash chain
(same `auditq.Queue` as the HTTP proxy and SSH proxy). Query recent events:

```sql
SELECT event_type, payload->>'agent_id', payload->>'subject_truncated'
FROM audit_events
WHERE event_type LIKE 'email.%'
ORDER BY at DESC LIMIT 20;
```

13 event types are defined: `email.sent`, `email.received`, `email.deleted`, `email.moved`,
`email.searched`, `email.attachment.downloaded`, `email.service.registered`,
`email.service.auth_expired`, `email.rate_limit.exceeded`, `email.domain.blocked`,
`email.oauth2.refreshed`, `email.oauth2.expired`, `email.flags.updated`.

**Common confusions (FAQ):**

| Question | Answer |
|---|---|
| "Does the agent see the password / OAuth2 token?" | No. Only the vault holds it. The agent presents a JWT; email-proxy fetches the credential internally. |
| "Why does my OAuth2 service show `error` status?" | The refresh token was revoked by the provider. Re-authorize via Admin UI → Email Services → Setup OAuth2 → Re-authorize. |
| "Can I use the HTTP proxy (`:8000`) to call IMAP?" | No. IMAP is a stateful TCP protocol. Use the email-proxy REST endpoints on `:8088` via MCP tools. |
| "Does email-proxy need a host key like ssh-proxy?" | No. There is no persistent host key for email. TLS verification uses the system trust store. |
| "Where does attachment data go?" | Attachments are streamed through email-proxy on demand. They are not stored in Mintkey. |

---

## 7. Vault migration: SQLite → Postgres

> **When to run:** only when upgrading from a pre-2026-05-31 deployment where `MINTKEY_VAULT_BACKEND=sqlite` (or the env var was unset and the stack was running the SQLite-default build). New deployments use Postgres by default and can skip this section entirely.

### Pre-flight checklist

1. **`make backup`** — mandatory. This is your rollback point.
2. Confirm Postgres is healthy:
   ```bash
   docker exec mintkey-postgres-1 pg_isready -U mintkey_migrate -d mintkey
   ```
3. Confirm Liquibase has applied changelog `018-vault-schema`:
   ```bash
   docker exec mintkey-postgres-1 psql -U mintkey_migrate -d mintkey -c '\dt vault.*'
   ```
   Expected: one row — `vault | credentials | table | mintkey_migrate`.

### Run the migration

```bash
make migrate-vault-sqlite-to-pg
```

Expected output:
```
Read from sqlite: 138, Inserted: 138, Skipped (conflict): 0, Errors: 0
Sample verify (5): PASS
Postgres row count: 138 (matches sqlite)
```

### Restart vault-adapter on the new backend

```bash
docker compose up -d --no-deps --force-recreate vault-adapter
```

> Do **not** use `-f infra/compose/...` here — the root compose path reads the root `.env` which carries the correct `MINTKEY_VAULT_BACKEND=postgres` value.

### Verify the cutover

```bash
docker compose logs --tail=20 mintkey-vault-adapter-1 | grep -i "backend\|store"
```

Expected: `vault-adapter: store backend = postgres` (or `BACKEND=postgres` in env — visible via `docker inspect`).

### Rollback

If anything looks wrong before or after cutover:

```bash
MINTKEY_RESTORE_FORCE=1 make restore BACKUP_DIR=<your-pre-migration-backup>
```

This undoes everything — restores the Postgres DB, KEK volume, and bootstrap secrets from the backup created in step 1.

### Failure modes and remedies

| Symptom | Cause | Remedy |
|---|---|---|
| Migration reports `Errors > 0` | Rows with malformed `tenant_id` or `service_id` are skipped | Inspect the per-row error log printed to stdout; fix the SQLite rows if needed and re-run (idempotent) |
| `Sample verify (5): FAIL` | Blob corruption detected — plaintext round-trip mismatch | **STOP immediately.** Do not switch backends. Restore from backup. |
| Post-restart `GetCredential` returns wrong data | `MINTKEY_VAULT_BACKEND` not set to `postgres` in compose env; or RLS misconfiguration | Check `docker inspect mintkey-vault-adapter-1` env; confirm `mintkey_app` grants on `vault.credentials` (`\dp vault.credentials` in psql) |
| vault-adapter exits with DSN error | `MINTKEY_VAULT_PG_DSN` not set | Ensure `.env` has `MINTKEY_VAULT_PG_DSN=postgres://mintkey_migrate:<pass>@postgres:5432/mintkey` |

See [ADR-0021](architecture/01-architecture/adr/0021-vault-storage-backend-postgres.md) for the full decision rationale.

---

## 7. Operations

The proxy endpoint for all brokered calls is **`http://localhost:8000`** (env `MINTKEY_PROXY_URL`,
per [`docs/guides/github-quickstart.md`](guides/github-quickstart.md) lines 358–360 and the Ports
reference at lines 414–428). Do not use port `8087` — that is the vault-adapter HTTP port, not the
proxy.

If clients on other machines need to reach this Mintkey instance, set `MINTKEY_MCP_PUBLIC_URL` and
`MINTKEY_PROXY_PUBLIC_URL` — see [NETWORK.md](NETWORK.md).

| Task | Where to look |
|---|---|
| Rotate a credential | [`QUICKSTART.md`](../QUICKSTART.md) §8 and [`docs/architecture/03-flows/F-OP-03-register-credential-and-test.md`](architecture/03-flows/F-OP-03-register-credential-and-test.md) |
| Revoke an agent | [`docs/architecture/03-flows/F-OP-04-create-agent-and-permissions.md`](architecture/03-flows/F-OP-04-create-agent-and-permissions.md) |
| Inspect the audit log | `POST /v1/admin/audit/verify-chain` — see [`QUICKSTART.md`](../QUICKSTART.md) §9 "Troubleshooting" (note: requires `PlatformAdmin` role; pass `Authorization: Bearer <operator-session-token>`) |
| Read traces | `http://localhost:16686` (Jaeger) — see [`PORTS.md`](../PORTS.md) |
| Read dashboards | `http://localhost:3003` (Grafana) — see [`PORTS.md`](../PORTS.md) |
| Reset Grafana password | [`docs/guides/github-quickstart.md`](guides/github-quickstart.md) §9 |

---

## 8. Database schema changes

Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) first. The schema is owned by Liquibase per
[ADR-0015](architecture/01-architecture/adr/0015-liquibase-schema-source-of-truth.md); never edit
SQLAlchemy directly. If you are an operator and the change is to your deployment's schema, you
still go through Liquibase changelogs — add a new changeset, never edit an existing one.

---

## 9. Stack health checks

| Command | Expected outcome |
|---|---|
| `docker compose ps` | All 15 long-running services show `Up (healthy)`; `liquibase` and `seed-job` show `Exit 0` |
| `curl http://localhost:8080/v1/ready` | `200 OK` with `{"status": "ok"}` (reports failing dependencies on `503`) |
| `make test-arch` | Architecture invariants: RLS coverage, OpenAPI parity, SQLAlchemy mirror diff — all exit `0` |
| `make smoke` | E2E-01 happy path; completes in ≤ 90 s |
| `docker compose logs --tail=50 <svc>` | Recent logs for any service; replace `<svc>` with e.g. `mintkey-admin-api-1` |

---

## Connect a vanilla MCP client to Mintkey

To wire Claude Code (or Cursor, mcp-cli, etc.) at Mintkey:

1. Get an agent API key. In the admin UI (`http://<host>:8081`), create an Agent + grant it permission on one or more Services. The key is shown once — copy `mk_agent_<...>`.

2. Configure your MCP client. Point the server URL at:
   ```
   http://<MINTKEY_MCP_PUBLIC_URL>/mcp
   ```
   (For local dev: `http://localhost:8082/mcp`. For LAN: `http://10.243.1.200:8082/mcp`.)

3. Set the Authorization header to `Bearer mk_agent_<your-key>`.

4. The client will call `initialize` (unauthenticated), then `tools/list` and `tools/call` (authenticated). The six Mintkey tools (`mintkey_bootstrap`, `mintkey_list_services`, `mintkey_discover`, `mintkey_describe_service`, `mintkey_get_openapi`, `mintkey_request_token`) become available to the LLM.

5. Verify with curl:
   ```bash
   # Handshake (no auth needed)
   curl -X POST http://<host>:8082/mcp \
     -H 'Content-Type: application/json' \
     -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"manual","version":"0"}}}'

   # List available tools (auth required)
   curl -X POST http://<host>:8082/mcp \
     -H 'Content-Type: application/json' \
     -H 'Authorization: Bearer mk_agent_<your-key>' \
     -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
   ```

For the full agent onboarding markdown (which the `initialize` response also points at), GET `http://<host>:8082/v1/tools/bootstrap`.

See [AUTH.md](AUTH.md) for the full header reference and [NETWORK.md](NETWORK.md) for the discovery endpoint table.

---

## 10. Where else to look

| Need | Document |
|---|---|
| Layered troubleshooting (triage tree, per-service failure modes) | [`docs/DEBUG.md`](DEBUG.md) |
| Report a bug or file a feature request | [`docs/REPORTING.md`](REPORTING.md) |
| Report a security vulnerability | [`SECURITY.md`](../SECURITY.md) |

---

## 11. Operator cookbook — step-by-step recipes

Each recipe below is self-contained. Shared setup (session cookie, CSRF token, tenant ID)
is shown once in Recipe 0 and referenced in subsequent recipes. Use either the Admin UI
navigation or the curl path — they reach the same result.

### Recipe 0: open an operator session (curl prerequisite)

> Skip if you are using the Admin UI — sign in via Keycloak at `http://localhost:8081`.

```bash
# Enable break-glass path (only needed if Keycloak is unavailable)
docker compose exec admin-api python -m admin_api.cli admin reset-password \
  --email admin@mintkey.internal
# Prints: Temporary password: <TEMP_PASS>

# Log in
curl -s -X POST http://localhost:8080/v1/auth/internal-login \
  -H "Content-Type: application/json" \
  -c /tmp/mk_cookies.txt \
  -d '{"email":"admin@mintkey.internal","password":"TEMP_PASS"}' | jq .

# Capture CSRF token and tenant ID
CSRF=$(grep csrf_token /tmp/mk_cookies.txt | awk '{print $NF}')
TENANT_ID=$(curl -s http://localhost:8080/v1/tenants \
  -b /tmp/mk_cookies.txt -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" \
  | jq -r '.data[0].id')
echo "TENANT_ID: $TENANT_ID"

# When done, clear the break-glass hash
docker compose exec admin-api python -m admin_api.cli admin clear-password \
  --email admin@mintkey.internal
```

**What could go wrong:** `internal-login` returns 404 if Keycloak is healthy (break-glass
not enabled by default per ADR-0020). Run the `reset-password` command first.

---

### Recipe 1: add a service

**Via Admin UI:** Services → New → fill Name, Base URL, Auth scheme, Description →
optionally check "Add credential now?" → Create Service.

**Via curl:**

```bash
SVC=$(curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{
    "name":        "MyAPI",
    "slug":        "myapi",
    "display_name":"My API",
    "description": "Description of the service",
    "base_url":    "https://api.myservice.example.com",
    "auth_scheme": "bearer_token"
  }')
SID=$(echo "$SVC" | jq -r '.id')
echo "Service ID: $SID"
```

Expected: `{"id":"svc_01...","status":"active","slug":"myapi",...}`.

**What could go wrong:** 422 if `slug` is not unique within the tenant. Choose a
different slug or check for an existing service with the same slug.

#### Setting `openapi_url` to make the spec agent-discoverable

If the upstream service publishes an OpenAPI spec, set `openapi_url` at registration time (or update it later):

```bash
SVC=$(curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{
    "name":        "MyAPI",
    "slug":        "myapi",
    "base_url":    "https://api.myservice.example.com",
    "auth_scheme": "bearer_token",
    "openapi_url": "https://api.myservice.example.com/openapi.json"
  }')
```

Once set, agents see the spec in two ways:

- `mintkey_describe_service` returns `openapi.status: "available"` and `openapi_url` — agents can check before fetching.
- `mintkey_get_openapi` returns the registered URL (`kind: "url"`) or fetches the document inline (`kind: "inline"` when `inline=true`) with etag-conditional caching and a 1 MiB size cap.

**Via Admin UI:** Services → Edit → fill the `OpenAPI URL` field → Save.

If no `openapi_url` is set, `describe_service` reports `openapi.status: "not_registered"` and `get_openapi` returns `kind: "not_registered"` with a hint for the operator.

---

### Recipe 2: add a credential

```bash
curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SID/credentials" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{"auth_scheme":"bearer_token","value":"YOUR_TOKEN_HERE"}' | jq .
# Expected: {"id":"cred_01...","key_version":1,"status":"active"}
```

For API key header auth, also pass `"header_name": "X-Api-Key"`.

**Via Admin UI:** service show page → Set Credential → choose auth scheme → paste value → Save.

**What could go wrong:** 400 if `auth_scheme` does not match the service's registered
scheme. Ensure both use the same value (e.g. both `bearer_token`).

---

### Recipe 3: test a credential

Test the persisted credential without exposing the value:

```bash
curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SID/test" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{"method":"GET","path":"/health","timeout_ms":5000}' | jq .
# Expected: {"ok":true,"status_code":200,"latency_ms":42,...}
```

For a transient test (without saving first), use `/test-transient` — see
[`docs/guides/github-quickstart.md`](guides/github-quickstart.md) §3 for the full shape.

**Via Admin UI:** service show page → Test Connection button.

**What could go wrong:** `{"ok":false,"status_code":401}` means the credential is
invalid or has insufficient scope. Update the credential (Recipe 8) and re-test.

---

### Recipe 4: create an agent

```bash
AGENT=$(curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/agents" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{"name":"my-agent","description":"Purpose of this agent","rate_limit_rps":10}')
AGENT_ID=$(echo "$AGENT" | jq -r '.id')
AGENT_KEY=$(echo "$AGENT" | jq -r '.api_key')
echo "Agent key (copy now — shown once): $AGENT_KEY"
```

> **The API key is shown once.** Copy `mk_agent_...` immediately. It cannot be
> retrieved again; if lost, rotate the key (not shown here — use Admin UI → Agent
> show page → Rotate Key).

**Via Admin UI:** Agents → New → fill Name + Rate limit → Create → copy the key from
the success screen.

**What could go wrong:** 422 if `name` is not unique within the tenant.

---

### Recipe 5: grant permission

```bash
GRANT=$(curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/permissions" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d "{\"service_id\":\"$SID\",\"action\":\"call\"}")
echo "$GRANT" | jq '{id: .id, action: .action}'
# Expected: {"id":"perm_01...","action":"call"}
```

**Via Admin UI:** Permission Grants → New → select Agent, Service, Action → Create.

**What could go wrong:** 404 if `service_id` or `agent_id` is not found. Use `svc_...`
wire IDs (returned by list_services) or raw UUIDs — both are accepted.

---

### Recipe 6: request a token (agent-side)

```bash
AGENT_KEY="mk_agent_PASTE_YOUR_KEY_HERE"

TOKEN=$(curl -s -X POST http://localhost:8082/v1/tools/request_token \
  -H "Authorization: Bearer $AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\":\"$SID\",\"action\":\"call\"}" | jq -r '.token')
echo "Token (first 40): ${TOKEN:0:40}..."
```

The token is a JWS-Ed25519 JWT with a 10-minute TTL. Refresh before expiry
by calling `request_token` again.

**What could go wrong:** 403 with `permission_not_found` means no active grant exists
for this agent + service + action. Create a grant (Recipe 5) first.

---

### Recipe 7: call a service through the proxy

```bash
# URL pattern: http://localhost:8000/v1/call/<service_id>/<upstream_path>
curl -s "http://localhost:8000/v1/call/$SID/health" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

The proxy validates the JWT, fetches the credential from vault, injects it into the
upstream request, and returns the upstream response. Your agent never sees the raw
credential value.

**What could go wrong:**
- `401` → token expired; call `request_token` again.
- `403 permission_not_found` → no active grant; create one (Recipe 5).
- `404` from Kong → route not synced yet; wait 30 s and check
  `docker compose logs mintkey-kong-syncer-1 | grep routes_published`.
- `502` → vault lookup failed; check `docker compose logs mintkey-vault-adapter-1`.

---

### Recipe 8: rotate a credential

Rotation stores a new credential version. The old version is invalidated after the
key-version overlap window.

**Via Admin UI:** service show page → Credentials → Rotate → paste new value → Save.

**Via curl:**

```bash
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SID/credentials/rotate" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{"auth_scheme":"bearer_token","value":"NEW_TOKEN_HERE"}' | jq .
# Expected: {"id":"cred_01...","key_version":2,"status":"active"}
```

After rotation, test the new credential (Recipe 3) before discarding the old one.

**What could go wrong:** 400 if `auth_scheme` doesn't match the service's registered
scheme. Use the same scheme that was stored originally.

---

### Recipe 9: revoke an agent

Revoking an agent immediately invalidates all its in-flight requests after the current
request completes (ADR-0016). Tokens already issued will fail on the next proxy call.

**Via Admin UI:** Agents → select agent → Revoke.

**Via curl:**

```bash
curl -s -X DELETE \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID" \
  -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" \
  -b /tmp/mk_cookies.txt
# Expected: 204 No Content
```

**What could go wrong:** 404 if the agent ID is wrong. Use `jq -r '.id'` from the
agent creation response, or list agents in Admin UI → Agents.

---

### Recipe 10: inspect the audit trail

All Mintkey operations emit cryptographically chained audit events. The chain is
verifiable: each event includes a hash of the previous event.

**Via Admin UI:** Audit Events → filter by time, agent, or service.

**Via curl (chain verification):**

```bash
curl -s -X POST "http://localhost:8080/v1/admin/audit/verify-chain" \
  -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" \
  -b /tmp/mk_cookies.txt | jq '{ok: .ok, events_verified: .count}'
# Expected: {"ok":true,"events_verified":N}
```

**What could go wrong:** `{"ok":false}` indicates a chain integrity violation — this
should not happen in a normal stack. Capture the full response and report it as a
security incident.

---

### Recipe 11: inspect a trace

Jaeger collects distributed traces for all Mintkey requests. Access requires Keycloak
sign-in (oauth2-proxy protects Jaeger).

1. Open `http://localhost:16686` → sign in with Keycloak credentials
2. In **Service** dropdown, select `admin-api` or `mcp-server`
3. Click **Find Traces** → click any trace to expand the call chain

**Via curl (Jaeger API — no auth required on localhost):**

```bash
# List recent traces for admin-api
curl -s "http://localhost:16686/api/traces?service=admin-api&limit=5" \
  | jq '[.data[].traceID]'
```

**What could go wrong:** Jaeger UI shows "No traces found" if the stack was just
started and no requests have been made yet. Make any API call and refresh.
If you get a 401, ensure you are signed in to Keycloak at `http://localhost:8081` first
(the oauth2-proxy session is shared).

---

## 12. Agent-stored secrets

Agents can store small named secrets (API keys, tokens, passwords — up to 64 KiB) inside
Mintkey's vault without ever exposing them in logs, audit payloads, or span attributes.
The architecture decision is [ADR-0025](architecture/01-architecture/adr/0025-agent-stored-secrets.md).

### What it is

- Each secret is scoped to `(tenant, owning agent, name)`.
- Values are envelope-encrypted (AES-256-GCM DEK wrapped by the vault KEK) before reaching storage.
- Agents access secrets via four MCP tools on the MCP server (`:8082`).
- Operators manage metadata and share grants via the admin-api REST surface (`:8080`).
- **Plaintext read-back caveat:** unlike service credentials (which the vault holds and the
  egress proxy injects without the agent ever seeing them), agent-stored secrets ARE returned
  to the owning agent in plaintext by `secret_get`. This is intentional — agents store and
  retrieve their own secrets — but it means the agent must handle the plaintext value
  responsibly. See ADR-0025 §Security deviation for the full rationale.

### The four MCP tools

All calls require an `Authorization: Bearer <mk_agent_KEY>` header against `http://localhost:8082`.

#### `secret_put` — store or overwrite

```bash
curl -s -X POST http://localhost:8082/v1/tools/secret_put \
  -H "Authorization: Bearer $MK_AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name": "my-db-password", "value": "s3cr3t", "content_type": "text/plain"}'
```

Response: `{"secret_id": "sec_...", "name": "my-db-password", "version": 1}`

- `name` must match `^[a-zA-Z0-9._-]{1,128}$`
- `value` is UTF-8 plaintext, maximum 65536 bytes
- Storing to an existing `name` overwrites and increments `version`
- Emits `agent_secret.created` (or `.updated`) audit event — identifier-only payload

#### `secret_get` — read plaintext

```bash
curl -s "http://localhost:8082/v1/tools/secret_get?secret_id=sec_..." \
  -H "Authorization: Bearer $MK_AGENT_KEY"
```

Response: `{"secret_id": "sec_...", "name": "my-db-password", "version": 1, "value": "s3cr3t", "access": "owner"}`

- Only the owning agent or a recipient with a share grant may call this.
- `access` is `"owner"` or `"shared"`.
- Emits `agent_secret.read` audit event — identifier-only payload, value never logged.

#### `secret_list` — list metadata

```bash
curl -s "http://localhost:8082/v1/tools/secret_list" \
  -H "Authorization: Bearer $MK_AGENT_KEY"
```

Response: `{"secrets": [{...metadata only, no value...}], "next_cursor": null}`

- Returns all owned and shared secrets with `access` flag (`"owner"` or `"shared"`).
- Values are never returned. Pagination via `?after=sec_...&limit=50`.

#### `secret_delete` — delete (owner only)

```bash
curl -s -X DELETE "http://localhost:8082/v1/tools/secret_delete?secret_id=sec_..." \
  -H "Authorization: Bearer $MK_AGENT_KEY"
```

Response: `{}` (200 — idempotent)

- Only the owning agent may delete.
- Cascades all share grants. Emits `agent_secret.deleted` audit event.

### Operator share grants

Operators control which other agents may read an agent's secret.

```bash
# Grant agent B read access to agent A's secret
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agent-secrets/$SECRET_ID/grants" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -b /tmp/mk_cookies.txt \
  -d '{"recipient_agent_id": "agent_..."}'
# → 201 {"id": "secgrant_...", ...}

# List grants
curl -s "http://localhost:8080/v1/tenants/$TENANT_ID/agent-secrets/$SECRET_ID/grants" \
  -b /tmp/mk_cookies.txt
# → 200 {"data": [...], "next_cursor": null}

# Revoke a grant (idempotent)
curl -s -X DELETE \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agent-secrets/$SECRET_ID/grants/$GRANT_ID" \
  -H "X-Mintkey-Csrf: $CSRF" -b /tmp/mk_cookies.txt
# → 204

# Operator hard-delete a secret (removes ciphertext + all grants)
curl -s -X DELETE \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agent-secrets/$SECRET_ID" \
  -H "X-Mintkey-Csrf: $CSRF" -b /tmp/mk_cookies.txt
# → 204
```

**Constraints:**
- Secret and recipient agent must both exist in the operator's tenant (cross-tenant references → 422).
- Granting to the secret's own owner → 422 `grant_to_owner`.
- Duplicate grant → 409 `already_exists`.
- Operator metadata endpoints (`GET /agent-secrets`, `GET /agent-secrets/{id}`) return metadata only — no value, no ciphertext.

### Audit events emitted

| Event type | When | Payload keys |
|---|---|---|
| `agent_secret.created` | First `secret_put` for a name | `secret_id`, `agent_id`, `name`, `version` |
| `agent_secret.updated` | Overwrite via `secret_put` | same + `previous_version` |
| `agent_secret.read` | Successful `secret_get` | `secret_id`, `version`, `reader_agent_id`, `access` |
| `agent_secret.deleted` | `secret_delete` (agent or operator) | `secret_id`, `agent_id`, `name` |
| `agent_secret_grant.created` | Operator `POST .../grants` | `grant_id`, `secret_id`, `owner_agent_id`, `recipient_agent_id` |
| `agent_secret_grant.revoked` | Operator `DELETE .../grants/{id}` | same |

All payloads carry **identifiers only** — the plaintext value never appears in any audit row.

---

## 13. MongoDB Atlas Administration API

Mintkey can broker the **MongoDB Atlas Administration API**
(`https://cloud.mongodb.com/api/atlas/v2`) so agents perform Atlas administrative operations —
create/scale clusters, manage projects, database users, network access, backups, alerts — without
ever holding the Atlas credential. The architecture decision is
[ADR-0029](architecture/01-architecture/adr/0029-mongodb-atlas-admin-api-support.md), which records the two new
auth schemes and the read-scoped method-gating semantic.

> **Control-plane only — reading collection documents is out of scope.** The Atlas Administration
> API manages Atlas resources; it **cannot read documents from your collections**. The former Atlas
> Data API (HTTP document access) has been **retired** by MongoDB, and reading collection data
> requires the MongoDB wire protocol, which Mintkey's HTTP proxy does not speak. Mintkey brokers
> Atlas *administration* only — there is no data-plane / document-read path.

### 13.1 Two ways to register — pick your credential type

Atlas authenticates via exactly two schemes, and Mintkey ships a template for each:

| Template | Auth scheme | Credential you supply | When to use |
|---|---|---|---|
| `mongodb-atlas-service-account` | `oauth2_client_credentials` | `client_id` + `client_secret` | Atlas **Service Account** (OAuth2 client-credentials; the proxy exchanges the pair for a 1-hour Bearer token and refreshes it automatically) |
| `mongodb-atlas-api-key` | `http_digest` | `public_key` + `private_key` | Atlas **Programmatic API Key** (HTTP Digest challenge-response; the proxy performs the RFC 2617 handshake per request) |

Both templates create a service with `base_url: https://cloud.mongodb.com/api/atlas/v2`,
`test_path: /groups`, and the Atlas v2 OpenAPI spec URL. In either case the agent never sees the
credential — the proxy injects it in-flight.

**Via Admin UI:** Services → New → **From Template** → choose **MongoDB Atlas (Service Account)** or
**MongoDB Atlas (Programmatic API Key)** → supply the credential fields → Create.

**Via curl (Service Account):**

```bash
# Step 1 — create the service from the template's shape
SVC=$(curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{
    "name":        "Atlas Admin (Service Account)",
    "slug":        "atlas-admin-sa",
    "display_name":"MongoDB Atlas Administration API",
    "auth_scheme": "oauth2_client_credentials",
    "base_url":    "https://cloud.mongodb.com/api/atlas/v2"
  }')
SID=$(echo "$SVC" | jq -r '.id')

# Step 2 — store the credential (client_id/client_secret; never echoed back)
curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SID/credentials" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d '{
    "auth_scheme": "oauth2_client_credentials",
    "value": {
      "token_url":           "https://cloud.mongodb.com/api/oauth/token",
      "client_id":           "CLIENT_ID_HERE",
      "client_secret":       "CLIENT_SECRET_HERE",
      "token_response_path": "$.access_token"
    }
  }' | jq .
```

**Via curl (Programmatic API Key):** identical, but with `"auth_scheme": "http_digest"` and a
credential value of `{"public_key": "PUBLIC_KEY_HERE", "private_key": "PRIVATE_KEY_HERE"}`.

### 13.2 REQUIRED: the agent must send the dated Atlas version header

Atlas v2 **requires** a dated `Accept` version header on **every** request:

```
Accept: application/vnd.atlas.<yyyy-mm-dd>+json      # e.g. application/vnd.atlas.2025-03-12+json
```

**Without it, Atlas returns `406 Not Acceptable`.** Mintkey forwards your request headers to MongoDB
**unchanged** — it strips/replaces only `Authorization` and `X-Mintkey-*`, and it does **not** add
the version header for you. The agent must set `Accept` itself on the proxy call. Both templates
carry this instruction verbatim in the service `description` (surfaced to agents via
`list_services` / `describe_service`) and in operator `config_notes`.

### 13.3 Grant the agent `read:atlas` and/or `admin:atlas`

Two actions bound what an agent can do. Grant either, both, or neither per agent:

| Action / scope | HTTP methods allowed at the proxy | Use for |
|---|---|---|
| `read:atlas` | `GET`, `HEAD`, `OPTIONS` only (any other method → `403`) | Read-only inventory: list projects, clusters, DB users, alerts |
| `admin:atlas` | all methods (`POST`, `PATCH`, `DELETE`, …) | Full administration: create/scale/delete clusters, manage users |

The proxy enforces the `read:atlas` method gate from the JWT `scope`; a `read:atlas` token that
attempts a `DELETE` is rejected with `403` before the upstream is contacted. `admin:atlas` and all
pre-existing actions (`call`, the email scopes, …) are unaffected. Full power is still additionally
bounded by the Service Account's / API Key's own roles on MongoDB's side.

**Via Admin UI:** Permission Grants → New → select Agent, Service, and `read:atlas` or `admin:atlas`.

**Via curl:**

```bash
# Read-only grant
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/permissions" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d "{\"service_id\":\"$SID\",\"action\":\"read:atlas\"}" | jq .

# Full-admin grant (separate call — each action is a separate grant)
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/permissions" \
  -H "Content-Type: application/json" -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt \
  -d "{\"service_id\":\"$SID\",\"action\":\"admin:atlas\"}" | jq .
```

### 13.4 Agent calling Atlas through the proxy

```bash
# Step 1 — request a token with the granted action
TOKEN=$(curl -s -X POST http://localhost:8082/v1/tools/request_token \
  -H "Authorization: Bearer $AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\":\"$SID\",\"action\":\"read:atlas\"}" | jq -r '.token')

# Step 2 — call the Atlas API through the proxy, sending the dated Accept header yourself.
# URL pattern: http://localhost:8000/v1/call/<service_id>/<atlas_path>
curl -s "http://localhost:8000/v1/call/$SID/groups" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Accept: application/vnd.atlas.2025-03-12+json" | jq .
```

The proxy injects the Atlas credential (exchanged Bearer token for a Service Account, Digest
challenge-response for an API Key) and forwards your `Accept` header unchanged. Your agent never
sees the raw credential value.

**What could go wrong:**
- `406 Not Acceptable` → you omitted (or misspelled) the dated `Accept: application/vnd.atlas.<date>+json` header. Mintkey does not add it for you (§13.2).
- `403 forbidden: read:atlas grants read-only access` → a `read:atlas` token attempted a write method; request an `admin:atlas` token instead (and hold the matching grant).
- `403 permission_not_found` → no active grant for this agent + service + action; create one (§13.3).
- `401` → token expired; call `request_token` again.

---
