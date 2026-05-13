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
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

const _agentsResource = new RestResource({
  id: "agents", name: "Agents",
  listPath: "/v1/tenants/{tenantId}/agents",
  listKey: "agents",
  idField: "id",
  filterKeys: ["q", "has_access_to_service_id"],
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "name", type: "string" },
    { path: "description", type: "string" },
    { path: "status", type: "string" },
    { path: "api_key_fingerprint", type: "string" },
    { path: "mcp_endpoint", type: "string" },
    { path: "rate_limit_rps", type: "number" },
    { path: "created_at", type: "datetime" },
    { path: "updated_at", type: "datetime" },
    // Virtual filter-only properties
    { path: "q", type: "string" },
    { path: "has_access_to_service_id", type: "string" },
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
    filterProperties: ["q", "has_access_to_service_id", "name", "status"],
    properties: {
      q: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "Search (name)",
        description: "Case-insensitive substring match on agent name.",
      },
      has_access_to_service_id: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "Has access to service (ID)",
        description: "Filter agents that have a permission grant for this service. Paste a UUID or svc_… wire ID.",
      },
    },
    actions: {
      list: {
        component: Components.AgentsIntro,
      },
      new: {
        isVisible: true,
        handler: async (request, response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents`,
            "POST",
            request.payload
          );

          const body = await resp.json().catch(() => ({})) as { api_key?: string; id?: string; title?: string };

          if (!resp.ok) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: body.title ?? "Failed to create agent", type: "error" },
            };
          }

          return {
            record: await recordJSON(context, request.payload ?? {}),
            notice: {
              // API key shown once — displayed in the notice banner (Req 5 AC2)
              // Agent ID embedded in brackets so E2E tests can parse it without URL dependency.
              message: body.api_key
                ? `Agent created [${body.id}]. API key (shown once): ${body.api_key}`
                : `Agent created [${body.id}].`,
              type: "success",
            },
            redirectUrl: `/admin/resources/agents/records/${body.id}/show`,
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
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const agentId = request.params.recordId;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}/revoke`,
            "POST"
          );

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context),
              notice: { message: err.title ?? "Revocation failed", type: "error" },
            };
          }

          return {
            record: await recordJSON(context),
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
