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
import { isPlatformAdminView } from "../middleware/platform-admin.js";
import { RestResource } from "../lib/rest-resource.js";
import type { Request } from "express";

function assertPlatformAdmin(context: ActionContext): void {
  const admin = context.currentAdmin as { isPlatformAdmin?: boolean };
  if (!admin.isPlatformAdmin) {
    throw new Error("PlatformAdmin required");
  }
}

const _tenantsResource = new RestResource({
  id: "tenants", name: "Tenants",
  listPath: "/v1/tenants/{tenantId}/services",
  listKey: "services",
  idField: "id",
  properties: [
    { path: "id", type: "uuid", isId: true },
    { path: "slug", type: "string" },
    { path: "display_name", type: "string" },
    { path: "isolation_mode", type: "string" },
    { path: "created_at", type: "datetime" },
  ],
});

export const TenantsResource: ResourceWithOptions & { adminResource: typeof _tenantsResource } = {
  resource: _tenantsResource.resource,
  adminResource: _tenantsResource,
  options: {
    navigation: { name: "Tenants", icon: "Building" },
    listProperties: ["id", "slug", "display_name", "isolation_mode", "status", "created_at"],
    showProperties: ["id", "slug", "display_name", "isolation_mode", "status", "settings", "created_at", "updated_at"],
    editProperties: ["display_name", "status"],
    filterProperties: ["slug", "status"],

    // Resource is visible only to PlatformAdmin
    // Non-PlatformAdmin gets empty results (RLS enforces tenant scope)
    actions: {
      list: {
        isVisible: true,
        before: [
          async (request, context) => {
            assertPlatformAdmin(context);
            // Set X-Platform-Admin header on the underlying DB session
            // by checking req.session.platformAdminView
            const req = (context as { req?: Request }).req;
            if (req && isPlatformAdminView(req)) {
              // Signal admin-api to use app.platform_admin_view='on'
              (request as { headers?: Record<string, string> }).headers = {
                ...((request as { headers?: Record<string, string> }).headers ?? {}),
                "X-Platform-Admin": "true",
              };
            }
            return request;
          },
        ],
      },
      new: {
        isVisible: true,
        handler: async (request, response, context) => {
          assertPlatformAdmin(context);
          const { resource, currentAdmin, record } = context;
          if (request.method === "get") {
            const emptyRecord = await resource.build({});
            return { record: emptyRecord.toJSON(currentAdmin) };
          }

          const resp = await apiWrite("/v1/tenants", "POST", request.payload);

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Failed to create tenant", type: "error" },
            };
          }

          return {
            record: record?.toJSON(currentAdmin) ?? {},
            notice: { message: "Tenant created — genesis hash initialized", type: "success" },
            redirectUrl: "/admin/resources/tenants",
          };
        },
      },
      edit: {
        isVisible: true,
        handler: async (request, response, context) => {
          assertPlatformAdmin(context);
          const { currentAdmin, record } = context;
          if (request.method === "get") {
            return { record: record?.toJSON(currentAdmin) ?? {} };
          }
          const targetTenantId = request.params.recordId;

          const resp = await apiWrite(
            `/v1/tenants/${targetTenantId}`,
            "PATCH",
            request.payload
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Failed to update tenant", type: "error" },
            };
          }

          return { record: record?.toJSON(currentAdmin) ?? {} };
        },
      },
      delete: { isVisible: false },
    },
  },
};
