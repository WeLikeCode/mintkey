# Connecting Claude Code to Mintkey

[Claude Code](https://claude.ai/claude-code) is Anthropic's official CLI for Claude,
designed for software development tasks in your terminal. It supports MCP servers,
letting Claude call your Mintkey-brokered services without ever seeing the real credentials.

**Official MCP docs:** https://docs.anthropic.com/en/docs/claude-code/mcp

---

## Prerequisites

- Mintkey stack running locally (`docker compose up -d` — all services healthy)
- Claude Code installed (`npm install -g @anthropic-ai/claude-code` or via the official installer)
- An agent API key (`mk_agent_...`) from the Mintkey Admin UI

**Get an agent API key:**
1. Open `http://localhost:8081` → sign in with Keycloak
2. **Agents → New** → name it (e.g. `claude-code-agent`) → **Create**
3. Copy the `mk_agent_...` key shown once on the success screen
4. **Permission Grants → New** → select the agent and at least one service → `call` → **Create**

---

## Configuration

Claude Code reads MCP server configuration from a JSON file. You can configure MCP
servers at the project level or the user level.

**User-level (applies to all projects):**

```bash
claude mcp add mintkey \
  --url "http://localhost:8082/mcp" \
  --header "Authorization: Bearer mk_agent_PASTE_YOUR_KEY_HERE"
```

**Or edit the config file directly.** The user-level MCP config lives at:

```
~/.claude/mcp.json
```

Add the `mintkey` server block:

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

**Project-level (applies only to this repo, checked in to `.claude/`):**

Create or edit `.claude/mcp.json` in your project root with the same structure. This
lets you commit a Mintkey MCP config alongside your code so every team member uses it
(each developer must supply their own `mk_agent_...` key via an env var or local override).

**If Mintkey runs on a different machine** (LAN or server), replace `localhost:8082`
with the value of `MINTKEY_MCP_PUBLIC_URL` set in the operator's `.env` file. See
[`docs/NETWORK.md`](../../NETWORK.md) for the full reference.

---

## Verify the connection

```bash
# List configured MCP servers
claude mcp list

# Test the connection
claude mcp test mintkey
```

Or verify directly via curl:

```bash
# Handshake (no auth needed)
curl -s -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"test","version":"0"}}}'

# Confirm the 6 Mintkey tools are present (auth required)
curl -s -X POST http://localhost:8082/mcp \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer mk_agent_PASTE_YOUR_KEY_HERE" \
  -d '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | jq '[.result.tools[].name]'
# Expected: ["mintkey_bootstrap","mintkey_list_services","mintkey_discover",
#            "mintkey_describe_service","mintkey_get_openapi","mintkey_request_token"]
```

Inside a Claude Code session, you can also ask:

> "Use Mintkey to list the services I have access to."

---

## The 6 Mintkey tools

| Tool | What it does |
|---|---|
| `mintkey_bootstrap` | Returns agent onboarding instructions (no auth required) |
| `mintkey_list_services` | Lists services your agent has access to |
| `mintkey_discover` | Discovers services with brokered-call instructions |
| `mintkey_describe_service` | Details + constraints for one service |
| `mintkey_get_openapi` | Fetches the upstream service's OpenAPI spec |
| `mintkey_request_token` | Issues a short-lived JWT for a service call |

Claude Code will use these tools autonomously when you ask it to interact with a
Mintkey-registered service. The real credentials stay in the vault; your shell never
sees them.

---

## Using Mintkey in agentic tasks

When Claude Code calls a Mintkey-registered service, the flow is:

1. Claude calls `mintkey_list_services` → finds e.g. `GitHub`, `mock-backend`
2. Claude calls `mintkey_request_token` with the service ID and action `call`
3. Mintkey returns a short-lived JWT (10-minute TTL, Ed25519-signed)
4. Claude makes HTTP requests to `http://localhost:8000/v1/call/<service_id>/<path>` with the JWT
5. The Mintkey proxy validates the JWT, fetches the real credential from vault, and forwards the request

**Important:** when Claude needs to make direct HTTP calls (not via a tool), it will
use the proxy URL, not the upstream service URL. The proxy URL is:
`http://localhost:8000/v1/call/<service_id>/<upstream_path>`.

For remote deployments, `localhost:8000` becomes the value of `MINTKEY_PROXY_PUBLIC_URL`.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `mcp list` shows no servers | Config not found | Verify `~/.claude/mcp.json` exists and is valid JSON (`jq . ~/.claude/mcp.json`) |
| `401 Unauthorized` | Wrong or missing agent key | Re-copy `mk_agent_...` from Admin UI; check the `Authorization` header |
| `404 Not Found` | Wrong URL path | Ensure URL ends with `/mcp`; verify port `8082` is correct |
| Connection refused | Stack not running | `docker compose ps` — all services must be `Up (healthy)` |
| Tools listed but calls fail | Agent lacks permission grant | Admin UI → Permission Grants → add the service |
| Token expires mid-task | JWT TTL is 10 minutes | Claude Code should call `mintkey_request_token` again; if it doesn't, report as a bug |

---

## Once connected

See [`docs/HOW-TO.md`](../../HOW-TO.md) for the full operator cookbook — adding services,
rotating credentials, revoking agents, and reading the audit trail.

For the 10-minute demo with the built-in mock backend (no external keys needed), see
[`docs/guides/10min-mock-demo.md`](../10min-mock-demo.md).
