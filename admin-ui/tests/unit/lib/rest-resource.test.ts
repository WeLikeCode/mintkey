/**
 * Unit tests for RestResource.find() filter → query-param translation.
 *
 * Verifies that, per resource, supported filter keys in `params.filters` are
 * forwarded as admin-api query-string params, while unsupported keys are dropped.
 *
 * Source: admin-ui-search-filter-wiring chunk; ADR-0013; ADR-0014.5.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { RestResource } from "../../../src/lib/rest-resource.js";
import type { Filter, ActionContext } from "adminjs";
import { BaseProperty } from "adminjs";

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

type FilterValue = string | { from: string; to: string };

/**
 * Build a minimal AdminJS Filter-like object with real FilterElement shapes.
 * AdminJS stores each filter entry as a FilterElement:
 *   { path, property, value, populated? }
 * NOT as a raw string — this matches what AdminJS actually emits at runtime.
 */
function makeFilter(filters: Record<string, FilterValue>): Filter {
  const filterElements: Record<string, { path: string; property: BaseProperty; value: FilterValue }> = {};
  for (const [key, value] of Object.entries(filters)) {
    filterElements[key] = {
      path: key,
      property: new BaseProperty({ path: key, type: "string" }),
      value,
    };
  }
  return {
    filters: filterElements,
    reduce: () => ({}),
    populate: async () => ({}),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as unknown as Filter;
}

/** Build a minimal ActionContext with tenantId + sessionToken. */
function makeContext(tenantId: string): ActionContext {
  return {
    currentAdmin: { tenantId, sessionToken: "tok123" },
  } as unknown as ActionContext;
}

// ---------------------------------------------------------------------------
// fetch mock setup
// ---------------------------------------------------------------------------

const fetchMock = vi.fn();

beforeEach(() => {
  fetchMock.mockReset();
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (global as any).fetch = fetchMock;
  // Default: return empty list
  fetchMock.mockResolvedValue({
    ok: true,
    json: async () => ({ services: [], agents: [], items: [], permissions: [], api_keys: [], grants: [], data: [] }),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function capturedUrl(): string {
  expect(fetchMock).toHaveBeenCalledOnce();
  return fetchMock.mock.calls[0][0] as string;
}

// ---------------------------------------------------------------------------
// Services: q only
// ---------------------------------------------------------------------------

describe("Services resource — filter q forwarded as ?q=", () => {
  const res = new RestResource({
    id: "services",
    name: "Services",
    listPath: "/v1/tenants/{tenantId}/services",
    listKey: "services",
    idField: "id",
    properties: [
      { path: "id", type: "string", isId: true },
      { path: "name", type: "string" },
    ],
    filterKeys: ["q"],
  });

  it("appends ?q= when filter q is provided", async () => {
    await res.find(makeFilter({ q: "myservice" }), {}, makeContext("tid1"));
    const url = capturedUrl();
    expect(url).toContain("?q=myservice");
    expect(url).toContain("/v1/tenants/tid1/services");
  });

  it("no query string when filter is empty", async () => {
    await res.find(makeFilter({}), {}, makeContext("tid1"));
    const url = capturedUrl();
    expect(url).not.toContain("?");
  });

  it("ignores unknown filter keys", async () => {
    await res.find(makeFilter({ nonexistent: "x" }), {}, makeContext("tid1"));
    const url = capturedUrl();
    expect(url).not.toContain("nonexistent");
  });

  it("does not emit ?q= when value is empty string", async () => {
    await res.find(makeFilter({ q: "" }), {}, makeContext("tid1"));
    const url = capturedUrl();
    expect(url).not.toContain("q=");
    expect(url).not.toContain("?");
  });

  it("strips leading/trailing whitespace from filter value", async () => {
    await res.find(makeFilter({ q: "  crm  " }), {}, makeContext("tid1"));
    const url = capturedUrl();
    expect(url).toContain("q=crm");
    expect(url).not.toContain("q=++crm");
  });
});

// ---------------------------------------------------------------------------
// Agents: q + has_access_to_service_id
// ---------------------------------------------------------------------------

describe("Agents resource — q + has_access_to_service_id", () => {
  const res = new RestResource({
    id: "agents",
    name: "Agents",
    listPath: "/v1/tenants/{tenantId}/agents",
    listKey: "agents",
    idField: "id",
    properties: [{ path: "id", type: "string", isId: true }],
    filterKeys: ["q", "has_access_to_service_id"],
  });

  it("forwards q", async () => {
    await res.find(makeFilter({ q: "myagent" }), {}, makeContext("tid2"));
    expect(capturedUrl()).toContain("q=myagent");
  });

  it("forwards has_access_to_service_id (UUID)", async () => {
    await res.find(makeFilter({ has_access_to_service_id: "123e4567-e89b-12d3-a456-426614174000" }), {}, makeContext("tid2"));
    expect(capturedUrl()).toContain("has_access_to_service_id=123e4567-e89b-12d3-a456-426614174000");
  });

  it("forwards has_access_to_service_id (svc_ wire ID)", async () => {
    await res.find(makeFilter({ has_access_to_service_id: "svc_01HX5J9F" }), {}, makeContext("tid2"));
    expect(capturedUrl()).toContain("has_access_to_service_id=svc_01HX5J9F");
  });

  it("forwards both q and has_access_to_service_id together", async () => {
    await res.find(
      makeFilter({ q: "robot", has_access_to_service_id: "svc_01HX5J9F" }),
      {},
      makeContext("tid2"),
    );
    const url = capturedUrl();
    expect(url).toContain("q=robot");
    expect(url).toContain("has_access_to_service_id=svc_01HX5J9F");
  });
});

// ---------------------------------------------------------------------------
// Audit: q + event_type + actor_id + target_id + from_ts + to_ts
// ---------------------------------------------------------------------------

describe("Audit resource — multi-filter", () => {
  const res = new RestResource({
    id: "audit_events",
    name: "Audit Events",
    listPath: "/v1/tenants/{tenantId}/audit",
    listKey: "items",
    idField: "id",
    properties: [{ path: "id", type: "string", isId: true }],
    filterKeys: ["q", "event_type", "actor_id", "target_id", "from_ts", "to_ts"],
  });

  it("forwards event_type", async () => {
    await res.find(makeFilter({ event_type: "service.registered" }), {}, makeContext("tid3"));
    expect(capturedUrl()).toContain("event_type=service.registered");
  });

  it("forwards from_ts + to_ts (ISO 8601 as separate string entries)", async () => {
    await res.find(
      makeFilter({ from_ts: "2024-01-01T00:00:00Z", to_ts: "2024-12-31T23:59:59Z" }),
      {},
      makeContext("tid3"),
    );
    const url = capturedUrl();
    expect(url).toContain("from_ts=2024-01-01T00%3A00%3A00Z");
    expect(url).toContain("to_ts=2024-12-31T23%3A59%3A59Z");
  });

  it("forwards from_ts + to_ts (range object shape {from, to})", async () => {
    await res.find(
      makeFilter({ from_ts: { from: "2024-01-01T00:00:00Z", to: "2024-12-31T23:59:59Z" } }),
      {},
      makeContext("tid3"),
    );
    const url = capturedUrl();
    expect(url).toContain("from_ts=2024-01-01T00%3A00%3A00Z");
    expect(url).toContain("to_ts=2024-12-31T23%3A59%3A59Z");
  });

  it("forwards actor_id and target_id", async () => {
    await res.find(
      makeFilter({ actor_id: "op_abc", target_id: "svc_xyz" }),
      {},
      makeContext("tid3"),
    );
    const url = capturedUrl();
    expect(url).toContain("actor_id=op_abc");
    expect(url).toContain("target_id=svc_xyz");
  });
});

// ---------------------------------------------------------------------------
// Permissions: service_id only (no q)
// ---------------------------------------------------------------------------

describe("Permissions resource — service_id filter", () => {
  const res = new RestResource({
    id: "permission_grants",
    name: "Permissions",
    listPath: "/v1/tenants/{tenantId}/permissions",
    listKey: "grants",
    idField: "id",
    properties: [{ path: "id", type: "string", isId: true }],
    filterKeys: ["service_id"],
  });

  it("forwards service_id", async () => {
    await res.find(makeFilter({ service_id: "svc_01" }), {}, makeContext("tid4"));
    expect(capturedUrl()).toContain("service_id=svc_01");
  });

  it("ignores q (not in filterKeys)", async () => {
    await res.find(makeFilter({ q: "something" }), {}, makeContext("tid4"));
    expect(capturedUrl()).not.toContain("q=");
  });
});

// ---------------------------------------------------------------------------
// API Keys: q + service_id
// ---------------------------------------------------------------------------

describe("API Keys resource — q + service_id", () => {
  const res = new RestResource({
    id: "service_api_keys",
    name: "API Keys",
    listPath: "/v1/tenants/{tenantId}/api-keys",
    listKey: "api_keys",
    idField: "id",
    properties: [{ path: "id", type: "string", isId: true }],
    filterKeys: ["q", "service_id"],
  });

  it("forwards q (key_fingerprint prefix match)", async () => {
    await res.find(makeFilter({ q: "abc123" }), {}, makeContext("tid5"));
    expect(capturedUrl()).toContain("q=abc123");
  });

  it("forwards service_id", async () => {
    await res.find(makeFilter({ service_id: "svc_42" }), {}, makeContext("tid5"));
    expect(capturedUrl()).toContain("service_id=svc_42");
  });
});

// ---------------------------------------------------------------------------
// Tenants: q (slug / display_name)
// ---------------------------------------------------------------------------

describe("Tenants resource — q filter", () => {
  const res = new RestResource({
    id: "tenants",
    name: "Tenants",
    listPath: "/v1/tenants",
    listKey: "data",
    idField: "id",
    properties: [{ path: "id", type: "string", isId: true }],
    filterKeys: ["q"],
  });

  it("forwards q for tenants list (no tenantId substitution in listPath)", async () => {
    await res.find(makeFilter({ q: "acme" }), {}, makeContext("tid6"));
    // listPath has no {tenantId} — tenants are top-level
    const url = capturedUrl();
    expect(url).toContain("/v1/tenants");
    expect(url).toContain("q=acme");
  });
});

// ---------------------------------------------------------------------------
// X-Platform-Admin header propagation (ADR-0016.3)
// ---------------------------------------------------------------------------

/** Build a context with isPlatformAdmin flag. */
function makeContextWithPlatformAdmin(tenantId: string, isPlatformAdmin: boolean): ActionContext {
  return {
    currentAdmin: { tenantId, sessionToken: "tok123", isPlatformAdmin },
  } as unknown as ActionContext;
}

describe("X-Platform-Admin header propagation", () => {
  const res = new RestResource({
    id: "tenants",
    name: "Tenants",
    listPath: "/v1/tenants",
    listKey: "data",
    idField: "id",
    properties: [{ path: "id", type: "string", isId: true }],
    filterKeys: [],
  });

  it("sends X-Platform-Admin: true when isPlatformAdmin=true", async () => {
    await res.find(makeFilter({}), {}, makeContextWithPlatformAdmin("tid7", true));
    expect(fetchMock).toHaveBeenCalledOnce();
    const callHeaders = fetchMock.mock.calls[0][1]?.headers as Record<string, string> | undefined;
    expect(callHeaders?.["X-Platform-Admin"]).toBe("true");
  });

  it("omits X-Platform-Admin when isPlatformAdmin=false", async () => {
    await res.find(makeFilter({}), {}, makeContextWithPlatformAdmin("tid7", false));
    expect(fetchMock).toHaveBeenCalledOnce();
    const callHeaders = fetchMock.mock.calls[0][1]?.headers as Record<string, string> | undefined;
    expect(callHeaders?.["X-Platform-Admin"]).toBeUndefined();
  });

  it("omits X-Platform-Admin when context has no isPlatformAdmin field", async () => {
    await res.find(makeFilter({}), {}, makeContext("tid7"));
    expect(fetchMock).toHaveBeenCalledOnce();
    const callHeaders = fetchMock.mock.calls[0][1]?.headers as Record<string, string> | undefined;
    expect(callHeaders?.["X-Platform-Admin"]).toBeUndefined();
  });
});

// ---------------------------------------------------------------------------
// PropertyDef type:"mixed" — fix-show-page-react-31
// ---------------------------------------------------------------------------

describe("PropertyDef type:mixed (fix-show-page-react-31)", () => {
  it("accepts type:mixed in PropertyDef without TypeScript error", () => {
    // If this compiles, the PropertyDef union accepts "mixed".
    const mixedRes = new RestResource({
      id: "test_mixed",
      name: "Test Mixed",
      listPath: "/v1/test",
      listKey: "items",
      idField: "id",
      properties: [
        { path: "id", type: "string", isId: true },
        { path: "settings", type: "mixed" },
        { path: "constraints", type: "mixed" },
      ],
    });
    const props = mixedRes.properties();
    const settingsProp = props.find((p) => p.path() === "settings");
    expect(settingsProp?.type()).toBe("mixed");
    const constraintsProp = props.find((p) => p.path() === "constraints");
    expect(constraintsProp?.type()).toBe("mixed");
  });

  it("property() returns type:mixed for a mixed-typed property", () => {
    const mixedRes = new RestResource({
      id: "test_mixed2",
      name: "Test Mixed2",
      listPath: "/v1/test2",
      listKey: "items",
      idField: "id",
      properties: [{ path: "payload", type: "mixed" }],
    });
    const prop = mixedRes.property("payload");
    expect(prop).not.toBeNull();
    expect(prop?.type()).toBe("mixed");
  });
});
