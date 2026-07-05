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

describe("PermissionsResource — UX-CLARITY field descriptions (Chunk D)", () => {
  it("action property has a description covering <verb>:<resource> pattern and `call` sentinel", () => {
    const props = (PermissionsResource.options?.properties ?? {}) as Record<string, { description?: string }>;
    const desc = props.action?.description ?? "";
    expect(desc).toBeTruthy();
    expect(desc).toMatch(/call/);
    expect(desc).toMatch(/<verb>:<resource>/);
    expect(desc).toMatch(/read:contacts|write:invoices|delete:invoices/);
  });

  it("constraints property has a description listing all allowed keys", () => {
    const props = (PermissionsResource.options?.properties ?? {}) as Record<string, { description?: string }>;
    const desc = props.constraints?.description ?? "";
    expect(desc).toBeTruthy();
    expect(desc).toMatch(/rate_limit/);
    expect(desc).toMatch(/time_window/);
    expect(desc).toMatch(/request_path_prefix/);
    expect(desc).toMatch(/source_ip_allowlist/);
    expect(desc).toMatch(/422/);
  });
});

describe("PermissionsResource — Budget management (Tasks 8.1-8.3)", () => {
  it("editBudget action is registered as a record action", () => {
    const actions = PermissionsResource.options?.actions ?? {};
    const editBudget = (actions as any).editBudget;
    expect(editBudget).toBeDefined();
    expect(editBudget.actionType).toBe("record");
    expect(editBudget.isVisible).toBe(true);
  });

  it("_budgetPanel virtual property has show component", () => {
    const props = PermissionsResource.options?.properties ?? {};
    expect((props as any)._budgetPanel).toBeDefined();
    expect((props as any)._budgetPanel.components.show).toBeDefined();
  });

  it("generic edit action remains disabled", () => {
    const actions = PermissionsResource.options?.actions ?? {};
    expect((actions as any).edit.isVisible).toBe(false);
  });

  it("_budgetPanel is in showProperties", () => {
    const showProps = PermissionsResource.options?.showProperties ?? [];
    expect(showProps).toContain("_budgetPanel");
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

  it("includes budget fields in constraints when budget_ceiling and budget_period are provided", async () => {
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
          budget_ceiling: "500",
          budget_period: "daily",
          budget_alert_thresholds: "50, 80, 100",
        },
      },
      {},
      {
        currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc" },
        record: { toJSON: () => ({}) },
      }
    );

    expect((capturedBody.constraints as any).budget).toEqual({
      ceiling: 500,
      period: "daily",
      alert_thresholds: [50, 80, 100],
    });
  });
});
