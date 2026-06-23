# Admin API Client Notes (Task 0 — read once)

## Agent-key validation

- Endpoint: `POST /v1/internal/validate-agent-key`
- Request body: `{ api_key: string }` (required; the `mk_agent_`-prefixed plaintext key)
- 200 response body: `{ agent_id: string (ULID, agent_ prefix), tenant_id: string (ULID, tenant_ prefix), status: "active" }`
- Non-200: any 4xx → treat as invalid key; no body fields are consumed on failure
- Source in agent_key.py: `validate_agent_key()` at line 34, URL built as
  `f"{ADMIN_API_BASE}/v1/internal/validate-agent-key"` where
  `ADMIN_API_BASE = os.getenv("ADMIN_API_BASE_URL", "http://admin-api:8080")`

## Mintkey error envelope

The canonical schema is `components/schemas/Problem` (RFC 7807 + two Mintkey extensions):

| Field | Type | Notes |
|---|---|---|
| `mintkey:code` | string | machine-readable code (snake_case); checked first by jsonrpc.py |
| `title` | string | human-readable title |
| `detail` | string | human-readable detail sentence |
| `mintkey:trace_id` | string | 32-hex W3C trace-id |
| `type` / `status` / `instance` | RFC 7807 standard fields | |

**`reason_code` and `hint` are NOT in the Problem schema** but `_upstream_to_tool_result`
in `tools/jsonrpc.py` reads them defensively (`body.get("reason_code", "")`
and `body.get("hint", "")`) — these appear in email-proxy or other upstream
non-Problem error bodies, not in admin-api responses.

`_upstream_to_tool_result` reads: `mintkey:code` (fallback `code`), `title`,
`detail`, `reason_code`, `hint` — all optional via `.get(..., "")`.

## Additional admin-api calls from MCP handlers

`agent_key.py` makes only one call: `POST /v1/internal/validate-agent-key`.

Other HTTP calls in the mcp-server hit **different backends** (not admin-api):
- `tools/jsonrpc.py` — calls the MCP server's own internal `/v1/tools/*` routes
- `tools/request_token.py` — calls the broker/Kong proxy
- `tools/discovery.py` and email tools — call the email-proxy or Kong
- `vault/agent_secrets_client.py` — gRPC to vault-adapter, not HTTP to admin-api
