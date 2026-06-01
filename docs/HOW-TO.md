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
  └── dials upstream SSH server (target_address from vault row)
             │
             ▼
     upstream SSH server (any host:port)
```

### One-time setup

| Step | Command | Notes |
|---|---|---|
| Seed bastion host key | `make ssh-proxy-init` | Idempotent; seeds Ed25519 host key into `mintkey_ssh_proxy_hostkey` volume. Run before `make dev` the first time. |
| Start the stack | `make dev` | Binds `:2222` on all host interfaces. In production, restrict to a specific interface behind a firewall. |

### Adding an SSH service via the Admin UI

1. **Services → New → From Template**: choose `ssh-bastion-key` (private-key auth) or
   `ssh-bastion-password` (username + password).
2. Replace the placeholder base URL `ssh://CHANGE-ME:22` with your real target, e.g.
   `ssh://internal-server.corp:22`.
3. Open the service → **Set Credential**:
   - For `ssh-bastion-key`: paste the private key (PEM/OpenSSH) in the text area, set `ssh_user` and `target_address` (host:port).
   - For `ssh-bastion-password`: set `ssh_user`, `ssh_password`, and `target_address`.
4. **Permission Grants → New**: grant the relevant agent `call` on this service.

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

## 6. Vault migration: SQLite → Postgres

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
