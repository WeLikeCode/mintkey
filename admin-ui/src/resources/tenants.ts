/**
 * AdminJS Tenants resource — T-1.12.4.
 *
 * Visible ONLY to PlatformAdmin operators.
 * Includes cross-tenant view escape: when platformAdminView=true, the
 * list shows all tenants; when false, only the current tenant is shown.
 *
 * WRITE: create/edit tenant via apiWrite (session + CSRF, ADR-0014.5).
 *
 * UX-BL4: crossTenantServicesList resource action — PlatformAdmin can fetch
 * services for any tenant. The panel calls this when viewed tenant ≠ session
 * tenant. The action forwards X-Platform-Admin:true and the operator's session
 * cookie to admin-api GET /v1/tenants/{tenant_id}/services.
 *
 * Source: T-1.12.4; Req 13 AC1, AC6; ADR-0016.3; UX-BL4.
 */

import type { ResourceWithOptions, ActionContext } from "adminjs";
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";
import { RestResource } from "../lib/rest-resource.js";
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

const ADMIN_API_URL = process.env.ADMIN_API_URL ?? "http://admin-api:8080";

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
//
// `_services_panel` is a virtual show-only property that renders the
// TenantServicesPanel component on the show page (UX-E).
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
    // Virtual show-only: associated services panel (UX-E)
    { path: "_services_panel", type: "string" },
  ],
});

export const TenantsResource: ResourceWithOptions & { adminResource: typeof _tenantsResource } = {
  resource: _tenantsResource.resource,
  adminResource: _tenantsResource,
  options: {
    navigation: { name: "Tenants", icon: "Building" },
    listProperties: ["id", "slug", "display_name", "isolation_mode", "status", "created_at"],
    showProperties: ["id", "slug", "display_name", "isolation_mode", "status", "settings", "created_at", "updated_at", "_services_panel"],
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
        availableValues: [
          { value: "row", label: "Row-level (RLS in shared tables)" },
          { value: "database", label: "Database-level (dedicated DB per tenant)" },
        ],
        description: `Determines how tenant data is isolated at the storage layer.
• \`row\` (default): data lives in shared tables with Postgres row-level security — fast onboarding, lower cost, fine for most tenants.
• \`database\`: each tenant gets a dedicated database/schema — required for regulatory isolation, slower onboarding, higher cost.
Cannot be changed after tenant creation.`,
      },
      // Virtual show-only panel: lists services belonging to this tenant (UX-E).
      // Component fetches services via the AdminJS list action for the "services"
      // resource, which the RestResource resolves against the session's tenantId.
      _services_panel: {
        isVisible: { list: false, show: true, edit: false, filter: false },
        label: "Services",
        components: { show: Components.TenantServicesPanel },
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
          const { currentAdmin } = context;
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const resp = await apiWrite("/v1/tenants", "POST", request.payload, operatorOpts);

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
          const { currentAdmin: ca } = context;
          const operatorOpts = operatorOptsFromAdmin(ca as Record<string, unknown>);
          const targetTenantId = request.params.recordId;

          const resp = await apiWrite(
            `/v1/tenants/${targetTenantId}`,
            "PATCH",
            { display_name: request.payload?.display_name },
            operatorOpts
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

      // UX-BL4: BFF passthrough — cross-tenant services list for PlatformAdmin.
      //
      // The panel calls this resource action when the viewed tenant differs from
      // the session tenant AND the operator is a PlatformAdmin. The action:
      //   1. Validates that the operator is a PlatformAdmin.
      //   2. Extracts the target tenant_id from the request query string.
      //   3. Fetches GET /v1/tenants/{tenant_id}/services from admin-api with:
      //        Cookie: mintkey_session=<operator session token>
      //        X-Platform-Admin: true
      //   4. Returns the services array in record.params.services.
      //
      // The non-PA case is blocked at step 1 — a 403-equivalent notice is returned
      // so the panel can render an empty state rather than leaking data.
      //
      // This is a GET (no CSRF needed). The operator-session cookie is threaded
      // through context.currentAdmin.sessionToken (set by RestResource._sessionHeaders).
      //
      // Source: UX-BL4; ADR-0016.3; admin-api _is_platform_admin MVP gate.
      crossTenantServicesList: {
        actionType: "resource" as const,
        isVisible: false,
        handler: async (request, _response, context) => {
          const admin = context.currentAdmin as {
            isPlatformAdmin?: boolean;
            sessionToken?: string;
          };

          // Gate: PlatformAdmin only
          if (!admin.isPlatformAdmin) {
            const baseRecord = await recordJSON(context, {});
            return {
              record: {
                ...baseRecord,
                params: { ...baseRecord.params, services: [], error: "PlatformAdmin required" },
              },
              services: [],
            };
          }

          const targetTenantId = (request.query?.tenant_id as string | undefined) ?? "";
          if (!targetTenantId) {
            const baseRecord = await recordJSON(context, {});
            return {
              record: { ...baseRecord, params: { ...baseRecord.params, services: [], error: "tenant_id query parameter required" } },
              services: [],
            };
          }

          const headers: Record<string, string> = {
            "X-Platform-Admin": "true",
          };
          if (admin.sessionToken) {
            headers["Cookie"] = `mintkey_session=${admin.sessionToken}`;
          }

          try {
            const resp = await fetch(
              `${ADMIN_API_URL}/v1/tenants/${encodeURIComponent(targetTenantId)}/services`,
              { headers }
            );

            if (!resp.ok) {
              const baseRecord = await recordJSON(context, {});
              return {
                record: { ...baseRecord, params: { ...baseRecord.params, services: [], error: `admin-api ${resp.status}` } },
                services: [],
              };
            }

            const data = await resp.json() as { services?: unknown[] };
            const services = Array.isArray(data.services) ? data.services : [];
            const baseRecord = await recordJSON(context, {});
            return {
              record: { ...baseRecord, params: { ...baseRecord.params, services } },
              services,
            };
          } catch (err: unknown) {
            const msg = err instanceof Error ? err.message : "fetch failed";
            const baseRecord = await recordJSON(context, {});
            return {
              record: { ...baseRecord, params: { ...baseRecord.params, services: [], error: msg } },
              services: [],
            };
          }
        },
      },
    },
  },
};
