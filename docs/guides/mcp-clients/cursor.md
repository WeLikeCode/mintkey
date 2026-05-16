# Connecting Cursor to Mintkey

[Cursor](https://cursor.sh) is an AI-powered code editor with native MCP support.
Connecting it to Mintkey lets Cursor's AI call your brokered services without ever
seeing the real credentials.

**Official MCP docs:** https://docs.cursor.com/context/model-context-protocol

---

## Prerequisites

- Mintkey stack running locally (`docker compose up -d` — all services healthy)
- Cursor installed (v0.43 or later recommended for stable MCP support)
- An agent API key (`mk_agent_...`) from the Mintkey Admin UI

**Get an agent API key:**
1. Open `http://localhost:8081` → sign in with Keycloak
2. **Agents → New** → name it (e.g. `cursor-agent`) → **Create**
3. Copy the `mk_agent_...` key shown once on the success screen
4. **Permission Grants → New** → select the agent and at least one service → `call` → **Create**

---

## Configuration

Cursor reads MCP configuration from `.cursor/mcp.json` in your project root.
This file can be committed to version control (each developer supplies their own key).

Create or edit `.cursor/mcp.json`:

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

**Global configuration** (applies to all projects, not committed to repos):

Cursor also supports a user-level MCP config. Open Cursor settings:
`Cursor → Settings → MCP` and add a new server entry with:
- **Name:** `mintkey`
- **Type:** HTTP
- **URL:** `http://localhost:8082/mcp`
- **Headers:** `Authorization: Bearer mk_agent_PASTE_YOUR_KEY_HERE`

**If Mintkey runs on a different machine** (LAN or server), replace `localhost:8082`
with the value of `MINTKEY_MCP_PUBLIC_URL` set in the operator's `.env` file. See
[`docs/NETWORK.md`](../../NETWORK.md) for the full reference.

---

## Verify the connection

After saving the config, reload Cursor (or reopen the project folder). In the Cursor
chat panel, the Mintkey server should appear under **MCP Servers**.

Verify directly with curl before opening Cursor:

```bash
# Handshake (no auth needed)
curl -s -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'

# Confirm the 6 Mintkey tools (auth required)
curl -s -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mk_agent_PASTE_YOUR_KEY_HERE" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | jq '[.result.tools[].name]'
# Expected: ["mintkey_bootstrap","mintkey_list_services","mintkey_discover",
#            "mintkey_describe_service","mintkey_get_openapi","mintkey_request_token"]
```

In Cursor chat, you can also ask:

> "Use Mintkey to list the services I have access to."

---

## The 6 Mintkey tools Cursor will see

| Tool | What it does |
|---|---|
| `mintkey_bootstrap` | Returns agent onboarding instructions (no auth required) |
| `mintkey_list_services` | Lists services your agent has access to |
| `mintkey_discover` | Discovers services with brokered-call instructions |
| `mintkey_describe_service` | Details + constraints for one service |
| `mintkey_get_openapi` | Fetches the upstream service's OpenAPI spec |
| `mintkey_request_token` | Issues a short-lived JWT for a service call |

Cursor's AI will use these tools when you ask it to interact with a Mintkey-registered
service. Real credentials stay encrypted in the vault.

---

## Committing `.cursor/mcp.json` safely

The MCP config file references your personal `mk_agent_...` key, which is a secret.
**Do not commit your actual key.** Two patterns:

**Pattern 1 — placeholder in repo + personal key in env var:**

```json
{
  "mcpServers": {
    "mintkey": {
      "type": "http",
      "url": "http://localhost:8082/mcp",
      "headers": {
        "Authorization": "Bearer ${MINTKEY_AGENT_KEY}"
      }
    }
  }
}
```

Set `MINTKEY_AGENT_KEY=mk_agent_...` in your shell profile or `.env.local`.

**Pattern 2 — gitignore the file:**

Add `.cursor/mcp.json` to `.gitignore` and keep the actual key locally. Share a
`.cursor/mcp.json.example` with a placeholder value in the repo instead.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Server not listed in Cursor MCP panel | Config not found or malformed JSON | Validate JSON: `jq . .cursor/mcp.json`; reload Cursor |
| `401 Unauthorized` | Wrong or missing agent key | Re-copy `mk_agent_...` from Admin UI; check the `Authorization` header |
| `404 Not Found` | Wrong URL path | Ensure URL ends with `/mcp`; verify port `8082` |
| Connection refused | Stack not running | `docker compose ps` — all services must be `Up (healthy)` |
| Tools visible but calls fail | Agent lacks permission grant | Admin UI → Permission Grants → add the service |

---

## Once connected

See [`docs/HOW-TO.md`](../../HOW-TO.md) for the full operator cookbook — adding services,
rotating credentials, revoking agents, and reading the audit trail.

For the 10-minute demo with the built-in mock backend (no external keys needed), see
[`docs/guides/10min-mock-demo.md`](../10min-mock-demo.md).
