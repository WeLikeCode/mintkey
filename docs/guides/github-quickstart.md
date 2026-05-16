# GitHub REST API — Mintkey Operator Quickstart

This guide walks through configuring GitHub as a Mintkey-brokered service: register the service from the bundled template, store a Personal Access Token (PAT) in the vault, validate the credential against the live GitHub API before committing it to the database, create an agent with a permission grant and MCP config, and make a real proxied call to the GitHub REST API — all without the agent ever touching the raw PAT.

**Prerequisites:** `docker compose up -d` is healthy (all services green).

> **Prerequisite — break-glass session.** The curl examples below use `POST /v1/auth/internal-login` to obtain a session cookie. Post-SSO, that endpoint returns 404 by default (per ADR-0020). To enable the break-glass path before following this guide:
>
> ```bash
> docker compose exec admin-api python -m admin_api.cli admin reset-password --email admin@mintkey.internal
> # → prints a temporary password; use it in the internal-login call below.
> ```
>
> When you're done, close the window: `mintkey admin clear-password --email admin@mintkey.internal`.

---

## 0. Prerequisites

**Stack health check:**

```bash
docker compose ps
```

Run `docker compose ps` — all Mintkey services should show `Up (healthy)`. The stack has 17 services including one-shot jobs (seed-job, liquibase) that exit after initial setup.

**GitHub Personal Access Token (PAT):**

Create a fine-grained or classic PAT at [github.com/settings/tokens?type=beta](https://github.com/settings/tokens?type=beta).

Minimum scopes for this guide:
- `repo` → `Contents: Read` (fine-grained, private repos) — or
- `public_repo` (classic, public repos only)

**Operator session:**

For local dev use `admin@mintkey.internal` with the password from the bootstrap volume:

```bash
# PRIMARY — read directly from the bootstrap volume:
docker run --rm -v mintkey_bootstrap_secrets:/secrets alpine \
  cat /secrets/admin_password

# FALLBACK — grep the seed-job log (only works on the first `docker compose up`):
docker compose logs seed-job | grep "Bootstrap admin password"
```

For Playwright-based local dev the password is in `admin-ui/e2e/.env.local` as `PLAYWRIGHT_PASS`.

---

## 0a. Note on the "Hermes" naming convention

Some Mintkey examples use agent names like `hermes-twilio-agent` or `hermes-coingecko-agent`. "Hermes" is not a Mintkey concept or special agent type — it is simply a name the operator chose. You may name your agent anything. This guide uses `gh-agent`.

---

## 1. Get an operator session + tenant ID

```bash
# 1a. Log in — sets a session cookie and a CSRF cookie
curl -s -X POST http://localhost:8080/v1/auth/internal-login \
  -H "Content-Type: application/json" \
  -c cookies.txt \
  -d '{"email":"admin@mintkey.internal","password":"YOUR_BOOTSTRAP_PASSWORD"}' | jq .

# 1b. Capture the CSRF token from the cookie jar
CSRF=$(grep csrf_token cookies.txt | awk '{print $NF}')

# 1c. Get the default tenant ID (or use the known fixture value for local dev)
#     Platform-admin role is signaled via X-Platform-Admin: true.
#     The admin UI's BFF injects it automatically for platform-admin sessions (commit 72770e27).
#     For curl-path operators, set it manually:
TENANT_ID=$(curl -s http://localhost:8080/v1/tenants \
  -b cookies.txt \
  -H "X-Mintkey-Csrf: $CSRF" \
  -H "X-Platform-Admin: true" \
  | jq -r '.data[0].id')

echo "Tenant: $TENANT_ID"
# Local dev fixture: 9593e3ba-4102-4235-9748-28d35b473214
```

---

## 2. Register GitHub as a Mintkey service

**Via UI — Create from Template (recommended):**

1. Navigate to `http://localhost:8081/admin/resources/services`
2. Click the **Templates** button (top-right of the services list) to navigate to the **Create from Template** picker page at `/admin/resources/services/actions/templates`
3. Click the **Use this template** button inside the GitHub card (the card body has `cursor: pointer` but only the button has an `onClick` handler)
4. The form pre-fills all 5 fields after OPS-DDEE (commit `294dd273`): `name=GitHub`, `base_url=https://api.github.com`, `auth_scheme=bearer_token`, `description`, and `openapi_url` (GitHub OpenAPI spec URL)
5. Leave the credential value empty for now — that is Step 3. Click **Create Service**.
6. The form shows an in-place success banner with **Test connection** and **View service** CTAs (the URL doesn't change). Click **View service** to navigate to the show page.

**Via curl (automation):**

```bash
SERVICE=$(curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/services" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" \
  -b cookies.txt \
  -d '{
    "name":        "GitHub",
    "slug":        "github",
    "display_name":"GitHub REST API",
    "description": "GitHub v3 REST API — issues, repos, PRs, workflows. Use a Personal Access Token (classic or fine-grained).",
    "base_url":    "https://api.github.com",
    "auth_scheme": "bearer_token",
    "openapi_url": "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"
  }')

SID=$(echo $SERVICE | jq -r '.id')
echo "Service ID: $SID"
# Example: svc_01HX5J9F8V8H8V0CG3F2Y5J6S1
```

> The template slug is `github` — you can also fetch it to see all pre-filled fields:
> ```bash
> curl -s http://localhost:8080/v1/service-templates/github \
>   -H "X-Mintkey-Csrf: $CSRF" \
>   -b cookies.txt | jq .
> ```

---

## 3. Test the credential before saving it

Mintkey provides a `/test-transient` endpoint that validates a service config and credential against the live upstream API **without writing anything to the database or vault**. Use this to confirm your PAT is valid before committing it.

```bash
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/services/test-transient" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" \
  -b cookies.txt \
  -d '{
    "service": {
      "name":        "GitHub-candidate",
      "base_url":    "https://api.github.com",
      "auth_scheme": "bearer_token"
    },
    "credential": {
      "value": "ghp_YOUR_PAT_HERE"
    },
    "test": {
      "method":     "GET",
      "path":       "/user",
      "timeout_ms": 5000
    }
  }' | jq .
```

Expected response (success):

```json
{
  "ok": true,
  "status_code": 200,
  "latency_ms": 142,
  "final_url": "https://api.github.com/user",
  "response_body_truncated": "{\"login\":\"your-github-username\",\"id\":12345678,...}"
}
```

**Via UI:** in the ServiceCreateForm fill all fields including the credential value and click **Test connection** — the button is at the bottom of the form, above **Create Service**. Check the **Add a credential now?** checkbox to reveal the credential `value` field. The Test connection button is enabled once `name`, `base_url`, `auth_scheme`, and the credential `value` are all populated. A result panel shows `status_code`, `latency_ms`, and the response body.

If the test returns `{"ok": false, "status_code": 401, ...}`, the PAT is invalid or has insufficient scopes — do not proceed to Step 4 until this returns 200.

---

## 4. Set the credential (persist to vault)

Once the transient test passes, store the PAT in the vault so the proxy can retrieve it at call time.

**Via UI:** on the service show page click **Set Credential** — this navigates to `/admin/resources/credentials/actions/new?service_id=<id>` with the service_id pre-filled (OPS-DDEE, commit `294dd273`). Choose `bearer_token`, paste the PAT in the Value field, click **Save**.

**Via curl:**

```bash
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SID/credentials" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" \
  -b cookies.txt \
  -d '{
    "auth_scheme": "bearer_token",
    "value":       "ghp_YOUR_PAT_HERE"
  }' | jq .
# Response: {"id": "cred_01...", "key_version": 1, "status": "active"}
```

The endpoint accepts both `svc_…` wire IDs and raw UUIDs (OPS-AA, commit `32bdc642`).

**Test after save** — verify the persisted credential health using the service-scoped test endpoint:

```bash
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SID/test" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" \
  -b cookies.txt \
  -d '{"method": "GET", "path": "/user", "timeout_ms": 5000}' | jq .
```

Or use the **Test Connection** button on the service show page.

---

## 5. Create the agent, grant, and MCP config

```bash
# 5a. Create the agent — API key is returned ONCE; copy it immediately
AGENT=$(curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" \
  -b cookies.txt \
  -d '{
    "name":            "gh-agent",
    "description":     "GitHub query agent",
    "rate_limit_rps":  10
  }')

AGENT_ID=$(echo $AGENT | jq -r '.id')
AGENT_KEY=$(echo $AGENT | jq -r '.api_key')

echo "Agent ID:  $AGENT_ID"
echo "Agent key: $AGENT_KEY"   # shown once — store it now
```

> **This API key will not be shown again — copy it now.** After OPS-DDEE (commit `294dd273`), the agent-created success screen in the admin UI shows a **Copy** button next to the one-time API key. Use it.

The `api_key` is the credential the agent presents to the MCP server (`Authorization: Bearer <key>`). It is returned exactly once.

```bash
# 5b. Grant the agent permission to call GitHub
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/permissions" \
  -H "Content-Type: application/json" \
  -H "X-Mintkey-Csrf: $CSRF" \
  -b cookies.txt \
  -d "{
    \"service_id\": \"$SID\",
    \"action\":     \"call\"
  }" | jq .
```

**MCP config snippet** — for the operator's AI client (Claude Desktop, Cursor, etc.):

Use the **Show MCP config** button on the dashboard onboarding checklist (the modal title is "Connect your LLM via MCP") to get a pre-filled snippet. The authoritative snippet after OPS-FF (commit `aa9259ed`) is:

```json
{
  "mcpServers": {
    "mintkey": {
      "type": "http",
      "url": "http://localhost:8082/v1",
      "headers": {
        "Authorization": "Bearer <PASTE_AGENT_API_KEY>"
      },
      "description": "Mintkey credential broker — paste your agent API key above (mk_agent_...)."
    }
  }
}
```

Replace `<PASTE_AGENT_API_KEY>` with the `mk_agent_…` value from step 5a. For remote deployments replace `localhost:8082` with the actual hostname.

If the AI client runs on a different machine, replace `localhost` with the LAN-reachable URL configured via `MINTKEY_MCP_PUBLIC_URL`. See [docs/NETWORK.md](../NETWORK.md) for the full setup.

> **Note:** `bootstrap` is the only MCP tool that does not require the `Authorization` header — all other tools require `Authorization: Bearer <AGENT_KEY>`.

---

## 6. Discover GitHub via MCP

Once the AI client is connected the agent can call these MCP tools — all require `Authorization: Bearer $AGENT_KEY` except `bootstrap`.

```bash
# Bootstrap — no auth required; returns agent-bootstrap skill description
curl -s http://localhost:8082/v1/tools/bootstrap | jq .

# List services the agent has access to
curl -s http://localhost:8082/v1/tools/list_services \
  -H "Authorization: Bearer $AGENT_KEY" | jq .
```

Expected list_services response (after OPS-CC, commit `fb0f0809` — `id` is now in `svc_…` wire form):

```json
{
  "services": [
    {
      "id":          "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
      "name":        "GitHub",
      "slug":        "github",
      "base_url":    "https://api.github.com",
      "auth_scheme": "bearer_token"
    }
  ]
}
```

All MCP tools accept both `svc_…` wire IDs and raw UUIDs. The canonical operator-facing form is `svc_…`, returned by `list_services`.

```bash
# Capture the wire-form service ID for use in subsequent calls
SID=$(curl -s http://localhost:8082/v1/tools/list_services \
  -H "Authorization: Bearer $AGENT_KEY" \
  | jq -r '.services[] | select(.slug == "github") | .id')

# Describe GitHub — returns description + openapi_url (new fields per OPS-V)
curl -s "http://localhost:8082/v1/tools/describe_service/$SID" \
  -H "Authorization: Bearer $AGENT_KEY" | jq .
```

Expected describe_service response:

```json
{
  "service": {
    "id":          "svc_01HX5J9F8V8H8V0CG3F2Y5J6S1",
    "name":        "GitHub",
    "slug":        "github",
    "base_url":    "https://api.github.com",
    "auth_scheme": "bearer_token",
    "description": "GitHub v3 REST API — issues, repos, PRs, workflows. Use a Personal Access Token (classic or fine-grained).",
    "openapi_url": "https://raw.githubusercontent.com/github/rest-api-description/main/descriptions/api.github.com/api.github.com.json"
  }
}
```

The agent uses `base_url` and `auth_scheme` to know how to call the service through the proxy. It never sees the PAT value — the proxy injects it at request time.

---

## 7. Make a real proxy call

```bash
# 7a. Request a short-lived JWT for this service + action
TOKEN=$(curl -s -X POST http://localhost:8082/v1/tools/request_token \
  -H "Authorization: Bearer $AGENT_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\": \"$SID\", \"action\": \"call\"}" \
  | jq -r '.token')

echo "Token: $TOKEN"   # eyJ...
```

```bash
# 7b. Call GitHub through the egress proxy
#     URL pattern: $MINTKEY_PROXY_URL/v1/call/<service_id>/<path>
curl -s "http://localhost:8000/v1/call/$SID/repos/octocat/hello-world" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

Expected response: GitHub repository metadata JSON for `octocat/hello-world`.

The Kong egress proxy:
1. Validates the JWT (Ed25519 signature from broker, 60-second TTL)
2. Fetches the PAT from vault-adapter via gRPC
3. Strips the JWT, injects `Authorization: Bearer <PAT>`
4. Forwards to `https://api.github.com/repos/octocat/hello-world`

> **Proxy URL:** always use `MINTKEY_PROXY_URL` (default: `http://localhost:8000`) — not `MINTKEY_KONG_URL`. The env var is set in `docker-compose.yml` (OPS-FF, commit `aa9259ed`) and should be used in any automation or agent system prompt.

> **Kong route sync:** after OPS-BB (commit `c49463bd`), kong-syncer performs an initial full reconcile on startup and re-syncs on every `mintkey:service` NOTIFY event. Routes appear in Kong immediately. If you get Kong `no Route matched`: wait 30s for kong-syncer to complete initial reconcile, then check `docker compose logs mintkey-kong-syncer-1 | grep routes_published`.

Additional call examples:

```bash
# Get the authenticated user's profile
curl -s "http://localhost:8000/v1/call/$SID/user" \
  -H "Authorization: Bearer $TOKEN" | jq '{login: .login, name: .name}'

# List the authenticated user's repos (first page)
curl -s "http://localhost:8000/v1/call/$SID/user/repos?per_page=5" \
  -H "Authorization: Bearer $TOKEN" | jq '.[].full_name'
```

---

## 8. Failure modes

| Symptom | Likely cause | Where to look | Quick remediation |
|---------|--------------|---------------|-------------------|
| 401 from proxy | JWT expired (60-second TTL) or wrong service_id in URL | `docker compose logs mintkey-proxy-plugin-1 --tail 50`, `docker compose logs mintkey-broker-1 --tail 50` | Re-issue the token via `/v1/tools/request_token` |
| **403** with body `{"code": "mintkey:not_authorized", "reason_code": "permission_not_found"}` | Missing grant for agent → service → `call` action | `docker compose logs mintkey-admin-api-1 --tail 50`; check `audit_events` table for `token.denied` | Create the grant — Step 5b |
| 404 `service_not_found` | Wrong service_id in the proxy URL | `curl -s http://localhost:8082/v1/tools/list_services -H "Authorization: Bearer $AGENT_KEY" \| jq .` | Use the canonical `svc_` ID from list_services |
| 429 rate-limited | `rate_limit_rps` exceeded on agent | Agent show page → **Rate Limit Rps** field | Raise the limit or wait for the window to reset |
| 502 from proxy | Credential row missing or vault lookup failed | `docker compose logs mintkey-proxy-plugin-1 --tail 50` (502 surfaces here; `docker compose logs mintkey-vault-adapter-1` may help diagnose root cause) | Verify vault-adapter is up; verify credential was saved in Step 4 |
| Token request returns 403 | Broker down or `MINTKEY_BROKER_SERVICE_TOKEN` mismatch | `docker compose logs mintkey-broker-1 --tail 50` | Restart broker; verify `MINTKEY_BROKER_SERVICE_TOKEN` env matches across services |
| Kong 404 on proxy call | Routes not synced after service create | `docker compose logs mintkey-kong-syncer-1 --tail 50` | Kong-syncer publishes routes after each `mintkey:service` NOTIFY (~300ms). Wait or check `docker compose logs mintkey-kong-syncer-1 \| grep routes_published`. If still 404 with a known-good `svc_` ID, verify the wire-form encoder matches between Python and Go (`services/kong-syncer/internal/wireids/encode_test.go`). |
| `description`/`openapi_url` missing from describe_service | Service registered without these fields | `docker compose logs mintkey-admin-api-1 --tail 20` | Confirm service was registered with `description` and `openapi_url` fields — re-save if not |
| Transient test returns `{"ok": false, "status_code": 401}` | PAT is invalid, revoked, or missing required scope | GitHub tokens page at `https://github.com/settings/tokens` | Generate a new PAT with correct scopes; re-run Step 3 |

---

## 9. Observability — verify it's working

```bash
# Jaeger traces
open http://localhost:16686
# Service dropdown: admin-api, mcp-server. Pick a trace to see the full call chain.

# Grafana dashboards
open http://localhost:3003   # admin / admin
# Grafana container listens on 3000; host port mapping is 3003.
# Dashboards: mintkey-overview (request volume), mintkey-per-service (token issuance per service),
#             mintkey-credential-cache (vault DEK hit/miss ratio),
#             mintkey-audit (audit event stream), mintkey-memory (memory + GC metrics)
# Note: Grafana persists state in a docker volume; if your operator changed the password,
#       reset via: docker compose exec grafana grafana-cli admin reset-admin-password admin

# Prometheus (internal — no host port by default; query via Grafana)
# prometheus has no host ports: compose binds only 9090/tcp inside the Docker network.
```

---

## Ports reference

| Service | Host port | Purpose |
|---------|-----------|---------|
| admin-api | 8080 | REST API (`/v1/`) |
| admin-ui | 8081 | Operator UI |
| mcp-server | 8082 | Agent-facing MCP tools |
| broker | 8083 | JWT issuance |
| vault-adapter | 8084 (gRPC) / 8087 (HTTP) | Credential vault |
| kong (egress proxy) | **8000** | `MINTKEY_PROXY_URL` — use this for all proxy calls |
| kong (admin) | 8001 | Kong admin API (internal) |
| jaeger | 16686 | Traces UI |
| grafana | **3003** | Dashboards (container listens on 3000; host mapped to 3003) [^grafana-port] |

> **Internal only (no host port):** `prometheus` (9090 inside the Docker network), `proxy-plugin`, `kong-syncer`.

[^grafana-port]: Grafana container listens on 3000; host port mapping is `3003:3000` as configured in `docker-compose.yml`.
