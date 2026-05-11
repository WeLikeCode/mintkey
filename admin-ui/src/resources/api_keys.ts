/**
 * AdminJS API Keys resource — long-lived-api-keys tasks 9.1–9.3.
 *
 * READ:  list/show via @adminjs/sql (service_api_keys table).
 * WRITE: createApiKey, revokeApiKey, rotateApiKey via signed admin-api requests.
 *
 * The plaintext key is shown exactly once in the createApiKey response (ADR-0018 §1.3).
 * All writes route through the Admin REST API (ADR-0014.5).
 * Never exposes key_hash or plaintext_key in list/show (Req 10.1).
 *
 * Source: long-lived-api-keys tasks 9.1–9.3; Req 9.1–9.4; ADR-0013; ADR-0014.5; ADR-0018.
 */

import type { ResourceWithOptions } from "adminjs";
import { buildSignedRequest } from "../lib/signed-request.js";
import { RestResource } from "../lib/rest-resource.js";

const ADMIN_API_URL = process.env.ADMIN_API_URL ?? "http://admin-api:8080";

const _apiKeysResource = new RestResource({
  id: "service_api_keys", name: "API Keys",
  listPath: "/v1/tenants/{tenantId}/agents",
  listKey: "agents",
  idField: "id",
  properties: [
    { path: "id", type: "uuid", isId: true },
    { path: "name", type: "string" },
    { path: "status", type: "string" },
    { path: "api_key_fingerprint", type: "string" },
  ],
});

export const ApiKeysResource: ResourceWithOptions & { adminResource: typeof _apiKeysResource } = {
  resource: _apiKeysResource.resource,
  adminResource: _apiKeysResource,
  options: {
    navigation: { name: "API Keys", icon: "Key" },
    listProperties: [
      "key_fingerprint",
      "service_id",
      "allowed_actions",
      "expires_at",
      "last_used_at",
      "status",
      "created_at",
    ],
    showProperties: [
      "id",
      "key_fingerprint",
      "service_id",
      "allowed_actions",
      "constraints",
      "expires_at",
      "last_used_at",
      "created_at",
      "created_by",
      "status",
    ],
    filterProperties: ["service_id", "status"],
    actions: {
      // new is hidden — creation uses the custom createApiKey action (Req 9.2)
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
          const { currentAdmin, record } = context;
          const operatorId = (currentAdmin as { operatorId: string }).operatorId;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const agentId = request.payload?.agent_id as string | undefined;

          if (!agentId) {
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: "agent_id is required", type: "error" },
            };
          }

          const jwt = await buildSignedRequest({ operatorId, tenantId });
          const resp = await fetch(
            `${ADMIN_API_URL}/v1/tenants/${tenantId}/agents/${agentId}/api-keys`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${jwt}`,
              },
              body: JSON.stringify({
                service_id: request.payload?.service_id,
                allowed_actions: request.payload?.allowed_actions,
                constraints: request.payload?.constraints,
                expires_at: request.payload?.expires_at,
              }),
            }
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Failed to create API key", type: "error" },
            };
          }

          const data = await resp.json() as { plaintext_key?: string };
          // Plaintext shown once — displayed in the notice banner (ADR-0018 §1.3)
          return {
            record: record?.toJSON(currentAdmin) ?? {},
            notice: {
              message: data.plaintext_key
                ? `API key created. Store it now (shown once): ${data.plaintext_key}`
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
          const operatorId = (currentAdmin as { operatorId: string }).operatorId;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const agentId = record?.get("agent_id") as string;
          const keyId = record?.get("id") as string;

          const jwt = await buildSignedRequest({ operatorId, tenantId });
          const resp = await fetch(
            `${ADMIN_API_URL}/v1/tenants/${tenantId}/agents/${agentId}/api-keys/${keyId}/revoke`,
            {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                Authorization: `Bearer ${jwt}`,
              },
              body: JSON.stringify({ reason: request.payload?.reason ?? "operator_revoked" }),
            }
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
          const operatorId = (currentAdmin as { operatorId: string }).operatorId;
          const tenantId = (currentAdmin as { tenantId: string }).tenantId;
          const agentId = record?.get("agent_id") as string;
          const keyId = record?.get("id") as string;

          const jwt = await buildSignedRequest({ operatorId, tenantId });
          const resp = await fetch(
            `${ADMIN_API_URL}/v1/tenants/${tenantId}/agents/${agentId}/api-keys/${keyId}/rotate`,
            {
              method: "POST",
              headers: { Authorization: `Bearer ${jwt}` },
            }
          );

          if (!resp.ok) {
            const err = await resp.json() as { title?: string };
            return {
              record: record?.toJSON(currentAdmin) ?? {},
              notice: { message: err.title ?? "Rotation failed", type: "error" },
            };
          }

          const data = await resp.json() as { plaintext_key?: string };
          return {
            record: record?.toJSON(currentAdmin) ?? {},
            notice: {
              message: data.plaintext_key
                ? `New key created. Old key remains active until revoked. New key (shown once): ${data.plaintext_key}`
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
