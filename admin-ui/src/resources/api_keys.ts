/**
 * AdminJS API Keys resource — long-lived-api-keys tasks 9.1–9.3.
 *
 * READ:  list/show via RestResource (admin-api HTTP, GET /v1/tenants/{tid}/api-keys).
 * WRITE: createApiKey, revokeApiKey, rotateApiKey via apiWrite (session + CSRF, ADR-0014.5).
 *
 * The plaintext key is shown exactly once in the createApiKey response (ADR-0018 §1.3).
 * The default `new`/`edit`/`delete` actions are hidden — creation is only via the
 * custom `createApiKey` resource action (spec §2.7); revoke/rotate are the only
 * mutations after creation. Never exposes key_hash or plaintext_key in list/show (Req 10.1).
 *
 * Source: long-lived-api-keys tasks 9.1–9.3; Req 9.1–9.4; ADR-0013; ADR-0014.5; ADR-0018.
 */

import type { ResourceWithOptions } from "adminjs";
import { RestResource } from "../lib/rest-resource.js";
import { apiWrite } from "../lib/api-client.js";
import { recordJSON } from "../lib/record-helpers.js";

const _apiKeysResource = new RestResource({
  id: "service_api_keys", name: "API Keys",
  listPath: "/v1/tenants/{tenantId}/api-keys",
  listKey: "api_keys",
  idField: "id",
  properties: [
    { path: "id", type: "string", isId: true },
    { path: "agent_id", type: "string" },
    { path: "service_id", type: "string" },
    { path: "key_fingerprint", type: "string" },
    { path: "allowed_actions", type: "string" },
    { path: "constraints", type: "string" },
    { path: "expires_at", type: "string" },
    { path: "last_used_at", type: "string" },
    { path: "created_at", type: "datetime" },
    { path: "created_by", type: "string" },
    { path: "status", type: "string" },
  ],
});

export const ApiKeysResource: ResourceWithOptions & { adminResource: typeof _apiKeysResource } = {
  resource: _apiKeysResource.resource,
  adminResource: _apiKeysResource,
  options: {
    navigation: { name: "API Keys", icon: "Key" },
    listProperties: ["key_fingerprint", "service_id", "allowed_actions", "expires_at", "last_used_at", "status", "created_at"],
    showProperties: ["id", "key_fingerprint", "service_id", "allowed_actions", "constraints", "expires_at", "last_used_at", "created_at", "created_by", "status"],
    filterProperties: ["service_id", "status"],
    editProperties: ["agent_id", "service_id", "allowed_actions", "expires_at"],
    actions: {
      // new is hidden — creation uses the custom createApiKey action (Req 9.2; spec §2.7)
      new: { isVisible: false },
      // edit is hidden — keys are immutable after creation (ADR-0014.5)
      edit: { isVisible: false },
      // delete is hidden — revoke endpoint must be used (Req 9.3)
      delete: { isVisible: false },

      // Create a new API key (Req 9.2; ADR-0018 §1; ADR-0014.5)
      createApiKey: {
        actionType: "resource",
        label: "Create API Key",
        icon: "Plus",
        isVisible: true,
        handler: async (request, response, context) => {
          if (request.method === "get") {
            return { record: await recordJSON(context, {}) };
          }
          const { currentAdmin } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const agentId = request.payload?.agent_id as string | undefined;

          if (!agentId) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: "agent_id is required", type: "error" },
            };
          }

          const rawActions = request.payload?.allowed_actions;
          const allowed_actions: string[] = typeof rawActions === "string"
            ? rawActions.split(",").map((s: string) => s.trim()).filter(Boolean)
            : Array.isArray(rawActions) ? rawActions : [];

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}/api-keys`,
            "POST",
            {
              service_id: request.payload?.service_id,
              allowed_actions,
              constraints: request.payload?.constraints,
              expires_at: request.payload?.expires_at,
            }
          );

          const body = await resp.json().catch(() => ({})) as { plaintext_key?: string; title?: string };

          if (!resp.ok) {
            return {
              record: await recordJSON(context, request.payload ?? {}),
              notice: { message: body.title ?? "Failed to create API key", type: "error" },
            };
          }

          // Plaintext shown once — displayed in the notice banner (ADR-0018 §1.3)
          return {
            record: await recordJSON(context, request.payload ?? {}),
            notice: {
              message: body.plaintext_key
                ? `API key created. Store it now (shown once): ${body.plaintext_key}`
                : "API key created.",
              type: "success",
            },
            redirectUrl: "/admin/resources/service_api_keys",
          };
        },
      },

      // Revoke an API key (Req 9.3; ADR-0014.5)
      revokeApiKey: {
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
          const agentId = record?.get("agent_id") as string;
          const keyId = record?.get("id") as string;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}/api-keys/${keyId}/revoke`,
            "POST",
            { reason: request.payload?.reason ?? "operator_revoked" }
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
              message: "API key revoked — proxy cache evicted within ≤5s via mintkey:agent channel",
              type: "success",
            },
          };
        },
      },

      // Rotate an API key — creates new key, old key continues until revoked (Req 9.3; 5.2)
      rotateApiKey: {
        actionType: "record",
        label: "Rotate",
        icon: "RefreshCw",
        isVisible: (context) => {
          const record = context.record;
          return record?.get("status") !== "revoked";
        },
        handler: async (request, response, context) => {
          const { currentAdmin, record } = context;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const agentId = record?.get("agent_id") as string;
          const keyId = record?.get("id") as string;

          const resp = await apiWrite(
            `/v1/tenants/${tenantId}/agents/${agentId}/api-keys/${keyId}/rotate`,
            "POST"
          );

          const body = await resp.json().catch(() => ({})) as { plaintext_key?: string; title?: string };

          if (!resp.ok) {
            return {
              record: await recordJSON(context),
              notice: { message: body.title ?? "Rotation failed", type: "error" },
            };
          }

          return {
            record: await recordJSON(context),
            notice: {
              message: body.plaintext_key
                ? `New key created. Old key remains active until revoked. New key (shown once): ${body.plaintext_key}`
                : "API key rotated.",
              type: "success",
            },
            redirectUrl: "/admin/resources/service_api_keys",
          };
        },
      },
    },
  },
};
