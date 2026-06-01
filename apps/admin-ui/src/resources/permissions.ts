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
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

/**
 * Normalise a bare UUID agent_id to wire-form (agent_<32hex>) per ADR-0017.
 *
 * The /v1/tenants/{tid}/permissions endpoint returns agent_id as a plain UUID
 * (e.g. "6c3c950a-2e18-4ba9-8c89-5b875b1bf5bd") while the agents list endpoint
 * returns IDs in wire-form (e.g. "agent_6c3c950a2e184ba98c895b875b1bf5bd").
 * ApiKeyCreate.tsx compares r.params.agent_id === agentId where agentId comes
 * from the agents dropdown — so the formats must match.  Normalising here at the
 * BFF boundary (ADR-0017: wire-form on the wire) fixes the comparison for ALL
 * downstream consumers of permission_grants records, not just ApiKeyCreate.
 */
function normalisePermissionRecord(item: Record<string, unknown>): Record<string, unknown> {
  const agentId = item.agent_id;
  if (typeof agentId === "string" && agentId.length > 0 && !agentId.startsWith("agent_")) {
    // Bare UUID — convert to agent_<32hex> wire-form
    const hex32 = agentId.replace(/-/g, "");
    if (hex32.length === 32) {
      return { ...item, agent_id: `agent_${hex32}` };
    }
  }
  return item;
}

const _permissionsResource = new RestResource({
  id: "permission_grants", name: "Permissions",
  listPath: "/v1/tenants/{tenantId}/permissions",
  listKey: "permissions",
  idField: "id",
  filterKeys: ["q", "service_id"],
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "agent_id", type: "string" },
    { path: "service_id", type: "string" },
    { path: "action", type: "string" },
    { path: "constraints", type: "mixed" },
    { path: "created_at", type: "datetime" },
    { path: "created_by", type: "string" },
    // UX-BL1: denormalised display fields from services/agents JOIN (read-only)
    { path: "service_name", type: "string" },
    { path: "service_slug", type: "string" },
    { path: "agent_name", type: "string" },
    // Virtual filter-only: free-text search on action
    { path: "q", type: "string" },
  ],
  // ADR-0017: normalise agent_id from bare UUID to wire-form (agent_<32hex>)
  // at the BFF boundary so all consumers see consistent wire shapes.
  // Fixes: ApiKeyCreate.tsx service dropdown empty due to agent_id format mismatch
  // between permissions list (UUID) and agents list (wire-form). (R10-redux)
  recordTransform: normalisePermissionRecord,
});

export const PermissionsResource: ResourceWithOptions & { adminResource: typeof _permissionsResource } = {
  resource: _permissionsResource.resource,
  adminResource: _permissionsResource,
  options: {
    navigation: { name: "Permissions", icon: "Shield" },
    listProperties: ["id", "agent_id", "agent_name", "service_id", "service_name", "action", "created_at"],
    showProperties: ["id", "agent_id", "agent_name", "service_id", "service_name", "service_slug", "action", "constraints", "created_at", "created_by"],
    editProperties: ["agent_id", "service_id", "action", "constraints"],
    filterProperties: ["q", "agent_id", "service_id", "action"],
    properties: {
      q: {
        isVisible: { list: false, show: false, edit: false, filter: true },
        label: "Search (action)",
        description: "Search by action (e.g., 'read', 'write').",
      },
      // UX-A: replace plain text inputs with typeahead comboboxes for agent + service
      agent_id: {
        isVisible: { list: true, show: true, edit: true, filter: true },
        components: { edit: Components.AgentCombobox },
      },
      service_id: {
        isVisible: { list: true, show: true, edit: true, filter: true },
        components: { edit: Components.ServiceCombobox },
      },
      // UX-BL1: denormalised convenience fields — read-only, populated from
      // a LEFT JOIN on services/agents at list time.
      service_name: {
        label: "Service Name",
        isVisible: { list: true, show: true, edit: false, filter: false },
        description: "Denormalised convenience field — the human-readable name of the service linked to this grant. Populated at list time via JOIN on services; null if the service has been deleted.",
      },
      service_slug: {
        label: "Service Slug",
        isVisible: { list: false, show: true, edit: false, filter: false },
        description: "Denormalised convenience field — the slug of the service linked to this grant. Populated at list time via JOIN on services; null if the service has been deleted.",
      },
      agent_name: {
        label: "Agent Name",
        isVisible: { list: true, show: true, edit: false, filter: false },
        description: "Denormalised convenience field — the human-readable name of the agent that holds this grant. Populated at list time via JOIN on agents; null if the agent has been deleted.",
      },
      action: {
        description:
          "What this agent is allowed to do on this service.\n\nDefault: `call` — lets the agent invoke any operation on the service. This is the right choice for most grants.\n\nAdvanced: a `<verb>:<resource>` pattern restricts the agent to a narrower subset (examples: `read:contacts`, `write:invoices`, `delete:invoices`). The agent's API key can then only request actions from this exact set; anything else is rejected with a 422.",
      },
      constraints: {
        type: "mixed",
        isArray: false,
        components: { show: Components.JsonValue },
        description:
          "Optional JSON object restricting this grant. Closed schema — unknown keys return 422.\n\nAllowed keys (all optional, mix freely):\n• rate_limit: {\"requests_per_second\": 10, \"burst\": 5}\n• time_window: {\"timezone\": \"America/New_York\", \"days\": [\"Mon\",\"Tue\",\"Wed\",\"Thu\",\"Fri\"], \"start_local\": \"09:00\", \"end_local\": \"17:00\"}\n• request_path_prefix: {\"prefix\": \"/v2/orders\"}\n• source_ip_allowlist: {\"cidrs\": [\"1.2.3.4/32\", \"10.0.0.0/8\"]}\n\nLeave empty for no restrictions.",
      },
    },
    actions: {
      list: {
        component: Components.PermissionsIntro,
      },
      new: {
        isVisible: true,
        handler: async (request, response, context) => {
          if (request.method === "get") {
            // Prefill action="call" so operators don't have to guess; ~95% of grants
            // are unrestricted invoke-the-service. They can still type a narrower
            // <verb>:<resource> pattern.
            return { record: await recordJSON(context, { action: "call" }) };
          }
          // On POST, default the action field if the form somehow submitted empty.
          if (!request.payload?.action) {
            request.payload = { ...(request.payload ?? {}), action: "call" };
          }
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          let constraints: Record<string, unknown> = {};
          try {
            constraints = request.payload?.constraints
              ? JSON.parse(request.payload.constraints as string)
              : {};
          } catch {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: "constraints must be valid JSON", type: "error" },
            };
          }

          // admin-api grant endpoint: POST /v1/tenants/{tid}/agents/{aid}/permissions
          // (tenant-wide POST /v1/tenants/{tid}/permissions does not exist — 405 if called)
          const agentId = request.payload?.agent_id as string | undefined;
          if (!agentId) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: "agent_id is required", type: "error" },
            };
          }

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}/permissions`,
            "POST",
            {
              service_id: request.payload?.service_id,
              action: request.payload?.action,
              constraints,
            },
            operatorOpts
          );

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: err.title ?? "Failed to grant permission", type: "error" },
            };
          }

          return {
            record: await recordJSON(context, request.payload ?? {}),
            notice: { message: "Permission granted", type: "success" },
            redirectUrl: "/admin/resources/permission_grants",
          };
        },
      },
      delete: {
        isVisible: true,
        handler: async (request, response, context) => {
          const { currentAdmin, record } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const permissionId = request.params.recordId;
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          // admin-api DELETE: /v1/tenants/{tid}/agents/{aid}/permissions/{pid}
          // agent_id comes from the permission record (set by normalisePermissionRecord
          // in wire-form: agent_<32hex>). Plain UUIDs also work via _wire_id_to_uuid.
          const agentId = record?.get("agent_id") as string | undefined;
          if (!agentId) {
            return {
              record: await recordJSON(context),
              notice: { message: "Cannot delete: agent_id not found in record", type: "error" },
            };
          }

          await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}/permissions/${permissionId}`,
            "DELETE",
            undefined,
            operatorOpts
          );

          return {
            record: await recordJSON(context),
            notice: { message: "Permission revoked", type: "success" },
            redirectUrl: "/admin/resources/permission_grants",
          };
        },
      },
      edit: { isVisible: false },
    },
  },
};
