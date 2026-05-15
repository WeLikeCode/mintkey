/**
 * CHUNK 9: Tenants resource tests — PlatformAdmin only.
 *
 * Tests verify:
 * - TenantsResource exists
 * - delete action is not visible
 * - list action has assertPlatformAdmin guard (throws if not PlatformAdmin)
 * - new action requires PlatformAdmin
 * - isolation_mode has availableValues dropdown (UX-CLARITY chunk E)
 * - isolation_mode has description (UX-CLARITY chunk E)
 * - isolation_mode has NO JsonValue show component (UX-CLARITY chunk E)
 *
 * Source: ADMIN_UI_SPEC.md §2.9; T-1.12.4; ADR-0016.3.
 */

import { describe, it, expect } from "vitest";
import { TenantsResource } from "../src/resources/tenants.js";
import { Components } from "../src/components/index.js";

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

// ---------------------------------------------------------------------------
// UX-CLARITY chunk E: isolation_mode dropdown, description, no JsonValue
// ---------------------------------------------------------------------------

describe("TenantsResource — isolation_mode UX (UX-CLARITY chunk E)", () => {
  type PropertyOptions = {
    availableValues?: Array<{ value: string; label: string }>;
    description?: string;
    components?: { show?: unknown };
  };

  const isolationModeOpts = (
    TenantsResource.options?.properties as Record<string, PropertyOptions> | undefined
  )?.isolation_mode;

  it("isolation_mode has availableValues with exactly 2 entries", () => {
    expect(isolationModeOpts?.availableValues).toBeDefined();
    expect(Array.isArray(isolationModeOpts?.availableValues)).toBe(true);
    expect(isolationModeOpts?.availableValues?.length).toBe(2);
  });

  it("isolation_mode availableValues includes 'row' option", () => {
    const values = isolationModeOpts?.availableValues?.map((v) => v.value) ?? [];
    expect(values).toContain("row");
  });

  it("isolation_mode availableValues includes 'database' option", () => {
    const values = isolationModeOpts?.availableValues?.map((v) => v.value) ?? [];
    expect(values).toContain("database");
  });

  it("isolation_mode 'row' option has descriptive label", () => {
    const rowOpt = isolationModeOpts?.availableValues?.find((v) => v.value === "row");
    expect(rowOpt?.label).toBeTruthy();
    expect(typeof rowOpt?.label).toBe("string");
  });

  it("isolation_mode 'database' option has descriptive label", () => {
    const dbOpt = isolationModeOpts?.availableValues?.find((v) => v.value === "database");
    expect(dbOpt?.label).toBeTruthy();
    expect(typeof dbOpt?.label).toBe("string");
  });

  it("isolation_mode has a non-empty description", () => {
    expect(isolationModeOpts?.description).toBeTruthy();
    expect(typeof isolationModeOpts?.description).toBe("string");
    expect((isolationModeOpts?.description as string).length).toBeGreaterThan(20);
  });

  it("isolation_mode description mentions 'row'", () => {
    expect(isolationModeOpts?.description).toContain("row");
  });

  it("isolation_mode description mentions 'database'", () => {
    expect(isolationModeOpts?.description).toContain("database");
  });

  it("isolation_mode does NOT have JsonValue as show component (plain text rendering)", () => {
    // JsonValue caused broken rendering on the show page — must be absent
    const showComponent = isolationModeOpts?.components?.show;
    expect(showComponent).not.toBe(Components.JsonValue);
  });
});
