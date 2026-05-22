/**
 * CHUNK 5: Agents resource tests — one-time API key, connect snippet.
 *
 * Tests verify:
 * - AgentsResource has revokeAgent action
 * - listProperties includes api_key_fingerprint but NOT api_key
 * - showProperties includes api_key_fingerprint but NOT api_key
 * - getMcpConnectSnippet generates correct JSON snippet
 * - Agent create handler produces notice with API key (shown once)
 * - formatRelativeExpiry helper (UX-FB-AK-2)
 *
 * Source: ADMIN_UI_SPEC.md §2.5; T-1.4.3; T-1.9.4; ADR-0014.4; S-SEC-1.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { formatRelativeExpiry } from "../src/lib/key-expiry.js";
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

describe("AgentsResource — UX-CLARITY descriptive uplift (chunk C)", () => {
  it("api_key_fingerprint has updated label and description", () => {
    const props = AgentsResource.options?.properties ?? {};
    const fp = (props as Record<string, { label?: string; description?: string }>).api_key_fingerprint;
    expect(fp?.label).toBe("API Key Fingerprint (SHA-256 prefix)");
    expect(fp?.description).toMatch(/First 16 hex chars of SHA-256/);
    expect(fp?.description).toMatch(/cannot be reversed/);
  });

  it("mcp_endpoint has description explaining mcpServers config", () => {
    const props = AgentsResource.options?.properties ?? {};
    const ep = (props as Record<string, { description?: string }>).mcp_endpoint;
    expect(ep?.description).toMatch(/mcpServers\.mintkey\.url/);
    expect(ep?.description).toMatch(/\/v1\/tools/);
  });

  it("rate_limit_rps has description covering blank and 0 semantics", () => {
    const props = AgentsResource.options?.properties ?? {};
    const rps = (props as Record<string, { description?: string }>).rate_limit_rps;
    expect(rps?.description).toMatch(/Requests per second cap/);
    expect(rps?.description).toMatch(/emergency stop/);
  });

  it("status has availableValues with active and revoked", () => {
    const props = AgentsResource.options?.properties ?? {};
    const status = (props as Record<string, { availableValues?: { value: string; label: string }[] }>).status;
    expect(status?.availableValues).toBeDefined();
    const values = (status?.availableValues ?? []).map((v) => v.value);
    expect(values).toContain("active");
    expect(values).toContain("revoked");
    // Each entry must have a label too
    for (const entry of status?.availableValues ?? []) {
      expect(entry.label).toBeTruthy();
    }
  });

  it("revokeAgent action has description for permanent-revocation copy", () => {
    const actions = AgentsResource.options?.actions ?? {};
    const revoke = (actions as Record<string, { custom?: { description?: string } }>).revokeAgent;
    expect(revoke?.custom?.description).toMatch(/permanent/i);
    expect(revoke?.custom?.description).toMatch(/create a new agent/i);
  });

  it("revokeAgent description is wired via action.custom (AdminJS serializes custom, not description)", () => {
    const actions = AgentsResource.options?.actions ?? {};
    const revoke = (actions as Record<string, { custom?: { description?: string } }>).revokeAgent;
    expect(revoke).toBeDefined();
    expect(revoke?.custom).toBeDefined();
    expect(revoke?.custom?.description).toBeTruthy();
  });
});

describe("formatRelativeExpiry — UX-FB-AK-2", () => {
  it("returns Never / tone=never for null", () => {
    const result = formatRelativeExpiry(null);
    expect(result.label).toBe("Never");
    expect(result.tone).toBe("never");
    expect(result.absolute).toBe("");
  });

  it("returns Never / tone=never for undefined", () => {
    const result = formatRelativeExpiry(undefined);
    expect(result.label).toBe("Never");
    expect(result.tone).toBe("never");
  });

  it("returns 'in N days' / tone=ok for 10 days in the future (> 7 day threshold)", () => {
    const tenDays = new Date(Date.now() + 10 * 86_400_000).toISOString();
    const result = formatRelativeExpiry(tenDays);
    expect(result.label).toMatch(/^in \d+ days?$/);
    expect(result.tone).toBe("ok");
  });

  it("returns 'in N days' / tone=warn for 2 days in the future (< 7 days)", () => {
    const twoDays = new Date(Date.now() + 2 * 86_400_000).toISOString();
    const result = formatRelativeExpiry(twoDays);
    expect(result.label).toMatch(/^in \d+ days?$/);
    expect(result.tone).toBe("warn");
  });

  it("returns 'Expired N hours ago' / tone=expired for 1 hour in the past", () => {
    const oneHourAgo = new Date(Date.now() - 3_600_000).toISOString();
    const result = formatRelativeExpiry(oneHourAgo);
    expect(result.label).toMatch(/^Expired \d+ hours? ago$/);
    expect(result.tone).toBe("expired");
  });

  it("absolute contains ISO string for non-null expiry", () => {
    const iso = new Date(Date.now() + 10 * 86_400_000).toISOString();
    const result = formatRelativeExpiry(iso);
    expect(result.absolute).toMatch(/^\d{4}-\d{2}-\d{2}T/);
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
