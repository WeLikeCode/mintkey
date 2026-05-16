# Connecting Claude Desktop to Mintkey

[Claude Desktop](https://claude.ai/download) is Anthropic's desktop application for macOS
and Windows. It supports custom MCP servers, letting Claude call your Mintkey-brokered
services without ever seeing the real credentials.

**Official MCP docs:** https://modelcontextprotocol.io/clients/claude-desktop

---

## Prerequisites

- Mintkey stack running locally (`docker compose up -d` — all services healthy)
- Claude Desktop installed and signed in
- An agent API key (`mk_agent_...`) from the Mintkey Admin UI

**Get an agent API key:**
1. Open `http://localhost:8081` → sign in with Keycloak
2. **Agents → New** → name it (e.g. `claude-desktop-agent`) → **Create**
3. Copy the `mk_agent_...` key shown once on the success screen
4. **Permission Grants → New** → select the agent and at least one service → `call` → **Create**

---

## Configuration

The Claude Desktop MCP config file lives at:

| Platform | Path |
|---|---|
| macOS | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json` |

Open or create the file and add the `mintkey` server block:

```json
{
  "mcpServers": {
    "mintkey": {
      "type": "http",
      "url": "http://localhost:8082/mcp",
      "headers": {
        "Authorization": "Bearer mk_agent_PASTE_YOUR_KEY_HERE"
      },
      "description": "Mintkey credential broker — brokered access to registered services"
    }
  }
}
```

Replace `mk_agent_PASTE_YOUR_KEY_HERE` with your actual agent API key.

**If Mintkey runs on a different machine** (LAN or server), replace `localhost:8082`
with the value of `MINTKEY_MCP_PUBLIC_URL` set in the operator's `.env` file. See
[`docs/NETWORK.md`](../../NETWORK.md) for the full configuration reference.

---

## Verify the connection

After saving the config, restart Claude Desktop. Then ask Claude:

> "List the Mintkey services available to me."

Claude should call `mintkey_list_services` and return the services your agent has
permission grants on.

You can also verify directly via curl before restarting Claude:

```bash
# 1. Handshake (no auth needed)
curl -s -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'

# 2. Confirm the 6 Mintkey tools are present (auth required)
curl -s -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mk_agent_PASTE_YOUR_KEY_HERE" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | jq '[.result.tools[].name]'
# Expected: ["mintkey_bootstrap","mintkey_list_services","mintkey_discover",
#            "mintkey_describe_service","mintkey_get_openapi","mintkey_request_token"]
```

---

## The 6 Mintkey tools Claude will see

| Tool | What it does |
|---|---|
| `mintkey_bootstrap` | Returns agent onboarding instructions (no auth required) |
| `mintkey_list_services` | Lists services your agent has access to |
| `mintkey_discover` | Discovers services with brokered-call instructions |
| `mintkey_describe_service` | Details + constraints for one service |
| `mintkey_get_openapi` | Fetches the upstream service's OpenAPI spec |
| `mintkey_request_token` | Issues a short-lived JWT for a service call |

Claude will use these tools to discover what services you have, request tokens, and
call those services through the Mintkey proxy — never touching the real credentials.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| MCP server not appearing in Claude | Config file not found or malformed JSON | Validate JSON with `jq . claude_desktop_config.json`; restart Claude after saving |
| `401 Unauthorized` | Wrong or missing agent key | Check `Authorization` header value; re-copy from Admin UI |
| `404 Not Found` | Wrong URL path | Ensure URL ends with `/mcp` (not `/v1/mcp` or `/`) |
| Connection refused | Stack not running | `docker compose ps` — all services must be `Up (healthy)` |
| Tools listed but calls fail | Agent lacks permission grant | Admin UI → Permission Grants → add the service your agent needs |
| `403 permission_not_found` | No active grant for requested service | Create a permission grant in Admin UI (see Prerequisites) |

---

## Once connected

See [`docs/HOW-TO.md`](../../HOW-TO.md) for the full operator cookbook — adding services,
rotating credentials, revoking agents, and reading the audit trail.

For the 10-minute demo with the built-in mock backend (no external keys needed), see
[`docs/guides/10min-mock-demo.md`](../10min-mock-demo.md).
