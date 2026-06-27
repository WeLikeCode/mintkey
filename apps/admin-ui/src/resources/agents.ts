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
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

const _agentsResource = new RestResource({
  id: "agents", name: "Agents",
  listPath: "/v1/tenants/{tenantId}/agents",
  getPath: "/v1/tenants/{tenantId}/agents/{id}",
  listKey: "agents",
  idField: "id",
  filterKeys: ["q", "has_access_to_service_id", "status"],
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "name", type: "string" },
    { path: "description", type: "string" },
    { path: "status", type: "string" },
    { path: "api_key_fingerprint", type: "string" },
    { path: "api_key_expires_at", type: "datetime" },
    { path: "api_key_version", type: "number" },
    { path: "api_key_last_rotated_at", type: "datetime" },
    { path: "mcp_endpoint", type: "string" },
    { path: "rate_limit_rps", type: "number" },
    { path: "created_at", type: "datetime" },
    { path: "updated_at", type: "datetime" },
    { path: "grants_count", type: "number" },
    // Virtual filter-only properties
    { path: "q", type: "string" },
    { path: "has_access_to_service_id", type: "string" },
    // Virtual show-page properties
    { path: "_grants_warning", type: "string" },
  ],
});

export const AgentsResource: ResourceWithOptions & { adminResource: typeof _agentsResource } = {
  resource: _agentsResource.resource,
  adminResource: _agentsResource,
  options: {
    navigation: { name: "Agents", icon: "Bot" },
    // api_key_fingerprint in list/show — NEVER api_key (S-SEC-1)
    listProperties: ["id", "name", "status", "grants_count", "api_key_fingerprint", "api_key_expires_at", "rate_limit_rps", "created_at"],
    showProperties: ["_grants_warning", "id", "name", "description", "status", "api_key_fingerprint", "api_key_expires_at", "api_key_version", "api_key_last_rotated_at", "mcp_endpoint", "rate_limit_rps", "created_at", "updated_at"],
    editProperties: ["name", "description", "mcp_endpoint", "rate_limit_rps"],
    filterProperties: ["q", "has_access_to_service_id", "name", "status"],
    properties: {
      _grants_warning: {
        isVisible: { show: true, list: false, edit: false, new: false, filter: false },
        components: { show: Components.AgentGrantsWarningPanel },
      },
      grants_count: {
        label: "Grants",
        description: "Number of permission grants assigned to this agent. Zero means the agent can authenticate but will be denied on every service call.",
      },
      api_key_fingerprint: {
        label: "API Key Fingerprint (SHA-256 prefix)",
        description: "First 16 hex chars of SHA-256(api_key). Safe to share in logs and audit events; cannot be reversed to the plaintext key. Use this to identify a key in audit events without exposing the secret.",
      },
      api_key_expires_at: {
        label: "API Key Expires",
        description: "When this agent's API key will stop authenticating. 'Never' means the key has no expiry (rotate manually via the Rotate Key action).",
        components: {
          list: Components.AgentExpiryDisplay,
          show: Components.AgentExpiryDisplay,
        },
      },
      api_key_version: {
        label: "API Key Version",
        description: "Incremented on every rotation. Useful for correlating audit events to a specific key generation.",
      },
      api_key_last_rotated_at: {
        label: "API Key Last Rotated",
        description: "Timestamp of the most recent key rotation. Blank means the key has never been rotated since creation.",
      },
      mcp_endpoint: {
        description: "URL to copy into your MCP client configuration as `mcpServers.mintkey.url`. The `/v1/agents/{agent_id}` suffix is informational only — actual MCP tool routes live under `/v1/tools/*` and the agent is identified by the bearer API key, not the URL path.",
      },
      rate_limit_rps: {
        description: "Requests per second cap. Blank = no limit. `0` = block ALL requests (emergency stop).",
      },
      status: {
        isVisible: { list: true, show: true, edit: false, filter: true },
        availableValues: [
          { value: "active", label: "active" },
          { value: "revoked", label: "revoked" },
        ],
      },
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
        // (OPS-DDEE DD-2) Custom component renders the API key with a Copy button.
        component: Components.AgentCreatedNotice,
        handler: async (request, response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents`,
            "POST",
            request.payload,
            operatorOpts
          );

          const body = await resp.json().catch(() => ({})) as { api_key?: string; id?: string; title?: string };

          if (!resp.ok) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: body.title ?? "Failed to create agent", type: "error" },
            };
          }

          // (OPS-DDEE DD-2) Embed api_key + agent_id in record.params so
          // AgentCreatedNotice component can read them for the Copy button.
          // The notice message retains the bracket form for E2E test compatibility.
          const baseRecord = await recordJSON(context, request.payload ?? {});
          return {
            record: {
              ...baseRecord,
              params: {
                ...baseRecord.params,
                // DD-2: one-time key fields for AgentCreatedNotice component
                created_agent_id: body.id ?? "",
                created_api_key: body.api_key ?? "",
              },
            },
            notice: {
              // Retain legacy message format for E2E + vitest compatibility
              message: body.api_key
                ? `Agent created [${body.id}]. API key (shown once): ${body.api_key}`
                : `Agent created [${body.id}].`,
              type: "success",
            },
            // No redirectUrl — AgentCreatedNotice handles navigation
          };
        },
      },

      delete: {
        isVisible: true,
        component: Components.ConfirmAction,
        handler: async (request, response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          // Pass the wire-form ID as-is — admin-api _wire_id_to_uuid handles both
          // Crockford (canonical post-#13) and legacy 32-hex forms.
          const agentId = request.params.recordId ?? "";
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}`,
            "DELETE",
            undefined,
            operatorOpts
          );

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context),
              notice: { message: err.title ?? "Failed to delete agent", type: "error" },
            };
          }

          return {
            record: await recordJSON(context),
            notice: { message: "Agent deleted", type: "success" },
            redirectUrl: "/admin/resources/agents",
          };
        },
      },

      // T-1.9.4: Revoke action
      revokeAgent: {
        actionType: "record",
        component: Components.ConfirmAction,
        label: "Revoke",
        icon: "Ban",
        // UX-CLARITY chunk H: warning routed via action.custom.description because
        // AdminJS does NOT serialize action.description — only action.custom is part
        // of ActionJSON (action-decorator.ts:339-360).
        custom: {
          description: "Revocation is permanent — to restore access, create a new agent.",
        },
        // isVisible receives RecordJSON (plain object, no .get()) during HTML routing —
        // use params.status to avoid TypeError that AdminJS catches as a 404.
        isVisible: (context) => {
          const rec = context.record as { params?: Record<string, unknown> } | undefined;
          return rec?.params?.status !== "revoked";
        },
        handler: async (request, response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          // Pass the wire-form ID as-is — admin-api _wire_id_to_uuid handles both
          // Crockford (canonical post-#13) and legacy 32-hex forms.
          const agentId = request.params.recordId ?? "";
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}/revoke`,
            "POST",
            undefined,
            operatorOpts
          );

          if (!resp.ok) {
            const err = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context),
              notice: { message: err.title ?? "Revocation failed", type: "error" },
            };
          }

          const respBody = await resp.json().catch(() => ({})) as {
            active_api_keys_count?: number;
          };
          const keys = respBody.active_api_keys_count ?? 0;
          const apiKeysUrl = `/admin/resources/service_api_keys?filters.agent_id=${agentId}`;
          const baseMessage = "Agent revoked — propagates to proxy plugin within ≤5s via mintkey:agent channel.";
          const warningMessage = keys > 0
            ? `${baseMessage} ⚠ ${keys} classical API key${keys === 1 ? "" : "s"} for this agent remain active and are NOT auto-revoked. Review at ${apiKeysUrl} and revoke each one if no longer needed.`
            : baseMessage;
          return {
            record: await recordJSON(context),
            notice: { message: warningMessage, type: keys > 0 ? "error" : "success" },
          };
        },
      },

      // C6: Manage secrets — navigate to agent-secrets resource filtered by this agent
      manageSecrets: {
        actionType: "record",
        component: Components.RedirectAction,
        label: "Manage Secrets",
        icon: "Key",
        isVisible: true,
        handler: async (request, _response, context) => {
          const { record } = context;
          const agentId = record?.get("id") as string ?? request.params.recordId ?? "";
          return {
            record: await recordJSON(context),
            redirectUrl: `/admin/resources/agent-secrets/actions/new?agent_id=${agentId}`,
          };
        },
      },

      // UX-FB-AK-2: Rotate Key action — hard cutover, invalidates old key immediately
      rotateAgentKey: {
        actionType: "record",
        component: Components.AgentKeyRotatedNotice,
        label: "Rotate Key",
        icon: "RefreshCw",
        custom: {
          description: "Hard cutover: the current API key is invalidated the instant you confirm. Have your agent runtime ready to receive the new key.",
        },
        isVisible: (context) => {
          const rec = context.record as { params?: Record<string, unknown> } | undefined;
          return rec?.params?.status !== "revoked";
        },
        handler: async (request, response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const agentId = request.params.recordId ?? "";
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}/rotate-key`,
            "POST",
            request.payload ?? {},
            operatorOpts
          );
          const body = await resp.json().catch(() => ({})) as {
            api_key?: string;
            api_key_fingerprint?: string;
            api_key_expires_at?: string | null;
            api_key_version?: number;
            api_key_last_rotated_at?: string | null;
            title?: string;
          };

          if (!resp.ok) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: body.title ?? "Rotation failed", type: "error" },
            };
          }

          const baseRecord = await recordJSON(context, request.payload ?? {});
          return {
            record: {
              ...baseRecord,
              params: {
                ...baseRecord.params,
                rotated_agent_id: agentId,
                rotated_api_key: body.api_key ?? "",
                rotated_api_key_fingerprint: body.api_key_fingerprint ?? "",
                rotated_api_key_expires_at: body.api_key_expires_at ?? null,
                rotated_api_key_version: body.api_key_version ?? null,
                rotated_api_key_last_rotated_at: body.api_key_last_rotated_at ?? null,
              },
            },
            notice: {
              message: `API key rotated for agent [${agentId}]. The old key is now invalid.`,
              type: "success",
            },
          };
        },
      },
    },
  },
};
