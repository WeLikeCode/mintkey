/**
 * AdminJS Permissions resource — T-1.4.3.
 *
 * READ: list permission grants via RestResource.
 * WRITE: create/revoke via apiWrite (session + CSRF, ADR-0014.5).
 *
 * Source: T-1.4.3; Req 6; ADR-0013; ADR-0014.5.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { apiWrite } from "../lib/api-client.js";

const _permissionsResource = new RestResource({
  id: "permission_grants", name: "Permissions",
  listPath: "/v1/tenants/{tenantId}/agents",
  listKey: "agents",
  idField: "id",
  properties: [
    { path: "id", type: "uuid", isId: true },
    { path: "name", type: "string" },
    { path: "status", type: "string" },
  ],
});

export const PermissionsResource: ResourceWithOptions & { adminResource: typeof _permissionsResource } = {
  resource: _permissionsResource.resource,
  adminResource: _permissionsResource,
  options: {
    navigation: { name: "Permissions", icon: "Shield" },
    listProperties: ["id", "agent_id", "service_id", "action", "created_at"],
    showProperties: ["id", "agent_id", "service_id", "action", "constraints", "created_at", "created_by"],
    editProperties: ["agent_id", "service_id", "action", "constraints"],
    filterProperties: ["agent_id", "service_id", "action"],
    properties: {
      constraints: {
        type: "mixed",
        isArray: false,
        // Render as JSON editor
        components: {},
      },
    },
    actions: {
      new: {
        isVisible: true,
        handler: async (request, response, context) => {
          const { resource, currentAdmin, record } = context;
          if (request.method === "get") {
            const emptyRecord = await resource.build({});
            return { record: emptyRecord.toJSON(currentAdmin) };
          }
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;

          let constraints: Record<string, unknown> = {};
          try {
            constraints = request.payload?.constraints
              ? JSON.parse(request.payload.constraints as string)
              : {};
          } catch {
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: "constraints must be valid JSON", type: "error" },
            };
          }

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/permissions`,
            "POST",
            {
              agent_id: request.payload?.agent_id,
              service_id: request.payload?.service_id,
              action: request.payload?.action,
              constraints,
            }
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Failed to grant permission", type: "error" },
            };
          }

          return {
            record: record?.toJSON(currentAdmin) ?? {},
            notice: { message: "Permission granted", type: "success" },
          };
        },
      },
      delete: {
        isVisible: true,
        handler: async (request, response, context) => {
          const { currentAdmin, record } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const permissionId = request.params.recordId;

          await apiWrite(
            `/v1/tenants/${tenantId}/permissions/${permissionId}`,
            "DELETE"
          );

          return { record: record?.toJSON(currentAdmin) ?? {} };
        },
      },
      edit: { isVisible: false },
    },
  },
};
