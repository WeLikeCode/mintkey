/**
 * CHUNK 7: API Keys UI tests.
 *
 * Tests verify:
 * - createApiKey action exists and is resource-level
 * - listProperties/showProperties never include plaintext key
 * - revokeApiKey action exists and is record-level
 * - rotateApiKey action exists and is record-level
 * - create handler returns plaintext key in notice (one-time)
 * - list/show never includes key_hash or plaintext_key
 *
 * Source: ADMIN_UI_SPEC.md §2.7; ADR-0018 §1.3; S-SEC-1.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { ApiKeysResource } from "../src/resources/api_keys.js";

vi.mock("../src/lib/signed-request.js", () => ({
  buildSignedRequest: vi.fn().mockResolvedValue("mock.jwt.token"),
}));

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("ApiKeysResource — security properties", () => {
  it("listProperties never includes key_hash or plaintext_key", () => {
    const listProps = ApiKeysResource.options?.listProperties ?? [];
    expect(listProps).not.toContain("key_hash");
    expect(listProps).not.toContain("plaintext_key");
    expect(listProps).not.toContain("api_key");
  });

  it("showProperties never includes key_hash or plaintext_key", () => {
    const showProps = ApiKeysResource.options?.showProperties ?? [];
    expect(showProps).not.toContain("key_hash");
    expect(showProps).not.toContain("plaintext_key");
    expect(showProps).not.toContain("api_key");
  });

  it("showProperties includes key_fingerprint", () => {
    const showProps = ApiKeysResource.options?.showProperties ?? [];
    expect(showProps).toContain("key_fingerprint");
  });
});

describe("ApiKeysResource — actions", () => {
  it("new action is hidden (create via createApiKey only)", () => {
    const actions = ApiKeysResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).new?.isVisible).toBe(false);
  });

  it("edit action is hidden", () => {
    const actions = ApiKeysResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).edit?.isVisible).toBe(false);
  });

  it("delete action is hidden (use revoke instead)", () => {
    const actions = ApiKeysResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).delete?.isVisible).toBe(false);
  });

  it("createApiKey action is resource-level and visible", () => {
    const actions = ApiKeysResource.options?.actions ?? {};
    expect("createApiKey" in actions).toBe(true);
    expect((actions as Record<string, { actionType?: string }>).createApiKey?.actionType).toBe("resource");
    expect((actions as Record<string, { isVisible?: boolean }>).createApiKey?.isVisible).toBe(true);
  });

  it("revokeApiKey action is record-level", () => {
    const actions = ApiKeysResource.options?.actions ?? {};
    expect("revokeApiKey" in actions).toBe(true);
    expect((actions as Record<string, { actionType?: string }>).revokeApiKey?.actionType).toBe("record");
  });

  it("rotateApiKey action is record-level", () => {
    const actions = ApiKeysResource.options?.actions ?? {};
    expect("rotateApiKey" in actions).toBe(true);
    expect((actions as Record<string, { actionType?: string }>).rotateApiKey?.actionType).toBe("record");
  });
});

describe("ApiKeysResource — createApiKey handler", () => {
  beforeEach(() => vi.clearAllMocks());

  it("returns one-time key in notice when created", async () => {
    mockFetch.mockResolvedValueOnce({
      ok: true,
      json: async () => ({ id: "apikey_abc", plaintext_key: "mintkey.key.supersecret" }),
    });

    const actions = ApiKeysResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).createApiKey?.handler;

    const result = await handler!(
      { payload: { agent_id: "agent_abc", service_id: "svc_xyz", allowed_actions: ["call"] } },
      {},
      {
        currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc" },
        record: { toJSON: () => ({}) },
      }
    );

    expect(result.notice?.type).toBe("success");
    expect(result.notice?.message).toContain("mintkey.key.supersecret");
    expect(result.notice?.message).toMatch(/shown once|store it now/i);
  });

  it("returns error if agent_id is missing", async () => {
    const actions = ApiKeysResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).createApiKey?.handler;

    const result = await handler!(
      { payload: {} },
      {},
      {
        currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc" },
        record: { toJSON: () => ({}) },
      }
    );

    expect(result.notice?.type).toBe("error");
    expect(result.notice?.message).toContain("agent_id");
  });
});
