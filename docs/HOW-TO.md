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
| 1. Bring the stack up | `docker compose up -d` — 15 long-running containers + 2 one-shot jobs | [`QUICKSTART.md`](../QUICKSTART.md) §1 |
| 2. Get the bootstrap admin password | Printed once to stdout; also at `./data/bootstrap-secrets/` (mode `0400`) | [`docs/guides/github-quickstart.md`](guides/github-quickstart.md) §0 |
| 3. Open the Admin UI | `http://localhost:8081` | [`PORTS.md`](../PORTS.md) "Quick access" |

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

## 4. Operations

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

## 5. Database schema changes

Read [`CONTRIBUTING.md`](../CONTRIBUTING.md) first. The schema is owned by Liquibase per
[ADR-0015](architecture/01-architecture/adr/0015-liquibase-schema-source-of-truth.md); never edit
SQLAlchemy directly. If you are an operator and the change is to your deployment's schema, you
still go through Liquibase changelogs — add a new changeset, never edit an existing one.

---

## 6. Stack health checks

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

## 7. Where else to look

| Need | Document |
|---|---|
| Layered troubleshooting (triage tree, per-service failure modes) | [`docs/DEBUG.md`](DEBUG.md) |
| Report a bug or file a feature request | [`docs/REPORTING.md`](REPORTING.md) |
| Report a security vulnerability | [`SECURITY.md`](../SECURITY.md) |

---

## 8. Operator cookbook — step-by-step recipes

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
