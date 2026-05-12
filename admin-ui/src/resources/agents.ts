/**
 * AdminJS Agents resource — T-1.4.3 + T-1.9.4.
 *
 * READ: list agents via RestResource.
 * WRITE: create/revoke via apiWrite (session + CSRF, ADR-0014.5).
 *
 * The API key is shown exactly once in the create response (ADR-0014.4 /
 * Req 5 AC2). The AdminJS UI displays it as a one-time notice.
 *
 * Source: T-1.4.3; T-1.9.4; Req 5; ADR-0013; ADR-0014.5.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { apiWrite } from "../lib/api-client.js";

const _agentsResource = new RestResource({
  id: "agents", name: "Agents",
  listPath: "/v1/tenants/{tenantId}/agents",
  getPath: "/v1/tenants/{tenantId}/agents/{id}",
  listKey: "agents",
  idField: "id",
  properties: [
    { path: "id", type: "uuid", isId: true },
    { path: "name", type: "string" },
    { path: "description", type: "string" },
    { path: "status", type: "string" },
    { path: "api_key_fingerprint", type: "string" },
    { path: "mcp_endpoint", type: "string" },
    { path: "rate_limit_rps", type: "number" },
    { path: "created_at", type: "datetime" },
    { path: "updated_at", type: "datetime" },
  ],
});

export const AgentsResource: ResourceWithOptions & { adminResource: typeof _agentsResource } = {
  resource: _agentsResource.resource,
  adminResource: _agentsResource,
  options: {
    navigation: { name: "Agents", icon: "Bot" },
    // api_key_fingerprint in list/show — NEVER api_key (S-SEC-1)
    listProperties: ["id", "name", "status", "api_key_fingerprint", "rate_limit_rps", "created_at"],
    showProperties: ["id", "name", "description", "status", "api_key_fingerprint", "mcp_endpoint", "rate_limit_rps", "created_at", "updated_at"],
    editProperties: ["name", "description", "mcp_endpoint", "rate_limit_rps"],
    filterProperties: ["name", "status"],
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

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents`,
            "POST",
            request.payload
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Failed to create agent", type: "error" },
            };
          }

          const data = await resp.json() as { api_key?: string; id: string };
          return {
            record: record?.toJSON(currentAdmin) ?? {},
            notice: {
              // API key shown once — displayed in the notice banner (Req 5 AC2)
              message: data.api_key
                ? `Agent created. API key (shown once): ${data.api_key}`
                : "Agent created.",
              type: "success",
            },
            redirectUrl: "/admin/resources/agents",
          };
        },
      },

      // T-1.9.4: Revoke action
      revokeAgent: {
        actionType: "record",
        label: "Revoke",
        icon: "Ban",
        isVisible: (context) => {
          const record = context.record;
          return record?.get("status") !== "revoked";
        },
        handler: async (request, response, context) => {
          const { currentAdmin, record } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const agentId = request.params.recordId;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}/revoke`,
            "POST"
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Revocation failed", type: "error" },
            };
          }

          return {
            record: record?.toJSON(currentAdmin) ?? {},
            notice: {
              message: "Agent revoked — propagates to proxy plugin within ≤5s via mintkey:agent channel",
              type: "success",
            },
          };
        },
      },
    },
  },
};
