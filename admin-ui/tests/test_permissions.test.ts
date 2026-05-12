/**
 * CHUNK 6: Permissions resource tests.
 *
 * Tests verify:
 * - PermissionsResource has correct new action
 * - New action POSTs to /v1/tenants/{tid}/permissions (NOT agent-nested path)
 * - Constraints validation: valid JSON accepted, invalid JSON rejected
 * - edit action is not visible
 *
 * Source: ADMIN_UI_SPEC.md §2.6; T-1.4.3; ADR-0014.5.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { PermissionsResource } from "../src/resources/permissions.js";

// Mock signed-request
vi.mock("../src/lib/signed-request.js", () => ({
  buildSignedRequest: vi.fn().mockResolvedValue("mock.jwt.token"),
}));

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

describe("PermissionsResource configuration", () => {
  it("has resource id permission_grants", () => {
    expect(PermissionsResource.resource).toBe("permission_grants");
  });

  it("edit action is not visible", () => {
    const actions = PermissionsResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).edit?.isVisible).toBe(false);
  });

  it("new action exists", () => {
    const actions = PermissionsResource.options?.actions ?? {};
    expect("new" in actions).toBe(true);
  });

  it("delete action exists", () => {
    const actions = PermissionsResource.options?.actions ?? {};
    expect("delete" in actions).toBe(true);
  });
});

describe("PermissionsResource — new action handler", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("POSTs to /v1/tenants/{tid}/permissions with agent_id, service_id, action, constraints", async () => {
    let capturedUrl = "";
    let capturedBody = {};
    mockFetch.mockImplementation(async (url: string, opts: { body: string }) => {
      capturedUrl = url;
      capturedBody = JSON.parse(opts.body);
      return { ok: true, json: async () => ({ id: "perm_abc" }) };
    });

    const actions = PermissionsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;

    await handler!(
      {
        payload: {
          agent_id: "agent_abc",
          service_id: "svc_xyz",
          action: "call",
          constraints: '{"max_calls_per_day": 100}',
        },
      },
      {},
      {
        currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc" },
        record: { toJSON: () => ({}) },
      }
    );

    expect(capturedUrl).toContain("/v1/tenants/tenant_abc/permissions");
    expect((capturedBody as Record<string, unknown>).agent_id).toBe("agent_abc");
    expect((capturedBody as Record<string, unknown>).service_id).toBe("svc_xyz");
    expect((capturedBody as Record<string, unknown>).constraints).toEqual({ max_calls_per_day: 100 });
  });

  it("returns error notice when constraints is invalid JSON", async () => {
    const actions = PermissionsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;

    const result = await handler!(
      {
        payload: {
          agent_id: "agent_abc",
          service_id: "svc_xyz",
          action: "call",
          constraints: "not-valid-json{",
        },
      },
      {},
      {
        currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc" },
        record: { toJSON: () => ({}) },
      }
    );

    expect(result.notice?.type).toBe("error");
    expect(result.notice?.message).toContain("JSON");
  });

  it("accepts empty constraints (defaults to {})", async () => {
    let capturedBody = {} as Record<string, unknown>;
    mockFetch.mockImplementation(async (_url: string, opts: { body: string }) => {
      capturedBody = JSON.parse(opts.body);
      return { ok: true, json: async () => ({ id: "perm_abc" }) };
    });

    const actions = PermissionsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;

    await handler!(
      {
        payload: {
          agent_id: "agent_abc",
          service_id: "svc_xyz",
          action: "call",
          constraints: "",
        },
      },
      {},
      {
        currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc" },
        record: { toJSON: () => ({}) },
      }
    );

    expect(capturedBody.constraints).toEqual({});
  });
});
