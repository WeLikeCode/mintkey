# 10-Minute Mintkey Demo (mock backend only)

> **No external API keys required.** This demo uses Mintkey's built-in
> mock backend service. You'll see an agent successfully request a
> brokered token and call the mock API through Mintkey's proxy — all
> running on your laptop.

> **Pre-alpha.** Mintkey is under active development. This demo
> exercises a stable subset of the stack; production use is not
> supported.

---

## What you'll do

1. Clone and start the stack
2. Get the bootstrap admin password
3. Sign in to the Admin UI via Keycloak
4. Register the mock-backend service
5. Create a demo agent and permission grant
6. Use the agent's API key to request a brokered token and call the mock backend
7. Inspect the audit trail
8. Inspect a trace in Jaeger
9. Clean up (optional)

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker Desktop or Docker Engine + Compose v2 | `docker compose version` must show v2.x |
| 4 GB free RAM | The stack runs 17 containers |
| ~5 GB free disk | Images + volumes |
| `curl` and `jq` | For the CLI walkthrough; Admin UI steps need only a browser |

---

## Step 1: Clone and start

```bash
git clone https://github.com/WeLikeCode/mintkey.git mintkey
cd mintkey
docker compose up -d
```

Expected output (abridged):

```
 Container mintkey-postgres-1        Healthy
 Container mintkey-keycloak-1        Healthy
 Container mintkey-admin-api-1       Healthy
 Container mintkey-mcp-server-1      Healthy
 Container mintkey-mock-backend-1    Healthy
```

Wait until `docker compose ps` shows all long-running services as `Up (healthy)`. The
one-shot jobs (`liquibase`, `seed-job`) should show `Exit 0`. This takes about 60–90 s
on first run (images must be pulled).

```bash
# Confirm the mock backend container is responding
curl http://localhost:8999/health
# Expected: {"status":"ok"}
```

**What could go wrong:** If any service shows `Restarting`, run
`docker compose logs <service-name> --tail 30` to find the cause. Common issues:
port conflicts (8080, 8081, 8082, 8000, 8999 must be free) and insufficient RAM.

---

## Step 2: Get the bootstrap admin password

The seed job writes the admin password to a Docker volume during first start.

```bash
docker run --rm -v mintkey_bootstrap_secrets:/secrets alpine \
  cat /secrets/admin_password
```

Copy the password — you need it in Step 3. The email is always `admin@mintkey.internal`.

**Fallback (if the volume read fails):**

```bash
docker compose logs mintkey-seed-job-1 | grep "Bootstrap admin password"
```

---

## Step 3: Sign in to the Admin UI

1. Open `http://localhost:8081` in your browser.
2. Click **Sign in with Keycloak**.
3. Enter `admin@mintkey.internal` and the password from Step 2.
4. You are redirected to the Mintkey dashboard.

> If the Keycloak login page shows a certificate error, you may need to
> accept the self-signed cert for `localhost:8443`. Click "Advanced" →
> "Proceed" in your browser.

---

## Step 4: Register the mock-backend service

The `mock-backend` container runs at `http://mock-backend:8999` on the Docker network.
It exposes several endpoints that exercise different auth schemes (bearer, API key header,
echo, etc.) — no real credentials or external accounts needed.

### Via Admin UI (recommended for first-time users)

1. Navigate to **Admin UI → Services** (`http://localhost:8081/admin/resources/services`)
2. Click **New** (top right)
3. Fill in the form:
   - **Name:** `mock-backend`
   - **Slug:** `mock-backend`
   - **Display name:** `Mintkey Mock Backend`
   - **Base URL:** `http://mock-backend:8999`
   - **Auth scheme:** `api_key_header`
   - **Description:** `Built-in demo service — no external keys required`
4. Check **Add a credential now?**, set:
   - **Header name:** `X-Api-Key`
   - **Value:** `canary-demo-api-key`
5. Click **Create Service**

Expected: success banner with **View service** link. Status shown as `active`.

### Via curl (automation path)

```bash
# 1. Log in and capture session
curl -s -X POST http://localhost:8080/v1/auth/internal-login \
  -H "Content-Type: application/json" \
  -c /tmp/mk_cookies.txt \
  -d '{"email":"admin@mintkey.internal","password":"PASTE_PASSWORD_HERE"}' | jq .

CSRF=$(grep csrf_token /tmp/mk_cookies.txt | awk '{print $NF}')
TENANT_ID=$(curl -s http://localhost:8080/v1/tenants \
  -b /tmp/mk_cookies.txt -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" \
  | jq -r '.data[0].id')

# 2. Register the service
SVC=$(curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" \
  -b /tmp/mk_cookies.txt \
  -d '{
    "name": "mock-backend", "slug": "mock-backend",
    "display_name": "Mintkey Mock Backend",
    "description": "Built-in demo service — no external keys required",
    "base_url": "http://mock-backend:8999",
    "auth_scheme": "api_key_header"
  }')
SID=$(echo "$SVC" | jq -r '.id')
echo "Service ID: $SID"

# 3. Store the demo credential
curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SID/credentials" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" \
  -b /tmp/mk_cookies.txt \
  -d '{"auth_scheme":"api_key_header","header_name":"X-Api-Key","value":"canary-demo-api-key"}' | jq .
```

> **Note:** `http://mock-backend:8999` is a Docker-network-internal URL. The browser
> and external agents should never try to reach that address directly — they use the
> proxy at `http://localhost:8000` instead. The broker resolves the service base URL
> internally at request time.

**What could go wrong:** If `internal-login` returns 404, Keycloak is reachable and
the break-glass path is not enabled. Run:
```bash
docker compose exec admin-api python -m admin_api.cli admin reset-password --email admin@mintkey.internal
```
Use the printed temporary password for `internal-login`, then clear it afterward:
```bash
docker compose exec admin-api python -m admin_api.cli admin clear-password --email admin@mintkey.internal
```

---

## Step 5: Create a demo agent

### Via Admin UI

1. **Admin UI → Agents → New**
2. Set **Name:** `Demo-Agent`, **Rate limit rps:** `10`
3. Click **Create Agent**
4. On the success screen: copy the `mk_agent_...` API key immediately — it is shown **once only**

### Via curl

```bash
AGENT=$(curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/agents" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" \
  -b /tmp/mk_cookies.txt \
  -d '{"name":"Demo-Agent","description":"10-min demo agent","rate_limit_rps":10}')

AGENT_ID=$(echo "$AGENT" | jq -r '.id')
AGENT_KEY=$(echo "$AGENT" | jq -r '.api_key')
echo "Agent ID:  $AGENT_ID"
echo "Agent key: $AGENT_KEY"   # copy this — shown once
```

---

## Step 6: Grant permission to call mock-backend

### Via Admin UI

1. **Admin UI → Permission Grants → New**
2. Select **Agent:** `Demo-Agent`, **Service:** `mock-backend`, **Action:** `call`
3. Click **Create**

### Via curl

```bash
curl -s -X POST "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/permissions" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" \
  -b /tmp/mk_cookies.txt \
  -d "{\"service_id\":\"$SID\",\"action\":\"call\"}" | jq .
# Expected: {"id":"perm_...","action":"call","status":"active"}
```

---

## Step 7: Call the mock backend through the broker

```bash
# 7a. Set your agent key (from Step 5)
AGENT_KEY="mk_agent_PASTE_YOUR_KEY_HERE"
SID="svc_PASTE_YOUR_SERVICE_ID_HERE"   # or use jq to extract from Step 4

# 7b. Request a short-lived brokered token (10-minute TTL)
TOKEN=$(curl -s -X POST http://localhost:8082/v1/tools/request_token \
  -H "Authorization: Bearer $AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\":\"$SID\",\"action\":\"call\"}" \
  | jq -r '.token')

echo "Token (first 40 chars): ${TOKEN:0:40}..."
```

Expected response (before extracting token):

```json
{
  "token": "eyJhbGci....",
  "expires_at": 1778924958,
  "service_id": "svc_01KRR2EF7G27CT840XW10FXFRX"
}
```

```bash
# 7c. Call the mock backend through the Mintkey egress proxy
#     URL pattern: http://localhost:8000/v1/call/<service_id>/<upstream_path>
curl -s "http://localhost:8000/v1/call/$SID/health" \
  -H "Authorization: Bearer $TOKEN"
# Expected: {"status":"ok"}

# 7d. Call the echo endpoint (shows injected headers)
curl -s -X POST "http://localhost:8000/v1/call/$SID/echo" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"hello":"mintkey"}' | jq '{injected_key: .headers["x-api-key"], body: .body}'
# Expected: {"injected_key":"canary-demo-api-key","body":{"hello":"mintkey"}}
```

The proxy:
1. Validated your JWT (Ed25519 signature from broker, 10-minute TTL)
2. Fetched the `canary-demo-api-key` from the vault adapter
3. Stripped your JWT, injected `X-Api-Key: canary-demo-api-key`
4. Forwarded the request to `http://mock-backend:8999/echo`

Your agent never saw the stored credential value.

**What could go wrong:**

| Symptom | Cause | Fix |
|---|---|---|
| `401` on `request_token` | Wrong or expired agent key | Re-check key from Step 5; keys are one-time display |
| `403 permission_not_found` | Grant not created or wrong service_id | Re-run Step 6; confirm `$SID` matches |
| `404` from proxy | Kong routes not synced yet | Wait 30 s; check `docker compose logs mintkey-kong-syncer-1 \| grep routes_published` |
| `502` from proxy | Credential not stored or vault unreachable | Verify Step 4 credential save; check `docker compose logs mintkey-vault-adapter-1` |

---

## Step 8: Inspect the audit trail

All Mintkey operations emit cryptographically chained audit events.

### Via Admin UI

1. Navigate to **Admin UI → Audit Events**
2. Filter by time (last 5 minutes) to see the `token.issued` and `proxy.call` events from this demo

### Via curl

```bash
# The audit verify-chain endpoint requires a platform-admin session
curl -s -X POST "http://localhost:8080/v1/admin/audit/verify-chain" \
  -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" \
  -b /tmp/mk_cookies.txt | jq '{chain_valid: .ok, events_verified: .count}'
```

Expected: `{"chain_valid": true, "events_verified": <N>}`. The count grows with each demo step.

---

## Step 9: Inspect a trace in Jaeger

Jaeger is protected by Keycloak via oauth2-proxy. Sign in with the same
`admin@mintkey.internal` credentials.

1. Open `http://localhost:16686` — you will be redirected to Keycloak login
2. Sign in with `admin@mintkey.internal` + your bootstrap password
3. In the **Service** dropdown, select `admin-api` or `mcp-server`
4. Click **Find Traces**
5. Click any trace to see the full call chain: MCP server → broker → vault adapter → proxy

The trace shows the latency breakdown for each hop and confirms that the real credential
was fetched from vault at proxy time (look for the `vault-adapter` span).

---

## Cleanup (optional)

To delete the demo agent and service when you're done:

```bash
# Revoke the demo agent
curl -s -X DELETE "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID" \
  -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt

# Delete the mock-backend service (removes credential from vault too)
curl -s -X DELETE "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SID" \
  -H "X-Mintkey-Csrf: $CSRF" -H "X-Platform-Admin: true" -b /tmp/mk_cookies.txt
```

To stop the stack without destroying data:

```bash
docker compose stop       # containers stop; volumes preserved
docker compose start      # resume where you left off
```

To tear everything down (data lost):

```bash
docker compose down -v    # WARNING: deletes all volumes including vault data; back up first with bash scripts/dev-backup.sh — see team/remediation/HOWTO-backup-before-reset.md (EV-DESTRUCTIVE-009)
```

---

## What just happened (architecture in 1 paragraph)

Mintkey acted as a credential broker between your agent and the mock backend. Your
agent presented an API key (`mk_agent_...`) to the MCP server, which issued a
short-lived JWT signed by the broker's Ed25519 key. When you called the egress proxy
(Kong + proxy-plugin), Mintkey validated the JWT, looked up the real credential
(`canary-demo-api-key`) from the encrypted vault adapter, and injected it into the
upstream request — all without your agent ever seeing the stored value. Every step
emitted an audit event to a cryptographically chained log. The mock backend received
a correctly authenticated request and your agent received the response, with Mintkey
as the invisible credential intermediary.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `docker compose up` hangs | Image pull slow or port conflict | Check `docker compose logs`; ensure ports 8000, 8080, 8081, 8082, 8999 are free |
| Keycloak login page not loading | keycloak container not healthy | `docker compose logs mintkey-keycloak-1 --tail 30` |
| `internal-login` returns 404 | Keycloak is up; break-glass not enabled | Run `admin reset-password` CLI (see Step 4 note) |
| Seed job shows `Exit 1` | Liquibase failed | `docker compose logs mintkey-liquibase-1`; often a stale volume — back up first with `bash scripts/dev-backup.sh` (see HOWTO-backup-before-reset.md, EV-DESTRUCTIVE-010), then `docker compose down && docker volume rm mintkey_postgres_data` (data loss!) |
| `request_token` returns 403 | Permission grant missing | Verify Step 6; check `$SID` matches the registered service |
| Proxy returns 404 | Kong route not synced | Wait 30 s; `docker compose logs mintkey-kong-syncer-1 | grep routes_published` |
| Echo endpoint shows `"x-api-key": null` | Credential not stored properly | Re-run credential save in Step 4; check vault-adapter logs |

---

## Next steps

- Try the GitHub PAT walkthrough: [`docs/guides/github-quickstart.md`](github-quickstart.md)
- Connect an MCP client: [`docs/guides/mcp-clients/`](mcp-clients/)
  - [Claude Desktop](mcp-clients/claude-desktop.md)
  - [Claude Code](mcp-clients/claude-code.md)
  - [Cursor](mcp-clients/cursor.md)
  - [mcp-cli](mcp-clients/mcp-cli.md)
- Read the security model: [`docs/AUTH.md`](../AUTH.md), [`SECURITY.md`](../../SECURITY.md)
- Deployment posture: [`docs/DEPLOYMENT.md`](../DEPLOYMENT.md)
- Operator cookbook: [`docs/HOW-TO.md`](../HOW-TO.md)
