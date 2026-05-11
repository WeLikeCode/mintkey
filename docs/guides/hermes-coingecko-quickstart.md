# Hermes + Mintkey MCP — CoinGecko Live Test

This guide walks through registering CoinGecko as a Mintkey service, creating a Hermes agent, connecting it to the Mintkey MCP server, and making a live Bitcoin price query — all using the egress proxy to inject the real API key so Hermes never touches it.

**Prerequisites:** `docker compose up -d` is healthy (all services green).

---

## 1. Register CoinGecko as a Mintkey service

CoinGecko's free demo tier requires a key in the `x-cg-demo-api-key` header. Get one at [coingecko.com/en/api](https://www.coingecko.com/en/api) — the free tier covers price queries.

```bash
# 1a. Get an operator session token (or log in through http://localhost:3000/admin)
OPERATOR_TOKEN=$(curl -s -X POST http://localhost:8080/v1/auth/internal-login \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@mintkey.local","password":"changeme"}' \
  | jq -r '.token')

TENANT_ID=$(curl -s http://localhost:8080/v1/tenants \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  | jq -r '.tenants[0].id')

# 1b. Register the service
SERVICE=$(curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/services" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":        "CoinGecko",
    "slug":        "coingecko",
    "display_name":"CoinGecko Price API",
    "description": "Public cryptocurrency price data",
    "base_url":    "https://api.coingecko.com/api/v3",
    "auth_scheme": "api_key_header",
    "openapi_url": "https://api.coingecko.com/api/v3/openapi.json"
  }')

SERVICE_ID=$(echo $SERVICE | jq -r '.id')
echo "Service ID: $SERVICE_ID"

# 1c. Store the CoinGecko demo API key in the Vault Adapter
#     Replace CG_DEMO_KEY with your actual key from coingecko.com/en/api
CG_DEMO_KEY="your-coingecko-demo-api-key"

curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/services/$SERVICE_ID/credentials" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"auth_scheme\": \"api_key_header\",
    \"header_name\": \"x-cg-demo-api-key\",
    \"value\":       \"$CG_DEMO_KEY\"
  }"
```

> **Free-tier alternative:** CoinGecko's `/simple/price` endpoint works without a key at lower rate limits. If you skip 1c, Kong will forward requests without an auth header — that's fine for a quick test.

---

## 2. Create the Hermes agent

```bash
AGENT=$(curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name":        "hermes",
    "description": "Hermes — CoinGecko price-query agent",
    "rate_limit_rps": 10
  }')

AGENT_ID=$(echo $AGENT | jq -r '.id')
AGENT_API_KEY=$(echo $AGENT | jq -r '.api_key')

echo "Agent ID:  $AGENT_ID"
echo "Agent key: $AGENT_API_KEY"   # shown once — store it now
```

The `api_key` value is the credential Hermes presents to the MCP server (`Authorization: Bearer <key>`). It is returned exactly once.

---

## 3. Grant Hermes permission to query CoinGecko prices

```bash
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/permissions" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"service_id\": \"$SERVICE_ID\",
    \"action\":     \"read:simple_price\"
  }"
```

Mintkey derives `read:simple_price` from `GET /simple/price` — the action is `read:<first path segment>`. You can grant additional actions (`read:coins`, `read:markets`, …) or add constraints (`rate_limit`, `time_window`, `source_ip_allowlist`) here.

---

## 4. Configure Hermes to use the Mintkey MCP server

Hermes connects to the MCP server at `http://localhost:8082`. The MCP server exposes four tools:

| Tool | Method | Path | What it does |
|---|---|---|---|
| `list_services` | GET | `/v1/tools/list_services` | Discover services Hermes has access to |
| `describe_service` | GET | `/v1/tools/describe_service/{id}` | Full service metadata |
| `get_openapi` | GET | `/v1/tools/get_openapi/{id}` | OpenAPI URL for the service |
| `request_token` | POST | `/v1/tools/request_token` | Get a short-lived JWT for a service call |

All requests must carry `Authorization: Bearer <AGENT_API_KEY>`.

### MCP client config snippet

```json
{
  "mcpServers": {
    "mintkey": {
      "url": "http://localhost:8082",
      "headers": {
        "Authorization": "Bearer <AGENT_API_KEY>"
      }
    }
  }
}
```

Replace `<AGENT_API_KEY>` with the value from step 2. For remote deployments replace `localhost:8082` with the actual hostname.

### System prompt addition for Hermes

Add this to Hermes's system prompt so it knows how to discover and call services:

```
You have access to a Mintkey MCP server that manages API credentials on your behalf.
Before calling any external service:
  1. Call list_services to see what you have access to.
  2. Call request_token with the service_id and action (e.g. "read:simple_price") to get a JWT.
  3. Make the real API call through the Mintkey egress proxy at http://localhost:8087
     by passing the JWT as: Authorization: Bearer <token>
     The proxy injects the real backend credential — never include raw API keys in your requests.
```

---

## 5. Run the live test — Bitcoin price query

### 5a. Verify discovery works

```bash
# Hermes sees CoinGecko in its service list
curl -s http://localhost:8082/v1/tools/list_services \
  -H "Authorization: Bearer $AGENT_API_KEY" | jq .
```

Expected response:
```json
{
  "services": [
    {
      "id": "<SERVICE_ID>",
      "name": "CoinGecko",
      "slug": "coingecko",
      "base_url": "https://api.coingecko.com/api/v3",
      "auth_scheme": "api_key_header"
    }
  ]
}
```

### 5b. Get a token

```bash
TOKEN=$(curl -s -X POST http://localhost:8082/v1/tools/request_token \
  -H "Authorization: Bearer $AGENT_API_KEY" \
  -H "Content-Type: application/json" \
  -d "{\"service_id\": \"$SERVICE_ID\", \"action\": \"read:simple_price\"}" \
  | jq -r '.token')
echo "Token: $TOKEN"
```

### 5c. Query Bitcoin price through the egress proxy

```bash
curl -s "http://localhost:8087/v1/call/$SERVICE_ID/simple/price?ids=bitcoin&vs_currencies=usd" \
  -H "Authorization: Bearer $TOKEN" | jq .
```

The egress proxy:
1. Validates the JWT against the broker
2. Injects the CoinGecko demo API key as `x-cg-demo-api-key`
3. Forwards the request to `https://api.coingecko.com/api/v3/simple/price`

Expected response:
```json
{
  "bitcoin": {
    "usd": 67000
  }
}
```

---

## 6. (Optional) Classical service API key for Hermes

If Hermes needs long-lived access without going through MCP `request_token` on every call — for example, in a background job — issue a classical service API key instead:

```bash
# Create the classical key (new in long-lived-api-keys feature)
NEW_KEY=$(curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/api-keys" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{
    \"service_id\":      \"$SERVICE_ID\",
    \"allowed_actions\": [\"read:simple_price\"],
    \"expires_at\":      \"$(date -u -v+90d +%Y-%m-%dT%H:%M:%SZ)\"
  }")

CLASSICAL_KEY=$(echo $NEW_KEY | jq -r '.plaintext_key')
echo "Classical key: $CLASSICAL_KEY"   # shown once — store it now
```

Hermes can now query Bitcoin prices directly without a token exchange:

```bash
curl -s "http://localhost:8087/v1/call/$SERVICE_ID/simple/price?ids=bitcoin,ethereum&vs_currencies=usd" \
  -H "Authorization: Bearer $CLASSICAL_KEY" | jq .
```

The proxy checks the `mk_svckey_` prefix, resolves it against the broker cache, verifies the allowed action and constraints, then injects the real CoinGecko key — same egress path, no token round-trip.

To revoke it later:

```bash
KEY_ID=$(echo $NEW_KEY | jq -r '.api_key_id')
curl -s -X POST \
  "http://localhost:8080/v1/tenants/$TENANT_ID/agents/$AGENT_ID/api-keys/$KEY_ID/revoke" \
  -H "Authorization: Bearer $OPERATOR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"reason": "test complete"}'
```

---

## Ports reference

| Service | Local port | Purpose |
|---|---|---|
| Admin UI | 3000 | Operator dashboard (browser) |
| Admin REST API | 8080 | CRUD + audit (curl / AdminJS) |
| MCP server | 8082 | Agent tool endpoints |
| Egress proxy (Kong) | 8087 | Proxy all backend calls through here |
| Credential broker | 8083 | JWT + resolve (internal only) |

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `mintkey:auth_required` from MCP | Missing/wrong agent API key | Check `Authorization: Bearer <key>` header |
| `mintkey:not_authorized` + `permission_not_found` | Permission grant missing | Re-run step 3 |
| 404 from egress proxy | Service not registered with Kong | `docker compose restart kong-syncer` |
| 401 `api_key_wrong_service` on classical key | Key bound to different service_id | Create a new key for the correct service |
| 429 from broker | Rate limit exceeded | Wait 60s or increase `rate_limit_rps` on the agent |
