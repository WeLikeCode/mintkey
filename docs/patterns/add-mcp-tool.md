# Pattern: Add an MCP Tool to the MCP Server

## Goal

Use this guide to expose a new tool via the Mintkey MCP Server's JSON-RPC bridge. The MCP
Server uses Python + FastAPI with a JSON-RPC 2.0 transport (ADR-0009). Every tool is defined
in the contract first (`tools.yaml`), then implemented as a handler that the dispatcher routes
to. This guide covers schema authoring, handler implementation, auth validation, and tests.

---

## Where the change lives

- `docs/architecture/contracts/mcp/tools.yaml` — canonical tool catalog; edit this first (P-4)
- `mcp-server/src/mcp_server/tools/jsonrpc.py` — JSON-RPC dispatcher and tool-list builder
- `mcp-server/src/mcp_server/tools/<handler_module>.py` — tool handler logic (new file or
  extend an existing one; existing tools: `discovery.py`, `request_token.py`, `bootstrap.py`)
- `tests/unit/mcp_server/test_<handler_module>.py` — unit tests for the handler
- `tests/acceptance/test_mcp_auth_chain.py` — acceptance tests for auth + dispatch

---

## Step-by-step

1. **Write the tool schema first.** Add a new entry under `tools:` in
   `docs/architecture/contracts/mcp/tools.yaml`. Required fields: `name`, `description`,
   `inputSchema` (JSON Schema), `outputSchema` (JSON Schema). Mark sensitive output fields
   with `x-mintkey-sensitive: true`. Validate:
   ```bash
   python3 -c "import yaml; yaml.safe_load(open('docs/architecture/contracts/mcp/tools.yaml'))"
   ```

2. **Write a failing unit test.** In `tests/unit/mcp_server/test_<handler_module>.py`, add a
   test that calls the handler function directly and asserts the return value shape. It will
   fail until step 5.

3. **Create the handler module** (or extend an existing one). In
   `mcp-server/src/mcp_server/tools/<handler>.py`:
   ```python
   async def handle_mintkey_<tool_name>(params: dict, agent_ctx: AgentContext) -> dict:
       """
       Implements the mintkey_<tool_name> MCP tool.
       agent_ctx carries tenant_id, agent_id — never accept these from params (ADR-0008).
       """
       ...
       return {"result": ...}
   ```

4. **Validate the agent API key before any logic.** All tools that modify state or return
   sensitive data must assert `agent_ctx.authenticated is True`. The middleware populates this
   from the `Authorization: Bearer <Agent API Key>` header or the `MINTKEY_AGENT_API_KEY` env
   var. Never skip this check.

5. **Register the tool in the dispatcher.** In `mcp-server/src/mcp_server/tools/jsonrpc.py`:
   - Add the tool's input schema to the `_build_tools_list()` function.
   - Add an `if name == "mintkey_<tool_name>":` branch to `dispatch_tool()` that calls your
     handler.

6. **Run schema validation and tests:**
   ```bash
   make lint-contracts
   make test-unit
   ```

7. **Write an acceptance test** in `tests/acceptance/` that calls the tool via a real MCP
   JSON-RPC request against a running stack and asserts the response.

---

## Tests to write

- **Unit test** — `tests/unit/mcp_server/test_<handler_module>.py`: call the handler directly
  with a mock `AgentContext`; assert the correct response dict; assert that unauthenticated
  calls raise `AuthError`.
- **Schema validation test** — `tests/unit/mcp_server/test_<handler_module>.py`: load
  `tools.yaml` and assert the new tool's `inputSchema` validates a known-good payload and
  rejects a known-bad one using `jsonschema.validate`.
- **Acceptance test** — call the tool over JSON-RPC against a running stack; assert the HTTP
  200 response; assert the `result` field shape matches `outputSchema`.

---

## Common pitfalls

- **Schema mismatch between `tools.yaml` and the handler.** The JSON-RPC dispatcher validates
  input against the schema at call time. Write the schema and the handler together, not
  sequentially.
- **Accepting `tenant_id` or `agent_id` from the tool params.** These must come exclusively
  from `agent_ctx` (the authenticated context). User-supplied tenant IDs would break P-3.
- **Missing auth check.** Every tool handler must assert `agent_ctx.authenticated`. The
  dispatcher calls `authenticate_agent()` before routing, but defence-in-depth requires the
  handler to assert too.
- **Forgetting to add the tool to the dispatcher's `_build_tools_list()`.** The tool list is
  served to MCP clients at discovery time; if your tool isn't there, clients won't call it.
- **Using non-ULID IDs in tool responses.** All returned identifiers must follow the
  `^<prefix>_[0-9A-HJKMNP-TV-Z]{26}$` format (ADR-0017.11).

---

## References

- [ADR-0009 — MCP Server stack (Python + JSON-RPC)](../architecture/01-architecture/adr/0009-mcp-server-stack-python.md)
- [ADR-0008 — Multi-tenancy (tenant from auth context, never params)](../architecture/01-architecture/adr/0008-multi-tenancy-row-level-with-db-tier.md)
- [ADR-0017 — Round-3 corrections (ULID prefixes, § 0017.11)](../architecture/01-architecture/adr/0017-round-3-corrections.md)
- [MCP tool catalog contract](../architecture/contracts/mcp/tools.yaml)
- Existing tools to read as examples:
  - `mcp-server/src/mcp_server/tools/discovery.py` (`mintkey_list_services`, `mintkey_discover`)
  - `mcp-server/src/mcp_server/tools/request_token.py` (`mintkey_request_token`)
