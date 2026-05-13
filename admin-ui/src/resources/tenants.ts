/**
 * AdminJS Tenants resource — T-1.12.4.
 *
 * Visible ONLY to PlatformAdmin operators.
 * Includes cross-tenant view escape: when platformAdminView=true, the
 * list shows all tenants; when false, only the current tenant is shown.
 *
 * WRITE: create/edit tenant via apiWrite (session + CSRF, ADR-0014.5).
 *
 * Source: T-1.12.4; Req 13 AC1, AC6; ADR-0016.3.
 */

import type { ResourceWithOptions, ActionContext } from "adminjs";
import { apiWrite } from "../lib/api-client.js";
import { RestResource } from "../lib/rest-resource.js";
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

function assertPlatformAdmin(context: ActionContext): void {
  const admin = context.currentAdmin as { isPlatformAdmin?: boolean };
  if (!admin.isPlatformAdmin) {
    throw new Error("PlatformAdmin required");
  }
}

// Property set reconciled with what admin-api actually returns for
// GET /v1/tenants (`{ data: [...] }`): id, slug, display_name, status, settings,
// created_at, updated_at. `isolation_mode` is not in the response but is a field
// on the create form (CreateTenantRequest in the OpenAPI), so it stays declared
// here so AdminJS can render it on the `new` form without a "no property" warning.
const _tenantsResource = new RestResource({
  id: "tenants", name: "Tenants",
  listPath: "/v1/tenants",
  listKey: "data",
  idField: "id",
  filterKeys: ["q"],
  properties: [
    { path: "id", type: "uuid", isId: true },
    { path: "slug", type: "string" },
    { path: "display_name", type: "string" },
    { path: "status", type: "string" },
    { path: "settings", type: "mixed" },
    { path: "isolation_mode", type: "string" },
    { path: "created_at", type: "datetime" },
    { path: "updated_at", type: "datetime" },
    // Virtual filter-only: free-text search on slug / display_name
    { path: "q", type: "string" },
  ],
});

export const TenantsResource: ResourceWithOptions & { adminResource: typeof _tenantsResource } = {
  resource: _tenantsResource.resource,
  adminResource: _tenantsResource,
  options: {
    navigation: { name: "Tenants", icon: "Building" },
    listProperties: ["id", "slug", "display_name", "isolation_mode", "status", "created_at"],
    showProperties: ["id", "slug", "display_name", "isolation_mode", "status", "settings", "created_at", "updated_at"],
    newProperties: ["slug", "display_name", "isolation_mode"],
    editProperties: ["slug", "display_name", "isolation_mode"],
    filterProperties: ["q", "slug", "status"],
    properties: {
      q: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "Search (slug / name)",
        description: "Case-insensitive substring match on tenant slug and display_name.",
      },
      settings: {
        type: "mixed",
        components: { show: Components.JsonValue },
      },
      isolation_mode: {
        components: { show: Components.JsonValue },
      },
    },

    // Resource is visible only to PlatformAdmin
    // Non-PlatformAdmin gets empty results (RLS enforces tenant scope)
    actions: {
      list: {
        isVisible: ({ currentAdmin }: { currentAdmin?: { isPlatformAdmin?: boolean } }) =>
          currentAdmin?.isPlatformAdmin === true,
        component: Components.TenantsIntro,
        before: [
          async (request, context) => {
            assertPlatformAdmin(context);
            return request;
          },
        ],
      },
      new: {
        isVisible: true,
        handler: async (request, response, context) => {
          assertPlatformAdmin(context);
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }

          const resp = await apiWrite("/v1/tenants", "POST", request.payload);

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: err.title ?? "Failed to create tenant", type: "error" },
            };
          }

          return {
            record: await recordJSON(context, request.payload ?? {}),
            notice: { message: "Tenant created — genesis hash initialized", type: "success" },
            redirectUrl: "/admin/resources/tenants",
          };
        },
      },
      edit: {
        isVisible: true,
        handler: async (request, response, context) => {
          assertPlatformAdmin(context);
          if (request.method === "get") {
            return { record: await recordJSON(context, request.payload ?? {}) };
          }
          const targetTenantId = request.params.recordId;

          const resp = await apiWrite(
            `/v1/tenants/${targetTenantId}`,
            "PATCH",
            { display_name: request.payload?.display_name }
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: err.title ?? "Failed to update tenant", type: "error" },
            };
          }

          return { record: await recordJSON(context, request.payload ?? {}) };
        },
      },
      delete: { isVisible: false },
    },
  },
};
