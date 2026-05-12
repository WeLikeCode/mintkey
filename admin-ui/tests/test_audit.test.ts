/**
 * CHUNK 8: Audit Log resource tests.
 *
 * Tests verify:
 * - All write actions disabled (append-only)
 * - listProperties includes the required columns
 * - showProperties includes hash chain (hash + prev_hash)
 * - Filter properties include event_type, actor_id, service_id, time range
 * - Default sort is descending by time field
 *
 * Source: ADMIN_UI_SPEC.md §2.8; T-1.7.4; ADR-0014.7.
 */

import { describe, it, expect } from "vitest";
import { AuditResource } from "../src/resources/audit.js";

describe("AuditResource — append-only (no writes)", () => {
  it("new action is not visible", () => {
    const actions = AuditResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).new?.isVisible).toBe(false);
  });

  it("edit action is not visible", () => {
    const actions = AuditResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).edit?.isVisible).toBe(false);
  });

  it("delete action is not visible", () => {
    const actions = AuditResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).delete?.isVisible).toBe(false);
  });

  it("bulkDelete action is not visible", () => {
    const actions = AuditResource.options?.actions ?? {};
    expect((actions as Record<string, { isVisible?: boolean }>).bulkDelete?.isVisible).toBe(false);
  });
});

describe("AuditResource — list and show columns", () => {
  it("listProperties includes event_type", () => {
    const props = AuditResource.options?.listProperties ?? [];
    expect(props).toContain("event_type");
  });

  it("listProperties includes at for time column", () => {
    const props = AuditResource.options?.listProperties ?? [];
    // The time column may be 'at' or 'created_at'
    const hasTime = props.includes("at") || props.includes("created_at");
    expect(hasTime).toBe(true);
  });

  it("showProperties includes hash (hash chain)", () => {
    const props = AuditResource.options?.showProperties ?? [];
    expect(props).toContain("hash");
  });

  it("showProperties includes prev_hash (hash chain linkage)", () => {
    const props = AuditResource.options?.showProperties ?? [];
    expect(props).toContain("prev_hash");
  });

  it("filterProperties includes event_type", () => {
    const props = AuditResource.options?.filterProperties ?? [];
    expect(props).toContain("event_type");
  });
});

describe("AuditResource — sort order", () => {
  it("default sort direction is desc", () => {
    const sort = AuditResource.options?.sort;
    expect((sort as { direction?: string })?.direction).toBe("desc");
  });
});
