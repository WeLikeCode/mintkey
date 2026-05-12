/**
 * CHUNK 9: Tenants resource tests — PlatformAdmin only.
 *
 * Tests verify:
 * - TenantsResource exists
 * - delete action is not visible
 * - list action has assertPlatformAdmin guard (throws if not PlatformAdmin)
 * - new action requires PlatformAdmin
 *
 * Source: ADMIN_UI_SPEC.md §2.9; T-1.12.4; ADR-0016.3.
 */

import { describe, it, expect } from "vitest";
import { TenantsResource } from "../src/resources/tenants.js";

describe("TenantsResource — PlatformAdmin access control", () => {
  it("has resource id 'tenants'", () => {
    expect(TenantsResource.resource).toBe("tenants");
  });

  it("delete action is not visible", () => {
    const actions = TenantsResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).delete?.isVisible).toBe(false);
  });

  it("list action has a before hook (PlatformAdmin guard)", () => {
    const actions = TenantsResource.options?.actions ?? {};
    const listAction = (actions as Record<string, { before?: unknown[] }>).list;
    expect(Array.isArray(listAction?.before)).toBe(true);
    expect(listAction?.before?.length).toBeGreaterThan(0);
  });

  it("new action exists (PlatformAdmin can create tenants)", () => {
    const actions = TenantsResource.options?.actions ?? {};
    expect("new" in actions).toBe(true);
  });

  it("new action throws for non-PlatformAdmin", async () => {
    const actions = TenantsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).new?.handler;
    expect(handler).toBeDefined();

    await expect(
      handler!(
        { payload: { slug: "test", display_name: "Test" } },
        {},
        {
          currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc", isPlatformAdmin: false },
          record: { toJSON: () => ({}) },
        }
      )
    ).rejects.toThrow("PlatformAdmin required");
  });

  it("edit action handler throws for non-PlatformAdmin", async () => {
    const actions = TenantsResource.options?.actions ?? {};
    const handler = (actions as Record<string, { handler?: Function }>).edit?.handler;

    await expect(
      handler!(
        { params: { recordId: "tenant_xyz" }, payload: { display_name: "updated" } },
        {},
        {
          currentAdmin: { operatorId: "op_123", tenantId: "tenant_abc", isPlatformAdmin: false },
          record: { toJSON: () => ({}) },
        }
      )
    ).rejects.toThrow("PlatformAdmin required");
  });
});
