/**
 * Form-record regression tests — Bug 1 (`record.errors is undefined` /
 * `Cannot read properties of undefined`).
 *
 * The custom new/edit action handlers must return a well-formed RecordJSON
 * (one with `params` and `errors` objects), never `{}` — otherwise AdminJS's
 * frontend form renderer throws a TypeError for every property. The bug bites
 * hardest after a failed submit (admin-api 422): the handler used
 * `record?.toJSON(currentAdmin) ?? {}` and `context.record` is always undefined
 * for a `new` action, so it returned `{ record: {} }` — a record with no
 * `params` / `errors` objects.
 *
 * These tests drive the real handlers with a real RestResource (decorated by a
 * real AdminJS instance) and a stubbed `fetch`.
 *
 * Source: ADMIN_UI_SPEC.md §4 (unit tests must drive the handlers); AdminJS 7.x
 * New/Edit form renderer.
 */

import { describe, it, expect, beforeAll, afterEach, vi } from "vitest";
import AdminJS from "adminjs";
import { RestDatabase, RestResource } from "../src/lib/rest-resource.js";
import { ServicesResource } from "../src/resources/services.js";
import { AgentsResource } from "../src/resources/agents.js";
import { PermissionsResource } from "../src/resources/permissions.js";
import { CredentialsResource } from "../src/resources/credentials.js";
import { ApiKeysResource } from "../src/resources/api_keys.js";
import { TenantsResource } from "../src/resources/tenants.js";

AdminJS.registerAdapter({ Database: RestDatabase, Resource: RestResource });

let admin: AdminJS;

beforeAll(() => {
  admin = new AdminJS({
    rootPath: "/admin",
    resources: [
      { resource: ServicesResource.adminResource, options: ServicesResource.options },
      { resource: AgentsResource.adminResource, options: AgentsResource.options },
      { resource: PermissionsResource.adminResource, options: PermissionsResource.options },
      { resource: CredentialsResource.adminResource, options: CredentialsResource.options },
      { resource: ApiKeysResource.adminResource, options: ApiKeysResource.options },
      { resource: TenantsResource.adminResource, options: TenantsResource.options },
    ],
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

type Handlers = Record<string, { handler?: (req: unknown, res: unknown, ctx: unknown) => Promise<unknown> }>;

function ctx(resourceId: string, extra: Record<string, unknown> = {}) {
  const resource = admin.findResource(resourceId);
  return {
    resource,
    currentAdmin: { operatorId: "op_1", tenantId: "tenant_abc", email: "a@b.c", isPlatformAdmin: true },
    h: (resource as unknown as { decorate(): { h: unknown } }).decorate().h,
    ...extra,
  };
}

function stubFetch(status: number, body: unknown) {
  vi.spyOn(globalThis, "fetch").mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
    headers: { get: () => null, getSetCookie: () => [] },
    json: async () => body,
  } as unknown as Response);
}

function assertWellFormedRecord(result: unknown) {
  const r = result as { record?: { params?: unknown; errors?: unknown } };
  expect(r.record, "handler must return a record").toBeTruthy();
  expect(typeof r.record!.params, "record.params must be an object (the form renderer does record.params[path])").toBe("object");
  expect(r.record!.params).not.toBeNull();
  expect(typeof r.record!.errors, "record.errors must be an object (the form renderer does record.errors[path])").toBe("object");
  expect(r.record!.errors).not.toBeNull();
}

describe("Bug 1 — new-action handlers return a well-formed RecordJSON", () => {
  // service_api_keys intentionally has no `new` handler — creation is via the
  // custom createApiKey action (spec §2.7); it is exercised separately below.
  for (const [name, resourceId, res, payload] of [
    ["tenants", "tenants", TenantsResource, { slug: "x", display_name: "X" }],
    ["services", "services", ServicesResource, { name: "S", slug: "s" }],
    ["agents", "agents", AgentsResource, { name: "A" }],
    ["permission_grants", "permission_grants", PermissionsResource, { agent_id: "a", service_id: "s", action: "read" }],
    ["credentials", "credentials", CredentialsResource, { service_id: "s", auth_scheme: "none" }],
  ] as const) {
    it(`${name}: GET (render fresh form) → record with params + errors`, async () => {
      const handler = (res.options.actions as Handlers).new?.handler!;
      expect(handler, `${name} must have a new-action handler`).toBeDefined();
      const result = await handler({ method: "get", params: {}, payload: {} }, {}, ctx(resourceId));
      assertWellFormedRecord(result);
    });

    it(`${name}: POST that admin-api rejects (422) → record with params + errors, plus an error notice`, async () => {
      stubFetch(422, { title: "Validation failed", "mintkey:code": "validation_error" });
      const handler = (res.options.actions as Handlers).new?.handler!;
      const result = await handler(
        { method: "post", params: {}, payload },
        {},
        ctx(resourceId)
      );
      assertWellFormedRecord(result);
      const r = result as { notice?: { type?: string } };
      expect(r.notice?.type).toBe("error");
    });
  }
});

describe("Bug 1 — edit-action handlers return a well-formed RecordJSON when context.record is absent", () => {
  it("services edit: GET → record with params + errors", async () => {
    const handler = (ServicesResource.options.actions as Handlers).edit?.handler!;
    const result = await handler({ method: "get", params: { recordId: "svc_1" }, payload: {} }, {}, ctx("services"));
    assertWellFormedRecord(result);
  });

  it("tenants edit: GET → record with params + errors", async () => {
    const handler = (TenantsResource.options.actions as Handlers).edit?.handler!;
    const result = await handler({ method: "get", params: { recordId: "tenant_1" }, payload: {} }, {}, ctx("tenants"));
    assertWellFormedRecord(result);
  });
});
