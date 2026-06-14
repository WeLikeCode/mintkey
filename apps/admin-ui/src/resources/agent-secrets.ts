/**
 * AdminJS Agent Secrets resource (Chunk C6, D10, D11).
 *
 * READ: list + show agent secrets via RestResource (metadata only — no value).
 * WRITE: create via apiWrite (session + signed-request, ADR-0019).
 *
 * The plaintext secret value NEVER appears in the UI after creation
 * (ADR-0014.4, S-SEC-1). The reveal-once panel in AgentSecretNewForm
 * shows the value the operator TYPED (from component state), not the
 * API response (which has no value field).
 *
 * Source: Chunk C6; D10; D11; D13; ADR-0013; ADR-0014.4; ADR-0019.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { apiWrite, operatorOptsFromAdmin } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";
import { Components } from "../components/index.js";

const _agentSecretsResource = new RestResource({
  id: "agent-secrets",
  name: "Agent Secrets",
  listPath: "/v1/tenants/{tenantId}/agent-secrets",
  getPath: "/v1/tenants/{tenantId}/agent-secrets/{id}",
  listKey: "secrets",
  idField: "id",
  filterKeys: ["agent_id"],
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "agent_id", type: "string" },
    { path: "name", type: "string" },
    { path: "content_type", type: "string" },
    { path: "size_bytes", type: "number" },
    { path: "version", type: "number" },
    { path: "created_at", type: "datetime" },
    { path: "updated_at", type: "datetime" },
    { path: "created_by", type: "string" },
    // Virtual filter-only — never rendered as a value column
    { path: "_agent_id_filter", type: "string" },
  ],
});

export const AgentSecretsResource: ResourceWithOptions & { adminResource: typeof _agentSecretsResource } = {
  resource: _agentSecretsResource.resource,
  adminResource: _agentSecretsResource,
  options: {
    navigation: { name: "Agent Secrets", icon: "Key" },
    listProperties: ["name", "agent_id", "content_type", "size_bytes", "version", "created_at"],
    showProperties: ["id", "agent_id", "name", "content_type", "size_bytes", "version", "created_at", "updated_at", "created_by"],
    filterProperties: ["agent_id"],
    properties: {
      agent_id: {
        label: "Agent ID",
        description: "The agent this secret belongs to.",
        isVisible: { list: true, show: true, edit: false, new: false, filter: true },
      },
      name: {
        label: "Name",
        description: "Secret name — used by the agent to look up this secret via MCP (secret_get).",
      },
      content_type: {
        label: "Content Type",
        description: "MIME type hint (e.g. text/plain, application/json). Optional.",
      },
      size_bytes: {
        label: "Size (bytes)",
        description: "Encrypted size of the stored value. The plaintext value is never exposed here.",
      },
      version: {
        label: "Version",
        description: "Incremented on every update. Useful for correlating which version an agent read.",
      },
      created_by: {
        label: "Created By",
        description: "Operator who created this secret.",
      },
      _agent_id_filter: {
        isVisible: { list: false, show: false, edit: false, new: false, filter: true },
        label: "Filter by Agent ID",
      },
    },
    actions: {
      // Custom create form with reveal-once panel (D11)
      new: {
        isVisible: true,
        label: "Create Secret",
        component: Components.AgentSecretNewForm,
        handler: async (request, _response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }

          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const payload = request.payload as {
            agent_id?: string;
            name?: string;
            value?: string;
            content_type?: string;
          };

          const body: Record<string, string> = {
            agent_id: payload.agent_id ?? "",
            name: payload.name ?? "",
            value: payload.value ?? "",
          };
          if (payload.content_type) {
            body.content_type = payload.content_type;
          }

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agent-secrets`,
            "POST",
            body,
            operatorOpts
          );

          if (!resp.ok) {
            const errBody = await resp.json().catch(() => ({})) as {
              title?: string;
              detail?: string;
            };
            return {
              record: await recordJSON(context, {}),
              notice: { message: errBody.title ?? "Failed to create secret", type: "error" },
            };
          }

          return {
            record: await recordJSON(context, {}),
            notice: { message: "Secret created", type: "success" },
          };
        },
      },

      // Rotate action (C6b): replace the encrypted value; version++ on backend.
      // The reveal-once panel shows the value the operator TYPED — never from the API.
      editValue: {
        actionType: "record",
        isVisible: true,
        label: "Rotate Value",
        icon: "RefreshCw",
        component: Components.AgentSecretUpdateForm,
        handler: async (request, _response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }

          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const secretId = request.params.recordId ?? "";
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const payload = request.payload as {
            value?: string;
            content_type?: string;
          };

          const body: Record<string, string> = {
            value: payload.value ?? "",
          };
          if (payload.content_type) {
            body.content_type = payload.content_type;
          }

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agent-secrets/${secretId}`,
            "PUT",
            body,
            operatorOpts
          );

          if (!resp.ok) {
            const errBody = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context),
              notice: { message: errBody.title ?? "Failed to update secret", type: "error" },
            };
          }

          return {
            record: await recordJSON(context),
            notice: { message: "Secret value rotated", type: "success" },
          };
        },
      },

      // Delete action (C6b): purges the ciphertext; idempotent on the backend.
      delete: {
        actionType: "record",
        isVisible: true,
        label: "Delete Secret",
        icon: "Trash",
        component: Components.ConfirmAction,
        custom: {
          description: "This permanently removes the encrypted secret value. The agent will no longer be able to retrieve it.",
        },
        handler: async (request, _response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context) };
          }

          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const secretId = request.params.recordId ?? "";
          const operatorOpts = operatorOptsFromAdmin(currentAdmin as Record<string, unknown>);

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agent-secrets/${secretId}`,
            "DELETE",
            undefined,
            operatorOpts
          );

          if (!resp.ok) {
            const errBody = await resp.json().catch(() => ({})) as { title?: string };
            return {
              record: await recordJSON(context),
              notice: { message: errBody.title ?? "Failed to delete secret", type: "error" },
            };
          }

          return {
            record: await recordJSON(context),
            notice: { message: "Secret deleted", type: "success" },
            redirectUrl: `/admin/resources/agent-secrets`,
          };
        },
      },

      edit: { isVisible: false },
    },
  },
};
