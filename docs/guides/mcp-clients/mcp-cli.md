# Connecting mcp-cli to Mintkey

[mcp-cli](https://github.com/chrishayuk/mcp-cli) is a command-line MCP client for
testing and scripting MCP server interactions. It is useful for debugging Mintkey's MCP
tools, scripting agentic workflows, or verifying your Mintkey setup without a full IDE.

**Official mcp-cli repo:** https://github.com/chrishayuk/mcp-cli

---

## Prerequisites

- Mintkey stack running locally (`docker compose up -d` — all services healthy)
- Python 3.10+ and `pip` or `uv`
- An agent API key (`mk_agent_...`) from the Mintkey Admin UI

**Get an agent API key:**
1. Open `http://localhost:8081` → sign in with Keycloak
2. **Agents → New** → name it (e.g. `mcp-cli-agent`) → **Create**
3. Copy the `mk_agent_...` key shown once on the success screen
4. **Permission Grants → New** → select the agent and at least one service → `call` → **Create**

---

## Install mcp-cli

```bash
pip install mcp-cli
# or
uv tool install mcp-cli
```

Verify:

```bash
mcp-cli --version
```

---

## Configuration

mcp-cli uses a JSON config file to define servers. Create `~/.mcp-cli/servers.json`
(or a project-local `mcp-servers.json`):

```json
{
  "servers": {
    "mintkey": {
      "type": "http",
      "url": "http://localhost:8082/mcp",
      "headers": {
        "Authorization": "Bearer mk_agent_PASTE_YOUR_KEY_HERE"
      }
    }
  }
}
```

Replace `mk_agent_PASTE_YOUR_KEY_HERE` with your actual agent API key.

**If Mintkey runs on a different machine** (LAN or server), replace `localhost:8082`
with the value of `MINTKEY_MCP_PUBLIC_URL` set in the operator's `.env` file. See
[`docs/NETWORK.md`](../../NETWORK.md) for the full reference.

---

## Command-line invocation (no config file)

You can also pass the server URL and headers directly on the command line without a
config file:

```bash
# List available tools
mcp-cli tools list \
  --server-url http://localhost:8082/mcp \
  --header "Authorization: Bearer mk_agent_PASTE_YOUR_KEY_HERE"

# Discover services the agent has access to
mcp-cli tools call mintkey_list_services \
  --server-url http://localhost:8082/mcp \
  --header "Authorization: Bearer mk_agent_PASTE_YOUR_KEY_HERE" \
  --arguments '{}'
```

---

## Verify the connection

```bash
# Using config file
export MINTKEY_AGENT_KEY="mk_agent_PASTE_YOUR_KEY_HERE"

# Initialize handshake (no auth needed)
mcp-cli initialize --server mintkey

# List tools (auth required — uses key from config)
mcp-cli tools list --server mintkey
```

Expected `tools list` output:

```
mintkey_bootstrap
mintkey_list_services
mintkey_discover
mintkey_describe_service
mintkey_get_openapi
mintkey_request_token
```

You can also verify with a raw curl call:

```bash
# Confirm the 6 Mintkey tools
curl -s -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mk_agent_PASTE_YOUR_KEY_HERE" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
  | jq '[.result.tools[].name]'
# Expected: ["mintkey_bootstrap","mintkey_list_services","mintkey_discover",
#            "mintkey_describe_service","mintkey_get_openapi","mintkey_request_token"]
```

---

## The 6 Mintkey tools

| Tool | What it does | Auth required |
|---|---|---|
| `mintkey_bootstrap` | Returns agent onboarding instructions | No |
| `mintkey_list_services` | Lists services your agent has access to | Yes |
| `mintkey_discover` | Discovers services with call instructions | Yes |
| `mintkey_describe_service` | Details + constraints for one service | Yes |
| `mintkey_get_openapi` | Fetches the upstream OpenAPI spec | Yes |
| `mintkey_request_token` | Issues a short-lived JWT for a service call | Yes |

---

## Scripting example: list services and request a token

```bash
AGENT_KEY="mk_agent_PASTE_YOUR_KEY_HERE"
MCP_URL="http://localhost:8082/mcp"

# Step 1: list services
SERVICES=$(curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AGENT_KEY" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"mintkey_list_services","arguments":{}}}')
echo "$SERVICES" | jq '.result.content[0].text' | python3 -c "import sys,json; d=json.loads(json.load(sys.stdin)); [print(s['id'], s['name']) for s in d.get('services',[])]"

# Step 2: capture a service ID
SID=$(echo "$SERVICES" | jq -r '.result.content[0].text' | python3 -c "import sys,json; d=json.loads(sys.stdin.read()); print(d['services'][0]['id'])")

# Step 3: request a token
curl -s -X POST "$MCP_URL" \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer $AGENT_KEY" \
  -d "{\"jsonrpc\":\"2.0\",\"id\":2,\"method\":\"tools/call\",\"params\":{\"name\":\"mintkey_request_token\",\"arguments\":{\"service_id\":\"$SID\",\"action\":\"call\"}}}" \
  | jq '.result.content[0].text' | python3 -c "import sys,json; print(json.loads(json.load(sys.stdin))['token'][:40], '...')"
```

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `mcp-cli: command not found` | Not installed or not in PATH | `pip install mcp-cli`; add `~/.local/bin` to PATH |
| `401 Unauthorized` | Wrong or missing agent key | Check `Authorization` header; re-copy from Admin UI |
| `404 Not Found` | Wrong URL path | Ensure URL ends with `/mcp`; verify port `8082` |
| Connection refused | Stack not running | `docker compose ps` — all services must be `Up (healthy)` |
| `tools list` is empty | mcp-cli version incompatible | Update: `pip install --upgrade mcp-cli` |
| Tool call returns error | Agent lacks permission grant | Admin UI → Permission Grants → add the service |

---

## Once connected

See [`docs/HOW-TO.md`](../../HOW-TO.md) for the full operator cookbook — adding services,
rotating credentials, revoking agents, and reading the audit trail.

For the 10-minute demo with the built-in mock backend (no external keys needed), see
[`docs/guides/10min-mock-demo.md`](../10min-mock-demo.md).
