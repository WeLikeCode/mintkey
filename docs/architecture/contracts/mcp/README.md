# MCP tool contracts — *iteration 4 placeholder*

This directory will contain the **typed MCP tool definitions** exposed to agents. Tools are catalogued in [`../README.md`](../README.md).

## Coming in iteration 4
- One JSON Schema (or TypeScript type) per tool input and output.
- A reference list of error codes.
- Examples per tool.
- Test fixtures usable by both the server (TDD) and SDKs (consumer tests).

## Conventions (preview)
- Tool names are stable; deprecation requires a new tool and a deprecation window.
- Tool inputs always include the implicit caller (the authenticated Agent); they never accept `agent_id` as a parameter.
- Tool outputs are JSON; large payloads (e.g., OpenAPI docs > 1 MB) are returned by URL, not inline.
- Error responses include both a machine code (e.g., `not_authorized`) and a human message.
