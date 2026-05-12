/**
 * CHUNK 5: Agents resource tests — one-time API key, connect snippet.
 *
 * Tests verify:
 * - AgentsResource has revokeAgent action
 * - listProperties includes api_key_fingerprint but NOT api_key
 * - showProperties includes api_key_fingerprint but NOT api_key
 * - getMcpConnectSnippet generates correct JSON snippet
 * - Agent create handler produces notice with API key (shown once)
 *
 * Source: ADMIN_UI_SPEC.md §2.5; T-1.4.3; T-1.9.4; ADR-0014.4; S-SEC-1.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { AgentsResource } from "../src/resources/agents.js";
import { getMcpConnectSnippet } from "../src/lib/mcp-connect.js";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

// Mock signed-request to avoid needing the private key file
vi.mock("../src/lib/signed-request.js", () => ({
  buildSignedRequest: vi.fn().mockResolvedValue("mock.jwt.token"),
}));

describe("AgentsResource — list/show property safety", () => {
  it("listProperties contains api_key_fingerprint not api_key", () => {
    const listProps = AgentsResource.options?.listProperties ?? [];
    expect(listProps).toContain("api_key_fingerprint");
    expect(listProps).not.toContain("api_key");
  });

  it("showProperties contains api_key_fingerprint not api_key", () => {
    const showProps = AgentsResource.options?.showProperties ?? [];
    expect(showProps).toContain("api_key_fingerprint");
    expect(showProps).not.toContain("api_key");
  });

  it("revokeAgent action exists and is record-level", () => {
    const actions = AgentsResource.options?.actions ?? {};
    expect("revokeAgent" in actions).toBe(true);
    expect((actions as Record<string, { actionType?: string }>).revokeAgent?.actionType).toBe("record");
  });
});

describe("AgentsResource — create handler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("create handler returns notice containing API key when returned by admin-api", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "agent_test001", api_key: "mintkey.agent.secretkey" }),
    });

    const actions = AgentsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;
    expect(handler).toBeDefined();

    const result = await handler!(
      { payload: { name: "TestAgent", description: "test" } },
      {},
      {
        currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc" },
        record: { toJSON: () => ({}) },
      }
    );

    expect(result.notice?.type).toBe("success");
    expect(result.notice?.message).toContain("mintkey.agent.secretkey");
  });

  it("create handler returns error notice on failure", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: false,
      json: async () => ({ title: "Name already in use" }),
    });

    const actions = AgentsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;

    const result = await handler!(
      { payload: { name: "DuplicateAgent" } },
      {},
      {
        currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc" },
        record: { toJSON: () => ({}) },
      }
    );

    expect(result.notice?.type).toBe("error");
    expect(result.notice?.message).toContain("Name already in use");
  });
});

describe("getMcpConnectSnippet", () => {
  it("generates a valid JSON snippet with mcp_endpoint", () => {
    const snippet = getMcpConnectSnippet({
      agentId: "agent_abc123",
      mcpEndpoint: "http://mcp.example.com/mcp",
      apiKeyHint: "mintkey.agent.XXXX",
    });

    expect(snippet).toContain("mcp.example.com");
    expect(snippet).toContain("agent_abc123");
    // Should be valid JSON
    const parsed = JSON.parse(snippet);
    expect(parsed).toBeTruthy();
  });

  it("snippet does not contain plaintext API key value", () => {
    const snippet = getMcpConnectSnippet({
      agentId: "agent_abc123",
      mcpEndpoint: "http://mcp.example.com/mcp",
      apiKeyHint: "mintkey.agent.XXXX",
    });

    // Should not contain 'XXXX' - only the hint prefix form
    expect(snippet).not.toContain("mintkey.agent.XXXX");
    // Should reference where to put the key, not the key itself
    expect(snippet).toMatch(/<your[_\- ]?api[_\- ]?key>/i);
  });
});
